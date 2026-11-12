"""Magnetic kill switch (KiCad 7): power board (100 A continuous / 150 A burst, 3S-6S LiPo) and sensor board.

Power board  ks_power.kicad_pcb  118 x 120 mm, 2 layers, 2 oz copper
  - 8 x IPT007N06N (TOLL) in parallel as one high-side switch, driven by an LM5060 (charge pump, VDS short
    detection, UVLO, OVP). Battery + comes in on a top copper band, thruster + leaves on the band below.
  - Pre-charge path (P-MOSFET, PTC, 2 x 22 Ohm) charges the ESC capacitors first; an LM393 aborts it within
    about 10 ms if the thruster bus is shorted and only lets the main MOSFETs close once VOUT > 0.5 VIN.
  - Arm chain, energise to arm: 5 V -> reed (closed by the magnet) -> P-MOSFET switched by the Hall sensor -> ARM.
    Loss of either sensor, the cable, the 5 V or the magnet pulls ARM low and kills.
  - Second, independent kill path: an optocoupler shorts the MOSFET gates to source whenever ARM is low.
Sensors are bought modules that plug in: a 3-pin Hall module (KY-003 style, A3144, output low with the magnet)
  on J4 and a 2-wire reed door contact (MC-38 style, closed with the magnet) on J6. Both sit on the inside of the
  hull wall behind the magnet; both must see the magnet for the thrusters to get power.

Run with KiCad 7's python from this folder:  python3 build_ks.py   (then python3 route_ks.py)
"""
import os
import pcbnew

HERE = os.path.dirname(os.path.abspath(__file__))
FP = "/usr/share/kicad/footprints/"
OX, OY = 100.0, 100.0
mm = pcbnew.FromMM

class Board:
    def __init__(self, path):
        self.path = path; self.b = pcbnew.BOARD(); self.nets = {}; self.parts = []
    def P(self, x, y): return pcbnew.VECTOR2I(mm(OX + x), mm(OY + y))
    def net(self, name):
        if name not in self.nets:
            n = pcbnew.NETINFO_ITEM(self.b, name); self.b.Add(n); self.nets[name] = n
        return self.nets[name]
    def place(self, ref, lib, name, x, y, rot, value, padnets, back=False, ref_at=None, ref_size=0.8, hide_ref=False):
        fp = (reed_footprint(self.b) if name is None else nettie_footprint(self.b)) if lib is None else pcbnew.FootprintLoad(FP + lib + ".pretty", name)
        if lib is not None: fp.SetFPID(pcbnew.LIB_ID(lib, name))
        fp.SetReference(ref); fp.SetValue(value); self.b.Add(fp)
        fp.SetPosition(self.P(x, y)); fp.SetOrientationDegrees(rot)
        if back: fp.Flip(self.P(x, y), False)
        for pad in fp.Pads():
            n = padnets.get(pad.GetNumber())
            if n: pad.SetNet(self.net(n))
        r = fp.Reference(); r.SetTextSize(pcbnew.VECTOR2I(mm(ref_size), mm(ref_size))); r.SetTextThickness(mm(ref_size * 0.15))
        if ref_at: r.SetPosition(self.P(*ref_at[:2])); r.SetTextAngleDegrees(ref_at[2] if len(ref_at) > 2 else 0)
        r.SetVisible(not hide_ref)
        fp.Value().SetVisible(False)
        self.parts.append((ref, value, name))
        return fp
    def text(self, t, x, y, size=1.0, rot=0, layer=pcbnew.F_SilkS, bold=False):
        tx = pcbnew.PCB_TEXT(self.b); tx.SetText(t); tx.SetPosition(self.P(x, y)); tx.SetLayer(layer)
        tx.SetTextSize(pcbnew.VECTOR2I(mm(size), mm(size))); tx.SetTextThickness(mm(size * (0.2 if bold else 0.15)))
        tx.SetTextAngleDegrees(rot)
        if layer == pcbnew.B_SilkS: tx.SetMirrored(True)
        self.b.Add(tx)
    def line(self, x0, y0, x1, y1, layer=pcbnew.F_SilkS, w=0.15):
        s = pcbnew.PCB_SHAPE(self.b); s.SetShape(pcbnew.SHAPE_T_SEGMENT); s.SetLayer(layer)
        s.SetStart(self.P(x0, y0)); s.SetEnd(self.P(x1, y1)); s.SetWidth(mm(w)); self.b.Add(s)
    def rect(self, x0, y0, x1, y1, layer=pcbnew.F_SilkS, w=0.15):
        for a, b_, c, d in ((x0, y0, x1, y0), (x1, y0, x1, y1), (x1, y1, x0, y1), (x0, y1, x0, y0)): self.line(a, b_, c, d, layer, w)
    def circle(self, cx, cy, r, layer, w=0.1):
        s = pcbnew.PCB_SHAPE(self.b); s.SetShape(pcbnew.SHAPE_T_CIRCLE); s.SetLayer(layer)
        s.SetCenter(self.P(cx, cy)); s.SetEnd(self.P(cx + r, cy)); s.SetWidth(mm(w)); self.b.Add(s)
    def rules(self, clearance=0.2, track=0.3):
        ds = self.b.GetDesignSettings()
        ds.m_MinClearance = mm(0.2); ds.m_TrackMinWidth = mm(0.2); ds.m_ViasMinSize = mm(0.6)
        ds.m_MinThroughDrill = mm(0.3); ds.m_CopperEdgeClearance = mm(0.4); ds.m_HoleClearance = mm(0.25)
        nc = ds.m_NetSettings.m_DefaultNetClass
        nc.SetClearance(mm(clearance)); nc.SetTrackWidth(mm(track)); nc.SetViaDiameter(mm(0.8)); nc.SetViaDrill(mm(0.4))
    def save(self, bom):
        self.b.SetFileName(self.path); pcbnew.SaveBoard(self.path, self.b)
        with open(bom, "w") as f:
            f.write("ref,value,footprint\n")
            key = lambda r: ("".join(c for c in r[0] if not c.isdigit()), int("".join(c for c in r[0] if c.isdigit()) or 0))
            for ref, val, name in sorted(self.parts, key=key):
                if not ref.startswith("H"): f.write(f'{ref},"{val}",{name}\n')
        print(os.path.basename(self.path), len(list(self.b.GetFootprints())), "footprints,", len(self.nets), "nets")

