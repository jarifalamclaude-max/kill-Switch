# Magnetic Kill Switch (100 A)

Magnetic kill switch for an underwater robot on a 4S–6S LiPo. The board sits inside the hull and the magnet plug sits outside. Plug in: the ESCs get power. Pull the plug out: power is cut about 1.5 ms later.

There are two boards with the **same circuit**, both for **100 A** with **XT90 in (battery) and XT90 out (ESCs)**:

| | Through-hole | SMD (small) |
|---|---|---|
| Board | `kicad/ks_tht.kicad_pcb`, 123 × 100 mm | `kicad/ks_smd.kicad_pcb`, 80 × 75 mm |
| Parts | 108 (4 of them test pads), all through-hole | 96 (4 of them test pads): TOLL, SOIC, SOT-23, 0805; XT90s, B0512S and sensor plugs through-hole |
| Switch | 8 × IRFB3206 (TO-220) | 4 × IPT007N06N (TOLL) |
| Controller | one LM339 + isolated gate supply (B0512S) + PC817 | same circuit in SMD parts |
| 100 A path | bare copper strips with 8 AWG bare wire soldered on | same idea |
| Copper | 2 layers, 2 oz, green solder mask | same |

**Neither board has been built or tested yet.** Everything below comes from calculations, KiCad DRC (0 violations, 0 unconnected on both boards) and ngspice simulations of the netlists taken from the PCBs: [`SIMULATION_RESULT.md`](SIMULATION_RESULT.md).

![Through-hole board, top](docs/board_tht_top.png)

Schematic (drawn from the PCB netlist): [`docs/kill_switch_tht_schematic.png`](docs/kill_switch_tht_schematic.png), [SVG](docs/kill_switch_tht_schematic.svg).

## Opening in KiCad (3D view)

Open `kicad/ks_tht.kicad_pro` (or `ks_smd.kicad_pro`) in **KiCad 7, 8, 9 or 10**. Every 3D model the boards use is in `kicad/3dmodels/` and the footprints point at it through `${KIPRJMOD}`. The 3D view shows all parts on any of those versions, even without KiCad's 3D library installed. Keep the `kicad/` folder together (the zips do). The XT90 footprints are in the project library `kicad/ks.pretty`. KiCad 6 cannot open KiCad 7 files.

## Why no reed switch in the power path

A reed switch carries well under 1 A and burns at the arc of a DC break at tens of amps. So the magnet only drives sensors. The current is switched by MOSFETs.

## How it works

1. **Two sensors in series.** A Hall module (KY-003, A3144) and a reed door contact (MC-38) must both see the magnet before anything turns on. A Hall stuck on, a welded reed, a cut cable, a Hall without power or a shorted Hall wire still kill (all simulated).
2. **Arm delay and debounce.** The sensors pull ARM high. ARM charges EN through 100 kΩ / 10 µF, so the switch starts about 0.8 s after the plug goes in. Losing ARM empties EN through a 2N3904 in about 1.5 ms. A sensor gap shorter than about 1 ms (vibration) is ignored, and a real pull kills in about 1.5 ms.
3. **Pre-charge first.** An IRF9540N charges the ESC capacitors through a 0.5 A PTC and 2 × 22 Ω (1.4 A at 4S, 2.1 A at 6S). Without it a few hundred amps would rush into cold capacitors.
4. **One LM339 does the sequencing.**
   - EN above 2.5 V starts the pre-charge.
   - If VOUT does not keep up with a ramp that rises with VIN (a shorted ESC bus), the pre-charge stops and stays off until the magnet is pulled.
   - The main MOSFETs close only when VOUT is above half of VIN.
   - The same comparator trips when a short pulls VOUT down while running.
5. **Main switch.** 8 × IRFB3206 in parallel (through-hole board) as a high-side switch.
   - The gate supply is an isolated 5 V → 12 V module (B0512S) whose output floats on the MOSFET sources, so the gates get about 12.8 V on any pack.
   - A PC817 connects it to the gates through a diode and 10 kΩ. A 220 nF capacitor (with 100 Ω) makes VOUT ramp up gently: 19 A peak when the MOSFETs close.
   - When the opto lets go, a BC327 pulls the gates down fast (R37 = 47 kΩ lets it pull them all the way below 1.5 V).
