"""Magnetic kill switch, small SMD version (KiCad 7): ks_smd.kicad_pcb, 2 layers, 2 oz copper.

Same circuit and net names as the through-hole board (build_tht.py), with SMD parts:
  - 4 x IPT007N06N (TOLL, 60 V, 0.75 mOhm max) in parallel as one high-side switch, 100 A continuous.
  - XT90 in (battery, XT90PW-M) and XT90 out (ESC harness, XT90PW-F), both on the left edge, IN above OUT, so
    the two minus pins sit next to each other and the 100 A ground link between them is only 11 mm long.
  - The 100 A paths are copper pours on both layers plus bare strips (no solder mask) for 8 AWG bare copper wire:
    VIN above the MOSFET row, VOUT below it and down to the OUT connector, and the GND link on the bottom side.
  - The two TVS diodes (SMCJ28A) sit on the bottom, right between the + and - pins of each XT90.
  - Gate drive, pre-charge, arm chain and the LM339 sequencing are the through-hole circuit 1:1
    (0805 resistors, SOT-23 transistors, SOIC-14 LM339, SOP-4 optocoupler, DPAK regulator and pre-charge MOSFET).
Run with KiCad 7's python from this folder:  python3 build_smd.py   (then python3 route_smd.py)
"""
import os
import pcbnew
from build_ks import Board, auto_refs, OX, OY, mm, HERE

W, H = 80.0, 75.0
KS = os.path.join(HERE, "ks.pretty")

F = {
    "TOLL": ("Package_TO_SOT_SMD", "Infineon_PG-HSOF-8-1_ThermalVias"), "DPAK": ("Package_TO_SOT_SMD", "TO-252-2"),
    "SOT23": ("Package_TO_SOT_SMD", "SOT-23"), "SOIC14": ("Package_SO", "SOIC-14_3.9x8.7mm_P1.27mm"),
    "SOP4": ("Package_SO", "SOP-4_4.4x2.6mm_P1.27mm"),
    "R": ("Resistor_SMD", "R_0805_2012Metric"), "R12": ("Resistor_SMD", "R_1206_3216Metric"), "R2512": ("Resistor_SMD", "R_2512_6332Metric"),
    "C": ("Capacitor_SMD", "C_0805_2012Metric"), "C12": ("Capacitor_SMD", "C_1206_3216Metric"),
    "CPE": ("Capacitor_SMD", "CP_Elec_6.3x7.7"), "TANT": ("Capacitor_Tantalum_SMD", "CP_EIA-3216-18_Kemet-A"),
    "SMC": ("Diode_SMD", "D_SMC"), "SMB": ("Diode_SMD", "D_SMB"), "SMA": ("Diode_SMD", "D_SMA"), "SOD123": ("Diode_SMD", "D_SOD-123"),
    "LED": ("LED_SMD", "LED_0805_2012Metric"), "PTC": ("Fuse", "Fuse_2920_7451Metric"),
    "XH2": ("Connector_JST", "JST_XH_B2B-XH-A_1x02_P2.50mm_Vertical"), "XH3": ("Connector_JST", "JST_XH_B3B-XH-A_1x03_P2.50mm_Vertical"),
    "SIP4": ("Connector_PinHeader_2.54mm", "PinHeader_1x04_P2.54mm_Vertical"),
    "XT90M": (KS, "AMASS_XT90PW-M_1x02_P10.90mm_Horizontal"), "XT90F": (KS, "AMASS_XT90PW-F_1x02_P10.90mm_Horizontal"),
    "TP": ("TestPoint", "TestPoint_Pad_D1.5mm"),
}
def two(a, b): return {"1": a, "2": b}

# ------------------------------------------------------------------------------------------------ netlist
# pads: TOLL 1 G 2 S 3 D(tab); DPAK 1 G/IN 2 D/GND(tab) 3 S/OUT; SOT-23 MOSFET 1 G 2 S 3 D, bipolar 1 B 2 E 3 C;
# diodes and LEDs 1 = cathode; SOP-4 opto 1 A 2 K 3 E 4 C; SOIC-14 LM339 = DIP pin numbers
PARTS = []
def part(ref, fp, value, pads, back=False): PARTS.append((ref, fp, value, pads, back))

