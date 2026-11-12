"""Route the through-hole kill switch (ks_tht.kicad_pcb), run after build_tht.py with KiCad 7's python.

1. Hand-routed on B.Cu: each gate pin -> its 10 Ohm and 1 MOhm, the gate bus, and the VIN_K link out of the
   power section, so the VIN and VOUT pours on F.Cu stay whole.
2. Grid router for everything else, with 0/45/90-degree segments only. F.Cu is kept out of the power pours;
   wide tracks (0.9 mm) for the pre-charge path, 0.6 mm for supplies and the gate bus, 0.35 mm for signals.
3. Every 90-degree corner the router leaves is cut at 45 degrees (where the cut clears other copper).
4. Pours: VIN and VOUT on F.Cu (solid to the pads), GND on both layers (thermal spokes; solid on the XT60 and
   TVS pins), then the BRACU Duburi logo and the designer's name, zone fill, DRC report.
"""
import os, sys, math
import numpy as np
import pcbnew
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from gridroute import GridRouter
from route_ks import helpers, trim_dangling, OX, OY, P, mm
from build_tht import W, H, FET_X, NFET

B_CU, F_CU = pcbnew.B_Cu, pcbnew.F_Cu
NAME = "Md. Jarif Alam 13"
VIN_POLY = [(0.0, 0.0), (110.0, 0.0), (110.0, 13.97), (15.0, 13.97), (15.0, 16.5), (0.0, 16.5)]
VOUT_POLY = [(23.0, 13.97), (118.0, 13.97), (118.0, 30.0), (23.0, 30.0)]
CLR = 0.45                                         # track to other copper: room for hand soldering, nothing between pins
WIDE = {"PCD": 0.9, "PCF": 0.9}
# (mask layer, rectangle): VIN on top above the MOSFET pins, VOUT on top between the 1 MOhm and 10 Ohm resistors,
# GND underneath from the battery XT60 to the ESC XT60
WIRE_STRIPS = [(pcbnew.F_Mask, (12.0, 7.3, 80.0, 8.9)), (pcbnew.F_Mask, (36.0, 21.7, 109.0, 23.7)),
               (pcbnew.B_Mask, (31.0, 7.3, 108.6, 8.9)), (pcbnew.B_Mask, (107.0, 8.9, 108.6, 24.0))]
MID = {"VIN_K": 0.6, "SRC": 0.6, "V5": 0.6, "V12F": 0.5, "FG": 0.6, "VR1": 0.6, "VR2": 0.6, "DRV": 0.4}

BODIES = []
def bodies(b):
    """Courtyard boxes of the small parts: tracks stay out of them unless there is no other way."""
    out = []
    for fp in b.GetFootprints():
        ref = fp.GetReference()
        if ref.startswith(("H", "TP", "J1", "J2")) or ref in ("Q1", "Q2", "Q3", "Q4", "Q5"): continue
        xs, ys = [], []
        for g in fp.GraphicalItems():
            if g.GetLayer() == pcbnew.F_CrtYd:
                bb = g.GetBoundingBox(); xs += [bb.GetLeft(), bb.GetRight()]; ys += [bb.GetTop(), bb.GetBottom()]
        if xs: out.append((pcbnew.ToMM(min(xs)) - OX, pcbnew.ToMM(min(ys)) - OY, pcbnew.ToMM(max(xs)) - OX, pcbnew.ToMM(max(ys)) - OY))
    return out

