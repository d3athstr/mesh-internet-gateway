#!/usr/bin/env python3
"""Generate the MeshGW Pi HAT PCB (placement pass).

Emits meshgw-hat.kicad_pcb from the shared netlist in netlist.py, with
footprints placed, board outline, mounting holes and a ground pour on both
layers.
Routing is a separate pass (freerouting via route.sh).

Layout reasoning:
  * J1 (40-pin header) runs along the TOP edge, which is where the Pi's header
    physically is. Everything else hangs below it.
  * U1 (E22) sits centred in the remaining area with its long axis vertical.
    Its VCC pads (9, 10) face right, so the decoupling column sits to their
    right with the shortest possible loop.
  * C2/C3 (0.1uF) sit directly beside pins 9/10. C1 (1000uF bulk) sits lower
    right, out of the SPI fan-out region.
  * The whole left half below the header is deliberately empty: that is where
    the SPI/control bundle runs from the header down to U1's left column. With
    the control lines on odd (inner-row) header pins the bundle fans in without
    a single crossing - see netlist.py for why those pins.

EVERYTHING IS PLACED AT ROTATION 0 — KiCad folds footprint orientation into
each pad's angle field, which is easy to get subtly wrong by hand.

MECHANICAL GEOMETRY — VERIFIED 2026-08-11, sources cited per number
-------------------------------------------------------------------
Everything below was checked against the official Raspberry Pi HAT board
mechanical specification (raspberrypi/hats, hat-board-mechanical.pdf, rev
2014/2018) and the Raspberry Pi 3B+ mechanical drawing
(datasheets.raspberrypi.com/rpi3/raspberry-pi-3-b-plus-mechanical-drawing.pdf),
cross-checked against KiCad 9's own /usr/share/kicad/template/RaspberryPi-HAT.

  * 65.0 x 56.0 mm.  The drawing gives BOTH 65x56 and 65x56.5 and states
    which is which: "56.5mm FOR SMT STYLE GPIO HEADER / OTHERWISE 56.0mm FOR
    THROUGH HOLE HEADER". This board uses a through-hole socket, so 56.0.
  * 3 mm radius corners (mandatory: "BOARD MUST HAVE 3mm RADIUS CORNERS").
    Emitted as a 12-segment polyline per corner — 0.006 mm chord error, and
    unlike gr_arc it survives every downstream tool we run.
  * 4x M2.5 mounting holes 3.5 mm in from each corner, drilled 2.75 mm,
    58 x 49 mm apart. The spec also requires the 6.2 mm land around each to be
    "EITHER ISOLATED COPPER OR BARE BOARD" and says of the holes "DO NOT
    CONNECT THESE TO GND" — hence the four keepout rule areas below, without
    which the B.Cu pour floods to 0.5 mm of every hole.
  * Header pin 1 at (8.37, 4.77), ODD pins at y=4.77 and EVEN pins at y=2.23.
    The even row is the one NEARER the board edge — on the Pi that is the row
    carrying 5V on pins 2/4. The previous revision of this file had the two
    rows swapped, which would have put every SPI signal on its neighbouring
    pin (MOSI on pin 19 would have landed on the Pi's pin 20 = GND).
    Note 8.37 is symmetric (pin 39 sits 8.37 from the other end), so the holes
    alone do not fix which end pin 1 is on: pin 1 is at the micro-SD/power end,
    the end AWAY from the Ethernet jack, which is also the end away from the
    PoE notch below.

PI 3B+ PoE HEADER (J14) — why this board has a notch
-----------------------------------------------------
The 3B+ added a 4-pin PoE header the original HAT spec knew nothing about, and
raspberrypi/hats says: "Newly designed HATs that do not provide a connector for
this header must avoid fouling it." Measured off the vector geometry of the 3B+
drawing (mounting-hole circles used as the scale reference, 26.183 units/mm),
J14's body occupies x 59.05-64.02, y 7.38-11.92 from the board's pin-1 corner —
i.e. directly under the top-right mounting hole, 1 mm from the HAT's right
edge. Its pins stand as tall as the GPIO pins (the official PoE HAT mates with
them), so they reach this board's underside. That matters here beyond fit:
J14 lands on the Ethernet magnetics' centre taps, so on a PoE-capable switch
those pins can sit at ~48-57 V, and this gateway is by definition plugged into
wired Ethernet. Shorting them into the GND pour is the failure being designed
out. The notch is open to the right edge deliberately: J14 leaves only ~1 mm to
the board edge, and an enclosed cutout would leave a 1 mm bridge of FR4 that
would snap.

DEVIATIONS FROM THE SPEC, DELIBERATE
-------------------------------------
  * No camera-flex slot and no display-flex cutout. Both are "RECOMMENDED",
    not required. The camera slot lands at x=45, y 27.5-44.5, straight through
    the E22's footprint, and this gateway has no camera or display.
  * No ID EEPROM on ID_SD/ID_SC (pins 27/28), which the full HAT spec does
    require. Those pins are left unconnected, which is what the spec demands of
    a board without one. meshtasticd is configured from /etc, not from an
    EEPROM. Strictly this makes the board "HAT-format", not a certified HAT.
"""
import math
import os
import re
import uuid

