"""Write ../../SIMULATION_RESULT.md from the final-board runs: summary_tht.md (15 scenarios), results_tht_ctr0.5.json
(worst-case PC817) and copper_tht.json / copper_tht_wires.json (DC current in the power copper)."""
import json, os
HERE = os.path.dirname(os.path.abspath(__file__))
S = open(os.path.join(HERE, "summary_tht.md")).read()
table = "\n".join(l for l in S.splitlines() if l.startswith("|"))
C = json.load(open(os.path.join(HERE, "results_tht_ctr0.5.json")))
A = json.load(open(os.path.join(HERE, "results_tht.json")))
E = json.load(open(os.path.join(HERE, "copper_tht.json"))); Wr = json.load(open(os.path.join(HERE, "copper_tht_wires.json")))
f = lambda v, n=1: "-" if v is None else f"{v:.{n}f}"
pct = lambda s: " / ".join(f"{100 * x:.1f}" for x in s)
ctr_rows = []
for k, what in (("normal_4S", "4S normal"), ("normal_6S", "6S normal"), ("start_into_short", "magnet in, ESC side shorted"),
                ("short_while_running_6S", "dead short while live, 6S"), ("fault_hall_stuck", "Hall stuck ON, magnet pulled"),
                ("chatter_0p8ms", "0.8 ms sensor chatter")):
    r, n = C[k], A[k]
    res = ("never turns on" if r["t_live_ms"] is None else f"live {f(r['t_live_ms'], 0)} ms, Vgs {f(r['vgs_on_V'], 1)} V") + \
          ("" if r.get("kill_latency_ms") is None else f", off in {f(r['kill_latency_ms'], 2)} ms") + \
          (", stays live" if k == "chatter_0p8ms" and r.get("kill_latency_ms") is None else "")
    nom = ("never turns on" if n["t_live_ms"] is None else f"Vgs {f(n['vgs_on_V'], 1)} V") + ("" if n.get("kill_latency_ms") is None else f", off in {f(n['kill_latency_ms'], 2)} ms")
    ctr_rows.append(f"| {what} | {nom} | {res} |")
def cu(d, key, I=None): return d[key] if I is None else d[key.replace("X", str(I))]
cu_rows = [
 ("Copper resistance, battery XT60 + to MOSFET drains", "r_vin_copper_mohm", "mOhm"),
 ("Copper resistance, MOSFET sources to ESC XT60 +", "r_vout_copper_mohm", "mOhm"),
 ("Copper resistance, GND return (ESC XT60 - to battery XT60 -)", "r_gnd_copper_mohm", "mOhm"),
 ("4 MOSFETs in parallel (3.34 mOhm each)", "r_fets_parallel_mohm", "mOhm"),
]
lines = ["# Simulation result: through-hole kill switch", "",
 "Final run on the finished board `kicad/ks_tht.kicad_pcb` (XT60 in/out, 4 x IRFB3206, 30 A continuous / 60 A burst). "
 "The board has **not been built yet**: these are ngspice simulations of the netlist taken from the PCB, plus a DC current solve of the board's own copper.", "",
 "## Verdict", "",
 "- All 15 circuit scenarios pass, also with the weakest PC817 optocoupler (CTR 50 %).",
 f"- Magnet pulled: power off in {f(A['normal_4S']['kill_latency_ms'], 1)} ms. Dead short while running: off in {f(A['short_while_running']['kill_latency_ms'], 2)} ms (4S) / {f(A['short_while_running_6S']['kill_latency_ms'], 2)} ms (6S). Magnet in with the ESC side shorted: never turns on.",
 f"- The board's own copper loses more than the MOSFETs: {f(E['copper_loss_30A_W'], 1)} W against {f(E['fet_loss_30A_W'], 2)} W at 30 A. Soldering a 12 AWG bare wire on the bare strips brings the copper down to {f(Wr['copper_loss_30A_W'], 1)} W.",
 "- Three problems found in this final round were fixed on the board (below).", "",
 "## 1. Circuit: 15 scenarios (ngspice, netlist from the PCB)", "", table, "",
 "## 2. Weakest optocoupler (PC817 CTR 50 % instead of 100 %)", "",
 "| Case | CTR 100 % | CTR 50 % |", "|---|---|---|"] + ctr_rows + ["",
 "The gate drive has enough margin: nothing changes by more than 0.05 ms or 0.1 V.", "",
 "## 3. Board copper: DC current solve", "",
 "The filled pours, tracks and pads of VIN, VOUT and GND are taken from the PCB on a 0.25 mm grid and solved as 2 oz copper (70 um, 20 C). "
 "The 4 MOSFETs are 3.34 mOhm each between their drain and source pads, so the solve also shows how the current shares between them (`kicad/simulation/copper_tht.py`).", "",
 "| | As etched | With 12 AWG wire on the bare strips |", "|---|---|---|"]
