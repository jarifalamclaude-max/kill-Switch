"""Magnetic kill switch, through-hole version (KiCad 7): ks_tht.kicad_pcb, 2 layers, 2 oz copper.

For 4S-6S LiPo (12-25.2 V), XT60 in (battery) and XT60 out (ESC harness): 30 A continuous / 60 A burst, the
XT60's own rating. Every part is through-hole.
  - 4 x IRFB3206 (TO-220, 60 V, 3.0 mOhm max) in parallel as one high-side switch (about 0.2 W each at 30 A).
  - Gate supply: an isolated 5 V -> 12 V module (B0512S, SIP-4) whose output floats on the MOSFET sources, so the
    gates get about +13 V whatever the pack voltage. A PC817 switches it onto the gate bus through 4.7 kOhm with
    a 100 nF soft-start capacitor to VIN; a BC327 pulls the gates down fast when the opto lets go.
  - Arm chain, energise to arm: 5 V -> reed (MC-38 door contact, closed with the magnet, J4) -> 2N3906 switched
    by the Hall module (KY-003, J3) -> ARM. ARM charges EN (100k / 10 uF, about 0.8 s); losing ARM empties EN in
    about 1.5 ms through a 2N3904, so gaps under ~1 ms (vibration) are ignored.
  - Pre-charge: IRF9540N + 0.5 A PTC + 2 x 22 Ohm 2 W charge the ESC capacitors first. One LM339:
    EN above V5/2 starts it; if VOUT does not follow a ramp that rises with VIN (shorted bus) it stops and stays
    off until the magnet is pulled; the main MOSFETs close only when VOUT > 0.5 VIN. The same comparator also
    trips when a short pulls VOUT down while running.
Run with KiCad 7's python from this folder:  python3 build_tht.py   (then python3 route_tht.py)
"""
import os
import pcbnew
from build_ks import Board, auto_refs, OX, OY, mm, HERE

W, H = 120.0, 98.0
G = 2.54

F = {
    "FET": ("Package_TO_SOT_THT", "TO-220-3_Vertical"), "TO220H": ("Package_TO_SOT_THT", "TO-220-3_Horizontal_TabDown"),
    "TO92": ("Package_TO_SOT_THT", "TO-92_Inline_Wide"), "DIP14": ("Package_DIP", "DIP-14_W7.62mm"),
    "DIP8": ("Package_DIP", "DIP-8_W7.62mm"), "DIP4": ("Package_DIP", "DIP-4_W7.62mm"),
    "R": ("Resistor_THT", "R_Axial_DIN0207_L6.3mm_D2.5mm_P2.54mm_Vertical"),
    "RH": ("Resistor_THT", "R_Axial_DIN0207_L6.3mm_D2.5mm_P7.62mm_Horizontal"),
    "RV": ("Resistor_THT", "R_Axial_DIN0207_L6.3mm_D2.5mm_P2.54mm_Vertical"),
    "R2W": ("Resistor_THT", "R_Axial_DIN0414_L11.9mm_D4.5mm_P15.24mm_Horizontal"),
    "CD": ("Capacitor_THT", "C_Disc_D5.0mm_W2.5mm_P5.00mm"),
    "CF": ("Capacitor_THT", "C_Rect_L7.2mm_W3.5mm_P5.00mm_FKS2_FKP2_MKS2_MKP2"),
    "CE5": ("Capacitor_THT", "CP_Radial_D5.0mm_P2.00mm"), "CE6": ("Capacitor_THT", "CP_Radial_D6.3mm_P2.50mm"),
    "D35": ("Diode_THT", "D_DO-35_SOD27_P2.54mm_Vertical_KathodeUp"), "D41": ("Diode_THT", "D_DO-41_SOD81_P10.16mm_Horizontal"), "DO15": ("Diode_THT", "D_DO-15_P10.16mm_Horizontal"),
    "P600": ("Diode_THT", "D_P600_R-6_P12.70mm_Horizontal"), "D201": ("Diode_THT", "D_DO-201AE_P15.24mm_Horizontal"),
    "LED": ("LED_THT", "LED_D3.0mm"), "PTC": ("Fuse", "Fuse_Bourns_MF-RHT050"),
    "XH2": ("Connector_JST", "JST_XH_B2B-XH-A_1x02_P2.50mm_Vertical"), "XH3": ("Connector_JST", "JST_XH_B3B-XH-A_1x03_P2.50mm_Vertical"),
    "SIP4": ("Connector_PinHeader_2.54mm", "PinHeader_1x04_P2.54mm_Vertical"),
    "XT60M": ("Connector_AMASS", "AMASS_XT60PW-M_1x02_P7.20mm_Horizontal"), "XT60F": ("Connector_AMASS", "AMASS_XT60PW-F_1x02_P7.20mm_Horizontal"),
    "M5": ("MountingHole", "MountingHole_5.3mm_M5_Pad_Via"), "M4": ("MountingHole", "MountingHole_4.3mm_M4_Pad_Via"),
    "M3": ("MountingHole", "MountingHole_3.2mm_M3"), "TP": ("TestPoint", "TestPoint_THTPad_D2.0mm_Drill1.0mm"),
}

