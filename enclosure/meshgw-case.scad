// MeshGW enclosure — Raspberry Pi 3B/3B+ with the MeshGW HAT stacked.
//
//   openscad -D part=\"base\" -o meshgw-base.stl meshgw-case.scad
//   openscad -D part=\"lid\"  -o meshgw-lid.stl  meshgw-case.scad
//   openscad -D part=\"all\"  meshgw-case.scad          // preview both
//
// INDOOR ONLY. This is a shelf/rack box: vented, not sealed, no gasket. The
// outdoor RF node on this mesh is the e12solar RAK4631 in its LeMotech IP65
// enclosure — do not repurpose this design for outdoor use.
//
// DIMENSIONS ARE NOMINAL AND UNVERIFIED against a physical Pi. Print the
// test coupon (part="coupon") FIRST — it is just the mounting-boss pattern
// and the port wall, ~10 minutes of filament — and offer it up to the actual
// Pi before committing to a 4-hour full print. Port positions in particular
// vary between Pi models.

part = "all";           // "base" | "lid" | "coupon" | "all"
$fn = 48;

/* ---------------------------------------------------------------- Pi */
pi_l        = 85.0;     // Pi 3B/3B+ board length
pi_w        = 56.0;     // board width
pi_t        = 1.4;      // board thickness
pi_hole_dx  = 58.0;     // mounting hole spacing, long axis
pi_hole_dy  = 49.0;     // mounting hole spacing, short axis
pi_hole_in  = 3.5;      // hole inset from the board corner
pi_hole_d   = 2.75;     // hole diameter (M2.5 clearance)

/* -------------------------------------------------------------- stack */
// Pi board -> standoff -> HAT board -> E22 module -> headroom.
standoff_h  = 11.0;     // Pi top face to HAT underside (stacking header)
hat_t       = 1.6;      // HAT board thickness
e22_t       = 3.6;      // E22-900M30S body height (datasheet: 3.6 mm)
head_room   = 10.0;     // clearance above the E22 for the IPEX pigtail, which
                        // bends sideways off the module and does not like a
                        // tight radius. 10 rather than 6 also buys the band of
                        // wall the exhaust vents need: they have to sit above
                        // the tallest connector opening (USB, top at ~23.8)
                        // and below the lid lip, and at head_room = 6 there
                        // was no gap left between the two.

/* ------------------------------------------------------------ shell */
wall        = 2.4;      // 3 perimeters at 0.4 mm nozzle, 0.2 mm layers
floor_t     = 2.4;
boss_h      = 4.0;      // Pi underside to floor: clears solder + microSD lip
clear       = 1.0;      // gap between board edge and inner wall, per side
lip_h       = 3.0;      // lid register lip
lip_gap     = 0.25;     // lid-to-base clearance; loosen to 0.35 if it binds

inner_l = pi_l + 2*clear;
inner_w = pi_w + 2*clear;
inner_h = boss_h + pi_t + standoff_h + hat_t + e22_t + head_room;

out_l = inner_l + 2*wall;
out_w = inner_w + 2*wall;

/* -------------------------------------------------------------- ports */
// Measured from the Pi board's origin corner (the microSD end, port side).
// [name, centre along that wall, opening width, opening height, sill height
//  above the Pi's TOP face]. VERIFY THESE AGAINST A REAL BOARD.
//
// Long wall (+Y, where Ethernet and USB live):
eth_x = 10.25;  eth_w = 16.0;  eth_h = 14.0;
usb1_x = 29.0;  usb_w = 14.5;  usb_h = 16.0;
usb2_x = 47.0;
// Short/bottom wall (-Y edge): micro-USB power, HDMI, audio.
pwr_x  = 10.6;  pwr_w  = 11.0;  pwr_h = 6.0;
hdmi_x = 32.0;  hdmi_w = 16.0;  hdmi_h = 8.0;
aud_x  = 53.5;  aud_w  = 10.0;  aud_h = 8.0;
// SMA bulkhead for the antenna pigtail: on the -X end wall, above the HAT so
// the connector body clears the board edge. 6.5 mm is the usual SMA bulkhead
// thread clearance. The centre is set from the HAT's top face rather than
// from the floor so it tracks standoff_h if that changes.
sma_d  = 6.5;
sma_z  = boss_h + pi_t + standoff_h + hat_t + 6.0;

module port(cx, cz, w, h) {
    // cx = centre along the wall, cz = centre height above the floor inside
    translate([cx, 0, cz]) cube([w, wall*4, h], center = true);
}

module boss(x, y, h, od = 6.0) {
    translate([x, y, 0]) difference() {
        cylinder(d = od, h = h);
        translate([0, 0, 1.2]) cylinder(d = 2.2, h = h);   // M2.5 self-tap
    }
}

module bosses(h) {
    ox = clear + pi_hole_in;
    oy = clear + pi_hole_in;
    for (x = [ox, ox + pi_hole_dx], y = [oy, oy + pi_hole_dy])
        boss(x, y, h);
}

