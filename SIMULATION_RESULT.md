# Simulation result: 100 A magnetic kill switch

Final runs on the two finished boards, both 100 A with XT90 in / XT90 out, the same circuit and the same 4S-6S design:

- **Through-hole** `kicad/ks_tht.kicad_pcb` (123 x 100 mm, 8 x IRFB3206)
- **SMD** `kicad/ks_smd.kicad_pcb` (4 x IPT007N06N)

The boards have **not been built yet**. These are ngspice simulations of the netlist taken from each PCB (15 scenarios each, `kicad/simulation/run_tht.py --board tht|smd`) plus a DC current solve of each board's own copper (`copper_tht.py --board tht|smd [--wires]`).

## Verdict

- **Through-hole board** (8 x IRFB3206 (TO-220)): all 15 scenarios pass, also with the weakest PC817 (CTR 50 %). Magnet pulled: off in 1.5 ms. Dead short while running: off in 0.43 ms (4S) / 0.44 ms (6S). Magnet in with a shorted ESC side: never turns on. VDS at 100 A: 42 mV.
- **SMD board** (4 x IPT007N06N (TOLL)): all 15 scenarios pass, also with the weakest PC817 (CTR 50 %). Magnet pulled: off in 1.6 ms. Dead short while running: off in 0.45 ms (4S) / 0.48 ms (6S). Magnet in with a shorted ESC side: never turns on. VDS at 100 A: 18 mV.
- **100 A needs the 8 AWG wires.** Without them the board copper alone loses more than the MOSFETs and the MOSFET nearest the XT90s takes far more than its share (section 3).
- **XT90 rating.** An XT90 is rated 45 A continuous and 90 A for short bursts. Thruster bursts of 100 A are normal XT90 use; 100 A for minutes heats each XT90 by several watts. For long 100 A runs use two XT90 per side, or AS150 / XT150 (different footprint).

## 1. Through-hole board: 15 scenarios (ngspice, netlist from `kicad/ks_tht.kicad_pcb`)

| Scenario | What it tests | Result | Pass |
|---|---|---|---|
| `normal_4S` | 4S pack, magnet in, 60 A then 100 A, magnet out | live after 817 ms, pre-charge 1.38 A, 19 A when the MOSFETs close, Vgs 12.8 V, VDS 25.3 mV at 60 A / 42.1 mV at 100 A, off 1.5 ms after the magnet, 14 mJ in the MOSFETs, VIN peak 19.5 V | yes |
| `normal_6S` | 6S pack, same test | live after 819 ms, pre-charge 2.08 A, 19 A when the MOSFETs close, Vgs 12.8 V, VDS 25.3 mV at 60 A / 42.1 mV at 100 A, off 1.5 ms after the magnet, 14 mJ in the MOSFETs, VIN peak 27.9 V | yes |
| `low_4S` | 4S pack nearly empty (13 V), same test | live after 808 ms, pre-charge 1.07 A, 18 A when the MOSFETs close, Vgs 12.8 V, VDS 25.3 mV at 60 A / 42.1 mV at 100 A, off 1.5 ms after the magnet, 14 mJ in the MOSFETs, VIN peak 15.7 V | yes |
| `start_into_short` | magnet in with the ESC side shorted | never goes live, pre-charge 1.39 A then stops, 0.29 J in the 22 Ohm resistors, nothing in the MOSFETs | yes |
| `short_while_running` | dead short on the ESC side while live (4S) | off 0.43 ms after the short, peak 904 A, 0.97 J shared by 8 x IRFB3206, Vgs max 15.7 V, VIN peak 26.6 V | yes |
| `short_while_running_6S` | same on 6S | off 0.44 ms after the short, peak 1344 A, 2.29 J shared by 8 x IRFB3206, Vgs max 16.0 V, VIN peak 36.3 V | yes |
| `chatter_0p8ms` | 0.8 ms sensor chatter (vibration) is ignored | stays live, output 15.3 V at the end | yes |
| `dropout_10ms` | 10 ms sensor dropout while 100 A flows | off 1.3 ms after the dropout | yes |
| `battery_sag_16v8_to_12v` | pack sags 16.8 -> 12 V in 0.2 s at 100 A | stays live, output 10.5 V at the end | yes |
| `fault_hall_stuck` | Hall stuck ON, magnet pulled | reed path kills in 1.5 ms | yes |
| `fault_reed_welded` | reed welded shut, magnet pulled | Hall path kills in 1.5 ms | yes |
| `fault_sensor_cable_cut` | sensor cable cut while live | off in 1.5 ms | yes |
| `fault_hall_vcc_cut` | Hall module loses its 5 V | off in 1.5 ms | yes |
| `fault_hall_signal_shorted` | Hall signal wire shorted to GND | reed path kills in 1.5 ms | yes |
| `hot_plug_magnet_in` | battery plugged in with the magnet already in | normal start: live after 821 ms, pre-charge 1.38 A | yes |

