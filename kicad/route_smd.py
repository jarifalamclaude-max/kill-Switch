"""Route the small SMD kill switch (ks_smd.kicad_pcb); run after build_smd.py with KiCad 7's python.

1. Hand-routed: each MOSFET gate leaves its lead through a via, runs on B.Cu at 45 degrees under the VOUT band
   and comes back up beside its 10 Ohm / 1 MOhm pair; the pair is joined on top.
2. Every top-side SMD ground pad gets its own via to the B.Cu ground pour.
3. Grid router for the rest (0/45/90-degree segments, then every 90-degree corner cut at 45 degrees): 0.8 mm for
   the pre-charge path and VIN_K, 0.4-0.6 mm for supplies and the gate bus, 0.25 mm for signals. Nothing is
   routed through the VIN / VOUT copper or under the XT90s, so the 100 A copper and the ground link stay whole.
4. Pours: VIN and VOUT on both layers (solid to the pads), GND on both layers everywhere else; bare strips for
   8 AWG wire; BRACU Duburi logo and the designer's name; zone fill; 3D models bundled; DRC report.
"""
import os, sys, math, json, re, subprocess
import numpy as np
import pcbnew
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from gridroute import GridRouter
from route_ks import helpers, trim_dangling, OX, OY, P, mm
from build_smd import W, H, NFET, GATE_X, RG_X, FET_YC, HOLES

B_CU, F_CU = pcbnew.B_Cu, pcbnew.F_Cu
NAME = "Md. Jarif Alam 13"
CLR = 0.25
BCU_COST, VIA_COST, SOFT = 1.4, 10.0, (3.0, 1.0)
WIDE = {"PCD": 0.8, "PCF": 0.8, "VIN_K": 0.8}
MID = {"SRC": 0.6, "VR1": 0.6, "VR2": 0.6, "V12F": 0.5, "FG": 0.5, "DRV": 0.4, "V5": 0.4}
YB = FET_YC + 2.6                                  # VIN / VOUT boundary between the drain tabs and the source leads
VIA1_Y = FET_YC + 7.75                             # gate via under each gate lead
VIA2_Y = VIA1_Y + 7.5                              # back up to F.Cu beside the resistor pair (45-degree run)
VIN_TOP = [(17.0, 0.0), (74.0, 0.0), (74.0, 6.9), (79.6, 6.9), (79.6, 10.0), (74.0, 10.0), (74.0, YB), (28.4, YB), (28.4, 11.4), (17.0, 11.4)]
VOUT_TOP = [(28.4, YB), (74.0, YB), (74.0, 15.5), (78.0, 15.5), (78.0, 20.9), (74.0, 20.9), (74.0, 25.5), (35.5, 25.5),
            (35.5, 44.0), (17.0, 44.0), (17.0, 33.0), (28.4, 33.0)]
VIN_BOT = [(17.0, 0.0), (74.0, 0.0), (74.0, YB), (28.4, YB), (28.4, 10.6), (12.0, 10.6), (12.0, 3.5), (17.0, 3.5)]
VOUT_BOT = [(28.4, YB), (74.0, YB), (74.0, 25.5), (35.5, 25.5), (35.5, 44.0), (17.0, 44.0), (17.0, 40.5), (12.0, 40.5),
            (12.0, 33.0), (28.4, 33.0)]
# bare copper (no solder mask) for 8 AWG wire: VIN above the MOSFETs, VOUT below them and down to the OUT
# connector (top), the ground link between the two XT90 minus pins (bottom)
WIRE_STRIPS = [(pcbnew.F_Mask, (28.6, 0.5, 73.6, 4.1)), (pcbnew.F_Mask, (29.0, 19.8, 73.6, 24.6)),
               (pcbnew.F_Mask, (29.0, 19.8, 33.0, 41.5)), (pcbnew.B_Mask, (21.2, 16.4, 27.1, 27.45))]
KEEP = [(x0, y0, x1, y1, 0) for (x0, y0, x1, y1) in ((17.0, 0.0, 74.0, YB), (74.0, 6.9, 79.6, 10.0), (28.4, YB, 74.0, 25.5),
                                                      (74.0, 15.5, 78.0, 20.9), (28.4, 25.5, 35.5, 44.0), (17.0, 33.0, 28.4, 44.0))]
