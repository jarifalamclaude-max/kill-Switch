"""Veroboard (dot perfboard) data for index.html, generated from the through-hole kill switch board
../kicad/ks_tht.kicad_pcb, so the hand-wiring plan has exactly the PCB's connections.

Every part is through-hole, so each footprint is snapped to the 2.54 mm hole grid: pin 1 to the nearest hole
(half-hole positions round up), the other pins by their own pitch rounded to whole holes. Collisions are reported.
The two XT60 board connectors do not fit a 2.54 mm grid: they become XT60 pigtails (12 AWG) whose wires are
soldered to the bare 12 AWG runs that carry VIN, VOUT and GND (the HEAVY pads below). The page routes those
runs on the hole grid itself, so they follow the spacing slider.

Run with KiCad 7's python:  /usr/bin/python3 make_vero_data.py   (rewrites the data block in index.html)
"""
import csv, json, math, os
import pcbnew

HERE = os.path.dirname(os.path.abspath(__file__))
KICAD = os.path.join(HERE, "..", "kicad")
PCB = os.path.join(KICAD, "ks_tht.kicad_pcb")
BOM = os.path.join(KICAD, "bom_tht_grouped.csv")
HTML = os.path.join(HERE, "index.html")
OX = OY = 100.0
G = 2.54
NUDGE = {}          # ref -> (dcol, drow) manual moves where snapping collides (none needed so far)