NFET = 4
for n in range(1, NFET + 1):                                     # power switch
    part(f"Q{n}", "TOLL", "IPT007N06N", {"1": f"G{n}", "2": "VOUT", "3": "VIN"})
    part(f"RG{n}", "R", "10", two(f"G{n}", "FG"))
    part(f"RS{n}", "R", "1M", two(f"G{n}", "SRC"))
part("J1", "XT90M", "XT90PW-M battery IN", {"1": "GND", "2": "VIN", "MP": "GND"})
part("J2", "XT90F", "XT90PW-F ESC OUT", {"1": "GND", "2": "VOUT", "MP": "GND"})
part("D1", "SMC", "SMCJ28A", two("VIN", "GND"), back=True)      # bottom side, between the IN connector's pins
part("D2", "SMC", "SMCJ28A", two("VOUT", "GND"), back=True)     # bottom side, between the OUT connector's pins
part("RK1", "R12", "0R", two("VIN", "VIN_K"))                    # logic taps VIN here (7805, dividers, pre-charge)
part("RK2", "R12", "0R", two("VOUT", "SRC"))                     # gate-drive ground taps VOUT here
# pre-charge
part("Q11", "DPAK", "FQD11P06", {"1": "PCG", "2": "PCD", "3": "VIN_K"})
part("R1", "R", "47k", two("VIN_K", "PCG"))
part("D3", "SOD123", "BZT52C12", two("VIN_K", "PCG"))
part("R2", "R", "22k", two("PCG", "PCDN"))
part("Q12", "SOT23", "2N7002", {"1": "PCEN", "2": "GND", "3": "PCDN"})
part("F1", "PTC", "MF-SM050/60-2 (0.5 A, 60 V)", two("PCD", "PCF"))
part("R3", "R2512", "22 2512", two("PCF", "SRC"))
part("R4", "R2512", "22 2512", two("PCF", "SRC"))
# 5 V
part("D4", "SMA", "S1M", two("VR1", "VIN_K"))
part("R5", "R12", "10", two("VR1", "VR2"))
part("C1", "CPE", "47u 50V", two("VR2", "GND"))
part("U1", "DPAK", "L7805CDT", {"1": "VR2", "2": "GND", "3": "V5"})
part("C2", "C12", "10u 25V", two("V5", "GND"))
# V5 / 2 reference
part("R6", "R", "10k", two("V5", "REF"))
part("R7", "R", "10k", two("REF", "GND"))
part("C8", "C", "100n", two("REF", "GND"))
# sensors and arm chain
part("J3", "XH3", "HALL MODULE (KY-003: S + -)", {"1": "HALL", "2": "V5S", "3": "GND"})
part("J4", "XH2", "REED (MC-38)", two("RIN", "ROUT"))
part("R8", "R", "100", two("V5", "V5S"))
part("R9", "R", "100", two("V5", "RIN"))
part("Q13", "SOT23", "MMBT3906", {"1": "QAB", "2": "ROUT", "3": "ARM"})
part("R10", "R", "10k", two("QAB", "HALL"))
part("R11", "R", "47k", two("ROUT", "QAB"))
part("R12", "R", "4.7k", two("ARM", "GND"))
part("D7", "LED", "blue HALL", two("HALL", "HLA"))
part("R13", "R", "1k", two("V5S", "HLA"))
part("D8", "LED", "blue REED", two("GND", "RLA"))
part("R14", "R", "1k", two("ROUT", "RLA"))
part("R15", "R", "100k", two("ARM", "EN"))
part("C7", "TANT", "10u 16V tantalum", two("EN", "GND"))
part("Q14", "SOT23", "MMBT3904", {"1": "QIB", "2": "GND", "3": "NARM"})
part("R16", "R", "10k", two("ARM", "QIB"))
part("R17", "R", "10k", two("V5", "NARM"))
part("Q15", "SOT23", "MMBT3904", {"1": "QDB", "2": "GND", "3": "QDC"})
part("R18", "R", "10k", two("NARM", "QDB"))
part("R19", "R", "100k", two("QDB", "GND"))
part("R20", "R", "220", two("QDC", "EN"))
# pre-charge sequencing: one LM339
part("U2", "SOIC14", "LM339D", {"1": "PCEN", "2": "PCEN", "3": "V5", "4": "REF", "5": "EN", "6": "RAMP", "7": "VOD",
                                "8": "VIND", "9": "VOD", "10": "REF", "11": "EN", "12": "GND", "13": "RRST", "14": "DONE"})
