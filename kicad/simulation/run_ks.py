"""Simulate the kill switch from its two PCBs (ngspice 42).

The netlist is generated from ks_power.kicad_pcb, so the simulation has exactly the board's connections; each
footprint gets a model by reference/value. The two bought sensors are modelled at the end of their cables: a
KY-003 style Hall module (A3144, 10k pull-up, LED) on J4 and a reed door contact on J6. Around the boards: a 4S or 6S LiPo with
internal resistance and lead inductance, the thruster cable, the ESC capacitor bank with idle and thruster
current, a shorting switch, the magnet, and fault switches for the safety cases.

Run with KiCad 7's python:  python3 run_ks.py [--only name]   -> results.json, out/<scenario>.cir and .csv
"""
import json, os, re, subprocess, sys
import pcbnew

HERE = os.path.dirname(os.path.abspath(__file__))
KIC = os.path.join(HERE, "..")
OUT = os.path.join(HERE, "out")
SENSOR_NETS = {"RIN", "ROUT", "HALL", "V5S"}

def val(s):
    s = s.split()[0].replace("R", "").replace("u", "e-6").replace("n", "e-9").replace("p", "e-12").replace("M", "e6").replace("k", "e3")
    return float(s) if s else 1e-3

def nets_of(fp):
    out = {}
    for p in fp.Pads():
        if p.GetNumber() and p.GetNumber() not in out: out[p.GetNumber()] = p.GetNetname()
    return out

def node(n, side, nc="nc"):
    if n == "": return nc
    if n == "GND": return "0"
    if side == "s" and n in SENSOR_NETS: return n + "_S"          # sensor side of the cable (joined by switches)
    return n

def board_lines(path, side, gateon):
    b = pcbnew.LoadBoard(path); L = []
    for fp in sorted(b.GetFootprints(), key=lambda f: f.GetReference()):
        ref, v, name = fp.GetReference(), fp.GetValue(), fp.GetFPID().GetLibItemName().wx_str()
        n = {k: node(x, side, f"NC_{ref}_{k}") for k, x in nets_of(fp).items()}
        r = ref if side == "p" else "S" + ref
        if ref.startswith(("H", "TP", "J")): continue
        if ref.startswith("RK"): L.append(f"R{r} {n['1']} {n['2']} 1m")
        elif ref.startswith("R") and not ref.startswith("RG"): L.append(f"R{r} {n['1']} {n['2']} {val(v)}")
        elif ref.startswith("RG"): L.append(f"R{r} {n['1']} {n['2']} {val(v)}")
        elif ref.startswith("C"): L.append(f"C{r} {n['1']} {n['2']} {val(v)}")
        elif ref == "F1": L.append(f"R{r} {n['1']} {n['2']} 0.3")
        elif ref.startswith("Q") and v == "IPT007N06N": L.append(f"M{r} {n['3']} {n['1']} {n['2']} IPT007")
        elif ref.startswith("Q") and v == "FQD11P06": L.append(f"M{r} {n['2']} {n['1']} {n['3']} FQD11P06")
        elif ref.startswith("Q") and v == "2N7002": L.append(f"M{r} {n['3']} {n['1']} {n['2']} M2N7002")
        elif ref.startswith("Q") and v == "BSS84": L.append(f"M{r} {n['3']} {n['1']} {n['2']} MBSS84")
        elif ref.startswith("Q") and v == "MMBT3906": L.append(f"Q{r} {n['3']} {n['1']} {n['2']} MMBT3906")
        elif ref.startswith("D") or ref.startswith("LED"):
            model = {"SMCJ26A": "DSMCJ26A", "SMDJ26A": "DSMDJ26A", "BZT52C15": "DZ15", "BZT52C12": "DZ12", "BZT52C6V2": "DZ6V2", "BAT54WS": "DBAT54"}.get(v)
            if model is None: model = "DLEDR" if "red" in v else "DLEDB"
            L.append(f"D{r} {n['2']} {n['1']} {model}")
        elif ref == "U1" and side == "p": L.append(f"X{r} " + " ".join(n[str(i)] for i in range(1, 11)) + f" LM5060 PARAMS: GATEON={gateon}")
        elif v.startswith("PC817"): L.append(f"X{r} {n['1']} {n['2']} {n['4']} {n['3']} PC817")
        elif v == "LM317": L.append(f"X{r} {n['1']} {n['2']} {n['3']} LM317")
        elif v == "LM393": L.append(f"X{r} " + " ".join(n[str(i)] for i in range(1, 9)) + " LM393")
        elif v == "LM339": L.append(f"X{r} " + " ".join(n.get(str(i), f"NC_{ref}_{i}") for i in range(1, 15)) + " LM339")
        elif v.startswith("DRV5033"): L.append(f"X{r} {n['1']} {n['2']} {n['3']} MAG_H HSTUCK DRV5033")
        elif ref == "SW1": L.append(f"S{r} {n['1']} {n['2']} MAG_R 0 SREED")
        else: raise SystemExit(f"no model for {ref} {v} {name}")
    return L