// Passive convection only. The E22 dumps ~3 W as heat on a sustained TX burst
// and the Pi adds its own; a sealed box would cook both.
//
// Intake is LOW on the +X end wall (under the Pi board) and exhaust is HIGH on
// both long walls, so air crosses the whole stack instead of pooling. The
// first version put tall slots low on the long walls and they cut straight
// through the Ethernet, USB, HDMI and audio openings — the slots and the ports
// merged into one ragged hole. Anything on a long wall now lives in the band
// above the connectors, which is why these z values are derived rather than
// typed in: connector_top < vent < lid lip.
connector_top = floor_t + boss_h + pi_t + max(eth_h, usb_h);
lip_bottom    = floor_t + inner_h - lip_h;
vent_h        = 3.5;
vent_z        = (connector_top + lip_bottom) / 2;   // centred in the free band

module vents_high() {
    // one wall's worth of exhaust, cut at y = 0 (the -Y wall)
    for (i = [0 : 6])
        translate([12 + i*10, -wall*2, vent_z - vent_h/2])
            cube([5, wall*4, vent_h]);
}

module vents_intake() {
    // +X end wall, below the Pi board so cool air enters under it
    for (i = [0 : 3])
        translate([inner_l - wall, 8 + i*12, floor_t + 1.0])
            cube([wall*4, 5, boss_h - 1.5]);
}

module base() {
    difference() {
        union() {
            // shell
            difference() {
                translate([-wall, -wall, 0])
                    cube([out_l, out_w, floor_t + inner_h]);
                translate([0, 0, floor_t])
                    cube([inner_l, inner_w, inner_h + 1]);
            }
            bosses(floor_t + boss_h);
        }
        // --- ports on the +Y long wall ---
        translate([0, inner_w + wall, 0]) {
            port(eth_x + clear,  floor_t + boss_h + pi_t + eth_h/2,  eth_w, eth_h);
            port(usb1_x + clear, floor_t + boss_h + pi_t + usb_h/2,  usb_w, usb_h);
            port(usb2_x + clear, floor_t + boss_h + pi_t + usb_h/2,  usb_w, usb_h);
        }
        // --- ports on the -Y wall ---
        port(pwr_x + clear,  floor_t + boss_h + pi_t + pwr_h/2,  pwr_w, pwr_h);
        port(hdmi_x + clear, floor_t + boss_h + pi_t + hdmi_h/2, hdmi_w, hdmi_h);
        port(aud_x + clear,  floor_t + boss_h + pi_t + aud_h/2,  aud_w, aud_h);
        // --- SMA bulkhead on the -X end wall ---
        translate([-wall*2, inner_w/2, sma_z])
            rotate([0, 90, 0]) cylinder(d = sma_d, h = wall*4);
        // --- microSD slot on the -X end wall, at board level ---
        translate([-wall*2, inner_w/2 - 8, floor_t + boss_h - 1.5])
            cube([wall*4, 16, 3.5]);
        vents_high();
        translate([0, inner_w, 0]) mirror([0, 1, 0]) vents_high();
        vents_intake();
    }
}

module lid() {
    difference() {
        union() {
            translate([-wall, -wall, 0]) cube([out_l, out_w, wall]);
            // register lip, inset by the fit clearance
            translate([lip_gap, lip_gap, -lip_h])
                difference() {
                    cube([inner_l - 2*lip_gap, inner_w - 2*lip_gap, lip_h]);
                    translate([wall, wall, -1])
                        cube([inner_l - 2*wall - 2*lip_gap,
                              inner_w - 2*wall - 2*lip_gap, lip_h + 2]);
                }
        }
        // lid vents, offset from the base vents so they do not line up and
        // let dust fall straight through onto the board
        for (i = [0 : 4])
            translate([24 + i*10, inner_w/2 - 12, -1])
                cube([4, 24, wall + 2]);
    }
}

// Print this first. All four bosses + the -Y port wall: proves hole spacing
// in BOTH axes, boss height and port alignment against a real Pi for ~20 min
// of filament instead of a 4-hour full print.
//
// The floor is a perimeter frame, not a slab — the middle is cut away to save
// filament. The frame must stay wide enough to actually reach all four
// bosses; a narrow strip along one edge leaves the far pair floating in
// space, which slices into two loose pucks (found the hard way: OpenSCAD
// reported 4 volumes).
coupon_frame = 12.0;    // frame width; must exceed pi_hole_in + boss radius

module coupon() {
    difference() {
        union() {
            translate([-wall, -wall, 0])
                cube([out_l, out_w, floor_t]);
            translate([-wall, -wall, 0])
                cube([out_l, wall, floor_t + boss_h + pi_t + 10]);
            bosses(floor_t + boss_h);
        }
        // hollow out the middle, leaving the frame
        translate([coupon_frame, coupon_frame, -1])
            cube([inner_l - 2*coupon_frame, inner_w - 2*coupon_frame,
                  floor_t + 2]);
        port(pwr_x + clear,  floor_t + boss_h + pi_t + pwr_h/2,  pwr_w, pwr_h);
        port(hdmi_x + clear, floor_t + boss_h + pi_t + hdmi_h/2, hdmi_w, hdmi_h);
        port(aud_x + clear,  floor_t + boss_h + pi_t + aud_h/2,  aud_w, aud_h);
    }
}

if (part == "base")        base();
else if (part == "lid")    lid();
else if (part == "coupon") coupon();
else {
    base();
    translate([0, 0, floor_t + inner_h + 12]) lid();
}
