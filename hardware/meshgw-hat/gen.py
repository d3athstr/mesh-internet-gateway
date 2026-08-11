#!/usr/bin/env python3
"""Generate the MeshGW Pi HAT symbol library + schematic.

The MeshGW HAT carries an Ebyte E22-900M30S (SX1262 + PA, 1 W) on a Raspberry
Pi 3B/3B+, turning it into a wired-Ethernet Meshtastic gateway running
meshtasticd. Design doc: ../../README.md, privacy rules:
../../docs/privacy-boundary.md.

GEOMETRY AND PINOUT ARE FROM THE DATASHEET, NOT FROM MEMORY
  E22-900M30S User Manual v1.20, sections 2.2 and 3:
    * body 38.5 x 24 x 3.6 mm, 22 castellated pads, 2.54 mm pitch
    * operating voltage 2.5-5.5 V, TYP 5.0 V, ">=5.0V ensures output power"
    * communication level 3.3 V
    * TX current 650 mA instantaneous, RX 14 mA
    * max TX power 30 dBm (29.5 min / 31 max)
    * pin 1-5 GND, 6 RXEN, 7 TXEN, 8 DIO2, 9 VCC, 10 VCC, 11-12 GND,
      13 DIO1, 14 BUSY, 15 NRST, 16 MISO, 17 MOSI, 18 SCK, 19 NSS,
      20 GND, 21 ANT, 22 GND

TWO CONSEQUENCES OF THAT DATASHEET READ, BOTH LOAD-BEARING:

1. VCC IS THE 5 V RAIL, NOT 3V3. The module is rated 2.5-5.5 V but only
   makes rated power at >=5 V, and it pulls 650 mA on a TX burst. The Pi's
   3V3 regulator has no business supplying that; the 5 V rail (straight off
   the USB input) does. Logic stays 3.3 V, so SPI wires to the Pi directly
   with no level shifting. Powering this module from 3V3 would "work" and
   quietly cost most of the 8 dB that motivated choosing it.

2. NO RF IS ROUTED ON THIS BOARD. The module carries its own IPEX connector;
   the antenna leaves via an IPEX->SMA bulkhead pigtail to the enclosure
   wall. Pad 21 (ANT stamp hole) is deliberately LEFT UNCONNECTED. A 2-layer
   autorouted board cannot hold a 50 ohm impedance, and a botched RF trace is
   invisible to every automated check we run.

TXEN/RXEN are driven explicitly from Pi GPIOs (matching the meshtasticd
config and the MeshAdv-Pi-Hat reference) rather than tying TXEN to DIO2. The
datasheet allows the DIO2 shortcut; explicit control is what meshtasticd's
config expects, and it keeps the failure mode diagnosable.

STATUS: DRAFT. See the verification checklist in README.md before ordering.
"""
import json, os, re, uuid

os.chdir(os.path.dirname(os.path.abspath(__file__)))
GRID = 1.27
LIB = "mgw"
PROJ = "meshgw-hat"


def snap(v):
    return round(round(v / GRID) * GRID, 4)


def U():
    return str(uuid.uuid4())


SYMS = {}


def sym(name, ref, fp, pins, w=10.16, datasheet="", desc="", power=False):
    ys = [p[4] for p in pins]
    top, bot = max(ys) + 2.54, min(ys) - 2.54
    body = ""
    if not power:
        body = (f'      (rectangle (start {-w} {top}) (end {w} {bot})\n'
                '        (stroke (width 0.254) (type default))'
                ' (fill (type background)))')
    pl, coords = [], {}
    for num, pn, et, side, y in pins:
        x, rot = (-w - 2.54, 0) if side == "L" else (w + 2.54, 180)
        coords[num] = (x, y)
        pl.append(f'''      (pin {et} line (at {x} {y} {rot}) (length 2.54)
        (name "{pn}" (effects (font (size 1.27 1.27))))
        (number "{num}" (effects (font (size 1.27 1.27)))))''')
    SYMS[name] = coords
    pwr = '    (power)\n' if power else ''
    return f'''  (symbol "{name}"
{pwr}    (pin_names (offset 0.508)) (exclude_from_sim no) (in_bom {"no" if power else "yes"}) (on_board yes)
    (property "Reference" "{ref}" (at 0 {top + 2.54} 0)
      (effects (font (size 1.27 1.27))))
    (property "Value" "{name}" (at 0 {bot - 2.54} 0)
      (effects (font (size 1.27 1.27))))
    (property "Footprint" "{fp}" (at 0 0 0)
      (effects (font (size 1.27 1.27)) (hide yes)))
    (property "Datasheet" "{datasheet}" (at 0 0 0)
      (effects (font (size 1.27 1.27)) (hide yes)))
    (property "Description" "{desc}" (at 0 0 0)
      (effects (font (size 1.27 1.27)) (hide yes)))
    (symbol "{name}_0_1"
{body}
    )
    (symbol "{name}_1_1"
{chr(10).join(pl)}
    )
  )'''


