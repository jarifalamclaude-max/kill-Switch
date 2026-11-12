"""Make the 3D view's data from the through-hole kill switch PCB (../kicad/ks_tht.kicad_pcb):

* tex_top.jpg / tex_bot.jpg: the board as a gerber viewer shows it (green mask, lighter green over copper,
  silver pads, bare FR4 where the mask is open over no copper, white silkscreen, black holes). Both are drawn as
  seen from the top, which is what index.html expects.
* PARTS: every footprint with its value, position, rotation, pads in the footprint's own frame and the body box
  from its F.Fab outline, so index.html can build each part in its own frame and turn it like KiCad does.
* PATHS: the current paths, each a list of polylines that follow the real copper:
    - on tracks, a shortest-path search over the net's tracks, vias and pads (bends exactly where the copper does);
    - through the VIN / VOUT / GND pours, a search over a raster of the pour's filled copper that keeps to the
      middle of the copper, then straightened only where the straight line stays on that copper;
    - through a part (pad to pad), a straight line marked "thru", so the page can light the part up.

Run with KiCad 7's python (KICAD7_FOOTPRINT_DIR set):  python3 make_3d_data.py [--no-tex]
It rewrites both textures and the generated data block in index.html. It only reads the board.
"""
import heapq, json, math, os, re, subprocess, sys, tempfile
import numpy as np
from PIL import Image, ImageDraw
import pcbnew

HERE = os.path.dirname(os.path.abspath(__file__))
PCB = os.path.join(HERE, "..", "kicad", "ks_tht.kicad_pcb")
HTML = os.path.join(HERE, "index.html")
W, H, PX = 120.0, 98.0, 20.0                   # board size (mm), texture pixels per mm
OX = OY = 100.0
MASK, MASK_CU, SILK, PAD, FR4, HOLE = (29, 91, 50), (40, 112, 62), (236, 238, 238), (214, 216, 218), (196, 170, 110), (13, 13, 13)
mm = pcbnew.ToMM
LAYERS = ((0, pcbnew.F_Cu), (1, pcbnew.B_Cu))

# ------------------------------------------------------------------ textures (same method as the torpedo board)
def render(layer, tmp):
    svg, png = os.path.join(tmp, layer + ".svg"), os.path.join(tmp, layer + ".png")
    subprocess.run(["kicad-cli", "pcb", "export", "svg", "--layers", layer, "--black-and-white", "--exclude-drawing-sheet",
                    "--page-size-mode", "2", "--drill-shape-opt", "0", "-o", svg, PCB], check=True, capture_output=True)
    head = open(svg).read(1000)
    wmm = float(head.split('width="')[1].split("mm")[0])
    subprocess.run(["rsvg-convert", "-w", str(int(round(wmm * PX))), "-b", "white", svg, "-o", png], check=True)
    return np.asarray(Image.open(png).convert("L")) < 128                 # True where the layer has ink