def route_nets(b, nets, width, keep, label, tries=6):
    """Route the given net codes with one track width; retry failed nets first."""
    name = lambda c: b.GetNetInfo().GetNetItem(c).GetNetname()
    pads = {}
    for fp in b.GetFootprints():
        for p in fp.Pads():
            if p.GetNetCode() in nets: pads.setdefault(p.GetNetCode(), []).append(complex(pcbnew.ToMM(p.GetPosition().x), pcbnew.ToMM(p.GetPosition().y)))
    hpwl = lambda c: (max(z.real for z in pads[c]) - min(z.real for z in pads[c])) + (max(z.imag for z in pads[c]) - min(z.imag for z in pads[c]))
    order = sorted([c for c in pads if len(pads[c]) > 1 or c in nets], key=hpwl)
    failed = []
    for attempt in range(tries):
        r = GridRouter(b, OX, OY, W, H, clearance=CLR, track_w=width, keepouts=keep, bcu_cost=2.2)
        r.octilinear = True
        for (x0, y0, x1, y1) in BODIES: r.soft_box(x0, y0, x1, y1, 0, 6.0); r.soft_box(x0, y0, x1, y1, 1, 2.0)
        failed = [c for c in order if not r.route_net(c)[0]]
        print(f"  {label} attempt {attempt}: failed {[name(c) for c in failed]}")
        if not failed: return []
        mine = set(order)
        for t in list(b.GetTracks()):
            if not t.IsLocked() and t.GetNetCode() in mine: b.Remove(t)
        order = failed + [c for c in order if c not in failed]
    return [name(c) for c in failed]

def isolated_gnd_pads(b, path):
    """Fill, save, run DRC in a fresh process and return the GND pads it reports as unconnected."""
    import re, subprocess
    pcbnew.ZONE_FILLER(b).Fill(b.Zones()); pcbnew.SaveBoard(path, b)
    rpt = path + ".tmp.rpt"
    subprocess.run([sys.executable, "-c", "import pcbnew,sys; b=pcbnew.LoadBoard(sys.argv[1]); "
                    "pcbnew.WriteDRCReport(b, sys.argv[2], pcbnew.EDA_UNITS_MILLIMETRES, True)", path, rpt], check=True, capture_output=True)
    found = set(re.findall(r"PTH pad (\S+) \[GND\] of (\S+)", open(rpt).read().split("unconnected pads")[1]))
    os.remove(rpt)
    return [(ref, num) for num, ref in found]

def main_island(b, r, code):
    """Grid cells inside the largest filled piece of the GND pour, per layer."""
    mask = np.zeros((2, r.ny, r.nx), dtype=bool)
    for z in b.Zones():
        if z.GetNetCode() != code or z.GetIsRuleArea(): continue
        for li, layer in ((0, F_CU), (1, B_CU)):
            if not z.IsOnLayer(layer): continue
            polys = z.GetFilledPolysList(layer)
            areas = [abs(polys.Outline(i).Area()) for i in range(polys.OutlineCount())]
            if not areas: continue
            k = int(np.argmax(areas)); one = pcbnew.SHAPE_POLY_SET(); one.AddOutline(polys.Outline(k))
            for h in range(polys.HoleCount(k)): one.AddHole(polys.Hole(k, h))
            for iy in range(1, r.ny - 1, 2):
                for ix in range(1, r.nx - 1, 2):
                    if one.Contains(P(ix * r.g, iy * r.g)): mask[li, iy - 1:iy + 2, ix - 1:ix + 2] = True
    return mask

def join_gnd_pads(b, keep, pads):
    """Route each isolated GND pad to the main piece of the GND pour with a short track."""
    r = GridRouter(b, OX, OY, W, H, clearance=CLR, track_w=0.5, keepouts=keep, bcu_cost=1.5)
    r.octilinear = True
    code = b.FindNet("GND").GetNetCode(); n = 0
    dst = main_island(b, r, code)
    for ref, num in pads:
        p = [q for q in b.FindFootprintByReference(ref).Pads() if q.GetNumber() == num][0]
        bb = p.GetBoundingBox(); src = np.zeros_like(dst)
        x0, y0 = pcbnew.ToMM(bb.GetLeft()) - OX, pcbnew.ToMM(bb.GetTop()) - OY
        x1, y1 = pcbnew.ToMM(bb.GetRight()) - OX, pcbnew.ToMM(bb.GetBottom()) - OY
        src[:, max(r._iy(y0), 0):r._iy(y1) + 1, max(r._ix(x0), 0):r._ix(x1) + 1] = True
        path = r.astar(code, src, dst & ~src) if dst.any() else None
        if path is None: print("  GND pad still isolated:", ref, num); continue
        runs, vias = r.simplify(code, path); r.commit(code, runs, vias); n += 1
    return n