def nettie_footprint(board):
    """Two 0.6 mm pads joined by a 0.3 mm copper bar: a Kelvin tap that DRC accepts as a deliberate net join."""
    fp = pcbnew.FOOTPRINT(board); fp.SetFPID(pcbnew.LIB_ID("ks", "NetTie_2_SMD_0.6mm")); fp.AddNetTiePadGroup("1, 2")
    for i, x in enumerate((-0.6, 0.6)):
        p = pcbnew.PAD(fp); p.SetNumber(str(i + 1)); p.SetAttribute(pcbnew.PAD_ATTRIB_SMD); p.SetShape(pcbnew.PAD_SHAPE_RECT)
        p.SetSize(pcbnew.VECTOR2I(mm(0.6), mm(0.6))); ls = pcbnew.LSET(); ls.AddLayer(pcbnew.F_Cu); p.SetLayerSet(ls)
        p.SetPos0(pcbnew.VECTOR2I(mm(x), 0)); p.SetPosition(pcbnew.VECTOR2I(mm(x), 0)); fp.Add(p)
    for layer, (x0, y0, x1, y1), fill in ((pcbnew.F_Cu, (-0.6, -0.15, 0.6, 0.15), True), (pcbnew.F_CrtYd, (-1.15, -0.55, 1.15, 0.55), False)):
        s = pcbnew.FP_SHAPE(fp); s.SetShape(pcbnew.SHAPE_T_RECT); s.SetLayer(layer); s.SetFilled(fill)
        s.SetStart0(pcbnew.VECTOR2I(mm(x0), mm(y0))); s.SetEnd0(pcbnew.VECTOR2I(mm(x1), mm(y1))); s.SetWidth(mm(0.05)); fp.Add(s)
    return fp

