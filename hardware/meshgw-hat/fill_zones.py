#!/usr/bin/env python3
"""Fill copper zones in a routed board using KiCad's own zone filler.

kicad-cli has no zone-fill command and its DRC ignores unfilled zones, so the
B.Cu GND pour contributes nothing to connectivity until it is filled. This
loads the board, runs pcbnew's ZONE_FILLER (the same algorithm the GUI uses,
with correct pad/track clearances), and saves. After this the pour bonds every
through-hole GND pad, so GND reads as one connected net in DRC — no reliance on
freerouting having routed GND into a single tree.

Usage: fill_zones.py <board.kicad_pcb>   (edits in place)
"""
import sys
import pcbnew

path = sys.argv[1]
board = pcbnew.LoadBoard(path)
zones = board.Zones()
pcbnew.ZONE_FILLER(board).Fill(zones)
board.Save(path)
filled = sum(1 for z in zones)
print(f"filled {filled} zone(s) with pcbnew {pcbnew.Version()}")