def chamfer_corners(b, keep, max_c=1.25):
    """Cut 90-degree (and sharper) corners between two straight tracks of one net on one layer at 45 degrees."""
    r = GridRouter(b, OX, OY, W, H, clearance=CLR, track_w=0.35, keepouts=())
    g = r.g; n_cut = 0
    pads_vias = []
    for fp in b.GetFootprints(): pads_vias += list(fp.Pads())
    pads_vias += [t for t in b.GetTracks() if t.GetClass() == "PCB_VIA"]
    for _ in range(3):
        ends = {}
        for t in b.GetTracks():
            if t.GetClass() != "PCB_TRACK": continue
            for which, p in (("s", t.GetStart()), ("e", t.GetEnd())):
                ends.setdefault((t.GetLayer(), t.GetNetCode(), p.x, p.y), []).append((t, which))
        changed = False
        for (layer, net, x, y), lst in ends.items():
            if len(lst) != 2: continue
            (t1, w1), (t2, w2) = lst
            Pc = pcbnew.VECTOR2I(x, y)
            if any(o.GetNetCode() == net and o.IsOnLayer(layer) and o.HitTest(Pc, 0) for o in pads_vias): continue
            o1 = t1.GetEnd() if w1 == "s" else t1.GetStart(); o2 = t2.GetEnd() if w2 == "s" else t2.GetStart()
            a = (o1.x - x, o1.y - y); c_ = (o2.x - x, o2.y - y)
            la, lc = math.hypot(*a), math.hypot(*c_)
            if la < 1 or lc < 1: continue
            cos = (a[0] * c_[0] + a[1] * c_[1]) / (la * lc)
            if cos < 0.1: continue                                   # 135 or 180 degrees: already fine
            width = min(t1.GetWidth(), t2.GetWidth())
            li = 0 if layer == F_CU else 1
            for cmm in (max_c, 1.0, 0.75, 0.5, 0.25):
                c = mm(cmm)
                if c > 0.5 * min(la, lc): continue
                A = (x + a[0] / la * c, y + a[1] / la * c); C = (x + c_[0] / lc * c, y + c_[1] / lc * c)
                # the cut must clear other copper: test points along it on the router's strict grid
                ok = True
                L = math.hypot(C[0] - A[0], C[1] - A[1]); k = max(int(pcbnew.ToMM(L) / 0.1), 1)
                for i in range(k + 1):
                    px = pcbnew.ToMM(A[0] + (C[0] - A[0]) * i / k) - OX; py = pcbnew.ToMM(A[1] + (C[1] - A[1]) * i / k) - OY
                    iy, ix = r._iy(py), r._ix(px)
                    v = r.occ_s[li, iy, ix]
                    if v not in (0, net): ok = False; break
                    hw = pcbnew.ToMM(width) / 2 - 0.15                  # wider tracks: check the edges too
                    if hw > 0:
                        for dx, dy in ((hw, 0), (-hw, 0), (0, hw), (0, -hw)):
                            v = r.occ_s[li, r._iy(py + dy), r._ix(px + dx)]
                            if v not in (0, net): ok = False; break
                    if not ok: break
                if not ok: continue
                Av = pcbnew.VECTOR2I(int(A[0]), int(A[1])); Cv = pcbnew.VECTOR2I(int(C[0]), int(C[1]))
                if w1 == "s": t1.SetStart(Av)
                else: t1.SetEnd(Av)
                if w2 == "s": t2.SetStart(Cv)
                else: t2.SetEnd(Cv)
                nt = pcbnew.PCB_TRACK(b); nt.SetStart(Av); nt.SetEnd(Cv); nt.SetWidth(width); nt.SetLayer(layer)
                nt.SetNet(t1.GetNet()); b.Add(nt); r._add_track(nt)
                n_cut += 1; changed = True; break
        if not changed: break
    return n_cut

def corners_left(b):
    """Count remaining 90-degree (or sharper) track corners."""
    ends = {}
    for t in b.GetTracks():
        if t.GetClass() != "PCB_TRACK": continue
        for which, p in (("s", t.GetStart()), ("e", t.GetEnd())):
            ends.setdefault((t.GetLayer(), t.GetNetCode(), p.x, p.y), []).append((t, which))
    n = 0
    for (layer, net, x, y), lst in ends.items():
        if len(lst) != 2: continue
        (t1, w1), (t2, w2) = lst
        o1 = t1.GetEnd() if w1 == "s" else t1.GetStart(); o2 = t2.GetEnd() if w2 == "s" else t2.GetStart()
        a = (o1.x - x, o1.y - y); c_ = (o2.x - x, o2.y - y); la, lc = math.hypot(*a), math.hypot(*c_)
        if la and lc and (a[0] * c_[0] + a[1] * c_[1]) / (la * lc) >= 0.1: n += 1
    return n

