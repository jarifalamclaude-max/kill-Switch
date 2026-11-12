# Simulation results

ngspice, netlist taken from `ks_power.kicad_pcb` by `run_ks.py`. Load: ESC bank with capacitance, then 100 A and 150 A steps.

| Scenario | What it tests | Result | Pass |
|---|---|---|---|
| `normal_4S` | 4S pack, magnet in, 100 A then 150 A, magnet out | live after 957 ms, pre-charge 1.49 A, Vgs 12.76 V, VDS 9.1 mV at 100 A / 13.7 mV at 150 A, off 4.7 ms after the magnet, 23 mJ in the FETs, VIN peak 27.8 V | yes |
| `normal_6S` | 6S pack, same test | live after 957 ms, pre-charge 2.25 A, Vgs 12.76 V, VDS 9.1 mV at 100 A / 13.7 mV at 150 A, off 4.7 ms after the magnet, 24 mJ in the FETs, VIN peak 37.0 V | yes |
| `low_3S` | 3S (low) pack still arms and kills | live after 947 ms, Vgs 12.75 V, off 4.7 ms | yes |
| `start_into_short` | magnet in with the output shorted | never goes live, pre-charge stops at 1.52 A, 0.19 J in the pre-charge resistors | yes |
| `short_while_running` | dead short on the output while live | off 0.82 ms after the short, peak 819 A, 1.87 J shared by 8 FETs, VIN peak 25.7 V | yes |
| `chatter_0p8ms` | 0.8 ms sensor chatter (vibration) is ignored | stays live, output 15.9 V at the end | yes |
| `dropout_10ms` | 10 ms sensor dropout while 60 A flows, magnet back after 10 ms | off 4.6 ms after the dropout; the restart pre-charge cannot lift the bus against the 60 A load, gives up and the output stays off (3.7 V at 4 s) | yes |
| `fault_hall_stuck` | Hall stuck ON, magnet pulled | reed path kills in 4.3 ms | yes |
| `fault_reed_welded` | reed welded shut, magnet pulled | Hall path kills in 5.0 ms | yes |
| `fault_controller_stuck_on` | LM5060 enable stuck high, magnet pulled | opto gate shunt kills in 5.0 ms | yes |
| `fault_sensor_cable_cut` | sensor cable cut while live | off in 4.8 ms | yes |
| `fault_hall_vcc_cut` | Hall module loses its 5 V | off in 4.6 ms | yes |
| `fault_hall_signal_shorted` | Hall signal wire shorted | off in 4.3 ms | yes |
| `wrong_pack_4S_option` | 6S pack on a board set for 4S (R4 = 91k) | OVP blocks it: never goes live, 5 uJ in the pre-charge resistors, output 0.001 V | yes |
| `hot_plug_magnet_in` | battery plugged in with the magnet already in | normal start: live after 957 ms, pre-charge 1.52 A | yes |

All 15 scenarios pass.
