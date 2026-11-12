"""Copper for the kill switch boards.

Power board
1. Copper pours carry the 100 A: VIN (top band, both layers), VOUT (band below the MOSFETs, both layers;
   on B.Cu it also reaches across to the pre-charge resistors), GND (left strip + whole logic area).
2. Hand-routed: each MOSFET gate -> its 10 Ohm resistor -> the FG bus; the Kelvin lines VIN_K / VOUT_K and FG
   down the 4 mm signal channel; the pre-charge gate, drain and resistor connections in the right channel.
3. Everything else in the logic area is routed by ../../kicad/gridroute.py, kept out of the power bands.
4. Copper keep-outs around the nylon mounting holes; solder-mask openings on the bottom of both bands so the
   current path can be tinned or have a copper bar soldered on.

Run with KiCad 7's python from this folder:  python3 route_ks.py   (writes drc_power.rpt, drc_sensor.rpt)
"""
import os, sys, math
import numpy as np
import pcbnew

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from gridroute import GridRouter

OX, OY = 100.0, 100.0
mm = pcbnew.FromMM
def P(x, y): return pcbnew.VECTOR2I(mm(OX + x), mm(OY + y))

def helpers(b):
    def pad_xy(ref, num, i=0):
        ps = [p for p in b.FindFootprintByReference(ref).Pads() if p.GetNumber() == num]
        p = ps[i].GetPosition(); return (pcbnew.ToMM(p.x) - OX, pcbnew.ToMM(p.y) - OY)
    def route(net, width, *pts, layer=pcbnew.F_Cu):
        n = b.FindNet(net); assert n is not None, net
        pts = [pad_xy(*p) if isinstance(p[0], str) else p for p in pts]
        for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
            t = pcbnew.PCB_TRACK(b); t.SetStart(P(x0, y0)); t.SetEnd(P(x1, y1))
            t.SetWidth(mm(width)); t.SetLayer(layer); t.SetNet(n); t.SetLocked(True); b.Add(t)
    def zone(net, layer, pts, prio=0, clearance=0.4, thermal=True, name=""):
        z = pcbnew.ZONE(b); z.SetLayer(layer); z.SetNet(b.FindNet(net))
        o = z.Outline(); o.NewOutline()
        for x, y in pts: o.Append(mm(OX + x), mm(OY + y))
        z.SetLocalClearance(mm(clearance)); z.SetMinThickness(mm(0.3))
        z.SetPadConnection(pcbnew.ZONE_CONNECTION_THERMAL if thermal else pcbnew.ZONE_CONNECTION_FULL)
        z.SetThermalReliefGap(mm(0.4)); z.SetThermalReliefSpokeWidth(mm(0.8))
        z.SetIslandRemovalMode(pcbnew.ISLAND_REMOVAL_MODE_ALWAYS); z.SetAssignedPriority(prio); z.SetZoneName(name); b.Add(z)
    def keepout(pts):
        z = pcbnew.ZONE(b); z.SetIsRuleArea(True); z.SetDoNotAllowTracks(True); z.SetDoNotAllowVias(True)
        z.SetDoNotAllowCopperPour(True); z.SetDoNotAllowPads(False); z.SetDoNotAllowFootprints(False)
        ls = pcbnew.LSET(); ls.AddLayer(pcbnew.F_Cu); ls.AddLayer(pcbnew.B_Cu); z.SetLayerSet(ls)
        o = z.Outline(); o.NewOutline()
        for x, y in pts: o.Append(mm(OX + x), mm(OY + y))
        b.Add(z)
    def mask_open(layer, x0, y0, x1, y1):
        s = pcbnew.PCB_SHAPE(b); s.SetShape(pcbnew.SHAPE_T_RECT); s.SetLayer(layer); s.SetFilled(True)
        s.SetStart(P(x0, y0)); s.SetEnd(P(x1, y1)); s.SetWidth(0); b.Add(s)
    return pad_xy, route, zone, keepout, mask_open