out = []

# ---- E22-900M30S. Pin order below matches the datasheet table exactly. ----
out.append(sym("E22_900M30S", "U", f"{LIB}:E22_900M30S", [
    ("9",  "VCC",  "power_in",     "L",  17.78),
    ("10", "VCC",  "power_in",     "L",  15.24),
    ("19", "NSS",  "input",        "L",  10.16),
    ("18", "SCK",  "input",        "L",   7.62),
    ("17", "MOSI", "input",        "L",   5.08),
    ("16", "MISO", "output",       "L",   2.54),
    ("15", "NRST", "input",        "L",   0.0),
    ("14", "BUSY", "output",       "L",  -2.54),
    ("13", "DIO1", "bidirectional", "L", -5.08),
    ("8",  "DIO2", "bidirectional", "L", -7.62),
    ("7",  "TXEN", "input",        "L", -10.16),
    ("6",  "RXEN", "input",        "L", -12.7),
    ("21", "ANT",  "passive",      "R",  17.78),
    ("1",  "GND",  "power_in",     "R",   7.62),
    ("2",  "GND",  "power_in",     "R",   5.08),
    ("3",  "GND",  "power_in",     "R",   2.54),
    ("4",  "GND",  "power_in",     "R",   0.0),
    ("5",  "GND",  "power_in",     "R",  -2.54),
    ("11", "GND",  "power_in",     "R",  -5.08),
    ("12", "GND",  "power_in",     "R",  -7.62),
    ("20", "GND",  "power_in",     "R", -10.16),
    ("22", "GND",  "power_in",     "R", -12.7)], 15.24,
    "https://www.cdebyte.com/products/E22-900M30S",
    "Ebyte E22-900M30S SX1262+PA 1W LoRa module (VCC=5V, logic 3.3V)"))

# ---- Raspberry Pi 40-pin GPIO header. Numbers are HEADER pin numbers. ----
_pi = [
    ("1",  "3V3",        "L",  25.4), ("2",  "5V",         "R",  25.4),
    ("6",  "GND",        "L",  22.86), ("4", "5V",         "R",  22.86),
    ("9",  "GND",        "L",  20.32), ("12", "GPIO18",    "R",  20.32),
    ("14", "GND",        "L",  17.78), ("19", "GPIO10_MOSI", "R", 17.78),
    ("20", "GND",        "L",  15.24), ("21", "GPIO9_MISO", "R", 15.24),
    ("25", "GND",        "L",  12.7), ("23", "GPIO11_SCLK", "R", 12.7),
    ("30", "GND",        "L",  10.16), ("32", "GPIO12",    "R",  10.16),
    ("34", "GND",        "L",   7.62), ("33", "GPIO13",    "R",   7.62),
    ("39", "GND",        "L",   5.08), ("36", "GPIO16",    "R",   5.08),
    ("17", "3V3",        "L",   2.54), ("38", "GPIO20",    "R",   2.54),
    ("40", "GPIO21",     "R",   0.0),
]
out.append(sym("RPi_GPIO40", "J", "Connector_PinHeader_2.54mm:PinHeader_2x20_P2.54mm_Vertical",
               [(n, nm, "passive", s, y) for n, nm, s, y in _pi], 17.78,
               "https://pinout.xyz/", "Raspberry Pi 40-pin GPIO header (HAT side)"))

out.append(sym("CP", "C", "Capacitor_THT:CP_Radial_D8.0mm_P3.50mm",
               [("1", "+", "passive", "L", 0.0), ("2", "-", "passive", "R", 0.0)],
               5.08, "", "Polarized electrolytic capacitor"))
out.append(sym("C", "C", "Capacitor_THT:C_Disc_D5.0mm_W2.5mm_P5.00mm",
               [("1", "1", "passive", "L", 0.0), ("2", "2", "passive", "R", 0.0)],
               5.08, "", "Ceramic disc capacitor"))
out.append(sym("PWR_FLAG", "#FLG", "", [("1", "pwr", "power_out", "L", 0.0)],
               2.54, "", "Power flag", power=True))

open(f"{LIB}.kicad_sym", "w").write(
    '(kicad_symbol_lib (version 20241209) (generator "empire12-gen")'
    ' (generator_version "9.0")\n' + "\n".join(out) + "\n)\n")

ROOT = U()
items, refs = [], {}


