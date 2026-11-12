"""DC current in the power copper of ks_tht.kicad_pcb (KiCad 7's python, numpy, PIL; no scipy needed).

The filled pours, tracks and pads of VIN, VOUT and GND are rasterised on a 0.25 mm grid and solved as a resistor
grid of 2 oz copper (70 um, 0.246 mOhm per square at 20 C). The 4 MOSFETs are 3.34 mOhm each (3.0 max + legs)
between their drain and source pads, so the solve also gives how the current shares between them.
Writes copper_tht.json and copper_<path>.png (current density maps) next to this file.

Run:  python3 copper_tht.py
"""
import json, math, os, sys
import numpy as np
import pcbnew
from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
PCB = os.path.join(HERE, "..", "ks_tht.kicad_pcb")
OX = OY = 100.0
G = 0.25                                  # mm per cell
W, H = 120.0, 98.0
NX, NY = int(round(W / G)), int(round(H / G))
R_SQ = 1.72e-8 / 70e-6                    # ohm per square, 2 oz copper at 20 C
R_FET = 3.34e-3                           # IRFB3206: 3.0 mOhm max + 0.34 mOhm legs and joints
G_CELL = 1.0 / R_SQ

def mm_xy(v): return (pcbnew.ToMM(v.x) - OX) / G, (pcbnew.ToMM(v.y) - OY) / G

def raster(b, net, layer):
    img = Image.new("L", (NX, NY), 0); d = ImageDraw.Draw(img)
    for z in b.Zones():
        if z.GetNetname() != net or z.GetIsRuleArea() or not z.IsOnLayer(layer): continue
        polys = z.GetFilledPolysList(layer)
        for i in range(polys.OutlineCount()):
            o = polys.Outline(i)
            pts = [mm_xy(o.CPoint(k)) for k in range(o.PointCount())]
            if len(pts) > 2: d.polygon(pts, fill=255)
    for t in b.GetTracks():
        if t.GetNetname() != net or not t.IsOnLayer(layer): continue
        w = max(1, int(round(pcbnew.ToMM(t.GetWidth()) / G)))
        if t.GetClass() == "PCB_VIA":
            x, y = mm_xy(t.GetPosition()); r = pcbnew.ToMM(t.GetWidth()) / G / 2
            d.ellipse([x - r, y - r, x + r, y + r], fill=255)
        else:
            a, c = mm_xy(t.GetStart()), mm_xy(t.GetEnd()); d.line([a, c], fill=255, width=w)
            for p in (a, c): d.ellipse([p[0] - w / 2, p[1] - w / 2, p[0] + w / 2, p[1] + w / 2], fill=255)
    for p in pads_of(b, net):
        x0, y0, x1, y1 = pad_box(p); d.rectangle([x0, y0, x1, y1], fill=255)
    return np.array(img) > 127

def pads_of(b, net):
    return [p for fp in b.GetFootprints() for p in fp.Pads() if p.GetNetname() == net and p.GetDrillSize().x > 0]

def pad_box(p):
    bb = p.GetBoundingBox()
    return ((pcbnew.ToMM(bb.GetLeft()) - OX) / G, (pcbnew.ToMM(bb.GetTop()) - OY) / G,
            (pcbnew.ToMM(bb.GetRight()) - OX) / G, (pcbnew.ToMM(bb.GetBottom()) - OY) / G)

def pad_cells(p, shape):
    x0, y0, x1, y1 = pad_box(p); m = np.zeros(shape, dtype=bool)
    m[..., max(int(math.floor(y0)), 0):int(math.ceil(y1)), max(int(math.floor(x0)), 0):int(math.ceil(x1))] = True
    return m

