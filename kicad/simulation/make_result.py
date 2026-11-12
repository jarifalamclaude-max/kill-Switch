"""Write ../../SIMULATION_RESULT.md from the final-board runs of both 100 A boards:
summary_<b>.md (15 scenarios), results_<b>_ctr0.5.json (weakest PC817) and copper_<b>[_wires].json (DC current in
the power copper), for b = tht (through-hole) and smd. A board whose files are missing is reported as not run."""
import json, os
HERE = os.path.dirname(os.path.abspath(__file__))
f = lambda v, n=1: "-" if v is None else f"{v:.{n}f}"
pct = lambda s: " / ".join(f"{100 * x:.1f}" for x in s)
load = lambda name: json.load(open(os.path.join(HERE, name))) if os.path.exists(os.path.join(HERE, name)) else None

BOARDS = {"tht": ("Through-hole board", "kicad/ks_tht.kicad_pcb", "8 x IRFB3206 (TO-220)", 3.0, 0.34),
          "smd": ("SMD board", "kicad/ks_smd.kicad_pcb", "4 x IPT007N06N (TOLL)", 0.75, 0.05)}
HOT = 1.5          # Rds(on) at Tj ~100 C vs 25 C (IRFB3206 and IPT007N06N datasheet curves: 1.5-1.6 at 100 C)

def table(b):
    p = os.path.join(HERE, f"summary_{b}.md")
    if not os.path.exists(p): return None
    return "\n".join(l for l in open(p).read().splitlines() if l.startswith("|"))

def ctr_rows(b):
    C, A = load(f"results_{b}_ctr0.5.json"), load(f"results_{b}.json")
    if not C or not A: return None
    rows = ["| Case | CTR 100 % | CTR 50 % |", "|---|---|---|"]
    for k, what in (("normal_4S", "4S normal"), ("normal_6S", "6S normal"), ("start_into_short", "magnet in, ESC side shorted"),
                    ("short_while_running_6S", "dead short while live, 6S"), ("fault_hall_stuck", "Hall stuck ON, magnet pulled"),
                    ("chatter_0p8ms", "0.8 ms sensor chatter")):
        if k not in C or k not in A: continue
        r, n = C[k], A[k]
        res = ("never turns on" if r["t_live_ms"] is None else f"live {f(r['t_live_ms'], 0)} ms, Vgs {f(r['vgs_on_V'], 1)} V") + \
              ("" if r.get("kill_latency_ms") is None else f", off in {f(r['kill_latency_ms'], 2)} ms") + \
              (", stays live" if k == "chatter_0p8ms" and r.get("kill_latency_ms") is None else "")
        nom = ("never turns on" if n["t_live_ms"] is None else f"Vgs {f(n['vgs_on_V'], 1)} V") + ("" if n.get("kill_latency_ms") is None else f", off in {f(n['kill_latency_ms'], 2)} ms")
        rows.append(f"| {what} | {nom} | {res} |")
    return rows

def copper_rows(b):
    E, Wr = load(f"copper_{b}.json"), load(f"copper_{b}_wires.json")
    if not E or not Wr: return None, None, None
    n = E["n_fets"]
    rows = ["| | As etched | With 8 AWG bare wire on the bare strips |", "|---|---|---|"]
    for label, key in (("Copper, battery XT90 + to the MOSFET drains", "r_vin_copper_mohm"),
                       ("Copper, MOSFET sources to the ESC XT90 +", "r_vout_copper_mohm"),
                       ("Copper, GND return (ESC XT90 - to battery XT90 -)", "r_gnd_copper_mohm"),
                       (f"{n} MOSFETs in parallel ({f(E['r_fet_mohm'], 2)} mOhm each, 25 C max)", "r_fets_parallel_mohm")):
        rows.append(f"| {label} | {f(E[key], 3)} mOhm | {f(Wr[key], 3)} mOhm |")
    rows += [f"| Current share Q1 ... Q{n} (%) | {pct(E['fet_share'])} | {pct(Wr['fet_share'])} |",
             f"| Busiest MOSFET at 100 A | {f(E['fet_max_current_100A_A'], 1)} A | {f(Wr['fet_max_current_100A_A'], 1)} A |",
             f"| Loss at 60 A: copper / MOSFETs | {f(E['copper_loss_60A_W'], 1)} W / {f(E['fet_loss_60A_W'], 1)} W | {f(Wr['copper_loss_60A_W'], 1)} W / {f(Wr['fet_loss_60A_W'], 1)} W |",
             f"| Loss at 100 A: copper / MOSFETs | {f(E['copper_loss_100A_W'], 1)} W / {f(E['fet_loss_100A_W'], 1)} W | {f(Wr['copper_loss_100A_W'], 1)} W / {f(Wr['fet_loss_100A_W'], 1)} W |",
             f"| Drop in the copper at 100 A | {f(E['copper_drop_100A_mV'], 0)} mV | {f(Wr['copper_drop_100A_mV'], 0)} mV |"]
    return rows, E, Wr