def two(a, b): return {"1": a, "2": b}

# ------------------------------------------------------------------------------------------------ netlist
# (ref, footprint key, value, {pad: net}); TO-220: 1 G 2 D 3 S (7805: 1 IN 2 GND 3 OUT); TO-92: 2N390x 1 E 2 B 3 C,
# 2N7000 1 S 2 G 3 D, BC327 1 C 2 B 3 E, TL431 1 REF 2 A 3 K; diodes and LEDs: 1 = cathode; PC817: 1 A 2 K 3 E 4 C
PARTS = []
def part(ref, fp, value, pads): PARTS.append((ref, fp, value, pads))

NFET = 4
for n in range(1, NFET + 1):                                     # power switch
    part(f"Q{n}", "FET", "IRFB3206", {"1": f"G{n}", "2": "VIN", "3": "VOUT"})
    part(f"RG{n}", "RH", "10", two(f"G{n}", "FG"))
    part(f"RS{n}", "R", "1M", two(f"G{n}", "VOUT"))
part("J1", "XT60M", "XT60 BATTERY IN", {"1": "GND", "2": "VIN"})
part("J2", "XT60F", "XT60 TO ESCs", {"1": "GND", "2": "VOUT"})
part("D1", "D201", "1.5KE33A", two("VIN", "GND"))
part("D2", "D201", "1.5KE33A", two("VOUT", "GND"))
part("RK1", "RH", "0R", two("VIN", "VIN_K"))                    # logic taps VIN here (7805, dividers)
part("RK2", "RH", "0R", two("VOUT", "SRC"))                     # gate-drive ground taps VOUT here
# pre-charge
part("Q5", "FET", "IRF9540N", {"1": "PCG", "2": "PCD", "3": "VIN"})
part("R1", "R", "47k", two("VIN", "PCG"))
part("D3", "D35", "BZX55C12", two("VIN", "PCG"))
part("R2", "R", "22k", two("PCG", "PCDN"))
part("Q6", "TO92", "2N7000", {"1": "GND", "2": "PCEN", "3": "PCDN"})
part("F1", "PTC", "RXEF050 (0.5 A, 72 V)", two("PCD", "PCF"))
part("R3", "R2W", "22 2W", two("PCF", "VOUT"))
part("R4", "R2W", "22 2W", two("PCF", "VOUT"))
# 5 V
part("D4", "D41", "1N4007", two("VR1", "VIN_K"))
part("R5", "R", "10", two("VR1", "VR2"))
part("C1", "CE6", "47u 50V", two("VR2", "GND"))
part("U1", "TO220H", "L7805CV", {"1": "VR2", "2": "GND", "3": "V5"})
part("C2", "CE5", "10u 25V", two("V5", "GND"))
# V5 / 2 reference
part("R6", "R", "10k", two("V5", "REF"))
part("R7", "R", "10k", two("REF", "GND"))
part("C8", "CD", "100n", two("REF", "GND"))
# sensors and arm chain
part("J3", "XH3", "HALL MODULE (KY-003: S + -)", {"1": "HALL", "2": "V5S", "3": "GND"})
part("J4", "XH2", "REED (MC-38)", two("RIN", "ROUT"))
part("R8", "R", "100", two("V5", "V5S"))
part("R9", "R", "100", two("V5", "RIN"))
part("Q7", "TO92", "2N3906", {"1": "ROUT", "2": "QAB", "3": "ARM"})
part("R10", "R", "10k", two("QAB", "HALL"))
part("R11", "R", "47k", two("ROUT", "QAB"))
part("R12", "R", "4.7k", two("ARM", "GND"))
part("D7", "LED", "blue HALL", two("HALL", "HLA"))
part("R13", "R", "1k", two("V5S", "HLA"))
part("D8", "LED", "blue REED", two("GND", "RLA"))
part("R14", "R", "1k", two("ROUT", "RLA"))
part("R15", "R", "100k", two("ARM", "EN"))
part("C7", "CE5", "10u 16V", two("EN", "GND"))
part("Q8", "TO92", "2N3904", {"1": "GND", "2": "QIB", "3": "NARM"})
part("R16", "R", "10k", two("ARM", "QIB"))
part("R17", "R", "10k", two("V5", "NARM"))
part("Q9", "TO92", "2N3904", {"1": "GND", "2": "QDB", "3": "QDC"})
part("R18", "R", "10k", two("NARM", "QDB"))
part("R19", "R", "100k", two("QDB", "GND"))
part("R20", "R", "220", two("QDC", "EN"))
# pre-charge sequencing: one LM339
part("U2", "DIP14", "LM339N", {"1": "PCEN", "2": "PCEN", "3": "V5", "4": "REF", "5": "EN", "6": "RAMP", "7": "VOD",
                               "8": "VIND", "9": "VOD", "10": "REF", "11": "EN", "12": "GND", "13": "RRST", "14": "DONE"})
