#!/bin/bash
# Regenerate and autoroute the MeshGW Pi HAT, end to end.
#
#   ./route.sh
#
# Produces meshgw-hat-routed.kicad_pcb — that is the file to fab from.
# meshgw-hat.kicad_pcb is the generated, UNROUTED board (the router's input);
# do not send it to a fab house.
#
# Needs: KiCad 9 (kicad-cli), OpenJDK 17 (FULL jre — headless has no AWT),
# xvfb + xauth, and freerouting 1.9.0 at /opt/freerouting/freerouting.jar.
set -euo pipefail
cd "$(dirname "$0")"
mkdir -p out logs

BRIDGE=/opt/empire12-ops/scripts/kicad_dsn.py
FR=/opt/freerouting/freerouting.jar

# +5V feeds the E22's PA: 650 mA instantaneous on a TX burst (datasheet 2.2),
# on top of whatever the Pi is doing. KiCad DRC has NO current check — an
# undersized power trace passes every automated gate — so the width is stated
# here deliberately. 1.0 mm on 1 oz copper is ~3x margin for this load.
# GND is not listed: it is a poured plane (see fill_zones.py).
WIDE="--wide=+5V=1.0"

echo "== generate =="
python3 gen.py
python3 gen_pcb.py

echo "== export DSN =="
python3 "$BRIDGE" export meshgw-hat.kicad_pcb out/meshgw-hat.dsn "$WIDE"

echo "== autoroute =="
rm -f out/meshgw-hat.ses
# freerouting is GUI-bound even with CLI flags, hence xvfb-run.
timeout 900 xvfb-run -a java -jar "$FR" \
    -de out/meshgw-hat.dsn -do out/meshgw-hat.ses -mp 20 -mt 1 \
    > out/fr.log 2>&1 || true
grep -E "Auto-routing|optimization|Saving|routed" out/fr.log || {
    echo "autorouting produced no result — see out/fr.log"; exit 1; }

echo "== import SES =="
python3 "$BRIDGE" import meshgw-hat.kicad_pcb out/meshgw-hat.ses \
    meshgw-hat-routed.kicad_pcb

echo "== fill GND pour (pcbnew — kicad-cli cannot) =="
python3 fill_zones.py meshgw-hat-routed.kicad_pcb

echo "== DRC =="
kicad-cli pcb drc --output out/drc.rpt --severity-error \
    meshgw-hat-routed.kicad_pcb | grep -E "Found"

echo "== render =="
kicad-cli pcb export svg --output out/pcb-routed.svg \
    --layers "F.Cu,B.Cu,Edge.Cuts,F.SilkS" --page-size-mode 2 \
    --exclude-drawing-sheet meshgw-hat-routed.kicad_pcb >/dev/null

cat <<'EOF'

done — review out/pcb-routed.svg

A clean DRC here does NOT mean this board is fab-ready. Three failure modes
pass every automated check on this toolchain:
  1. Wrong land pattern  — the E22 footprint is datasheet-derived and has
     never been offered up to a physical module.
  2. Unfilled zones      — IsFilled() lies; fill_zones.py above is the fix,
     but confirm copper is actually present in the SVG.
  3. Power-trace width   — no current check exists; see $WIDE above.
Plus, specific to this board: the HAT mechanical geometry (BW/BH, HDR_X,
HDR_Y, MOUNT) in gen_pcb.py is UNVERIFIED against the official Raspberry Pi
HAT spec. If the header origin is wrong the board will not seat on the Pi.
EOF
