"""Veroboard (dot perfboard) plan for the magnetic kill switch, generated from ../kicad/ks_power.kicad_pcb.

The PCB is SMD, so the pads cannot simply be snapped to the 2.54 mm grid. Instead every control-circuit footprint is
mapped to a through-hole part (pin names checked against the PCB pad numbers) and placed on the hole grid by a small
skyline packer, group by group. Nets come from the PCB, so the hand wiring has exactly the PCB's connections.

Everything that carries more than ~0.5 A (8 main MOSFETs, gate resistors, TVS, bulk caps, pre-charge FET/PTC/resistors)
is NOT on the perfboard: it is built on copper bus bars (see the Power stage tab). Five thin wires join the two.

The TO-220 MOSFETs of that build have several times the PCB's on-resistance, so the LM5060 SENSE resistor (R1) and the
heat are recomputed here with the same model as calc/design_calc.py.

Run with KiCad 7's python:  /usr/bin/python3 make_vero_data.py   (rewrites the data block in index.html,
writes bus_bar_calc.json and checks: no hole collisions, every PCB net of every perfboard part present).
"""
import json, math, os, sys
import pcbnew

HERE = os.path.dirname(os.path.abspath(__file__))
PCB = os.path.join(HERE, "..", "kicad", "ks_power.kicad_pcb")
HTML = os.path.join(HERE, "index.html")
OX = OY = 100.0

# ------------------------------------------------------------------ which footprint goes where
POWER = {f"Q{i}" for i in range(1, 10)} | {f"RG{i}" for i in range(1, 9)} | {"D1", "D2", "D4", "C1", "C2", "C3", "F1",
         "R8", "R9", "R12", "R13", "RK1", "RK2", "J1", "J2", "J3"}
SKIP = {"H1", "H2", "H3", "H4"}                 # PCB mounting holes
HARNESS = ["VIN_K", "VOUT_K", "FG", "GND", "PDRV"]   # the only nets shared by perfboard and bus-bar stage

# ------------------------------------------------------------------ TO-220 bus-bar build: SENSE resistor and heat
E96 = [1.00, 1.02, 1.05, 1.07, 1.10, 1.13, 1.15, 1.18, 1.21, 1.24, 1.27, 1.30, 1.33, 1.37, 1.40, 1.43, 1.47, 1.50, 1.54, 1.58,
       1.62, 1.65, 1.69, 1.74, 1.78, 1.82, 1.87, 1.91, 1.96, 2.00, 2.05, 2.10, 2.15, 2.21, 2.26, 2.32, 2.37, 2.43, 2.49, 2.55,
       2.61, 2.67, 2.74, 2.80, 2.87, 2.94, 3.01, 3.09, 3.16, 3.24, 3.32, 3.40, 3.48, 3.57, 3.65, 3.74, 3.83, 3.92, 4.02, 4.12,
       4.22, 4.32, 4.42, 4.53, 4.64, 4.75, 4.87, 4.99, 5.11, 5.23, 5.36, 5.49, 5.62, 5.76, 5.90, 6.04, 6.19, 6.34, 6.49, 6.65,
       6.81, 6.98, 7.15, 7.32, 7.50, 7.68, 7.87, 8.06, 8.25, 8.45, 8.66, 8.87, 9.09, 9.31, 9.53, 9.76]

def e96_at_least(v):
    dec = 10 ** math.floor(math.log10(v))
    for m in E96 + [10.0]:
        if m * dec >= v * (1 - 1e-9): return m * dec

