# Simulation results, through-hole board

ngspice, netlist taken from `ks_tht.kicad_pcb` by `run_tht.py`. Load: ESC bank (4000 uF) with idle current, then 30 A and 60 A.

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

All 15 scenarios pass.
