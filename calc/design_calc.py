"""Design calculations for the magnetic kill switch (100 A continuous, 150 A burst, 3S-6S LiPo).

Everything that sets a part value or a safety margin is computed here, so a change of magnet, hull wall,
MOSFET or battery is one edit and one re-run:  python3 design_calc.py   -> results.json and report.md

Datasheet numbers used (and where they came from) are in PARTS below. Values marked "verify" could only be
read from secondary copies of the datasheet during the design; check them against the manufacturer PDF.
"""
import json, math, os
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
MU0 = 4e-7 * math.pi

# ------------------------------------------------------------------ inputs
SPEC = dict(i_cont=100.0, i_burst=150.0, burst_s=10.0, v_min=9.0, v_max_4s=16.8, v_max_6s=25.2, t_air=40.0)
PARTS = {
    "mosfet": dict(name="Infineon IPT007N06N (TOLL)", n=8, vds=60, rds25_max=0.75e-3, rds_tc=0.0067,   # Rds(T)=Rds25*(1+tc*(T-25)): ~1.5x at 100 C (typ. OptiMOS curve, verify)
                   qg=216e-9, vgs_max=20, rth_ja_6cm2=40.0, src="Infineon datasheet Rev 2.3 via LCSC/Infineon CN summary"),
    "lm5060": dict(i_gate=(17e-6, 24e-6, 31e-6), i_tmr_start=(4e-6, 6e-6, 7e-6), i_tmr_fault=11e-6, v_tmrh=2.0,
                   i_sense=(13.6e-6, 16e-6, 18.0e-6), i_pd_off=2.2e-3, i_pd_fault=80e-3, en_on=2.0, en_off=0.8,
                   uvlo_th=(1.45, 1.6, 1.75), uvlo_hys=0.18, uvlo_i=5.5e-6, ovp_on=2.0, ovp_off=1.76, vin=(5.5, 65)),
    "tvs": dict(name="SMDJ26A (3 kW, SMC); SMCJ26A data shown for the 26 V family", vrwm=26.0, vbr_min=28.9, vc=42.1, ipp=35.7, ppk_w=3000),
    "hall": dict(name="KY-003 module, A3144 unipolar switch (south pole), open collector", bop_max=35e-3, brp_min=5e-3,
                 vcc=(4.5, 24), note="A3144 switch points are approximate (7-35 mT operate, 5-33 mT release): verify on your part"),
    "reed": dict(name="MC-38 style reed door contact, closed with the magnet", sw_a=(0.1, 0.5), v_max=100, pull_in_mT=(1.0, 3.0), drop_out_mT=0.5),
    "magnet": dict(grade="N52", br=(1.40, 1.43, 1.48), dia=15e-3, length=10e-3, density=7500),
}
GEOM = dict(plug_floor=1.5e-3, dock_floor=1.5e-3, hull_wall=6.0e-3, spacer=0.0, hall_depth=0.5e-3,   # magnet face -> Hall die (module face on the wall)
            reed_offset=12e-3, reed_len=14e-3, reed_depth=3.0e-3)                                       # reed sits ~3 mm inside the contact housing

# ------------------------------------------------------------------ magnet field (exact loop sum, no scipy)
def ellipke(m):
    a, b, c = np.ones_like(m), np.sqrt(1 - m), np.sqrt(m)
    s, p = 0.5 * c * c, 0.5
    for _ in range(30):
        a, b, c = 0.5 * (a + b), np.sqrt(a * b), 0.5 * (a - b)
        p *= 2; s = s + 0.5 * p * c * c
    K = np.pi / (2 * a)
    return K, K * (1 - s)

def magnet_B(r, z, br, a, L, n=400):
    """B (r, z components, tesla) of an axially magnetised cylinder (radius a, length L, front face at z=0,
    body at z<0) at radius r and distance z in front of the face. Side wall = stack of current loops."""
    K_surf = br / MU0
    zs = -L + (np.arange(n) + 0.5) * L / n
    I = K_surf * L / n
    br_, bz_ = 0.0, 0.0
    r = max(r, 1e-9)
    dz = z - zs
    q = (a + r) ** 2 + dz ** 2
    m = 4 * a * r / q
    Kk, Ee = ellipke(m)
    den = (a - r) ** 2 + dz ** 2
    bz = MU0 * I / (2 * np.pi * np.sqrt(q)) * (Kk + (a * a - r * r - dz * dz) / den * Ee)
    brr = MU0 * I / (2 * np.pi * r) * dz / np.sqrt(q) * (-Kk + (a * a + r * r + dz * dz) / den * Ee)
    return float(np.sum(brr)), float(np.sum(bz))