os.chdir(os.path.dirname(os.path.abspath(__file__)))

BX, BY = 100.0, 60.0          # board origin on the KiCad page
BW, BH = 65.0, 56.0           # HAT outline; 56.0 not 56.5 - THT header
CORNER_R = 3.0                # mandatory per the HAT spec
HDR_X, HDR_Y = 8.37, 4.77     # 40-pin header pin 1 (odd row) centre
# Pi 3B+ PoE header J14 clearance notch, open to the right edge.
# J14 body is x 59.05-64.02, y 7.38-11.92; this leaves >=0.68 mm all round.
POE_X0, POE_Y0, POE_Y1 = 58.2, 6.7, 12.8
MOUNT_LAND = 6.2              # spec: isolated copper or bare board
KFP = "/usr/share/kicad/footprints"
E22 = "lib.pretty/E22_900M30S.kicad_mod"
# Locally generated, pins running along X. KiCad's stock PinHeader_2x20 runs
# along Y, and rotating it is not an option: kicad_dsn.py does NOT export
# footprint rotation, so freerouting would route against unrotated pad
# positions (observed: 19 unconnected + 20 edge-clearance errors).
H2x20 = "lib.pretty/RPi_GPIO40_Horizontal.kicad_mod"
CAP_EL = f"{KFP}/Capacitor_THT.pretty/CP_Radial_D8.0mm_P3.50mm.kicad_mod"
CAP_CER = f"{KFP}/Capacitor_THT.pretty/C_Disc_D5.0mm_W2.5mm_P5.00mm.kicad_mod"


def U():
    return str(uuid.uuid4())


# ---------------------------------------------------------------- netlist
# Imported, not restated: gen.py builds the schematic from the same dict, and
# when these were two hand-kept copies they drifted (see netlist.py).
from netlist import NETS                                      # noqa: E402

NETNUM = {"": 0}
for i, n in enumerate(NETS, start=1):
    NETNUM[n] = i
PADNET = {}
for n, pads in NETS.items():
    for ref, pad in pads:
        PADNET[(ref, pad)] = n

# ------------------------------------------------------------- placement
# ref -> (footprint, value, local x, y, rotation). For J1 the coords are pin 1.
#
# EVERYTHING STAYS AT ROTATION 0. The Pi's GPIO header runs along the HAT's
# LONG (65 mm) axis, which KiCad's stock PinHeader_2x20 cannot do unrotated —
# so the footprint itself is generated horizontally instead of rotating the
# part. The embed() rot argument exists but is unused: see the H2x20 comment
# for why rotation is unusable with this DSN bridge.
PLACE = {
    "J1": (H2x20, "RPi_GPIO40", HDR_X, HDR_Y, 0),
    # E22 centred below the header. Body is 38.5 x 24; pads sit 1 mm proud of
    # the 24 mm edges, so it occupies x 19.5-45.5, y 10.75-49.25.
    # y=32.0, not 30.0: it widens the routing channel between the header pads
    # and U1's courtyard from 4.0 to 6.0 mm. Every signal has to funnel through
    # that channel, and the router ran out of room at 4.0.
    "U1": (E22, "E22-900M30S", 32.5, 32.0, 0),
    # decoupling column, right of U1's VCC pads (pads 10/9 at y = 16.9/19.44)
    "C2": (CAP_CER, "0.1uF", 52.0, 17.0, 0),
    "C3": (CAP_CER, "0.1uF", 52.0, 23.0, 0),
    "C1": (CAP_EL, "1000uF", 53.0, 44.0, 0),
}

# HAT mounting holes: 3.5 mm in from each corner, 58 x 49 mm apart, 2.75 mm.
# Matches KiCad's RaspberryPi-HAT template (MH1-MH4) exactly.
MOUNT = [(3.5, 3.5), (61.5, 3.5), (3.5, 52.5), (61.5, 52.5)]