def bus_bar_build():
    calc = json.load(open(os.path.join(HERE, "..", "calc", "results.json")))
    lm_pcb, th_pcb = calc["lm5060"], calc["thermal"]
    n = 8
    fet = dict(name="IRFB3206PbF (TO-220)", rds25_max=3.0e-3, rds25_typ=2.4e-3, tc=0.0067, rth_jc=0.45, rth_cs=0.5,
               qg_max=170e-9, note="Rds(on) 3.0 mOhm max / 2.4 typ at VGS 10 V, RthJC 0.45 K/W, Qg 170 nC max: verify with the datasheet")
    i_sense = (13.6e-6, 16e-6, 18.0e-6)          # LM5060 SENSE current min/typ/max, same as calc/design_calc.py
    r_leg = 0.2e-3                                # source leg past the datasheet's measuring point + solder joint (estimate)
    rho = 1.72e-8
    bar_vin = dict(w=20e-3, t=3e-3, L=0.12)       # copper flat bar, MOSFET tabs bolted on
    bar_out = dict(w=10e-3, t=3e-3, L=0.12)       # copper flat bar under the source legs
    r_bar = lambda b: rho * b["L"] / (b["w"] * b["t"])
    # diagonal feed (battery at one end of the VIN bar, ESCs at the far end of the VOUT bar): every MOSFET sees the same
    # copper; the Kelvin taps sit in the middle of each bar, so about a quarter of each bar lies between them
    r_sense_bar = 0.25 * (r_bar(bar_vin) + r_bar(bar_out))
    rds = lambda T: fet["rds25_max"] * (1 + fet["tc"] * (T - 25))
    r_hot = (rds(100) + r_leg) / n + r_sense_bar                     # same 100 C assumption as the PCB calc
    r_cold_typ = (fet["rds25_typ"] + r_leg) / n + r_sense_bar
    margin = 2.5
    r_s_min = margin * 150.0 * r_hot / i_sense[0]
    R_s = e96_at_least(r_s_min)
    vds_trip = [i * R_s for i in i_sense]
    out = {"fet": fet, "n": n, "r_leg_mohm": r_leg * 1e3, "r_sense_bar_mohm": r_sense_bar * 1e3,
           "bank_hot_mohm": r_hot * 1e3, "bank_cold_typ_mohm": r_cold_typ * 1e3,
           "R_sense_min_ohm": r_s_min, "R_sense_ohm": R_s, "R_sense_pcb_ohm": lm_pcb["R_sense_ohm"],
           "vds_trip_mV": [v * 1e3 for v in vds_trip],
           "trip_A_hot_min": vds_trip[0] / r_hot, "trip_A_cold_typ": vds_trip[1] / r_cold_typ, "trip_A_cold_max": vds_trip[2] / r_cold_typ,
           "burst_vds_hot_mV": 150.0 * r_hot * 1e3,
           "pcb_trip_A_hot_min": lm_pcb["trip_current_A_hot_max"], "pcb_burst_vds_hot_mV": lm_pcb["burst_vds_hot_mV"],
           "if_pcb_R_kept_trip_A_hot_min": lm_pcb["vds_trip_mV"][0] * 1e-3 / r_hot}
    # heat: bar at 60 C (worst, like the PCB calc), 20 % current-sharing imbalance, junction -> bar = RthJC + greased tab
    r_lugs = 2 * 0.03e-3
    r_bars_path = 0.5 * (r_bar(bar_vin) + r_bar(bar_out))
    for label, I in (("cont_100A", 100.0), ("burst_150A", 150.0)):
        T = 60.0
        for _ in range(30):
            r_bank = (rds(T) + r_leg) / n
            p_fets = I * I * r_bank
            p_each = p_fets / n * 1.2
            T = 60.0 + p_each * (fet["rth_jc"] + fet["rth_cs"])
        p_cu = I * I * (r_bars_path + r_lugs)
        out[label] = {"p_fets_W": p_fets, "p_per_fet_W": p_each, "tj_above_bar_K": T - 60.0, "p_bars_lugs_W": p_cu,
                      "p_total_W": p_fets + p_cu, "drop_mV": I * (r_bank + r_bars_path + r_lugs) * 1e3,
                      "pcb_p_fets_W": th_pcb[label]["p_fets_W"], "pcb_p_total_W": th_pcb[label]["p_total_W"]}
    m_bar = 8960 * bar_vin["w"] * bar_vin["t"] * bar_vin["L"] + 8960 * bar_out["w"] * bar_out["t"] * bar_out["L"]
    heat_cap = m_bar * 385.0
    out["bars"] = {"vin_bar_mm": "20 x 3 x 120", "vout_bar_mm": "10 x 3 x 120", "mass_g": m_bar * 1e3, "heat_capacity_J_per_K": heat_cap,
                   "rise_per_10s_burst_150A_K": out["burst_150A"]["p_total_W"] * 10.0 / heat_cap,
                   "still_air_K_per_W": 1 / (12.0 * 2 * (0.020 + 0.003 + 0.010 + 0.003) * 0.12),     # both bars, all faces, h = 12 W/m2K
                   "to_hull_K_per_W": 2.5}
    out["bars"]["rise_100A_still_air_K"] = out["cont_100A"]["p_total_W"] * out["bars"]["still_air_K_per_W"]
    out["bars"]["rise_100A_to_hull_K"] = out["cont_100A"]["p_total_W"] * out["bars"]["to_hull_K_per_W"]
    out["gate_charge_uC"] = n * fet["qg_max"] * 1e6 + 0.047 * 12
    out["pcb_gate_charge_uC"] = lm_pcb["gate_charge_uC"]
    return out