def bz_axis_closed(z, br, a, L):
    return br / 2 * ((z + L) / math.hypot(a, z + L) - z / math.hypot(a, z))

def reed_field(x0, z, br, a, L, length):
    """Mean field component along a reed lying flat (parallel to the magnet face) with its centre x0 off-axis."""
    xs = np.linspace(x0 - length / 2, x0 + length / 2, 41)
    comp = []
    for x in xs:
        brr, _ = magnet_B(abs(x), z, br, a, L)
        comp.append(brr * (1 if x >= 0 else -1))
    return float(np.mean(comp)), float(np.min(comp)), float(np.max(comp))

def main():
    out = {"spec": SPEC, "parts": PARTS, "geom": GEOM}
    mg, hl, rd = PARTS["magnet"], PARTS["hall"], PARTS["reed"]
    a, L = mg["dia"] / 2, mg["length"]
    z_hall = GEOM["plug_floor"] + GEOM["dock_floor"] + GEOM["hull_wall"] + GEOM["spacer"] + GEOM["hall_depth"]
    z_reed = GEOM["plug_floor"] + GEOM["dock_floor"] + GEOM["hull_wall"] + GEOM["reed_depth"]
    # check the loop model against the closed form on the axis
    _, bz_num = magnet_B(0, z_hall, mg["br"][1], a, L)
    bz_cf = bz_axis_closed(z_hall, mg["br"][1], a, L)
    mag = {"z_hall_mm": z_hall * 1e3, "bz_hall_mT_min_br": bz_axis_closed(z_hall, mg["br"][0], a, L) * 1e3,
           "bz_hall_mT_typ": bz_cf * 1e3, "loop_model_check_mT": bz_num * 1e3}
    mag["hall_on_margin_vs_bop_max"] = mag["bz_hall_mT_min_br"] / (hl["bop_max"] * 1e3)
    rmean, rmin, rmax = reed_field(GEOM["reed_offset"], z_reed, mg["br"][0], a, L, GEOM["reed_len"])
    rc, _, _ = reed_field(0.0, z_reed, mg["br"][0], a, L, GEOM["reed_len"])
    mag.update({"reed_axial_mean_mT": rmean * 1e3, "reed_axial_min_mT": rmin * 1e3, "reed_axial_max_mT": rmax * 1e3,
                "reed_on_axis_mean_mT": rc * 1e3, "reed_on_margin_vs_pullin_max": rmean * 1e3 / rd["pull_in_mT"][1]})
    # how far the magnet must go before both sensors release (strongest magnet, most sensitive sensor)
    def release_dist(th):
        z = z_hall
        while bz_axis_closed(z, mg["br"][2], a, L) > th: z += 0.5e-3
        return z
    mag["hall_release_extra_mm_worst"] = (release_dist(hl["brp_min"]) - z_hall) * 1e3
    mag["reed_release_extra_mm_worst"] = (release_dist(rd["drop_out_mT"] * 1e-3) - z_hall) * 1e3
    mag["park_distance_mm"] = math.ceil((release_dist(min(hl["brp_min"], rd["drop_out_mT"] * 1e-3) / 2)) * 1e3 / 10) * 10
    curve = []
    for dmm in [0, 2, 5, 10, 15, 20, 30, 40, 60, 80, 100, 150]:
        z = z_hall + dmm * 1e-3
        curve.append([dmm, round(bz_axis_closed(z, mg["br"][1], a, L) * 1e3, 3)])
    mag["bz_vs_pull_mm"] = curve
    out["magnet"] = mag

    # stray field of the thruster cables at the Hall sensor (must stay well under BRP min)
    stray = []
    for d_cm in [2, 5, 10, 20]:
        d = d_cm / 100
        single = MU0 * SPEC["i_burst"] / (2 * math.pi * d)
        pair = MU0 * SPEC["i_burst"] * 0.012 / (2 * math.pi * d * d)       # + and - run together, 12 mm apart
        stray.append({"d_cm": d_cm, "single_wire_mT": single * 1e3, "paired_mT": pair * 1e3})
    out["stray_field_150A"] = stray

    # ------------------------------------------------------------ MOSFETs and copper
    mf = PARTS["mosfet"]
    def rds(T): return mf["rds25_max"] * (1 + mf["rds_tc"] * (T - 25))
    therm = {}
    for label, I in (("cont_100A", SPEC["i_cont"]), ("burst_150A", SPEC["i_burst"])):
        T = 60.0
        for _ in range(20):
            r_bank = rds(T) / mf["n"]
            p_fets = I * I * r_bank
            p_each = p_fets / mf["n"] * 1.2                  # 20 % current-sharing imbalance
            T = 60.0 + p_each * 6.0                          # board at 60 C (worst), Rth junction->board ~6 K/W for TOLL on 2 oz + vias
        therm[label] = {"r_bank_mohm": r_bank * 1e3, "p_fets_W": p_fets, "p_per_fet_W": p_each, "tj_est_C": T, "vds_mV": I * r_bank * 1e3}
    r_copper = 0.06e-3                                       # VIN stud -> FETs -> VOUT stud, 2 oz both layers + mask-free strips
    r_lugs = 2 * 0.03e-3
    for k, I in (("cont_100A", SPEC["i_cont"]), ("burst_150A", SPEC["i_burst"])):
        therm[k]["p_copper_lugs_W"] = I * I * (r_copper + r_lugs)
        therm[k]["p_total_W"] = therm[k]["p_fets_W"] + therm[k]["p_copper_lugs_W"]
        therm[k]["drop_total_mV"] = I * (therm[k]["r_bank_mohm"] * 1e-3 + r_copper + r_lugs) * 1e3
    board_area = 2 * 0.100 * 0.120
    h = 12.0                                                 # still air inside the hull, convection + radiation
    therm["board_rise_no_spreader_C"] = therm["cont_100A"]["p_total_W"] / (h * board_area)
    therm["board_rise_with_al_spreader_to_hull_C"] = therm["cont_100A"]["p_total_W"] * 2.5    # pad + plate + hull to water ~2.5 K/W
    # what other teams' switches would dissipate at 100 A
    therm["compare_100A_W"] = {"3x IRF4905 P-FET (20 mOhm each)": 100 ** 2 * 0.020 / 3,
                               "4x IRLZ44N style N-FET (22 mOhm)": 100 ** 2 * 0.022 / 4,
                               "this design 8x IPT007N06N": therm["cont_100A"]["p_fets_W"],
                               "100 A contactor coil (typ. 12 V, 0.4-0.8 A)": 12 * 0.6}
    out["thermal"] = therm

    # ------------------------------------------------------------ LM5060 settings
    lm = PARTS["lm5060"]
    R_uv_t, R_uv_b = 47e3, 10e3
    uv_rise = lm["uvlo_th"][1] * (1 + R_uv_t / R_uv_b) + lm["uvlo_i"] * R_uv_t
    uv_fall = (lm["uvlo_th"][1] - lm["uvlo_hys"]) * (1 + R_uv_t / R_uv_b)
    ov = {}
    for name, rt in (("6S default 150k", 150e3), ("4S option 91k", 91e3)):
        ov[name] = {"rise_V": lm["ovp_on"] * (1 + rt / 10e3), "fall_V": lm["ovp_off"] * (1 + rt / 10e3)}
    R_sns = 4.32e3
    vds_trip = [i * R_sns for i in lm["i_sense"]]
    r_hot, r_cold = rds(100) / mf["n"], 0.55e-3 / mf["n"]
    C_tmr = 470e-9
    t_start = [C_tmr * lm["v_tmrh"] / i for i in lm["i_tmr_start"]]
    t_fault = C_tmr * lm["v_tmrh"] / lm["i_tmr_fault"]
    q_gate = mf["n"] * mf["qg"] + 47e-9 * 12
    qgd, v_pl = mf["n"] * 40e-9, 4.0
    t_pl = qgd / (v_pl / 220.0)
    out["turn_off"] = {"plateau_us": t_pl * 1e6, "di_dt_150A_A_per_us": SPEC["i_burst"] / (t_pl * 1e6),
                       "spike_1uH_V": 1e-6 * SPEC["i_burst"] / t_pl, "energy_150A_16V8_mJ": 0.5 * SPEC["v_max_4s"] * SPEC["i_burst"] * t_pl * 1e3,
                       "without_pnp_ms": q_gate / lm["i_pd_off"] * 1e3}
    out["lm5060"] = {"uvlo_rise_V": uv_rise, "uvlo_fall_V": uv_fall, "ovp": ov, "R_sense_ohm": R_sns,
                     "vds_trip_mV": [v * 1e3 for v in vds_trip],
                     "trip_current_A_hot_max": vds_trip[0] / r_hot, "trip_current_A_cold_typ": vds_trip[2] / r_cold,
                     "burst_vds_hot_mV": SPEC["i_burst"] * r_hot * 1e3,
                     "t_start_ms": [t * 1e3 for t in t_start], "t_fault_ms": t_fault * 1e3,
                     "gate_charge_uC": q_gate * 1e6, "t_full_enhance_ms": [q_gate / i * 1e3 for i in lm["i_gate"]],
                     "t_off_normal_ms": q_gate / lm["i_pd_off"] * 1e3}

    # ------------------------------------------------------------ pre-charge and short detection
    R_pc, C_esc, I_idle = 11.0, 4000e-6, 0.4
    pc = {}
    for vb in (SPEC["v_max_4s"], SPEC["v_max_6s"]):
        v_end = vb - I_idle * R_pc
        t60 = -R_pc * C_esc * math.log(1 - 0.5 * vb / vb) if v_end > 0.5 * vb else None
        pc[f"{vb:.1f}V"] = {"inrush_A": vb / R_pc, "v_final_with_idle_V": v_end, "t_to_50pct_ms": None if t60 is None else t60 * 1e3,
                            "energy_in_R_J": 0.5 * C_esc * vb * vb, "short_power_W": vb * vb / R_pc}
    # comparator abort ramp, ratiometric: VIN -> 1M / 47k, 3.3 uF; pre-charge stops when the ramp passes VOUT/10.1 + 46 mV
    v5 = 1.25 * (1 + 750 / 240)
    k = 47e3 / (1e6 + 47e3); tau = (1e6 * 47e3 / (1e6 + 47e3)) * 3.3e-6
    off = v5 * (10e3 * 90.9e3 / (10e3 + 90.9e3)) / 1e6
    vod = 10e3 / (90.9e3 + 10e3)
    ab = {"tau_ms": tau * 1e3, "offset_mV": off * 1e3, "vout_needed_at_end": f"VOUT > {k / vod:.3f} x VIN - {off / vod:.2f} V"}
    for vb in (SPEC["v_max_4s"], SPEC["v_max_6s"]):
        t_abort = -tau * math.log(1 - off / (k * vb))
        ab[f"t_abort_short_{vb:.1f}V_ms"] = t_abort * 1e3
        ab[f"energy_short_{vb:.1f}V_J"] = vb * vb / R_pc * t_abort
    pc["abort"] = ab
    vind = 10e3 / (191e3 + 10e3)
    pc["precharge_ok_threshold"] = f"VOUT > {vind / vod:.3f} x VIN - {off / vod:.2f} V"
    out["precharge"] = pc

    # ------------------------------------------------------------ kill and re-arm timing
    C_arm, R_arm = 2.2e-6, 2.2e3                      # ARM node: 2.2 uF debounce, 2.2k pull-down
    tau_arm = C_arm * R_arm
    t_inv = tau_arm * math.log(v5 / 1.8)              # ARM below the 2N7002 inverter threshold (~1.8 V): opto shunt + Q6 act
    t_pnp = tau_arm * math.log(v5 / (1.4 - 0.7))      # EN follows ARM + 0.7 V through the PNP; LM5060 off below ~1.4 V
    t_chatter_ok = tau_arm * math.log(v5 / (v5 - 0.9))   # a gap this short keeps EN above 2 V and ARM above the inverter
    tau_en = 100e3 * 22e-6
    t_en = tau_en * math.log(v5 / (v5 - lm["en_on"]))
    out["timing"] = {"arm_tau_ms": tau_arm * 1e3, "kill_inverter_path_ms": t_inv * 1e3, "kill_pnp_path_ms": t_pnp * 1e3,
                     "gate_off_ms": q_gate / (3.9e-3 + lm["i_pd_off"]) * 1e3,
                     "kill_total_ms_est": (t_inv + q_gate / (3.9e-3 + lm["i_pd_off"])) * 1e3,
                     "ignored_gap_ms": t_chatter_ok * 1e3, "rearm_delay_s": t_en}

    # ------------------------------------------------------------ surge and impedance
    L_bat, L_out, C_bus = 1.0e-6, 0.5e-6, C_esc
    R_loop = 0.012 + 0.004 + 0.1e-3 + 0.010
    z0 = math.sqrt(L_bat / C_bus)
    out["impedance"] = {"L_battery_uH": L_bat * 1e6, "C_esc_uF": C_bus * 1e6, "Z0_mohm": z0 * 1e3, "R_loop_mohm": R_loop * 1e3,
                        "damping": R_loop / (2 * z0), "hard_switch_inrush_A": SPEC["v_max_4s"] / R_loop,
                        "turn_off_energy_battery_lead_mJ": 0.5 * L_bat * SPEC["i_burst"] ** 2 * 1e3,
                        "turn_off_energy_output_lead_mJ": 0.5 * L_out * SPEC["i_burst"] ** 2 * 1e3}

    # ------------------------------------------------------------ magnet plug retention (side mount)
    vol = math.pi * a * a * L
    m_mag = vol * mg["density"]
    m_plug = m_mag + 0.010 + 0.006                         # body + handle/flag
    w = m_plug * 9.81
    out["retention"] = {"plug_mass_g": m_plug * 1e3, "weight_N": w, "design_pull_out_N": [10, 20],
                        "margin_vs_weight": 10 / w, "vibration_5g_N": 5 * w,
                        "drag_1p5ms_flag_N": 0.5 * 1000 * 1.5 ** 2 * 1.2 * 0.03 * 0.03}
    json.dump(out, open(os.path.join(HERE, "results.json"), "w"), indent=1, default=float)
    write_report(out)
    print(json.dumps(out, indent=1, default=lambda x: round(float(x), 4))[:6000])