def find_close(s, start):
    d, i = 0, start
    while True:
        if s[i] == '(':
            d += 1
        elif s[i] == ')':
            d -= 1
            if d == 0:
                return i
        i += 1


def embed(ref, path, value, lx, ly, rot=0):
    s = open(path).read().strip()
    x, y = BX + lx, BY + ly
    out, i = [], 0
    while True:
        m = re.compile(r'\(pad\s+"([^"]*)"').search(s, i)
        if not m:
            out.append(s[i:])
            break
        close = find_close(s, m.start())
        num = m.group(1)
        net = PADNET.get((ref, num))
        body = s[m.start():close]
        if net:
            body += f' (net {NETNUM[net]} "{net}")'
        out.append(s[i:m.start()])
        out.append(body + ')')
        i = close + 1
    s = "".join(out)
    at = f'(at {x} {y})' if rot == 0 else f'(at {x} {y} {rot})'
    s = s.replace('(layer "F.Cu")', f'(layer "F.Cu")\n  {at}\n'
                                    f'  (uuid "{U()}")', 1)
    s = s.replace('"REF**"', f'"{ref}"', 1)
    s = re.sub(r'\(property "Reference" "[^"]*"', f'(property "Reference" "{ref}"', s)
    s = re.sub(r'\(fp_text value "[^"]*"', f'(fp_text value "{value}"', s, count=1)
    return s


LAYERS = """  (layers
    (0 "F.Cu" signal)
    (31 "B.Cu" signal)
    (32 "B.Adhes" user "B.Adhesive")
    (33 "F.Adhes" user "F.Adhesive")
    (34 "B.Paste" user)
    (35 "F.Paste" user)
    (36 "B.SilkS" user "B.Silkscreen")
    (37 "F.SilkS" user "F.Silkscreen")
    (38 "B.Mask" user)
    (39 "F.Mask" user)
    (40 "Dwgs.User" user "User.Drawings")
    (41 "Cmts.User" user "User.Comments")
    (42 "Eco1.User" user "User.Eco1")
    (43 "Eco2.User" user "User.Eco2")
    (44 "Edge.Cuts" user)
    (45 "Margin" user)
    (46 "B.CrtYd" user "B.Courtyard")
    (47 "F.CrtYd" user "F.Courtyard")
    (48 "B.Fab" user)
    (49 "F.Fab" user)
  )"""

def arc(cx, cy, r, a0, a1, n=12):
    """Quarter-arc as a polyline. n=12 -> 0.006 mm chord error at r=3."""
    return [(cx + r * math.cos(math.radians(a0 + (a1 - a0) * i / n)),
             cy + r * math.sin(math.radians(a0 + (a1 - a0) * i / n)))
            for i in range(n + 1)]


def outline(g=0.0):
    """Closed board outline, inset by g mm. g=0 is Edge.Cuts itself.

    Clockwise from the top-left corner. The PoE notch is a bite out of the
    RIGHT edge, so it appears between the top-right and bottom-right corners.
    """
    r = CORNER_R - g
    pts = arc(CORNER_R, CORNER_R, r, 180, 270)                  # top-left
    pts += arc(BW - CORNER_R, CORNER_R, r, 270, 360)            # top-right
    pts += [(BW - g, POE_Y0 + g), (POE_X0 + g, POE_Y0 + g),     # PoE notch
            (POE_X0 + g, POE_Y1 - g), (BW - g, POE_Y1 - g)]
    pts += arc(BW - CORNER_R, BH - CORNER_R, r, 0, 90)          # bottom-right
    pts += arc(CORNER_R, BH - CORNER_R, r, 90, 180)             # bottom-left
    return pts


def circle_poly(cx, cy, r, n=24):
    """Polygon CIRCUMSCRIBING the circle of radius r.

    Inscribing it instead (vertices on the circle) leaves the edges up to
    r*(1-cos(pi/n)) inside it, and the pour then fills to 3.073 mm of a hole
    whose land must be clear to 3.100. check_geometry.py catches that; DRC
    never would, because to DRC the keepout IS the polygon.
    """
    rr = r / math.cos(math.pi / n)
    return [(cx + rr * math.cos(2 * math.pi * i / n),
             cy + rr * math.sin(2 * math.pi * i / n)) for i in range(n)]


def pts_str(pts):
    return " ".join(f"(xy {round(BX+x, 4)} {round(BY+y, 4)})" for x, y in pts)


