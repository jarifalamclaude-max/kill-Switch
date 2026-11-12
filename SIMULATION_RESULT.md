# Simulation result: through-hole kill switch

Final run on the finished board `kicad/ks_tht.kicad_pcb` (XT60 in/out, 4 x IRFB3206, 30 A continuous / 60 A burst). The board has **not been built yet**: these are ngspice simulations of the netlist taken from the PCB, plus a DC current solve of the board's own copper.

## Verdict

- All 15 circuit scenarios pass, also with the weakest PC817 optocoupler (CTR 50 %).
- Magnet pulled: power off in 1.6 ms. Dead short while running: off in 0.47 ms (4S) / 0.47 ms (6S). Magnet in with the ESC side shorted: never turns on.
- The board's own copper loses more than the MOSFETs: 2.4 W against 0.75 W at 30 A. Soldering a 12 AWG bare wire on the bare strips brings the copper down to 1.2 W.
- Three problems found in this final round were fixed on the board (below).

## 1. Circuit: 15 scenarios (ngspice, netlist from the PCB)

| Scenario | What it tests | Result | Pass |
|---|---|---|---|
| `normal_4S` | 4S pack, magnet in, 30 A then 60 A, magnet out | live after 816 ms, pre-charge 1.38 A, 19 A when the MOSFETs close, Vgs 13.3 V, VDS 25.2 mV at 30 A / 50.2 mV at 60 A, off 1.6 ms after the magnet, 9 mJ in the MOSFETs, VIN peak 17.6 V | yes |
| `normal_6S` | 6S pack, same test | live after 819 ms, pre-charge 2.08 A, 19 A when the MOSFETs close, Vgs 13.3 V, VDS 25.2 mV at 30 A / 50.2 mV at 60 A, off 1.6 ms after the magnet, 11 mJ in the MOSFETs, VIN peak 25.9 V | yes |
| `low_4S` | 4S pack nearly empty (13 V), same test | live after 807 ms, pre-charge 1.07 A, 19 A when the MOSFETs close, Vgs 13.3 V, VDS 25.2 mV at 30 A / 50.2 mV at 60 A, off 1.6 ms after the magnet, 9 mJ in the MOSFETs, VIN peak 13.8 V | yes |
| `start_into_short` | magnet in with the ESC side shorted | never goes live, pre-charge 1.39 A then stops, 0.29 J in the 22 Ohm resistors, nothing in the MOSFETs | yes |
| `short_while_running` | dead short on the ESC side while live (4S) | off 0.47 ms after the short, peak 872 A, 1.09 J shared by 4 MOSFETs, Vgs max 15.9 V, VIN peak 21.2 V | yes |
| `short_while_running_6S` | same on 6S | off 0.47 ms after the short, peak 1298 A, 2.56 J shared by 4 MOSFETs, Vgs max 16.1 V, VIN peak 30.6 V | yes |
| `chatter_0p8ms` | 0.8 ms sensor chatter (vibration) is ignored | stays live, output 16.3 V at the end | yes |
| `dropout_10ms` | 10 ms sensor dropout while 30 A flows | off 1.4 ms after the dropout | yes |
| `battery_sag_16v8_to_12v` | pack sags 16.8 -> 12 V in 0.2 s at 60 A | stays live, output 11.0 V at the end | yes |
| `fault_hall_stuck` | Hall stuck ON, magnet pulled | reed path kills in 1.6 ms | yes |
| `fault_reed_welded` | reed welded shut, magnet pulled | Hall path kills in 1.6 ms | yes |
| `fault_sensor_cable_cut` | sensor cable cut while live | off in 1.6 ms | yes |
| `fault_hall_vcc_cut` | Hall module loses its 5 V | off in 1.5 ms | yes |
| `fault_hall_signal_shorted` | Hall signal wire shorted to GND | reed path kills in 1.6 ms | yes |
| `hot_plug_magnet_in` | battery plugged in with the magnet already in | normal start: live after 821 ms, pre-charge 1.38 A | yes |

## 2. Weakest optocoupler (PC817 CTR 50 % instead of 100 %)

| Case | CTR 100 % | CTR 50 % |
|---|---|---|
| 4S normal | Vgs 13.3 V, off in 1.59 ms | live 816 ms, Vgs 13.3 V, off in 1.61 ms |
| 6S normal | Vgs 13.3 V, off in 1.59 ms | live 819 ms, Vgs 13.3 V, off in 1.61 ms |
| magnet in, ESC side shorted | never turns on | never turns on |
| dead short while live, 6S | Vgs 16.1 V, off in 0.47 ms | live 819 ms, Vgs 16.1 V, off in 0.47 ms |
| Hall stuck ON, magnet pulled | Vgs 13.3 V, off in 1.59 ms | live 816 ms, Vgs 13.3 V, off in 1.61 ms |
| 0.8 ms sensor chatter | Vgs 13.3 V | live 816 ms, Vgs 13.3 V, stays live |