6. **Clamps.** 1.5KE33A TVS on the battery and ESC sides, P6KE18A between gate and source, 15 V zener on the gate supply.
7. **LEDs.** Blue HALL and blue REED (each sensor sees the magnet) and red LIVE (ESCs powered).

Not included (to keep it simple): under- and over-voltage lockout, a second independent kill path, an over-current trip below a hard short, and a status line to the Jetson. **Put a 125–150 A fuse (ANL / MIDI / MEGA) in the battery + lead.** The board kills a hard short in about 0.5 ms; an overload below that is the fuse's job.

## Numbers (through-hole board, simulated)

| | Value |
|---|---|
| MOSFET drop, 8 in parallel | 25 mV at 60 A, 42 mV at 100 A |
| Board copper at 100 A, with the 8 AWG wires | 2.5 W (without the wires: 9.3 W) |
| MOSFETs at 100 A, with the wires | 4.2 W in total (25 °C max Rds(on)), 11–15 A each |
| Gate voltage | 12.8 V on 4S and 6S |
| Kill time after the magnet leaves | 1.5 ms (4S and 6S), also with any one sensor fault; 14 mJ in the MOSFETs |
| Ignored sensor gap | 0.8 ms tested (vibration) |
| Short on the ESC side while live | off in 0.43 / 0.44 ms (4S / 6S); 1.0 J / 2.3 J shared by the 8 MOSFETs; gate peak 15.7 / 16.0 V; battery side peak 26.6 / 36.3 V |
| Magnet in with the ESC side shorted | never turns on; 0.29 J in the pre-charge resistors |
| Battery spike when killing 100 A | 19.5 V peak on 4S, 27.9 V on 6S |
| SMD board (4 × IPT007N06N) | 18 mV at 100 A, gate 13.3 V, kill 1.6 ms, short off in 0.45 / 0.48 ms |

All 15 scenarios for each board, the weakest optocoupler, and the copper current solve: [`SIMULATION_RESULT.md`](SIMULATION_RESULT.md). Magnet field, sensor placement and plug retention: [`calc/report.md`](calc/report.md).

## 100 A: the bare strips and 8 AWG wire

PCB copper alone cannot carry 100 A: the 2 oz copper would lose 9 W, and the MOSFET nearest the XT90s would take 29 A of the 100. So every 100 A path has a **bare copper strip** (no solder mask). Solder **8 AWG bare copper wire** (3.3 mm solid, or bare earthing wire) along each strip:

- **VOUT** (top, above the MOSFET pins): from the J2 + pin along the whole strip.
- **VIN** (top, below the MOSFETs, under their tabs): from the J1 + pin along the whole strip.
- **GND** (bottom): bend the wire into a C on the bare strip, from the J2 − pin to the J1 − pin.

With the wires the copper loses 2.5 W at 100 A and the 8 MOSFETs share the current within 11–15 A each. The MOSFET tabs are all VIN. A flat copper or aluminium bar bolted across all 8 tabs (M3, no insulators needed) is optional; it spreads the heat so that Q1 runs as cool as the others.

## XT90

- J1 = **XT90PW-M** (male, right-angle PCB) for the battery's XT90; J2 = **XT90PW-F** (female) for the ESC harness. Both face out of the left edge.
- An XT90 is rated **45 A continuous, 90 A burst**. Short 100 A bursts (all thrusters at full throttle for seconds) are normal XT90 use; 100 A for minutes heats each XT90 by several watts. For long 100 A runs use two XT90s per side, or AS150 / XT150 (different footprint).
- Use 8 AWG silicone cable from the battery and to the ESCs, as short as possible.

## Buying

Full lists with quantities: [`kicad/bom_tht_grouped.csv`](kicad/bom_tht_grouped.csv) (through-hole) and [`kicad/bom_smd_grouped.csv`](kicad/bom_smd_grouped.csv) (SMD). Main parts of the through-hole board:

