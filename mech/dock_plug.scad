// Magnetic kill switch: dock (glued on the outside of the hull), plug with the N52 magnet,
// red T-handle, and the sensor bracket glued inside the hull. All sizes in mm, from spec.json.
//
// Print: PETG or ASA, 100 % infill for the plug and the dock floor (water must not soak in).
// Pick the part below, press F6, then File > Export > STL.
//
// The plug is held by its O-ring snapping into the dock's detent groove (10-20 N to pull out,
// the plug weighs 0.29 N), so it cannot fall out of a side-mounted dock. No steel anywhere near
// the sensors.

part   = "all";     // "dock" | "plug" | "handle" | "bracket" | "all"
hull_r = 0;         // 0 = flat hull wall; otherwise the OUTER radius of a tube hull (saddle base)
$fn    = 120;
e      = 0.01;

// ---------------- dock ----------------
dock_od      = 40.0;
dock_h       = 18.0;   // above the hull surface at the axis
bore         = 24.0;
dock_floor   = 1.5;    // plastic between the plug face and the hull
chamfer      = 1.0;
detent_depth = 0.4;
detent_w     = 2.4;
detent_z     = 6.0;    // groove centre above the bore bottom
vent_w       = 1.5;
vent_d       = 1.0;

// ---------------- plug ----------------
plug_d     = 23.6;
plug_l     = 16.0;
plug_floor = 1.5;      // plastic in front of the magnet
mag_d      = 15.1;     // pocket for a 15 x 10 mm N52 disc
mag_l      = 10.0;
groove_d   = 20.6;     // O-ring 20 x 2 NBR70 sits here
groove_w   = 2.6;
groove_z   = 6.0;      // groove centre from the front face (lines up with the detent)

// ---------------- handle ----------------
spigot_d  = 15.0;
spigot_l  = 4.0;       // closes the magnet pocket, set in epoxy
stem_d    = 10.0;
stem_l    = 10.0;
bar       = [34.0, 10.0, 6.0];
lanyard_d = 4.0;

// ---------------- bracket (inside the hull) ----------------
plate      = [44.0, 58.0, 1.6];
plate_y0   = -30.0;                // plate runs from y -30 to +28 (axis at 0)
hall_win   = [4.4, 3.4];          // A3144 lies in here, printed face on the wall, on the axis
mc38       = [14.2, 27.7, 8.6];   // MC-38 wired part, long side pointing at the axis
mc38_off   = 12.0;                // reed centre from the axis
ky003      = [15.2, 18.7];        // KY-003 board outline
rail_h     = 4.0;

module dock() {
    sag = hull_r > 0 ? hull_r - sqrt(hull_r * hull_r - (dock_od / 2) * (dock_od / 2)) : 0;
    difference() {
        union() {
            translate([0, 0, -sag]) cylinder(d = dock_od, h = dock_h + sag - 1.0);
            translate([0, 0, dock_h - 1.0]) cylinder(d1 = dock_od, d2 = dock_od - 2.0, h = 1.0);   // soft top edge
        }
        // bore, entry chamfer, detent groove
        translate([0, 0, dock_floor]) cylinder(d = bore, h = dock_h);
        translate([0, 0, dock_h - chamfer]) cylinder(d1 = bore, d2 = bore + 2 * chamfer, h = chamfer + e);
        translate([0, 0, dock_floor + detent_z - detent_w / 2])
            difference() { cylinder(d = bore + 2 * detent_depth, h = detent_w); translate([0, 0, -e]) cylinder(d = bore - 1, h = detent_w + 2 * e); }
        // vent slot down the whole bore wall (no hydraulic lock, no suction)
        translate([bore / 2 - e, -vent_w / 2, dock_floor]) cube([vent_d + e, vent_w, dock_h]);
        // saddle for a tube hull: the tube touches the dock floor at the axis
        if (hull_r > 0) translate([0, 0, -hull_r]) rotate([90, 0, 0]) cylinder(r = hull_r, h = dock_od + 2, center = true, $fn = 360);
        // "S>" engraved on the side: the magnet's south pole goes in first (toward the hull)
        translate([0, dock_od / 2 - 0.6, dock_h / 2]) rotate([90, 0, 180]) linear_extrude(1) text("S>", size = 4, halign = "center", valign = "center");
    }
}