def logo(b, layer, x, y, width):
    im = Image.open(os.path.join(HERE, "duburi_logo.png")).convert("RGB")
    ppm = 25; w = int(round(width * ppm)); h = int(round(w * im.height / im.width))
    im = im.resize((w, h), Image.LANCZOS); px = im.load(); s = 1.0 / ppm
    ink = [[(px[i, j][2] - px[i, j][0]) > 60 for i in range(w)] for j in range(h)]
    rects, open_runs = [], {}
    for j in range(h + 1):
        runs = set()
        if j < h:
            i = 0
            while i < w:
                if ink[j][i]:
                    i0 = i
                    while i < w and ink[j][i]: i += 1
                    runs.add((i0, i))
                else: i += 1
        for rr in list(open_runs):
            if rr not in runs: rects.append((rr[0], open_runs.pop(rr), rr[1], j))
        for rr in runs: open_runs.setdefault(rr, j)
    ps = pcbnew.SHAPE_POLY_SET()
    for x0, y0, x1, y1 in rects:
        ps.NewOutline()
        for qx, qy in ((x + x0 * s, y + y0 * s), (x + x1 * s, y + y0 * s), (x + x1 * s, y + y1 * s), (x + x0 * s, y + y1 * s)):
            ps.Append(mm(OX + qx), mm(OY + qy))
    ps.Simplify(pcbnew.SHAPE_POLY_SET.PM_FAST); ps.Fracture(pcbnew.SHAPE_POLY_SET.PM_FAST)
    for i in range(ps.OutlineCount()):
        one = pcbnew.SHAPE_POLY_SET(); one.AddOutline(ps.Outline(i))
        sh = pcbnew.PCB_SHAPE(b); sh.SetShape(pcbnew.SHAPE_T_POLY); sh.SetLayer(layer)
        sh.SetPolyShape(one); sh.SetFilled(True); sh.SetWidth(0); b.Add(sh)
    return h * s