class Grid:
    """Copper of one net on one or two layers; layers joined at the net's plated holes."""
    def __init__(self, masks, links):
        self.m = np.stack(masks).astype(float)               # (L, NY, NX)
        self.L = len(masks)
        self.gx = self.m[:, :, 1:] * self.m[:, :, :-1] * G_CELL
        self.gy = self.m[:, 1:, :] * self.m[:, :-1, :] * G_CELL
        self.gz = (links * self.m[0] * self.m[1] * G_CELL * 50.0) if self.L == 2 else None
    def apply(self, v, free):
        v = v * free; out = np.zeros_like(v)
        dx = (v[:, :, 1:] - v[:, :, :-1]) * self.gx; out[:, :, 1:] += dx; out[:, :, :-1] -= dx
        dy = (v[:, 1:, :] - v[:, :-1, :]) * self.gy; out[:, 1:, :] += dy; out[:, :-1, :] -= dy
        if self.gz is not None:
            dz = (v[1] - v[0]) * self.gz; out[1] += dz; out[0] -= dz
        return out
    def diag(self):
        dg = np.zeros_like(self.m)
        dg[:, :, 1:] += self.gx; dg[:, :, :-1] += self.gx; dg[:, 1:, :] += self.gy; dg[:, :-1, :] += self.gy
        if self.gz is not None: dg[0] += self.gz; dg[1] += self.gz
        return dg
    def boost(self, k):
        """k: (L, NY, NX) conductance multiplier (a wire soldered on a bare strip); edges inside the strip only."""
        self.gx = self.gx * np.minimum(k[:, :, 1:], k[:, :, :-1]); self.gy = self.gy * np.minimum(k[:, 1:, :], k[:, :-1, :])
    def solve(self, fixed, inject, tol=1e-7, maxit=20000):
        """Potentials with V = 0 on `fixed` cells and `inject` amps entering at each cell (PCG, Jacobi)."""
        free = (1.0 - fixed.astype(float)) * (self.m > 0)
        Aop = lambda v: free * self.apply(v, free) + (1.0 - free) * v
        dg = self.diag() * free + (1.0 - free); Minv = 1.0 / np.maximum(dg, 1e-12)
        b = inject * free; x = np.zeros_like(b); r = b - Aop(x); z = Minv * r; p = z.copy(); rz = np.sum(r * z)
        b2 = math.sqrt(np.sum(b * b)) or 1.0
        for it in range(maxit):
            Ap = Aop(p); a = rz / np.sum(p * Ap); x += a * p; r -= a * Ap
            if math.sqrt(np.sum(r * r)) / b2 < tol: break
            z = Minv * r; rz2 = np.sum(r * z); p = z + (rz2 / rz) * p; rz = rz2
        return x * free
    def density(self, v):
        """Current per mm of copper width (A/mm), cell centred, max over layers."""
        jx = np.zeros_like(v); jy = np.zeros_like(v)
        ix = (v[:, :, 1:] - v[:, :, :-1]) * self.gx; jx[:, :, 1:] += np.abs(ix) / 2; jx[:, :, :-1] += np.abs(ix) / 2
        iy = (v[:, 1:, :] - v[:, :-1, :]) * self.gy; jy[:, 1:, :] += np.abs(iy) / 2; jy[:, :-1, :] += np.abs(iy) / 2
        return np.sqrt(jx ** 2 + jy ** 2) / G

def mean_v(v, cells): return float(np.sum(v * cells) / max(np.sum(cells), 1))

def heat_png(name, dens, mask, scale):
    d = np.max(dens, axis=0); m = np.max(mask, axis=0)
    t = np.clip(d / scale, 0, 1)
    rgb = np.zeros((NY, NX, 3), dtype=np.uint8) + 245
    rgb[m] = [205, 205, 210]
    hot = m & (t > 0.02)
    col = np.stack([255 * np.clip(2 * t, 0, 1), 255 * np.clip(2 - 2 * t, 0, 1) * np.clip(2 * t, 0, 1) ** 0.3, 40 * (1 - t)], -1).astype(np.uint8)
    rgb[hot] = col[hot]
    Image.fromarray(rgb).resize((NX * 2, NY * 2), Image.NEAREST).save(os.path.join(HERE, f"copper_{name}.png"))

WIRES = "--wires" in sys.argv
AWG12_MM2 = 3.31

def wire_boost(b):
    """Conductance multiplier where a 12 AWG bare wire lies on a bare strip (F.Mask -> F.Cu, B.Mask -> B.Cu)."""
    k = np.ones((2, NY, NX))
    for d in b.GetDrawings():
        if d.GetLayer() not in (pcbnew.F_Mask, pcbnew.B_Mask): continue
        bb = d.GetBoundingBox()
        x0, y0 = (pcbnew.ToMM(bb.GetLeft()) - OX) / G, (pcbnew.ToMM(bb.GetTop()) - OY) / G
        x1, y1 = (pcbnew.ToMM(bb.GetRight()) - OX) / G, (pcbnew.ToMM(bb.GetBottom()) - OY) / G
        width_mm = min(x1 - x0, y1 - y0) * G
        li = 0 if d.GetLayer() == pcbnew.F_Mask else 1
        k[li, int(y0):int(math.ceil(y1)), int(x0):int(math.ceil(x1))] = 1 + AWG12_MM2 / (width_mm * 0.070)
    return k

