"""Fabrication files and pictures for one board (KiCad 7 kicad-cli):
    python3 make_outputs.py tht|smd
  -> ../gerber_<b>/ (gerbers + Excellon drill + maps), ../kill_switch_<b>_gerber_jlcpcb.zip,
     ../kill_switch_<b>_kicad.zip (board, project, scripts, ks.pretty and the bundled 3D models it uses),
     ../docs/board_<b>_top.png, board_<b>_bottom.png, board_<b>_layers.png"""
import glob, os, re, subprocess, sys, zipfile
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)
b = sys.argv[1]
pcb = os.path.join(HERE, f"ks_{b}.kicad_pcb")
gdir = os.path.join(ROOT, f"gerber_{b}"); os.makedirs(gdir, exist_ok=True)
run = lambda *a: subprocess.run(list(a), check=True, capture_output=True, text=True)
LAY = "F.Cu,B.Cu,F.Paste,B.Paste,F.Silkscreen,B.Silkscreen,F.Mask,B.Mask,Edge.Cuts"
run("kicad-cli", "pcb", "export", "gerbers", "--layers", LAY, "--subtract-soldermask", "-o", gdir + "/", pcb)
run("kicad-cli", "pcb", "export", "pos", "--format", "csv", "--units", "mm", "--side", "both", "-o", os.path.join(gdir, f"ks_{b}-pos.csv"), pcb)
run("kicad-cli", "pcb", "export", "drill", "--format", "excellon", "--excellon-separate-th", "--generate-map",
    "--map-format", "gerberx2", "-o", gdir + "/", pcb)
stem = f"ks_{b}"
fab = sorted(f for f in glob.glob(os.path.join(gdir, stem + "*")) if not f.endswith(".gbrjob"))
with zipfile.ZipFile(os.path.join(ROOT, f"kill_switch_{b}_gerber_jlcpcb.zip"), "w", zipfile.ZIP_DEFLATED) as z:
    for f in fab: z.write(f, os.path.basename(f))
# KiCad project zip: everything needed to open it (with 3D view) and to rebuild it
t = open(pcb).read()
models = sorted(set(re.findall(r'\$\{KIPRJMOD\}/3dmodels/([^"]+)"', t)))
files = [f"ks_{b}.kicad_pcb", f"ks_{b}.kicad_pro", f"ks_{b}.kicad_prl", f"ks_{b}.kicad_dru", f"bom_{b}.csv", f"bom_{b}_grouped.csv",
         f"drc_{b}.rpt", f"build_{b}.py", f"route_{b}.py", "build_ks.py", "route_ks.py", "gridroute.py", "bundle_3d.py",
         "make_xt90.py", "make_bom.py", "make_outputs.py", "duburi_logo.png", "build_tht.py", "route_tht.py", "fp-lib-table"]
files += [os.path.join("ks.pretty", os.path.basename(p)) for p in glob.glob(os.path.join(HERE, "ks.pretty", "*.kicad_mod"))]
files += [os.path.join("3dmodels", m) for m in models]
with zipfile.ZipFile(os.path.join(ROOT, f"kill_switch_{b}_kicad.zip"), "w", zipfile.ZIP_DEFLATED) as z:
    for f in dict.fromkeys(files):
        p = os.path.join(HERE, f)
        if os.path.exists(p): z.write(p, os.path.join("kicad", f))
    z.writestr("kicad/OPEN_ME.txt", f"Open kicad/ks_{b}.kicad_pro (or ks_{b}.kicad_pcb) in KiCad 7, 8, 9 or 10.\n"
               "The 3D models are in kicad/3dmodels and are found through ${KIPRJMOD}, so keep the folder together.\n")
# pictures: a green-solder-mask render of each side (like the made board) and the two copper layers
import numpy as np
from PIL import Image
docs = os.path.join(ROOT, "docs"); os.makedirs(docs, exist_ok=True)
tmp = os.path.join(HERE, "__pycache__"); os.makedirs(tmp, exist_ok=True)
ZOOM = "6"
def layer_png(layer, mirror=False, colour=False):
    svg = os.path.join(tmp, f"{b}_{layer}.svg"); png = svg[:-4] + ".png"
    args = ["kicad-cli", "pcb", "export", "svg", "--layers", layer + ",Edge.Cuts", "--page-size-mode", "2",
            "--exclude-drawing-sheet", "-o", svg, pcb]
    if not colour: args.insert(4, "--black-and-white")
    if mirror: args.insert(4, "--mirror")
    run(*args); run("rsvg-convert", "-z", ZOOM, "-b", "white", "-o", png, svg)
    return png
def ink(png): return np.asarray(Image.open(png).convert("L")) < 128
for side, cu, mask, silk, mirror in (("top", "F.Cu", "F.Mask", "F.Silkscreen", False), ("bottom", "B.Cu", "B.Mask", "B.Silkscreen", True)):
    c, m, k = ink(layer_png(cu, mirror)), ink(layer_png(mask, mirror)), ink(layer_png(silk, mirror))
    h, w = c.shape
    img = np.zeros((h, w, 3), np.uint8); img[:] = (22, 92, 48)                  # green solder mask over bare FR4
    img[c] = (40, 130, 66)                                                     # copper under the mask: lighter green
    img[m & ~c] = (196, 178, 120)                                              # mask opening without copper: FR4
    img[m & c] = (205, 208, 214)                                               # bare copper, tinned (HASL): silver
    img[k & ~m] = (245, 245, 240)                                              # white silkscreen (not on bare copper)
    gray = np.asarray(Image.open(layer_png(cu, mirror)).convert("L"))           # drill holes show white inside pads
    img[(gray > 250) & m & ~c] = (25, 25, 25)
    Image.fromarray(img).save(os.path.join(docs, f"board_{b}_{side}.png"))
svg = os.path.join(tmp, f"{b}_layers.svg")
run("kicad-cli", "pcb", "export", "svg", "--layers", "F.Cu,B.Cu,F.Silkscreen,Edge.Cuts", "--page-size-mode", "2", "--exclude-drawing-sheet", "-o", svg, pcb)
run("rsvg-convert", "-z", ZOOM, "-b", "white", "-o", os.path.join(docs, f"board_{b}_layers.png"), svg)
print(f"{b}: {len(fab)} fab files, {len(models)} 3D models in the project zip, pictures in docs/")