part("C3", "CD", "100n", two("V5", "GND"))
part("R21", "R", "75k 1%", two("SRC", "VOD"))
part("R22", "R", "10k 1%", two("VOD", "GND"))
part("R23", "R", "470k", two("V5", "VOD"))
part("C9", "CD", "10n", two("VOD", "GND"))
part("R24", "R", "160k 1%", two("VIN_K", "VIND"))
part("R25", "R", "10k 1%", two("VIND", "GND"))
part("C10", "CD", "10n", two("VIND", "GND"))
part("R26", "R", "1M", two("VIN_K", "RAMP"))
part("R27", "R", "68k", two("RAMP", "GND"))
part("C11", "CD", "3.3u X7R 50V", two("RAMP", "GND"))
part("R28", "R", "1k", two("RAMP", "RRST"))
part("R29", "R", "10k", two("V5", "PCEN"))
part("R30", "R", "10k", two("V5", "DONE"))
# live: PCEN and DONE both high -> gate-drive opto and the red LED
part("Q10", "TO92", "2N7000", {"1": "GND", "2": "PCEN", "3": "QGM"})
part("Q11", "TO92", "2N7000", {"1": "QGM", "2": "DONE", "3": "CATH"})
part("D9", "LED", "red LIVE", two("CATH", "LVA"))
part("R31", "R", "1k", two("V5", "LVA"))
part("U4", "DIP4", "PC817", {"1": "UGA", "2": "CATH", "3": "DRV", "4": "V12F"})
part("R32", "R", "330", two("V5", "UGA"))
# floating gate drive (ground = VOUT)
part("U3", "SIP4", "B0512S-1WR3", {"1": "GND", "2": "V5", "3": "SRC", "4": "V12F"})
part("C4", "CE5", "10u 16V", two("V5", "GND"))
part("C5", "CE5", "22u 25V", two("V12F", "SRC"))
part("D5", "D41", "1N4744A", two("V12F", "SRC"))
part("R33", "R", "4.7k", two("V12F", "SRC"))
part("R34", "R", "22k", two("DRV", "SRC"))
part("D10", "D35", "1N4148", two("DRVD", "DRV"))              # steering: lets DRV fall to VOUT when the opto lets go
part("R35", "R", "10k", two("DRVD", "FG"))
part("C6", "CF", "220n 100V film", two("FGC", "GND"))         # soft start: VOUT ramps ~9 V/ms, no VIN step coupling
part("R39", "R", "100", two("FGC", "FG"))                       # lets FG follow a sudden VOUT drop (short) instead of C6 holding it up
part("D11", "DO15", "P6KE18A", two("FG", "SRC"))              # gate-source clamp: C6 holds FG up when a short drops VOUT
part("Q12", "TO92", "BC327", {"1": "QOC", "2": "QOB", "3": "FG"})
part("R36", "R", "47", two("QOC", "SRC"))
part("R37", "R", "10k", two("FG", "QOB"))
part("D6", "D35", "1N4148", two("QOD", "QOB"))
part("R38", "R", "1k", two("QOD", "DRV"))
for i, net in enumerate(("FG", "EN", "V5", "GND"), 1):
    part(f"TP{i}", "TP", net, {"1": net})