def write_report(o):
    m, th, lm, pc, tm, im, rt = o["magnet"], o["thermal"], o["lm5060"], o["precharge"], o["timing"], o["impedance"], o["retention"]
    L = ["# Kill switch design numbers (generated by design_calc.py)", "",
         "## Magnet and sensors", "",
         f"- Magnet N52 diameter {o['parts']['magnet']['dia']*1e3:.0f} x {o['parts']['magnet']['length']*1e3:.0f} mm, Hall die {m['z_hall_mm']:.1f} mm from the magnet face.",
         f"- Field at the Hall sensor: {m['bz_hall_mT_min_br']:.1f} mT with the weakest N52 (A3144 operate point max about 35 mT): margin {m['hall_on_margin_vs_bop_max']:.1f}x.",
         f"- Reed {GEOM['reed_offset']*1e3:.0f} mm off axis sees {m['reed_axial_mean_mT']:.1f} mT along its length; centred on the axis it would see {m['reed_on_axis_mean_mT']:.2g} mT (field lines cancel), so it must sit off axis.",
         f"- Hall (A3144) releases at the latest {m['hall_release_extra_mm_worst']:.0f} mm out, the reed at the latest {m['reed_release_extra_mm_worst']:.0f} mm. Park the plug at least {m['park_distance_mm']} mm away.",
         "", "| Plug pulled out (mm) | Field at Hall (mT) |", "|---|---|"] + [f"| {d} | {b} |" for d, b in m["bz_vs_pull_mm"]] + [
         "", "Stray field of a 150 A cable at the sensor:", "", "| Distance | Single wire | + and - paired |", "|---|---|---|"] + [
         f"| {s['d_cm']} cm | {s['single_wire_mT']:.2f} mT | {s['paired_mT']:.3f} mT |" for s in o["stray_field_150A"]] + [
         "", "## Losses and temperature", "",
         f"- 8 MOSFETs in parallel, hot: {th['cont_100A']['r_bank_mohm']*1e3:.0f} uOhm. At 100 A: {th['cont_100A']['p_fets_W']:.2f} W in the MOSFETs ({th['cont_100A']['p_per_fet_W']:.2f} W each), {th['cont_100A']['p_total_W']:.1f} W for the whole board.",
         f"- At 150 A: {th['burst_150A']['p_fets_W']:.2f} W in the MOSFETs ({th['burst_150A']['p_per_fet_W']:.2f} W each), junction about {th['burst_150A']['tj_est_C']:.0f} C with the board at 60 C.",
         f"- Board rise at 100 A continuous: {th['board_rise_no_spreader_C']:.0f} C in still air, {th['board_rise_with_al_spreader_to_hull_C']:.0f} C with an aluminium spreader to the hull.",
         "", "| Switch at 100 A | Heat (W) |", "|---|---|"] + [f"| {k} | {v:.1f} |" for k, v in th["compare_100A_W"].items()] + [
         "", "## Controller (LM5060) settings", "",
         f"- UVLO {lm['uvlo_rise_V']:.1f} V rising / {lm['uvlo_fall_V']:.1f} V falling. OVP (6S default) {lm['ovp']['6S default 150k']['rise_V']:.0f} V / {lm['ovp']['6S default 150k']['fall_V']:.1f} V; 4S option {lm['ovp']['4S option 91k']['rise_V']:.1f} V / {lm['ovp']['4S option 91k']['fall_V']:.1f} V.",
         f"- Short-circuit (VDS) trip {lm['vds_trip_mV'][0]:.0f}-{lm['vds_trip_mV'][2]:.0f} mV: {lm['trip_current_A_hot_max']:.0f} A or more; a 150 A burst gives only {lm['burst_vds_hot_mV']:.0f} mV.",
         f"- Start-up check after {lm['t_start_ms'][2]:.0f}-{lm['t_start_ms'][0]:.0f} ms; fault timer {lm['t_fault_ms']:.0f} ms.",
         "", "## Pre-charge and short detection", "",
         f"- Pre-charge through 11 Ohm: {pc['16.8V']['inrush_A']:.1f} A (4S) / {pc['25.2V']['inrush_A']:.1f} A (6S) instead of about {im['hard_switch_inrush_A']:.0f} A when switching hard.",
         f"- Main MOSFETs close only when {pc['precharge_ok_threshold']}.",
         f"- Shorted thruster bus: pre-charge stops after {pc['abort']['t_abort_short_16.8V_ms']:.1f} ms at 4S ({pc['abort']['energy_short_16.8V_J']:.2f} J), {pc['abort']['t_abort_short_25.2V_ms']:.1f} ms at 6S ({pc['abort']['energy_short_25.2V_J']:.2f} J); the main MOSFETs never turn on.",
         f"- Pre-charge is also stopped if VOUT has not reached {pc['abort']['vout_needed_at_end']} (an ESC drawing current, a soft short).",
         f"- Turn-off with the PNP: Miller plateau about {o['turn_off']['plateau_us']:.0f} us, {o['turn_off']['di_dt_150A_A_per_us']:.1f} A/us at 150 A ({o['turn_off']['spike_1uH_V']:.1f} V on 1 uH, {o['turn_off']['energy_150A_16V8_mJ']:.0f} mJ in the MOSFETs) instead of {o['turn_off']['without_pnp_ms']:.1f} ms with the controller's 2.2 mA alone.",
         "", "## Timing", "",
         f"- Kill: about {tm['kill_total_ms_est']:.0f} ms after the magnet leaves. A gap shorter than {tm['ignored_gap_ms']:.1f} ms is ignored. Re-arm waits {tm['rearm_delay_s']:.1f} s.",
         "", "## Wiring impedance", "",
         f"- Battery lead 1 uH and 4000 uF of ESC capacitance: Z0 {im['Z0_mohm']:.1f} mOhm, loop resistance {im['R_loop_mohm']:.0f} mOhm, damping {im['damping']:.2f}.",
         f"- Energy left in the leads at a 150 A kill: {im['turn_off_energy_battery_lead_mJ']:.1f} mJ (battery side), {im['turn_off_energy_output_lead_mJ']:.1f} mJ (thruster side), taken by the TVS diodes (SMDJ26A on VIN, SMCJ26A on VOUT).",
         "", "## Magnet plug on a vertical wall", "",
         f"- Plug about {rt['plug_mass_g']:.0f} g, weight {rt['weight_N']:.2f} N. Pull-out force designed at 10-20 N: {rt['margin_vs_weight']:.0f}x its own weight, against {rt['vibration_5g_N']:.1f} N at 5 g vibration and {rt['drag_1p5ms_flag_N']:.1f} N of water drag at 1.5 m/s."]
    open(os.path.join(HERE, "report.md"), "w").write("\n".join(L) + "\n")

if __name__ == "__main__":
    main()
