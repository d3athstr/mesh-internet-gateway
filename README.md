# Mesh Internet Gateway (`meshgw`)

Wired-Ethernet Raspberry Pi + 1 W SX1262 LoRa gateway running **`meshtasticd`**.
Bridges the Empire12 / Techtaria LoRa mesh to the internet over MQTT, and
publishes **E12-owned nodes only** to the public Meshtastic map directories.

PartsBin project **[18]**. Status: **bare boards cleared to order 2026-08-12**;
nothing fabbed or deployed yet. The E22 radio is on order (AliExpress 1773).

**Projected cost ~$81.81**, of which **$35.00 is the Raspberry Pi itself** —
check the shelf first, a spare 3B/3B+/4 makes that line $0. The next largest
is the E22 at **$17.10**, which is what was actually paid on a single-item
AliExpress order; LCSC lists the bare module at ~$7.19, so the difference is
probably bundled shipping and worth checking before buying a second one. The
custom HAT is ~$0.80 ($4 for 5 boards) and the printed enclosure ~$1.20 of
filament — between them under 3 % of the build.

---

## Why this exists

Today the mesh's only internet-adjacent node is the Heltec V4 gateway
`!f66ae684` (`***REMOVED-HOST***`, ***REMOVED-IP***). It is a poor
foundation for an internet bridge:

| Problem | Evidence |
|---|---|
| ESP32 **WiFi-hang** — CPU alive, WiFi stack dead, every TCP client drops | Down again **2026-08-10 ~12:37**, ops bridge crash-looping `No route to host` → `BrokenPipe`. Needs a Tuya-switch power cycle to recover. |
| Serves **one** streaming TCP-API client, reliably | Already forced HA onto its own dedicated V3 radio (**D049**) |
| Bridge does **not** auto-reconnect | `meshtastic-bridge-watchdog.timer` exists solely to paper over it |
| WiFi-only | No wired path; it lives on E12-DMZ WiFi |

That radio is on the **load-bearing OOB control path** (4th reach channel,
D048). Hanging an internet/MQTT bridge off it stacks a new dependency on the
component that is already the mesh's most frequent outage.

`meshgw` is a separate, wired, purpose-built box. The V4 keeps doing C&C;
`meshgw` owns the internet bridge.

---

## Design

| Piece | Choice | Why |
|---|---|---|
| Host | **Raspberry Pi 3B/3B+** (wired Ethernet) | Native Ethernet kills the WiFi-hang failure mode. `meshtasticd` is a real Linux daemon — multiple concurrent API clients, no single-TCP-slot contention. Cheapest board with Ethernet + 40-pin header; a spare is likely already on the shelf. |
| Radio | **Ebyte E22-900M30S** (SX1262 + PA, 30 dBm) | ~$14 bare module vs ~$30 for a commercial LoRa HAT, and **1 W / 30 dBm** vs the Heltec's 22 dBm SX1262 ceiling — ~8 dB more link budget on the same mesh. |
| Carrier | **Custom HAT PCB** (`hardware/meshgw-hat/`) | A bare module needs a carrier. KiCad 9 headless, `gen.py` + freerouting — same workflow as the OSL / FD2 / Warden carriers. |
| Enclosure | **3D-printed, parametric** (`enclosure/`) | OpenSCAD source. Indoor shelf/rack box — *not* weatherproof. |
| Uplink | MQTT → `mqtt.meshtastic.org` | What makes nodes appear on the public map directories. |

### Ruled out: ESP32 + Ethernet