def place(lib, ref, val, at, conns, nc=(), dnp=False):
    px, py = snap(at[0]), snap(at[1])
    coords = SYMS[lib]
    ys = [c[1] for c in coords.values()]
    r_off, v_off = snap(max(ys) + 5.08), snap(abs(min(ys)) + 5.08)
    items.append(f'''  (symbol (lib_id "{LIB}:{lib}") (at {px} {py} 0) (unit 1)
    (exclude_from_sim no) (in_bom {"no" if ref.startswith("#") else "yes"})
    (on_board yes) (dnp {"yes" if dnp else "no"}) (uuid "{U()}")
    (property "Reference" "{ref}" (at {px} {snap(py - r_off)} 0)
      (effects (font (size 1.27 1.27))))
    (property "Value" "{val}" (at {px} {snap(py + v_off)} 0)
      (effects (font (size 1.27 1.27))))
{"".join(f'    (pin "{n}" (uuid "{U()}"))' + chr(10) for n in coords)}    (instances (project "{PROJ}"
      (path "/{ROOT}" (reference "{ref}") (unit 1))))
  )''')
    for num, net in conns.items():
        cx, cy = coords[num]
        ax, ay = snap(px + cx), snap(py - cy)
        d = -2.54 if cx < 0 else 2.54
        ex = snap(ax + d)
        items.append(f'  (wire (pts (xy {ax} {ay}) (xy {ex} {ay}))'
                     f' (stroke (width 0) (type default)) (uuid "{U()}"))')
        just, rot = ("right", 180) if d < 0 else ("left", 0)
        items.append(f'''  (label "{net}" (at {ex} {ay} {rot})
    (effects (font (size 1.27 1.27)) (justify {just} bottom)) (uuid "{U()}"))''')
    for num in nc:
        cx, cy = coords[num]
        items.append(f'  (no_connect (at {snap(px + cx)} {snap(py - cy)})'
                     f' (uuid "{U()}"))')
    if not ref.startswith("#"):
        refs[ref] = val


# ===================== Pi header J1 (left) ================================
place("RPi_GPIO40", "J1", "RPi 40-pin GPIO", (63.5, 118.11), {
    "2": "+5V", "4": "+5V",
    "1": "+3V3", "17": "+3V3",
    "6": "GND", "9": "GND", "14": "GND", "20": "GND", "25": "GND",
    "30": "GND", "34": "GND", "39": "GND",
    "19": "MOSI", "21": "MISO", "23": "SCK", "40": "NSS",
    "12": "NRST", "36": "DIO1", "38": "BUSY", "33": "TXEN", "32": "RXEN",
})

# ===================== E22 module U1 (right) ==============================
# ANT (pad 21) intentionally no-connect: the antenna leaves via the module's
# own IPEX connector and a pigtail. DIO2 unused (TXEN driven from GPIO13).
place("E22_900M30S", "U1", "E22-900M30S", (152.4, 118.11), {
    "9": "+5V", "10": "+5V",
    "19": "NSS", "18": "SCK", "17": "MOSI", "16": "MISO",
    "15": "NRST", "14": "BUSY", "13": "DIO1",
    "7": "TXEN", "6": "RXEN",
    "1": "GND", "2": "GND", "3": "GND", "4": "GND", "5": "GND",
    "11": "GND", "12": "GND", "20": "GND", "22": "GND",
}, nc=("8", "21"))

# ===================== Decoupling ========================================
# C1 bulk: the 650 mA TX burst is a step load on a rail that arrives through
# a stacking header. C2/C3 are the "external ceramic filter capacitor" the
# datasheet asks for at each VCC pin.
#
# C1's value says 6.3 V because that is what is in stock, and 6.3 V on a 5 V
# rail is ~26 % headroom — right at the usual 80 % derating limit. BUY A 10 V
# OR 16 V PART. The footprint (D8.0 mm, P3.50 mm) is unchanged either way, so
# this is a purchasing decision, not a layout one.
place("CP", "C1", "1000uF 6.3V", (109.22, 165.1), {"1": "+5V", "2": "GND"})
place("C", "C2", "0.1uF", (129.54, 165.1), {"1": "+5V", "2": "GND"})
place("C", "C3", "0.1uF", (147.32, 165.1), {"1": "+5V", "2": "GND"})

# The Pi header is the only source on +5V/+3V3/GND and its pins are passive,
# so ERC needs flags or it reports "no power source".
place("PWR_FLAG", "#FLG_5", "PWR_FLAG", (109.22, 180.34), {"1": "+5V"})
place("PWR_FLAG", "#FLG_G", "PWR_FLAG", (129.54, 180.34), {"1": "GND"})
place("PWR_FLAG", "#FLG_3", "PWR_FLAG", (147.32, 180.34), {"1": "+3V3"})