Weakest optocoupler (PC817 / EL357N CTR 50 % instead of 100 %):

| Case | CTR 100 % | CTR 50 % |
|---|---|---|
| 4S normal | Vgs 12.8 V, off in 1.52 ms | live 817 ms, Vgs 12.8 V, off in 1.54 ms |
| 6S normal | Vgs 12.8 V, off in 1.52 ms | live 819 ms, Vgs 12.8 V, off in 1.54 ms |
| magnet in, ESC side shorted | never turns on | never turns on |
| dead short while live, 6S | Vgs 16.0 V, off in 0.44 ms | live 819 ms, Vgs 16.0 V, off in 0.43 ms |
| Hall stuck ON, magnet pulled | Vgs 12.8 V, off in 1.52 ms | live 817 ms, Vgs 12.8 V, off in 1.54 ms |
| 0.8 ms sensor chatter | Vgs 12.8 V | live 817 ms, Vgs 12.8 V, stays live |

The gate drive has enough margin for a weak opto.

Board copper, DC current solve: pours, tracks and pads of VIN, VOUT and GND on a 0.25 mm grid, 2 oz copper at 20 C; each MOSFET is its 25 C maximum Rds(on) + legs between its drain and source pads (`kicad/simulation/copper_tht.py --board tht`). The wires are 8 AWG (8.4 mm2) on every bare strip.

| | As etched | With 8 AWG bare wire on the bare strips |
|---|---|---|
| Copper, battery XT90 + to the MOSFET drains | 0.374 mOhm | 0.072 mOhm |
| Copper, MOSFET sources to the ESC XT90 + | 0.177 mOhm | 0.058 mOhm |
| Copper, GND return (ESC XT90 - to battery XT90 -) | 0.380 mOhm | 0.116 mOhm |
| 8 MOSFETs in parallel (3.34 mOhm each, 25 C max) | 0.566 mOhm | 0.422 mOhm |
| Current share Q1 ... Q8 (%) | 28.5 / 19.0 / 14.6 / 11.0 / 8.6 / 6.9 / 5.9 / 5.4 | 15.1 / 13.6 / 13.1 / 12.3 / 11.8 / 11.5 / 11.3 / 11.2 |
| Busiest MOSFET at 100 A | 28.5 A | 15.1 A |
| Loss at 60 A: copper / MOSFETs | 3.4 W / 2.0 W | 0.9 W / 1.5 W |
| Loss at 100 A: copper / MOSFETs | 9.3 W / 5.7 W | 2.5 W / 4.2 W |
| Drop in the copper at 100 A | 93 mV | 25 mV |

Heat with the wires at 100 A continuous, MOSFETs hot (Rds(on) x1.5 at about 100 C): busiest MOSFET 15.1 A, about 1.11 W; average 0.76 W each. Current-density maps: `kicad/simulation/copper_tht_vin.png`, `_vout`, `_gnd` (and `*_wires.png`).

## 2. SMD board: 15 scenarios (ngspice, netlist from `kicad/ks_smd.kicad_pcb`)