WT32-ETH01 (ESP32 + LAN8720) would have been the cheapest wired option
(~$8). **Rejected:** native ESP32 Ethernet support is
[meshtastic/firmware PR #9586](https://github.com/meshtastic/firmware/pull/9586),
which is **closed and never merged** (verified 2026-08-10 via the GitHub API).
Using it means maintaining a firmware fork on the OOB control path. Not
acceptable for this role.

### Ruled out: reuse an in-stock Heltec V4

Zero cost (2 on hand), but it reintroduces the exact WiFi-hang failure mode
that has the current gateway down as this is being written. Reasonable as a
**cold standby**, not as the primary.

---

## Privacy boundary — read `docs/privacy-boundary.md`

This is the part that must not be got wrong.

- **Only E12-owned nodes** are published: `meshgw` itself, the Heltec V4
  gateway, the HA V3, and the e12solar RAK router.
- **Techtaria customer-home endpoints stay dark.** No `ok_to_mqtt`, no map
  reporting, ever. Publishing them would put approximate customer home
  locations on public maps.
- **`paw-cmd` (idx 1, C&C) and `Techtaria` (idx 2, community) have uplink AND
  downlink OFF.** Only the default primary channel uplinks. Downlink on the
  C&C channel would let internet-sourced packets inject into the command path.

The HMAC envelope on the C&C receiver is a second line of defence, not a
reason to relax the first.

---

## Repo layout

```
config/meshtasticd/    config.yaml (E22 pinout), MQTT + channel policy, systemd
hardware/meshgw-hat/   KiCad: netlist.py, gen.py, gen_pcb.py, route.sh,
                       check_geometry.py, lib.pretty/
enclosure/             OpenSCAD parametric case + build notes
docs/                  design notes, privacy boundary, provisioning runbook
scripts/               provisioning helpers
```

`netlist.py` is the **single source of truth for the pinout** — the schematic
generator, the board generator and (by hand) `config/meshtasticd/config.yaml`
all derive from it. It used to be duplicated in `gen.py` and `gen_pcb.py` with
a comment saying the two must mirror each other; on 2026-08-11 they silently
stopped mirroring each other. Change the map in one place.

## The HAT is mechanically verified, the footprints are not

These are two different claims and only the first one is true.

`check_geometry.py` asserts 27 facts about the **routed** board against the
Raspberry Pi HAT mechanical specification and the Pi 3B+: outline 65 x 56 mm
with R3 corners, all 40 header pads on the spec grid from pin 1 at
(8.37, 4.77), four 2.75 mm mounting holes with 6.2 mm isolated lands, no
copper over the Pi 3B+ PoE header, the ground pour actually filled, and the
`+5V` width. It exists because on this toolchain **a board can pass DRC with
0 violations and 0 unconnected and still be scrap** — the previous revision
of this board did exactly that with its two header rows swapped, which would
have put every SPI signal on its neighbour's pin.

Run it on anything you are about to fab. `route.sh` runs it automatically.

Two deliberate deviations from the spec: there are no camera/display flex
cutouts, and there is no ID EEPROM. Without the EEPROM this is a board in the
HAT *form factor*, not a certified HAT, and the Pi will not auto-configure it
— which is fine here, because `meshtasticd` is told the pinout explicitly.

### Pi 3B+ PoE header

The 3B+ adds a 4-pin PoE header (J14) that the 3B does not have, and it stands
tall enough to foul a HAT. The board has an **edge-open notch** rather than an
enclosed cutout, because J14 leaves only ~1 mm to the board edge and an
enclosed cutout would leave a 1 mm FR4 bridge that would snap.

Fit is the smaller reason. J14 sits on the Ethernet magnetics' centre taps, so
on a PoE-capable switch those pins can carry ~48-57 V — and this is by
definition a wired-Ethernet gateway, so it is exactly the machine likely to be
plugged into such a switch. Copper over J14 is checked for, not assumed.

## Build state

| Item | State |
|---|---|
| PartsBin project [18] + BOM | **done** — 11 lines |
| meshtasticd config | **drafted**, untested against real hardware |
| Device provisioning script | **drafted**, never run against a radio. Admin key comes from Vault (`secret/empire12/meshtastic/admin-key`), not from this repo |
| HAT PCB | **rev A, gerbers built, cleared to order 2026-08-12.** Mechanically verified against the HAT spec and the Pi 3B+ (see below); 119 segments, 0 vias, DRC 0/0, ERC 0, 27/27 mechanical assertions, schematic netlist matches `netlist.py`. Fab package `out/fab/meshgw-hat-revA-gerbers.zip`. **Exported on a recorded override — U1's land pattern still has not met a physical module. CHECK U1'S FIT BEFORE SOLDERING.** See `fab_gate.py` |
| Enclosure | **DRAFT** — all three parts render solid, dimensions not validated against a real Pi + HAT stack. Print `coupon` first |
| Deployment | not started |

### Bare boards were ordered with U1's land pattern unverified — on purpose

Don's call, 2026-08-12, recorded in `fab_gate.py` rather than laundered into a
flag that claims the unknown was resolved. `GEOMETRY_VERIFIED` is still
`False`; a separate `GEOMETRY_OVERRIDE` string permits the export and says who
decided, when, and why. Six weeks from now "verified" and "we decided to risk
it" are very different things to read.

The reasoning: boards are ~$2 and JLCPCB shipping is $6–25, so batching this
into the same checkout as OSL, FD2, pool and Sentinel costs ~$2 marginal.
Holding it back would pay that shipping charge again later *with certainty*.
If the land pattern is wrong the loss is ~$2 of board plus one respin's
shipping — cheaper in expectation than waiting, unless no further order is
ever placed.

**This is a real risk, not a formality.** The E22 solders to castellated pads,
so a wrong land pattern makes these boards scrap. That is unlike the Sentinel
carrier, where the open items were modules on headers and a wrong guess costs
a module rather than a respin.

**When the module arrives, before any soldering:** offer it up to the bare
board. Check the 2.54 mm pitch, both irregular gaps (7.60 mm pin 19→20,
5.46 mm pin 21→22), and that the castellations land on the 1 mm of pad left
outside the module body. Then set `GEOMETRY_VERIFIED = True` and clear
`GEOMETRY_OVERRIDE`. The board silkscreens the same warning, because that is
the object you will be holding at that moment.

### Still to check before the parts go on

1. **The E22-900M30S land pattern, against the physical module** (above). The
   footprint is internally self-consistent with its cited datasheet figures —
   pad count, first-pad offset, pitch, both irregular gaps and the pin ring
   direction were re-checked 2026-08-12 — but that only proves it was
   transcribed correctly, not that the source figures are right. Note the
   deliberate deviation: the land is 2.0 mm wide against a 0.80 mm
   castellation, centred on the body edge so 1 mm sits outside for a solder
   fillet. That is correct practice; do not "fix" it back to 0.80.
2. **Hand-check power-trace width.** KiCad DRC has no current check. The E22
   pulls ~650 mA peak on a 30 dBm TX burst; `route.sh` asks for 0.4 mm on
   `+5V`, which IPC-2221 puts at ~1.24 A on 1 oz external copper for a 10 °C
   rise — about 1.9x the peak. It is not wider because it cannot be: every
   `+5V` run has to thread the 1.04 mm gaps between the header's pads, and at
   0.5 mm and 1.0 mm freerouting could not finish the board at all. If you
   want more margin, the honest fix is a second `+5V` path on B.Cu, not a
   bigger number in `route.sh`.
3. **Confirm the Pi's 5V rail holds through a TX burst.** The E22 runs from
   **5 V, not 3V3** — the datasheet is explicit that ">=5.0 V ensures output
   power", and its SPI/control pins are 3.3 V logic so they land on the Pi's
   GPIO directly. A sagging rail during TX presents as terrible range, not as
   a power fault, which is why `provision-meshgw.sh` starts at `tx_power 22`
   and leaves 30 for after the rail is proven.
4. Check SMA vs **RP**-SMA on the pigtail against the antennas in stock.
5. **Swap C1 for a 10 V or 16 V part.** The 1000 µF in stock is rated 6.3 V;
   on a 5 V rail that is ~26 % headroom, right at the usual 80 % derating
   limit, and the Pi's 5 V rail does not sit low. The C1 footprint
   (D8.0 mm, P3.50 mm) takes either.
6. **Print the enclosure `coupon`** and offer it up to a real Pi 3B before
   committing to the ~4 h full base print.

> **Never power the E22 without an antenna attached.** 1 W into an open
> circuit damages the PA.