NETS = {
 # main current path: bare 12 AWG runs
 "VIN": ("#d32f2f", "Battery + from the battery-side XT60 pigtail (J1): drains and tabs of Q1–Q4, source of the pre-charge FET Q5"),
 "VOUT": ("#ef6c00", "Switched + to the ESCs (J2 pigtail): sources of Q1–Q4, pre-charge resistors, TVS D2"),
 "GND": ("#111111", "Battery minus: J1 to J2 through the board, and the ground of all the logic"),
 "VIN_K": ("#e57373", "VIN for the logic, through the 0 Ω link RK1: 7805 input diode, VIN divider and ramp"),
 "SRC": ("#ffa726", "VOUT for the gate drive, through the 0 Ω link RK2: 0 V of the floating 12 V supply, VOUT divider"),
 # gates
 "G1": ("#7b1fa2", "Q1 gate (after its 10 Ω resistor RG1; RS1 1 MΩ to the source)"),
 "G2": ("#8e24aa", "Q2 gate (RG2 10 Ω, RS2 1 MΩ)"), "G3": ("#9c27b0", "Q3 gate (RG3 10 Ω, RS3 1 MΩ)"),
 "G4": ("#ab47bc", "Q4 gate (RG4 10 Ω, RS4 1 MΩ)"),
 "FG": ("#6a1b9a", "Gate bus: drives Q1–Q4 through RG1–RG4; R39 and C6 to GND give the soft start"),
 "FGC": ("#9575cd", "Soft-start capacitor C6 (220 nF film to GND), joined to the gate bus through R39 100 Ω"),
 # pre-charge
 "PCG": ("#00838f", "Pre-charge P-FET Q5 gate: R1 47 kΩ and the 12 V zener D3 to VIN"),
 "PCD": ("#00acc1", "Q5 drain to the PTC F1"), "PCF": ("#26c6da", "PTC F1 to the two 22 Ω 2 W resistors R3, R4"),
 "PCDN": ("#006064", "Q6 drain: pulls the Q5 gate down through R2 22 kΩ, which starts the pre-charge"),
 "PCEN": ("#2e7d32", "Pre-charge enable: LM339 outputs 1 and 2 (wired), pulled up by R29; drives Q6 and Q10"),
 # 5 V and reference
 "VR1": ("#b71c1c", "After the reverse-polarity diode D4"), "VR2": ("#c62828", "7805 input, after R5 10 Ω and C1 47 µF"),
 "V5": ("#e53935", "5 V logic supply from the 7805 (U1)"), "REF": ("#f06292", "2.5 V reference: V5 halved by R6 / R7"),
 # sensors and arm chain
 "HALL": ("#1e88e5", "KY-003 output S: low while the magnet is in"), "V5S": ("#42a5f5", "5 V for the Hall module, through R8 100 Ω"),
 "RIN": ("#0277bd", "Reed contact input: V5 through R9 100 Ω"), "ROUT": ("#0288d1", "Reed contact output: 5 V while the magnet holds the reed closed"),
 "QAB": ("#64b5f6", "Q7 base: pulled down to HALL through R10, up to ROUT through R11"),
 "ARM": ("#1565c0", "Armed: Q7 passes ROUT only while the Hall sensor also sees the magnet"),
 "HLA": ("#90caf9", "HALL LED (D7) anode"), "RLA": ("#81d4fa", "REED LED (D8) anode"),
 "EN": ("#00897b", "Arm delay: ARM charges it through R15 100 kΩ into C7 10 µF (about 0.8 s); Q9 empties it in about 1.5 ms"),
 "QIB": ("#4db6ac", "Q8 base (from ARM through R16)"), "NARM": ("#283593", "Not armed: Q8 collector, high when ARM is low"),
 "QDB": ("#5c6bc0", "Q9 base (from NARM through R18)"), "QDC": ("#3949ab", "Q9 collector, to EN through R20 220 Ω"),
 # LM339 sequencing
 "RAMP": ("#558b2f", "Abort ramp: VIN_K through R26 1 MΩ into C11 3.3 µF, reset through R28 while EN is low"),
 "VOD": ("#827717", "VOUT divider: SRC / 8.5 (R21 / R22) plus a small offset from R23"),
 "VIND": ("#9e9d24", "VIN divider: VIN_K / 17 (R24 / R25)"),
 "RRST": ("#33691e", "LM339 output 4: empties the ramp through R28 while EN is below 2.5 V"),
 "DONE": ("#43a047", "LM339 output 3: high when VOUT is above half of VIN (pre-charge finished)"),
 # live: opto and LED
 "QGM": ("#795548", "Between Q10 and Q11 (the two 2N7000 in series form an AND gate)"),
 "CATH": ("#6d4c41", "Cathodes of the LIVE LED and of the gate-drive opto LED: pulled low when PCEN and DONE are both high"),
 "LVA": ("#ff5252", "LIVE LED (D9) anode"), "UGA": ("#ad1457", "Gate-drive opto U4 LED anode (V5 through R32 330 Ω)"),
 # floating gate drive
 "V12F": ("#c2185b", "Floating +12 V from the B0512S (U3), measured from SRC"),
 "DRV": ("#d81b60", "Opto U4 emitter: the gate-drive output (R34 22 kΩ to SRC)"),
 "DRVD": ("#ec407a", "After the steering diode D10, into R35 10 kΩ to the gate bus"),
 "QOB": ("#4527a0", "Q12 base: fast turn-off PNP (R37 10 kΩ to FG, D6 and R38 to DRV)"),
 "QOC": ("#5e35b1", "Q12 collector, to SRC through R36 47 Ω"), "QOD": ("#7e57c2", "D6 cathode to R38 1 kΩ"),
}
# pads on the 30-60 A path: joined by bare 12 AWG copper runs (routed on the grid by the page)
HEAVY = {"VIN": ["J1.+", "Q1.D", "Q2.D", "Q3.D", "Q4.D"],
         "VOUT": ["Q1.S", "Q2.S", "Q3.S", "Q4.S", "J2.+"],
         "GND": ["J1.-", "J2.-"]}
# pads that see amps for a short time (TVS clamps, pre-charge path): 0.5 mm2 / 20 AWG insulated wire
MID = ["D1.K", "D1.A", "D2.K", "D2.A", "Q5.S", "Q5.D", "F1.1", "F1.2", "R3.1", "R3.2", "R4.1", "R4.2"]