def auto_refs(B, edge):
    """Put every visible reference where it overlaps no pad, no other text and no footprint outline; ~0.8 mm text."""
    b = B.b; placed = []
    def boxes_of_fp(fp, inflate):
        out = []
        for p in fp.Pads():
            bb = p.GetBoundingBox(); out.append((pcbnew.ToMM(bb.GetLeft()) - inflate, pcbnew.ToMM(bb.GetTop()) - inflate, pcbnew.ToMM(bb.GetRight()) + inflate, pcbnew.ToMM(bb.GetBottom()) + inflate))
        for g in fp.GraphicalItems():
            if g.GetLayer() in (pcbnew.F_SilkS,) and type(g).__name__ in ("FP_SHAPE", "FP_TEXT"):
                bb = g.GetBoundingBox(); out.append((pcbnew.ToMM(bb.GetLeft()) - 0.1, pcbnew.ToMM(bb.GetTop()) - 0.1, pcbnew.ToMM(bb.GetRight()) + 0.1, pcbnew.ToMM(bb.GetBottom()) + 0.1))
        return out
    obstacles = []
    for fp in b.GetFootprints(): obstacles += boxes_of_fp(fp, 0.2)
    for d in b.GetDrawings():
        if d.GetLayer() == pcbnew.F_SilkS:
            bb = d.GetBoundingBox(); placed.append((pcbnew.ToMM(bb.GetLeft()), pcbnew.ToMM(bb.GetTop()), pcbnew.ToMM(bb.GetRight()), pcbnew.ToMM(bb.GetBottom())))
    def hit(bx, lst): return any(bx[0] < o[2] and o[0] < bx[2] and bx[1] < o[3] and o[1] < bx[3] for o in lst)
    x0e, y0e, x1e, y1e = [OX + v for v in edge]
    for fp in sorted(b.GetFootprints(), key=lambda f: f.GetReference()):
        r = fp.Reference()
        if not r.IsVisible() or fp.GetLayer() != pcbnew.F_Cu: continue
        cb = fp.GetBoundingBox(False, False); cx0, cy0, cx1, cy1 = pcbnew.ToMM(cb.GetLeft()), pcbnew.ToMM(cb.GetTop()), pcbnew.ToMM(cb.GetRight()), pcbnew.ToMM(cb.GetBottom())
        mx, my = (cx0 + cx1) / 2, (cy0 + cy1) / 2
        r.SetTextSize(pcbnew.VECTOR2I(mm(0.8), mm(0.8))); r.SetTextThickness(mm(0.13))
        cands = []
        for gap in (0.65, 1.2, 2.0):
            cands += [(mx, cy0 - gap, 0), (mx, cy1 + gap, 0), (cx0 - gap, my, 90), (cx1 + gap, my, 90)]
        cands.insert(0, (r.GetPosition().x / 1e6, r.GetPosition().y / 1e6, r.GetTextAngle().AsDegrees()))
        best = None
        for (x, y, a) in cands:
            r.SetPosition(pcbnew.VECTOR2I(mm(x), mm(y))); r.SetTextAngleDegrees(a)
            bb = r.GetBoundingBox(); bx = (pcbnew.ToMM(bb.GetLeft()), pcbnew.ToMM(bb.GetTop()), pcbnew.ToMM(bb.GetRight()), pcbnew.ToMM(bb.GetBottom()))
            if bx[0] < x0e + 0.5 or bx[1] < y0e + 0.5 or bx[2] > x1e - 0.5 or bx[3] > y1e - 0.5: continue
            if hit(bx, obstacles) or hit(bx, placed): continue
            best = (x, y, a, bx); break
        if best is None:
            r.SetVisible(False); print("  reference hidden (no room):", fp.GetReference()); continue
        x, y, a, bx = best; r.SetPosition(pcbnew.VECTOR2I(mm(x), mm(y))); r.SetTextAngleDegrees(a); placed.append(bx)

def reed_footprint(board):
    """Glass reed switch, about 14 x 2.5 mm body, leads bent down 17.78 mm apart."""
    fp = pcbnew.FOOTPRINT(board); fp.SetFPID(pcbnew.LIB_ID("ks", "Reed_Glass_L14mm_P17.78mm"))
    for i, x in enumerate((0.0, 17.78)):
        p = pcbnew.PAD(fp); p.SetNumber(str(i + 1)); p.SetAttribute(pcbnew.PAD_ATTRIB_PTH)
        p.SetShape(pcbnew.PAD_SHAPE_RECT if i == 0 else pcbnew.PAD_SHAPE_CIRCLE)
        p.SetSize(pcbnew.VECTOR2I(mm(1.7), mm(1.7))); p.SetDrillSize(pcbnew.VECTOR2I(mm(0.9), mm(0.9)))
        p.SetLayerSet(pcbnew.PAD.PTHMask()); p.SetPos0(pcbnew.VECTOR2I(mm(x), 0)); p.SetPosition(pcbnew.VECTOR2I(mm(x), 0)); fp.Add(p)
    for layer, (x0, y0, x1, y1), w in ((pcbnew.F_SilkS, (1.89, -1.4, 15.89, 1.4), 0.12), (pcbnew.F_CrtYd, (-1.1, -1.65, 18.88, 1.65), 0.05),
                                         (pcbnew.F_Fab, (1.89, -1.25, 15.89, 1.25), 0.1)):
        s = pcbnew.FP_SHAPE(fp); s.SetShape(pcbnew.SHAPE_T_RECT); s.SetLayer(layer)
        s.SetStart0(pcbnew.VECTOR2I(mm(x0), mm(y0))); s.SetEnd0(pcbnew.VECTOR2I(mm(x1), mm(y1))); s.SetWidth(mm(w)); fp.Add(s)
    return fp

