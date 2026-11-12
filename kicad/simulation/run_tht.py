"""Simulate the through-hole kill switch from its PCB (ngspice 42).

The netlist is generated from ks_tht.kicad_pcb, so the simulation has exactly the board's connections; each
footprint gets a model by reference/value. The two bought sensors are modelled at the end of their cables: a
KY-003 Hall module (A3144, 10k pull-up, LED) on J4 and a reed door contact on J6. Around the board: a 4S or 6S
LiPo with internal resistance and lead inductance, the thruster cable, the ESC capacitor bank with idle and
thruster current, a shorting switch, the magnet, and fault switches for the safety cases.

Run with KiCad 7's python:  python3 run_tht.py [--board tht|smd] [--only name] [--ctr 0.5]
    -> results_<board>.json, out_<board>/<scenario>.cir/.csv  (the SMD board has the same circuit with SMD parts:
    their values are mapped to the same models by ALIAS / DIODES below)
"""
import json, os, subprocess, sys
import pcbnew

HERE = os.path.dirname(os.path.abspath(__file__))
KIC = os.path.join(HERE, "..")
BOARD = sys.argv[sys.argv.index("--board") + 1] if "--board" in sys.argv else "tht"
OUT = os.path.join(HERE, "out_" + BOARD)
SENSOR_NETS = {"RIN", "ROUT", "HALL", "V5S"}
CTR = float(sys.argv[sys.argv.index("--ctr") + 1]) if "--ctr" in sys.argv else 1.0

def val(s):
    s = s.split()[0].replace("R", "").replace("u", "e-6").replace("n", "e-9").replace("p", "e-12").replace("M", "e6").replace("k", "e3")
    return float(s) if s else 1e-3

def nets_of(fp):
    out = {}
    for p in fp.Pads():
        if p.GetNumber() and p.GetNumber() not in out: out[p.GetNumber()] = p.GetNetname()
    return out

def node(n):
    if n == "": return "nc"
    if n == "GND": return "0"
    return n

DIODES = {"P6KE18A": "DP6KE18A", "5KP28A": "D5KP28A", "1.5KE33A": "D15KE33A", "BZX55C12": "DZ12", "1N4744A": "DZ15", "1N4007": "D1N4007",
          "1N4148": "D1N4148", "BAT85": "DBAT85",
          # SMD board: same jobs, SMD packages (SMBJ15A ~ P6KE18A, SMCJ28A ~ 1.5KE33A, SMAZ15 = 1 W 15 V zener)
          "SMBJ15A": "DP6KE18A", "SMCJ28A": "D15KE33A", "BZT52C12": "DZ12", "SMAZ15": "DZ15", "S1M": "D1N4007", "1N4148W": "D1N4148"}
# same pin numbers as the through-hole part (DPAK 1 G/IN 2 tab 3 S/OUT, SOP-4 opto 1 A 2 K 3 E 4 C, SOIC-14 LM339)
ALIAS = {"IRFR5305": "IRF9540N", "LM339D": "LM339N", "L7805CDT": "L7805CV", "MC78M05CDT": "L7805CV", "EL357N": "PC817", "EL817S": "PC817"}