part("C3", "C", "100n", two("V5", "GND"))
part("R21", "R", "75k 1%", two("SRC", "VOD"))
part("R22", "R", "10k 1%", two("VOD", "GND"))
part("R23", "R", "470k", two("V5", "VOD"))
part("C9", "C", "10n", two("VOD", "GND"))
part("R24", "R", "160k 1%", two("VIN_K", "VIND"))
part("R25", "R", "10k 1%", two("VIND", "GND"))
part("C10", "C", "10n", two("VIND", "GND"))
part("R26", "R", "1M", two("VIN_K", "RAMP"))
part("R27", "R", "68k", two("RAMP", "GND"))
part("C11", "C12", "3.3u X7R 50V", two("RAMP", "GND"))
part("R28", "R", "1k", two("RAMP", "RRST"))
part("R29", "R", "10k", two("V5", "PCEN"))
part("R30", "R", "10k", two("V5", "DONE"))
# live: PCEN and DONE both high -> gate-drive opto and the red LED
part("Q16", "SOT23", "2N7002", {"1": "PCEN", "2": "GND", "3": "QGM"})
part("Q17", "SOT23", "2N7002", {"1": "DONE", "2": "QGM", "3": "CATH"})
part("D9", "LED", "red LIVE", two("CATH", "LVA"))
part("R31", "R", "1k", two("V5", "LVA"))
part("U4", "SOP4", "EL357N", {"1": "UGA", "2": "CATH", "3": "DRV", "4": "V12F"})
part("R32", "R", "330", two("V5", "UGA"))
# floating gate drive (ground = VOUT)
part("U3", "SIP4", "B0512S-1WR3", {"1": "GND", "2": "V5", "3": "SRC", "4": "V12F"})
part("C4", "C12", "10u 25V", two("V5", "GND"))
part("C5", "C12", "22u 25V", two("V12F", "SRC"))
part("D5", "SMA", "SMAZ15", two("V12F", "SRC"))
part("R33", "R", "4.7k", two("V12F", "SRC"))
part("R34", "R", "22k", two("DRV", "SRC"))
part("D10", "SOD123", "1N4148W", two("DRVD", "DRV"))
part("R35", "R", "10k", two("DRVD", "FG"))
part("C6", "C12", "220n 100V X7R", two("FGC", "GND"))
part("R39", "R", "100", two("FGC", "FG"))
part("D11", "SMB", "SMBJ15A", two("FG", "SRC"))
part("Q18", "SOT23", "BC807-40", {"1": "QOB", "2": "FG", "3": "QOC"})
part("R36", "R", "47", two("QOC", "SRC"))
part("R37", "R", "47k", two("FG", "QOB"))                       # 47k (THT: 10k): lets the BC807 pull the gate below ~1.4 V
                                                                 # instead of leaving the low-threshold TOLLs half on at ~3 V
part("D6", "SOD123", "1N4148W", two("QOD", "QOB"))
part("R38", "R", "1k", two("QOD", "DRV"))
for i, net in enumerate(("FG", "EN", "V5", "GND"), 1):
    part(f"TP{i}", "TP", net, {"1": net})