R06 = ("Resistor_SMD", "R_0603_1608Metric"); R08 = ("Resistor_SMD", "R_0805_2012Metric"); R12 = ("Resistor_SMD", "R_1206_3216Metric")
C06 = ("Capacitor_SMD", "C_0603_1608Metric"); C08 = ("Capacitor_SMD", "C_0805_2012Metric"); C12 = ("Capacitor_SMD", "C_1206_3216Metric")
C1210 = ("Capacitor_SMD", "C_1210_3225Metric"); SOT23 = ("Package_TO_SOT_SMD", "SOT-23"); SOD123 = ("Diode_SMD", "D_SOD-123")
SMC = ("Diode_SMD", "D_SMC"); LED = ("LED_SMD", "LED_0805_2012Metric"); OPTO = ("Package_DIP", "SMDIP-4_W9.53mm")
TOLL = ("Package_TO_SOT_SMD", "Infineon_PG-HSOF-8-1_ThermalVias"); TIE = ("NetTie", "NetTie-2_SMD_Pad0.5mm")
TP = ("TestPoint", "TestPoint_Pad_D1.5mm")

# ------------------------------------------------------------------ power board
PW, PH = 118.0, 120.0
FET_X = [17.0 + 11.0 * i for i in range(8)]
FET_Y = 29.0

