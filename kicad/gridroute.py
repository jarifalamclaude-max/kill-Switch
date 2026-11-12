"""Small two-layer grid router (A*) for KiCad 7 boards, used by route_v4.py.

How it works
- The board is a grid (default 0.25 mm) on F.Cu and B.Cu.
- Every piece of copper (pads, tracks, vias), board edge, NPTH hole and keepout is "inflated" by the
  clearance it needs. A cell is usable by a net only if no other net's inflated copper covers it.
- Each net is connected pad by pad (nearest first) with A*. Steps on B.Cu and vias cost extra, so the
  ground planes on B.Cu stay mostly whole.
- Paths are string-pulled into long straight segments, then written to the board.
- Nets that fail are moved to the front of the order and everything is re-routed (rip-up and retry).
"""
import heapq, math
import numpy as np
import pcbnew

NM = 1e6
LAYERS = (pcbnew.F_Cu, pcbnew.B_Cu)


class GridRouter:
    def __init__(self, board, ox, oy, w, h, grid=0.25, clearance=0.25, track_w=0.35, via_d=0.8, via_drill=0.4,
                 edge_clear=0.4, hole_clear=0.25, margin=0.06, bcu_cost=4.0, via_cost=30.0, keepouts=()):
        self.b, self.ox, self.oy, self.w, self.h, self.g = board, ox, oy, w, h, grid
        self.cl, self.tw, self.vd, self.vdrill = clearance, track_w, via_d, via_drill
        self.edge_cl, self.hole_cl, self.margin = edge_clear, hole_clear, margin
        self.layer_cost = (1.0, bcu_cost); self.via_cost = via_cost
        self.nx, self.ny = int(round(w / grid)) + 1, int(round(h / grid)) + 1
        self.X = np.arange(self.nx) * grid; self.Y = np.arange(self.ny) * grid
        self.r_t = clearance + track_w / 2 + margin          # copper edge -> allowed track centre
        self.r_v = clearance + via_d / 2 + margin            # copper edge -> allowed via centre
        self.r_s = self.r_t + 0.12                           # strict: any-angle segments may pass 0.18 mm off a cell centre
        self.keepouts = list(keepouts)
        self.reset()

    # ------------------------------------------------------------------ occupancy
    def reset(self):
        self.occ_t = np.zeros((2, self.ny, self.nx), dtype=np.int32)    # 0 free, >0 net, -1 blocked
        self.occ_v = np.zeros((2, self.ny, self.nx), dtype=np.int32)
        self.occ_s = np.zeros((2, self.ny, self.nx), dtype=np.int32)
        self.own = {}                                                   # net -> bool array (2, ny, nx) of its copper
        g = self.g
        # board edge
        for occ, r in ((self.occ_t, self.edge_cl + self.tw / 2 + self.margin), (self.occ_v, self.edge_cl + self.vd / 2 + self.margin),
                       (self.occ_s, self.edge_cl + self.tw / 2 + self.margin + 0.12)):
            k = int(math.ceil(r / g))
            occ[:, :k, :] = -1; occ[:, -k:, :] = -1; occ[:, :, :k] = -1; occ[:, :, -k:] = -1
        for (x0, y0, x1, y1) in self.keepouts:
            for occ, r in ((self.occ_t, self.tw / 2 + self.margin), (self.occ_v, self.vd / 2 + self.margin), (self.occ_s, self.tw / 2 + self.margin + 0.12)):
                ix0, ix1 = self._ix(x0 - r), self._ix(x1 + r) + 1; iy0, iy1 = self._iy(y0 - r), self._iy(y1 + r) + 1
                occ[:, max(iy0, 0):iy1, max(ix0, 0):ix1] = -1
        for fp in self.b.GetFootprints():
            for p in fp.Pads(): self._add_pad(p)
        for t in self.b.GetTracks(): self._add_track(t)

    def _ix(self, x): return int(round(x / self.g))
    def _iy(self, y): return int(round(y / self.g))
    def _mm(self, v): return v / NM

    def _region(self, x0, y0, x1, y1):
        ix0, ix1 = max(self._ix(x0) - 1, 0), min(self._ix(x1) + 2, self.nx)
        iy0, iy1 = max(self._iy(y0) - 1, 0), min(self._iy(y1) + 2, self.ny)
        return ix0, ix1, iy0, iy1

    def _mark(self, layers, dist_fn, bbox, net):
        """dist_fn(XX, YY) -> distance from the copper edge (<= 0 inside). Marks own copper and inflated zones."""
        x0, y0, x1, y1 = bbox; r = self.r_v
        ix0, ix1, iy0, iy1 = self._region(x0 - r, y0 - r, x1 + r, y1 + r)
        if ix0 >= ix1 or iy0 >= iy1: return
        XX, YY = np.meshgrid(self.X[ix0:ix1], self.Y[iy0:iy1])
        d = dist_fn(XX, YY)
        for li in layers:
            for occ, rr in ((self.occ_t, self.r_t), (self.occ_v, self.r_v), (self.occ_s, self.r_s)):
                sub = occ[li, iy0:iy1, ix0:ix1]; m = d <= rr
                if net <= 0:
                    sub[m] = -1
                else:
                    free = m & (sub == 0); clash = m & (sub != 0) & (sub != net)
                    sub[free] = net; sub[clash] = -1
            if net > 0:
                own = self.own.setdefault(net, np.zeros((2, self.ny, self.nx), dtype=bool))
                own[li, iy0:iy1, ix0:ix1] |= (d <= 0)

    def _add_pad(self, p):
        pos = p.GetPosition(); cx, cy = self._mm(pos.x) - self.ox, self._mm(pos.y) - self.oy
        net = p.GetNetCode()
        if p.GetAttribute() == pcbnew.PAD_ATTRIB_NPTH:
            r = self._mm(p.GetDrillSize().x) / 2
            # a hole needs hole clearance, not copper clearance: shift the radius so _mark's inflation matches
            rr = r + self.hole_cl - self.cl
            self._mark((0, 1), lambda X, Y: np.hypot(X - cx, Y - cy) - rr, (cx - r, cy - r, cx + r, cy + r), -1)
            return
        sx, sy = self._mm(p.GetSize().x) / 2, self._mm(p.GetSize().y) / 2
        ang = math.radians(p.GetOrientation().AsDegrees())
        shape = p.GetShape()
        if shape == pcbnew.PAD_SHAPE_CIRCLE:
            cr = sx; hx = hy = sx
        elif shape == pcbnew.PAD_SHAPE_OVAL:
            cr = min(sx, sy); hx, hy = sx, sy
        elif shape == pcbnew.PAD_SHAPE_ROUNDRECT:
            cr = self._mm(p.GetRoundRectCornerRadius()); hx, hy = sx, sy
        else:
            cr = 0.0; hx, hy = sx, sy
        ca, sa = math.cos(ang), math.sin(ang)
        def dist(X, Y, cx=cx, cy=cy, hx=hx, hy=hy, cr=cr, ca=ca, sa=sa):
            lx = (X - cx) * ca - (Y - cy) * sa; ly = (X - cx) * sa + (Y - cy) * ca
            qx = np.abs(lx) - (hx - cr); qy = np.abs(ly) - (hy - cr)
            out = np.hypot(np.maximum(qx, 0), np.maximum(qy, 0)) + np.minimum(np.maximum(qx, qy), 0)
            return out - cr
        R = math.hypot(hx, hy)
        layers = [i for i, L in enumerate(LAYERS) if p.IsOnLayer(L)]
        self._mark(layers, dist, (cx - R, cy - R, cx + R, cy + R), net if net > 0 else -1)

    def _seg_dist(self, X, Y, x0, y0, x1, y1, hw):
        dx, dy = x1 - x0, y1 - y0; L2 = dx * dx + dy * dy
        if L2 == 0: return np.hypot(X - x0, Y - y0) - hw
        t = np.clip(((X - x0) * dx + (Y - y0) * dy) / L2, 0, 1)
        return np.hypot(X - (x0 + t * dx), Y - (y0 + t * dy)) - hw

    def _add_track(self, t):
        net = t.GetNetCode()
        if t.GetClass() == "PCB_VIA":
            pos = t.GetPosition(); cx, cy = self._mm(pos.x) - self.ox, self._mm(pos.y) - self.oy; r = self._mm(t.GetWidth()) / 2
            self._mark((0, 1), lambda X, Y: np.hypot(X - cx, Y - cy) - r, (cx - r, cy - r, cx + r, cy + r), net)
            return
        s, e = t.GetStart(), t.GetEnd()
        x0, y0, x1, y1 = self._mm(s.x) - self.ox, self._mm(s.y) - self.oy, self._mm(e.x) - self.ox, self._mm(e.y) - self.oy
        hw = self._mm(t.GetWidth()) / 2; li = 0 if t.GetLayer() == pcbnew.F_Cu else 1
        self._mark((li,), lambda X, Y: self._seg_dist(X, Y, x0, y0, x1, y1, hw),
                   (min(x0, x1) - hw, min(y0, y1) - hw, max(x0, x1) + hw, max(y0, y1) + hw), net)

    # ------------------------------------------------------------------ routing
    def _passable(self, net, li, iy, ix):
        v = self.occ_t[li, iy, ix]; return v == 0 or v == net

    def _via_ok(self, net, iy, ix):
        a, b = self.occ_v[0, iy, ix], self.occ_v[1, iy, ix]
        return (a == 0 or a == net) and (b == 0 or b == net)

    def astar(self, net, src, dst, max_expand=900000):
        """src, dst: bool arrays (2, ny, nx). Returns list of (li, iy, ix) from a src cell to a dst cell."""
        tl, ty, tx = np.nonzero(dst); tcx, tcy = tx.mean(), ty.mean()
        trad = max(np.hypot(tx - tcx, ty - tcy).max(), 0)
        def h(iy, ix): return max(math.hypot(ix - tcx, iy - tcy) - trad, 0.0)
        g = {}; came = {}; heap = []
        sl, sy, sx = np.nonzero(src)
        for l, y, x in zip(sl.tolist(), sy.tolist(), sx.tolist()):
            if not self._passable(net, l, y, x): continue
            k = (l, y, x); g[k] = 0.0; heapq.heappush(heap, (h(y, x), 0.0, k))
        nb = [(-1, 0, 1.0), (1, 0, 1.0), (0, -1, 1.0), (0, 1, 1.0), (-1, -1, 1.4142), (-1, 1, 1.4142), (1, -1, 1.4142), (1, 1, 1.4142)]
        exp = 0
        while heap:
            f, gc, k = heapq.heappop(heap)
            if gc > g.get(k, 1e18): continue
            l, y, x = k
            if dst[l, y, x]:
                path = [k]
                while path[-1] in came: path.append(came[path[-1]])
                return path[::-1]
            exp += 1
            if exp > max_expand: return None
            lc = self.layer_cost[l]
            for dy, dx, c in nb:
                yy, xx = y + dy, x + dx
                if not (0 <= yy < self.ny and 0 <= xx < self.nx): continue
                if not self._passable(net, l, yy, xx): continue
                if dy and dx and not (self._passable(net, l, y, xx) and self._passable(net, l, yy, x)): continue
                nk = (l, yy, xx); ng = gc + c * lc
                if ng < g.get(nk, 1e18):
                    g[nk] = ng; came[nk] = k; heapq.heappush(heap, (ng + h(yy, xx), ng, nk))
            ol = 1 - l; nk = (ol, y, x)
            if self._passable(net, ol, y, x) and self._via_ok(net, y, x):
                ng = gc + self.via_cost
                if ng < g.get(nk, 1e18):
                    g[nk] = ng; came[nk] = k; heapq.heappush(heap, (ng + h(y, x), ng, nk))
        return None

    def _clear_line(self, net, li, a, b):
        (y0, x0), (y1, x1) = a, b
        dy, dx = y1 - y0, x1 - x0
        if dy == 0 or dx == 0 or abs(dy) == abs(dx):          # 0/45/90 degrees: the line runs through cell centres
            n = max(abs(dy), abs(dx))
            for i in range(n + 1):
                y = y0 + (dy // n if n else 0) * i if dy else y0; x = x0 + (dx // n if n else 0) * i if dx else x0
                if dy and n: y = y0 + (1 if dy > 0 else -1) * i
                if dx and n: x = x0 + (1 if dx > 0 else -1) * i
                if not self._passable(net, li, y, x): return False
            return True
        n = int(max(abs(dy), abs(dx)) * 3) + 1
        for i in range(n + 1):
            t = i / n; fy, fx = y0 + dy * t, x0 + dx * t
            for y in {math.floor(fy), math.ceil(fy)}:
                for x in {math.floor(fx), math.ceil(fx)}:
                    v = self.occ_s[li, y, x]
                    if not (v == 0 or v == net): return False
        return True

    def simplify(self, net, path):
        """Split by layer, string-pull each run. Returns [(layer, [(iy, ix), ...]), ...] and via cells."""
        runs, vias = [], []
        cur = [path[0]]
        for k in path[1:]:
            if k[0] != cur[-1][0]:
                runs.append(cur); vias.append((k[1], k[2])); cur = [k]
            else:
                cur.append(k)
        runs.append(cur)
        out = []
        for run in runs:
            li = run[0][0]; pts = [(k[1], k[2]) for k in run]; res = [pts[0]]; i = 0
            while i < len(pts) - 1:
                j = len(pts) - 1
                while j > i + 1 and not self._clear_line(net, li, pts[i], pts[j]): j -= 1
                res.append(pts[j]); i = j
            out.append((li, res))
        return out, vias

    def commit(self, net, runs, vias):
        n = self.b.FindNet(self.b.GetNetInfo().GetNetItem(net).GetNetname())
        added = []
        for li, pts in runs:
            for (y0, x0), (y1, x1) in zip(pts, pts[1:]):
                if (y0, x0) == (y1, x1): continue
                t = pcbnew.PCB_TRACK(self.b)
                t.SetStart(pcbnew.VECTOR2I(int((x0 * self.g + self.ox) * NM), int((y0 * self.g + self.oy) * NM)))
                t.SetEnd(pcbnew.VECTOR2I(int((x1 * self.g + self.ox) * NM), int((y1 * self.g + self.oy) * NM)))
                t.SetWidth(int(self.tw * NM)); t.SetLayer(LAYERS[li]); t.SetNet(n); self.b.Add(t); added.append(t)
        for (y, x) in vias:
            v = pcbnew.PCB_VIA(self.b); v.SetPosition(pcbnew.VECTOR2I(int((x * self.g + self.ox) * NM), int((y * self.g + self.oy) * NM)))
            v.SetWidth(int(self.vd * NM)); v.SetDrill(int(self.vdrill * NM)); v.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
            v.SetViaType(pcbnew.VIATYPE_THROUGH); v.SetNet(n); self.b.Add(v); added.append(v)
        for t in added: self._add_track(t)
        return added

    def pad_cells(self, net):
        """Group the net's own copper cells per pad (pads of this net), as bool arrays."""
        groups = []
        for fp in self.b.GetFootprints():
            for p in fp.Pads():
                if p.GetNetCode() != net: continue
                pos = p.GetPosition(); cx, cy = self._mm(pos.x) - self.ox, self._mm(pos.y) - self.oy
                m = np.zeros((2, self.ny, self.nx), dtype=bool)
                rx, ry = self._mm(p.GetBoundingBox().GetWidth()) / 2, self._mm(p.GetBoundingBox().GetHeight()) / 2
                ix0, ix1, iy0, iy1 = self._region(cx - rx, cy - ry, cx + rx, cy + ry)
                m[:, iy0:iy1, ix0:ix1] = self.own[net][:, iy0:iy1, ix0:ix1]
                if m.any(): groups.append((fp.GetReference() + "." + p.GetNumber(), (cx, cy), m))
        return groups

    def route_net(self, net):
        groups = self.pad_cells(net)
        if len(groups) < 2: return True, []
        own = self.own[net]
        # connected set starts with the largest copper island of this net (e.g. a hand-routed trunk)
        connected = np.zeros_like(own)
        lab = self._islands(own)
        best = max(set(lab[lab > 0].tolist()), key=lambda v: int((lab == v).sum()))
        connected |= (lab == best)
        # a pad's target is its whole copper island, so a hand-routed escape stub counts as part of the pad
        groups = [(g[0], g[1], g[2] | np.isin(lab, [v for v in set(lab[g[2] & (lab > 0)].tolist())])) for g in groups]
        todo = [gname for gname in groups if not (gname[2] & connected).any()]
        added = []
        while todo:
            cl, cy, cx = np.nonzero(connected)
            def gap(gr):
                (px, py) = gr[1]; return np.min(np.hypot(cx * self.g - px, cy * self.g - py))
            todo.sort(key=gap); target = todo.pop(0)
            path = self.astar(net, connected, target[2])
            if path is None: return False, added
            runs, vias = self.simplify(net, path)
            added += self.commit(net, runs, vias)
            connected |= target[2]
            for li, pts in runs:
                for (y, x) in pts: connected[li, y, x] = True
            lab = self._islands(self.own[net]); ids = set(lab[connected & (lab > 0)].tolist())
            for v in ids: connected |= (lab == v)
            todo = [gr for gr in todo if not (gr[2] & connected).any()]
        return True, added

    def _islands(self, own):
        """Connected components of a net's copper over both layers (THT pads / vias join the layers)."""
        lab = np.zeros(own.shape, dtype=np.int32); cur = 0
        both = own[0] & own[1]
        for start in zip(*np.nonzero(own)):
            if lab[start]: continue
            cur += 1; stack = [start]; lab[start] = cur
            while stack:
                l, y, x = stack.pop()
                nbrs = [(l, y - 1, x), (l, y + 1, x), (l, y, x - 1), (l, y, x + 1)]
                if both[y, x]: nbrs.append((1 - l, y, x))
                for k in nbrs:
                    l2, y2, x2 = k
                    if 0 <= y2 < self.ny and 0 <= x2 < self.nx and own[k] and not lab[k]:
                        lab[k] = cur; stack.append(k)
        return lab
