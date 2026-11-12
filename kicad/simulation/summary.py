"""Turn results.json (written by run_ks.py) into summary.md: one line per scenario with its pass/fail check."""
import json, os
HERE = os.path.dirname(os.path.abspath(__file__))
R = json.load(open(os.path.join(HERE, "results.json")))

def f(v, n=1): return "-" if v is None else f"{v:.{n}f}"
def live(r): return r["t_live_ms"] is not None
def kill_ok(r, ms=10): return r.get("kill_latency_ms") is not None and 0 < r["kill_latency_ms"] <= ms

ROWS = [
 ("normal_4S", "4S pack, magnet in, 100 A then 150 A, magnet out",
  lambda r: live(r) and r["i_out_max_before_live_A"] <= 2.5 and r["vgs_on_V"] >= 10 and r["vds_150A_mV"] <= 20 and kill_ok(r) and r["vin_max_V"] <= 45 and r["fet_energy_kill_J"] <= 0.1,
  lambda r: f"live after {f(r['t_live_ms'],0)} ms, pre-charge {f(r['i_out_max_before_live_A'],2)} A, Vgs {f(r['vgs_on_V'],2)} V, VDS {f(r['vds_100A_mV'])} mV at 100 A / {f(r['vds_150A_mV'])} mV at 150 A, off {f(r['kill_latency_ms'],1)} ms after the magnet, {f(r['fet_energy_kill_J']*1e3,0)} mJ in the FETs, VIN peak {f(r['vin_max_V'])} V"),
 ("normal_6S", "6S pack, same test", None, None),
 ("low_3S", "3S (low) pack still arms and kills", lambda r: live(r) and kill_ok(r) and r["vgs_on_V"] >= 10,
  lambda r: f"live after {f(r['t_live_ms'],0)} ms, Vgs {f(r['vgs_on_V'],2)} V, off {f(r['kill_latency_ms'],1)} ms"),
 ("start_into_short", "magnet in with the output shorted", lambda r: not live(r) and r["i_out_max_before_live_A"] <= 2.5 and r["precharge_R_energy_J"] <= 0.5,
  lambda r: f"never goes live, pre-charge stops at {f(r['i_out_max_before_live_A'],2)} A, {f(r['precharge_R_energy_J'],2)} J in the pre-charge resistors"),
 ("short_while_running", "dead short on the output while live", lambda r: kill_ok(r, 2) and r["fet_energy_short_event_J"] <= 3 and r["vin_peak_short_V"] <= 45,
  lambda r: f"off {f(r['kill_latency_ms'],2)} ms after the short, peak {f(r['iout_peak_short_A'],0)} A, {f(r['fet_energy_short_event_J'],2)} J shared by 8 FETs, VIN peak {f(r['vin_peak_short_V'])} V"),
 ("chatter_0p8ms", "0.8 ms sensor chatter (vibration) is ignored", lambda r: r["kill_latency_ms"] is None and r["bus_end_V"] > 10,
  lambda r: f"stays live, output {f(r['bus_end_V'])} V at the end"),
 ("dropout_10ms", "10 ms sensor dropout while 60 A flows, magnet back after 10 ms", lambda r: kill_ok(r) and r["bus_end_V"] < 8,
  lambda r: f"off {f(r['kill_latency_ms'],1)} ms after the dropout; the restart pre-charge cannot lift the bus against the 60 A load, gives up and the output stays off ({f(r['bus_end_V'])} V at 4 s)"),
 ("fault_hall_stuck", "Hall stuck ON, magnet pulled", lambda r: kill_ok(r), lambda r: f"reed path kills in {f(r['kill_latency_ms'],1)} ms"),
 ("fault_reed_welded", "reed welded shut, magnet pulled", lambda r: kill_ok(r), lambda r: f"Hall path kills in {f(r['kill_latency_ms'],1)} ms"),
 ("fault_controller_stuck_on", "LM5060 enable stuck high, magnet pulled", lambda r: kill_ok(r), lambda r: f"opto gate shunt kills in {f(r['kill_latency_ms'],1)} ms"),
 ("fault_sensor_cable_cut", "sensor cable cut while live", lambda r: kill_ok(r), lambda r: f"off in {f(r['kill_latency_ms'],1)} ms"),
 ("fault_hall_vcc_cut", "Hall module loses its 5 V", lambda r: kill_ok(r), lambda r: f"off in {f(r['kill_latency_ms'],1)} ms"),
 ("fault_hall_signal_shorted", "Hall signal wire shorted", lambda r: kill_ok(r), lambda r: f"off in {f(r['kill_latency_ms'],1)} ms"),
 ("wrong_pack_4S_option", "6S pack on a board set for 4S (R4 = 91k)", lambda r: not live(r) and r["precharge_R_energy_J"] <= 0.01,
  lambda r: f"OVP blocks it: never goes live, {f(r['precharge_R_energy_J']*1e6,0)} uJ in the pre-charge resistors, output {f(r['bus_end_V'],3)} V"),
 ("hot_plug_magnet_in", "battery plugged in with the magnet already in", lambda r: live(r) and r["i_out_max_before_live_A"] <= 2.5,
  lambda r: f"normal start: live after {f(r['t_live_ms'],0)} ms, pre-charge {f(r['i_out_max_before_live_A'],2)} A"),
]

def main():
    lines = ["# Simulation results", "", "ngspice, netlist taken from `ks_power.kicad_pcb` by `run_ks.py`. Load: ESC bank with capacitance, then 100 A and 150 A steps.", "",
             "| Scenario | What it tests | Result | Pass |", "|---|---|---|---|"]
    ok_all = True
    prev = None
    for name, what, chk, desc in ROWS:
        chk = chk or prev[0]; desc = desc or prev[1]; prev = (chk, desc)
        r = R[name]; ok = bool(chk(r)); ok_all &= ok
        lines.append(f"| `{name}` | {what} | {desc(r)} | {'yes' if ok else '**NO**'} |")
    lines += ["", f"All {len(ROWS)} scenarios pass." if ok_all else "Some scenarios FAIL - see the table."]
    open(os.path.join(HERE, "summary.md"), "w").write("\n".join(lines) + "\n")
    print("\n".join(lines))

if __name__ == "__main__":
    main()