# ------------------------------------------------------------------------------------------------ placement
XT_X = 24.15                                   # XT90 pin column: the connector fronts stick 0.5 mm past the left edge
IN_Y, OUT_Y = 16.4, 27.45                      # minus pins; IN + at 5.5 (top), OUT + at 38.35 (bottom)
FET_YC = 11.0                                  # TOLL centres (rot 90: drain tab up, gate + source leads down)
FET_XC = [34.0 + 11.4 * i for i in range(NFET)]
GATE_X = [x - 4.2 for x in FET_XC]             # gate lead of each MOSFET (a via under it takes the gate to B.Cu)
RG_X = [x + 7.5 for x in GATE_X]                # 10 Ohm + 1 MOhm pair of each MOSFET, right of the VOUT leg
FIXED = {
    "J1": (XT_X, IN_Y, 90), "J2": (XT_X, OUT_Y, 90),
    "D1": (15.0, (5.5 + IN_Y) / 2, 90), "D2": (15.0, (OUT_Y + 38.35) / 2, 90),
    "RK1": (77.0, 10.2, 270), "RK2": (76.5, 21.6, 270), "TP1": (77.0, 30.0, 0),   # rot 270: pad 1 up
}
for i, x in enumerate(FET_XC, 1):
    FIXED[f"Q{i}"] = (x, FET_YC, 90)
    FIXED[f"RG{i}"] = (RG_X[i - 1], 28.5, 270)                   # pad 1 (gate) up, pad 2 (gate bus) down
    FIXED[f"RS{i}"] = (RG_X[i - 1] + 2.6, 28.5, 270)             # pad 1 (gate) up, pad 2 (SRC) down
BACK_ROT = {}                                  # bottom-side parts: rotation chosen so pad 1 (cathode) faces the + pin
REGIONS = [   # (name, box, fill from "top" or "bottom", refs in connection order: neighbours in the list end up side by side)
    ("gate", (36.0, 26.0, 74.5, 44.0), "top", ["U3", "C5", "D5", "R33", "C4", "D11", "Q18", "R37", "R36", "D6", "R38", "R39", "C6",
                                             "R35", "D10", "R34", "U4"]),
    ("pre", (43.0, 44.6, 79.5, 66.8), "top", ["Q11", "R1", "D3", "R2", "Q12", "F1", "R3", "R4", "D4", "R5", "C1", "U1", "C2"]),
    ("logic", (18.5, 44.6, 43.0, 66.8), "top", ["R32", "R29", "Q16", "Q17", "R31", "U2", "C3", "R30", "R6", "R7", "C8", "R23", "R21",
                                              "R22", "C9", "R24", "R25", "C10", "R26", "R27", "C11", "R28"]),
    ("arm", (0.5, 44.6, 18.5, 66.8), "bottom", ["R9", "R11", "R10", "R8", "R13", "R14", "Q13", "R12", "R15", "C7", "R20", "Q15", "R18",
                                              "R19", "Q14", "R16", "R17", "TP2", "TP3", "TP4"]),
]
HOLES = ((3.5, H - 3.5), (W - 3.5, H - 3.5), (W - 3.0, 3.4))
EDGE_H = 8.2                                   # bottom strip: sensor connectors, LEDs, logo
EDGE_ROW = [("J3", 0), ("J4", 0), ("D7", 0), ("D8", 0), ("D9", 0)]
GRID = 0.5
OVERFLOW = {}
GAP = 0.9                                      # courtyard to courtyard: room for one track between parts
U3_BODY = (-3.2, -2.1, 3.2, 9.7)               # the B0512S module body around its pin header (pin 1 at 0,0)