body = []
edge = outline(0.0)
for i in range(len(edge)):
    x1, y1 = edge[i]
    x2, y2 = edge[(i + 1) % len(edge)]
    body.append(f'  (gr_line (start {round(BX+x1, 4)} {round(BY+y1, 4)})'
                f' (end {round(BX+x2, 4)} {round(BY+y2, 4)})'
                f' (stroke (width 0.1) (type default)) (layer "Edge.Cuts")'
                f' (uuid "{U()}"))')

# The same outline inset by the board-edge clearance, on Eco1.User.
# kicad_dsn.py hands this to freerouting as the routing boundary in place of
# the Edge.Cuts bounding box, so the router stops 0.5 mm short of the cut line
# instead of laying copper 0.42 mm from it (observed 2026-08-11, net BUSY).
# It must NOT go on Margin: KiCad treats Margin as a board-edge layer in
# copper_edge_clearance, so the inset ring then fails DRC against itself.
EDGE_CLEARANCE = 0.5
mrg = outline(EDGE_CLEARANCE)
for i in range(len(mrg)):
    x1, y1 = mrg[i]
    x2, y2 = mrg[(i + 1) % len(mrg)]
    body.append(f'  (gr_line (start {round(BX+x1, 4)} {round(BY+y1, 4)})'
                f' (end {round(BX+x2, 4)} {round(BY+y2, 4)})'
                f' (stroke (width 0.05) (type default)) (layer "Eco1.User")'
                f' (uuid "{U()}"))')
for _i, (mx, my) in enumerate(MOUNT, start=1):
    body.append(f'''  (footprint "MountingHole:MountingHole_2.75mm"
    (layer "F.Cu") (at {BX+mx} {BY+my}) (uuid "{U()}")
    (attr exclude_from_pos_files exclude_from_bom)
    (property "Reference" "H{_i}" (at 0 -3 0) (layer "F.SilkS") (uuid "{U()}")
      (effects (font (size 1 1) (thickness 0.15))))
    (pad "" np_thru_hole circle (at 0 0) (size 2.75 2.75) (drill 2.75)
      (layers "F&B.Cu" "*.Mask") (uuid "{U()}"))
  )''')

for ref, (path, value, lx, ly, rot) in PLACE.items():
    body.append(embed(ref, path, value, lx, ly, rot))

# Loud silkscreen. The Warden carrier precedent: a draft board says so on the
# copper, because a bare PCB on a bench outlives the note that explained it.
for txt, tx, ty, sz in [
        ("MeshGW HAT rev A - DRAFT", 32.5, 53.6, 1.4),
        ("DO NOT ORDER - E22 land pattern unverified", 32.5, 55.1, 0.9),
        ("E22 VCC = 5V", 52.0, 30.0, 1.0),
        # Names the notch so nobody "tidies it up" on a later spin.
        ("PoE J14", 53.5, 9.75, 1.0)]:
    body.append(f'  (gr_text "{txt}" (at {BX+tx} {BY+ty}) (layer "F.SilkS")'
                f' (uuid "{U()}") (effects (font (size {sz} {sz})'
                f' (thickness {0.2 if sz > 1 else 0.15}))))')

# GND pour on the back, inset 0.3 mm.
#
# GND pads connect SOLID, not via thermal relief. Thermal relief was tried
# first (hand-soldered board; relief makes a THT pin far easier to heat) and
# it does not work here: J1's interior GND pins are boxed in by neighbouring
# pads on a 2.54 mm grid, so each could only grow ONE spoke and KiCad raised
# four starved_thermal errors. Tightening to gap 0.3 / bridge 0.4 did not
# clear them — the blocker is the neighbouring pads' clearance, not the gap.
# Solid is also the electrically better answer on a 1 W RF board. Practical
# consequence: soldering J1's GND pins needs a 60 W+ iron or a preheater;
# a 25 W pencil will not wet them.
# The pour polygon follows the real outline inset 0.3 mm, INCLUDING the PoE
# notch and the radiused corners. It has to be built this way round: the DSN
# bridge hands freerouting only the bounding BOX of Edge.Cuts, so nothing else
# in the toolchain knows the notch exists. KiCad's own copper_edge_clearance
# check is what catches a track that wanders into it.
#
# The pour is on BOTH layers. B.Cu is the plane proper; F.Cu matters because
# every one of the E22's nine GND pads is an SMD pad on F.Cu ONLY, and there is
# no via under the module. Without a front pour those pads reach ground through
# a daisy chain of 0.25 mm tracks to one header pin, which satisfies DRC and is
# a poor ground for a 1 W PA. With it they land straight on copper, and F.Cu
# and B.Cu are stitched by J1's eight through-hole GND pins plus C1/C2/C3.
for _lay, _name in [("B.Cu", "GND_POUR_B"), ("F.Cu", "GND_POUR_F")]:
    body.append(f'''  (zone (net {NETNUM["GND"]}) (net_name "GND") (layers "{_lay}")
    (uuid "{U()}") (name "{_name}") (hatch edge 0.5)
    (connect_pads yes (clearance 0.5))
    (min_thickness 0.25) (filled_areas_thickness no)
    (fill yes (thermal_gap 0.3) (thermal_bridge_width 0.4))
    (polygon (pts {pts_str(outline(0.3))}))
  )''')