KEEP += [(x0, y0, x1, y1, 1) for (x0, y0, x1, y1) in ((17.0, 0.0, 74.0, YB), (12.0, 3.5, 17.0, 10.6), (28.4, YB, 74.0, 25.5),
                                                      (28.4, 25.5, 35.5, 44.0), (12.0, 33.0, 28.4, 44.0))]
KEEP += [(0.0, 0.0, 28.4, 44.2)]                    # under the XT90s: ground copper only, both layers
LOGO = (45.6, 67.9, 12.6)                          # x, y, width of the BRACU Duburi logo (bottom strip, right of the LEDs)

BODIES = []
def bodies(b):
    """Courtyard boxes of the small parts: tracks stay out of them unless there is no other way."""
    out = []
    for fp in b.GetFootprints():
        ref = fp.GetReference()
        if ref.startswith(("H", "TP", "J1", "J2")) or ref in ("Q1", "Q2", "Q3", "Q4") or fp.GetLayer() == B_CU: continue
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
    order = sorted([c for c in pads if len(pads[c]) > 1], key=hpwl)
    failed = []
    for attempt in range(tries):
        r = GridRouter(b, OX, OY, W, H, clearance=CLR, track_w=width, keepouts=keep, bcu_cost=BCU_COST, via_cost=VIA_COST)
        r.octilinear = True
        for (x0, y0, x1, y1) in BODIES: r.soft_box(x0, y0, x1, y1, 0, SOFT[0]); r.soft_box(x0, y0, x1, y1, 1, SOFT[1])
        failed = [c for c in order if not r.route_net(c)[0]]
        print(f"  {label} attempt {attempt}: failed {[name(c) for c in failed]}", flush=True)
        if not failed: return []
        mine = set(order)
        for t in list(b.GetTracks()):
            if not t.IsLocked() and t.GetNetCode() in mine: b.Remove(t)
        order = failed + [c for c in order if c not in failed]
    return [name(c) for c in failed]