def kind_and_names(ref, fp, pads):
    if fp.startswith("R_Axial") and fp.endswith("_Vertical"): return "rv", {"1": "1", "2": "2"}
    if fp.startswith("R_Axial_DIN0414"): return "ax2", {"1": "1", "2": "2"}
    if fp.startswith("R_Axial"): return "ax", {"1": "1", "2": "2"}
    if fp.startswith("C_Disc"): return "cd", {"1": "1", "2": "2"}
    if fp.startswith("C_Rect"): return "cf", {"1": "1", "2": "2"}
    if fp.startswith("CP_Radial"): return "elec", {"1": "+", "2": "-"}
    if fp.startswith("D_DO-35") and "Vertical" in fp: return "dv", {"1": "K", "2": "A"}
    if fp.startswith("D_DO-201"): return "dio2", {"1": "K", "2": "A"}
    if fp.startswith("D_"): return "dio", {"1": "K", "2": "A"}
    if fp.startswith("LED"): return "led", {"1": "K", "2": "A"}
    if fp.startswith("Fuse"): return "ptc", {"1": "1", "2": "2"}
    if fp.startswith("TO-220-3_Horizontal"): return "to220h", {"1": "IN", "2": "GND", "3": "OUT"}
    if fp.startswith("TO-220"): return "to220", {"1": "G", "2": "D", "3": "S"}
    if fp.startswith("TO-92"):
        names = {"2N7000": "SGD", "2N3904": "EBC", "2N3906": "EBC", "BC327": "CBE"}[pads["__val"]]
        return "to92", {str(i + 1): c for i, c in enumerate(names)}
    if fp.startswith("DIP"): return "dip", {str(i): str(i) for i in range(1, 15)}
    if fp.startswith("PinHeader_1x04"): return "sip", {"1": "GND", "2": "Vin", "3": "0V", "4": "+Vo"}
    if fp.startswith("JST_XH_B3B"): return "xh", {"1": "S", "2": "+", "3": "-"}
    if fp.startswith("JST_XH_B2B"): return "xh", {"1": "1", "2": "2"}
    if fp.startswith("AMASS_XT60"): return "xt60", {"1": "-", "2": "+"}
    if fp.startswith("TestPoint"): return "tp", {"1": "1"}
    raise SystemExit("no veroboard kind for " + ref + " " + fp)

VALUE = {   # value text on the plan (the PCB value, made clearer where the part differs on perfboard)
    "J1": "XT60 male pigtail, 12 AWG (to battery)", "J2": "XT60 female pigtail, 12 AWG (to ESCs)",
    "U3": "B0512S-1WR3", "U1": "L7805CV", "U2": "LM339N", "U4": "PC817", "F1": "RXEF050 PTC",
    "J3": "KY-003 (S + -)", "J4": "MC-38 reed",
}

def rnd(v): return int(math.floor(v + 0.5 + 1e-6))      # half-hole positions round up (float-safe)

