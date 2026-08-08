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

**Three open defects on the WOMEN panel, pinned rather than fixed.** The panel
was added to the prototype's spec list while writing this file and immediately
showed them; recording them here is what stops them being rediscovered a third
time, and stops them getting quietly worse.

  PRE/SOLID  the walk stops about seven rows below the bar top, where the ink
             narrows from 62 px to 34, and the bar refuses itself. The refusal
             is correct - the ink above it really is bar - but the extent is
             not yet resolvable. Its provisional value is nonetheless within
             0.1 mmHg of the eye reading.
  PRE/HATCHED and POST/HATCHED
             no cap is found. The stem on this panel is one to two pixels and
             runs off the bar's centre line, so the centre-column trace loses
             it, and the cap search only looks near the stem's tip.
  POST/HATCHED
             a structure exactly as wide as the bar sits above it. A cap may
             not touch both side tracks - that is what keeps a bar's own top
             rule from being read as a cap - so this one is rejected, whatever
             it is.

Until those are closed, publication 397 yields 8 means from the prototype and 5
dispersions, and this file asserts exactly that. A run that suddenly produces 8
dispersions is not allowed to pass silently either: it means somebody changed
the cap rule and owes this file an update.
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
if not os.path.exists(path):
    print("BLOCKED: publisher raster not found: %s" % path, file=sys.stderr)
    raise SystemExit(2)

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
NO_CAP = {("397_fig3_P3_WOMEN", "PRE", 1), ("397_fig3_P3_WOMEN", "POST", 1),
          ("397_fig3_P3_WOMEN", "PRE", 0)}
NO_EXTENT = {("397_fig3_P3_WOMEN", "PRE", 0)}

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
             r.get("declared"), r.get("stroke_px"), value, EYE[key],
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

refused = {(r["figure"], r.get("group"), r.get("slot")) for r in records
           if "value" not in r}
check("the extents that do not resolve are the ones on record",
      refused == NO_EXTENT, "%r against %r" % (sorted(refused), sorted(NO_EXTENT)))
capless = {(r["figure"], r.get("group"), r.get("slot")) for r in records
           if "dispersion" not in r}
check("the cells without a cap are the ones on record",
      capless == NO_CAP, "%r against %r" % (sorted(capless), sorted(NO_CAP)))
check("so five of eight cells carry a dispersion",
      sum("dispersion" in r for r in records) == 5,
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
check("seven of the eight bars are named, the eighth having no fill to sample",
      len(resolved) == 7, "%d resolved" % len(resolved))
check("and every name is the fill the spec declares",
      all(r["resolved_fill_pattern"] == r["declared"] for r in resolved),
      repr([(r["figure"], r.get("slot"), r.get("resolved_fill_pattern"),
             r["declared"]) for r in resolved
            if r["resolved_fill_pattern"] != r["declared"]]))
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
