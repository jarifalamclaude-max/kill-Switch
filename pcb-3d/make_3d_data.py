"""Make the 3D view's data from the kill switch PCB (../kicad/ks_power.kicad_pcb):

* tex_top.jpg / tex_bot.jpg: the board as a gerber viewer shows it (green mask, lighter green over copper,
  silver pads, bare copper where the mask is open, white silkscreen, black holes). Both are drawn as seen
  from the top, which is what index.html expects.
* PARTS: every footprint with its value, body box (from the F.Fab outline) and pads.
* PATHS: the six current paths, each a list of polylines that follow the real copper. Track legs are found
  by a shortest-path search over the net's tracks, vias and pads, so a path bends exactly where the copper
  does. The 150 A legs run through the VIN / VOUT pours (which have no tracks) and are drawn by hand inside
  the pour outlines; the pour and the off-board cables are marked as such in index.html.

Run with KiCad 7's python (KICAD7_FOOTPRINT_DIR set):  python3 make_3d_data.py
It rewrites both textures and the generated data block in index.html.
"""
import heapq, json, math, os, re, subprocess, tempfile
import numpy as np
from PIL import Image, ImageDraw
import pcbnew

HERE = os.path.dirname(os.path.abspath(__file__))
PCB = os.path.join(HERE, "..", "kicad", "ks_power.kicad_pcb")
HTML = os.path.join(HERE, "index.html")
W, H, PX = 118.0, 120.0, 21.0                  # board size (mm), texture pixels per mm
OX = OY = 100.0
MASK, MASK_CU, SILK, PAD, FR4, HOLE = (29, 91, 50), (40, 112, 62), (236, 238, 238), (214, 216, 218), (196, 170, 110), (13, 13, 13)
mm = pcbnew.ToMM

# ------------------------------------------------------------------ textures (same method as the torpedo board)
def render(layer, tmp):
    svg, png = os.path.join(tmp, layer + ".svg"), os.path.join(tmp, layer + ".png")
    subprocess.run(["kicad-cli", "pcb", "export", "svg", "--layers", layer, "--black-and-white", "--exclude-drawing-sheet",
                    "--page-size-mode", "2", "--drill-shape-opt", "0", "-o", svg, PCB], check=True, capture_output=True)
    head = open(svg).read(1000)
    wmm = float(head.split('width="')[1].split("mm")[0])
    subprocess.run(["rsvg-convert", "-w", str(int(round(wmm * PX))), "-b", "white", svg, "-o", png], check=True)
    return np.asarray(Image.open(png).convert("L")) < 128

