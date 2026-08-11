#!/usr/bin/env python3
"""Generate the MeshGW Pi HAT PCB (placement pass).

Emits meshgw-hat.kicad_pcb from the netlist below (which MIRRORS gen.py), with
footprints placed, board outline, mounting holes and a B.Cu ground pour.
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
    the SPI/control bundle runs from the header down to U1's left column.

EVERYTHING IS PLACED AT ROTATION 0 — KiCad folds footprint orientation into
each pad's angle field, which is easy to get subtly wrong by hand.

!!! MECHANICAL GEOMETRY IS UNVERIFIED !!!
Board size and mounting-hole positions below are the standard Raspberry Pi HAT
figures (65 x 56.5 mm, holes 3.5 mm in from each corner, 2.75 mm dia). The
40-pin header ORIGIN (HDR_X/HDR_Y, = pin 1) is the number most likely to be
wrong, and getting it wrong means the board does not seat on the Pi. Check all
four against the official Raspberry Pi HAT mechanical specification before
generating gerbers. This is a fab-blocking item, not a nicety.
"""
import os
import re
import uuid

os.chdir(os.path.dirname(os.path.abspath(__file__)))

BX, BY = 100.0, 60.0          # board origin on the KiCad page
BW, BH = 65.0, 56.5           # Raspberry Pi HAT outline  [VERIFY]
HDR_X, HDR_Y = 7.0, 2.5       # 40-pin header pin-1 centre  [VERIFY - critical]
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
# net name -> [(refdes, pad number)]. MUST mirror gen.py.
# J1 pad numbers are HEADER pin numbers; U1 pad numbers are E22 datasheet pins.
NETS = {
    "GND":   [("J1", "6"), ("J1", "9"), ("J1", "14"), ("J1", "20"),
              ("J1", "25"), ("J1", "30"), ("J1", "34"), ("J1", "39"),
              ("U1", "1"), ("U1", "2"), ("U1", "3"), ("U1", "4"), ("U1", "5"),
              ("U1", "11"), ("U1", "12"), ("U1", "20"), ("U1", "22"),
              ("C1", "2"), ("C2", "2"), ("C3", "2")],
    # E22 VCC is the 5V rail: datasheet says >=5.0V for rated output power and
    # 650 mA on a TX burst. Do NOT move this to 3V3.
    "+5V":   [("J1", "2"), ("J1", "4"), ("U1", "9"), ("U1", "10"),
              ("C1", "1"), ("C2", "1"), ("C3", "1")],
    "+3V3":  [("J1", "1"), ("J1", "17")],
    "MOSI":  [("J1", "19"), ("U1", "17")],   # BCM GPIO10
    "MISO":  [("J1", "21"), ("U1", "16")],   # BCM GPIO9
    "SCK":   [("J1", "23"), ("U1", "18")],   # BCM GPIO11
    "NSS":   [("J1", "40"), ("U1", "19")],   # BCM GPIO21 (software CS)
    "NRST":  [("J1", "12"), ("U1", "15")],   # BCM GPIO18
    "DIO1":  [("J1", "36"), ("U1", "13")],   # BCM GPIO16 -> meshtasticd IRQ
    "BUSY":  [("J1", "38"), ("U1", "14")],   # BCM GPIO20
    "TXEN":  [("J1", "33"), ("U1", "7")],    # BCM GPIO13 - RF switch, REQUIRED
    "RXEN":  [("J1", "32"), ("U1", "6")],    # BCM GPIO12 - RF switch, REQUIRED
    # U1 pad 8 (DIO2) and pad 21 (ANT) are intentionally unconnected.
    # ANT: antenna leaves via the module's IPEX connector, not this board.
}
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
    "U1": (E22, "E22-900M30S", 32.5, 30.0, 0),
    # decoupling column, right of U1's VCC pads (which land at x = 44.5)
    "C2": (CAP_CER, "0.1uF", 52.0, 16.0, 0),
    "C3": (CAP_CER, "0.1uF", 52.0, 22.0, 0),
    "C1": (CAP_EL, "1000uF", 53.0, 44.0, 0),
}

# Standard HAT mounting holes, 3.5 mm in from each corner.  [VERIFY]
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

body = []
corners = [(0, 0), (BW, 0), (BW, BH), (0, BH)]
for i in range(4):
    x1, y1 = corners[i]
    x2, y2 = corners[(i + 1) % 4]
    body.append(f'  (gr_line (start {BX+x1} {BY+y1}) (end {BX+x2} {BY+y2})'
                f' (stroke (width 0.1) (type default)) (layer "Edge.Cuts")'
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
        ("MeshGW HAT rev A - DRAFT", 32.5, 54.0, 1.6),
        ("DO NOT ORDER - land pattern unverified", 32.5, 56.0, 1.0)]:
    body.append(f'  (gr_text "{txt}" (at {BX+tx} {BY+ty}) (layer "F.SilkS")'
                f' (uuid "{U()}") (effects (font (size {sz} {sz})'
                f' (thickness 0.2))))')
body.append(f'  (gr_text "E22 VCC = 5V" (at {BX+52} {BY+30}) (layer "F.SilkS")'
            f' (uuid "{U()}") (effects (font (size 1 1) (thickness 0.15))))')

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
pts = " ".join(f"(xy {BX+x} {BY+y})" for x, y in
               [(0.3, 0.3), (BW - 0.3, 0.3), (BW - 0.3, BH - 0.3), (0.3, BH - 0.3)])
body.append(f'''  (zone (net {NETNUM["GND"]}) (net_name "GND") (layers "B.Cu")
    (uuid "{U()}") (name "GND_POUR") (hatch edge 0.5)
    (connect_pads yes (clearance 0.5))
    (min_thickness 0.25) (filled_areas_thickness no)
    (fill yes (thermal_gap 0.3) (thermal_bridge_width 0.4))
    (polygon (pts {pts}))
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