BASE = dict(VB=16.8, RINT=0.012, LBAT=1e-6, LOUT=0.5e-6, ROUT=3e-3, CESC=4000e-6, ESR=0.01, IIDLE=0.4,
            T_END=3.2, MAG="0 0 0.2 0 0.2001 1 3.0 1 3.0001 0", ITHR="0 0 2.0 0 2.05 100 2.6 100 2.62 150 3.05 150 3.06 0",
            SHORT="0 0", HSTUCK=0, REED_WELD=0, GATEON=0, CUT="0 1", CUT5="0 1", HALLSHORT="0 0", R4=150e3)

SCEN = {
    "normal_4S": {},
    "normal_6S": dict(VB=25.2),
    "low_3S": dict(VB=10.5, ITHR="0 0 2.0 0 2.05 60 3.05 60 3.06 0"),
    "start_into_short": dict(SHORT="0 1", ITHR="0 0", MAG="0 0 0.2 0 0.2001 1"),
    "short_while_running": dict(SHORT="0 0 2.3 0 2.3001 1", ITHR="0 0 2.0 0 2.05 50 3.2 50", MAG="0 0 0.2 0 0.2001 1", KILL_AT=2.3),
    "chatter_0p8ms": dict(MAG="0 0 0.2 0 0.2001 1 2.2 1 2.2001 0 2.2008 0 2.2009 1", ITHR="0 0 2.0 0 2.05 60 3.2 60", T_END=2.6),
    "dropout_10ms": dict(MAG="0 0 0.2 0 0.2001 1 2.2 1 2.2001 0 2.21 0 2.2101 1", ITHR="0 0 2.0 0 2.05 60 3.6 60", T_END=4.0),
    "fault_hall_stuck": dict(HSTUCK=1),
    "fault_reed_welded": dict(REED_WELD=1),
    "fault_controller_stuck_on": dict(GATEON=1),
    "fault_sensor_cable_cut": dict(MAG="0 0 0.2 0 0.2001 1", CUT="0 1 2.8 1 2.8001 0", KILL_AT=2.8),
    "fault_hall_vcc_cut": dict(CUT5="0 1 2.5 1 2.5001 0"),
    "fault_hall_signal_shorted": dict(HALLSHORT="0 0 2.5 0 2.5001 1"),
    "wrong_pack_4S_option": dict(VB=25.2, R4=91e3, ITHR="0 0"),
    "hot_plug_magnet_in": dict(MAG="0 1", ITHR="0 0 2.0 0 2.05 100 3.05 100 3.06 0"),
}