def board_lines(path):
    b = pcbnew.LoadBoard(path); L = []
    for fp in sorted(b.GetFootprints(), key=lambda f: f.GetReference()):
        ref, v = fp.GetReference(), fp.GetValue()
        v = ALIAS.get(v.split()[0], v) if v else v
        n = {k: (node(x) if x else f"NC_{ref}_{k}") for k, x in nets_of(fp).items()}
        if ref.startswith(("H", "TP", "J")): continue
        if ref.startswith("RK"): L.append(f"R{ref} {n['1']} {n['2']} 1m")
        elif ref.startswith("R"): L.append(f"R{ref} {n['1']} {n['2']} {val(v)}")
        elif ref.startswith("C"): L.append(f"C{ref} {n['1']} {n['2']} {val(v)}")
        elif ref == "F1": L.append(f"R{ref} {n['1']} {n['2']} 1.0")
        elif v == "IRFB3206": L.append(f"M{ref} {n['2']} {n['1']} {n['3']} IRFB3206")
        elif v == "IPT007N06N": L.append(f"M{ref} {n['3']} {n['1']} {n['2']} IPT007")          # TOLL: 1 G, 2 S, 3 D (tab)
        elif v == "IRF9540N": L.append(f"M{ref} {n['2']} {n['1']} {n['3']} IRF9540N")
        elif v == "2N7000": L.append(f"M{ref} {n['3']} {n['2']} {n['1']} M2N7000")
        elif v == "2N3904": L.append(f"Q{ref} {n['3']} {n['2']} {n['1']} Q2N3904")
        elif v == "2N3906": L.append(f"Q{ref} {n['3']} {n['2']} {n['1']} Q2N3906")
        elif v == "BC327": L.append(f"Q{ref} {n['1']} {n['2']} {n['3']} QBC327")
        # SOT-23 parts (SMD board): MOSFET 1 G 2 S 3 D, bipolar 1 B 2 E 3 C
        elif v == "2N7002": L.append(f"M{ref} {n['3']} {n['1']} {n['2']} M2N7002")
        elif v == "MMBT3904": L.append(f"Q{ref} {n['3']} {n['1']} {n['2']} Q2N3904")
        elif v == "MMBT3906": L.append(f"Q{ref} {n['3']} {n['1']} {n['2']} Q2N3906")
        elif v in ("BC807-40", "BC807"): L.append(f"Q{ref} {n['3']} {n['1']} {n['2']} QBC327")
        elif v == "FQD11P06": L.append(f"M{ref} {n['2']} {n['1']} {n['3']} FQD11P06")
        elif ref.startswith("D"):
            model = DIODES.get(v) or ("DLEDB" if "blue" in v else "DLEDR")
            L.append(f"D{ref} {n['2']} {n['1']} {model}")
        elif v == "L7805CV": L.append(f"X{ref} {n['1']} {n['2']} {n['3']} LM7805")
        elif v == "TL431A": L.append(f"D{ref} {n['2']} {n['3']} DTL431")
        elif v == "LM339N": L.append(f"X{ref} " + " ".join(n[str(i)] for i in range(1, 15)) + " LM339")
        elif v == "LM393N": L.append(f"X{ref} " + " ".join(n[str(i)] for i in range(1, 9)) + " LM393")
        elif v.startswith("PC817"): L.append(f"X{ref} {n['1']} {n['2']} {n['4']} {n['3']} PC817 PARAMS: CTR={CTR}")
        elif v.startswith("B0512S"): L.append(f"X{ref} {n['1']} {n['2']} {n['3']} {n['4']} B0512S")
        else: raise SystemExit(f"no model for {ref} {v}")
    return L

BASE = dict(VB=16.8, VBPWL=None, RINT=0.012, LBAT=1e-6, LOUT=0.5e-6, ROUT=3e-3, CESC=4000e-6, ESR=0.01, IIDLE=0.4,
            T_END=3.2, MAG="0 0 0.2 0 0.2001 1 3.0 1 3.0001 0", ITHR="0 0 2.0 0 2.05 60 2.6 60 2.62 100 3.05 100 3.06 0",
            SHORT="0 0", HSTUCK=0, REED_WELD=0, GATEON=0, CUT="0 1", CUT5="0 1", HALLSHORT="0 0")

SCEN = {
    "normal_4S": {},
    "normal_6S": dict(VB=25.2),
    "low_4S": dict(VB=13.0),
    "start_into_short": dict(SHORT="0 1", ITHR="0 0", MAG="0 0 0.2 0 0.2001 1"),
    "short_while_running": dict(SHORT="0 0 2.3 0 2.3001 1", ITHR="0 0 2.0 0 2.05 100 3.2 100", MAG="0 0 0.2 0 0.2001 1", KILL_AT=2.3),
    "short_while_running_6S": dict(VB=25.2, SHORT="0 0 2.3 0 2.3001 1", ITHR="0 0 2.0 0 2.05 100 3.2 100", MAG="0 0 0.2 0 0.2001 1", KILL_AT=2.3),
    "chatter_0p8ms": dict(MAG="0 0 0.2 0 0.2001 1 2.2 1 2.2001 0 2.2008 0 2.2009 1", ITHR="0 0 2.0 0 2.05 100 3.2 100", T_END=2.6),
    "dropout_10ms": dict(MAG="0 0 0.2 0 0.2001 1 2.2 1 2.2001 0 2.21 0 2.2101 1", ITHR="0 0 2.0 0 2.05 100 3.6 100", T_END=4.0),
    "battery_sag_16v8_to_12v": dict(VBPWL="0 0 10u 16.8 2.65 16.8 2.85 12.0", ITHR="0 0 2.0 0 2.05 100 3.2 100", MAG="0 0 0.2 0 0.2001 1", T_END=3.2),
    "fault_hall_stuck": dict(HSTUCK=1),
    "fault_reed_welded": dict(REED_WELD=1),
    "fault_sensor_cable_cut": dict(MAG="0 0 0.2 0 0.2001 1", CUT="0 1 2.8 1 2.8001 0", KILL_AT=2.8),
    "fault_hall_vcc_cut": dict(CUT5="0 1 2.5 1 2.5001 0"),
    "fault_hall_signal_shorted": dict(HALLSHORT="0 0 2.5 0 2.5001 1"),
    "hot_plug_magnet_in": dict(MAG="0 1", ITHR="0 0 2.0 0 2.05 60 3.05 60 3.06 0"),
}
COLS = ["vin", "vout", "bus", "iout", "fg", "en", "arm", "pcg", "mag", "drv", "pcf", "v12f", "pcen", "done", "ramp", "vod"]