TXT = []


def note(t, x, y, size=2.0):
    TXT.append(f'  (text "{t}" (at {snap(x)} {snap(y)} 0)'
               f' (effects (font (size {size} {size})) (justify left bottom))'
               f' (uuid "{U()}"))')


note("MeshGW Pi HAT - E22-900M30S carrier (rev A DRAFT, 2026-08-10)", 20, 15.24, 3.0)
note("DO NOT ORDER: E22 land pattern is datasheet-derived and has NOT been", 20, 21.59, 2.0)
note("checked against a physical part; HAT mechanical geometry unverified.", 20, 26.67, 2.0)

NX, NY = 20.0, 200.0
for i, line in enumerate([
        "POWER: E22 VCC = +5V (Pi header pins 2/4), NOT 3V3.",
        "  Datasheet: 2.5-5.5V range but '>=5.0V ensures output power',",
        "  650 mA instantaneous on a TX burst. The Pi 3V3 regulator must",
        "  not carry that. Logic level is 3.3V so SPI wires straight to",
        "  the Pi with no level shifting.",
        "",
        "RF: pad 21 (ANT stamp hole) is NO-CONNECT by design. The antenna",
        "  leaves through the module's own IPEX connector via an IPEX->SMA",
        "  bulkhead pigtail. Nothing on this 2-layer board is impedance-",
        "  controlled, and a bad RF trace passes every automated check.",
        "",
        "PIN MAP (BCM) - mirrors config/meshtasticd/config.yaml exactly:",
        "  NSS  GPIO21 (hdr 40)   BUSY GPIO20 (hdr 38)",
        "  SCK  GPIO11 (hdr 23)   DIO1 GPIO16 (hdr 36)",
        "  MOSI GPIO10 (hdr 19)   NRST GPIO18 (hdr 12)",
        "  MISO GPIO9  (hdr 21)   TXEN GPIO13 (hdr 33)",
        "                         RXEN GPIO12 (hdr 32)",
        "  Change one, change BOTH files.",
        "",
        "TXEN/RXEN are REQUIRED - the E22 has an RF switch. Leave them",
        "  unconnected and the PA transmits into a closed switch.",
        "",
        "NEVER power the module without an antenna: 1W into an open",
        "  circuit damages the PA.",
]):
    if line:
        note(line, NX, NY + i * 5.6, 1.7)

sch = f'''(kicad_sch (version 20250114) (generator "empire12-gen") (generator_version "9.0")
  (uuid "{ROOT}")
  (paper "A3")
  (title_block (title "MeshGW Pi HAT - E22-900M30S carrier") (date "2026-08-10")
    (rev "A") (company "Empire12"))
  (lib_symbols)
{chr(10).join(items)}
{chr(10).join(TXT)}
  (sheet_instances (path "/" (page "1")))
)
'''

lib = open(f"{LIB}.kicad_sym").read()
blocks, i = [], 0
while True:
    m = re.search(r'\n  \(symbol "([^"]+)"', lib[i:])
    if not m:
        break
    start, name = i + m.start() + 1, m.group(1)
    d, j = 0, start
    while True:
        if lib[j] == '(':
            d += 1
        elif lib[j] == ')':
            d -= 1
            if d == 0:
                break
        j += 1
    blocks.append(lib[start:j + 1].replace(
        f'(symbol "{name}"', f'(symbol "{LIB}:{name}"', 1))
    i = j + 1
sch = sch.replace("  (lib_symbols)", "  (lib_symbols\n" + "\n".join(blocks) + "\n  )")
open(f"{PROJ}.kicad_sch", "w").write(sch)

open("sym-lib-table", "w").write(
    '(sym_lib_table\n  (version 7)\n  (lib (name "mgw")(type "KiCad")'
    '(uri "${KIPRJMOD}/mgw.kicad_sym")(options "")(descr "MeshGW symbols"))\n)\n')
open("fp-lib-table", "w").write(
    '(fp_lib_table\n  (version 7)\n  (lib (name "mgw")(type "KiCad")'
    '(uri "${KIPRJMOD}/lib.pretty")(options "")(descr "MeshGW footprints"))\n)\n')
open(f"{PROJ}.kicad_pro", "w").write(json.dumps({
    "board": {"design_settings": {}},
    "libraries": {"pinned_footprint_libs": [], "pinned_symbol_libs": []},
    "meta": {"filename": f"{PROJ}.kicad_pro", "version": 3},
    "sheets": [[ROOT, "Root"]]}, indent=2) + "\n")

print(f"symbols: {len(out)}   components: {len(refs)}")
for r, v in sorted(refs.items()):
    print(f"  {r:6} {v}")
