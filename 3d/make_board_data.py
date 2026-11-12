"""Board texture (board_top.jpg) and part boxes (board_parts.json) for the 3D tutorial, read from
../kicad/ks_power.kicad_pcb. Run with KiCad 7's python:  /usr/bin/python3 make_board_data.py"""
import json, math, os
import pcbnew
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
PCB = os.path.join(HERE, "..", "kicad", "ks_power.kicad_pcb")
OX = OY = 100.0
W, H = 118.0, 120.0
S = 10                                   # px per mm
MASK, CU_MASK, PAD, SILK, HOLE = (12, 84, 50), (30, 118, 70), (205, 205, 200), (240, 240, 235), (25, 25, 25)

b = pcbnew.LoadBoard(PCB)
mm = pcbnew.ToMM
px = lambda x, y: ((mm(x) - OX) * S, (mm(y) - OY) * S)
img = Image.new("RGB", (int(W * S), int(H * S)), MASK)
d = ImageDraw.Draw(img)

# copper pours on F.Cu (seen through the mask)
for z in [b.GetArea(i) for i in range(b.GetAreaCount())]:
    if z.GetIsRuleArea() or not z.IsOnLayer(pcbnew.F_Cu): continue
    ps = z.GetFilledPolysList(pcbnew.F_Cu)
    for i in range(ps.OutlineCount()):
        o = ps.Outline(i)
        d.polygon([px(o.CPoint(j).x, o.CPoint(j).y) for j in range(o.PointCount())], fill=CU_MASK)
        for h in range(ps.HoleCount(i)):
            hp = ps.Hole(i, h)
            d.polygon([px(hp.CPoint(j).x, hp.CPoint(j).y) for j in range(hp.PointCount())], fill=MASK)
# tracks and vias
for t in b.GetTracks():
    if t.GetClass() == "PCB_VIA":
        x, y = px(t.GetPosition().x, t.GetPosition().y); r = mm(t.GetWidth()) / 2 * S; rd = mm(t.GetDrill()) / 2 * S
        d.ellipse([x - r, y - r, x + r, y + r], fill=CU_MASK); d.ellipse([x - rd, y - rd, x + rd, y + rd], fill=HOLE)
    elif t.GetLayer() == pcbnew.F_Cu:
        w = max(1, int(round(mm(t.GetWidth()) * S)))
        a, c = px(t.GetStart().x, t.GetStart().y), px(t.GetEnd().x, t.GetEnd().y)
        d.line([a, c], fill=CU_MASK, width=w)
        for p in (a, c): d.ellipse([p[0] - w / 2, p[1] - w / 2, p[0] + w / 2, p[1] + w / 2], fill=CU_MASK)
# pads (exposed, tinned)
for fp in b.GetFootprints():
    for p in fp.Pads():
        if not (p.IsOnLayer(pcbnew.F_Cu) or p.GetAttribute() == pcbnew.PAD_ATTRIB_NPTH): continue
        x, y = px(p.GetPosition().x, p.GetPosition().y)
        sx, sy = mm(p.GetSize().x) * S / 2, mm(p.GetSize().y) * S / 2
        a = math.radians(-p.GetOrientationDegrees())
        npth = p.GetAttribute() == pcbnew.PAD_ATTRIB_NPTH
        if p.GetShape() == pcbnew.PAD_SHAPE_CIRCLE or npth:
            r = max(sx, sy)
            d.ellipse([x - r, y - r, x + r, y + r], fill=MASK if npth else PAD)
        else:
            pts = [(x + cx * math.cos(a) - cy * math.sin(a), y + cx * math.sin(a) + cy * math.cos(a)) for cx, cy in ((-sx, -sy), (sx, -sy), (sx, sy), (-sx, sy))]
            d.polygon(pts, fill=PAD)
        if p.GetDrillSize().x > 0:
            r = mm(p.GetDrillSize().x) / 2 * S
            d.ellipse([x - r, y - r, x + r, y + r], fill=HOLE)
# silkscreen labels that matter in the video
def font(sz):
    for f in ("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"):
        if os.path.exists(f): return ImageFont.truetype(f, sz)
    return ImageFont.load_default()
F2, F3, F4 = font(int(2.0 * S)), font(int(2.6 * S)), font(int(3.6 * S))
def label(x, y, s, f=F2, anchor="mm"): d.text((x * S, y * S), s, fill=SILK, font=f, anchor=anchor)
F15 = font(int(1.5 * S))
for x, s in ((48, "HALL"), (53, "REED"), (58, "SAFE"), (63, "LIVE")):
    d.text((x * S, 117.4 * S), s, fill=SILK, font=F15, anchor="mm")
label(20, 109.6, "J4 HALL"); label(33, 109.6, "J6 REED"); label(95.75, 109.6, "J5 STATUS")
label(58, 17.5, "BAT+ IN", F3); label(58, 64.5, "OUT+ ESC", F3); label(5.75, 57, "GND", F3)
label(55, 79.0, "MAGNETIC KILL SWITCH  150 A", F3)
label(55, 39.8, "8 x IPT007N06N  (VIN -> VOUT)", F2)
img = img.resize((int(W * 8), int(H * 8)), Image.LANCZOS)
img.save(os.path.join(HERE, "board_top.jpg"), quality=86)

# part boxes for the 3D model: ref, kind, centre x/y, size x/y (mm, board coordinates)
parts = []
for fp in b.GetFootprints():
    ref = fp.GetReference(); name = fp.GetFPID().GetLibItemName().wx_str()
    if ref.startswith("H") or "MountingHole" in name and not ref.startswith("J"): continue
    bb = fp.GetBoundingBox(False, False)
    cx, cy = mm(bb.GetCenter().x) - OX, mm(bb.GetCenter().y) - OY
    w, h = mm(bb.GetWidth()), mm(bb.GetHeight())
    kind = ("fet" if name.startswith("Infineon") else "led" if name.startswith("LED") else "jst" if name.startswith("JST") else
            "stud" if "MountingHole" in name else "ic" if name.startswith(("MSOP", "SOIC", "SMDIP", "SOT-223", "TO-252")) else
            "tvs" if name.startswith("D_SMC") else "sot" if name.startswith("SOT-23") else "small")
    if kind == "stud": cx, cy = mm(fp.GetPosition().x) - OX, mm(fp.GetPosition().y) - OY
    parts.append([ref, kind, round(cx, 2), round(cy, 2), round(w, 2), round(h, 2), fp.GetValue()])
json.dump(parts, open(os.path.join(HERE, "board_parts.json"), "w"))
print(len(parts), "parts; texture", img.size)