# ------------------------------------------------------------------ through-hole substitutes
# kind -> pin names in package order, pin offsets (col,row) from pin 1, occupied box (dc0, dc1, dr0, dr1) incl. label room
KIND = {
    "R":     (["1", "2"], [(0, 0), (4, 0)], (0, 4, -1, 0)),
    "C":     (["1", "2"], [(0, 0), (2, 0)], (0, 2, -1, 0)),
    "E":     (["+", "-"], [(0, 0), (2, 0)], (-1, 3, -2, 1)),
    "D":     (["K", "A"], [(0, 0), (4, 0)], (0, 4, -1, 0)),
    "LED":   (["K", "A"], [(0, 0), (1, 0)], (-1, 2, -1, 0)),
    "TO92":  (None,       [(0, 0), (1, 0), (2, 0)], (-1, 3, -2, 0)),
    "TO220": (["ADJ", "OUT", "IN"], [(0, 0), (1, 0), (2, 0)], (-1, 3, -2, 0)),
    "DIP4":  (["1", "2", "3", "4"], [(0, 0), (0, 1), (3, 1), (3, 0)], (0, 3, -1, 2)),
    "DIP14": ([str(i) for i in range(1, 15)], [(0, i) for i in range(7)] + [(3, 6 - i) for i in range(7)], (0, 3, -1, 7)),
    "DIP10A": ([str(i) for i in range(1, 11)], [(0, i) for i in range(5)] + [(3, 4 - i) for i in range(5)], (-3, 7, -2, 5)),
    "XH3":   (None, [(0, 0), (1, 0), (2, 0)], (-1, 3, -1, 2)),
    "XH2":   (None, [(0, 0), (1, 0)], (-1, 2, -1, 2)),
    "TP":    (["1"], [(0, 0)], (0, 1, -1, 0)),
    "TERM":  (HARNESS, [(0, i) for i in range(5)], (-1, 4, -2, 4)),
}
# SOT-23 pad order on the PCB: MOSFET 1 G, 2 S, 3 D; BJT 1 B, 2 E, 3 C
TO92 = {"2N7000": (["S", "G", "D"], {"1": "G", "2": "S", "3": "D"}),
        "BS250":  (["D", "G", "S"], {"1": "G", "2": "S", "3": "D"}),
        "2N3906": (["E", "B", "C"], {"1": "B", "2": "E", "3": "C"})}

