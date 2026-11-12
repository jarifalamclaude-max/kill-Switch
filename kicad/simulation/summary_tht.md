# Simulation results, through-hole board (8 x IRFB3206)

ngspice, netlist taken from `ks_tht.kicad_pcb` by `run_tht.py --board tht`. Load: ESC bank (4000 uF) with idle current, then 60 A and 100 A.

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

All 15 scenarios pass.