def gnd_vias(b, keep):
    """Every top-side SMD ground pad gets its own via to the B.Cu ground pour: the nearest spot (up to 3 mm away)
    where the via and its short track clear every other net and no other via is within 1 mm; else a small via in
    the outer end of the pad."""
    r = GridRouter(b, OX, OY, W, H, clearance=0.25, track_w=0.3, via_d=0.8, keepouts=list(keep))
    gnd = b.FindNet("GND"); code = gnd.GetNetCode(); n = 0; missing = []
    vias = [(pcbnew.ToMM(v.GetPosition().x) - OX, pcbnew.ToMM(v.GetPosition().y) - OY) for v in b.GetTracks() if v.GetClass() == "PCB_VIA"]
    def line_ok(x0, y0, x1, y1):
        L = math.hypot(x1 - x0, y1 - y0); k = max(int(L / 0.1), 1)
        for i in range(k + 1):
            x, y = x0 + (x1 - x0) * i / k, y0 + (y1 - y0) * i / k
            if r.occ_s[0, r._iy(y), r._ix(x)] not in (0, code): return False
        return True
    for fp in b.GetFootprints():
        if fp.GetLayer() != F_CU: continue
        for p in fp.Pads():
            if p.GetNetCode() != code or p.GetAttribute() != pcbnew.PAD_ATTRIB_SMD: continue
            cx, cy = pcbnew.ToMM(p.GetPosition().x) - OX, pcbnew.ToMM(p.GetPosition().y) - OY
            ext = max(pcbnew.ToMM(p.GetBoundingBox().GetWidth()), pcbnew.ToMM(p.GetBoundingBox().GetHeight())) / 2
            best = None; d = ext + 0.7
            while d <= ext + 4.0 and best is None:
                for ang in range(0, 360, 15):
                    x = round((cx + d * math.cos(math.radians(ang))) / 0.25) * 0.25; y = round((cy + d * math.sin(math.radians(ang))) / 0.25) * 0.25
                    iy, ix = r._iy(y), r._ix(x)
                    if not (0 <= iy < r.ny and 0 <= ix < r.nx): continue
                    if not all(r.occ_v[li, iy, ix] in (0, code) for li in (0, 1)): continue
                    if any(math.hypot(x - vx, y - vy) < 1.05 for vx, vy in vias): continue
                    if not line_ok(cx, cy, x, y): continue
                    best = (x, y); break
                d += 0.25
            if best is None: missing.append(p); continue
            x, y = best
            v = pcbnew.PCB_VIA(b); v.SetPosition(P(x, y)); v.SetWidth(mm(0.8)); v.SetDrill(mm(0.4))
            v.SetLayerPair(F_CU, B_CU); v.SetNet(gnd); b.Add(v); r._add_track(v); vias.append((x, y))
            tr = pcbnew.PCB_TRACK(b); tr.SetStart(p.GetPosition()); tr.SetEnd(P(x, y)); tr.SetWidth(mm(0.3)); tr.SetLayer(F_CU); tr.SetNet(gnd); b.Add(tr); r._add_track(tr)
            n += 1
    def clear(x, y, rad, clr=0.22):
        pos = P(x, y)
        for o in list(b.GetTracks()) + [pd for fp in b.GetFootprints() for pd in fp.Pads()]:
            if o.GetNetCode() == code: continue
            for layer in (F_CU, B_CU):
                if o.IsOnLayer(layer) and o.HitTest(pos, mm(rad + clr)): return False
        return True
    for p in missing:
        fp = p.GetParent()
        cx, cy = pcbnew.ToMM(p.GetPosition().x) - OX, pcbnew.ToMM(p.GetPosition().y) - OY
        fx, fy = pcbnew.ToMM(fp.GetPosition().x) - OX, pcbnew.ToMM(fp.GetPosition().y) - OY
        bw, bh = pcbnew.ToMM(p.GetBoundingBox().GetWidth()), pcbnew.ToMM(p.GetBoundingBox().GetHeight())
        ax, ay = ((bw / 2 - 0.3) * (1 if cx > fx else -1), 0.0) if bw >= bh else (0.0, (bh / 2 - 0.3) * (1 if cy > fy else -1))
        spot = next(((cx + ax * f, cy + ay * f) for f in (1.0, 0.75, 0.5, 0.25, 0.0) if clear(cx + ax * f, cy + ay * f, 0.3)
                     and not any(math.hypot(cx + ax * f - vx, cy + ay * f - vy) < 0.9 for vx, vy in vias)), None)
        if spot is None: print("  ground pad without via (pour only):", fp.GetReference(), p.GetNumber()); continue
        x, y = spot
        v = pcbnew.PCB_VIA(b); v.SetPosition(P(x, y)); v.SetWidth(mm(0.6)); v.SetDrill(mm(0.3))
        v.SetLayerPair(F_CU, B_CU); v.SetNet(gnd); b.Add(v); r._add_track(v); vias.append((x, y)); n += 1
        print("  via in pad:", fp.GetReference(), p.GetNumber())
    return n

def unconnected_gnd_pads(b, path):
    """Fill, save, run DRC in a fresh process and return the GND pads it reports as unconnected."""
    pcbnew.ZONE_FILLER(b).Fill(b.Zones()); pcbnew.SaveBoard(path, b)
    rpt = path + ".tmp.rpt"
    subprocess.run([sys.executable, "-c", "import pcbnew,sys; b=pcbnew.LoadBoard(sys.argv[1]); "
                    "pcbnew.WriteDRCReport(b, sys.argv[2], pcbnew.EDA_UNITS_MILLIMETRES, True)", path, rpt], check=True, capture_output=True)
    txt = open(rpt).read(); os.remove(rpt)
    found = set(re.findall(r"(?:PTH|SMD) pad (\S+) \[GND\] of (\S+)", txt.split("unconnected pads")[1]))
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
    """Route each unconnected GND pad to the main piece of the GND pour with a short track (SMD pads start on F.Cu)."""
    r = GridRouter(b, OX, OY, W, H, clearance=CLR, track_w=0.4, keepouts=keep, bcu_cost=1.5)
    r.octilinear = True
    code = b.FindNet("GND").GetNetCode(); n = 0
    dst = main_island(b, r, code)
    for ref, num in pads:
        p = [q for q in b.FindFootprintByReference(ref).Pads() if q.GetNumber() == num][0]
        bb = p.GetBoundingBox(); src = np.zeros_like(dst)
        x0, y0 = pcbnew.ToMM(bb.GetLeft()) - OX, pcbnew.ToMM(bb.GetTop()) - OY
        x1, y1 = pcbnew.ToMM(bb.GetRight()) - OX, pcbnew.ToMM(bb.GetBottom()) - OY
        layers = [0, 1] if p.GetAttribute() == pcbnew.PAD_ATTRIB_PTH else [0 if p.IsOnLayer(F_CU) else 1]
        for li in layers: src[li, max(r._iy(y0), 0):r._iy(y1) + 1, max(r._ix(x0), 0):r._ix(x1) + 1] = True
        path = r.astar(code, src, dst & ~src) if dst.any() else None
        if path is None: print("  GND pad still isolated:", ref, num); continue
        runs, vias = r.simplify(code, path); r.commit(code, runs, vias); n += 1
    return n