def main():
    path = os.path.join(HERE, "ks_tht.kicad_pcb")
    b = pcbnew.LoadBoard(path)
    pad_xy, route, zone, keepout, mask_open = helpers(b)
    # 1. hand routes on B.Cu
    for i in range(1, NFET + 1):
        route(f"G{i}", 0.6, (f"Q{i}", "1"), (f"RG{i}", "1"), layer=B_CU)
        route(f"G{i}", 0.5, (f"RG{i}", "1"), (f"RS{i}", "1"), layer=B_CU)
    bus = [(f"RG{i}", "2") for i in range(1, NFET + 1)] + [("TP1", "1")]
    route("FG", 0.6, *bus, layer=B_CU)
    tp = pad_xy("TP1", "1")
    route("FG", 0.6, tp, (tp[0], 32.0), layer=B_CU)            # gate bus leaves the power section at its right end
    vk = pad_xy("RK1", "2")
    route("VIN_K", 0.6, vk, (vk[0], 15.24), (vk[0] - 1.27, 16.51), (vk[0] - 1.27, 31.0), layer=F_CU)   # on F.Cu: the
    # B.Cu GND plane under the power section stays whole for the return current between the XT60s
    # the 22 Ohm pre-charge resistors end left of VIN_K: join them to VOUT at RK2 underneath
    route("VOUT", 0.9, ("R4", "2"), ("R3", "2"), ("RK2", "1"), layer=B_CU)
    BODIES[:] = bodies(b)
    # 2. router: wide, medium, then signal nets; F.Cu stays out of the power pours
    keep = [(x0, y0, x1, y1, 0) for (x0, y0, x1, y1) in ((0.0, 0.0, 110.0, 13.97), (0.0, 13.97, 15.0, 16.5), (23.0, 13.97, 118.0, 30.0))]
    keep.append((24.0, 0.0, W, 31.5, 1))        # B.Cu under the power section carries the GND current between the XT60s
    code = lambda n: b.FindNet(n).GetNetCode()
    skip = {"VIN", "VOUT", "GND", ""}
    all_nets = {p.GetNetCode() for fp in b.GetFootprints() for p in fp.Pads() if p.GetNetname() not in skip}
    left = []
    left += route_nets(b, {code(n) for n in WIDE}, 0.9, keep, "wide")
    left += route_nets(b, {code(n) for n in MID}, 0.6, keep, "medium")
    left += route_nets(b, all_nets - {code(n) for n in list(WIDE) + list(MID)}, 0.35, keep, "signal")
    if left: print("ROUTING INCOMPLETE:", left)
    trim = trim_dangling(b); print("  dangling segments removed:", trim)
    # 3. 45-degree corners
    print("  corners cut:", chamfer_corners(b, keep), " 90-degree corners left:", corners_left(b))
    # 4. pours
    zone("VIN", F_CU, VIN_POLY, prio=3, thermal=False, name="VIN_top")
    zone("VOUT", F_CU, VOUT_POLY, prio=2, thermal=False, name="VOUT_top")
    whole = [(0.0, 0.0), (W, 0.0), (W, H), (0.0, H)]
    zone("GND", F_CU, whole, prio=1, name="GND_top")
    zone("GND", B_CU, whole, prio=1, name="GND_bot")
    for ref in ("J1", "J2", "D1", "D2"):
        for p in b.FindFootprintByReference(ref).Pads():
            if p.GetNetname() == "GND": p.SetZoneConnection(pcbnew.ZONE_CONNECTION_FULL)
    for _ in range(3):                                         # GND pads the pours cannot reach get a track
        iso = isolated_gnd_pads(b, path)
        if not iso: break
        print("  isolated GND pads:", iso, "joined:", join_gnd_pads(b, keep, iso))
    # bare copper strips along the three current paths: solder a 12 AWG bare copper wire (or thick solder) on them
    for layer, (x0, y0, x1, y1) in WIRE_STRIPS: mask_open(layer, x0, y0, x1, y1)
    # branding: logo in the free corner of the VIN band, name under it
    hl = logo(b, pcbnew.F_SilkS, 84.0, 1.4, 21.0)
    t = pcbnew.PCB_TEXT(b); t.SetText(NAME); t.SetLayer(pcbnew.F_SilkS); t.SetPosition(P(94.5, 1.4 + hl + 1.3))
    t.SetTextSize(pcbnew.VECTOR2I(mm(1.0), mm(1.0))); t.SetTextThickness(mm(0.16)); b.Add(t)
    pcbnew.ZONE_FILLER(b).Fill(b.Zones())
    pcbnew.SaveBoard(path, b)
    # the XT60 bodies overhang the board edge on purpose: their outline silkscreen is clipped there
    import json
    pro = path.replace(".kicad_pcb", ".kicad_pro")
    d = json.load(open(pro)); d["board"]["design_settings"]["rule_severities"]["silk_edge_clearance"] = "ignore"
    d["board"]["design_settings"]["rule_severities"]["lib_footprint_mismatch"] = "ignore"   # extra 3D model paths
    d["board"]["design_settings"]["rule_severities"]["silk_over_copper"] = "ignore"         # silk clipped on the bare wire strips
    json.dump(d, open(pro, "w"), indent=2)
    import fix_3d_models; fix_3d_models.fix(path)           # 3D models for KiCad 7, 8 and 9
    drc(path)

def drc(path):
    """DRC in a fresh process, so the project settings written above are the ones used."""
    import subprocess
    rpt = os.path.join(HERE, "drc_tht.rpt")
    subprocess.run([sys.executable, "-c", "import pcbnew,sys; b=pcbnew.LoadBoard(sys.argv[1]); "
                    "pcbnew.WriteDRCReport(b, sys.argv[2], pcbnew.EDA_UNITS_MILLIMETRES, True)", path, rpt],
                   check=True, capture_output=True)
    print([l for l in open(rpt).read().splitlines() if l.startswith("** Found")])

if __name__ == "__main__":
    main()