def textures(b):
    with tempfile.TemporaryDirectory() as tmp:
        edge = render("Edge.Cuts", tmp)
        ys, xs = np.nonzero(edge)
        x0, x1, y0, y1 = xs.min(), xs.max(), ys.min(), ys.max()          # outer edge of the outline line
        lw = max(1, int(round(0.1 * PX)))
        box = (x0 + lw // 2, y0 + lw // 2, x1 - lw // 2, y1 - lw // 2)
        size = (int(round(W * PX)), int(round(H * PX)))
        def crop(a): return np.asarray(Image.fromarray(a.astype(np.uint8) * 255).crop(box).resize(size, Image.NEAREST)) > 127
        holes = []
        for fp in b.GetFootprints():
            for p in fp.Pads():
                d = p.GetDrillSize()
                if d.x > 0: holes.append((mm(p.GetPosition().x) - OX, mm(p.GetPosition().y) - OY, mm(d.x) / 2, mm(d.y) / 2, p.GetOrientationDegrees()))
        for t in b.GetTracks():
            if t.GetClass() == "PCB_VIA":
                r = mm(t.GetDrillValue()) / 2
                holes.append((mm(t.GetPosition().x) - OX, mm(t.GetPosition().y) - OY, r, r, 0))
        for side, (cu, mk, sk) in (("top", ("F.Cu", "F.Mask", "F.Silkscreen")), ("bot", ("B.Cu", "B.Mask", "B.Silkscreen"))):
            copper, opening, silk = crop(render(cu, tmp)), crop(render(mk, tmp)), crop(render(sk, tmp))
            img = np.zeros(copper.shape + (3,), dtype=np.uint8); img[:] = MASK
            img[copper] = MASK_CU
            img[opening & copper] = PAD; img[opening & ~copper] = FR4
            img[silk & ~opening] = SILK
            im = Image.fromarray(img); dr = ImageDraw.Draw(im)
            for x, y, rx, ry, ang in holes:
                if abs(rx - ry) > 0.01 and round(ang) % 180 == 90: rx, ry = ry, rx      # slotted pegs turned with the part
                if abs(rx - ry) > 0.01:                                               # slot: a stadium, drawn as a fat line
                    r = min(rx, ry); dx, dy = (rx - r, 0) if rx > ry else (0, ry - r)
                    dr.line([((x - dx) * PX, (y - dy) * PX), ((x + dx) * PX, (y + dy) * PX)], fill=HOLE, width=int(round(2 * r * PX)))
                    for s in (-1, 1): dr.ellipse([(x + s * dx - r) * PX, (y + s * dy - r) * PX, (x + s * dx + r) * PX, (y + s * dy + r) * PX], fill=HOLE)
                else:
                    dr.ellipse([(x - rx) * PX, (y - ry) * PX, (x + rx) * PX, (y + ry) * PX], fill=HOLE)
            out = os.path.join(HERE, f"tex_{side}.jpg")
            im.save(out, quality=84, optimize=True, progressive=True)
            print(f"tex_{side}.jpg", im.size, os.path.getsize(out) // 1024, "kB")

# ------------------------------------------------------------------ parts
def parts(b):
    """ref, value, footprint, board position, rotation (degrees, KiCad sense), pads [number, lx, ly, w, h, drill] in the
    footprint's own frame, and the F.Fab body box [x0, y0, x1, y1] in that frame."""
    out = []
    for fp in sorted(b.GetFootprints(), key=lambda f: (re.sub(r"\d+", "", f.GetReference()), int(re.sub(r"\D", "", f.GetReference()) or 0))):
        pos, rot = fp.GetPosition(), fp.GetOrientationDegrees()
        fp.SetOrientationDegrees(0)
        pads = []
        for p in fp.Pads():
            q = p.GetPosition()
            pads.append([p.GetNumber(), round(mm(q.x - pos.x), 3), round(mm(q.y - pos.y), 3), round(mm(p.GetSize().x), 2),
                         round(mm(p.GetSize().y), 2), round(mm(p.GetDrillSize().x), 2)])
        xs, ys = [], []
        for it in fp.GraphicalItems():
            if it.GetLayer() == pcbnew.F_Fab and type(it).__name__ == "FP_SHAPE":
                bb = it.GetBoundingBox(); xs += [bb.GetX(), bb.GetRight()]; ys += [bb.GetY(), bb.GetBottom()]
        fp.SetOrientationDegrees(rot)
        fab = [round(mm(min(xs) - pos.x), 2), round(mm(min(ys) - pos.y), 2), round(mm(max(xs) - pos.x), 2), round(mm(max(ys) - pos.y), 2)] if xs else None
        out.append({"ref": fp.GetReference(), "val": fp.GetValue(), "fp": fp.GetFPID().GetLibItemName().wx_str(),
                    "x": round(mm(pos.x) - OX, 3), "y": round(mm(pos.y) - OY, 3), "rot": round(rot, 1), "fab": fab, "pads": pads})
    return out

# ------------------------------------------------------------------ copper graph of a net's tracks
class NetGraph:
    """Nodes: (layer, x, y) at track ends, split where another track end touches a track; pad centres and via
    centres are hub nodes joined to every track end that lies on them (through-hole pads join both layers)."""
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
                if math.hypot(px - ex, py - ey) > 1e-4: extra.append((L, ex, ey, px, py))
            pts.sort()
            for a, c in zip(pts, pts[1:]):
                if math.hypot(c[1] - a[1], c[2] - a[2]) > 1e-5: split.append((L, a[1], a[2], c[1], c[2], w))
        self.adj = {}
        k = lambda L, x, y: (L, round(x, 4), round(y, 4))
        def edge(a, c, wgt):
            self.adj.setdefault(a, []).append((c, wgt)); self.adj.setdefault(c, []).append((a, wgt))
        for (L, x0, y0, x1, y1, w) in split: edge(k(L, x0, y0), k(L, x1, y1), math.hypot(x1 - x0, y1 - y0))
        for (L, x0, y0, x1, y1) in extra: edge(k(L, x0, y0), k(L, x1, y1), math.hypot(x1 - x0, y1 - y0))
        nodes = list(self.adj.keys())
        wmax = max([s[5] for s in segs] or [0.3])
        for (vx, vy, r) in vias:
            edge(k(0, vx, vy), k(1, vx, vy), 0.01)
            for n in nodes:
                if math.hypot(n[1] - vx, n[2] - vy) <= r + wmax / 2: edge(n, k(n[0], vx, vy), math.hypot(n[1] - vx, n[2] - vy))
        nodes = list(self.adj.keys())
        self.hubxy = {}
        for fp in b.GetFootprints():
            for p in fp.Pads():
                if p.GetNetCode() != code or not p.GetNumber(): continue
                cx, cy = mm(p.GetPosition().x) - OX, mm(p.GetPosition().y) - OY
                layers = [L for L, lid in LAYERS if p.IsOnLayer(lid)]
                hub = ("P", fp.GetReference(), p.GetNumber())
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
        for s, nm in ((sa, a), (sc, c)):
            if s not in self.adj: raise SystemExit(f"{self.net}: no pad {nm}")
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
        same = lambda p, q: abs(p[0] - q[0]) < 1e-6 and abs(p[1] - q[1]) < 1e-6
        runs, cur, layer = [], [], None
        for n in seq:
            if n[0] == "P":
                x, y, layers, _ = self.hubxy[n]
                L = layer if layer in layers else layers[0]
            else:
                L, x, y = n
            if layer is None:
                cur, layer = [(x, y)], L; continue
            if L != layer:                                         # layer change at a via or a through-hole pad
                runs.append((layer, cur)); cur = [cur[-1]]; layer = L
            if not same(cur[-1], (x, y)): cur.append((x, y))
        runs.append((layer, cur))
        return [(L, pts) for L, pts in runs if len(pts) > 1]

# ------------------------------------------------------------------ routes through a copper pour
class PourMap:
    """Raster (RES cells per mm) of everything of one net on one copper layer: the filled zone, its pads and tracks.
    route() runs A* over it with a cost that keeps to the middle of the copper, then straightens the result
    wherever a straight line stays on the copper at least as far from the edge as the A* path did."""
    RES = 4.0
    def __init__(self, b, net, layer):
        code, lid = b.FindNet(net).GetNetCode(), dict(LAYERS)[layer]
        R = self.RES; img = Image.new("L", (int(W * R), int(H * R)), 0); dr = ImageDraw.Draw(img)
        P = lambda v: ((mm(v.x) - OX) * R, (mm(v.y) - OY) * R)
        for z in b.Zones():
            if z.GetIsRuleArea() or z.GetNetCode() != code or not z.IsOnLayer(lid): continue
            polys = z.GetFilledPolysList(lid)
            for i in range(polys.OutlineCount()):
                o = polys.Outline(i); dr.polygon([P(o.CPoint(j)) for j in range(o.PointCount())], fill=255)
                for h in range(polys.HoleCount(i)):
                    hh = polys.Hole(i, h); dr.polygon([P(hh.CPoint(j)) for j in range(hh.PointCount())], fill=0)
        for fp in b.GetFootprints():
            for p in fp.Pads():
                if p.GetNetCode() != code or not p.IsOnLayer(lid): continue
                bb = p.GetBoundingBox(); x0, y0 = P(pcbnew.VECTOR2I(bb.GetLeft(), bb.GetTop())); x1, y1 = P(pcbnew.VECTOR2I(bb.GetRight(), bb.GetBottom()))
                dr.ellipse([x0, y0, x1, y1], fill=255)
        for t in b.GetTracks():
            if t.GetNetCode() == code and t.IsOnLayer(lid) and t.GetClass() == "PCB_TRACK":
                dr.line([P(t.GetStart()), P(t.GetEnd())], fill=255, width=max(1, int(mm(t.GetWidth()) * R)))
        self.mask = np.asarray(img) > 127
        # distance to the copper edge (mm), by repeated erosion (alternating 4- and 8-neighbour: close to Euclidean)
        d = np.zeros(self.mask.shape, np.float32); cur = self.mask.copy(); k = 0
        while cur.any() and k < 200:
            k += 1; d[cur] = k
            n = cur.copy()
            n[1:, :] &= cur[:-1, :]; n[:-1, :] &= cur[1:, :]; n[:, 1:] &= cur[:, :-1]; n[:, :-1] &= cur[:, 1:]
            n[0, :] = n[-1, :] = False; n[:, 0] = n[:, -1] = False
            if k % 2 == 0:
                n[1:, 1:] &= cur[:-1, :-1]; n[1:, :-1] &= cur[:-1, 1:]; n[:-1, 1:] &= cur[1:, :-1]; n[:-1, :-1] &= cur[1:, 1:]
            cur = n
        self.d = d / R
        self.net, self.layer = net, layer

    def cell(self, x, y):
        """Nearest copper cell to (x, y) mm."""
        R = self.RES; ix, iy = int(x * R), int(y * R)
        if self.mask[iy, ix]: return iy, ix
        ys, xs = np.nonzero(self.mask[max(iy - 40, 0):iy + 41, max(ix - 40, 0):ix + 41])
        k = np.argmin((ys + max(iy - 40, 0) - iy) ** 2 + (xs + max(ix - 40, 0) - ix) ** 2)
        return int(ys[k] + max(iy - 40, 0)), int(xs[k] + max(ix - 40, 0))

    def ok(self, a, c, need):
        """Straight line a -> c (mm) stays on copper at least `need` mm from its edge."""
        L = math.hypot(c[0] - a[0], c[1] - a[1]); n = max(int(L / 0.1), 1); R = self.RES
        for i in range(n + 1):
            x = a[0] + (c[0] - a[0]) * i / n; y = a[1] + (c[1] - a[1]) * i / n
            if self.d[int(y * R), int(x * R)] < need - 1e-6: return False
        return True

    def route(self, a, c, margin=1.0, pull=3.0):
        R = self.RES; ny, nx = self.mask.shape
        s, g = self.cell(*a), self.cell(*c)
        gs = np.full(self.mask.shape, np.inf); gs[s] = 0.0; prev = {}
        pen = 1.0 + pull * np.exp(-self.d / 1.0)
        pq = [(0.0, 0.0, s)]; nb = [(-1, 0, 1), (1, 0, 1), (0, -1, 1), (0, 1, 1), (-1, -1, 1.4142), (-1, 1, 1.4142), (1, -1, 1.4142), (1, 1, 1.4142)]
        while pq:
            f, gc, u = heapq.heappop(pq)
            if u == g: break
            if gc > gs[u]: continue
            for dy, dx, w in nb:
                v = (u[0] + dy, u[1] + dx)
                if not (0 <= v[0] < ny and 0 <= v[1] < nx) or not self.mask[v]: continue
                ng = gc + w * pen[v] / R
                if ng < gs[v]:
                    gs[v] = ng; prev[v] = u
                    heapq.heappush(pq, (ng + math.hypot(v[0] - g[0], v[1] - g[1]) / R, ng, v))
        if g not in prev and g != s: raise SystemExit(f"pour {self.net} L{self.layer}: no copper path {a} -> {c}")
        cells = [g]
        while cells[-1] != s: cells.append(prev[cells[-1]])
        cells.reverse()
        pts = [((ix + 0.5) / R, (iy + 0.5) / R) for iy, ix in cells]
        dv = [float(self.d[iy, ix]) for iy, ix in cells]
        out, i = [pts[0]], 0                                     # string pulling
        while i < len(pts) - 1:
            j = len(pts) - 1
            while j > i + 1:
                need = min(margin, min(dv[i:j + 1]))
                if self.ok(pts[i], pts[j], need): break
                j -= 1
            out.append(pts[j]); i = j
        out = [a] + out[1:-1] + [c] if len(out) > 2 else [a, c]
        return [[round(x, 2), round(y, 2)] for x, y in out]

# ------------------------------------------------------------------ the current paths
# A leg is one of:
#   ("NET", "REF.PAD", "REF.PAD", style)        along the net's tracks
#   ("@", "REF.PAD", "REF.PAD", style)          through the part (pad to pad)
#   ("~NET", layer, "REF.PAD", "REF.PAD", style) through that net's pour on layer 0 (F.Cu) or 1 (B.Cu)
# styles: "main" (the big current), "ret" (its return), "sig" (this path's own current), "ctl" (a control signal)
FETS = [f"Q{i}" for i in range(1, 5)]
DRAIN_X = [36.83, 49.53, 62.23, 74.93]; SRC_X = [39.37, 52.07, 64.77, 77.47]
WV, WO, WG = 8.1, 22.7, 107.8              # centre lines of the VIN wire (top), VOUT wire (top) and the GND wire (bottom)
LEGS = {
 "main": [("~VIN", 0, "J1.2", [12.8, WV], "main"), ("=", 0, [[12.8, WV], [DRAIN_X[-1], WV]], "main")]
         + [x for q, xd, xs in zip(FETS, DRAIN_X, SRC_X) for x in (("~VIN", 0, [xd, WV], f"{q}.2", "main"), ("@", f"{q}.2", f"{q}.3", "main"),
                                                                    ("~VOUT", 0, f"{q}.3", [xs, WO], "main"))]
         + [("=", 0, [[SRC_X[0], WO], [108.2, WO]], "main"), ("~VOUT", 0, [108.2, WO], "J2.2", "main"),
            ("~GND", 1, "J2.1", [WG, 23.4], "ret"), ("=", 1, [[WG, 23.4], [WG, WV], [31.6, WV]], "ret"), ("~GND", 1, [31.6, WV], "J1.1", "ret")],
 "pre": [("~VIN", 0, "J1.2", "Q5.3", "sig"), ("@", "Q5.3", "Q5.2", "sig"), ("PCD", "Q5.2", "F1.1", "sig"), ("@", "F1.1", "F1.2", "sig"),
         ("PCF", "F1.2", "R3.1", "sig"), ("PCF", "F1.2", "R4.1", "sig"), ("@", "R3.1", "R3.2", "sig"), ("@", "R4.1", "R4.2", "sig"),
         ("VOUT", "R4.2", "R3.2", "sig"), ("VOUT", "R3.2", "RK2.1", "sig"), ("~VOUT", 0, "RK2.1", "J2.2", "sig"),
         ("@", "R1.1", "R1.2", "ctl"), ("PCG", "R1.2", "Q5.1", "ctl"), ("PCG", "Q5.1", "R2.1", "ctl"), ("@", "R2.1", "R2.2", "ctl"),
         ("PCDN", "R2.2", "Q6.3", "ctl"), ("@", "Q6.3", "Q6.1", "ctl"), ("@", "D3.1", "D3.2", "ctl"), ("PCG", "D3.2", "Q5.1", "ctl")],
 "gate": [("V5", "C4.1", "U3.2", "ctl"), ("@", "U3.2", "U3.4", "sig"), ("V12F", "U3.4", "U4.4", "sig"), ("@", "U4.4", "U4.3", "sig"),
          ("DRV", "U4.3", "D10.2", "sig"), ("@", "D10.2", "D10.1", "sig"), ("DRVD", "D10.1", "R35.1", "sig"), ("@", "R35.1", "R35.2", "sig")]
         + [("FG", "R35.2", f"RG{i}.2", "sig") for i in range(1, 5)]
         + [x for i in range(1, 5) for x in (("@", f"RG{i}.2", f"RG{i}.1", "sig"), (f"G{i}", f"RG{i}.1", f"Q{i}.1", "sig"))]
         + [("~VOUT", 0, "Q2.3", "RK2.1", "ret"), ("@", "RK2.1", "RK2.2", "ret"), ("SRC", "RK2.2", "U3.3", "ret"),
            ("FG", "R35.2", "R39.2", "ctl"), ("@", "R39.2", "R39.1", "ctl"), ("FGC", "R39.1", "C6.1", "ctl"),
            ("FG", "R35.2", "D11.1", "ctl"), ("@", "D11.1", "D11.2", "ctl"),
            ("V12F", "U3.4", "D5.1", "ctl"), ("V12F", "U3.4", "R33.1", "ctl"), ("V12F", "U3.4", "C5.1", "ctl")],
 "arm": [("V5", "C2.1", "R9.1", "ctl"), ("@", "R9.1", "R9.2", "sig"), ("RIN", "R9.2", "J4.1", "sig"), ("ROUT", "J4.2", "Q7.1", "sig"),
         ("@", "Q7.1", "Q7.3", "sig"), ("ARM", "Q7.3", "R15.1", "sig"), ("@", "R15.1", "R15.2", "sig"), ("EN", "R15.2", "C7.1", "sig"),
         ("@", "Q7.1", "Q7.2", "ctl"), ("QAB", "Q7.2", "R10.1", "ctl"), ("@", "R10.1", "R10.2", "ctl"), ("HALL", "R10.2", "J3.1", "ctl"),
         ("V5", "C2.1", "R8.1", "ctl"), ("@", "R8.1", "R8.2", "ctl"), ("V5S", "R8.2", "J3.2", "ctl"),
         ("V5S", "R8.2", "R13.1", "ctl"), ("@", "R13.1", "R13.2", "ctl"), ("HLA", "R13.2", "D7.2", "ctl"), ("@", "D7.2", "D7.1", "ctl"),
         ("ROUT", "J4.2", "R14.1", "ctl"), ("@", "R14.1", "R14.2", "ctl"), ("RLA", "R14.2", "D8.2", "ctl"),
         ("ARM", "Q7.3", "R16.1", "ctl"), ("@", "R16.1", "R16.2", "ctl"), ("QIB", "R16.2", "Q8.2", "ctl"),
         ("EN", "R15.2", "U2.5", "ctl"), ("EN", "R15.2", "U2.11", "ctl")],
 "seq": [("@", "R32.1", "R32.2", "sig"), ("UGA", "R32.2", "U4.1", "sig"), ("@", "U4.1", "U4.2", "sig"), ("CATH", "U4.2", "Q11.3", "sig"),
         ("@", "R31.1", "R31.2", "sig"), ("LVA", "R31.2", "D9.2", "sig"), ("@", "D9.2", "D9.1", "sig"), ("CATH", "D9.1", "Q11.3", "sig"),
         ("@", "Q11.3", "Q11.1", "sig"), ("QGM", "Q11.1", "Q10.3", "sig"), ("@", "Q10.3", "Q10.1", "sig"),
         ("REF", "R6.2", "U2.4", "ctl"), ("REF", "R6.2", "U2.10", "ctl"), ("@", "U2.5", "U2.2", "ctl"), ("PCEN", "U2.2", "Q10.2", "ctl"),
         ("PCEN", "U2.2", "Q6.2", "ctl"), ("PCEN", "U2.2", "R29.2", "ctl"), ("PCEN", "U2.2", "U2.1", "ctl"),
         ("@", "R21.1", "R21.2", "ctl"), ("VOD", "R21.2", "U2.7", "ctl"), ("VOD", "R21.2", "U2.9", "ctl"),
         ("@", "R26.1", "R26.2", "ctl"), ("RAMP", "R26.2", "U2.6", "ctl"), ("@", "R24.1", "R24.2", "ctl"), ("VIND", "R24.2", "U2.8", "ctl"),
         ("@", "U2.9", "U2.14", "ctl"), ("DONE", "U2.14", "Q11.2", "ctl"), ("DONE", "U2.14", "R30.2", "ctl"),
         ("RRST", "U2.13", "R28.2", "ctl"), ("@", "R28.2", "R28.1", "ctl")],
 "kill": [("EN", "C7.1", "R20.2", "sig"), ("@", "R20.2", "R20.1", "sig"), ("QDC", "R20.1", "Q9.3", "sig"), ("@", "Q9.3", "Q9.1", "sig"),
          ("@", "R17.1", "R17.2", "ctl"), ("NARM", "R17.2", "R18.1", "ctl"), ("@", "R18.1", "R18.2", "ctl"), ("QDB", "R18.2", "Q9.2", "ctl"),
          ("EN", "C7.1", "U2.5", "ctl")]
         + [x for i in range(1, 5) for x in ((f"G{i}", f"Q{i}.1", f"RG{i}.1", "sig"), ("@", f"RG{i}.1", f"RG{i}.2", "sig"), ("FG", f"RG{i}.2", "Q12.3", "sig"))]
         + [("FGC", "C6.1", "R39.1", "sig"), ("@", "R39.1", "R39.2", "sig"), ("FG", "R39.2", "Q12.3", "sig"), ("@", "Q12.3", "Q12.1", "sig"), ("QOC", "Q12.1", "R36.1", "sig"), ("@", "R36.1", "R36.2", "sig"),
            ("SRC", "R36.2", "RK2.2", "sig"), ("@", "RK2.2", "RK2.1", "sig"),
            ("@", "R34.1", "R34.2", "ctl"), ("DRV", "U4.3", "R38.2", "ctl"), ("@", "R38.2", "R38.1", "ctl"), ("QOD", "R38.1", "D6.1", "ctl"),
            ("@", "D6.1", "D6.2", "ctl"), ("QOB", "D6.2", "Q12.2", "ctl")],
 "v5": [("~VIN", 0, "J1.2", "RK1.1", "sig"), ("@", "RK1.1", "RK1.2", "sig"), ("VIN_K", "RK1.2", "D4.2", "sig"), ("@", "D4.2", "D4.1", "sig"),
        ("VR1", "D4.1", "R5.1", "sig"), ("@", "R5.1", "R5.2", "sig"), ("VR2", "R5.2", "U1.1", "sig"), ("VR2", "R5.2", "C1.1", "ctl"),
        ("@", "U1.1", "U1.3", "sig"), ("V5", "U1.3", "C2.1", "sig"), ("V5", "U1.3", "U3.2", "sig"), ("V5", "U1.3", "U2.3", "sig"),
        ("V5", "U1.3", "R32.1", "sig"), ("V5", "U1.3", "R9.1", "sig"), ("V5", "U1.3", "R6.1", "ctl"), ("@", "R6.1", "R6.2", "ctl")],
}
WIDTH = {"main": 2.6, "ret": 2.6, "sig": 0.9, "ctl": 0.5}           # pour routes keep this far from the copper edge (half ribbon)

def padxy(b, ref):
    if isinstance(ref, (list, tuple)): return [float(ref[0]), float(ref[1])]
    r, n = ref.split(".")
    ps = [p for p in b.FindFootprintByReference(r).Pads() if p.GetNumber() == n]
    big = max(ps, key=lambda p: p.GetSize().x * p.GetSize().y)
    return [round(mm(big.GetPosition().x) - OX, 3), round(mm(big.GetPosition().y) - OY, 3)]

def paths(b):
    graphs, pours, out, missing = {}, {}, {}, []
    for pid, legs in LEGS.items():
        lines, vias = [], []
        for leg in legs:
            if leg[0] == "=":
                lines.append({"l": leg[1], "s": leg[3], "p": [[round(x, 2), round(y, 2)] for x, y in leg[2]], "wire": 1}); continue
            if leg[0].startswith("~"):
                net, layer, a, c, st = leg[0][1:], leg[1], leg[2], leg[3], leg[4]
                pm = pours.get((net, layer)) or pours.setdefault((net, layer), PourMap(b, net, layer))
                lines.append({"l": layer, "s": st, "p": pm.route(padxy(b, a), padxy(b, c), margin=WIDTH[st] / 2), "pour": net}); continue
            net, a, c, st = leg
            if net == "@":
                lines.append({"l": 0, "s": st, "p": [padxy(b, a), padxy(b, c)], "thru": a.split(".")[0]}); continue
            g = graphs.get(net) or graphs.setdefault(net, NetGraph(b, net))
            runs = g.route(a, c)
            if not runs:
                missing.append(f"{pid}: {net} {a}->{c}")
                lines.append({"l": 0, "s": st, "p": [padxy(b, a), padxy(b, c)], "gap": 1}); continue
            for L, pts in runs: lines.append({"l": L, "s": st, "p": [[round(x, 3), round(y, 3)] for x, y in pts]})
            for (L0, p0), (L1, p1) in zip(runs, runs[1:]):
                if L0 != L1: vias.append([round(p1[0][0], 3), round(p1[0][1], 3)])
        out[pid] = {"lines": lines, "vias": vias}
    if missing: print("legs with no copper found (drawn straight):", missing)
    return out

def wires(b):
    """The bare-copper strips (rectangles on F.Mask / B.Mask) carry a soldered 12 AWG wire: one straight piece
    along the long axis of each strip, [layer, x0, y0, x1, y1]."""
    out = []
    for d in b.GetDrawings():
        if d.GetLayer() not in (pcbnew.F_Mask, pcbnew.B_Mask): continue
        bb = d.GetBoundingBox(); x0, y0, x1, y1 = mm(bb.GetLeft()) - OX, mm(bb.GetTop()) - OY, mm(bb.GetRight()) - OX, mm(bb.GetBottom()) - OY
        L = 0 if d.GetLayer() == pcbnew.F_Mask else 1
        if x1 - x0 >= y1 - y0: out.append([L, round(x0 + 0.3, 2), round((y0 + y1) / 2, 2), round(x1 - 0.3, 2), round((y0 + y1) / 2, 2)])
        else: out.append([L, round((x0 + x1) / 2, 2), round(y0 - 0.5, 2), round((x0 + x1) / 2, 2), round(y1 - 0.3, 2)])
    return out

def write(b):
    data = {"PARTS": parts(b), "PATHS": paths(b)}
    js = ("/* ---------- generated by make_3d_data.py from ../kicad/ks_tht.kicad_pcb ---------- */\n"
          f"const BW = {W:g}, BH = {H:g};\n"
          f"const PARTS = {json.dumps(data['PARTS'], separators=(',', ':'))};\n"
          f"const PATHS = {json.dumps(data['PATHS'], separators=(',', ':'))};\n"
          f"const WIRES = {json.dumps(wires(b), separators=(',', ':'))};\n"
          "/* ---------- end generated ---------- */")
    t = open(HTML).read()
    t, n = re.subn(r"/\* ---------- generated by make_3d_data\.py.*?/\* ---------- end generated ---------- \*/", lambda m: js, t, count=1, flags=re.S)
    if n != 1: raise SystemExit("generated block not found in index.html")
    open(HTML, "w").write(t)
    print("PARTS", len(data["PARTS"]), "PATHS", {k: sum(len(l["p"]) for l in v["lines"]) for k, v in data["PATHS"].items()})

if __name__ == "__main__":
    board = pcbnew.LoadBoard(PCB)
    if "--no-tex" not in sys.argv: textures(board)
    write(board)