def autoroute(b, w, h, skip, keepouts, label):
    nets = {}
    for fp in b.GetFootprints():
        for p in fp.Pads():
            if p.GetNetname() in skip: continue
            nets.setdefault(p.GetNetCode(), []).append(pcbnew.ToMM(p.GetPosition().x) + 1j * pcbnew.ToMM(p.GetPosition().y))
    def hpwl(c):
        xs = [z.real for z in nets[c]]; ys = [z.imag for z in nets[c]]; return (max(xs) - min(xs)) + (max(ys) - min(ys))
    order = sorted([c for c in nets if len(nets[c]) > 1], key=hpwl)
    name = lambda c: b.GetNetInfo().GetNetItem(c).GetNetname()
    for attempt in range(10):
        r = GridRouter(b, OX, OY, w, h, clearance=0.25, track_w=0.3, keepouts=keepouts)
        failed = [c for c in order if not r.route_net(c)[0]]
        print(f"{label} attempt {attempt}: failed {[name(c) for c in failed]}")
        if not failed: return
        for t in list(b.GetTracks()):
            if not t.IsLocked(): b.Remove(t)
        order = failed + [c for c in order if c not in failed]
    print(f"{label}: ROUTING INCOMPLETE for " + ", ".join(name(c) for c in failed))

def stitch(b, net, rects, pitch, size=0.8, drill=0.4, w=None, h=None, keep=(), inside=None):
    """Vias joining the F.Cu and B.Cu pours of one net, on a grid, wherever they clear all pads and tracks."""
    r = GridRouter(b, OX, OY, w, h, clearance=0.3, track_w=0.3, via_d=size, keepouts=list(keep))
    code = b.FindNet(net).GetNetCode(); n = 0
    for (x0, y0, x1, y1) in rects:
        y = y0
        while y <= y1:
            x = x0
            while x <= x1:
                iy, ix = r._iy(y), r._ix(x)
                ok = inside is None or inside(x, y)
                if ok and 0 <= iy < r.ny and 0 <= ix < r.nx and all(r.occ_v[li, iy, ix] == 0 for li in (0, 1)):
                    v = pcbnew.PCB_VIA(b); v.SetPosition(P(x, y)); v.SetWidth(mm(size)); v.SetDrill(mm(drill))
                    v.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu); v.SetNet(b.FindNet(net)); b.Add(v); n += 1
                    r._add_track(v)
                x += pitch
            y += pitch
    return n

def same(o, t):
    """SWIG hands out a new wrapper per call, so compare tracks by geometry instead of identity."""
    return o.GetClass() == t.GetClass() == "PCB_TRACK" and o.GetStart() == t.GetStart() and o.GetEnd() == t.GetEnd() and o.GetLayer() == t.GetLayer()

def trim_dangling(b):
    """Remove dangling escape-stub segments one at a time, keeping a removal only if connectivity is unchanged."""
    removed = 0
    while True:
        b.BuildConnectivity(); base = b.GetConnectivity().GetUnconnectedCount(False)
        progress = False
        u1 = b.FindFootprintByReference("U1").GetPosition()
        near_u1 = lambda tr: max(abs(tr.GetStart().x - u1.x), abs(tr.GetStart().y - u1.y)) < mm(8)
        for t in dangling_ends(b):
            if not (t.IsLocked() and not near_u1(t)):            # hand-routed copper is never removed, only shortened
                b.Remove(t); b.BuildConnectivity()
                if b.GetConnectivity().GetUnconnectedCount(False) <= base:
                    removed += 1; progress = True; continue
                b.Add(t)
            # keep the segment up to the furthest point where other copper of the net touches it
            s, e = t.GetStart(), t.GetEnd()
            free_end = None
            for end in (s, e):
                if not any(not same(o, t) and o.GetNetCode() == t.GetNetCode() and o.IsOnLayer(t.GetLayer()) and o.HitTest(end, mm(0.01))
                           for o in list(b.GetTracks()) + [pd for fp in b.GetFootprints() for pd in fp.Pads()]):
                    free_end = end
            if free_end is None: continue
            fixed = e if free_end == s else s
            touches = []
            for o in b.GetTracks():
                if same(o, t) or o.GetNetCode() != t.GetNetCode() or not o.IsOnLayer(t.GetLayer()): continue
                pts = [o.GetPosition()] if o.GetClass() == "PCB_VIA" else [o.GetStart(), o.GetEnd()]
                for q in pts:
                    if t.HitTest(q, mm(0.01)) and q != free_end: touches.append(q)
            if not touches: continue
            far = max(touches, key=lambda q: math.hypot(q.x - fixed.x, q.y - fixed.y))
            # keep the segment on its own line: project the touch point onto it
            dx, dy = free_end.x - fixed.x, free_end.y - fixed.y; L2 = float(dx * dx + dy * dy)
            u = max(0.0, min(1.0, ((far.x - fixed.x) * dx + (far.y - fixed.y) * dy) / L2)) if L2 else 0.0
            far = pcbnew.VECTOR2I(int(round(fixed.x + u * dx)), int(round(fixed.y + u * dy)))
            if math.hypot(far.x - fixed.x, far.y - fixed.y) < mm(0.05): continue
            if free_end == s: t.SetStart(far)
            else: t.SetEnd(far)
            b.BuildConnectivity()
            if b.GetConnectivity().GetUnconnectedCount(False) > base:
                if free_end == s: t.SetStart(s)
                else: t.SetEnd(e)
            else: removed += 1; progress = True
        if not progress: return removed