| Scenario | What it tests | Result | Pass |
|---|---|---|---|
| `normal_4S` | 4S pack, magnet in, 60 A then 100 A, magnet out | live after 816 ms, pre-charge 1.38 A, 20 A when the MOSFETs close, Vgs 13.3 V, VDS 10.9 mV at 60 A / 18.1 mV at 100 A, off 1.6 ms after the magnet, 13 mJ in the MOSFETs, VIN peak 18.9 V | yes |
| `normal_6S` | 6S pack, same test | live after 819 ms, pre-charge 2.07 A, 20 A when the MOSFETs close, Vgs 13.3 V, VDS 10.9 mV at 60 A / 18.1 mV at 100 A, off 1.6 ms after the magnet, 13 mJ in the MOSFETs, VIN peak 27.3 V | yes |
| `low_4S` | 4S pack nearly empty (13 V), same test | live after 808 ms, pre-charge 1.06 A, 20 A when the MOSFETs close, Vgs 13.3 V, VDS 10.9 mV at 60 A / 18.1 mV at 100 A, off 1.6 ms after the magnet, 13 mJ in the MOSFETs, VIN peak 15.1 V | yes |
| `start_into_short` | magnet in with the ESC side shorted | never goes live, pre-charge 1.38 A then stops, 0.29 J in the 22 Ohm resistors, nothing in the MOSFETs | yes |
| `short_while_running` | dead short on the ESC side while live (4S) | off 0.45 ms after the short, peak 921 A, 1.01 J shared by 4 x IPT007N06N, Vgs max 15.7 V, VIN peak 25.3 V | yes |
| `short_while_running_6S` | same on 6S | off 0.48 ms after the short, peak 1377 A, 2.43 J shared by 4 x IPT007N06N, Vgs max 15.9 V, VIN peak 34.6 V | yes |
| `chatter_0p8ms` | 0.8 ms sensor chatter (vibration) is ignored | stays live, output 15.3 V at the end | yes |
| `dropout_10ms` | 10 ms sensor dropout while 100 A flows | off 1.4 ms after the dropout | yes |
| `battery_sag_16v8_to_12v` | pack sags 16.8 -> 12 V in 0.2 s at 100 A | stays live, output 10.5 V at the end | yes |
| `fault_hall_stuck` | Hall stuck ON, magnet pulled | reed path kills in 1.6 ms | yes |
| `fault_reed_welded` | reed welded shut, magnet pulled | Hall path kills in 1.5 ms | yes |
| `fault_sensor_cable_cut` | sensor cable cut while live | off in 1.6 ms | yes |
| `fault_hall_vcc_cut` | Hall module loses its 5 V | off in 1.5 ms | yes |
| `fault_hall_signal_shorted` | Hall signal wire shorted to GND | reed path kills in 1.6 ms | yes |
| `hot_plug_magnet_in` | battery plugged in with the magnet already in | normal start: live after 821 ms, pre-charge 1.38 A | yes |

Weakest optocoupler (PC817 / EL357N CTR 50 % instead of 100 %):

| Case | CTR 100 % | CTR 50 % |
|---|---|---|
| 4S normal | Vgs 13.3 V, off in 1.56 ms | live 816 ms, Vgs 13.3 V, off in 1.57 ms |
| 6S normal | Vgs 13.3 V, off in 1.56 ms | live 819 ms, Vgs 13.3 V, off in 1.57 ms |
| magnet in, ESC side shorted | never turns on | never turns on |
| dead short while live, 6S | Vgs 15.9 V, off in 0.48 ms | live 819 ms, Vgs 15.9 V, off in 0.47 ms |
| Hall stuck ON, magnet pulled | Vgs 13.3 V, off in 1.56 ms | live 817 ms, Vgs 13.3 V, off in 1.56 ms |
| 0.8 ms sensor chatter | Vgs 13.3 V | live 816 ms, Vgs 13.3 V, stays live |

The gate drive has enough margin for a weak opto.

## 3. What to do with this

- Solder 8 AWG bare copper wire on every bare strip before running more than about 30 A: VIN and VOUT on top, and the C-shaped GND link underneath from the ESC XT90 minus to the battery XT90 minus.
- Through-hole board: a flat copper or aluminium bar bolted across all 8 MOSFET tabs is optional. The tabs are all VIN, so no insulators are needed. It spreads the heat, so the MOSFET nearest the XT90s runs as cool as the others.
- Put a 125-150 A fuse (ANL / MIDI / MEGA) in the battery + lead close to the battery. The board switches off a dead short in under 1 ms, but the fuse protects the wiring between the battery and the board.
- First power-up on a current-limited bench supply, then one ESC, then full current. Feel the MOSFETs and the XT90s after a long full-throttle run.

## 4. Not simulated

- Temperature over time (only losses are computed); copper resistance rises about 20 % when hot.
- XT90 contact resistance, battery wiring and the ESCs themselves.
- Part tolerances other than the opto CTR; comparator and opto delays are simplified; the B0512S isolated supply is a behavioural model.
- EMI, vibration, water and the mechanical plug.

## Bangla-English summary

- Through-hole board (8 x IRFB3206 (TO-220)): 15 ta simulation-i pass; magnet tanle 1.5 ms-e off, chalu obosthay short hole 0.43 ms-e off, short thakle chalu-i hoy na.
- SMD board (4 x IPT007N06N (TOLL)): 15 ta simulation-i pass; magnet tanle 1.6 ms-e off, chalu obosthay short hole 0.45 ms-e off, short thakle chalu-i hoy na.
- 100 A-te bare strip gulote 8 AWG tar lagbei: tar chara copper-e 9.3 W gorom, Q1 ekai 29 A ney; tar dile copper 2.5 W ar protita MOSFET 11-15 A.
- XT90 45 A continuous / 90 A burst rated: thruster-er short 100 A burst thik ache; onek khon 100 A cholle XT90 gorom hobe (2 ta XT90 parallel ba AS150).
- Battery + tare 125-150 A fuse rakho.