module plug() {
    difference() {
        union() {
            translate([0, 0, 0.8]) cylinder(d = plug_d, h = plug_l - 0.8);
            cylinder(d1 = plug_d - 1.6, d2 = plug_d, h = 0.8);              // lead-in on the front edge
        }
        translate([0, 0, plug_floor]) cylinder(d = mag_d, h = plug_l);    // magnet pocket, open at the back
        translate([0, 0, groove_z - groove_w / 2])
            difference() { cylinder(d = plug_d + 2, h = groove_w); translate([0, 0, -e]) cylinder(d = groove_d, h = groove_w + 2 * e); }
        // engraved front: S faces the hull
        translate([0, 0, -e]) linear_extrude(0.4) mirror([1, 0, 0]) text("S", size = 7, halign = "center", valign = "center");
    }
}

module handle() {
    difference() {
        union() {
            translate([0, 0, -spigot_l]) cylinder(d = spigot_d, h = spigot_l);
            cylinder(d = stem_d, h = stem_l + e);
            translate([-bar[0] / 2, -bar[1] / 2, stem_l]) cube(bar);
        }
        translate([0, -spigot_d / 2, -spigot_l - e]) cube([0.8, spigot_d, spigot_l]);          // epoxy escape groove
        translate([bar[0] / 2 - 5, 0, stem_l + bar[2] / 2]) rotate([90, 0, 0]) cylinder(d = lanyard_d, h = bar[1] + 2, center = true);
        translate([-6, 0, stem_l + bar[2] - 0.6]) linear_extrude(1) text("PULL", size = 4.5, halign = "center", valign = "center");
    }
}

module bracket() {
    difference() {
        union() {
            translate([-plate[0] / 2, plate_y0, 0]) cube(plate);
            // MC-38 rails: reed centre 12 mm from the axis, body pointing at the axis (+y)
            for (s = [-1, 1]) translate([s * (mc38[0] / 2 + 0.6) - 0.6, mc38_off - mc38[1] / 2, 0]) cube([1.2, mc38[1], plate[2] + rail_h]);
            translate([-mc38[0] / 2 - 1.2, mc38_off + mc38[1] / 2, 0]) cube([mc38[0] + 2.4, 1.2, plate[2] + rail_h]);
            // KY-003 posts below the axis (board parallel to the wall, 8 mm off it)
            for (x = [-5, 5]) translate([x, -16, 0]) cylinder(d = 4, h = plate[2] + 8);
        }
        translate([-hall_win[0] / 2, -hall_win[1] / 2, -e]) cube([hall_win[0], hall_win[1], plate[2] + 2 * e]);   // A3144 window, on the axis
        translate([-2.0, plate_y0 - e, -e]) cube([4.0, -plate_y0 - hall_win[1] / 2 + 2 * e, 0.8]);           // channel for the bent legs
        for (x = [-5, 5]) translate([x, -16, plate[2]]) cylinder(d = 1.8, h = 9);                            // M2 self-tapping
        // cable-tie slots over the MC-38
        for (sx = [-1, 1], yy = [mc38_off - 6, mc38_off + 6]) translate([sx * 10.5 - 1.5, yy - 1.5, -e]) cube([3, 3, plate[2] + 2 * e]);
        // centre mark for lining up with the dock
        translate([-plate[0] / 2 - e, -0.3, plate[2] - 0.4]) cube([3, 0.6, 0.5]);
        translate([plate[0] / 2 - 3 + e, -0.3, plate[2] - 0.4]) cube([3, 0.6, 0.5]);
    }
}

if (part == "dock") dock();
if (part == "plug") plug();
if (part == "handle") handle();
if (part == "bracket") bracket();
if (part == "all") {
    dock();
    translate([50, 0, 0]) plug();
    translate([50, 0, plug_l + spigot_l + 15]) handle();
    translate([0, 70, 0]) bracket();
}