def netlist(sc):
    p = dict(BASE); p.update(sc)
    vb = p["VBPWL"] or f"0 0 10u {p['VB']}"
    L = ["* kill switch (through-hole) scenario", f".include {os.path.join(HERE, 'models_tht.lib')}",
         ".model SREED SW(Vt=0.5 Vh=0.1 Ron=0.1 Roff=1e9)", ".model SCUT SW(Vt=0.5 Vh=0.1 Ron=0.01 Roff=1e9)",
         ".model SSHORT SW(Vt=0.5 Vh=0.1 Ron=2m Roff=1e9)", ".model SGON SW(Vt=0.5 Vh=0.1 Ron=10 Roff=1e9)"]
    L += board_lines(os.path.join(KIC, f"ks_{BOARD}.kicad_pcb"))
    # the bought sensors at the end of their cables: one switch per wire (GND stays joined)
    L += ["XKY HALL_S V5S_S 0 MAG_H HSTUCK KY003", "SREED RIN_S ROUT_S MAG_R 0 SREED"]
    L += [f"Scut_{n} {n} {n}_S {'VCUT5' if n == 'V5S' else 'VCUT'} 0 SCUT" for n in sorted(SENSOR_NETS)]
    L += [f"Vcut VCUT 0 PWL({p['CUT']})", f"Vcut5 VCUT5 0 PWL({p['CUT5']})",
          f"Vhs vhs 0 PWL({p['HALLSHORT']})", "Shs HALL_S 0 vhs 0 SSHORT"]
    # controller stuck on: the gate-drive opto output shorted
    L += [f"Vgon gon 0 {p['GATEON']}", "Sgon V12F DRV gon 0 SGON"]
    # battery, leads, ESC bank, thrusters, short, magnet, faults, Jetson input
    L += [f"Vbat batp 0 PWL({vb})", f"Rbat batp batr {p['RINT']}", f"Lbat batr VIN {p['LBAT']}",
          "Vi_out VOUT vo1 0", f"Lout vo1 vo2 {p['LOUT']}", f"Rout vo2 BUS {p['ROUT']}",
          f"Cbus BUS besr {p['CESC']}", f"Resr besr 0 {p['ESR']}",
          f"Bidle BUS 0 I = {p['IIDLE']} * 0.5 * (1 + tanh((V(BUS) - 6) / 0.5))",
          f"Vithr ithr 0 PWL({p['ITHR']})", "Bthr BUS 0 I = V(ithr) * 0.5 * (1 + tanh((V(BUS) - 8) / 0.5))",
          f"Vsh vsh 0 PWL({p['SHORT']})", "Sshort BUS 0 vsh 0 SSHORT",
          f"Vmag MAG 0 PWL({p['MAG']})", "Bmagh MAG_H 0 V = V(MAG)", f"Bmagr MAG_R 0 V = max(V(MAG), {p['REED_WELD']})",
          f"Vhst HSTUCK 0 {p['HSTUCK']}", "Rjet STC j33 10k", "Vj33 j33 0 3.3", "Rjg STE 0 1m"]
    L += [".options method=gear reltol=1e-3 abstol=1e-6 vntol=1e-5 itl4=200",
          f".tran 5u {p['T_END']} 0 100u",
          ".control", "run",
          f"wrdata {os.path.join(OUT, '%NAME%.csv')} " + " ".join(f"v({c})" if c != "iout" else "i(vi_out)" for c in COLS),
          "quit", ".endc", ".end"]
    return "\n".join(L) + "\n"

def run(name, sc):
    os.makedirs(OUT, exist_ok=True)
    cir = os.path.join(OUT, name + ".cir")
    open(cir, "w").write(netlist(sc).replace("%NAME%", name))
    r = subprocess.run(["ngspice", "-b", cir], capture_output=True, text=True, timeout=3000)
    if not os.path.exists(os.path.join(OUT, name + ".csv")) or "rror" in (r.stdout + r.stderr)[-2000:]:
        print(r.stdout[-3000:], r.stderr[-2000:])
        if not os.path.exists(os.path.join(OUT, name + ".csv")): raise SystemExit("ngspice failed: " + name)
    return analyse(name, sc)