def netlist(sc):
    p = dict(BASE); p.update(sc)
    L = ["* kill switch scenario", f".include {os.path.join(HERE, 'models_ks.lib')}",
         ".model SREED SW(Vt=0.5 Vh=0.1 Ron=0.1 Roff=1e9)", ".model SCUT SW(Vt=0.5 Vh=0.1 Ron=0.01 Roff=1e9)",
         ".model SSHORT SW(Vt=0.5 Vh=0.1 Ron=2m Roff=1e9)"]
    L += board_lines(os.path.join(KIC, "ks_power.kicad_pcb"), "p", p["GATEON"])
    # the bought sensors at the end of their cables: one switch per wire (GND stays joined)
    L += ["XKY HALL_S V5S_S 0 MAG_H HSTUCK KY003", "SREED RIN_S ROUT_S MAG_R 0 SREED"]
    L += [f"Scut_{n} {n} {n}_S {'VCUT5' if n == 'V5S' else 'VCUT'} 0 SCUT" for n in sorted(SENSOR_NETS)]
    L += [f"Vcut VCUT 0 PWL({p['CUT']})", f"Vcut5 VCUT5 0 PWL({p['CUT5']})",
          f"Vhs vhs 0 PWL({p['HALLSHORT']})", "Shs HALL_S 0 vhs 0 SSHORT"]
    # battery, leads, ESC bank, thrusters, short, magnet, faults, Jetson input
    L += [f"Vbat batp 0 PWL(0 0 10u {p['VB']})", f"Rbat batp batr {p['RINT']}", f"Lbat batr VIN {p['LBAT']}",
          "Vi_out VOUT vo1 0", f"Lout vo1 vo2 {p['LOUT']}", f"Rout vo2 BUS {p['ROUT']}",
          f"Cbus BUS besr {p['CESC']}", f"Resr besr 0 {p['ESR']}",
          f"Bidle BUS 0 I = {p['IIDLE']} * 0.5 * (1 + tanh((V(BUS) - 6) / 0.5))",
          f"Vithr ithr 0 PWL({p['ITHR']})", "Bthr BUS 0 I = V(ithr) * 0.5 * (1 + tanh((V(BUS) - 8) / 0.5))",
          f"Vsh vsh 0 PWL({p['SHORT']})", "Sshort BUS 0 vsh 0 SSHORT",
          f"Vmag MAG 0 PWL({p['MAG']})", f"Bmagh MAG_H 0 V = V(MAG)", f"Bmagr MAG_R 0 V = max(V(MAG), {p['REED_WELD']})",
          f"Vhst HSTUCK 0 {p['HSTUCK']}", "Rjet STC j33 10k", "Vj33 j33 0 3.3"]
    L = [l.replace("R4 VIN_K OVP 150000.0", f"R4 VIN_K OVP {p['R4']}") for l in L]
    L += [".options method=gear reltol=1e-3 abstol=1e-6 vntol=1e-5 itl4=200",
          f".tran 5u {p['T_END']} 0 100u",
          ".control", "run",
          "let ifet = i(vi_out)", "let vgs = v(g1) - v(vout)", "let pfet = (v(vin) - v(vout)) * i(vi_out)",
          f"wrdata {os.path.join(OUT, '%NAME%.csv')} v(vin) v(vout) v(bus) i(vi_out) v(fg) v(en) v(arm) v(pcg) v(mag) v(tmr) v(pcf)",
          "quit", ".endc", ".end"]
    return "\n".join(L) + "\n"

def run(name, sc):
    os.makedirs(OUT, exist_ok=True)
    cir = os.path.join(OUT, name + ".cir")
    open(cir, "w").write(netlist(sc).replace("%NAME%", name))
    r = subprocess.run(["ngspice", "-b", cir], capture_output=True, text=True, timeout=3000)
    if "Error" in r.stdout + r.stderr and not os.path.exists(os.path.join(OUT, name + ".csv")):
        print(r.stdout[-3000:], r.stderr[-2000:]); raise SystemExit("ngspice failed: " + name)
    return analyse(name, sc)