def courtyard(lib, name, rot):
    fp = pcbnew.FootprintLoad(lib if lib.endswith(".pretty") else "/usr/share/kicad/footprints/" + lib + ".pretty", name)
    fp.SetPosition(pcbnew.VECTOR2I(0, 0)); fp.SetOrientationDegrees(rot)
    xs, ys = [], []
    for g in fp.GraphicalItems():
        if g.GetLayer() == pcbnew.F_CrtYd:
            bb = g.GetBoundingBox(); xs += [bb.GetLeft(), bb.GetRight()]; ys += [bb.GetTop(), bb.GetBottom()]
    if not xs:
        for p in fp.Pads():
            bb = p.GetBoundingBox(); xs += [bb.GetLeft(), bb.GetRight()]; ys += [bb.GetTop(), bb.GetBottom()]
    box = (pcbnew.ToMM(min(xs)), pcbnew.ToMM(min(ys)), pcbnew.ToMM(max(xs)), pcbnew.ToMM(max(ys)))
    if name.startswith("PinHeader_1x04"):                       # the DC/DC module is bigger than its pins
        c, s = (1, 0) if rot % 180 == 0 else (0, 1)
        x0, y0, x1, y1 = U3_BODY
        box = (x0, y0, x1, y1) if rot == 0 else (-y1, x0, -y0, x1) if rot == 90 else box
    return box

def pack(pos):
    """Drop each region's parts (biggest first) at the top-most, then left-most free spot of their region, on a
    0.25 mm grid, trying both orientations; every part keeps GAP of free board around its courtyard."""
    import numpy as np
    by_ref = {p[0]: p for p in PARTS}
    R = 0.25; nx, ny = int(W / R) + 1, int(H / R) + 1
    occ = np.zeros((ny, nx), dtype=np.int32)
    def mark(x0, y0, x1, y1):
        occ[max(int(y0 / R), 0):max(int(np.ceil(y1 / R)), 0), max(int(x0 / R), 0):max(int(np.ceil(x1 / R)), 0)] = 1
    for ref, (x, y, rot) in pos.items():
        if by_ref.get(ref) and not by_ref[ref][4]:
            lib, fpn = F[by_ref[ref][1]]; cl, ct, cr, cb = courtyard(lib, fpn, rot); mark(x + cl - GAP / 2, y + ct - GAP / 2, x + cr + GAP / 2, y + cb + GAP / 2)
    for (hx, hy) in HOLES: mark(hx - 3.4, hy - 3.4, hx + 3.4, hy + 3.4)
    mark(0.0, H - EDGE_H, W, H)
    # power copper: nothing small goes on the VIN / VOUT pours or the right-hand track column
    for bx in ((17.0, 0.0, 74.6, 25.8), (28.0, 25.8, 35.8, 44.2), (17.0, 32.5, 35.8, 44.2), (74.0, 0.0, W, 44.2)): mark(*bx)
    mark(0.0, 0.0, 0.4, H); mark(W - 0.4, 0.0, W, H); mark(0.0, 0.0, W, 0.4)
    rows = {}
    for name, (x0, y0, x1, y1), fill, refs in REGIONS:
        items = [(0, ref) for ref in refs if ref not in pos]
        ybot = y0
        for _, ref in items:
            lib, fpn = F[by_ref[ref][1]]
            best = None
            for rot in ((0, 90) if not fpn.startswith("PinHeader") else (0,)):
                cl, ct, cr, cb = courtyard(lib, fpn, rot)
                wc = int(np.ceil((cr - cl + GAP) / R)); hc = int(np.ceil((cb - ct + GAP) / R))
                ix0, iy0, ix1, iy1 = int(np.ceil(x0 / R)), int(np.ceil(y0 / R)), int(x1 / R), int(y1 / R)
                sub = occ[iy0:iy1, ix0:ix1]
                if sub.shape[0] < hc or sub.shape[1] < wc: continue
                S = np.zeros((sub.shape[0] + 1, sub.shape[1] + 1), dtype=np.int64); S[1:, 1:] = sub.cumsum(0).cumsum(1)
                win = S[hc:, wc:] - S[:-hc, wc:] - S[hc:, :-wc] + S[:-hc, :-wc]
                free = np.argwhere(win == 0)
                if not len(free): continue
                k = np.lexsort((free[:, 1], free[:, 0] if fill == "top" else -free[:, 0]))[0]; jy, jx = free[k]
                bx0, by0 = (ix0 + jx) * R, (iy0 + jy) * R
                cand = (by0, bx0, rot, bx0 - cl + GAP / 2, by0 - ct + GAP / 2, wc, hc)
                key = (cand[0] if fill == "top" else -(cand[0] + hc * R), cand[1])
                if best is None or key < best[0]: best = (key, cand)
            if best is None: raise SystemExit(f"region {name}: no room for {ref}")
            by0, bx0, rot, px, py, wc, hc = best[1]
            px, py = round(px / R) * R, round(py / R) * R
            pos[ref] = (px, py, rot)
            cl, ct, cr, cb = courtyard(lib, fpn, rot)
            mark(px + cl - GAP / 2, py + ct - GAP / 2, px + cr + GAP / 2, py + cb + GAP / 2)
            ybot = max(ybot, py + cb)
        rows[name] = ybot
        print(f"  region {name}: y {y0:.1f}-{ybot:.1f} (limit {y1})")
    x = 7.5
    for ref, rot in EDGE_ROW:
        lib, fpn = F[by_ref[ref][1]]
        cl, ct, cr, cb = courtyard(lib, fpn, rot)
        px = round((x - cl) / GRID) * GRID; pos[ref] = (px, round((H - 1.0 - cb) / GRID) * GRID, rot); x = px + cr + 1.5
    return rows