def substitute(ref, val, fpname):
    """-> (kind, th_value, pad->pin-name map, pin names in package order)"""
    if ref == "JH1": return "TERM", "Harness pads", {h: h for h in HARNESS}, HARNESS
    if fpname.startswith("R_"):
        v = val.replace(" 1%", "")
        return "R", v + (" 1% metal film" if "1%" in val else "") + ", 1/4 W", {"1": "1", "2": "2"}, ["1", "2"]
    if fpname.startswith("C_"):
        if ref in ("C9", "C12"):
            return "E", val.split()[0] + " 16 V electrolytic (+ to " + ("V5" if ref == "C9" else "EN") + ")", {"1": "+", "2": "-"}, ["+", "-"]
        v = {"C15": "3.3u X7R ceramic, 16 V+ (not electrolytic)", "C11": "2.2u X7R ceramic, 16 V+", "C8": "1u X7R ceramic, 50 V",
             "C6": "100n ceramic, 100 V", "C4": "47n X7R ceramic, 50 V", "C5": "470n X7R ceramic"}.get(ref, val.split()[0] + " ceramic")
        return "C", v, {"1": "1", "2": "2"}, ["1", "2"]
    if fpname.startswith("LED"):
        colour = val.split()[0]
        return "LED", f"3 mm {colour} LED ({val.split()[1]})", {"1": "K", "2": "A"}, ["K", "A"]
    if fpname.startswith("D_"):
        v = {"BZT52C15": "BZX55C15 (15 V zener)", "BZT52C6V2": "BZX55C6V2 (6.2 V zener)",
             "BAT54WS": "BAT46 (100 V Schottky)"}[val]
        return "D", v, {"1": "K", "2": "A"}, ["K", "A"]
    if fpname.startswith("SOT-23") and not fpname.startswith("SOT-223"):
        th = {"2N7002": "2N7000", "BSS84": "BS250", "MMBT3906": "2N3906"}[val]
        names, padmap = TO92[th]
        return "TO92", th, padmap, names
    if fpname.startswith("SOT-223"): return "TO220", "LM317T (TO-220)", {"1": "ADJ", "2": "OUT", "3": "IN"}, ["ADJ", "OUT", "IN"]
    if fpname.startswith("SMDIP-4"): return "DIP4", "PC817 " + ("(gate kill)" if ref == "U2" else "(status)"), {k: k for k in "1234"}, list("1234")
    if fpname.startswith("SOIC-14"): return "DIP14", "LM339N (DIP-14)", {str(i): str(i) for i in range(1, 15)}, [str(i) for i in range(1, 15)]
    if fpname.startswith("MSOP-10"): return "DIP10A", "LM5060 on MSOP-10 to DIP-10 adapter", {str(i): str(i) for i in range(1, 11)}, [str(i) for i in range(1, 11)]
    if fpname.startswith("JST_XH_B3B"): return "XH3", "JST XH 3-pin (KY-003: S + -)", {"1": "S", "2": "+", "3": "-"}, ["S", "+", "-"]
    if fpname.startswith("JST_XH_B2B"):
        if ref == "J5": return "XH2", "JST XH 2-pin (status to Jetson)", {"1": "C", "2": "E"}, ["C", "E"]
        return "XH2", "JST XH 2-pin (MC-38 reed)", {"1": "1", "2": "2"}, ["1", "2"]
    if fpname.startswith("TestPoint"): return "TP", "test pin " + val, {"1": "1"}, ["1"]
    raise SystemExit("no through-hole substitute for " + ref + " " + fpname)

# ------------------------------------------------------------------ placement: groups packed bottom-left, in this order
GROUPS = [
    # name, first column, first row, width (cols), parts in order (ICs first, then by signal flow)
    ("arm",    1, 1, 30, ["Q14", "R19", "R20", "R22", "C11", "R23", "R24", "Q15", "R25", "Q16", "R27", "R26", "C12", "Q10",
                          "R21", "R37", "R38", "Q18", "R36", "R39"]),
    ("lm5060", 33, 1, 27, ["U1", "R1", "C6", "R2", "R3", "C7", "R4", "R5", "C5", "R6", "D9", "R43", "Q11", "R44", "C4", "D3",
                           "U2", "R7", "Q12"]),
    ("supply", 1, None, 30, ["U3", "R14", "C8", "R15", "R16", "C9", "D5", "C17", "R18", "C16", "R17", "R41", "R42", "U5", "R40"]),
    ("lm339",  33, None, 27, ["U4", "R28", "R29", "R30", "C13", "R31", "R32", "C14", "R33", "R34", "C15", "Q17", "R45", "R46",
                              "R10", "R11", "Q13"]),
    ("front",  1, None, 59, ["J4", "J6", "D6", "D7", "D8", "LED1", "J5", "TP1", "TP2", "TP3", "TP4", "TP5", "TP6"]),
]

def pin_cells(kind, c, r):
    return [(c + dc, r + dr) for dc, dr in KIND[kind][1]]

def box_cells(kind, c, r):
    dc0, dc1, dr0, dr1 = KIND[kind][2]
    return {(c + x, r + y) for x in range(dc0, dc1 + 1) for y in range(dr0, dr1 + 1)}

