"""Forward test: the GEOMETRY PROTOTYPE against publication 397 Figure 3.

    python3 forward_test_397_mono_geometry.py [PATH_TO_397_fig3.jpeg]

`forward_test_397_mono_bar.py` exercises the production reader,
`MR.read_monochrome_bar_panel`. This exercises `measure_mono_bars.py`, which is
a different implementation of the same measurement and shares none of its code.
Both are needed: the production reader is what ships today and the prototype is
what will replace it, and a change to one says nothing about the other. The
prototype's 397 behaviour was not pinned anywhere until this file, so the
baseline-bound stroke change could have moved every value on the figure that
CI can actually open and nothing would have said so.

The expected means are the SAME independent eye readings the production forward
test uses - read off the plotted bars to the nearest millimetre of mercury. They
are the only independent truth this project has for any real figure.

**Two panels, and they do not agree about the stroke.** MEN measures 1 px and
WOMEN 2 px on one JPEG of one figure, because the printed axis lands on the
pixel grid differently in the two panels: MEN's rule is one row at 118 px,
WOMEN's is two rows at 116 px. The stroke is a property of the panel as
rendered, not of the figure, and an invariant saying otherwise would be false
here and on publication 127 as well.

**The WOMEN panel is closed.** All three of the defects it exposed are fixed and
this section records what they were, because each was a different mistake. The panel
was added to the prototype's spec list while writing this file and immediately
showed them; recording them here is what stops them being rediscovered a third
time, and stops them getting quietly worse.

  PRE/SOLID  RESOLVED, by two separate fixes for two separate defects.

             First, the two bars of this group TOUCH: the solid
             one occupies columns 16-73 of the panel and the hatched one starts
             at 78, and the hatched bar's leading diagonals reach back to column
             74 on some rows. The seed band sees those columns as inked and the
             solid bar's footprint comes out 16-77, four columns into its
             neighbour. Above the solid bar's top at row 233 those four columns
             carry the hatched bar's body, which is a structure inside the
             footprint that is not this bar - correctly unnameable, correctly
             refused, and caused by the footprint rather than by the classifier.

             The footprint IS now trimmed: `trim_to_own_bar` measures each
             column's occupancy in the body band between the provisional top and
             the baseline, compares it with the most inked column just inside
             it, and walks in from each end. That takes this cell's footprint
             from 16-77 back to 16-73 and drops all four of the neighbour's
             columns.

             That was not enough, and the 2 px by 14 row structure left at
             columns 72-73 turned out not to be trimmable at all. Read across a
             wider span it is the HATCHED BAR'S OWN TOP RULE: rows 219-221 are
             one continuous rule from column 72 to 129. The neighbour's outline
             overhangs three columns to the left, above the solid bar's top,
             into columns that below that top are solid bar - no trim can take
             them, they are this bar's columns. So the signal is what happens
             OUTSIDE the footprint: a bar is never wider than its own footprint,
             and ink joined to the component that continues past it belongs to
             something else. NEIGHBOUR_STRUCTURE, which does not invalidate the
             bar.

             An earlier approach was tried and REVERTED, so nobody spends the
             round on it twice. "A bar's top is level": take each column's
             topmost ink, take the median across the footprint, trim inward
             from each end while the columns disagree. It fails because the
             topmost ink in a column is not the bar top - it is the ERROR BAR.
             The synthetic fixture's caps span 70% of the bar, so the median
             column top is the cap row and every column outside the cap gets
             trimmed; the fixture lost three bars per group and 397 MEN
             collapsed. "Topmost ink CONTIGUOUS with the baseline" does not
             rescue it either, because a stipple's columns are dotted and stop
             at the first blank row.

             Whatever the signal is, it has to be measured in a band that
             excludes the error bar above and tolerates dots - which means it
             needs the bar's extent first, so the separation is iterative:
             trace with the provisional footprint, re-measure the columns below
             that extent, trim, re-trace. Note also that below the bar top BOTH
             the bar's columns and the neighbour's overhang are inked, so the
             discriminator there is density and not presence.

             The fix belongs in footprint separation and needs its own round:
             the midpoint-of-the-gap boundary this file's geometry already
             computes does not help, because the bleed is INSIDE the seed run
             rather than beyond it. A bar's own columns are inked over its full
             height and a neighbour's diagonal crossing into the slot is inked
             only on some rows, which is the signal to separate them on - and
             `seed_support` currently thresholds persistence without asking
             which side of the boundary a column's ink belongs to.

             The provisional value is within 0.1 mmHg of the eye reading and is
             still not returned, which is the contract working.
Two of the three are CLOSED. Both hatched cells were missing their cap because
this figure draws its whiskers off the bar's centre line - at 39% of the bar
width against a centre slice covering the middle fifth - and `stem_band` finds
the stem instead of assuming it. That is the defect this panel existed to
expose; it cost three of publication 397's four WOMEN dispersions and would have
cost them silently in production.

Publication 397 now yields 8 means and 8 dispersions from the prototype, with a
worst mean of 0.75 mmHg against the independent eye reading, and this file
asserts exactly that.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import measure_mono_bars as M                                      # noqa: E402

DEFAULT = os.path.join(HERE, "397_fig3.jpeg")
path = sys.argv[1] if len(sys.argv) > 1 else DEFAULT
# The raster ships with the package, so its absence means the package is
# incomplete, not that this run has nothing to do.
# THE RASTER IS A PUBLISHER FIGURE AND THIS REPOSITORY IS PUBLIC, so it is not
# carried here. Absent is a SKIP and not a failure; present-but-different is a
# failure, because coordinates measured on one render return a plausible number
# on another. `raster_root.py` holds the pinned hash.
import raster_root as RR                                          # noqa: E402
# AN EXPLICIT PATH IS AN INSTRUCTION, not a hint: a caller who names a file and
# is handed a different one has been answered about the wrong figure.
_want = sys.argv[1] if len(sys.argv) > 1 else ""
if _want and not os.path.exists(_want):
    print(RR.skip_note('397_fig3.jpeg'))
    raise SystemExit(0)
path, _note = RR.check('397_fig3.jpeg', extra=os.path.dirname(_want) if _want else "")
if not path:
    print(RR.skip_note('397_fig3.jpeg'))
    raise SystemExit(0)
print(_note)

#: The independent eye reading, in mmHg. Slot 0 is the solid bar (FLUID) and
#: slot 1 the hatched one (NON_FLUID).
EYE = {("397_fig3_P3_MEN", "PRE", 0): 97, ("397_fig3_P3_MEN", "PRE", 1): 96,
       ("397_fig3_P3_MEN", "POST", 0): 123, ("397_fig3_P3_MEN", "POST", 1): 113,
       ("397_fig3_P3_WOMEN", "PRE", 0): 88, ("397_fig3_P3_WOMEN", "PRE", 1): 92,
       ("397_fig3_P3_WOMEN", "POST", 0): 110,
       ("397_fig3_P3_WOMEN", "POST", 1): 104}

STROKE = {"397_fig3_P3_MEN": 1, "397_fig3_P3_WOMEN": 2}

#: The cells that do not yet yield a dispersion, and the one that does not yet
#: yield an extent. Pinned so they cannot grow, and so they cannot shrink
#: without somebody noticing.
NO_CAP = set()
NO_EXTENT = set()

FAILURES, PASSED = [], [0]


def check(name, ok, detail=""):
    print(("  ok   " if ok else "  FAIL ") + name + ("" if ok else "  <- " + detail))
    if ok:
        PASSED[0] += 1
    else:
        FAILURES.append(name)


specs = [s for s in M.builtin_specs() if s["tag"].startswith("397")]
records = []
for spec in specs:
    spec = dict(spec, path=path)
    records.extend(M.measure_panel(spec))

print("publication 397 Figure 3, read by the geometry prototype")
for r in records:
    key = (r["figure"], r.get("group"), r.get("slot"))
    value = r.get("value", r.get("provisional_value"))
    print("  %-18s %-5s %-8s stroke %s  mean %6.2f (eye %3d, d %.2f)  SE %-6s %s"
          % (r["figure"].replace("397_fig3_P3_", ""), r.get("group"),
             r.get("spec_fill"), r.get("stroke_px"), value, EYE[key],
             abs(value - EYE[key]),
             "%.2f" % r["dispersion"] if "dispersion" in r else "----",
             r.get("error") or ""))

check("eight cells across two panels", len(records) == 8, "got %d" % len(records))
for spec in specs:
    got = {r.get("stroke_px") for r in records if r["figure"] == spec["tag"]}
    check("%s measures a %d px stroke" % (spec["tag"], STROKE[spec["tag"]]),
          got == {STROKE[spec["tag"]]}, repr(sorted(got)))
check("the two panels of one figure do NOT share a stroke, and are not made to",
      len({r["stroke_px"] for r in records}) == 2)

errors = []
for r in records:
    key = (r["figure"], r.get("group"), r.get("slot"))
    value = r.get("value", r.get("provisional_value"))
    errors.append((key, abs(value - EYE[key])))
worst = max(e for _k, e in errors)
check("every mean is within 1 mmHg of the independent eye reading",
      worst < 1.0, repr(sorted(errors, key=lambda t: -t[1])[:3]))

# The footprints, exactly. The prose said 16-73 and nothing asserted it, so a
# trim that took the wrong columns - or stopped taking them - would have passed.
FOOTPRINT = {("397_fig3_P3_WOMEN", "PRE", 0): ([16, 73], [74, 75, 76, 77]),
             ("397_fig3_P3_WOMEN", "POST", 0): ([16, 74], [75, 76, 77]),
             ("397_fig3_P3_MEN", "PRE", 0): ([10, 68], [69]),
             ("397_fig3_P3_MEN", "POST", 0): ([16, 74], [75])}
for r in records:
    key = (r["figure"], r.get("group"), r.get("slot"))
    want = FOOTPRINT.get(key)
    if want is None:
        check("%s/%s/%s is not trimmed at all"
              % (r["figure"].replace("397_fig3_P3_", ""), r.get("group"),
                 r.get("slot")),
              not r.get("trimmed_columns"), repr(r.get("trimmed_columns")))
        continue
    check("%s/%s/%s keeps its own columns and drops the neighbour's"
          % (r["figure"].replace("397_fig3_P3_", ""), r.get("group"),
             r.get("slot")),
          r.get("footprint") == want[0] and r.get("trimmed_columns") == want[1],
          "%r %r against %r" % (r.get("footprint"), r.get("trimmed_columns"), want))

refused = {(r["figure"], r.get("group"), r.get("slot")) for r in records
           if "value" not in r}
check("the extents that do not resolve are the ones on record",
      refused == NO_EXTENT, "%r against %r" % (sorted(refused), sorted(NO_EXTENT)))
capless = {(r["figure"], r.get("group"), r.get("slot")) for r in records
           if "dispersion" not in r}
check("the cells without a cap are the ones on record",
      capless == NO_CAP, "%r against %r" % (sorted(capless), sorted(NO_CAP)))
check("all eight cells carry a dispersion",
      sum("dispersion" in r for r in records) == 8,
      repr(sum("dispersion" in r for r in records)))
check("no cell is contradicted by a body continuation",
      not [r for r in records if r.get("error") == "BAR_EXTENT_UNRESOLVED"],
      repr([r.get("error") for r in records]))
verdicts = M.fill_identities_by_figure(records)
verdict = verdicts.get("397_fig3", {})
check("the figure establishes a reusable fill vocabulary",
      verdict.get("status") == "ESTABLISHED" and verdict.get("prototype_ready"),
      repr(verdict.get("status")))
resolved = [r for r in records if r.get("identity_status") == "RESOLVED"]
check("all eight bars are named",
      len(resolved) == 8, "%d resolved" % len(resolved))
check("both hatched cells now carry the dispersion their off-centre stem hangs",
      all("dispersion" in r for r in records
          if r.get("spec_fill") == "HATCHED"),
      repr([(r["figure"], r.get("group"), r.get("dispersion")) for r in records
            if r.get("spec_fill") == "HATCHED"]))
check("and every name is the fill the spec declares",
      all(r["resolved_fill_pattern"] == r["spec_fill"] for r in resolved),
      repr([(r["figure"], r.get("slot"), r.get("resolved_fill_pattern"),
             r["spec_fill"]) for r in resolved
            if r["resolved_fill_pattern"] != r["spec_fill"]]))
check("the bar with no measurable fill is not named by its slot",
      all(r.get("identity_status") == "UNRESOLVED_NO_FILL"
          for r in records if r.get("fill_sample_status") != "MEASURED"),
      repr([(r["figure"], r.get("slot"), r.get("identity_status"))
            for r in records if r.get("fill_sample_status") != "MEASURED"]))

print("\n%d checks passed, %d failed" % (PASSED[0], len(FAILURES)))
if FAILURES:
    for f in FAILURES:
        print("  FAILED: " + f)
    raise SystemExit(1)