for label, key, unit in cu_rows:
    lines.append(f"| {label} | {f(E[key], 2)} {unit} | {f(Wr[key], 2)} {unit} |")
lines += [f"| Current share Q1 / Q2 / Q3 / Q4 (%) | {pct(E['fet_share'])} | {pct(Wr['fet_share'])} |",
 f"| Loss at 30 A: copper / MOSFETs | {f(E['copper_loss_30A_W'], 2)} W / {f(E['fet_loss_30A_W'], 2)} W | {f(Wr['copper_loss_30A_W'], 2)} W / {f(Wr['fet_loss_30A_W'], 2)} W |",
 f"| Loss at 60 A burst: copper / MOSFETs | {f(E['copper_loss_60A_W'], 1)} W / {f(E['fet_loss_60A_W'], 1)} W | {f(Wr['copper_loss_60A_W'], 1)} W / {f(Wr['fet_loss_60A_W'], 1)} W |",
 f"| Drop in the copper at 30 A / 60 A | {f(E['copper_drop_30A_mV'], 0)} / {f(E['copper_drop_60A_mV'], 0)} mV | {f(Wr['copper_drop_30A_mV'], 0)} / {f(Wr['copper_drop_60A_mV'], 0)} mV |",
 f"| Most crowded spot at 60 A | {f(E['gnd_peak_60A_A_per_mm'], 0)} A per mm of width, GND next to the battery XT60 pin | at the ends of the wires, where current moves from the pour into the wire |", "",
 "Current-density maps: `kicad/simulation/copper_vin.png`, `copper_vout.png`, `copper_gnd.png` (and `*_wires.png`).", "",
 "## 4. Fixed because of this run", "",
 "1. **GND neck.** The first copper solve found the GND return squeezed through a gap in the bottom plane (18 A/mm at 60 A), between the VIN_K track and where the gate bus left the power section. The gate bus now leaves at the right end and VIN_K runs on the top layer; the most crowded GND spot is now at the XT60 pin itself.",
 "2. **Copper loss.** Bare strips without solder mask now run along the VIN and VOUT paths (top) and the GND path (bottom), so a 12 AWG bare copper wire or a thick solder bead can be added: copper loss at 30 A drops from 2.4 W to 1.2 W, and the 4 MOSFETs share the current within 1 %.",
 "3. **Gate overshoot.** In a 6S dead short the gate briefly reached 19.7 V (IRFB3206 limit 20 V), because the soft-start capacitor held the gate up while VOUT fell. A 100 Ohm resistor (R39) in series with it brings the peak to 16.1 V; start-up and turn-off are unchanged.", "",
 "## 5. What to do with this", "",
 "- Up to about 30 A continuous the board is fine as etched (about 3 W in total, spread over the board).",
 "- For frequent 60 A bursts, solder a 12 AWG bare copper wire on each bare strip (VIN and VOUT on top, GND underneath).",
 "- Keep the 40 A fuse in the battery lead: overloads below a hard short are the fuse's job.",
 "- First power-up on a current-limited bench supply, then one ESC, then full current.", "",
 "## 6. Not simulated", "",
 "- Temperature over time (only losses are computed), and copper resistance rising about 20 % when hot.",
 "- Real part tolerances other than the opto CTR; comparator and opto delays are simplified; the B0512S is a behavioural model.",
 "- EMI, vibration, water and the mechanical plug.", "",
 "## Bangla-English summary", "",
 "- Final board-e 15 ta simulation-i pass, kharap PC817 (CTR 50 %) diyeo.",
 f"- Magnet tanle {f(A['normal_4S']['kill_latency_ms'], 1)} ms-e off; chalu obosthay short hole {f(A['short_while_running']['kill_latency_ms'], 2)} ms-e off; short obosthay chalu-i hoy na.",
 f"- Board-er copper MOSFET-er cheye beshi gorom hoy (30 A-te {f(E['copper_loss_30A_W'], 1)} W vs {f(E['fet_loss_30A_W'], 2)} W). Khola pheete gulote 12 AWG tar solder korle {f(Wr['copper_loss_30A_W'], 1)} W.",
 "- Ei run-e 3 ta somossa peye thik korechi: GND-er shoru gola, copper-er gorom (tar-er pheete), short-e gate-er 19.7 V (R39 diye 16.1 V).", ""]
open(os.path.join(HERE, "..", "..", "SIMULATION_RESULT.md"), "w").write("\n".join(lines))
print("written", len(lines), "lines")
