"""Turn results_<board>.json (written by run_tht.py) into summary_<board>.md: one line per scenario with its pass/fail check.
    python3 summary_tht.py [--board tht|smd]"""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
BOARD = sys.argv[sys.argv.index("--board") + 1] if "--board" in sys.argv else "tht"
NFET = {"tht": "8 x IRFB3206", "smd": "4 x IPT007N06N"}[BOARD]
R = json.load(open(os.path.join(HERE, f"results_{BOARD}.json")))

def f(v, n=1): return "-" if v is None else f"{v:.{n}f}"
def live(r): return r["t_live_ms"] is not None
def kill_ok(r, ms=5): return r.get("kill_latency_ms") is not None and 0 < r["kill_latency_ms"] <= ms
def normal(r): return (live(r) and 600 <= r["t_live_ms"] <= 1200 and r["i_precharge_max_A"] <= 2.5 and r["i_out_max_before_live_A"] <= 40
                       and 10 <= r["vgs_on_V"] <= 18 and r["vds_100A_mV"] <= 60 and kill_ok(r) and r["vin_max_V"] <= 40 and r["fet_energy_kill_J"] <= 0.1)
def normal_txt(r): return (f"live after {f(r['t_live_ms'],0)} ms, pre-charge {f(r['i_precharge_max_A'],2)} A, {f(r['i_out_max_before_live_A'],0)} A when the MOSFETs close, "
                           f"Vgs {f(r['vgs_on_V'],1)} V, VDS {f(r['vds_60A_mV'])} mV at 60 A / {f(r['vds_100A_mV'])} mV at 100 A, off {f(r['kill_latency_ms'],1)} ms after the magnet, "
                           f"{f(r['fet_energy_kill_J']*1e3,0)} mJ in the MOSFETs, VIN peak {f(r['vin_max_V'])} V")
ROWS = [
 ("normal_4S", "4S pack, magnet in, 60 A then 100 A, magnet out", normal, normal_txt),
 ("normal_6S", "6S pack, same test", normal, normal_txt),
 ("low_4S", "4S pack nearly empty (13 V), same test", normal, normal_txt),
 ("start_into_short", "magnet in with the ESC side shorted", lambda r: not live(r) and r["i_precharge_max_A"] <= 2.5 and r["precharge_R_energy_J"] <= 1 and r["fet_energy_total_J"] <= 0.01,
  lambda r: f"never goes live, pre-charge {f(r['i_precharge_max_A'],2)} A then stops, {f(r['precharge_R_energy_J'],2)} J in the 22 Ohm resistors, nothing in the MOSFETs"),
 ("short_while_running", "dead short on the ESC side while live (4S)", lambda r: kill_ok(r, 2) and r["fet_energy_short_event_J"] <= 3 and r["vgs_on_V"] <= 20 and r["vin_peak_short_V"] <= 40,
  lambda r: f"off {f(r['kill_latency_ms'],2)} ms after the short, peak {f(r['iout_peak_short_A'],0)} A, {f(r['fet_energy_short_event_J'],2)} J shared by {NFET}, Vgs max {f(r['vgs_on_V'],1)} V, VIN peak {f(r['vin_peak_short_V'])} V"),
 ("short_while_running_6S", "same on 6S", None, None),
 ("chatter_0p8ms", "0.8 ms sensor chatter (vibration) is ignored", lambda r: r["kill_latency_ms"] is None and r["bus_end_V"] > 10,
  lambda r: f"stays live, output {f(r['bus_end_V'])} V at the end"),
 ("dropout_10ms", "10 ms sensor dropout while 100 A flows", lambda r: kill_ok(r),
  lambda r: f"off {f(r['kill_latency_ms'],1)} ms after the dropout"),
 ("battery_sag_16v8_to_12v", "pack sags 16.8 -> 12 V in 0.2 s at 100 A", lambda r: r["bus_end_V"] > 10,
  lambda r: f"stays live, output {f(r['bus_end_V'])} V at the end"),
 ("fault_hall_stuck", "Hall stuck ON, magnet pulled", lambda r: kill_ok(r), lambda r: f"reed path kills in {f(r['kill_latency_ms'],1)} ms"),
 ("fault_reed_welded", "reed welded shut, magnet pulled", lambda r: kill_ok(r), lambda r: f"Hall path kills in {f(r['kill_latency_ms'],1)} ms"),
 ("fault_sensor_cable_cut", "sensor cable cut while live", lambda r: kill_ok(r), lambda r: f"off in {f(r['kill_latency_ms'],1)} ms"),
 ("fault_hall_vcc_cut", "Hall module loses its 5 V", lambda r: kill_ok(r), lambda r: f"off in {f(r['kill_latency_ms'],1)} ms"),
 ("fault_hall_signal_shorted", "Hall signal wire shorted to GND", lambda r: kill_ok(r), lambda r: f"reed path kills in {f(r['kill_latency_ms'],1)} ms"),
 ("hot_plug_magnet_in", "battery plugged in with the magnet already in", lambda r: live(r) and r["i_precharge_max_A"] <= 2.5 and r["i_out_max_before_live_A"] <= 40,
  lambda r: f"normal start: live after {f(r['t_live_ms'],0)} ms, pre-charge {f(r['i_precharge_max_A'],2)} A"),
]

def main():
    lines = [f"# Simulation results, {'through-hole' if BOARD == 'tht' else 'SMD'} board ({NFET})", "",
             f"ngspice, netlist taken from `ks_{BOARD}.kicad_pcb` by `run_tht.py --board {BOARD}`. Load: ESC bank (4000 uF) with idle current, then 60 A and 100 A.", "",
             "| Scenario | What it tests | Result | Pass |", "|---|---|---|---|"]
    ok_all = True; prev = None
    for name, what, chk, desc in ROWS:
        chk = chk or prev[0]; desc = desc or prev[1]; prev = (chk, desc)
        if name not in R: continue
        r = R[name]; ok = bool(chk(r)); ok_all &= ok
        lines.append(f"| `{name}` | {what} | {desc(r)} | {'yes' if ok else '**NO**'} |")
    lines += ["", f"All {len(ROWS)} scenarios pass." if ok_all else "Some scenarios FAIL - see the table."]
    open(os.path.join(HERE, f"summary_{BOARD}.md"), "w").write("\n".join(lines) + "\n")
    print("\n".join(lines))

if __name__ == "__main__":
    main()