# ------------------------------------------------------------------------------------------------ placement
ROW_Y = 13.97                                     # MOSFET pin row; tabs face the top edge
FET_X = [34.29 + 12.7 * i for i in range(NFET)]   # pin 1 of each MOSFET (pitch 12.7 mm = 5 holes)
FIXED = {}
for i, x in enumerate(FET_X, 1):
    FIXED[f"Q{i}"] = (x, ROW_Y, 0)
    FIXED[f"RG{i}"] = (x, ROW_Y + 3.81, 270)                    # gate pin -> 10 Ohm -> gate bus (bus on B.Cu at y 25.4)
    FIXED[f"RS{i}"] = (x + 2 * G, ROW_Y + 3.81, 270)            # 1 MOhm gate -> source, under the source pin
FIXED.update({
    "J1": (8.89, 13.97, 90), "J2": (111.76, 26.67, 270),          # XT60s overhang the left and right edges; + pin on top
    "Q5": (19.05, ROW_Y, 0), "R1": (20.32, 3.81, 270), "D3": (15.24, 3.81, 270),
    "F1": (19.05, 18.42, 180), "R3": (8.89, 22.86, 0), "R4": (8.89, 27.94, 0),
    "R2": (19.05, 34.29, 0), "Q6": (11.43, 34.29, 0),
    "D1": (40.64, 3.81, 0), "D2": (88.9, 27.94, 0),
    "RK1": (29.21, 2.54, 270), "RK2": (30.48, 22.86, 270), "TP1": (82.55, 25.4, 0),
    "U1": (86.36, 45.72, 90),
})
# the rest is packed in rows inside regions, group by group, pin 1 on the 2.54 mm grid
REGIONS = [
    ("float", (2.0, 37.0, 58.0, 60.0), ["U3", "C4", "C5", "D5", "R33", "U4", "R34", "D10", "R35", "C6", "R39", "D11", "Q12", "R36", "R37", "D6", "R38", "R32"]),
    ("supply", (60.0, 37.0, 118.0, 58.0), ["D4", "R5", "C1", "C2", "R6", "R7", "C8", "TP3", "TP4"]),
    ("logic", (60.0, 59.0, 118.0, 100.0), ["U2", "C3", "R21", "R22", "R23", "C9", "R24", "R25", "C10", "R26", "R27", "C11", "R28",
                                          "R29", "R30", "Q10", "Q11", "R31"]),
    ("arm", (2.0, 60.0, 58.0, 100.0), ["Q7", "R8", "R9", "R10", "R11", "R12", "R13", "R14", "R15", "C7", "Q8", "R16", "R17", "Q9", "R18",
                                       "R19", "R20", "TP2"]),
]
HOLES = ((4.0, H - 4.0), (W - 4.0, H - 4.0), (W - 4.0, 36.0), (4.0, 36.0))
EDGE_H = 9.0                                      # bottom strip kept for the connectors and LEDs
EDGE_ROW = [("J3", 0), ("J4", 0), ("D7", 0), ("D8", 0), ("D9", 0)]   # bottom edge, left to right

def courtyard(b, lib, name, rot):
    fp = pcbnew.FootprintLoad("/usr/share/kicad/footprints/" + lib + ".pretty", name)
    fp.SetPosition(pcbnew.VECTOR2I(0, 0)); fp.SetOrientationDegrees(rot)
    xs, ys = [], []
    for g in fp.GraphicalItems():
        if g.GetLayer() == pcbnew.F_CrtYd:
            bb = g.GetBoundingBox(); xs += [bb.GetLeft(), bb.GetRight()]; ys += [bb.GetTop(), bb.GetBottom()]
    if not xs:
        for p in fp.Pads():
            bb = p.GetBoundingBox(); xs += [bb.GetLeft(), bb.GetRight()]; ys += [bb.GetTop(), bb.GetBottom()]
        pad = 0.5
    else: pad = 0.0
    return (pcbnew.ToMM(min(xs)) - pad, pcbnew.ToMM(min(ys)) - pad, pcbnew.ToMM(max(xs)) + pad, pcbnew.ToMM(max(ys)) + pad)

