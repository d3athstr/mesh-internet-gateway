#!/bin/bash
# Export a JLCPCB-ready gerber + drill package for the MeshGW Pi HAT.
#
#   ./make_fab.sh          -> out/fab/meshgw-hat-revA-gerbers.zip
#
# Run ./route.sh first. Deliberately separate from route.sh: routing is safe to
# re-run any time, producing a fab package is the step that leads to spending
# money on boards.
#
# Gates come from fab_gate.py — read it. GEOMETRY blocks, FUNCTION warns, and
# on this board GEOMETRY is NOT verified: it exports only because there is an
# explicit recorded override.
set -euo pipefail
cd "$(dirname "$0")"

SRC=meshgw-hat-routed.kicad_pcb
FAB=out/fab
BOARD=$FAB/meshgw-hat-fab.kicad_pcb
REV=$(python3 -c "import fab_gate; print(fab_gate.REV)")
ZIP=$FAB/meshgw-hat-rev${REV}-gerbers.zip

BLOCK=$(python3 -c "import fab_gate; print(fab_gate.blocked() or '')")
[ -z "$BLOCK" ] || {
    echo "REFUSING TO EXPORT — $BLOCK" >&2
    echo "See fab_gate.py; check the part, fix the footprint, re-route." >&2
    exit 1; }

[ -f "$SRC" ] || { echo "no $SRC — run ./route.sh first" >&2; exit 1; }

rm -rf "$FAB"
mkdir -p "$FAB/gerbers"

# Work on a COPY. Never mutate the routed board in the shared repo — several
# claude sessions run on this box and tarring a live generated file has already
# produced a silently corrupt copy once (different DRC on each machine).
cp "$SRC" "$BOARD"

# Fill again on the copy. route.sh already fills, but a fab run must not inherit
# an assumption: an UNFILLED pour exports as a blank layer and neither the
# gerber viewer nor DRC complains. fill_zones.py asserts real filled_polygon
# vertices — ZONE.IsFilled() lies.
echo "== fill zones on the fab copy =="
python3 fill_zones.py "$BOARD"

echo "== DRC (fab copy) =="
kicad-cli pcb drc --output "$FAB/drc-fab.rpt" --severity-error "$BOARD" \
    | grep -E "Found"
# Gate on the REPORT FILE's phrasing ("Found 0 DRC violations"), which differs
# from kicad-cli's stdout phrasing ("Found 0 violations"). Matching stdout's
# wording against the file refuses every board — the Warden's copy of this
# script has exactly that bug.
grep -qE "Found 0 DRC violations" "$FAB/drc-fab.rpt" \
  && grep -qE "Found 0 unconnected pads" "$FAB/drc-fab.rpt" \
  && grep -qE "Found 0 Footprint errors" "$FAB/drc-fab.rpt" || {
    echo "DRC is not clean on the fab copy — see $FAB/drc-fab.rpt" >&2
    grep -E "Found" "$FAB/drc-fab.rpt" >&2; exit 1; }

echo "== mechanical checks (fab copy) =="
# The board being the right SHAPE is not something DRC has an opinion about,
# and this board's whole history is that it passed DRC while unfabbable.
python3 check_geometry.py "$BOARD"

echo "== gerbers =="
# --subtract-soldermask matters for the silk; --use-drill-file-origin keeps the
# drill files on the same origin as the copper.
kicad-cli pcb export gerbers --output "$FAB/gerbers" \
    --layers "F.Cu,B.Cu,F.SilkS,B.SilkS,F.Mask,B.Mask,Edge.Cuts" \
    --subtract-soldermask --use-drill-file-origin "$BOARD" >/dev/null

echo "== drill =="
# The flag is --excellon-units, NOT --units. The wrong one silently prints help
# and writes no files, leaving a zip with copper in it and no holes.
kicad-cli pcb export drill --output "$FAB/gerbers" --format excellon \
    --excellon-units mm --excellon-separate-th \
    --drill-origin plot --generate-map --map-format gerberx2 "$BOARD" >/dev/null

