#!/usr/bin/env python3
"""Assert the MeshGW HAT's mechanical facts against the ROUTED board.

    ./check_geometry.py meshgw-hat-routed.kicad_pcb

Why this exists: on this toolchain a board can pass `kicad-cli pcb drc` with
0 violations and 0 unconnected and still be scrap. DRC has no opinion about
whether the header sits where a Raspberry Pi's header actually is, whether the
board is the size the HAT spec says, whether the ground pour really filled, or
whether a track is wide enough for the current it carries. The previous
revision of this board passed DRC cleanly with its two header rows swapped —
every SPI signal would have landed on its neighbouring pin.

Every number here comes from the specification, not from whatever the
generator happened to emit; the sources are cited in gen_pcb.py's docstring.
If a check fails the board is wrong. If a check needs changing, the
specification changed.

The board is parsed as s-expressions, not with regexes: pcbnew rewrites this
file in its own canonical multi-line form when fill_zones.py saves it, so the
one-line shapes gen_pcb.py emits are not what ends up on disk.
"""
import math
import re
import sys

BX, BY = 100.0, 60.0           # board origin on the KiCad page
BW, BH = 65.0, 56.0
CORNER_R = 3.0
MOUNT = [(3.5, 3.5), (61.5, 3.5), (3.5, 52.5), (61.5, 52.5)]
MOUNT_LAND = 6.2
# Pi 3B+ PoE header J14 body, measured off the official mechanical drawing.
J14 = (59.05, 7.38, 64.02, 11.92)
MIN_5V_WIDTH = 0.4             # see route.sh for the current-carrying sum

fails, checks = [], 0


def parse(text):
    toks = re.findall(r'"(?:[^"\\]|\\.)*"|[()]|[^\s()]+', text)
    stack, cur = [], []
    for t in toks:
        if t == '(':
            stack.append(cur)
            cur = []
        elif t == ')':
            parent = stack.pop()
            parent.append(cur)
            cur = parent
        else:
            cur.append(t[1:-1] if t.startswith('"') else t)
    return cur[0]


def kids(node, tag):
    return [c for c in node if isinstance(c, list) and c and c[0] == tag]


def kid(node, tag):
    k = kids(node, tag)
    return k[0] if k else None


def walk(node, tag):
    """Every descendant with this tag, at any depth."""
    out = []
    if isinstance(node, list):
        if node and node[0] == tag:
            out.append(node)
        for c in node:
            if isinstance(c, list):
                out += walk(c, tag)
    return out


def xy(node, tag):
    n = kid(node, tag)
    return (float(n[1]), float(n[2])) if n else None


def ok(cond, msg):
    global checks
    checks += 1
    if not cond:
        fails.append(msg)


def local(p):
    return (p[0] - BX, p[1] - BY)