def smd_board():
    B = Board(os.path.join(HERE, "ks_smd.kicad_pcb"))
    b = B.b
    B.rules(clearance=0.25, track=0.25)
    b.GetDesignSettings().SetCopperLayerCount(2)
    for x0, y0, x1, y1 in ((0, 0, W, 0), (W, 0, W, H), (W, H, 0, H), (0, H, 0, 0)):
        B.line(x0, y0, x1, y1, pcbnew.Edge_Cuts, 0.1)
    pos = dict(FIXED)
    pack(pos)
    for ref, fp, value, pads, back in PARTS:
        x, y, rot = pos[ref]
        lib, name = F[fp]
        f = B.place(ref, lib, name, x, y, rot, value, pads, back=back)
        if back:                                                # pad 1 (cathode) must face the + pin (up for D1, down for D2)
            p1 = [p for p in f.Pads() if p.GetNumber() == "1"][0].GetPosition().y
            p2 = [p for p in f.Pads() if p.GetNumber() == "2"][0].GetPosition().y
            want_up = ref == "D1"
            if (p1 < p2) != want_up: f.SetOrientationDegrees(f.GetOrientationDegrees() + 180)
    for i, (x, y) in enumerate(HOLES, 1):
        B.place(f"H{i}", "MountingHole", "MountingHole_3.2mm_M3", x, y, 0, "M3 nylon", {}, hide_ref=True)
    return B, pos

