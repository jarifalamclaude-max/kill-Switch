"""Board texture and part list for the 3D tutorial, read from ../kicad/ks_tht.kicad_pcb (read only).

  /usr/bin/python3 make_board_data.py      (KiCad 7's python, kicad-cli and rsvg-convert on the PATH)

Exports F.Cu, F.Mask, F.Silkscreen and Edge.Cuts as SVG with kicad-cli into a temporary folder, rasterises them
with rsvg-convert, paints a green solder-mask board (copper under the mask, tinned pads, drilled holes, white
silkscreen) and writes it, with every footprint's position and pads, into index.html between the BOARD markers.
Board-level silkscreen texts that are not in TEXTS_KEPT are left out of the picture.
"""
import base64, io, json, os, re, subprocess, tempfile
import pcbnew
from PIL import Image, ImageChops, ImageDraw, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
PCB = os.path.join(HERE, "..", "kicad", "ks_tht.kicad_pcb")
PAGE = os.path.join(HERE, "index.html")
OX = OY = 100.0                  # KiCad page offset used by build_tht.py
W, H = 123.0, 100.0
S = 10                           # px per mm
TEXTS_KEPT = ("MAGNETIC KILL SWITCH", "4S-6S LiPo", "VIN + VOUT", "tabs are all VIN")
MASK, MASK_CU, PAD, FR4, SILK, HOLE = (22, 92, 54), (40, 122, 72), (196, 198, 190), (190, 172, 120), (238, 240, 232), (16, 18, 16)

mm = pcbnew.ToMM
b = pcbnew.LoadBoard(PCB)

# ------------------------------------------------------------------ layer pictures
tmp = tempfile.mkdtemp(prefix="ks_tht_svg_")
def layer(name):
    svg = os.path.join(tmp, name + ".svg")
    subprocess.run(["kicad-cli", "pcb", "export", "svg", "--layers", name + ",Edge.Cuts" if name != "Edge.Cuts" else name,
                    "--black-and-white", "--page-size-mode", "2", "--exclude-drawing-sheet", "--drill-shape-opt", "2",
                    "-o", svg, PCB], check=True, capture_output=True)
    return svg
svgs = {n: layer(n) for n in ("Edge.Cuts", "F.Cu", "F.Mask", "F.Silkscreen")}
head = open(svgs["Edge.Cuts"]).read()
vb = [float(v) for v in re.search(r'viewBox="([^"]+)"', head).group(1).split()]
xs = [float(v) for v in re.findall(r"[ML]([-\d.]+) [-\d.]+", head)]
ys = [float(v) for v in re.findall(r"[ML][-\d.]+ ([-\d.]+)", head)]
x0, y0 = min(xs), min(ys)        # SVG position of the board's top-left corner (centre of the 0.1 mm edge line)

def raster(name):
    png = os.path.join(tmp, name + ".png")
    subprocess.run(["rsvg-convert", "-b", "white", "-w", str(round(vb[2] * S)), "-h", str(round(vb[3] * S)), "-o", png, svgs[name]], check=True)
    im = Image.open(png).convert("L")
    im = im.crop((round(x0 * S), round(y0 * S), round((x0 + W) * S), round((y0 + H) * S)))
    return im.point(lambda v: 255 if v < 128 else 0)          # 255 where the layer has something

cu, mask_open, silk = raster("F.Cu"), raster("F.Mask"), raster("F.Silkscreen")

# leave out board-level texts that are not on the list (a name, for example)
blank = ImageDraw.Draw(silk)
for d in b.GetDrawings():
    if d.GetClass() == "PCB_TEXT" and d.GetLayer() == pcbnew.F_SilkS and not d.GetShownText().startswith(TEXTS_KEPT):
        bb = d.GetBoundingBox()
        blank.rectangle([(mm(bb.GetLeft()) - OX - 0.6) * S, (mm(bb.GetTop()) - OY - 0.6) * S,
                         (mm(bb.GetRight()) - OX + 0.6) * S, (mm(bb.GetBottom()) - OY + 0.6) * S], fill=0)

size = cu.size
img = Image.new("RGB", size, MASK)
img.paste(Image.new("RGB", size, MASK_CU), mask=cu)
bare = ImageChops.subtract(mask_open, cu)
img.paste(Image.new("RGB", size, FR4), mask=bare)
img.paste(Image.new("RGB", size, PAD), mask=ImageChops.multiply(mask_open, cu))
# drilled holes from the pads (the black and white plot paints them white, which would read as bare copper)
d = ImageDraw.Draw(img)
for fp in b.GetFootprints():
    for p in fp.Pads():
        if p.GetDrillSize().x > 0:
            x, y = (mm(p.GetPosition().x) - OX) * S, (mm(p.GetPosition().y) - OY) * S
            r = mm(p.GetDrillSize().x) / 2 * S
            d.ellipse([x - r, y - r, x + r, y + r], fill=HOLE)
for t in b.GetTracks():
    if t.GetClass() == "PCB_VIA":
        x, y = (mm(t.GetPosition().x) - OX) * S, (mm(t.GetPosition().y) - OY) * S
        r = mm(t.GetDrill()) / 2 * S
        d.ellipse([x - r, y - r, x + r, y + r], fill=HOLE)
img.paste(Image.new("RGB", size, SILK), mask=silk.filter(ImageFilter.GaussianBlur(0.4)))
img = img.filter(ImageFilter.UnsharpMask(radius=1.2, percent=60, threshold=2))
buf = io.BytesIO()
img.save(buf, "JPEG", quality=84, optimize=True, progressive=True)
img.save(os.path.join(tmp, "board_top.jpg"), "JPEG", quality=84)

# ------------------------------------------------------------------ parts
parts = []
for fp in sorted(b.GetFootprints(), key=lambda f: f.GetReference()):
    p = fp.GetPosition()
    pads = []
    for pad in fp.Pads():
        q = pad.GetPosition()
        pads.append([pad.GetNumber(), round(mm(q.x) - OX, 3), round(mm(q.y) - OY, 3), round(mm(pad.GetDrillSize().x), 2)])
    pads.sort(key=lambda r: (len(r[0]), r[0]))
    parts.append({"ref": fp.GetReference(), "fp": fp.GetFPID().GetLibItemName().wx_str(), "val": fp.GetValue(),
                  "x": round(mm(p.x) - OX, 3), "y": round(mm(p.y) - OY, 3), "rot": round(fp.GetOrientationDegrees(), 1), "pads": pads})

data = {"w": W, "h": H, "parts": parts, "tex": "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()}
block = "/*BOARD:BEGIN*/const BOARD = " + json.dumps(data, separators=(",", ":")) + ";/*BOARD:END*/"
page = open(PAGE).read()
page, n = re.subn(r"/\*BOARD:BEGIN\*/.*?/\*BOARD:END\*/", lambda m: block, page, flags=re.S)
if n != 1:
    raise SystemExit("index.html has no BOARD markers")
open(PAGE, "w").write(page)
print(f"{len(parts)} parts, texture {img.size[0]}x{img.size[1]} px, {len(buf.getvalue()) // 1024} kB; preview in {tmp}")
