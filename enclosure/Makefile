# Render the enclosure. OpenSCAD 2021.01 on ops (apt), headless via xvfb-run.
#
#   make            # all three parts
#   make coupon     # print THIS first — see the note in meshgw-case.scad
#
# STLs are deliberately not committed; they are a pure function of the .scad.

SCAD    := meshgw-case.scad
OPENSCAD := xvfb-run -a openscad

PARTS := base lid coupon
STLS  := $(addprefix meshgw-,$(addsuffix .stl,$(PARTS)))

all: $(STLS)

meshgw-%.stl: $(SCAD)
	$(OPENSCAD) -D 'part="$*"' -o $@ $<

# Each part must report "Volumes: 2" — that is one solid plus the outer space.
# More than 2 means the geometry fell into disconnected pieces, which slices
# into loose fragments rather than a printable part.
check: $(SCAD)
	@for p in $(PARTS); do \
	    printf '%-8s ' $$p; \
	    $(OPENSCAD) -D "part=\"$$p\"" -o /dev/null $(SCAD) 2>&1 \
	        | grep -E 'Volumes' || echo "NO GEOMETRY"; \
	done

clean:
	rm -f $(STLS)

.PHONY: all check clean