def main():
    b = pcbnew.LoadBoard(PCB)
    buy = {}
    for row in csv.DictReader(open(BOM)):
        for r in row["refs"].split(): buy[r] = row["buy"]
    parts, occupied, pcbnet = [], {}, {}
    for fp in sorted(b.GetFootprints(), key=lambda f: f.GetReference()):
        ref = fp.GetReference(); name = fp.GetFPID().GetLibItemName().wx_str()
        if ref.startswith("H"): continue                          # PCB mounting holes
        pads, pos = {}, {}
        for p in fp.Pads():
            n = p.GetNumber()
            if not n or n in pos: continue                       # skip XT60 pegs and the 7805 tab hole
            pos[n] = ((pcbnew.ToMM(p.GetPosition().x) - OX) / G, (pcbnew.ToMM(p.GetPosition().y) - OY) / G)
            pads[n] = p.GetNetname()
        pcbnet[ref] = {"val": fp.GetValue(), "pads": pads}
        dc, dr = NUDGE.get(ref, (0, 0))
        first = sorted(pos, key=int)[0]; x1, y1 = pos[first]
        c1, r1 = rnd(x1) + dc, rnd(y1) + dr
        cell = {}
        for n, (x, y) in pos.items():
            ddx, ddy = rnd(x - x1), rnd(y - y1)
            if n != first and ddx == 0 and ddy == 0:
                if abs(x - x1) >= abs(y - y1): ddx = 1 if x > x1 else -1
                else: ddy = 1 if y > y1 else -1
            cell[n] = (c1 + ddx, r1 + ddy)
        k, names = kind_and_names(ref, name, dict(pads, __val=fp.GetValue()))
        pins = []
        for n in sorted(cell, key=int):
            c, r = cell[n]
            pins.append([names[n], c, r, pads[n] or None])
            occupied.setdefault((c, r), []).append(f"{ref}.{n}")
        part = {"ref": ref, "val": VALUE.get(ref, fp.GetValue()), "k": k, "p": pins, "buy": buy.get(ref, "")}
        if k == "to220h":                                         # where the tab lies: away from the pins, toward the tab hole
            tab = [p for p in fp.Pads() if not p.GetNumber()][0]
            tx, ty = (pcbnew.ToMM(tab.GetPosition().x) - OX) / G, (pcbnew.ToMM(tab.GetPosition().y) - OY) / G
            part["tab"] = [round(tx - pos["2"][0]), round(ty - pos["2"][1])]
        parts.append(part)
    clashes = {k: v for k, v in occupied.items() if len(v) > 1}
    # every PCB pad must sit on its own hole with its PCB net
    for pt in parts:
        for name, c, r, net in pt["p"]:
            assert net is None or net in NETS, (pt["ref"], name, net)
    nets = {n for pt in parts for q in pt["p"] for n in [q[3]] if n}
    pcb_nets = {n for v in pcbnet.values() for n in v["pads"].values() if n}
    assert nets == pcb_nets, (nets ^ pcb_nets)
    for net, ids in list(HEAVY.items()) + [("", MID)]:
        for i in ids:
            ref, pin = i.split(".")
            assert any(q[0] == pin for pt in parts if pt["ref"] == ref for q in pt["p"]), i
    cols = max(q[1] for pt in parts for q in pt["p"]) + 2
    rows = max(q[2] for pt in parts for q in pt["p"]) + 2
    return parts, clashes, cols, rows, pcbnet, nets

if __name__ == "__main__":
    parts, clashes, cols, rows, pcbnet, nets = main()
    if clashes: raise SystemExit("hole collisions: " + "; ".join(f"{k}: {v}" for k, v in sorted(clashes.items())))
    unused = sorted(set(NETS) - nets)
    if unused: raise SystemExit("colours for nets that are not on the board: " + ", ".join(unused))
    js = ("/* ---------- generated by make_vero_data.py from ../kicad/ks_tht.kicad_pcb ---------- */\n"
          f"const NETS={json.dumps({k: {'c': c, 'd': d} for k, (c, d) in NETS.items()}, ensure_ascii=False)};\n"
          f"const HEAVY={json.dumps(HEAVY)};\n"
          f"const MID=new Set({json.dumps(MID)});\n"
          f"const BASE_PARTS={json.dumps(parts, ensure_ascii=False)};\n"
          f"const BASE_COLS={cols}, BASE_ROWS={rows}, P=20, OFF=34;\n"
          f"const PCBNET={json.dumps(pcbnet, ensure_ascii=False)};\n"
          "/* ---------- end generated ---------- */\n")
    t = open(HTML).read()
    s = t.index("/* ---------- generated"); e = t.index("/* ---------- end generated ---------- */\n") + len("/* ---------- end generated ---------- */\n")
    open(HTML, "w").write(t[:s] + js + t[e:])
    n_pins = sum(len(p["p"]) for p in parts)
    print(f"{len(parts)} parts ({n_pins} pins, {len(nets)} nets), board {cols} x {rows} holes "
          f"({cols * G / 10:.1f} x {rows * G / 10:.1f} cm), no collisions")