def main(path):
    root = parse(open(path).read())

    # ---------------------------------------------------------- board outline
    edge = [(xy(l, "start"), xy(l, "end")) for l in kids(root, "gr_line")
            if (kid(l, "layer") or [None, None])[1] == "Edge.Cuts"]
    ok(bool(edge), "no Edge.Cuts outline at all")
    if edge:
        pts = [local(p) for seg in edge for p in seg]
        w = max(p[0] for p in pts) - min(p[0] for p in pts)
        h = max(p[1] for p in pts) - min(p[1] for p in pts)
        ok(abs(w - BW) < 0.01, f"board width {w:.3f}, expected {BW} (HAT spec)")
        ok(abs(h - BH) < 0.01,
           f"board height {h:.3f}, expected {BH} — 56.0 is the through-hole "
           f"header figure, 56.5 is only for an SMT header")
        # Radiused corners are mandatory; with them the square corner point
        # itself never appears on the outline.
        for cx, cy in [(0, 0), (BW, 0), (0, BH), (BW, BH)]:
            ok(not any(abs(p[0] - cx) < 0.01 and abs(p[1] - cy) < 0.01
                       for p in pts),
               f"corner ({cx},{cy}) is square; the HAT spec requires R{CORNER_R}")
        # The PoE notch must actually be cut, not merely kept clear of copper.
        ok(sum(1 for a, b in edge
               if all(local(p)[0] > 55 and local(p)[1] < 16 for p in (a, b))
               ) >= 3, "no PoE notch in Edge.Cuts near the top-right corner")

    # ------------------------------------------------------- J1 header pads
    # Pin 1 at (8.37, 4.77); ODD pins on the inner row, EVEN pins on the outer
    # row nearest the board edge — which is where the Pi puts 5V (pins 2/4).
    j1 = [f for f in kids(root, "footprint")
          if "RPi_GPIO40_Horizontal" in f[1]]
    ok(len(j1) == 1, "J1 (40-pin header) footprint not found")
    if j1:
        origin = xy(j1[0], "at")
        pads = {int(p[1]): xy(p, "at") for p in kids(j1[0], "pad")
                if p[1].isdigit()}
        ok(len(pads) == 40, f"J1 has {len(pads)} pads, expected 40 "
                            f"(HAT spec: board must have a full 40W connector)")
        bad = []
        for pin, p in pads.items():
            lx, ly = local((origin[0] + p[0], origin[1] + p[1]))
            wx = 8.37 + ((pin - 1) // 2) * 2.54
            wy = 4.77 if pin % 2 else 2.23
            if abs(lx - wx) > 0.01 or abs(ly - wy) > 0.01:
                bad.append(f"pin {pin} at ({lx:.2f},{ly:.2f}) want "
                           f"({wx:.2f},{wy:.2f})")
        ok(not bad, "J1 pads are not where the Pi's header is, so the board "
                    "will not seat correctly: " + "; ".join(bad[:4]))

    # --------------------------------------------------------- mounting holes
    holes = [xy(f, "at") for f in kids(root, "footprint")
             if f[1].startswith("MountingHole")]
    ok(len(holes) == 4, f"{len(holes)} mounting holes, expected 4")
    for mx, my in MOUNT:
        ok(any(abs(h[0] - (BX + mx)) < 0.01 and abs(h[1] - (BY + my)) < 0.01
               for h in holes), f"no mounting hole at ({mx},{my})")
    drills = [float(d[1]) for f in kids(root, "footprint")
              if f[1].startswith("MountingHole") for d in walk(f, "drill")]
    ok(drills and all(abs(d - 2.75) < 0.01 for d in drills),
       f"mounting hole drills are {sorted(set(drills))}, spec says 2.75 mm")

    # ------------------------------------------------------------ copper map
    segs = []
    for sg in kids(root, "segment"):
        net = kid(sg, "net")
        segs.append((xy(sg, "start"), xy(sg, "end"),
                     float(kid(sg, "width")[1]),
                     int(net[1]) if net else 0))
    ok(bool(segs), "no routed tracks in this file — did the SES import run?")
    vias = [xy(v, "at") for v in kids(root, "via")]

    # Zone copper: the fill is what actually exists on the board, and
    # ZONE.IsFilled() lies, so count real filled_polygon vertices.
    fillpts = [(float(p[1]), float(p[2]))
               for fp in walk(root, "filled_polygon")
               for p in walk(fp, "xy")]
    ok(len(fillpts) > 20,
       f"GND pour has {len(fillpts)} filled vertices — the pour did not fill, "
       f"and an unfilled zone contributes no copper and no connectivity")

    def copper_in(pred):
        """Any track sample, via or pour vertex inside the region?"""
        for a, b, _w, _n in segs:
            n = max(2, int(math.dist(a, b) / 0.2))
            for i in range(n + 1):
                t = i / n
                if pred(local((a[0] + (b[0] - a[0]) * t,
                               a[1] + (b[1] - a[1]) * t))):
                    return True
        return any(pred(local(p)) for p in vias + fillpts)

    # ------------------------------------------- Pi 3B+ PoE header clearance
    x0, y0, x1, y1 = J14
    ok(not copper_in(lambda p: x0 <= p[0] <= x1 and y0 <= p[1] <= y1),
       "copper sits over the Pi 3B+ PoE header J14 — those pins can carry "
       "~48-57 V from a PoE switch, and this is a wired-Ethernet gateway")

    # ------------------------------------------------- mounting-hole lands
    # HAT spec: 6.2 mm land, isolated copper or bare board, never tied to GND.
    # EPS: the pour boundary lands exactly ON the keepout edge, so comparing
    # at exactly MOUNT_LAND/2 is a floating-point coin flip. Copper AT 3.1 mm
    # satisfies "clear to 3.1 mm"; 5 um inside it does not.
    EPS = 0.005
    for i, (mx, my) in enumerate(MOUNT, start=1):
        ok(not copper_in(lambda p, mx=mx, my=my:
                         math.dist(p, (mx, my)) < MOUNT_LAND / 2 - EPS),
           f"copper inside H{i}'s {MOUNT_LAND} mm mounting-hole land — the "
           f"HAT spec requires isolated copper or bare board there")

    # ------------------------------------------------------- +5V trace width
    # KiCad has no current-carrying check of any kind. This is the only gate.
    v5 = [int(n[1]) for n in kids(root, "net") if len(n) > 2 and n[2] == "+5V"]
    ok(bool(v5), "no +5V net in the board")
    if v5:
        widths = [w for _a, _b, w, n in segs if n == v5[0]]
        ok(bool(widths), "found no +5V tracks to width-check")
        if widths:
            ok(min(widths) >= MIN_5V_WIDTH - 1e-6,
               f"narrowest +5V track is {min(widths)} mm, below the "
               f"{MIN_5V_WIDTH} mm sized for the E22's 650 mA TX burst")

    print(f"{checks} mechanical checks run against {path}")
    for f in fails:
        print(f"  FAIL: {f}")
    if fails:
        print(f"{len(fails)} FAILED — this board is not correct")
        return 1
    print("all passed")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1
                  else "meshgw-hat-routed.kicad_pcb"))