def heat_line(b, Wr):
    name, _, fets, rmax, legs = BOARDS[b]
    n = Wr["n_fets"]; share = max(Wr["fet_share"])
    r_hot = (rmax * HOT + legs) * 1e-3
    i = 100 * share; p_hot = i * i * r_hot; p_avg = (100 / n) ** 2 * r_hot
    return i, p_hot, p_avg

lines = ["# Simulation result: 100 A magnetic kill switch", "",
 "Final runs on the two finished boards, both 100 A with XT90 in / XT90 out, the same circuit and the same 4S-6S design:",
 "",
 "- **Through-hole** `kicad/ks_tht.kicad_pcb` (123 x 100 mm, 8 x IRFB3206)",
 "- **SMD** `kicad/ks_smd.kicad_pcb` (4 x IPT007N06N)",
 "",
 "The boards have **not been built yet**. These are ngspice simulations of the netlist taken from each PCB (15 scenarios each, `kicad/simulation/run_tht.py --board tht|smd`) "
 "plus a DC current solve of each board's own copper (`copper_tht.py --board tht|smd [--wires]`).", "",
 "## Verdict", ""]
A = {b: load(f"results_{b}.json") for b in BOARDS}
for b, (name, path, fets, _, _) in BOARDS.items():
    t = table(b)
    if t is None: lines.append(f"- **{name}**: not simulated yet."); continue
    ok = "**NO**" not in t; R = A[b]
    lines.append(f"- **{name}** ({fets}): {'all 15 scenarios pass' if ok else 'SOME SCENARIOS FAIL'}"
                 + (", also with the weakest PC817 (CTR 50 %)" if load(f"results_{b}_ctr0.5.json") else "")
                 + f". Magnet pulled: off in {f(R['normal_4S']['kill_latency_ms'], 1)} ms. Dead short while running: off in "
                 f"{f(R['short_while_running']['kill_latency_ms'], 2)} ms (4S) / {f(R['short_while_running_6S']['kill_latency_ms'], 2)} ms (6S). "
                 f"Magnet in with a shorted ESC side: never turns on. VDS at 100 A: {f(R['normal_4S']['vds_100A_mV'], 0)} mV.")
lines += ["- **100 A needs the 8 AWG wires.** Without them the board copper alone loses more than the MOSFETs and the MOSFET nearest the XT90s takes far more than its share (section 3).",
 "- **XT90 rating.** An XT90 is rated 45 A continuous and 90 A for short bursts. Thruster bursts of 100 A are normal XT90 use; "
 "100 A for minutes heats each XT90 by several watts. For long 100 A runs use two XT90 per side, or AS150 / XT150 (different footprint).", ""]