def gnd_pieces(b, code):
    """Filled GND pieces on both layers, grouped into connected sets (vias, through-hole pads, tracks, SMD pads)."""
    pcbnew.ZONE_FILLER(b).Fill(b.Zones())
    polys = []
    for z in b.Zones():
        if z.GetNetCode() != code or z.GetIsRuleArea(): continue
        for li, layer in ((0, F_CU), (1, B_CU)):
            if not z.IsOnLayer(layer): continue
            fl = z.GetFilledPolysList(layer)
            for i in range(fl.OutlineCount()):
                one = pcbnew.SHAPE_POLY_SET(); one.AddOutline(fl.Outline(i))
                for h in range(fl.HoleCount(i)): one.AddHole(fl.Hole(i, h))
                polys.append((li, one, abs(fl.Outline(i).Area()) / 1e12))
    par = list(range(len(polys)))
    def find(a):
        while par[a] != a: par[a] = par[par[a]]; a = par[a]
        return a
    def touching(pos, rad, layers):
        return [k for k, (li, one, _) in enumerate(polys) if li in layers and one.Collide(pos, rad)]
    links = []
    for t in b.GetTracks():
        if t.GetNetCode() != code: continue
        if t.GetClass() == "PCB_VIA": links.append(touching(t.GetPosition(), t.GetWidth() // 2 + mm(0.05), (0, 1)))
        else:
            li = 0 if t.GetLayer() == F_CU else 1
            links.append(touching(t.GetStart(), t.GetWidth() // 2 + mm(0.05), (li,)) + touching(t.GetEnd(), t.GetWidth() // 2 + mm(0.05), (li,)))
    for fp in b.GetFootprints():
        for p in fp.Pads():
            if p.GetNetCode() != code: continue
            rad = max(p.GetBoundingBox().GetWidth(), p.GetBoundingBox().GetHeight()) // 2 + mm(0.05)
            lays = (0, 1) if p.GetAttribute() == pcbnew.PAD_ATTRIB_PTH else ((0,) if p.IsOnLayer(F_CU) else (1,))
            links.append(touching(p.GetPosition(), rad, lays))
    for grp in links:
        for k in grp[1:]: par[find(k)] = find(grp[0])
    comps = {}
    for k in range(len(polys)): comps.setdefault(find(k), []).append(k)
    return polys, list(comps.values())

def join_gnd_islands(b):
    """Every piece of the GND pours must reach the main one: a via where a piece lies over the main ground on the
    other layer, otherwise a short routed track."""
    code = b.FindNet("GND").GetNetCode(); added = 0
    for _ in range(4):
        polys, comps = gnd_pieces(b, code)
        main = max(comps, key=lambda c: sum(polys[k][2] for k in c))
        others = [c for c in comps if c is not main and sum(polys[k][2] for k in c) > 0.05]
        if not others: return added
        progress = False
        for comp in others:
            done = False
            for k in comp:
                li, one, _ = polys[k]
                bb = one.BBox()
                x0, y0, x1, y1 = pcbnew.ToMM(bb.GetLeft()), pcbnew.ToMM(bb.GetTop()), pcbnew.ToMM(bb.GetRight()), pcbnew.ToMM(bb.GetBottom())
                y = y0
                while y <= y1 and not done:
                    x = x0
                    while x <= x1 and not done:
                        pos = pcbnew.VECTOR2I(mm(x), mm(y))
                        disk = pcbnew.SHAPE_POLY_SET(); disk.NewOutline()
                        for a in range(12): disk.Append(mm(x + 0.75 * math.cos(a * math.pi / 6)), mm(y + 0.75 * math.sin(a * math.pi / 6)))
                        if one.Contains(pos) and all(one.Contains(disk.Outline(0).CPoint(i)) for i in range(12)):
                            for m in main:
                                lm, om, _ = polys[m]
                                if lm != li and om.Contains(pos) and all(om.Contains(disk.Outline(0).CPoint(i)) for i in range(12)):
                                    v = pcbnew.PCB_VIA(b); v.SetPosition(pos); v.SetWidth(mm(0.8)); v.SetDrill(mm(0.4))
                                    v.SetLayerPair(F_CU, B_CU); v.SetNet(b.FindNet("GND")); b.Add(v); added += 1; done = True; break
                        x += 0.25
                    y += 0.25
                if done: break
            if not done:
                r = GridRouter(b, OX, OY, W, H, clearance=CLR, track_w=0.4, keepouts=KEEP, bcu_cost=1.2)
                r.octilinear = True
                src = np.zeros((2, r.ny, r.nx), dtype=bool); dst = np.zeros_like(src)
                for kk, target in ((comp, src), (main, dst)):
                    for k in kk:
                        li, one, _ = polys[k]; bb = one.BBox()
                        for iy in range(max(r._iy(pcbnew.ToMM(bb.GetTop()) - OY), 0), min(r._iy(pcbnew.ToMM(bb.GetBottom()) - OY) + 1, r.ny)):
                            for ix in range(max(r._ix(pcbnew.ToMM(bb.GetLeft()) - OX), 0), min(r._ix(pcbnew.ToMM(bb.GetRight()) - OX) + 1, r.nx)):
                                if one.Contains(P(ix * r.g, iy * r.g)): target[li, iy, ix] = True
                path = r.astar(code, src, dst & ~src) if dst.any() and src.any() else None
                if path is None: print("  GND piece could not be joined, area", round(sum(polys[k][2] for k in comp), 1)); continue
                runs, vias = r.simplify(code, path); r.commit(code, runs, vias); added += 1; done = True
            progress |= done
        if not progress: break
    return added

def chamfer_corners(b, keep, max_c=1.0):
    """Cut 90-degree (and sharper) corners between two straight tracks of one net on one layer at 45 degrees."""
    r = GridRouter(b, OX, OY, W, H, clearance=CLR, track_w=0.25, keepouts=())
    n_cut = 0
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
            if cos < 0.1: continue
            width = min(t1.GetWidth(), t2.GetWidth())
            li = 0 if layer == F_CU else 1
            for cmm in (max_c, 0.75, 0.5, 0.25):
                c = mm(cmm)
                if c > 0.5 * min(la, lc): continue
                A = (x + a[0] / la * c, y + a[1] / la * c); C = (x + c_[0] / lc * c, y + c_[1] / lc * c)
                ok = True
                L = math.hypot(C[0] - A[0], C[1] - A[1]); k = max(int(pcbnew.ToMM(L) / 0.1), 1)
                for i in range(k + 1):
                    px = pcbnew.ToMM(A[0] + (C[0] - A[0]) * i / k) - OX; py = pcbnew.ToMM(A[1] + (C[1] - A[1]) * i / k) - OY
                    v = r.occ_s[li, r._iy(py), r._ix(px)]
                    if v not in (0, net): ok = False; break
                    hw = pcbnew.ToMM(width) / 2 - 0.12
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

def text(b, s, x, y, size, layer=pcbnew.F_SilkS, bold=False, rot=0):
    t = pcbnew.PCB_TEXT(b); t.SetText(s); t.SetLayer(layer); t.SetPosition(P(x, y)); t.SetTextAngleDegrees(rot)
    t.SetTextSize(pcbnew.VECTOR2I(mm(size), mm(size))); t.SetTextThickness(mm(size * (0.2 if bold else 0.15)))
    if layer == pcbnew.B_SilkS: t.SetMirrored(True)
    b.Add(t)

def main():
    path = os.path.join(HERE, "ks_smd.kicad_pcb")
    b = pcbnew.LoadBoard(path)
    pad_xy, route, zone, keepout, mask_open = helpers(b)
    # 1. gate escapes: lead -> via -> B.Cu at 45 degrees under the VOUT band -> via -> 10 Ohm, 1 MOhm
    for i in range(1, NFET + 1):
        gx, rx = GATE_X[i - 1], RG_X[i - 1]
        g = pad_xy(f"Q{i}", "1")
        route(f"G{i}", 0.5, g, (gx, VIA1_Y), layer=F_CU)
        route(f"G{i}", 0.5, (gx, VIA1_Y), (rx, VIA2_Y), layer=B_CU)
        route(f"G{i}", 0.5, (rx, VIA2_Y), (f"RG{i}", "1"), layer=F_CU)
        route(f"G{i}", 0.4, (f"RG{i}", "1"), (f"RS{i}", "1"), layer=F_CU)
        for (x, y) in ((gx, VIA1_Y), (rx, VIA2_Y)):
            v = pcbnew.PCB_VIA(b); v.SetPosition(P(x, y)); v.SetWidth(mm(0.8)); v.SetDrill(mm(0.4))
            v.SetLayerPair(F_CU, B_CU); v.SetNet(b.FindNet(f"G{i}")); v.SetLocked(True); b.Add(v)
    BODIES[:] = bodies(b)
    # 2. ground vias beside every top-side SMD ground pad (first, so the signals route around them)
    print("  ground vias:", gnd_vias(b, KEEP))
    # 3. router: wide, medium, then signal nets
    code = lambda n: b.FindNet(n).GetNetCode()
    skip = {"VIN", "VOUT", "GND", ""}
    all_nets = {p.GetNetCode() for fp in b.GetFootprints() for p in fp.Pads() if p.GetNetname() not in skip}
    left = []
    left += route_nets(b, {code(n) for n in WIDE}, 0.8, KEEP, "wide")
    for wd in sorted(set(MID.values()), reverse=True):
        left += route_nets(b, {code(n) for n, v in MID.items() if v == wd}, wd, KEEP, f"medium {wd}")
    left += route_nets(b, all_nets - {code(n) for n in list(WIDE) + list(MID)}, 0.25, KEEP, "signal")
    if left: print("ROUTING INCOMPLETE:", left)
    print("  dangling segments removed:", trim_dangling(b))
    print("  corners cut:", chamfer_corners(b, KEEP), " 90-degree corners left:", corners_left(b))
    # 4. pours
    zone("VIN", F_CU, VIN_TOP, prio=3, clearance=0.3, thermal=False, name="VIN_top")
    zone("VOUT", F_CU, VOUT_TOP, prio=2, clearance=0.3, thermal=False, name="VOUT_top")
    zone("VIN", B_CU, VIN_BOT, prio=3, clearance=0.3, thermal=False, name="VIN_bot")
    zone("VOUT", B_CU, VOUT_BOT, prio=2, clearance=0.3, thermal=False, name="VOUT_bot")
    whole = [(0.0, 0.0), (W, 0.0), (W, H), (0.0, H)]
    zone("GND", F_CU, whole, prio=1, clearance=0.3, name="GND_top")
    zone("GND", B_CU, whole, prio=1, clearance=0.3, name="GND_bot")
    hx, hy = HOLES[2]                                          # nylon-screw hole next to the VIN band: keep copper away
    keepout([(hx + 3.2 * math.cos(a * math.pi / 8), hy + 3.2 * math.sin(a * math.pi / 8)) for a in range(16)])
    for ref in ("J1", "J2", "D1", "D2", "U1"):                   # U1: the 7805 tab spreads its heat into the ground copper
        for p in b.FindFootprintByReference(ref).Pads():
            if p.GetNetname() == "GND": p.SetZoneConnection(pcbnew.ZONE_CONNECTION_FULL)
    for _ in range(3):
        iso = unconnected_gnd_pads(b, path)
        if not iso: break
        print("  unconnected GND pads:", iso, "joined:", join_gnd_pads(b, KEEP, iso))
    print("  GND pour pieces joined:", join_gnd_islands(b))
    for layer, (x0, y0, x1, y1) in WIRE_STRIPS: mask_open(layer, x0, y0, x1, y1)
    # silkscreen: LED names, logo + name on top; title and wiring notes underneath
    for ref, lab in (("D7", "HALL"), ("D8", "REED"), ("D9", "LIVE")):
        p = b.FindFootprintByReference(ref).GetPosition()
        text(b, lab, pcbnew.ToMM(p.x) - OX, pcbnew.ToMM(p.y) - OY - 1.75, 0.8)
    lx, ly, lw = LOGO
    hl = logo(b, pcbnew.F_SilkS, lx, ly, lw)
    text(b, NAME, lx + lw + 6.1, ly + hl / 2 + 0.2, 0.8)
    bt = pcbnew.B_SilkS
    text(b, "MAGNETIC KILL SWITCH  100 A  (SMD)", 60.0, 48.5, 1.3, bt, bold=True)
    text(b, "4S-6S LiPo    magnet in = ESCs live", 60.0, 50.8, 0.9, bt)
    text(b, "solder 8 AWG bare copper wire on the bare", 60.0, 53.4, 0.8, bt)
    text(b, "VIN + VOUT strips (top) and GND link (here)", 60.0, 54.8, 0.8, bt)
    text(b, "GND LINK: 8 AWG", 24.2, 21.9, 0.8, bt, rot=90)
    text(b, "BRACU DUBURI", 60.0, 57.4, 0.9, bt, bold=True)
    text(b, "pairs under the MOSFETs: RGn 10 Ohm (left), RSn 1 MOhm (right)", 52.0, 33.6, 0.8, bt)
    pcbnew.ZONE_FILLER(b).Fill(b.Zones())
    pcbnew.SaveBoard(path, b)
    pro = path.replace(".kicad_pcb", ".kicad_pro")
    d = json.load(open(pro)); sev = d["board"]["design_settings"]["rule_severities"]
    sev["silk_edge_clearance"] = "ignore"          # the XT90 bodies stick out past the board edge on purpose
    sev["lib_footprint_mismatch"] = "ignore"       # bundled 3D model paths differ from the library
    sev["lib_footprint_issues"] = "ignore"         # the XT90 footprints come from the project's own ks.pretty
    sev["silk_over_copper"] = "ignore"             # silk clipped on the bare wire strips
    json.dump(d, open(pro, "w"), indent=2)
    ptc_model()
    import bundle_3d; bundle_3d.bundle(path)        # 3D models inside the project: KiCad 7, 8, 9, 10
    drc(path)

def ptc_model():
    """KiCad's 3D library has no model for the 2920 fuse footprint: write a simple one (VRML, 1 unit = 2.54 mm)."""
    out = os.path.join(HERE, "3dmodels", "Fuse_2920_7451Metric.wrl")
    def box(x0, y0, z0, x1, y1, z1, rgb):
        p = [(x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0), (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)]
        P_ = ", ".join(f"{x / 2.54:.4f} {y / 2.54:.4f} {z / 2.54:.4f}" for x, y, z in p)
        F_ = ", ".join(" ".join(map(str, f)) + " -1" for f in ((0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)))
        return (f"Shape {{ appearance Appearance {{ material Material {{ diffuseColor {rgb[0]} {rgb[1]} {rgb[2]} specularColor 0.3 0.3 0.3 }} }} "
                f"geometry IndexedFaceSet {{ solid FALSE coord Coordinate {{ point [ {P_} ] }} coordIndex [ {F_} ] }} }}")
    body = box(-2.6, -2.6, 0.05, 2.6, 2.6, 2.4, (0.55, 0.42, 0.18))                 # PTC body 7.4 x 5.2 mm
    ends = [box(s * 3.7 - (1.2 if s > 0 else 0), -2.65, 0.0, s * 3.7 + (0 if s > 0 else 1.2), 2.65, 2.45, (0.82, 0.82, 0.8)) for s in (-1, 1)]
    open(out, "w").write("#VRML V2.0 utf8\n" + "\n".join([body] + ends) + "\n")

def drc(path):
    """DRC in a fresh process, so the project settings written above are the ones used."""
    rpt = os.path.join(HERE, "drc_smd.rpt")
    subprocess.run([sys.executable, "-c", "import pcbnew,sys; b=pcbnew.LoadBoard(sys.argv[1]); "
                    "pcbnew.WriteDRCReport(b, sys.argv[2], pcbnew.EDA_UNITS_MILLIMETRES, True)", path, rpt],
                   check=True, capture_output=True)
    print([l for l in open(rpt).read().splitlines() if l.startswith("** Found")])

if __name__ == "__main__":
    main()
