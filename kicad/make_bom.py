"""Group bom_power.csv (written by build_ks.py) into an order list: bom_grouped.csv.
Run with any python3:  python3 make_bom.py"""
import csv, collections, os, re

HERE = os.path.dirname(os.path.abspath(__file__))
# what to buy for each value; "verify" where the exact part number must be checked against its datasheet
BUY = {
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
    for k, v in BUY.items():
        if value.startswith(k) or value == k: return v
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
    rows = list(csv.DictReader(open(os.path.join(HERE, "bom_power.csv"))))
    g = collections.OrderedDict()
    for r in rows: g.setdefault((r["value"], r["footprint"]), []).append(r["ref"])
    key = lambda ref: (re.match(r"[A-Z]+", ref).group(0), int(re.search(r"\d+", ref).group(0)))
    out = sorted(g.items(), key=lambda kv: key(sorted(kv[1], key=key)[0]))
    with open(os.path.join(HERE, "bom_grouped.csv"), "w", newline="") as f:
        w = csv.writer(f); w.writerow(["qty", "value", "footprint", "refs", "buy"])
        for (v, fp), refs in out:
            if fp.startswith("TestPoint"): continue
            w.writerow([len(refs), v, fp, " ".join(sorted(refs, key=key)), buy(v, fp)])
    print(len(out), "lines ->", "bom_grouped.csv")

if __name__ == "__main__":
    main()
