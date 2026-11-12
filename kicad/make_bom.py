"""Group a per-reference BOM into an order list.
Run with any python3:  python3 make_bom.py                       (SMD board: bom_power.csv -> bom_grouped.csv)
                       python3 make_bom.py bom_tht.csv bom_tht_grouped.csv   (through-hole board)"""
import csv, collections, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
# what to buy for each value; "verify" where the exact part number must be checked against its datasheet
BUY = {
    # through-hole board
    "IRFB3206": "Infineon IRFB3206PbF (TO-220, 60 V, 3.0 mOhm max at 10 V)",
    "IRF9540N": "IRF9540NPbF (TO-220, -100 V P-MOSFET)",
    "2N7000": "2N7000 (TO-92, pins S G D)", "2N3904": "2N3904 (TO-92, pins E B C)", "2N3906": "2N3906 (TO-92, pins E B C)",
    "BC327": "BC327-40 (TO-92, pins C B E)",
    "L7805CV": "L7805CV (TO-220, tab = GND, lies flat on the board); a K7805-500R3 or R-78E5.0-0.5 switching module fits the same holes and runs cool",
    "LM339N": "LM339N (DIP-14) + socket", "B0512S": "Mornsun B0512S-1WR3 (5 V -> 12 V isolated, 1 W, SIP-4): pins 1 GND, 2 Vin, 3 0V, 4 +Vo - check yours",
    "1.5KE33A": "1.5KE33A TVS (DO-201, 1500 W, 28.2 V standoff)", "P6KE18A": "P6KE18A TVS (DO-15, 600 W, 15.3 V standoff)",
    "1N4744A": "1N4744A zener 15 V 1 W (DO-41)", "1N4007": "1N4007 (DO-41)", "1N4148": "1N4148 (DO-35)", "BZX55C12": "BZX55C12 zener 12 V (DO-35)",
    "RXEF050": "Littelfuse RXEF050 radial PTC (0.5 A hold, 72 V)",
    "XT60 BATTERY": "AMASS XT60PW-M (male, PCB right-angle) - mates with the battery", "XT60 TO ESCs": "AMASS XT60PW-F (female, PCB right-angle) - the ESC harness plugs in here",
    "HALL MODULE": "JST XH 3-pin header B3B-XH-A + housing XHP-3; KY-003 Hall module", "REED (MC-38)": "JST XH 2-pin header B2B-XH-A + housing XHP-2; MC-38 wired door contact (closed with the magnet)",
    "0R": "0 Ohm jumper (or a wire link)", "22 2W": "22 Ohm 2 W metal oxide or metal film, axial",
    "3.3u X7R": "3.3 uF 50 V X7R radial ceramic (not electrolytic: its leakage would upset the ramp)",
    "220n 100V film": "220 nF 100 V film (MKT/MKS), 5 mm pitch",
    "yellow": "3 mm LED, yellow",
    "IPT007N06N": "Infineon IPT007N06N (60 V, 0.75 mOhm max, TOLL)",
    "LM5060": "TI LM5060MM/NOPB (VSSOP-10)",
    "LM339": "LM339DR or LM339ADR (SOIC-14)",
    "LM317": "LM317 in SOT-223 (e.g. LM317DCYR)",
    "PC817": "Sharp/Everlight PC817 SMD (SMDIP-4, gull wing)",
    "FQD11P06": "onsemi FQD11P06TM (-60 V P-FET, DPAK)",
    "SMDJ26A": "Littelfuse SMDJ26A (3 kW TVS, 26 V standoff, SMC)",
    "SMCJ26A": "Littelfuse SMCJ26A (1.5 kW TVS, 26 V standoff, SMC)",
    "BZT52C": "BZT52C series zener, SOD-123",
    "BAT54WS": "BAT54WS Schottky, SOD-323",
    "MMBT3906": "MMBT3906 PNP, SOT-23",
    "2N7002": "2N7002 N-FET, SOT-23",
    "BSS84": "BSS84 P-FET, SOT-23",
    "PTC": "1812 PTC fuse, hold 0.5 A, rated 30 V or more (60 V better for 6S) - verify the rating",
    "22 2W": "22 Ohm 2 W metal oxide or metal film, axial (pulse 1.5 J each)",
    "HALL MODULE": "JST XH 3-pin header B3B-XH-A + housing XHP-3 for the KY-003 cable",
    "REED CONTACT": "JST XH 2-pin header B2B-XH-A + housing XHP-2 for the MC-38 cable",
    "STATUS": "JST XH 2-pin header B2B-XH-A + housing XHP-2",
    "BAT+": "M5 ring lug, 6 AWG or thicker cable, M5 brass/stainless bolt + nut",
    "THRUSTER+": "M5 ring lug, 6 AWG or thicker cable, M5 brass/stainless bolt + nut",
    "GND (M4)": "M4 ring lug, thin wire to battery minus (logic ground only)",
    "blue": "0805 LED, blue", "green": "0805 LED, green", "red": "0805 LED, red",
    "FG": "test pad (no part)", "EN": "test pad (no part)", "ARM": "test pad (no part)", "V5": "test pad (no part)",
    "VOD": "test pad (no part)", "GND": "test pad (no part)",
}

def buy(value, fp):
    if fp.startswith("LED_D3.0mm"): return "3 mm LED, " + value.split()[0]
    if fp.startswith("DIP-4") and value.startswith("PC817"): return "PC817 optocoupler (DIP-4)"
    for k, v in BUY.items():
        if value.startswith(k) or value == k: return v
    if fp.startswith("R_Axial"):
        return "1/4 W resistor " + ("1%" if "1%" in value else "5% or 1%") + (", stood up (2.54 mm)" if "Vertical" in fp else "")
    if fp.startswith(("CP_Radial", "C_Disc", "C_Rect")):
        return ("radial electrolytic " if fp.startswith("CP") else "ceramic disc or MLCC radial ") + value
    if fp.startswith("LED_D3.0mm"): return "3 mm LED"
    if fp.startswith("TestPoint"): return "test pad (no part)"
    if fp.startswith("R_"):
        tol = "1%" if "1%" in value else "1% or 5%"
        size = re.search(r"R_(\d{4})", fp).group(1)
        return f"{size} resistor {tol}" + (", 0 Ohm jumper" if value.startswith("0R") else "")
    if fp.startswith("C_"):
        size = re.search(r"C_(\d{4})", fp).group(1)
        v = re.search(r"(\d+V)", value)
        return f"{size} X7R ceramic" + (f", {v.group(1)}" if v else ", 25 V or more")
    return ""

def main():
    src, dst = (sys.argv[1], sys.argv[2]) if len(sys.argv) > 2 else ("bom_power.csv", "bom_grouped.csv")
    rows = list(csv.DictReader(open(os.path.join(HERE, src))))
    g = collections.OrderedDict()
    for r in rows: g.setdefault((r["value"], r["footprint"]), []).append(r["ref"])
    key = lambda ref: (re.match(r"[A-Z]+", ref).group(0), int(re.search(r"\d+", ref).group(0)))
    out = sorted(g.items(), key=lambda kv: key(sorted(kv[1], key=key)[0]))
    with open(os.path.join(HERE, dst), "w", newline="") as f:
        w = csv.writer(f); w.writerow(["qty", "value", "footprint", "refs", "buy"])
        for (v, fp), refs in out:
            if fp.startswith("TestPoint"): continue
            w.writerow([len(refs), v, fp, " ".join(sorted(refs, key=key)), buy(v, fp)])
    print(len(out), "lines ->", dst)

if __name__ == "__main__":
    main()
