#!/usr/bin/env python3
"""The MeshGW HAT netlist — the single source for BOTH generators.

gen.py (schematic) and gen_pcb.py (board) used to each carry their own copy of
this map with a comment saying they must mirror each other. On 2026-08-11 they
stopped mirroring each other: the board was re-pinned and the schematic was
not, and nothing in the toolchain would have complained. One definition, two
consumers, no drift.

  * J1 pad numbers are Raspberry Pi HEADER pin numbers (not BCM GPIO).
  * U1 pad numbers are E22-900M30S datasheet pin numbers.

WHY THESE HEADER PINS (changed 2026-08-11, was the MeshAdv-Pi-Hat map)
----------------------------------------------------------------------
Every control line now lands on an ODD-numbered header pin. On the Pi the odd
pins are the INNER row and the even pins are the outer row against the board
edge, so a signal on an even pin has to thread the 1.04 mm gaps between the
inner row's pads to reach the board. With NSS/NRST/DIO1/BUSY/RXEN on even pins
(GPIO21/18/16/20/12, the MeshAdv reference map) freerouting could not finish
this board at all — it left four nets unrouted. On odd pins it routes clean,
0 violations and 0 unconnected, and the control lines get much shorter: DIO1,
BUSY and NRST now drop straight down into U1's left column instead of crossing
the whole board from the far end of the header.

The boot-time pull states improve too, which is the better argument of the
two. The Pi pulls GPIO0-8 UP and GPIO9-27 DOWN at reset:

  NSS  GPIO5  pulled UP   -> chip DESELECTED until the driver takes over.
                             GPIO21 pulled DOWN asserted CS at every boot.
  TXEN GPIO13 pulled DOWN -> no accidental transmit into a cold RF switch.
  RXEN GPIO6  pulled UP   -> receive path enabled, which is the safe default.
  NRST GPIO22 pulled DOWN -> module held in reset (NRST is active low).

Deliberately NOT used: pins 27/28 (ID_SD/ID_SC) are reserved by the HAT spec
for the ID EEPROM and must be left alone; pins 3/5 (GPIO2/3) carry the Pi's
fixed 1.8k I2C pull-ups; pins 24/26 (CE0/CE1) are left free because
meshtasticd drives chip-select in software.

If you re-pin this, config/meshtasticd/config.yaml must change to match — it
is the file that tells meshtasticd which GPIO is which.
"""

NETS = {
    "GND":   [("J1", "6"), ("J1", "9"), ("J1", "14"), ("J1", "20"),
              ("J1", "25"), ("J1", "30"), ("J1", "34"), ("J1", "39"),
              ("U1", "1"), ("U1", "2"), ("U1", "3"), ("U1", "4"), ("U1", "5"),
              ("U1", "11"), ("U1", "12"), ("U1", "20"), ("U1", "22"),
              ("C1", "2"), ("C2", "2"), ("C3", "2")],
    # E22 VCC is the 5V rail: the datasheet says >=5.0V for rated output power
    # and 650 mA on a TX burst. Do NOT move this to 3V3.
    "+5V":   [("J1", "2"), ("J1", "4"), ("U1", "9"), ("U1", "10"),
              ("C1", "1"), ("C2", "1"), ("C3", "1")],
    "+3V3":  [("J1", "1"), ("J1", "17")],
    "MOSI":  [("J1", "19"), ("U1", "17")],   # BCM GPIO10, SPI0
    "MISO":  [("J1", "21"), ("U1", "16")],   # BCM GPIO9,  SPI0
    "SCK":   [("J1", "23"), ("U1", "18")],   # BCM GPIO11, SPI0
    "NSS":   [("J1", "29"), ("U1", "19")],   # BCM GPIO5   software chip-select
    "NRST":  [("J1", "15"), ("U1", "15")],   # BCM GPIO22
    "DIO1":  [("J1", "11"), ("U1", "13")],   # BCM GPIO17 -> meshtasticd IRQ
    "BUSY":  [("J1", "13"), ("U1", "14")],   # BCM GPIO27
    "TXEN":  [("J1", "33"), ("U1", "7")],    # BCM GPIO13 - RF switch, REQUIRED
    "RXEN":  [("J1", "31"), ("U1", "6")],    # BCM GPIO6  - RF switch, REQUIRED
    # U1 pad 8 (DIO2) and pad 21 (ANT) are intentionally unconnected. ANT: the
    # antenna leaves via the module's IPEX connector, not this board.
}

# Header pin -> BCM GPIO, for the pinout note on the schematic and for
# cross-checking against config/meshtasticd/config.yaml by eye.
BCM = {"11": 17, "13": 27, "15": 22, "19": 10, "21": 9, "23": 11,
       "29": 5, "31": 6, "33": 13}

NC = {"U1": ("8", "21")}


def pins(ref):
    """{pad number: net name} for one reference designator."""
    return {pad: net for net, pads in NETS.items()
            for r, pad in pads if r == ref}


def netnums():
    """{net name: KiCad net number}, 0 reserved for the unnamed net."""
    return dict({"": 0}, **{n: i for i, n in enumerate(NETS, start=1)})