def pack(parts, kinds):
    occ = set(); place = {}; bottoms = {}
    top_of = {}
    for gname, c0, r0, W, refs in GROUPS:
        if r0 is None:                                          # below the group(s) above it in the same columns
            r0 = max([b for (g, cc, ww), b in bottoms.items() if not (cc + ww <= c0 or c0 + W <= cc)] + [1]) + 1
        top_of[gname] = r0
        sky = {c: r0 for c in range(c0, c0 + W)}
        gap = 1
        for ref in refs:
            k = kinds[ref]; dc0, dc1, dr0, dr1 = KIND[k][2]
            w, h = dc1 - dc0 + 1, dr1 - dr0 + 1
            best = None
            for x in range(c0, c0 + W - w + 1):
                y = max(sky[c] for c in range(x, min(x + w + gap, c0 + W)))
                if best is None or (y, x) < best: best = (y, x)
            y, x = best
            c, r = x - dc0, y - dr0
            cells = box_cells(k, c, r)
            if cells & occ: raise SystemExit(f"overlap placing {ref}")
            occ |= cells; place[ref] = (c, r)
            for cc in range(x, min(x + w + gap, c0 + W)): sky[cc] = y + h + (1 if k in ("R", "C", "D", "TP") else 1)
        bottoms[(gname, c0, W)] = max(sky.values())
    return place, occ

def main():
    b = pcbnew.LoadBoard(PCB)
    pcb = {}
    for fp in b.GetFootprints():
        ref = fp.GetReference()
        pads = {}
        for p in fp.Pads():
            if p.GetNumber() and p.GetNumber() not in pads: pads[p.GetNumber()] = p.GetNetname()
        pcb[ref] = {"val": fp.GetValue(), "fp": fp.GetFPID().GetLibItemName().wx_str(), "pads": pads,
                    "pos": (round(pcbnew.ToMM(fp.GetPosition().x) - OX, 2), round(pcbnew.ToMM(fp.GetPosition().y) - OY, 2))}
    perf = sorted(r for r in pcb if r not in POWER and r not in SKIP)
    placed_refs = [r for g in GROUPS for r in g[4]]
    missing = set(perf) - set(placed_refs); extra = set(placed_refs) - set(perf)
    if missing or extra: raise SystemExit(f"group lists do not match the PCB: missing {sorted(missing)}, extra {sorted(extra)}")
    calc = bus_bar_build()
    subs, kinds = {}, {}
    for ref in perf:
        subs[ref] = substitute(ref, pcb[ref]["val"], pcb[ref]["fp"]); kinds[ref] = subs[ref][0]
    place, occ = pack(perf, kinds)
    # harness pads at the right edge, next to the LM5060 group
    maxc = max(c for c, _ in occ)
    jh = (maxc + 3, place["U1"][1])
    if box_cells("TERM", *jh) & occ: raise SystemExit("harness pads overlap")
    occ |= box_cells("TERM", *jh)
    parts, holes = [], {}
    for ref in perf + ["JH1"]:
        if ref == "JH1":
            k, val, padmap, names = substitute("JH1", "", ""); c, r = jh
            pads = {h: h for h in HARNESS}
        else:
            k, val, padmap, names = subs[ref]; c, r = place[ref]
            pads = pcb[ref]["pads"]
            if ref == "R1": val = f"{calc['R_sense_ohm'] / 1e3:.3g}k 1% metal film, 1/4 W (PCB: 4.32k; TO-220 build needs this value)"
            if ref == "R4": val = "150k 1% metal film, 1/4 W (6S; 91k for 4S)"
        names = names if names else KIND[k][0]
        name_to_net = {padmap[pn]: net for pn, net in pads.items() if pn in padmap}
        pins = []
        for name, (cc, rr) in zip(names, pin_cells(k, c, r)):
            net = name_to_net.get(name) or None
            pins.append([name, cc, rr, net])
            holes.setdefault((cc, rr), []).append(f"{ref}.{name}")
        parts.append({"ref": ref, "val": val, "k": k, "p": pins, "pcb": pcb[ref]["val"] if ref in pcb else ""})
    clashes = {k: v for k, v in holes.items() if len(v) > 1}
    if clashes: raise SystemExit("hole collisions: " + "; ".join(f"{k}: {v}" for k, v in sorted(clashes.items())))
    # every PCB net of every perfboard part must be on the matching pin
    for pt in parts:
        if pt["ref"] == "JH1": continue
        k, val, padmap, names = subs[pt["ref"]]
        for pn, net in pcb[pt["ref"]]["pads"].items():
            if not net: continue
            pin = next(q for q in pt["p"] if q[0] == padmap[pn])
            assert pin[3] == net, (pt["ref"], pn, net, pin)
    # harness = nets shared by perfboard and power stage
    pnets = {n for r in perf for n in pcb[r]["pads"].values() if n}
    snets = {n for r in POWER for n in pcb[r]["pads"].values() if n}
    shared = pnets & snets
    assert shared == set(HARNESS), shared
    cols = max(q[1] for pt in parts for q in pt["p"]) + 3
    rows = max(r for _, r in occ) + 2
    power = [{"ref": r, "val": pcb[r]["val"], "fp": pcb[r]["fp"], "pads": pcb[r]["pads"]} for r in sorted(POWER)]
    pcbnet = {r: {"val": pcb[r]["val"], "pads": pcb[r]["pads"]} for r in sorted(pcb) if r not in SKIP}
    return parts, cols, rows, calc, power, pcbnet, pnets

