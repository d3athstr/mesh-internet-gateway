"""Deterministic pre-fab gates for the MeshGW Pi HAT.

House pattern (learned on the Power Warden, whose MP1584EN pad pitch was an
estimate): when a board carries an unknown that NO automated check can catch,
the unknown lives in ONE file behind a flag and the fab script reads that flag
and refuses. A comment in a docstring is something a hurried session skims
past; a hard exit is not.

GEOMETRY  — "will the parts physically fit the copper?" The only question a fab
            run can get wrong in a way that wastes the board.

              * J1     40-pin Pi header — VERIFIED 2026-08-12 against the
                       official HAT mechanical spec, the Pi 3B+ drawing, and
                       KiCad's own HAT template. 27 assertions in
                       check_geometry.py run on every route.
              * H1-H4  2.75 mm NPTH at the spec positions, 6.2 mm isolated
                       lands. Same verification.
              * C1     CP_Radial_D8.0mm_P3.50mm, stock KiCad.
              * C2/C3  C_Disc_D5.0mm_W2.5mm_P5.00mm, stock KiCad.
              * U1     E22-900M30S — **NOT VERIFIED**. Derived from the User
                       Manual v1.20 section 3 and internally self-consistent
                       (pad count, first-pad offset, pitch, both irregular
                       gaps, ring direction all re-checked 2026-08-12), but it
                       has never been offered up to a physical module. The
                       module was ordered 2026-08-12 and has not arrived.

FUNCTION  — "once populated, does it actually work?" Unproven: nothing has been
            built. Does not block a BARE board order.

The E22 is SOLDERED to castellated pads, not socketed on a header. So unlike
Sentinel — where the open items were modules on headers and a wrong guess costs
a module, not a re-spin — a wrong land pattern here makes these boards scrap.
That is why GEOMETRY_VERIFIED below is False and stays False until someone
holds the module against the footprint.
"""

# U1's land pattern has never met a physical part. This is the honest state and
# it must NOT be flipped to True to make the export run — flip it only when
# someone has actually checked the module against the footprint.
GEOMETRY_VERIFIED = False

# Nothing has been built or bench-tested. Does not block a bare board order.
FUNCTION_VERIFIED = False

# EXPLICIT, INFORMED OVERRIDE of the GEOMETRY gate.
#
# Set to a "who, when, why" string to permit the export with GEOMETRY_VERIFIED
# still False; None re-arms the refusal. It exists so that a decision to fab on
# a known unknown is RECORDED rather than laundered into a flag that claims the
# unknown was resolved. The distinction matters: six weeks from now, "verified"
# and "we decided to risk it" are very different things to read.
#
# Don's call, 2026-08-12, with the state above in front of him: batch the bare
# board into the shared JLCPCB checkout alongside OSL, FD2, pool and Sentinel.
# Marginal cost ~$2 against $6-25 shipping that dominates any order; holding it
# back would pay that shipping charge again later with certainty, so batching is
# cheaper in expectation unless no further order is ever placed. If the land
# pattern is wrong the loss is ~$2 of board plus one re-spin's shipping.
GEOMETRY_OVERRIDE = (
    "Don, 2026-08-12 — batch bare board into the shared JLCPCB checkout at "
    "~$2 marginal; E22 land pattern still unverified, module in transit"
)

# Bumped when the copper changes.
REV = "A"


def blocked():
    """Reason the fab export must refuse, or None if it may proceed."""
    if GEOMETRY_VERIFIED or GEOMETRY_OVERRIDE:
        return None
    return ("U1 (E22-900M30S) land pattern has never been checked against a "
            "physical module, and the part is soldered to castellated pads — "
            "a wrong land pattern makes these boards scrap.")