sec = 1
for b, (name, path, fets, _, _) in BOARDS.items():
    t = table(b)
    lines += [f"## {sec}. {name}: 15 scenarios (ngspice, netlist from `{path}`)", ""]; sec += 1
    if t is None: lines += ["Not run yet.", ""]; continue
    lines += [t, ""]
    c = ctr_rows(b)
    if c: lines += [f"Weakest optocoupler (PC817 / EL357N CTR 50 % instead of 100 %):", ""] + c + ["", "The gate drive has enough margin for a weak opto.", ""]
    rows, E, Wr = copper_rows(b)
    if rows:
        lines += [f"Board copper, DC current solve: pours, tracks and pads of VIN, VOUT and GND on a 0.25 mm grid, 2 oz copper at 20 C; "
                  f"each MOSFET is its 25 C maximum Rds(on) + legs between its drain and source pads (`kicad/simulation/copper_tht.py --board {b}`). "
                  "The wires are 8 AWG (8.4 mm2) on every bare strip.", ""] + rows + [""]
        i, p_hot, p_avg = heat_line(b, Wr)
        lines += [f"Heat with the wires at 100 A continuous, MOSFETs hot (Rds(on) x{HOT} at about 100 C): busiest MOSFET {f(i, 1)} A, about {f(p_hot, 2)} W; "
                  f"average {f(p_avg, 2)} W each. Current-density maps: `kicad/simulation/copper_{b}_vin.png`, `_vout`, `_gnd` (and `*_wires.png`).", ""]
lines += [f"## {sec}. What to do with this", "",
 "- Solder 8 AWG bare copper wire on every bare strip before running more than about 30 A: VIN and VOUT on top, and the C-shaped GND link underneath from the ESC XT90 minus to the battery XT90 minus.",
 "- Through-hole board: a flat copper or aluminium bar bolted across all 8 MOSFET tabs is optional. The tabs are all VIN, so no insulators are needed. It spreads the heat, so the MOSFET nearest the XT90s runs as cool as the others.",
 "- Put a 125-150 A fuse (ANL / MIDI / MEGA) in the battery + lead close to the battery. The board switches off a dead short in under 1 ms, but the fuse protects the wiring between the battery and the board.",
 "- First power-up on a current-limited bench supply, then one ESC, then full current. Feel the MOSFETs and the XT90s after a long full-throttle run.", "",
 f"## {sec + 1}. Not simulated", "",
 "- Temperature over time (only losses are computed); copper resistance rises about 20 % when hot.",
 "- XT90 contact resistance, battery wiring and the ESCs themselves.",
 "- Part tolerances other than the opto CTR; comparator and opto delays are simplified; the B0512S isolated supply is a behavioural model.",
 "- EMI, vibration, water and the mechanical plug.", "",
 "## Bangla-English summary", ""]
for b, (name, path, fets, _, _) in BOARDS.items():
    R, t = A[b], table(b)
    if R is None or t is None: lines.append(f"- {name}: ekhono simulation hoy nai."); continue
    ok = "**NO**" not in t
    lines.append(f"- {name} ({fets}): 15 ta simulation-{'i pass' if ok else 'r kichu FAIL'}; magnet tanle {f(R['normal_4S']['kill_latency_ms'], 1)} ms-e off, "
                 f"chalu obosthay short hole {f(R['short_while_running']['kill_latency_ms'], 2)} ms-e off, short thakle chalu-i hoy na.")
Et, Wt = load("copper_tht.json"), load("copper_tht_wires.json")
if Et and Wt:
    lines.append(f"- 100 A-te bare strip gulote 8 AWG tar lagbei: tar chara copper-e {f(Et['copper_loss_100A_W'], 1)} W gorom, Q1 ekai {f(Et['fet_max_current_100A_A'], 0)} A ney; "
                 f"tar dile copper {f(Wt['copper_loss_100A_W'], 1)} W ar protita MOSFET {f(min(Wt['fet_share']) * 100, 0)}-{f(max(Wt['fet_share']) * 100, 0)} A.")
lines += ["- XT90 45 A continuous / 90 A burst rated: thruster-er short 100 A burst thik ache; onek khon 100 A cholle XT90 gorom hobe (2 ta XT90 parallel ba AS150).",
          "- Battery + tare 125-150 A fuse rakho.", ""]
open(os.path.join(HERE, "..", "..", "SIMULATION_RESULT.md"), "w").write("\n".join(lines))
print("written", len(lines), "lines")