NETS = {
 # harness / power-side nets
 "VIN_K": ("#d32f2f", "Kelvin sense of battery + (VIN bar, middle). Feeds the LM5060 VIN pin, the 5 V regulator and the dividers"),
 "VOUT_K": ("#ef6c00", "Kelvin sense of the switched thruster rail (VOUT bar, middle): LM5060 OUT pin, gate reference, LIVE LED"),
 "FG": ("#6a1b9a", "Gate bus of the 8 MOSFETs (through their 10 ohm resistors on the bus bars)"),
 "GND": ("#111111", "Battery minus (from the GND stud on the bus-bar stage)"),
 "PDRV": ("#ad1457", "Pre-charge drive: Q13 pulls the pre-charge P-FET gate down through R9 (on the bus-bar stage)"),
 # LM5060
 "SNS": ("#8e24aa", "LM5060 SENSE: VDS fault threshold = 16 uA x R1"), "UV": ("#5e35b1", "LM5060 UVLO divider (R2/R3)"),
 "OVP": ("#3949ab", "Over-voltage divider: LM5060 OVP pin and LM339 comparator 3"), "TMR": ("#7986cb", "LM5060 timer capacitor"),
 "PGD": ("#9fa8da", "LM5060 power-good (pulled up, not used)"), "GDRV": ("#8e24aa", "LM5060 GATE pin (charge pump out)"),
 "PNB2": ("#4527a0", "Q11 base: fast gate turn-off PNP"), "QOFF": ("#7b1fa2", "Q11 collector to R44 (220 ohm) to VOUT_K"),
 "EN": ("#00897b", "LM5060 enable: 1.1 s delay from ARM, fast discharge by Q16/Q10, LM339 comp 2 holds it low until VOUT > ~0.5 VIN"),
 "END": ("#26a69a", "Q16 drain to R27 (10 ohm) to EN"), "KA": ("#c2185b", "U2 LED anode (from V5 through R7)"),
 "KC": ("#f06292", "U2 LED cathode to Q12: gate-kill opto lights when not armed"),
 # supply
 "V5": ("#e53935", "5.2 V logic supply from the LM317"), "VINL": ("#b71c1c", "LM317 input (VIN_K through R14)"),
 "ADJ": ("#ff7043", "LM317 adjust (R15/R16)"), "V5S": ("#f4511e", "5 V for the Hall module through R18"),
 # arm chain
 "HALL": ("#1e88e5", "KY-003 output S: low while the magnet is in"), "HG": ("#42a5f5", "Q14 gate: pulled low by the Hall output"),
 "RIN": ("#0277bd", "Reed contact input (V5 through R17)"), "ROUT": ("#0288d1", "Reed contact output: high while the magnet is in"),
 "ARM": ("#1565c0", "Armed: both sensors see the magnet (2.2k + 2.2 uF debounce)"), "ARMG": ("#64b5f6", "Q15 gate"),
 "NARM": ("#283593", "Not armed: high kills (opto gate shunt, EN discharge, ramp reset)"),
 "PNB": ("#5c6bc0", "Q10 base: EN follows ARM down through the PNP"),
 "HLA": ("#90caf9", "HALL LED anode"), "RLA": ("#81d4fa", "REED LED anode"),
 "LSAFE": ("#43a047", "SAFE LED anode: on when not armed"), "SAFEG": ("#66bb6a", "Q18 gate: turns SAFE LED off when armed"),
 "LIVEA": ("#ff5252", "LIVE LED anode from VOUT_K"),
 # LM339 pre-charge / enable logic
 "PCEN": ("#2e7d32", "Pre-charge enable: ARM through R10, pulled low by comparator 1 (short abort) or 3 (over-voltage)"),
 "RAMP": ("#558b2f", "Abort ramp: VIN_K / 22 with 3.3 uF, reset by Q17 while not armed"),
 "VOD": ("#827717", "VOUT_K / 10.1 (+46 mV offset from R30)"), "VIND": ("#9e9d24", "VIN_K / 20.1"),
 "REF2": ("#33691e", "2.0 V reference for the over-voltage comparator"),
 # status
 "STA": ("#795548", "Status opto LED anode (VOUT_K through R40)"), "STC": ("#6d4c41", "Status opto collector (to the Jetson)"),
 "STE": ("#8d6e63", "Status opto emitter (to the Jetson)"),
}