# Keepout rule areas. These are the ONE declaration of "no copper here" that
# both KiCad's DRC and freerouting read (kicad_dsn.py exports rule areas as DSN
# keepouts), so the router does not have to be argued with after the fact.
#
#  * MH1-4: the HAT spec's 6.2 mm land around each mounting hole, which must be
#    isolated copper or bare board, and must not be tied to GND. Without it the
#    pour fills to 0.5 mm of every hole and a metal standoff bridges hole to
#    plane; the router also drove +5V straight through H1's land.
#  * POE: the Pi 3B+ J14 notch, grown by the 0.5 mm edge clearance. The notch
#    is a hole in Edge.Cuts, and freerouting ignores concave boundaries — it
#    put NSS through the middle of it until this rule area existed.
KEEPOUTS = [(f"MH{i}_LAND", circle_poly(mx, my, MOUNT_LAND / 2))
            for i, (mx, my) in enumerate(MOUNT, start=1)]
KEEPOUTS.append(("POE_J14_NOTCH", [
    (POE_X0 - EDGE_CLEARANCE, POE_Y0 - EDGE_CLEARANCE),
    (BW + 1.0, POE_Y0 - EDGE_CLEARANCE),
    (BW + 1.0, POE_Y1 + EDGE_CLEARANCE),
    (POE_X0 - EDGE_CLEARANCE, POE_Y1 + EDGE_CLEARANCE)]))
for _name, _poly in KEEPOUTS:
    body.append(f'''  (zone (net 0) (net_name "") (layers "F.Cu" "B.Cu")
    (uuid "{U()}") (name "{_name}") (hatch edge 0.5)
    (connect_pads (clearance 0))
    (min_thickness 0.25) (filled_areas_thickness no)
    (keepout (tracks not_allowed) (vias not_allowed) (pads allowed)
             (copperpour not_allowed) (footprints allowed))
    (fill (thermal_gap 0.5) (thermal_bridge_width 0.5))
    (polygon (pts {pts_str(_poly)}))
  )''')

nets = "\n".join(f'  (net {i} "{n}")' for n, i in
                 sorted(NETNUM.items(), key=lambda kv: kv[1]))

pcb = f'''(kicad_pcb (version 20241229) (generator "empire12-gen") (generator_version "9.0")
  (general (thickness 1.6) (legacy_teardrops no))
  (paper "A4")
{LAYERS}
  (setup
    (pad_to_mask_clearance 0)
    (allow_soldermask_bridges_in_footprints no)
    (pcbplotparams
      (layerselection 0x00010fc_ffffffff)
      (plot_on_all_layers_selection 0x0000000_00000000)
      (disableapertmacros no) (usegerberextensions no) (usegerberattributes yes)
      (usegerberadvancedattributes yes) (creategerberjobfile yes)
      (svgprecision 4) (plotframeref no) (mode 1) (useauxorigin no)
      (dxfpolygonmode yes) (dxfimperialunits yes) (dxfusepcbnewfont yes)
      (psnegative no) (psa4output no) (plotreference yes) (plotvalue yes)
      (plotfptext yes) (plotinvisibletext no) (sketchpadsonfab no)
      (subtractmaskfromsilk no) (outputformat 1) (mirror no) (drillshape 1)
      (scaleselection 1) (outputdirectory "gerbers/")
    )
  )
{nets}
{chr(10).join(body)}
)
'''
open("meshgw-hat.kicad_pcb", "w").write(pcb)
print(f"wrote meshgw-hat.kicad_pcb — {len(PLACE)} footprints, "
      f"{len(NETS)} nets, board {BW}x{BH}mm")