The gate drive has enough margin: nothing changes by more than 0.05 ms or 0.1 V.

## 3. Board copper: DC current solve

The filled pours, tracks and pads of VIN, VOUT and GND are taken from the PCB on a 0.25 mm grid and solved as 2 oz copper (70 um, 20 C). The 4 MOSFETs are 3.34 mOhm each between their drain and source pads, so the solve also shows how the current shares between them (`kicad/simulation/copper_tht.py`).

| | As etched | With 12 AWG wire on the bare strips |
|---|---|---|
| Copper resistance, battery XT60 + to MOSFET drains | 0.85 mOhm | 0.25 mOhm |
| Copper resistance, MOSFET sources to ESC XT60 + | 0.80 mOhm | 0.27 mOhm |
| Copper resistance, GND return (ESC XT60 - to battery XT60 -) | 1.00 mOhm | 0.77 mOhm |
| 4 MOSFETs in parallel (3.34 mOhm each) | 0.84 mOhm | 0.84 mOhm |
| Current share Q1 / Q2 / Q3 / Q4 (%) | 26.7 / 23.7 / 23.3 / 26.3 | 25.4 / 24.6 / 24.6 / 25.4 |
| Loss at 30 A: copper / MOSFETs | 2.38 W / 0.75 W | 1.16 W / 0.75 W |
| Loss at 60 A burst: copper / MOSFETs | 9.5 W / 3.0 W | 4.6 W / 3.0 W |
| Drop in the copper at 30 A / 60 A | 79 / 159 mV | 39 / 77 mV |
| Most crowded spot at 60 A | 20 A per mm of width, GND next to the battery XT60 pin | at the ends of the wires, where current moves from the pour into the wire |

Current-density maps: `kicad/simulation/copper_vin.png`, `copper_vout.png`, `copper_gnd.png` (and `*_wires.png`).

## 4. Fixed because of this run

1. **GND neck.** The first copper solve found the GND return squeezed through a gap in the bottom plane (18 A/mm at 60 A), between the VIN_K track and where the gate bus left the power section. The gate bus now leaves at the right end and VIN_K runs on the top layer; the most crowded GND spot is now at the XT60 pin itself.
2. **Copper loss.** Bare strips without solder mask now run along the VIN and VOUT paths (top) and the GND path (bottom), so a 12 AWG bare copper wire or a thick solder bead can be added: copper loss at 30 A drops from 2.4 W to 1.2 W, and the 4 MOSFETs share the current within 1 %.
3. **Gate overshoot.** In a 6S dead short the gate briefly reached 19.7 V (IRFB3206 limit 20 V), because the soft-start capacitor held the gate up while VOUT fell. A 100 Ohm resistor (R39) in series with it brings the peak to 16.1 V; start-up and turn-off are unchanged.

## 5. What to do with this

- Up to about 30 A continuous the board is fine as etched (about 3 W in total, spread over the board).
- For frequent 60 A bursts, solder a 12 AWG bare copper wire on each bare strip (VIN and VOUT on top, GND underneath).
- Keep the 40 A fuse in the battery lead: overloads below a hard short are the fuse's job.
- First power-up on a current-limited bench supply, then one ESC, then full current.

## 6. Not simulated

- Temperature over time (only losses are computed), and copper resistance rising about 20 % when hot.
- Real part tolerances other than the opto CTR; comparator and opto delays are simplified; the B0512S is a behavioural model.
- EMI, vibration, water and the mechanical plug.

## Bangla-English summary

- Final board-e 15 ta simulation-i pass, kharap PC817 (CTR 50 %) diyeo.
- Magnet tanle 1.6 ms-e off; chalu obosthay short hole 0.47 ms-e off; short obosthay chalu-i hoy na.
- Board-er copper MOSFET-er cheye beshi gorom hoy (30 A-te 2.4 W vs 0.75 W). Khola pheete gulote 12 AWG tar solder korle 1.2 W.
- Ei run-e 3 ta somossa peye thik korechi: GND-er shoru gola, copper-er gorom (tar-er pheete), short-e gate-er 19.7 V (R39 diye 16.1 V).