BUY = [   # (value starts with, what to buy); first match wins
    ("IPT007N06N", "Infineon IPT007N06N (TOLL / PG-HSOF-8-1, 60 V, 0.75 mOhm max): the drain is the big pad underneath - reflow or hot air"),
    ("FQD11P06", "onsemi FQD11P06TM (DPAK, -60 V P-MOSFET) - pre-charge switch"),
    ("2N7002", "2N7002 (SOT-23: 1 G, 2 S, 3 D)"), ("MMBT3904", "MMBT3904 (SOT-23: 1 B, 2 E, 3 C)"),
    ("MMBT3906", "MMBT3906 (SOT-23: 1 B, 2 E, 3 C)"), ("BC807-40", "BC807-40 (SOT-23 PNP: 1 B, 2 E, 3 C)"),
    ("L7805CDT", "ST L7805CDT-TR (DPAK, tab = GND)"), ("LM339D", "LM339DR (SOIC-14)"),
    ("EL357N", "Everlight EL357N(C)(TA)-G optocoupler (SOP-4, CTR 50-600 %; pins 1 A, 2 K, 3 E, 4 C)"),
    ("B0512S", "Mornsun B0512S-1WR3 (5 V -> 12 V isolated, 1 W, SIP-4, through-hole): pins 1 GND, 2 Vin, 3 0V, 4 +Vo - check yours"),
    ("SMCJ28A", "SMCJ28A TVS (SMC, 1500 W, 28 V standoff) - BOTTOM side, between the XT90 pins"),
    ("SMBJ15A", "SMBJ15A TVS (SMB, 600 W, 15 V standoff)"), ("SMAZ15", "SMAZ15 zener 15 V 1 W (SMA)"),
    ("S1M", "S1M diode 1 A 1000 V (SMA)"), ("BZT52C12", "BZT52C12 zener 12 V (SOD-123)"), ("1N4148W", "1N4148W (SOD-123)"),
    ("MF-SM050/60", "Bourns MF-SM050/60-2 PTC fuse (0.5 A hold, 60 V, 2920 size; LCSC C3760688)"),
    ("XT90PW-M", "AMASS XT90PW-M (male, PCB right-angle) - mates with the battery's XT90; rated 45 A continuous / 90 A burst"),
    ("XT90PW-F", "AMASS XT90PW-F (female, PCB right-angle) - the ESC harness plugs in here; rated 45 A continuous / 90 A burst"),
    ("HALL MODULE", "JST XH 3-pin header B3B-XH-A + housing XHP-3; KY-003 Hall module"),
    ("REED", "JST XH 2-pin header B2B-XH-A + housing XHP-2; MC-38 wired door contact (closed with the magnet)"),
    ("22 2512", "22 Ohm 2512 thick film, pulse-proof (1 W or more)"), ("0R", "0 Ohm 1206 jumper"),
    ("47u 50V", "SMD aluminium electrolytic 47 uF 50 V, 6.3 x 7.7 mm"), ("10u 16V tantalum", "tantalum 10 uF 16 V, case A (3216)"),
    ("3.3u X7R 50V", "MLCC 3.3 uF 50 V X7R 1206"), ("220n 100V X7R", "MLCC 220 nF 100 V X7R 1206"),
    ("22u 25V", "MLCC 22 uF 25 V X5R/X7R 1206"), ("10u 25V", "MLCC 10 uF 25 V X5R/X7R 1206"),
    ("100n", "MLCC 100 nF 50 V X7R 0805"), ("10n", "MLCC 10 nF 50 V X7R 0805"),
    ("blue", "LED 0805 blue"), ("red", "LED 0805 red"),
]

def grouped_bom(src=os.path.join(HERE, "bom_smd.csv"), dst=os.path.join(HERE, "bom_smd_grouped.csv")):
    """Order list: one line per value + footprint, with what to buy; plus the copper wire for the 100 A strips."""
    import csv, collections, re
    rows = list(csv.DictReader(open(src)))
    groups = collections.OrderedDict()
    for r in rows:
        if r["ref"].startswith(("TP",)): continue
        groups.setdefault((r["value"], r["footprint"]), []).append(r["ref"])
    def buy(v, fpn):
        for k, t in BUY:
            if v.startswith(k): return t
        if fpn.startswith("R_"):
            size = re.search(r"R_(\d{4})", fpn).group(1)
            return f"resistor {v.split()[0]} Ohm {size}" + (" 1 %" if "1%" in v else " 1 % or 5 %")
        return ""
    key = lambda kv: ("".join(c for c in kv[1][0] if not c.isdigit()), int("".join(c for c in kv[1][0] if c.isdigit()) or 0))
    with open(dst, "w", newline="") as f:
        w = csv.writer(f); w.writerow(["qty", "value", "footprint", "refs", "buy"])
        for (v, fpn), refs in sorted(groups.items(), key=key):
            w.writerow([len(refs), v, fpn, " ".join(refs), buy(v, fpn)])
        w.writerow([1, "8 AWG bare copper", "-", "-", "8 AWG (8 mm2) bare solid copper wire, about 15 cm: VIN strip 45 mm, VOUT strip 45 mm + 22 mm, "
                    "GND link 12 mm under the board between the XT90 minus pins - tin the strips and solder the wire along them"])
        w.writerow([3, "M3 nylon", "-", "H1 H2 H3", "M3 nylon screw + nylon standoff (H3 sits next to the VIN copper)"])
    print("grouped BOM:", dst, len(groups), "lines")