def power_board():
    B = Board(os.path.join(HERE, "ks_power.kicad_pcb"))
    pl = B.place
    # studs (ring lugs, M5 for the 100 A leads, M4 for the signal ground)
    pl("J1", "MountingHole", "MountingHole_5.3mm_M5_Pad_Via", 58.0, 11.0, 0, "BAT+ IN (M5)", {"1": "VIN"}, ref_at=(58.0, 11.0), hide_ref=True)
    pl("J2", "MountingHole", "MountingHole_5.3mm_M5_Pad_Via", 58.0, 58.0, 0, "THRUSTER+ OUT (M5)", {"1": "VOUT"}, hide_ref=True)
    pl("J3", "MountingHole", "MountingHole_4.3mm_M4_Pad_Via", 5.75, 50.0, 0, "GND (M4)", {"1": "GND"}, hide_ref=True)
    # main switch: 8 MOSFETs, drain tab up into VIN, sources down into VOUT, one 10 Ohm gate resistor each
    for i, x in enumerate(FET_X):
        n = i + 1
        pl(f"Q{n}", *TOLL, x, FET_Y, 90, "IPT007N06N", {"1": f"G{n}", "2": "VOUT", "3": "VIN"}, ref_at=(x + 1.5, FET_Y - 4.0), ref_size=1.0)
        pl(f"RG{n}", *R06, x - 4.2, FET_Y + 8.6, 270, "10", {"1": f"G{n}", "2": "FG"}, ref_at=(x - 2.2, FET_Y + 8.6, 90), ref_size=0.8)
    # surge clamps and local ceramics
    pl("D1", *SMC, 14.6, 6.0, 180, "SMDJ26A", {"1": "VIN", "2": "GND"}, ref_at=(14.6, 2.6))     # 3 kW: battery-lead energy at a hard turn-off
    pl("C1", *C1210, 12.0, 14.0, 0, "2.2u 100V", {"1": "GND", "2": "VIN"}, ref_at=(16.4, 14.0, 90), ref_size=0.8)
    pl("C2", *C1210, 12.0, 19.0, 0, "2.2u 100V", {"1": "GND", "2": "VIN"}, ref_at=(16.4, 19.0, 90), ref_size=0.8)
    pl("D2", *SMC, 14.6, 70.0, 180, "SMCJ26A", {"1": "VOUT", "2": "GND"}, ref_at=(14.6, 73.4))
    pl("C3", *C1210, 12.0, 64.0, 0, "2.2u 100V", {"1": "GND", "2": "VOUT"}, ref_at=(16.4, 64.0, 90), ref_size=0.8)
    # Kelvin taps for the controller: net ties right at the bands
    pl("RK1", *R06, 102.3, 22.3, 270, "0R (VIN Kelvin)", {"1": "VIN", "2": "VIN_K"}, hide_ref=True)
    pl("RK2", *R06, 101.3, 35.6, 270, "0R (VOUT Kelvin)", {"1": "VOUT", "2": "VOUT_K"}, hide_ref=True)
    # pre-charge path in the right-hand channel
    pl("Q9", "Package_TO_SOT_SMD", "TO-252-2", 111.0, 31.5, 270, "FQD11P06", {"1": "PCG", "2": "PCD", "3": "VIN"}, ref_at=(116.6, 31.5, 90))
    pl("R8", *R08, 116.0, 20.0, 270, "47k", {"1": "VIN", "2": "PCG"}, ref_at=(116.0, 16.6, 90), ref_size=0.8)
    pl("D4", *SOD123, 112.4, 20.0, 270, "BZT52C12", {"1": "VIN", "2": "PCG"}, ref_at=(110.4, 20.0, 90), ref_size=0.8)

    pl("F1", "Fuse", "Fuse_1812_4532Metric", 111.0, 40.2, 270, "PTC 0.5A 30V 1812", {"1": "PCD", "2": "PCF"}, ref_at=(114.0, 40.2, 90))
    pl("R12", "Resistor_THT", "R_Axial_DIN0414_L11.9mm_D4.5mm_P15.24mm_Horizontal", 107.5, 45.0, 270, "22 2W", {"1": "PCF", "2": "VOUT"}, ref_at=(107.5, 52.5, 90))
    pl("R13", "Resistor_THT", "R_Axial_DIN0414_L11.9mm_D4.5mm_P15.24mm_Horizontal", 114.5, 45.0, 270, "22 2W", {"1": "PCF", "2": "VOUT"}, ref_at=(114.5, 52.5, 90))
    # ---------------- logic area (y > 77)
    L = 77.0
    # controller
    pl("U1", "Package_SO", "MSOP-10_3x3mm_P0.5mm", 95.0, L + 11.0, 0, "LM5060", {"1": "SNS", "2": "VIN_K", "3": "OVP", "4": "UV", "5": "EN",
        "6": "GND", "7": "TMR", "8": "PGD", "9": "VOUT_K", "10": "GDRV"}, ref_at=(95.0, L + 7.6))
    pl("R1", *R06, 91.0, L + 4.5, 0, "4.32k 1%", {"1": "VIN_K", "2": "SNS"})
    pl("C6", *C06, 95.5, L + 4.5, 0, "100n 100V", {"1": "VIN_K", "2": "GND"})
    pl("C5", *C08, 101.6, L + 12.5, 270, "470n", {"1": "TMR", "2": "GND"})
    pl("R2", *R06, 86.0, L + 9.0, 90, "47k", {"1": "VIN_K", "2": "UV"})
    pl("R3", *R06, 86.0, L + 14.0, 90, "10k", {"1": "UV", "2": "GND"})
    pl("C7", *C06, 88.5, L + 16.5, 0, "10n", {"1": "UV", "2": "GND"})
    pl("R4", *R06, 83.5, L + 9.0, 90, "150k", {"1": "VIN_K", "2": "OVP"})
    pl("R5", *R06, 83.5, L + 14.0, 90, "10k", {"1": "OVP", "2": "GND"})
    pl("R6", *R06, 100.5, L + 16.5, 0, "100k", {"1": "PGD", "2": "V5"})
    # gate protection and the independent gate-kill optocoupler
    pl("D3", *SOD123, 108.5, L + 3.0, 0, "BZT52C15", {"1": "FG", "2": "VOUT_K"})
    # fast turn-off: D9 feeds the charge pump to the gates; when the LM5060 pulls GDRV down, Q11 turns on and
    # discharges the gates through R44 (220 Ohm: about 20 us through the Miller plateau, so di/dt stays moderate)
    pl("D9", "Diode_SMD", "D_SOD-323", 106.0, L + 6.5, 90, "BAT54WS", {"1": "FG", "2": "GDRV"})
    pl("R43", *R06, 104.3, L + 6.5, 90, "1k", {"1": "GDRV", "2": "PNB2"})
    pl("Q11", *SOT23, 113.6, L + 3.0, 0, "MMBT3906", {"1": "PNB2", "2": "FG", "3": "QOFF"})
    pl("R44", *R08, 114.2, L + 7.5, 90, "220", {"1": "QOFF", "2": "VOUT_K"})
    pl("C4", *C08, 109.3, L + 7.0, 0, "47n 50V", {"1": "FG", "2": "VOUT_K"})
    pl("U2", *OPTO, 109.0, L + 13.0, 0, "PC817 (gate kill)", {"1": "KA", "2": "KC", "3": "VOUT_K", "4": "FG"}, ref_at=(109.0, L + 9.6))
    pl("R7", *R06, 103.0, L + 18.5, 0, "1k", {"1": "V5", "2": "KA"})
    pl("Q12", *SOT23, 108.0, L + 19.5, 0, "2N7002", {"1": "NARM", "2": "GND", "3": "KC"})
    # pre-charge driver
    pl("Q13", *SOT23, 113.5, L + 21.0, 0, "2N7002", {"1": "PCEN", "2": "GND", "3": "PDRV"})
    pl("R9", *R08, 116.5, L + 18.0, 270, "22k", {"1": "PCG", "2": "PDRV"})
    pl("R10", *R06, 113.5, L + 25.0, 0, "100k", {"1": "ARM", "2": "PCEN"})
    pl("R11", *R06, 113.5, L + 27.5, 0, "1M", {"1": "PCEN", "2": "GND"})
    # comparators
    pl("U4", "Package_SO", "SOIC-14_3.9x8.7mm_P1.27mm", 76.0, L + 12.0, 0, "LM339", {"1": "EN", "2": "PCEN", "3": "V5", "4": "RAMP",
        "5": "VOD", "6": "VIND", "7": "VOD", "8": "OVP", "9": "REF2", "10": "V5", "11": "GND", "12": "GND", "14": "PCEN"}, ref_at=(76.0, L + 6.0))
    pl("R45", *R06, 66.0, L + 24.0, 0, "15.8k 1%", {"1": "V5", "2": "REF2"})
    pl("R46", *R06, 66.0, L + 26.5, 0, "10k 1%", {"1": "REF2", "2": "GND"})
    pl("C17", *C06, 81.0, L + 8.0, 90, "100n", {"1": "V5", "2": "GND"})
    pl("R28", *R06, 70.0, L + 5.0, 0, "90.9k 1%", {"1": "VOUT_K", "2": "VOD"})
    pl("R29", *R06, 70.0, L + 7.5, 0, "10k 1%", {"1": "VOD", "2": "GND"})
    pl("R30", *R06, 70.0, L + 10.0, 0, "1M", {"1": "V5", "2": "VOD"})
    pl("C13", *C06, 66.5, L + 7.5, 90, "10n", {"1": "VOD", "2": "GND"})
    pl("R31", *R06, 82.0, L + 17.0, 0, "191k 1%", {"1": "VIN_K", "2": "VIND"})
    pl("R32", *R06, 82.0, L + 19.5, 0, "10k 1%", {"1": "VIND", "2": "GND"})
    pl("C14", *C06, 82.0, L + 22.0, 0, "10n", {"1": "VIND", "2": "GND"})
    pl("R33", *R06, 70.0, L + 16.0, 0, "1M", {"1": "VIN_K", "2": "RAMP"})
    pl("R34", *R06, 70.0, L + 18.5, 0, "47k", {"1": "RAMP", "2": "GND"})
    pl("C15", *C08, 70.0, L + 21.5, 0, "3.3u", {"1": "RAMP", "2": "GND"})
    pl("Q17", *SOT23, 75.5, L + 21.0, 0, "2N7002", {"1": "NARM", "2": "GND", "3": "RAMP"})
    # enable timing: slow rise through R26/C12 (1.1 s), fast fall through Q16 and the PNP Q10
    pl("R26", *R06, 60.0, L + 6.0, 0, "100k", {"1": "ARM", "2": "EN"})
    pl("C12", *C12, 60.0, L + 9.5, 0, "22u 16V", {"1": "EN", "2": "GND"})
    pl("Q16", *SOT23, 60.0, L + 14.0, 0, "2N7002", {"1": "NARM", "2": "GND", "3": "END"})
    pl("R27", *R06, 64.0, L + 14.0, 90, "10", {"1": "END", "2": "EN"})
    pl("Q10", *SOT23, 60.0, L + 19.0, 0, "MMBT3906", {"1": "PNB", "2": "EN", "3": "GND"})
    pl("R21", *R06, 64.0, L + 19.0, 90, "4.7k", {"1": "PNB", "2": "ARM"})
    # inverter NARM = not ARM
    pl("Q15", *SOT23, 52.0, L + 6.0, 0, "2N7002", {"1": "ARMG", "2": "GND", "3": "NARM"})
    pl("R23", *R06, 52.0, L + 10.0, 0, "10k", {"1": "ARM", "2": "ARMG"})
    pl("R24", *R06, 52.0, L + 12.5, 0, "100k", {"1": "ARMG", "2": "GND"})
    pl("R25", *R06, 52.0, L + 15.0, 0, "100k", {"1": "V5", "2": "NARM"})
    # arm chain: 5 V -> reed -> Hall-switched P-MOSFET -> ARM
    pl("Q14", *SOT23, 40.0, L + 8.0, 0, "BSS84", {"1": "HG", "2": "ROUT", "3": "ARM"})
    pl("R19", *R06, 40.0, L + 12.0, 0, "100k", {"1": "ROUT", "2": "HG"})
    pl("R20", *R06, 40.0, L + 14.5, 0, "10k", {"1": "HG", "2": "HALL"})
    pl("C11", *C08, 45.0, L + 9.0, 90, "2.2u", {"1": "ARM", "2": "GND"})
    pl("R22", *R06, 45.0, L + 13.5, 90, "2.2k", {"1": "ARM", "2": "GND"})
    pl("R17", *R06, 34.0, L + 17.0, 0, "100", {"1": "V5", "2": "RIN"})
    pl("R18", *R06, 34.0, L + 19.5, 0, "100", {"1": "V5", "2": "V5S"})
    pl("C16", *C06, 34.0, L + 22.0, 0, "100n", {"1": "V5S", "2": "GND"})
    # LED drivers (LEDs on the sensor board) and the on-board LIVE LED
    pl("R36", *R06, 46.0, L + 25.0, 0, "1k", {"1": "V5", "2": "LSAFE"})
    pl("Q18", *SOT23, 51.0, L + 25.0, 0, "2N7002", {"1": "SAFEG", "2": "GND", "3": "LSAFE"})
    pl("R37", *R06, 51.0, L + 21.0, 0, "10k", {"1": "ARM", "2": "SAFEG"})
    pl("R38", *R06, 55.0, L + 23.0, 90, "100k", {"1": "SAFEG", "2": "GND"})
    pl("R39", *R12, 22.0, L + 6.0, 0, "4.7k", {"1": "VOUT_K", "2": "LIVEA"})
    # status LEDs in one row at the bottom edge: HALL and REED (each sensor seen on its own), SAFE, LIVE
    for ref, x, colour, a, k in (("D6", 48.0, "blue HALL", "HLA", "HALL"), ("D7", 53.0, "blue REED", "RLA", "GND"),
                                  ("D8", 58.0, "green SAFE", "LSAFE", "GND"), ("LED1", 63.0, "red LIVE", "LIVEA", "GND")):
        pl(ref, *LED, x, L + 37.0, 90, colour, {"1": k, "2": a}, hide_ref=True)
    pl("R41", *R06, 46.0, L + 33.5, 0, "1k", {"1": "V5S", "2": "HLA"})
    pl("R42", *R06, 51.5, L + 31.0, 0, "1k", {"1": "ROUT", "2": "RLA"})
    # logic 5 V: LM317 from the VIN Kelvin line
    pl("R14", *R08, 20.0, L + 15.0, 0, "10", {"1": "VIN_K", "2": "VINL"})
    pl("C8", *C08, 20.0, L + 18.0, 0, "1u 50V", {"1": "VINL", "2": "GND"})
    pl("U3", "Package_TO_SOT_SMD", "SOT-223-3_TabPin2", 27.0, L + 15.0, 0, "LM317", {"1": "ADJ", "2": "V5", "3": "VINL"}, ref_at=(27.0, L + 10.2))
    pl("R15", *R06, 26.0, L + 21.5, 0, "240 1%", {"1": "V5", "2": "ADJ"})
    pl("R16", *R06, 26.0, L + 24.0, 0, "750 1%", {"1": "ADJ", "2": "GND"})
    pl("C9", *C08, 20.0, L + 21.5, 0, "10u 16V", {"1": "V5", "2": "GND"})
    pl("D5", *SOD123, 20.0, L + 25.0, 0, "BZT52C6V2", {"1": "V5", "2": "GND"})
    # status to the Jetson through an optocoupler
    pl("U5", *OPTO, 92.0, L + 25.0, 0, "PC817 (status)", {"1": "STA", "2": "GND", "3": "STE", "4": "STC"}, ref_at=(92.0, L + 21.6))
    pl("R40", *R12, 82.0, L + 26.5, 0, "10k", {"1": "VOUT_K", "2": "STA"})
    pl("J5", "Connector_JST", "JST_XH_B2B-XH-A_1x02_P2.50mm_Vertical", 95.75, L + 37.0, 0, "STATUS to Jetson", {"1": "STC", "2": "STE"}, ref_at=(97.0, L + 33.0))
    # bought sensors: a 3-pin Hall module (KY-003 style, S + -) and a 2-wire reed door contact (MC-38 style)
    pl("J4", "Connector_JST", "JST_XH_B3B-XH-A_1x03_P2.50mm_Vertical", 20.0, L + 37.0, 0, "HALL MODULE (KY-003: S + -)",
       {"1": "HALL", "2": "V5S", "3": "GND"}, hide_ref=True)
    pl("J6", "Connector_JST", "JST_XH_B2B-XH-A_1x02_P2.50mm_Vertical", 33.0, L + 37.0, 0, "REED CONTACT (MC-38)",
       {"1": "RIN", "2": "ROUT"}, hide_ref=True)
    # test points
    for i, (nm, x) in enumerate((("FG", 64.0), ("EN", 68.0), ("ARM", 72.0), ("V5", 76.0), ("VOD", 80.0), ("GND", 84.0))):
        pl(f"TP{i + 1}", *TP, x, L + 31.0, 0, nm, {"1": nm}, ref_at=(x, L + 33.2), ref_size=0.8)
    # mounting holes: nylon M3 only (they sit in live copper areas)
    for i, (x, y) in enumerate(((4.0, 4.0), (114.0, 4.0), (4.0, 116.0), (114.0, 116.0))):
        pl(f"H{i + 1}", "MountingHole", "MountingHole_3.2mm_M3", x, y, 0, "M3 nylon", {}, hide_ref=True)

    s = pcbnew.PCB_SHAPE(B.b); s.SetShape(pcbnew.SHAPE_T_RECT); s.SetLayer(pcbnew.Edge_Cuts)
    s.SetStart(B.P(0, 0)); s.SetEnd(B.P(PW, PH)); s.SetWidth(mm(0.1)); B.b.Add(s)
    # silkscreen
    t = B.text
    t("BAT+ IN", 58.0, 18.2, 1.4, bold=True); t("M5 ring lug, 6 AWG", 58.0, 20.4, 0.9)
    t("THRUSTER+ OUT", 58.0, 65.2, 1.4, bold=True); t("M5 ring lug, 6 AWG", 58.0, 67.4, 0.9)
    t("GND", 5.75, 57.4, 1.2, bold=True); t("signal", 5.75, 59.2, 0.8); t("M4", 5.75, 60.8, 0.8)
    t("MAGNETIC KILL SWITCH", 58.0, 45.0, 1.6, bold=True)
    t("100 A cont / 150 A burst / 3S-6S LiPo", 58.0, 47.6, 1.0)
    t("magnet in = thrusters live, magnet out = killed", 58.0, 49.6, 1.0)
    t("M3 NYLON ONLY", 110.5, 8.6, 0.8); t("NYLON", 4.6, 8.6, 0.8); t("NYLON", 4.6, 111.4, 0.8); t("NYLON", 113.4, 111.4, 0.8)
    t("OVP R4: 150k 6S / 91k 4S", 101.0, L + 30.0, 0.8)
    t("HALL MODULE", 22.5, L + 41.6, 0.8, bold=True); t("S  +  -", 22.5, L + 33.4, 0.8)
    t("REED", 34.25, L + 41.6, 0.8, bold=True)
    t("HALL REED SAFE LIVE", 55.5, L + 41.6, 0.8)
    t("Jetson: low = live", 97.0, L + 41.4, 0.8)
    t("pre-charge", 111.0, 70.0, 0.9, rot=90)
    # bottom: insulating pad note
    B.text("Bottom = VIN / VOUT copper:", 30.0, 57.0, 1.0, layer=pcbnew.B_SilkS)
    B.text("insulating thermal pad only", 30.0, 59.0, 1.0, layer=pcbnew.B_SilkS)
    B.text("2 oz copper, ENIG", 30.0, 61.0, 1.0, layer=pcbnew.B_SilkS)
    B.rules(clearance=0.25, track=0.3)
    return B

if __name__ == "__main__":
    pw = power_board(); auto_refs(pw, (0, 0, PW, PH)); pw.save(os.path.join(HERE, "bom_power.csv"))
    open(os.path.join(HERE, "ks.kicad_dru"), "w").write('(version 1)\n(rule "plane_spokes" (layer "F.Cu") (constraint min_resolved_spokes 1))\n')