def gnd_pad_vias(b, w, h, keep=(), inside=None):
    """Every SMD ground pad gets its own via to the B.Cu ground pour: the nearest spot (up to 3 mm away) where
    the via and the short track to it clear every other net, and no other via is within 1 mm."""
    import math
    r = GridRouter(b, OX, OY, w, h, clearance=0.25, track_w=0.3, via_d=0.8, keepouts=list(keep))
    gnd = b.FindNet("GND"); code = gnd.GetNetCode(); n = 0; missing = []
    vias = [(pcbnew.ToMM(v.GetPosition().x) - OX, pcbnew.ToMM(v.GetPosition().y) - OY) for v in b.GetTracks() if v.GetClass() == "PCB_VIA"]
    def line_ok(x0, y0, x1, y1):
        L = math.hypot(x1 - x0, y1 - y0); k = max(int(L / 0.1), 1)
        for i in range(k + 1):
            x, y = x0 + (x1 - x0) * i / k, y0 + (y1 - y0) * i / k
            if r.occ_s[0, r._iy(y), r._ix(x)] not in (0, code): return False
        return True
    for fp in b.GetFootprints():
        for p in fp.Pads():
            if p.GetNetCode() != code or p.GetAttribute() != pcbnew.PAD_ATTRIB_SMD: continue
            cx, cy = pcbnew.ToMM(p.GetPosition().x) - OX, pcbnew.ToMM(p.GetPosition().y) - OY
            ext = max(pcbnew.ToMM(p.GetBoundingBox().GetWidth()), pcbnew.ToMM(p.GetBoundingBox().GetHeight())) / 2
            best = None
            d = ext + 0.7
            while d <= ext + 3.0 and best is None:
                for ang in range(0, 360, 15):
                    x, y = round((cx + d * math.cos(math.radians(ang))) / 0.25) * 0.25, round((cy + d * math.sin(math.radians(ang))) / 0.25) * 0.25
                    if inside is not None and not inside(x, y): continue
                    iy, ix = r._iy(y), r._ix(x)
                    if not (0 <= iy < r.ny and 0 <= ix < r.nx): continue
                    if not all(r.occ_v[li, iy, ix] in (0, code) for li in (0, 1)): continue
                    if any(math.hypot(x - vx, y - vy) < 1.05 for vx, vy in vias): continue
                    if not line_ok(cx, cy, x, y): continue
                    best = (x, y); break
                d += 0.25
            if best is None:
                missing.append(p); continue
            x, y = best
            v = pcbnew.PCB_VIA(b); v.SetPosition(P(x, y)); v.SetWidth(mm(0.8)); v.SetDrill(mm(0.4))
            v.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu); v.SetNet(gnd); b.Add(v); r._add_track(v); vias.append((x, y))
            tr = pcbnew.PCB_TRACK(b); tr.SetStart(p.GetPosition()); tr.SetEnd(P(x, y)); tr.SetWidth(mm(0.3)); tr.SetLayer(pcbnew.F_Cu); tr.SetNet(gnd); b.Add(tr); r._add_track(tr)
            n += 1
    # pads with no room beside them: a small via (0.6/0.3 mm) in the outer end of the pad itself, checked against
    # every other-net copper on both layers, then a B.Cu track from it to the nearest ground via
    def clear(x, y, rad, clr=0.22):
        pos = P(x, y)
        for o in list(b.GetTracks()) + [pd for fp in b.GetFootprints() for pd in fp.Pads()]:
            if o.GetNetCode() == code: continue
            for layer in (pcbnew.F_Cu, pcbnew.B_Cu):
                if o.IsOnLayer(layer) and o.HitTest(pos, mm(rad + clr)): return False
        return True
    still = []
    for p in missing:
        fp = p.GetParent()
        cx, cy = pcbnew.ToMM(p.GetPosition().x) - OX, pcbnew.ToMM(p.GetPosition().y) - OY
        fx, fy = pcbnew.ToMM(fp.GetPosition().x) - OX, pcbnew.ToMM(fp.GetPosition().y) - OY
        bw, bh = pcbnew.ToMM(p.GetBoundingBox().GetWidth()), pcbnew.ToMM(p.GetBoundingBox().GetHeight())
        ax, ay = ((bw / 2 - 0.3) * (1 if cx > fx else -1), 0.0) if bw >= bh else (0.0, (bh / 2 - 0.3) * (1 if cy > fy else -1))
        spot = next(((cx + ax * f, cy + ay * f) for f in (1.0, 0.75, 0.5, 0.25, 0.0) if clear(cx + ax * f, cy + ay * f, 0.3)
                     and not any(math.hypot(cx + ax * f - vx, cy + ay * f - vy) < 0.9 for vx, vy in vias)), None)
        if spot is None: still.append(p); continue
        x, y = spot
        v = pcbnew.PCB_VIA(b); v.SetPosition(P(x, y)); v.SetWidth(mm(0.6)); v.SetDrill(mm(0.3))
        v.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu); v.SetNet(gnd); b.Add(v); r._add_track(v)
        src = np.zeros((2, r.ny, r.nx), dtype=bool); src[1, r._iy(y), r._ix(x)] = True
        dst = np.zeros_like(src)
        for (vx, vy) in vias:
            if math.hypot(vx - x, vy - y) < 12: dst[1, r._iy(vy) - 1:r._iy(vy) + 2, r._ix(vx) - 1:r._ix(vx) + 2] = True
        vias.append((x, y)); n += 1
        path = r.astar(code, src, dst) if dst.any() else None
        if path is not None:
            runs, vv = r.simplify(code, path); r.commit(code, runs, vv)
        print("  via in pad:", fp.GetReference(), p.GetNumber(), (round(x, 2), round(y, 2)), "B.Cu link" if path else "pour only")
    # still nothing: route a short track to the nearest ground via
    for p in still:
        cx, cy = pcbnew.ToMM(p.GetPosition().x) - OX, pcbnew.ToMM(p.GetPosition().y) - OY
        src = np.zeros((2, r.ny, r.nx), dtype=bool)
        iy, ix = r._iy(cy), r._ix(cx); src[0, iy - 1:iy + 2, ix - 1:ix + 2] = True
        dst = np.zeros_like(src)
        for (vx, vy) in vias:
            if math.hypot(vx - cx, vy - cy) > 12: continue
            jy, jx = r._iy(vy), r._ix(vx); dst[:, jy - 1:jy + 2, jx - 1:jx + 2] = True
        path = r.astar(code, src, dst) if dst.any() else None
        if path is None:
            print("  ground pad left to the pour:", p.GetParent().GetReference(), p.GetNumber()); continue
        runs, vv = r.simplify(code, path); r.commit(code, runs, vv); n += 1
    return n