def textures():
    with tempfile.TemporaryDirectory() as tmp:
        edge = render("Edge.Cuts", tmp)
        ys, xs = np.nonzero(edge)
        x0, x1, y0, y1 = xs.min(), xs.max(), ys.min(), ys.max()
        lw = max(1, int(round(0.1 * PX)))
        box = (x0 + lw // 2, y0 + lw // 2, x1 - lw // 2, y1 - lw // 2)
        size = (int(round(W * PX)), int(round(H * PX)))
        def crop(a): return np.asarray(Image.fromarray(a.astype(np.uint8) * 255).crop(box).resize(size, Image.NEAREST)) > 127
        b = pcbnew.LoadBoard(PCB)
        holes = []
        for fp in b.GetFootprints():
            for p in fp.Pads():
                d = p.GetDrillSize()
                if d.x > 0: holes.append((mm(p.GetPosition().x) - OX, mm(p.GetPosition().y) - OY, mm(d.x) / 2, mm(d.y) / 2))
        for t in b.GetTracks():
            if t.GetClass() == "PCB_VIA":
                r = mm(t.GetDrillValue()) / 2
                holes.append((mm(t.GetPosition().x) - OX, mm(t.GetPosition().y) - OY, r, r))
        for side, (cu, mk, sk) in (("top", ("F.Cu", "F.Mask", "F.Silkscreen")), ("bot", ("B.Cu", "B.Mask", "B.Silkscreen"))):
            copper, opening, silk = crop(render(cu, tmp)), crop(render(mk, tmp)), crop(render(sk, tmp))
            img = np.zeros(copper.shape + (3,), dtype=np.uint8); img[:] = MASK
            img[copper] = MASK_CU
            img[opening & copper] = PAD; img[opening & ~copper] = FR4
            img[silk & ~opening] = SILK
            im = Image.fromarray(img); dr = ImageDraw.Draw(im)
            for x, y, rx, ry in holes:
                dr.ellipse([(x - rx) * PX, (y - ry) * PX, (x + rx) * PX, (y + ry) * PX], fill=HOLE)
            im.save(os.path.join(HERE, f"tex_{side}.jpg"), quality=82, optimize=True, progressive=True)
            print(f"tex_{side}.jpg", im.size, os.path.getsize(os.path.join(HERE, f"tex_{side}.jpg")) // 1024, "kB")

# ------------------------------------------------------------------ parts
def parts(b):
    """ref, value, footprint, position, rotation, body box [cx, cy, w, h] in the footprint's own frame
    (from the F.Fab outline, before rotation) and pads [number, x, y, w, h, drill] (board frame)."""
    out = []
    for fp in sorted(b.GetFootprints(), key=lambda f: f.GetReference()):
        pos, rot = fp.GetPosition(), fp.GetOrientationDegrees()
        pads, seen = [], set()
        for p in fp.Pads():
            n = p.GetNumber()
            if not n: continue
            d = mm(p.GetDrillSize().x)
            sx, sy = mm(p.GetSize().x), mm(p.GetSize().y)
            if 0 < d <= 0.35 and max(sx, sy) <= 0.7: continue          # thermal vias inside the MOSFET drain pads
            if fp.GetReference() in ("J1", "J2", "J3") and d < 1.0: continue
            q = p.GetPosition(); bb = p.GetBoundingBox()
            key = (n, round(mm(q.x), 2), round(mm(q.y), 2))
            if key in seen: continue
            seen.add(key)
            pads.append([n, round(mm(q.x) - OX, 3), round(mm(q.y) - OY, 3), round(mm(bb.GetWidth()), 2), round(mm(bb.GetHeight()), 2), round(d, 2)])
        fp.SetOrientationDegrees(0)                                     # body outline in the unrotated frame
        xs, ys = [], []
        for it in fp.GraphicalItems():
            if it.GetLayer() == pcbnew.F_Fab and type(it).__name__ in ("FP_SHAPE", "PCB_SHAPE"):
                bb = it.GetBoundingBox(); xs += [bb.GetX(), bb.GetRight()]; ys += [bb.GetY(), bb.GetBottom()]
        fp.SetOrientationDegrees(rot)
        body = None
        if xs:
            body = [round(mm((min(xs) + max(xs)) / 2 - pos.x), 3), round(mm((min(ys) + max(ys)) / 2 - pos.y), 3),
                    round(mm(max(xs) - min(xs)), 2), round(mm(max(ys) - min(ys)), 2)]
        out.append({"ref": fp.GetReference(), "val": fp.GetValue(), "fp": fp.GetFPID().GetLibItemName().wx_str(),
                    "x": round(mm(pos.x) - OX, 3), "y": round(mm(pos.y) - OY, 3), "rot": round(rot, 1), "body": body, "pads": pads})
    return out

# ------------------------------------------------------------------ copper graph per net
class NetGraph:
    """Nodes: (layer, x, y) at track ends, split where a track end lands inside another track; pad centres and
    via centres are hub nodes joined to every track end that lies on them."""
    def __init__(self, b, net):
        self.b, self.net = b, net
        code = b.FindNet(net).GetNetCode()
        segs, vias = [], []
        for t in b.GetTracks():
            if t.GetNetCode() != code: continue
            if t.GetClass() == "PCB_VIA":
                vias.append((mm(t.GetPosition().x) - OX, mm(t.GetPosition().y) - OY, mm(t.GetWidth()) / 2))
            else:
                L = 0 if t.GetLayer() == pcbnew.F_Cu else 1
                segs.append([L, mm(t.GetStart().x) - OX, mm(t.GetStart().y) - OY, mm(t.GetEnd().x) - OX, mm(t.GetEnd().y) - OY, mm(t.GetWidth())])
        # split tracks where another track's end touches them (KiCad joins copper that overlaps, so a track end
        # within both half-widths of another track counts as connected)
        ends = [(s[0], s[1], s[2], s[5]) for s in segs] + [(s[0], s[3], s[4], s[5]) for s in segs]
        split, extra = [], []
        for s in segs:
            L, x0, y0, x1, y1, w = s; pts = [(0.0, x0, y0), (1.0, x1, y1)]
            dx, dy = x1 - x0, y1 - y0; l2 = dx * dx + dy * dy
            for (Le, ex, ey, we) in ends:
                if Le != L or l2 == 0: continue
                u = max(0.0, min(1.0, ((ex - x0) * dx + (ey - y0) * dy) / l2))
                px, py = x0 + u * dx, y0 + u * dy
                if math.hypot(px - ex, py - ey) > 0.45 * (w + we): continue
                if 1e-4 < u < 1 - 1e-4: pts.append((u, px, py))
                if math.hypot(px - ex, py - ey) > 1e-4: extra.append((L, ex, ey, px, py))   # short bridge to the touch point
            pts.sort()
            for a, c in zip(pts, pts[1:]):
                if math.hypot(c[1] - a[1], c[2] - a[2]) > 1e-5: split.append((L, a[1], a[2], c[1], c[2], w))
        self.adj = {}
        k = lambda L, x, y: (L, round(x, 4), round(y, 4))
        def edge(a, c, wgt):
            self.adj.setdefault(a, []).append((c, wgt)); self.adj.setdefault(c, []).append((a, wgt))
        for (L, x0, y0, x1, y1, w) in split:
            edge(k(L, x0, y0), k(L, x1, y1), math.hypot(x1 - x0, y1 - y0))
        for (L, x0, y0, x1, y1) in extra:
            edge(k(L, x0, y0), k(L, x1, y1), math.hypot(x1 - x0, y1 - y0))
        nodes = list(self.adj.keys())
        wmax = max([s[5] for s in segs] or [0.3])
        for (vx, vy, r) in vias:
            a, c = k(0, vx, vy), k(1, vx, vy); edge(a, c, 0.01)
            for n in nodes:
                if math.hypot(n[1] - vx, n[2] - vy) <= r + wmax / 2: edge(n, k(n[0], vx, vy), math.hypot(n[1] - vx, n[2] - vy))
        nodes = list(self.adj.keys())
        self.pads, self.hubxy = {}, {}
        for fp in b.GetFootprints():
            for p in fp.Pads():
                if p.GetNetCode() != code or not p.GetNumber(): continue
                cx, cy = mm(p.GetPosition().x) - OX, mm(p.GetPosition().y) - OY
                layers = [L for L, lid in ((0, pcbnew.F_Cu), (1, pcbnew.B_Cu)) if p.IsOnLayer(lid)]
                hub = ("P", fp.GetReference(), p.GetNumber())
                self.pads.setdefault((fp.GetReference(), p.GetNumber()), []).append((cx, cy))
                self.adj.setdefault(hub, [])
                if hub not in self.hubxy or p.GetSize().x * p.GetSize().y > self.hubxy[hub][3]:
                    self.hubxy[hub] = (cx, cy, layers, p.GetSize().x * p.GetSize().y)
                for n in nodes:
                    if n[0] == "P" or n[0] not in layers: continue
                    if p.HitTest(pcbnew.VECTOR2I(pcbnew.FromMM(n[1] + OX), pcbnew.FromMM(n[2] + OY)), pcbnew.FromMM(wmax / 2)):
                        edge(hub, n, math.hypot(n[1] - cx, n[2] - cy))

    def route(self, a, c):
        """Shortest copper path from pad a to pad c ('REF.PAD'), as runs [(layer, [(x, y), ...])]."""
        sa, sc = ("P",) + tuple(a.split(".")), ("P",) + tuple(c.split("."))
        if sa not in self.adj or sc not in self.adj: raise SystemExit(f"{self.net}: no pad {a if sa not in self.adj else c}")
        dist, prev, pq, tie = {sa: 0.0}, {}, [(0.0, 0, sa)], 0
        while pq:
            d, _, n = heapq.heappop(pq)
            if n == sc: break
            if d > dist.get(n, 1e18): continue
            for m, w in self.adj.get(n, []):
                if m[0] == "P" and m != sc: w += 50.0          # do not run through other pads unless there is no other way
                nd = d + w
                if nd < dist.get(m, 1e18): tie += 1; dist[m] = nd; prev[m] = n; heapq.heappush(pq, (nd, tie, m))
        if sc not in dist: return None
        seq = [sc]
        while seq[-1] != sa: seq.append(prev[seq[-1]])
        seq.reverse()
        runs, cur, layer, prev_layers = [], [], None, None
        same = lambda p, q: abs(p[0] - q[0]) < 1e-6 and abs(p[1] - q[1]) < 1e-6
        for n in seq:
            if n[0] == "P":
                x, y, layers, _ = self.hubxy[n]
                L = layer if layer in layers else layers[0]
            else:
                (L, x, y), layers = n, None
            if layer is None:
                cur, layer = [(x, y)], L
            elif L != layer:
                if len(cur) == 1 and prev_layers and L in prev_layers:
                    layer = L                                     # leaving a through-hole pad on the other side
                    if not same(cur[-1], (x, y)): cur.append((x, y))
                else:
                    if not same(cur[-1], (x, y)): cur.append((x, y))
                    runs.append((layer, cur)); cur, layer = [(x, y)], L
            elif not same(cur[-1], (x, y)):
                cur.append((x, y))
            prev_layers = layers
        runs.append((layer, cur))
        return [(L, pts) for L, pts in runs if len(pts) > 1]

# ------------------------------------------------------------------ the six paths
# leg: (net, from "REF.PAD", to "REF.PAD", style)  — net "@" = straight through the part's body
# styles: main (thick), sig (the path's own current), ctl (thin dotted: sensing / control)
MOS_X = [17.0, 28.0, 39.0, 50.0, 61.0, 72.0, 83.0, 94.0]
def main_pour():
    """150 A: J1 lug -> VIN pour -> each drain tab -> through the MOSFET -> source bar -> VOUT pour -> J2 lug."""
    out = []
    for i, x in enumerate(MOS_X):
        out.append({"l": 0, "s": "main", "p": [[58.0, 11.0], [round(0.55 * x + 0.45 * 58.0, 2), 16.5], [x, 20.0], [x, 25.0]], "pour": 1})
        out.append({"l": 0, "s": "main", "p": [[x, 25.0], [x, 33.6]], "thru": "Q%d" % (i + 1)})
        out.append({"l": 0, "s": "main", "p": [[x, 33.6], [x, 36.6]], "pour": 1, "dive": 1})
        out.append({"l": 1, "s": "main", "p": [[x, 36.6], [x, 43.5], [round(0.6 * 58.0 + 0.4 * x, 2), 51.0], [58.0, 58.0]], "pour": 1})
    return out

LEGS = {
 "pre": [
  ("pour", [[58.0, 11.0], [80.0, 12.5], [100.0, 14.5], [108.72, 20.0], [108.72, 26.46]], "sig", 0),
  ("@", "Q9.3", "Q9.2", "sig"), ("PCD", "Q9.2", "F1.1", "sig"), ("@", "F1.1", "F1.2", "sig"),
  ("PCF", "F1.2", "R12.1", "sig"), ("PCF", "F1.2", "R13.1", "sig"),
  ("@", "R12.1", "R12.2", "sig"), ("@", "R13.1", "R13.2", "sig"),
  ("pour", [[107.5, 60.24], [109.5, 66.0], [111.0, 68.0]], "sig", 0), ("pour", [[114.5, 60.24], [112.5, 66.0], [111.0, 68.0]], "sig", 0),
  ("pour", [[111.0, 68.0], [96.0, 68.0], [64.0, 66.0], [58.0, 58.0]], "sig", 1),
  ("ARM", "Q14.3", "R10.1", "ctl"), ("@", "R10.1", "R10.2", "ctl"), ("PCEN", "R10.2", "Q13.1", "ctl"),
  ("PCEN", "R10.2", "U4.2", "ctl"), ("PCEN", "R10.2", "U4.14", "ctl"),
  ("@", "R8.1", "R8.2", "ctl"), ("PCG", "R8.2", "R9.1", "ctl"), ("PCG", "Q9.1", "R9.1", "ctl"),
  ("@", "R9.1", "R9.2", "ctl"), ("PDRV", "R9.2", "Q13.3", "ctl"), ("@", "Q13.3", "Q13.2", "ctl"),
  ("VOUT_K", "RK2.2", "R28.1", "ctl"), ("@", "R28.1", "R28.2", "ctl"), ("VOD", "R28.2", "U4.5", "ctl"), ("VOD", "R28.2", "U4.7", "ctl"),
  ("VIN_K", "RK1.2", "R33.1", "ctl"), ("@", "R33.1", "R33.2", "ctl"), ("RAMP", "R33.2", "U4.4", "ctl"),
  ("VIN_K", "RK1.2", "R31.1", "ctl"), ("@", "R31.1", "R31.2", "ctl"), ("VIND", "R31.2", "U4.6", "ctl"),
  ("VIN_K", "RK1.2", "R4.1", "ctl"), ("@", "R4.1", "R4.2", "ctl"), ("OVP", "R4.2", "U4.8", "ctl"),
  ("@", "R45.1", "R45.2", "ctl"), ("REF2", "R45.2", "U4.9", "ctl")],
 "gate": [
  ("GDRV", "U1.10", "D9.2", "sig"), ("@", "D9.2", "D9.1", "sig")] +
  [("FG", "D9.1", f"RG{i}.2", "sig") for i in range(1, 9)] +
  [x for i in range(1, 9) for x in (("@", f"RG{i}.2", f"RG{i}.1", "sig"), (f"G{i}", f"RG{i}.1", f"Q{i}.1", "sig"))] + [
  ("@", "RK1.1", "RK1.2", "ctl"), ("VIN_K", "RK1.2", "U1.2", "ctl"), ("VIN_K", "RK1.2", "R1.1", "ctl"), ("@", "R1.1", "R1.2", "ctl"), ("SNS", "R1.2", "U1.1", "ctl"),
  ("@", "RK2.1", "RK2.2", "ctl"), ("VOUT_K", "RK2.2", "U1.9", "ctl")],
 "off": [x for i in range(1, 9) for x in ((f"G{i}", f"Q{i}.1", f"RG{i}.1", "sig"), ("@", f"RG{i}.1", f"RG{i}.2", "sig"), ("FG", f"RG{i}.2", "Q11.2", "sig"))] + [
  ("@", "Q11.2", "Q11.3", "sig"), ("QOFF", "Q11.3", "R44.1", "sig"), ("@", "R44.1", "R44.2", "sig"), ("VOUT_K", "R44.2", "RK2.2", "sig"), ("@", "RK2.2", "RK2.1", "sig"),
  ("@", "Q11.2", "Q11.1", "ctl"), ("PNB2", "Q11.1", "R43.2", "ctl"), ("@", "R43.2", "R43.1", "ctl"), ("GDRV", "R43.1", "U1.10", "ctl")],
 "arm": [
  ("VINL", "R14.2", "U3.3", "ctl"), ("V5", "U3.2", "R17.1", "sig"), ("@", "R17.1", "R17.2", "sig"), ("RIN", "R17.2", "J6.1", "sig"),
  ("ROUT", "J6.2", "Q14.2", "sig"), ("@", "Q14.2", "Q14.3", "sig"), ("ARM", "Q14.3", "R26.1", "sig"), ("@", "R26.1", "R26.2", "sig"), ("EN", "R26.2", "U1.5", "sig"),
  ("EN", "R26.2", "C12.1", "sig"),
  ("V5", "U3.2", "R18.1", "ctl"), ("@", "R18.1", "R18.2", "ctl"), ("V5S", "R18.2", "J4.2", "ctl"),
  ("HG", "Q14.1", "R20.1", "ctl"), ("@", "R20.1", "R20.2", "ctl"), ("HALL", "R20.2", "J4.1", "ctl"),
  ("V5S", "R18.2", "R41.1", "ctl"), ("@", "R41.1", "R41.2", "ctl"), ("HLA", "R41.2", "D6.2", "ctl"), ("@", "D6.2", "D6.1", "ctl"), ("HALL", "D6.1", "J4.1", "ctl"),
  ("ROUT", "J6.2", "R42.1", "ctl"), ("@", "R42.1", "R42.2", "ctl"), ("RLA", "R42.2", "D7.2", "ctl"),
  ("VOUT_K", "RK2.2", "R39.1", "ctl"), ("@", "R39.1", "R39.2", "ctl"), ("LIVEA", "R39.2", "LED1.2", "ctl")],
 "kill": [
  ("ARM", "C11.1", "R22.1", "sig"), ("@", "R22.1", "R22.2", "sig"),
  ("@", "R25.1", "R25.2", "sig"), ("NARM", "R25.2", "Q16.1", "sig"), ("NARM", "R25.2", "Q12.1", "sig"), ("NARM", "R25.2", "Q17.1", "ctl"),
  ("EN", "U1.5", "R27.2", "sig"), ("@", "R27.2", "R27.1", "sig"), ("END", "R27.1", "Q16.3", "sig"), ("@", "Q16.3", "Q16.2", "sig"),
  ("EN", "C12.1", "Q10.2", "sig"), ("@", "Q10.2", "Q10.3", "sig"), ("@", "Q10.2", "Q10.1", "ctl"), ("PNB", "Q10.1", "R21.1", "ctl"), ("@", "R21.1", "R21.2", "ctl"),
  ("@", "R7.1", "R7.2", "sig"), ("KA", "R7.2", "U2.1", "sig"), ("@", "U2.1", "U2.2", "sig"), ("KC", "U2.2", "Q12.3", "sig"), ("@", "Q12.3", "Q12.2", "sig"),
  *[("FG", f"RG{i}.2", "U2.4", "sig") for i in range(1, 9)], ("@", "U2.4", "U2.3", "sig"), ("VOUT_K", "U2.3", "RK2.2", "sig"), ("@", "RK2.2", "RK2.1", "sig"),
  ("@", "R36.1", "R36.2", "ctl"), ("LSAFE", "R36.2", "D8.2", "ctl")],
}

def padxy(b, ref):
    r, n = ref.split(".")
    fp = b.FindFootprintByReference(r)
    ps = [p for p in fp.Pads() if p.GetNumber() == n]
    big = max(ps, key=lambda p: p.GetSize().x * p.GetSize().y)
    return [round(mm(big.GetPosition().x) - OX, 3), round(mm(big.GetPosition().y) - OY, 3)]

def paths(b):
    graphs, out, missing = {}, {"main": main_pour()}, []
    for pid, legs in LEGS.items():
        lines = []
        for leg in legs:
            if leg[0] == "pour":
                lines.append({"l": leg[3], "s": leg[2], "p": leg[1], "pour": 1}); continue
            net, a, c, st = leg
            if net == "@":
                lines.append({"l": 0, "s": st, "p": [padxy(b, a), padxy(b, c)], "thru": a.split(".")[0]}); continue
            if a == c: continue                                           # marker only
            g = graphs.get(net) or graphs.setdefault(net, NetGraph(b, net))
            runs = g.route(a, c)
            if not runs:
                missing.append(f"{pid}: {net} {a}->{c}")
                lines.append({"l": 0, "s": st, "p": [padxy(b, a), padxy(b, c)], "gap": 1}); continue
            for L, pts in runs: lines.append({"l": L, "s": st, "p": [[round(x, 3), round(y, 3)] for x, y in pts]})
        out[pid] = lines
    if missing: print("legs with no track (drawn straight):", missing)
    return out

def write(b):
    data = {"BW": W, "BH": H, "PARTS": parts(b), "PATHS": paths(b)}
    js = ("/* ---------- generated by make_3d_data.py from ../kicad/ks_power.kicad_pcb ---------- */\n"
          f"const BW = {W:g}, BH = {H:g};\n"
          f"const PARTS = {json.dumps(data['PARTS'], separators=(',', ':'))};\n"
          f"const PATHS = {json.dumps(data['PATHS'], separators=(',', ':'))};\n"
          "/* ---------- end generated ---------- */")
    t = open(HTML).read()
    t, n = re.subn(r"/\* ---------- generated by make_3d_data\.py.*?/\* ---------- end generated ---------- \*/", lambda m: js, t, count=1, flags=re.S)
    if n != 1: raise SystemExit("generated block not found in index.html")
    open(HTML, "w").write(t)
    print("PARTS", len(data["PARTS"]), "PATHS", {k: len(v) for k, v in data["PATHS"].items()})

if __name__ == "__main__":
    import sys
    if "--no-tex" not in sys.argv: textures()
    write(pcbnew.LoadBoard(PCB))
