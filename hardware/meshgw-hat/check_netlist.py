#!/usr/bin/env python3
"""Assert the SCHEMATIC's exported netlist equals netlist.py.

    kicad-cli sch export netlist --output out/meshgw-hat.net meshgw-hat.kicad_sch
    ./check_netlist.py out/meshgw-hat.net

Why this exists: `gen_pcb.py` builds the board straight from `netlist.py` and
never reads the schematic, so the two artefacts share an intent but not a
verification path. The schematic can be wrong in ways no board-side check can
see — and was.

On 2026-08-12 the exported schematic netlist had **no GND net at all**. C1, C2
and C3 were placed in a row 5.08 mm apart, `place()` draws a 2.54 mm stub off
every pin, so C1's right stub and C2's left stub met at exactly one point and
shorted GND to +5V. The result was a single 27-node "+5V" holding both plates
of all three decoupling caps — a dead short across the power rail, in the
document a human would actually build from. It surfaced as ONE ERC error
phrased as a two-PWR_FLAG complaint, which reads like a trivial annotation
nit. Meanwhile the PCB was correct and reported 0 DRC violations, 0
unconnected and 27/27 mechanical checks.

ERC cannot catch this in general: a wire joining two stubs is exactly what a
wire is for. Only comparing against the declared intent catches it.
"""
import re
import sys

from netlist import NETS, NC


def main(path):
    text = open(path).read()
    blk = text[text.index("(nets"):]

    got = {}
    marks = list(re.finditer(r'\(net \(code "\d+"\) \(name "([^"]*)"\)', blk))
    for i, m in enumerate(marks):
        end = marks[i + 1].start() if i + 1 < len(marks) else len(blk)
        seg = blk[m.end():end]
        name = m.group(1).lstrip("/")
        got[name] = {(r, p) for r, p in
                     re.findall(r'\(node \(ref "([^"]+)"\) \(pin "([^"]+)"\)',
                                seg)}

    want = {n: set(map(tuple, pads)) for n, pads in NETS.items()}

    fails = []

    # Deliberately-unconnected pins export as their own "unconnected-(...)"
    # nets. Drop them, but only after checking they really are alone.
    for name in list(got):
        if name.startswith("unconnected-"):
            if len(got[name]) != 1:
                fails.append(f"{name} has {len(got[name])} nodes, expected 1")
            del got[name]

    missing = set(want) - set(got)
    extra = set(got) - set(want)
    if missing:
        fails.append(f"nets in netlist.py but NOT in the schematic: "
                     f"{sorted(missing)}")
    if extra:
        fails.append(f"nets in the schematic but NOT in netlist.py: "
                     f"{sorted(extra)}")

    for name in sorted(set(want) & set(got)):
        if got[name] != want[name]:
            gained = got[name] - want[name]
            lost = want[name] - got[name]
            detail = []
            if gained:
                detail.append("gained " + " ".join(f"{r}.{p}" for r, p
                                                   in sorted(gained)))
            if lost:
                detail.append("lost " + " ".join(f"{r}.{p}" for r, p
                                                 in sorted(lost)))
            fails.append(f"net {name}: " + "; ".join(detail))

    # Every pin declared no-connect must actually be unconnected.
    for ref, pads in NC.items():
        for pad in pads:
            for name, nodes in got.items():
                if (ref, pad) in nodes:
                    fails.append(f"{ref} pad {pad} is declared NC in "
                                 f"netlist.py but sits on net {name}")

    print(f"{len(want)} nets compared: schematic vs netlist.py")
    for f in fails:
        print(f"  FAIL: {f}")
    if fails:
        print(f"{len(fails)} FAILED — the schematic does not describe the "
              f"board that gen_pcb.py builds")
        return 1
    print("all passed")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1
                  else "out/meshgw-hat.net"))