def main():
    b = pcbnew.LoadBoard(PCB)
    pcbnew.ZONE_FILLER(b).Fill(b.Zones())
    F, B = pcbnew.F_Cu, pcbnew.B_Cu
    fp = lambda r: b.FindFootprintByReference(r)
    pad = lambda r, n: [p for p in fp(r).Pads() if p.GetNumber() == n][0]
    out = {"grid_mm": G, "copper": "2 oz (70 um), 20 C", "r_fet_mohm": R_FET * 1e3, "wires_12awg_on_strips": WIRES}
    # VIN (F.Cu pour + B.Cu bits of the net) and VOUT: unit current at each MOSFET pad, one at a time
    vin = Grid([raster(b, "VIN", F), raster(b, "VIN", B)], np.zeros((NY, NX)))
    vout = Grid([raster(b, "VOUT", F), raster(b, "VOUT", B)], np.zeros((NY, NX)))
    if WIRES:
        kb = wire_boost(b); vin.boost(kb); vout.boost(kb)
    for gr, net in ((vin, "VIN"), (vout, "VOUT")):            # plated holes join the layers
        links = np.zeros((NY, NX))
        for p in pads_of(b, net): links = np.maximum(links, pad_cells(p, (NY, NX)).astype(float))
        gr.gz = links * gr.m[0] * gr.m[1] * G_CELL * 50.0
    j1p = pad_cells(pad("J1", "2"), (2, NY, NX)); j2p = pad_cells(pad("J2", "2"), (2, NY, NX))
    drains = [pad_cells(pad(f"Q{k}", "2"), (2, NY, NX)) for k in range(1, 5)]
    sources = [pad_cells(pad(f"Q{k}", "3"), (2, NY, NX)) for k in range(1, 5)]
    Rin = np.zeros((4, 4)); Rout = np.zeros((4, 4)); Vin_u, Vout_u = [], []
    for j in range(4):
        inj = -(drains[j] * vin.m) / max(np.sum(drains[j] * vin.m), 1)         # 1 A leaves the VIN copper at drain j
        v = vin.solve(j1p, inj); Vin_u.append(v)
        for k in range(4): Rin[k, j] = -mean_v(v, drains[k] * vin.m)
        inj = sources[j] * vout.m / max(np.sum(sources[j] * vout.m), 1)       # 1 A enters the VOUT copper at source j
        v = vout.solve(j2p, inj); Vout_u.append(v)
        for k in range(4): Rout[k, j] = mean_v(v, sources[k] * vout.m)
    # share: Rin I + R_FET I + Rout I = V (same for all four), sum I = 1
    A = np.zeros((5, 5)); A[:4, :4] = Rin + Rout + np.eye(4) * R_FET; A[:4, 4] = -1; A[4, :4] = 1
    sol = np.linalg.solve(A, np.r_[np.zeros(4), 1.0]); share = sol[:4]; r_total = sol[4]
    out["fet_share"] = [round(float(s), 4) for s in share]
    out["r_total_mohm"] = r_total * 1e3
    out["r_vin_copper_mohm"] = float(np.dot(share, Rin @ share) * 1e3)
    out["r_vout_copper_mohm"] = float(np.dot(share, Rout @ share) * 1e3)
    out["r_fets_parallel_mohm"] = float(np.sum(share ** 2) * R_FET * 1e3)
    # GND return: J2 - in, J1 - out, both layers joined at every plated GND hole and via
    gl = np.zeros((NY, NX))
    for p in pads_of(b, "GND"): gl = np.maximum(gl, pad_cells(p, (NY, NX)).astype(float))
    for t in b.GetTracks():
        if t.GetClass() == "PCB_VIA" and t.GetNetname() == "GND":
            x, y = mm_xy(t.GetPosition()); gl[max(int(y) - 1, 0):int(y) + 2, max(int(x) - 1, 0):int(x) + 2] = 1
    gnd = Grid([raster(b, "GND", F), raster(b, "GND", B)], gl)
    if WIRES: gnd.boost(kb)
    j1m = pad_cells(pad("J1", "1"), (2, NY, NX)); j2m = pad_cells(pad("J2", "1"), (2, NY, NX))
    vg = gnd.solve(j1m, j2m * gnd.m / max(np.sum(j2m * gnd.m), 1))
    out["r_gnd_copper_mohm"] = mean_v(vg, j2m * gnd.m) * 1e3
    # full-current pictures and numbers at 30 A and 60 A
    v_in = sum(s * v for s, v in zip(share, Vin_u)); v_out = sum(s * v for s, v in zip(share, Vout_u))
    for name, gr, v in (("vin", vin, v_in), ("vout", vout, v_out), ("gnd", gnd, vg)):
        dens = gr.density(v)                                     # A/mm per amp of total current
        k = np.unravel_index(np.argmax(dens), dens.shape)
        out[f"{name}_peak_A_per_mm_per_A"] = float(dens[k]); out[f"{name}_peak_at_mm"] = [round(k[2] * G, 2), round(k[1] * G, 2), "F.Cu" if k[0] == 0 else "B.Cu"]
        heat_png(name + ("_wires" if WIRES else ""), dens * 60.0, gr.m > 0, 6.0)   # colour scale: 0 .. 6 A/mm at 60 A
    for I in (30.0, 60.0):
        tag = f"{int(I)}A"
        rc = out["r_vin_copper_mohm"] + out["r_vout_copper_mohm"] + out["r_gnd_copper_mohm"]
        out[f"copper_drop_{tag}_mV"] = rc * I
        out[f"copper_loss_{tag}_W"] = rc * 1e-3 * I * I
        out[f"fet_loss_{tag}_W"] = out["r_fets_parallel_mohm"] * 1e-3 * I * I
        out[f"fet_max_current_{tag}_A"] = float(max(share) * I)
        for name in ("vin", "vout", "gnd"):
            out[f"{name}_loss_{tag}_W"] = out[f"r_{name}_copper_mohm"] * 1e-3 * I * I
            out[f"{name}_peak_{tag}_A_per_mm"] = out[f"{name}_peak_A_per_mm_per_A"] * I
    json.dump(out, open(os.path.join(HERE, "copper_tht_wires.json" if WIRES else "copper_tht.json"), "w"), indent=1)
    for k, v in out.items(): print(k, v if not isinstance(v, float) else round(v, 4))

if __name__ == "__main__":
    main()
