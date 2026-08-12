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
# here deliberately. IPC-2221 external, 1 oz copper, 10 C rise: 0.4 mm carries
# ~1.24 A, so ~1.9x the 650 mA peak. It is NOT wider because it cannot be:
# every +5V run has to thread the 1.04 mm gaps between the header's pads, and
# at 0.5 mm and 1.0 mm freerouting could not complete the board at all.
# GND is not listed: it is a poured plane (see fill_zones.py).
WIDE="--wide=+5V=0.4"

echo "== generate =="
python3 gen.py
python3 gen_pcb.py

# The schematic and the board share netlist.py but NOT a verification path:
# gen_pcb.py never reads the sheet, so the sheet can be wrong in ways every
# board-side check passes. It was — see check_netlist.py's docstring.
echo "== ERC + schematic netlist vs netlist.py =="
kicad-cli sch erc --output out/erc.rpt --severity-error \
    meshgw-hat.kicad_sch | grep -E "Found|violation"
kicad-cli sch export netlist --output out/meshgw-hat.net \
    meshgw-hat.kicad_sch >/dev/null
python3 check_netlist.py out/meshgw-hat.net

echo "== export DSN =="
python3 "$BRIDGE" export meshgw-hat.kicad_pcb out/meshgw-hat.dsn "$WIDE"

echo "== autoroute =="
rm -f out/meshgw-hat.ses
# Two JVMs on this 2-vCPU box is how a run dies. Queue behind another session's
# router rather than racing it. Bracket trick: pgrep -f "freerouting" would
# match this very script.
while pgrep -f "[f]reerouting.jar" >/dev/null; do
    echo "  another freerouting is running — waiting"; sleep 30
done
# freerouting is GUI-bound even with CLI flags, hence xvfb-run.
# nice: this is a 2-vCPU box that often has several other jobs on it, and a
# CPU-starved freerouting silently produces no .ses at all — which reads like a
# design failure and is not one.
timeout 1800 nice -n 10 xvfb-run -a java -jar "$FR" \
    -de out/meshgw-hat.dsn -do out/meshgw-hat.ses -mp 20 -mt 1 \
    > out/fr.log 2>&1 || true
# Assert the ARTEFACT, never the log. freerouting prints "Starting route
# optimization" well before it writes the SES, so a log grep PASSES on a run
# that then dies — and it dies silently under CPU/memory starvation, which
# looks exactly like a bad design. `timeout ... || true` above swallows it.
[ -s out/meshgw-hat.ses ] || {
    echo "autorouting produced no .ses — see out/fr.log."
    echo "Check load first: a starved freerouting fails silently."
    uptime; exit 1; }
grep -E "Auto-routing|optimization|Saving|routed" out/fr.log || true

echo "== import SES =="
python3 "$BRIDGE" import meshgw-hat.kicad_pcb out/meshgw-hat.ses \
    meshgw-hat-routed.kicad_pcb

echo "== fill GND pour (pcbnew — kicad-cli cannot) =="
python3 fill_zones.py meshgw-hat-routed.kicad_pcb

echo "== DRC =="
kicad-cli pcb drc --output out/drc.rpt --severity-error \
    meshgw-hat-routed.kicad_pcb | grep -E "Found"

echo "== mechanical checks (DRC has no opinion on any of these) =="
python3 check_geometry.py meshgw-hat-routed.kicad_pcb

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
Plus, specific to this board: freerouting is given only the bounding BOX of
Edge.Cuts by the DSN bridge, so it does not know about the radiused corners or
the Pi 3B+ PoE notch. Copper wandering into either shows up as
copper_edge_clearance in the DRC above, NOT as a routing failure — so read the
DRC report, do not just check that routing completed.
EOF