def load(name):
    rows = []
    for line in open(os.path.join(OUT, name + ".csv")):
        f = line.split()
        if len(f) < 2 * len(COLS): continue
        try: rows.append([float(f[0])] + [float(f[2 * i + 1]) for i in range(len(COLS))])
        except ValueError: continue
    T = [r[0] for r in rows]
    return T, {c: [r[i + 1] for r in rows] for i, c in enumerate(COLS)}

def analyse(name, sc):
    p = dict(BASE); p.update(sc)
    T, col = load(name)
    def at(t):
        i = min(range(len(T)), key=lambda k: abs(T[k] - t)); return {c: col[c][i] for c in COLS}
    def first(cond, t0=0.0):
        for i, t in enumerate(T):
            if t >= t0 and cond(i): return t
        return None
    res = {}
    vb = p["VB"]
    t_in = 0.2 if "0.2001 1" in p["MAG"] else 0.0
    res["t_live_ms"] = (lambda t: None if t is None else (t - t_in) * 1e3)(first(lambda i: col["vout"][i] > 0.97 * col["vin"][i] and col["fg"][i] - col["vout"][i] > 8, t_in))
    res["i_precharge_max_A"] = max([(col["pcf"][i] - col["vout"][i]) / 11.0 for i, t in enumerate(T) if t >= t_in] or [0])
    res["i_out_max_before_live_A"] = max([col["iout"][i] for i, t in enumerate(T) if t_in <= t <= t_in + (res["t_live_ms"] or 1e9) / 1e3 + 0.01 and t < 1.9] or [0])
    res["vgs_on_V"] = max(col["fg"][i] - col["vout"][i] for i in range(len(T)))
    res["v12f_V"] = max(col["v12f"][i] - col["vout"][i] for i in range(len(T)))
    res["vin_max_V"] = max(col["vin"]); res["vout_min_V"] = min(col["vout"])
    res["bus_end_V"] = col["bus"][-1]
    for tt, lab in ((2.5, "60A"), (2.9, "100A")):
        if T[-1] >= tt:
            a = at(tt); res[f"vds_{lab}_mV"] = (a["vin"] - a["vout"]) * 1e3; res[f"iout_{lab}_A"] = a["iout"]
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
        res["vin_at_kill_V"] = None if tk is None else at(tk)["vin"]
        res["vin_peak_after_kill_V"] = max(col["vin"][i] for i in range(len(T)) if T[i] >= tm)
        res["vout_min_after_kill_V"] = min(col["vout"][i] for i in range(len(T)) if T[i] >= tm)
    ipc = [(col["pcf"][i] - col["vout"][i]) / 11.0 for i in range(len(T))]
    pf = [(col["vin"][i] - col["vout"][i]) * max(col["iout"][i] - ipc[i], 0) for i in range(len(T))]
    pr = [(col["pcf"][i] - col["vout"][i]) ** 2 / 11.0 for i in range(len(T))]
    integ = lambda y, t0=0.0, t1=1e9: sum(0.5 * (y[i] + y[i - 1]) * (T[i] - T[i - 1]) for i in range(1, len(T)) if t0 <= T[i] <= t1)
    res["fet_power_peak_W"] = max(pf); res["fet_energy_total_J"] = integ(pf)
    res["precharge_R_energy_J"] = integ(pr); res["precharge_R_power_peak_W"] = max(pr)
    if tm is not None: res["fet_energy_kill_J"] = integ(pf, tm, tm + 0.05)
    if p.get("SHORT", "0 0") != "0 0":
        ts = float(p["SHORT"].split()[-2]) if p["SHORT"] != "0 1" else 0.0
        res["fet_energy_short_event_J"] = integ(pf, ts, ts + 0.2)
        res["iout_peak_short_A"] = max(col["iout"][i] for i in range(len(T)) if T[i] >= ts)
        res["vin_peak_short_V"] = max(col["vin"][i] for i in range(len(T)) if T[i] >= ts)
    res["t_end_s"] = T[-1]
    return res

if __name__ == "__main__":
    only = sys.argv[sys.argv.index("--only") + 1].split(",") if "--only" in sys.argv else list(SCEN)
    path = os.path.join(HERE, f"results_{BOARD}.json" if CTR == 1.0 else f"results_{BOARD}_ctr{CTR}.json")
    for name in only:
        print("running", name, flush=True)
        res = run(name, SCEN[name])
        print(" ", json.dumps({k: (round(v, 4) if isinstance(v, float) else v) for k, v in res.items()}), flush=True)
        # several runs may share the file (one process per scenario): re-read, update this scenario, swap in
        allres = json.load(open(path)) if os.path.exists(path) else {}
        allres[name] = res
        tmp = f"{path}.{os.getpid()}"; json.dump(allres, open(tmp, "w"), indent=1); os.replace(tmp, path)