def small_refs(B, size=0.8):
    """auto_refs hides a reference when its first spots are taken: try more spots (corners, wider gaps) around the part."""
    b = B.b
    mmbb = lambda bb: (pcbnew.ToMM(bb.GetLeft()), pcbnew.ToMM(bb.GetTop()), pcbnew.ToMM(bb.GetRight()), pcbnew.ToMM(bb.GetBottom()))
    obst = []
    for fp in b.GetFootprints():
        for p in fp.Pads():
            x0, y0, x1, y1 = mmbb(p.GetBoundingBox()); obst.append((x0 - 0.15, y0 - 0.15, x1 + 0.15, y1 + 0.15))
        for g in fp.GraphicalItems():
            if g.GetLayer() == pcbnew.F_SilkS and type(g).__name__ in ("FP_SHAPE", "FP_TEXT"): obst.append(mmbb(g.GetBoundingBox()))
        if fp.Reference().IsVisible() and fp.GetLayer() == pcbnew.F_Cu: obst.append(mmbb(fp.Reference().GetBoundingBox()))
    for d in b.GetDrawings():
        if d.GetLayer() == pcbnew.F_SilkS: obst.append(mmbb(d.GetBoundingBox()))
    hit = lambda bx: any(bx[0] < o[2] and o[0] < bx[2] and bx[1] < o[3] and o[1] < bx[3] for o in obst)
    left = []
    for fp in sorted(b.GetFootprints(), key=lambda f: f.GetReference()):
        r = fp.Reference()
        if r.IsVisible() or fp.GetLayer() != pcbnew.F_Cu or fp.GetReference().startswith("H"): continue
        cx0, cy0, cx1, cy1 = mmbb(fp.GetBoundingBox(False, False)); mx, my = (cx0 + cx1) / 2, (cy0 + cy1) / 2
        r.SetTextSize(pcbnew.VECTOR2I(mm(size), mm(size))); r.SetTextThickness(mm(0.13)); r.SetVisible(True)
        ok = False
        for gap in (0.4, 0.7, 1.0, 1.4):
            for (x, y, a) in ((mx, cy0 - gap, 0), (mx, cy1 + gap, 0), (cx0 - gap, my, 90), (cx1 + gap, my, 90),
                              (cx0 - gap, cy0 - gap, 0), (cx1 + gap, cy0 - gap, 0), (cx0 - gap, cy1 + gap, 0), (cx1 + gap, cy1 + gap, 0)):
                r.SetPosition(pcbnew.VECTOR2I(mm(x), mm(y))); r.SetTextAngleDegrees(a)
                bx = mmbb(r.GetBoundingBox())
                if bx[0] < OX + 0.5 or bx[1] < OY + 0.5 or bx[2] > OX + W - 0.5 or bx[3] > OY + H - 0.5: continue
                if hit(bx): continue
                obst.append(bx); ok = True; break
            if ok: break
        if not ok: r.SetVisible(False); left.append(fp.GetReference())
    print("  second reference pass:", "all placed" if not left else f"still hidden {left}")

if __name__ == "__main__":
    B, pos = smd_board()
    auto_refs(B, (0, 0, W, H))
    small_refs(B)
    for fp in B.b.GetFootprints():          # the gate resistor pairs sit against the bare VOUT strip: named on the bottom silk instead
        if fp.GetReference().startswith(("RG", "RS")): fp.Reference().SetVisible(False)
    B.save(os.path.join(HERE, "bom_smd.csv"))
    grouped_bom()
    open(os.path.join(HERE, "ks_smd.kicad_dru"), "w").write('(version 1)\n(rule "plane_spokes" (constraint min_resolved_spokes 1))\n')