def analyse(name, sc):
    p = dict(BASE); p.update(sc)
    cols = ["vin", "vout", "bus", "iout", "fg", "en", "arm", "pcg", "mag", "tmr", "pcf"]
    rows = []
    for line in open(os.path.join(OUT, name + ".csv")):
        f = line.split()
        if len(f) < 2 * len(cols): continue
        try: vals = [float(f[0])] + [float(f[2 * i + 1]) for i in range(len(cols))]
        except ValueError: continue
        rows.append(vals)
    T = [r[0] for r in rows]
    col = {c: [r[i + 1] for r in rows] for i, c in enumerate(cols)}
    def at(t):
        i = min(range(len(T)), key=lambda k: abs(T[k] - t)); return {c: col[c][i] for c in cols}
    def first(cond, t0=0.0):
        for i, t in enumerate(T):
            if t >= t0 and cond(i): return t
        return None
    res = {}
    vb = p["VB"]
    t_in = 0.2 if "0.2001 1" in p["MAG"] else 0.0
    res["t_bus_50pct_ms"] = (lambda t: None if t is None else (t - t_in) * 1e3)(first(lambda i: col["bus"][i] > 0.5 * vb, t_in))
    res["t_live_ms"] = (lambda t: None if t is None else (t - t_in) * 1e3)(first(lambda i: col["vout"][i] > 0.97 * vb and col["fg"][i] - col["vout"][i] > 8, t_in))
    res["i_out_max_before_live_A"] = max([col["iout"][i] for i, t in enumerate(T) if t_in <= t <= t_in + 0.15] or [0])
    res["vgs_on_V"] = max(col["fg"][i] - col["vout"][i] for i in range(len(T)))
    res["vin_max_V"] = max(col["vin"]); res["vout_min_V"] = min(col["vout"])
    res["bus_end_V"] = col["bus"][-1]
    for tt, lab in ((2.5, "100A"), (2.9, "150A")):
        if T[-1] >= tt:
            a = at(tt); res[f"vds_{lab}_mV"] = (a["vin"] - a["vout"]) * 1e3; res[f"iout_{lab}_A"] = a["iout"]
    # kill: magnet removed at the last falling edge of MAG, or the scenario's own kill event
    tm = p.get("KILL_AT")
    if tm is None:
        for i in range(1, len(T)):
            if col["mag"][i - 1] > 0.5 >= col["mag"][i]: tm = T[i]
    if tm is not None:
        i0 = max(i for i in range(len(T)) if T[i] <= tm)
        i_before = col["iout"][i0]
        tk = first(lambda i: col["iout"][i] < max(1.0, 0.05 * i_before), tm)
        res["kill_from_A"] = i_before
        res["kill_latency_ms"] = None if tk is None else (tk - tm) * 1e3
        res["vin_peak_after_kill_V"] = max(col["vin"][i] for i in range(len(T)) if T[i] >= tm)
        res["vout_min_after_kill_V"] = min(col["vout"][i] for i in range(len(T)) if T[i] >= tm)
    # main MOSFETs: VDS x (output current - pre-charge current); pre-charge resistors: (PCF - VOUT)^2 / 11 Ohm
    ipc = [(col["pcf"][i] - col["vout"][i]) / 11.0 for i in range(len(T))]
    pf = [(col["vin"][i] - col["vout"][i]) * max(col["iout"][i] - ipc[i], 0) for i in range(len(T))]
    pr = [(col["pcf"][i] - col["vout"][i]) ** 2 / 11.0 for i in range(len(T))]
    integ = lambda y, t0=0.0, t1=1e9: sum(0.5 * (y[i] + y[i - 1]) * (T[i] - T[i - 1]) for i in range(1, len(T)) if t0 <= T[i] <= t1)
    res["fet_power_peak_W"] = max(pf); res["fet_energy_total_J"] = integ(pf)
    res["precharge_R_energy_J"] = integ(pr); res["precharge_R_power_peak_W"] = max(pr)
    if tm is not None:
        res["fet_energy_kill_J"] = integ(pf, tm, tm + 0.05)
    if p.get("SHORT", "0 0") != "0 0":
        ts = float(p["SHORT"].split()[-2]) if p["SHORT"] != "0 1" else 0.0
        res["fet_energy_short_event_J"] = integ(pf, ts, ts + 0.2)
        res["iout_peak_short_A"] = max(col["iout"][i] for i in range(len(T)) if T[i] >= ts)
        res["vin_peak_short_V"] = max(col["vin"][i] for i in range(len(T)) if T[i] >= ts)
    res["t_end_s"] = T[-1]
    return res

if __name__ == "__main__":
    only = sys.argv[sys.argv.index("--only") + 1].split(",") if "--only" in sys.argv else list(SCEN)
    path = os.path.join(HERE, "results.json")
    allres = json.load(open(path)) if os.path.exists(path) else {}
    for name in only:
        print("running", name, flush=True)
        allres[name] = run(name, SCEN[name])
        print(" ", json.dumps({k: (round(v, 4) if isinstance(v, float) else v) for k, v in allres[name].items()}), flush=True)
    json.dump(allres, open(path, "w"), indent=1)