if __name__ == "__main__":
    parts, cols, rows, calc, power, pcbnet, pnets = main()
    missing = sorted(pnets - set(NETS))
    if missing: raise SystemExit("nets without colour: " + ", ".join(missing))
    json.dump(calc, open(os.path.join(HERE, "bus_bar_calc.json"), "w"), indent=1)
    js = ("/* ---------- generated by make_vero_data.py from ../kicad/ks_power.kicad_pcb ---------- */\n"
          f"const NETS={json.dumps({k: {'c': c, 'd': d} for k, (c, d) in NETS.items() if k in pnets}, ensure_ascii=False)};\n"
          "const HEAVY={};\n"
          f"const BASE_PARTS={json.dumps(parts, ensure_ascii=False)};\n"
          f"const BASE_COLS={cols}, BASE_ROWS={rows}, P=20, OFF=34;\n"
          f"const CALC={json.dumps(calc)};\n"
          f"const POWER_PARTS={json.dumps(power)};\n"
          f"const PCBNET={json.dumps(pcbnet)};\n"
          "/* ---------- end generated ---------- */\n")
    t = open(HTML).read()
    s = t.index("/* ---------- generated"); e = t.index("/* ---------- end generated ---------- */\n") + len("/* ---------- end generated ---------- */\n")
    open(HTML, "w").write(t[:s] + js + t[e:])
    n_pins = sum(len(p["p"]) for p in parts)
    print(f"{len(parts)} perfboard parts ({n_pins} pins), {len(power)} bus-bar parts, board {cols} x {rows} holes "
          f"({cols * 2.54 / 10:.1f} x {rows * 2.54 / 10:.1f} cm), no collisions, {len(pnets)} nets")
    print(f"R1 (SENSE) {calc['R_sense_ohm']:.0f} ohm (min {calc['R_sense_min_ohm']:.0f}); trip {calc['vds_trip_mV'][0]:.0f}-{calc['vds_trip_mV'][2]:.0f} mV, "
          f"{calc['trip_A_hot_min']:.0f} A hot min, {calc['trip_A_cold_typ']:.0f} A cold typ; 150 A burst {calc['burst_vds_hot_mV']:.0f} mV")
    for k in ("cont_100A", "burst_150A"):
        c = calc[k]; print(f"{k}: FETs {c['p_fets_W']:.1f} W ({c['p_per_fet_W']:.2f} W each, Tj {c['tj_above_bar_K']:.1f} K over bar), total {c['p_total_W']:.1f} W; PCB {c['pcb_p_fets_W']:.2f} / {c['pcb_p_total_W']:.2f} W")
    print("bars:", {k: (round(v, 2) if isinstance(v, float) else v) for k, v in calc["bars"].items()})