# ASSERT EVERY EXPECTED LAYER BY NAME.
# kicad-cli writes PROTEL extensions (.gtl/.gbl/.gts/.gbs/.gto/.gbo/.gm1) NOT
# .gbr, regardless of the board's (usegerberextensions no). A `*.gbr` glob
# matches nothing, and with a `|| :` fallback it once shipped a zip holding only
# the drill files and reported success. Name them, count them, or ship air.
echo "== verify package =="
# kicad-cli names every output after the BOARD FILE, so the fab copy's name is
# the prefix — derive it rather than hardcoding, or this check fails on a
# filename change while the real export was fine.
P=$(basename "$BOARD" .kicad_pcb)
missing=0
for f in "$P-F_Cu.gtl" "$P-B_Cu.gbl" \
         "$P-F_Silkscreen.gto" "$P-B_Silkscreen.gbo" \
         "$P-F_Mask.gts" "$P-B_Mask.gbs" \
         "$P-Edge_Cuts.gm1" \
         "$P-PTH.drl" "$P-NPTH.drl"; do
    if [ -s "$FAB/gerbers/$f" ]; then
        printf '   ok   %-40s %6s bytes\n' "$f" "$(stat -c%s "$FAB/gerbers/$f")"
    else
        printf '   MISS %s\n' "$f"; missing=$((missing+1))
    fi
done
[ "$missing" -eq 0 ] || {
    echo "FAIL: $missing expected fab file(s) missing — do NOT send this zip." >&2
    ls -1 "$FAB/gerbers" >&2; exit 1; }

echo "== drill sizes vs JLCPCB minimum =="
# A hole under the fab's minimum is a rejected order or a silent substitution,
# and nothing upstream of here checks it. JLCPCB: 0.3 mm minimum drill.
python3 - "$FAB/gerbers" <<'PY'
import glob, re, sys
mins = []
for f in glob.glob(sys.argv[1] + "/*.drl"):
    tools = {t: float(d) for t, d in
             re.findall(r'^(T\d+)C([\d.]+)', open(f).read(), re.M)}
    for t, d in sorted(tools.items()):
        print(f"   {f.split('/')[-1]:32s} {t} {d:.2f} mm")
        mins.append(d)
assert mins, "no drill tools found — the drill export produced nothing"
print(f"   smallest {min(mins):.2f} mm (JLCPCB minimum 0.30 mm)")
assert min(mins) >= 0.30, f"drill {min(mins)} mm is below JLCPCB's 0.30 mm"
PY

echo "== preview =="
kicad-cli pcb export svg --output "$FAB/meshgw-fab-preview.svg" \
    --layers "F.Cu,B.Cu,Edge.Cuts,F.SilkS" --page-size-mode 2 \
    --exclude-drawing-sheet "$BOARD" >/dev/null
rsvg-convert -z 4 -b white "$FAB/meshgw-fab-preview.svg" \
    -o "$FAB/meshgw-fab-preview.png"

rm -f "$ZIP"
( cd "$FAB/gerbers" && zip -q -r "../$(basename "$ZIP")" . )

# Assert the archive really holds what we just checked, rather than trusting zip.
members=$(unzip -l "$ZIP" | tail -1 | awk '{print $2}')
[ "$members" -ge 9 ] || {
    echo "FAIL: archive holds only $members member(s)" >&2; exit 1; }

echo
echo "wrote $ZIP  ($members members)"

python3 -c "import fab_gate,sys; sys.exit(0 if fab_gate.GEOMETRY_VERIFIED else 1)" || cat <<EOF

────────────────────────────────────────────────────────────────────────────
EXPORTED ON AN OVERRIDE — U1's LAND PATTERN IS STILL UNVERIFIED.

  $(python3 -c "import fab_gate; print(fab_gate.GEOMETRY_OVERRIDE)")

The E22 solders to castellated pads, so if that land pattern is wrong these
boards are scrap — this is not the Sentinel case where a wrong guess costs a
module on a header. The bet is ~\$2 of board against a shipping charge.

WHEN THE MODULE ARRIVES, BEFORE ANY SOLDERING: offer it up to the bare board.
Check pitch, the two irregular gaps (7.60 mm pin19->20, 5.46 mm pin21->22),
and that the castellations sit on the 1 mm of land left outside the body.
Then set GEOMETRY_VERIFIED = True and clear GEOMETRY_OVERRIDE in fab_gate.py.
The board silkscreens the same warning, because it is the board you will be
holding at that moment.
────────────────────────────────────────────────────────────────────────────
EOF

echo
echo "Hand the zip to Don — JLCPCB ordering is NOT automatable (login + bot"
echo "protection, partner-gated API) and an order spends money."
echo "2 layer, 1.6 mm, HASL. Check the preview PNG before uploading."
echo "Batch with OSL + FD2 + pool + Sentinel in ONE checkout — shipping"
echo "(\$6-25) dominates; the boards themselves are ~\$2 each."