def pack(b, pos):
    """Shelf-pack each region's parts left to right, row by row; pin 1 snapped to the 2.54 mm grid. Regions that
    share a column (same x range) are stacked: each starts 1 mm below where the previous one ended."""
    by_ref = {p[0]: p for p in PARTS}
    col_end = {}
    obst = []
    def box_at(ref, x, y, rot):
        lib, fpn = F[by_ref[ref][1]]; cl, ct, cr, cb = courtyard(b, lib, fpn, rot); return (x + cl, y + ct, x + cr, y + cb)
    for ref, (x, y, rot) in pos.items(): obst.append(box_at(ref, x, y, rot))
    for (hx, hy) in HOLES: obst.append((hx - 3.6, hy - 3.6, hx + 3.6, hy + 3.6))
    obst.append((0.0, H - EDGE_H, 80.0, H)); obst.append((0.0, H - 3.0, W, H))
    hit = lambda bx: any(bx[0] < o[2] and o[0] < bx[2] and bx[1] < o[3] and o[1] < bx[3] for o in obst)
    for name, (x0, y0, x1, y1), refs in REGIONS:
        y0 = max(y0, col_end.get((x0, x1), y0))
        x, y, row_h = x0, y0, 0.0
        items = []
        for k, ref in enumerate(refs):
            if ref in pos: continue
            lib, fpn = F[by_ref[ref][1]]
            items.append((ref, courtyard(b, lib, fpn, 0), k))
        items.sort(key=lambda it: (-round(it[1][3] - it[1][1], 0), it[2]))       # next-fit decreasing height
        for ref, (cl, ct, cr, cb), _ in items:
            rot = 0
            w, h = cr - cl, cb - ct
            while True:
                if x + w > x1:
                    x, y, row_h = x0, y + max(row_h, 1.0) + 0.6, 0.0
                px = round((x - cl) / G) * G
                if px + cl < x - 0.01: px += G
                py = round((y - ct) / G) * G
                if py + ct < y - 0.01: py += G
                bx = (px + cl - 0.3, py + ct - 0.3, px + cr + 0.3, py + cb + 0.3)
                if not hit(bx): break
                x += G
                if y > H: raise SystemExit("board full at " + ref)
            pos[ref] = (px, py, rot); obst.append(bx)
            x = px + cr + 0.6
            row_h = max(row_h, py + cb - y)
        col_end[(x0, x1)] = y + row_h + 1.0
        print(f"  region {name}: y {y0:.1f}-{y + row_h:.1f} (limit {y1})")
    # LEDs and connectors along the bottom edge
    x = 10.0
    for ref, rot in EDGE_ROW:
        lib, fpn = F[by_ref[ref][1]]
        cl, ct, cr, cb = courtyard(b, lib, fpn, rot)
        px = round((x - cl) / G) * G; pos[ref] = (px, round((H - 3.0 - cb) / G) * G, rot); x = px + cr + 2.0

def tht_board():
    B = Board(os.path.join(HERE, "ks_tht.kicad_pcb"))
    b = B.b
    B.rules(clearance=0.4, track=0.35)
    ds = b.GetDesignSettings()
    ds.SetCopperLayerCount(2)
    for x0, y0, x1, y1 in ((0, 0, W, 0), (W, 0, W, H), (W, H, 0, H), (0, H, 0, 0)):
        B.line(x0, y0, x1, y1, pcbnew.Edge_Cuts, 0.1)
    pos = dict(FIXED)
    pack(b, pos)
    for ref, fp, value, pads in PARTS:
        x, y, rot = pos[ref]
        lib, name = F[fp]
        B.place(ref, lib, name, x, y, rot, value, pads)
    for i, (x, y) in enumerate(HOLES, 1):
        B.place(f"H{i}", "MountingHole", "MountingHole_3.2mm_M3", x, y, 0, "M3 nylon", {}, hide_ref=True)
    # silkscreen
    B.text("MAGNETIC KILL SWITCH", 64.0, 31.0, 1.8, bold=True)
    B.text("4S-6S LiPo   30 A cont / 60 A burst   magnet in = ESCs live", 64.0, 34.2, 0.9)
    B.text("BATTERY", 3.0, 25.4, 1.1, rot=90, bold=True)
    B.text("ESCs", 117.8, 12.0, 1.1, rot=90, bold=True)
    B.text("4 x IRFB3206", 55.0, 9.0, 0.9)
    B.text("GATE DRIVE (ground = VOUT)", 40.0, 36.0, 0.8)
    return B, pos

if __name__ == "__main__":
    B, pos = tht_board()
    auto_refs(B, (0, 0, W, H))
    B.save(os.path.join(HERE, "bom_tht.csv"))
    open(os.path.join(HERE, "ks_tht.kicad_dru"), "w").write('(version 1)\n(rule "plane_spokes" (constraint min_resolved_spokes 1))\n')