- 8 × IRFB3206PbF (TO-220), 1 × IRF9540NPbF.
- AMASS XT90PW-M and XT90PW-F (right-angle PCB mount).
- Mornsun B0512S-1WR3 (5 V → 12 V isolated, SIP-4). Check its pin order against the board: 1 GND, 2 Vin, 3 0 V, 4 +Vo.
- LM339N (DIP-14), PC817 (DIP-4), L7805CV. A K7805-500R3 or R-78E5.0-0.5 switching module fits the 7805's holes and runs cooler on 6S.
- 2 × 1.5KE33A, P6KE18A, 1N4744A, 1N4007, 2 × 1N4148, BZX55C12.
- Littelfuse RXEF050 PTC, 2 × 22 Ω 2 W.
- About 0.35 m of 8 AWG bare copper wire, and a 125–150 A fuse for the battery lead.
- KY-003 Hall module. Check its pin order (S, +, −) with a multimeter: some clones swap + and −.
- MC-38 wired door contact, sold in Bangladesh ([ElectronicsBD](https://electronics.com.bd/components-price-in-Bangladesh/mc-38-wired-door-window-sensor-magnetic-switch-home-alarm-system), [BDTronics](https://www.bdtronics.com/mc38-magnetic-switch.html)). Listings disagree on "normally open" and "normally closed", so check with a multimeter: it must close when the magnet is near.
- N52 magnet, 15 mm diameter × 10 mm, axially magnetised.

**Ordering the PCB (JLCPCB):** upload `kill_switch_tht_gerber_jlcpcb.zip` (or `kill_switch_smd_gerber_jlcpcb.zip`). Set 2 layers, 1.6 mm, **2 oz outer copper**, green solder mask (the default), HASL.

## Wiring

- Battery → 125–150 A fuse → J1 (XT90, battery). ESC harness → J2 (XT90, ESCs). The ground passes through the board from J2 − to J1 − along the bottom GND wire.
- J3 → KY-003 (1 = S, 2 = +, 3 = −). J4 → MC-38 (2 wires, either way round).
- Run the battery + and − as a twisted pair, at least 10 cm from the sensors.
- There is no reverse-polarity protection on the power path. The XT90 is keyed, so keep it that way.

## Mechanics (side mount)

- The dock is glued to the outside of the hull (no holes through the hull). The hull wall must be non-magnetic: acrylic, polycarbonate or aluminium, not steel.
- The plug carries the magnet with its **south pole toward the hull**: the A3144 only reacts to a south pole on its printed face. If the HALL LED stays off with the plug in, flip the magnet.
- An O-ring on the plug snaps into a groove in the dock. Pulling it out takes 10–20 N, against 0.29 N of plug weight, 1.4 N at 5 g of vibration and 1.2 N of water drag at 1.5 m/s. A slot along the dock bore lets water in and out, so there is no suction and no trapped water.
- Inside, a printed bracket holds the A3144 flat against the wall on the plug's axis (9.5 mm from the magnet, about 104 mT, 3× margin) and the MC-38 12 mm off the axis.
- Keep steel away from the sensors. Park the pulled plug at least 120 mm away (30 cm is better), never on a steel part.

## Pre-dive check

1. Plug out, battery in: all three LEDs off.
2. Push the plug in: both blue LEDs (HALL, REED) on, then about 1 s later the red LIVE LED on. If only one blue LED lights, do not dive.
3. Pull the plug: LIVE off at once, the thrusters stop.
4. Pull the plug with a luggage scale once: it should need 10–20 N.

## Check before trusting it

- Build one board and test it on a bench supply with a current limit first, then with the battery and one ESC, then at full current. After a long full-throttle run, feel the MOSFETs, the wires and the XT90s.
- Measure the KY-003 and MC-38 with the magnet: KY-003 modules use A3144 or clones, and reed sensitivity varies by maker.
- The B0512S output is unregulated (about 14 V at light load in the model); the 15 V zener and the P6KE18A keep the gate below 20 V.
- The simulation models (MOSFETs fitted to datasheet numbers, behavioural comparators, opto, isolated module) are approximations.

## Folders

| Folder / file | Contents |
|---|---|
| `kicad/build_tht.py`, `route_tht.py` | Through-hole board: parts, netlist and placement; routing (0/45-degree corners), pours, bare strips, BRACU Duburi logo and name, DRC |
| `kicad/build_smd.py`, `route_smd.py` | SMD board, same circuit |
| `kicad/ks_tht.*`, `ks_smd.*`, `drc_*.rpt`, `bom_*.csv` | KiCad boards, DRC reports, BOMs and order lists |
| `kicad/3dmodels/`, `ks.pretty/`, `fp-lib-table` | 3D models of every part (found through `${KIPRJMOD}`), XT90 footprints |
| `kicad/bundle_3d.py`, `make_xt90.py`, `make_outputs.py`, `gridroute.py` | 3D-model bundling and green stackup, XT90 footprints and models, gerbers/zips/pictures, the router |
| `kicad/simulation/` | `run_tht.py --board tht/smd` (15 scenarios from the PCB netlist), `copper_tht.py` (copper current solve), `make_result.py` |
| `gerber_tht/`, `gerber_smd/`, `kill_switch_*_gerber_jlcpcb.zip`, `kill_switch_*_kicad.zip` | Gerbers for JLCPCB and the KiCad projects (with 3D models) |
| `veroboard/` | Perfboard version of the through-hole board, with schematic, wire list and parts |
| `pcb-3d/` | 3D through-hole board with every part and the current paths on the real copper |
| `3d/` | Tutorial: video `kill_switch_tutorial.mp4` and an interactive 3D scene of a diver pulling and re-arming the plug |
| `mech/` | Dock, plug, T-handle and inside sensor bracket (OpenSCAD, STL) |
| `kicad/build_ks.py`, `route_ks.py`, `ks_power.*`, `gerber/`, `kill_switch_gerber_jlcpcb.zip`, `kill_switch_kicad.zip` | First SMD version (LM5060, M5 lugs, 118 × 120 mm), kept for reference |
| `calc/` | `design_calc.py`: magnet field, reed placement, cable stray field, timing, plug retention (`report.md`) |

## Rebuilding

With KiCad 7 and its Python (`KICAD7_FOOTPRINT_DIR` and `KICAD7_SYMBOL_DIR` set to the KiCad libraries):

```bash
cd kicad && python3 build_tht.py && python3 route_tht.py && python3 make_bom.py bom_tht.csv bom_tht_grouped.csv && python3 make_outputs.py tht
```

```bash
cd kicad/simulation && python3 run_tht.py --board tht && python3 summary_tht.py --board tht && python3 copper_tht.py --board tht --wires && python3 make_result.py
```

The SMD board is the same with `build_smd.py`, `route_smd.py`, `make_outputs.py smd` and `--board smd`.

## Bangla-English summary

- Duita board, ekoi circuit, duitai 100 A: through-hole (8 ta IRFB3206, 123 × 100 mm) ar choto SMD (4 ta IPT007N06N, 80 × 75 mm).
- Battery ar ESC dui dikei XT90. XT90 45 A continuous / 90 A burst rated: thruster-er short burst thik ache; onek khon 100 A cholle 2 ta XT90 parallel ba AS150 din.
- 100 A-er jonno bare strip gulote 8 AWG khali tama-r tar solder korte hobe (VIN, VOUT upore; GND niche C shape). Tar chara copper-e 9 W gorom hoy, tar dile 2.5 W.
- Hall (KY-003) ar reed (MC-38) dutoi magnet dekhle tobei chalu hoy. Magnet tanle ~1.5 ms-e power off; chalu obosthay short hole 0.4 ms-e off; short thakle chalu-i hoy na.
- KiCad 7, 8, 9, 10 — jekono version-e khulle 3D view-te sob part dekha jabe (3D model project-er bhitorei ache). Board green.
- Battery + tare 125–150 A fuse rakho. Board ekhono banano/test kora hoyni: prothome bench supply-te current limit diye test korben.