def dangling_ends(b):
    """Track segments with an end that touches no other copper of their net (pads, tracks, vias, filled zones)."""
    items = []
    for fp in b.GetFootprints(): items += list(fp.Pads())
    tracks = list(b.GetTracks())
    zones = [b.GetArea(i) for i in range(b.GetAreaCount()) if not b.GetArea(i).GetIsRuleArea()]
    out = []
    for t in tracks:
        if t.GetClass() != "PCB_TRACK": continue
        for end in (t.GetStart(), t.GetEnd()):
            ok = False
            for o in items + tracks:
                if o is t or o.GetNetCode() != t.GetNetCode(): continue
                if o.GetClass() == "PCB_TRACK" and o.GetStart() == t.GetStart() and o.GetEnd() == t.GetEnd(): continue
                if o.IsOnLayer(t.GetLayer()) and o.HitTest(end, mm(0.01)): ok = True; break
            if not ok:
                for z in zones:
                    if z.GetNetCode() == t.GetNetCode() and z.IsOnLayer(t.GetLayer()) and z.HitTestFilledArea(t.GetLayer(), end): ok = True; break
            if not ok: out.append(t); break
    return out

def finish(b, path, rpt):
    pcbnew.ZONE_FILLER(b).Fill(b.Zones())
    print("dangling segments removed:", trim_dangling(b))
    pcbnew.ZONE_FILLER(b).Fill(b.Zones())
    pcbnew.SaveBoard(path, b)
    b2 = pcbnew.LoadBoard(path)
    pcbnew.WriteDRCReport(b2, rpt, pcbnew.EDA_UNITS_MILLIMETRES, True)
    print(open(rpt).read().split("** Found")[1:4])

def power():
    path = os.path.join(HERE, "ks_power.kicad_pcb")
    b = pcbnew.LoadBoard(path)
    for z in [b.GetArea(i) for i in range(b.GetAreaCount())]: b.Remove(z)
    for t in list(b.GetTracks()): b.Remove(t)
    for d in list(b.GetDrawings()):
        if d.GetLayer() in (pcbnew.F_Mask, pcbnew.B_Mask): b.Remove(d)
    pad_xy, route, zone, keepout, mask_open = helpers(b)
    W, H, LTOP = 118.0, 120.0, 76.5
    # gates: pad -> resistor -> FG bus at y 39.6, then down the signal channel at x 100.3
    FGY = 39.6
    for n in range(1, 9):
        gx, gy = pad_xy(f"Q{n}", "1"); r1 = pad_xy(f"RG{n}", "1"); r2 = pad_xy(f"RG{n}", "2")
        route(f"G{n}", 0.4, (gx, gy), (r1[0], r1[1]))
        route("FG", 0.4, r2, (r2[0], FGY))
    x_first = pad_xy("RG1", "2")[0]
    route("FG", 0.4, (x_first, FGY), (100.3, FGY), (100.3, 79.0))
    route("VOUT_K", 0.3, ("RK2", "2"), (101.3, 79.0))
    route("VIN_K", 0.3, ("RK1", "2"), (102.3, 79.0))
    # pre-charge: gate node, driver line, drain -> PTC -> resistors
    # pre-charge gate node: R8 / D4 / Q9 gate at the top, then down the right edge to R9 in the logic area
    route("PCG", 0.5, ("R8", "2"), (116.0, 23.0))
    route("PCG", 0.5, ("D4", "2"), (pad_xy("D4", "2")[0], 23.0), (117.2, 23.0), (117.2, 93.0), (pad_xy("R9", "1")[0], 93.0), ("R9", "1"))
    route("PCG", 0.5, ("Q9", "1"), (pad_xy("Q9", "1")[0], 23.0))
    route("PCD", 1.5, (111.0, 35.0), ("F1", "1"))
    route("PCF", 1.2, ("F1", "2"), (111.0, 43.0), (pad_xy("R12", "1")[0], 43.0), ("R12", "1"))
    route("PCF", 1.2, (111.0, 43.0), (pad_xy("R13", "1")[0], 43.0), ("R13", "1"))
    # LM5060 (0.5 mm pitch): fan the pins out on grid-aligned, axis-parallel stubs so the 0.25 mm grid router
    # sees each stub as one piece of copper and can reach its end
    ux, uy = pad_xy("U1", "3")                                   # pin 3: middle of the left row
    L = ux - 2.8; Rr = ux + 7.2                                  # stub end columns (x 90.0 and 100.0)
    steps = {"1": [(-0.55, 0), (0, -1.5), None], "2": [(-1.3, 0), (0, -1.0), None], "3": [None],
             "4": [(-1.3, 0), (0, 1.0), None], "5": [(-0.55, 0), (0, 1.5), None]}
    for side, pins, endx in ((-1, ("1", "2", "3", "4", "5"), L), (1, ("10", "9", "8", "7", "6"), Rr)):
        for k, pin in enumerate(pins):
            px, py = pad_xy("U1", pin); netn = b.FindFootprintByReference("U1").FindPadByNumber(pin).GetNetname()
            pts = [(px, py)]; x, y = px, py
            for st in steps[str(k + 1)]:
                if st is None: x = endx
                else: x, y = x + side * -st[0] * -1 if False else x + (st[0] if side < 0 else -st[0]), y + st[1]
                pts.append((x, y))
            route(netn, 0.25, *pts)
    # the three Kelvin/gate lines meet the controller: FG and VOUT_K straight down, VIN_K under them on B.Cu
    def via(net, x, y):
        v = pcbnew.PCB_VIA(b); v.SetPosition(P(x, y)); v.SetWidth(mm(0.8)); v.SetDrill(mm(0.4))
        v.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu); v.SetNet(b.FindNet(net)); v.SetLocked(True); b.Add(v)

    route("TMR", 0.25, (Rr, 89.5), (pad_xy("C5", "1")[0], 89.5), ("C5", "1"))
    c6 = pad_xy("C6", "1"); r1 = pad_xy("R1", "1")
    route("VIN_K", 0.3, (102.3, 79.0), (102.3, 80.2)); via("VIN_K", 102.3, 80.2)
    route("VIN_K", 0.3, (102.3, 80.2), (97.0, 80.2), layer=pcbnew.B_Cu); via("VIN_K", 97.0, 80.2)
    route("VIN_K", 0.3, (97.0, 80.2), (c6[0], 80.2), c6)
    route("VIN_K", 0.3, (c6[0], 80.2), (r1[0], 80.2), r1)
    # router for the logic area only
    autoroute(b, W, H, {"VIN", "VOUT", "GND", ""}, [(0.0, 0.0, W, LTOP + 0.5)], "power")
    # pours
    vin = [(12.0, 0.5), (117.5, 0.5), (117.5, 26.8), (103.8, 26.8), (103.8, 23.2), (99.6, 23.2), (99.6, 31.3), (12.0, 31.3)]
    vout_top = [(12.0, 33.0), (99.6, 33.0), (99.6, 34.0), (101.9, 34.0), (101.9, 35.4), (99.6, 35.4), (99.6, 74.5), (12.0, 74.5)]
    vout_ch = [(103.8, 54.5), (117.5, 54.5), (117.5, 74.5), (103.8, 74.5)]
    vout_bot = [(12.0, 33.0), (99.6, 33.0), (99.6, 54.5), (117.5, 54.5), (117.5, 74.5), (12.0, 74.5)]
    gnd = [(0.5, 0.5), (11.0, 0.5), (11.0, LTOP), (117.5, LTOP), (117.5, 119.5), (0.5, 119.5)]
    for layer, tag in ((pcbnew.F_Cu, "top"), (pcbnew.B_Cu, "bot")):
        zone("VIN", layer, vin, prio=2, thermal=False, name=f"VIN_{tag}")
        zone("VOUT", layer, vout_top if layer == pcbnew.F_Cu else vout_bot, prio=2, thermal=False, name=f"VOUT_{tag}")
        zone("GND", layer, gnd, prio=1, name=f"GND_{tag}")
    zone("VOUT", pcbnew.F_Cu, vout_ch, prio=2, thermal=False, name="VOUT_ch_top")
    for (x, y) in ((4.0, 4.0), (114.0, 4.0), (4.0, 116.0), (114.0, 116.0)):
        keepout([(x - 3.5, y - 3.5), (x + 3.5, y - 3.5), (x + 3.5, y + 3.5), (x - 3.5, y + 3.5)])
    # stitching: VOUT rows just under the MOSFET sources and across the band, GND over the logic area and strip
    holes = [(x - 3.5, y - 3.5, x + 3.5, y + 3.5) for (x, y) in ((4.0, 4.0), (114.0, 4.0), (4.0, 116.0), (114.0, 116.0))]
    nv = stitch(b, "VOUT", [(14.0, 36.6, 98.0, 36.6), (14.0, 42.0, 98.0, 52.0), (14.0, 64.0, 98.0, 73.0), (104.5, 64.0, 116.5, 73.0)], 2.5, 1.0, 0.5, W, H, keep=holes)
    in_gnd = lambda x, y: (1.0 <= x <= 10.3 and 1.0 <= y <= 75.8) or (1.0 <= x <= 117.0 and 77.3 <= y <= 119.0)
    npad = gnd_pad_vias(b, W, H, keep=holes, inside=in_gnd)
    ng = stitch(b, "GND", [(2.0, 2.0, 9.0, 74.0), (2.0, 78.5, 116.0, 118.0)], 3.0, 0.8, 0.4, W, H, keep=holes)
    print("stitching vias: VOUT", nv, "GND", ng, "GND at pads", npad)
    # bottom mask openings along the current path (tin it or solder a 2 x 5 mm copper bar on)
    for (x0, y0, x1, y1) in ((14.0, 2.0, 50.0, 21.0), (66.0, 2.0, 98.0, 21.0), (14.0, 41.0, 98.0, 51.0), (14.0, 65.0, 50.0, 73.0), (66.0, 65.0, 98.0, 73.0)):
        mask_open(pcbnew.B_Mask, x0, y0, x1, y1)
    finish(b, path, os.path.join(HERE, "drc_power.rpt"))

if __name__ == "__main__":
    power()
