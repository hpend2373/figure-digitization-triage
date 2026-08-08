"""Forward test: the monochrome geometry against publication 127 Figure 4.

    python3 forward_test_127_mono_bar.py [--raster-root DIR]
    FDT_RASTER_ROOT=DIR python3 forward_test_127_mono_bar.py

The raster is a 600 DPI render of a page of a publisher PDF and is NOT
redistributable, so unlike `forward_test_397_mono_bar.py` this cannot ship its
input. It therefore SKIPS - exit 0, loudly - when the raster is absent, and
FAILS when a raster is present that is not the one the geometry was measured on.
Those two have to be different outcomes: a hash mismatch means someone is
measuring a different figure with these coordinates, which is worse than not
measuring at all.

Publication 127 is the figure that found nine defects in the geometry
prototype, six of them coordinate or scale errors that returned a plausible
number rather than a refusal. None of those nine is reachable from anything CI
can see: it is the only figure in the corpus with a 3 px stroke, the only one
with a STIPPLED fill, the only one whose panels start hundreds of rows down the
page, and the only one whose three sub-panels must agree with each other. So
what is checked here is mostly STRUCTURE, which does not depend on trusting the
numbers:

  eighteen cells, sixteen with a fill and two refused for being 15 px tall
  no cell whose extent is contradicted or unresolved
  no group refused for geometry - clipped window, no seed, unclear direction
  eighteen error-bar caps, each hanging off a stem, and the SE each implies
  the stroke each panel measures, pinned per panel - NOT one shared value: the
    three sub-panels read 3, 3 and 4 because the rule lands on the pixel grid
    differently in each, exactly as 397's two panels read 1 and 2
  three printed fills that do not overlap in ink mass
  sixteen series identities, because two bars are too short to sample a fill
    and a BAR_MONO series is identified by its fill and never by its slot

**The per-cell values below are a self-measured baseline, not an independent
reading.** They detect drift - an anchor moved, a bar tracing its neighbour
again, a mean shifting by a few pixels - and they cannot detect a systematic
error that was already there when they were recorded. 397 has an independent
eye reading and this does not; getting one is still owed, and until it exists
this file must not be described as validating publication 127.
"""
import argparse
import hashlib
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import measure_mono_bars as M                                      # noqa: E402

GEOMETRY = os.path.join(HERE, "geometry", "pub127_fig4.geometry.json")

#: figure, group, slot, declared fill, mean, SE, ink mass (None = no interior),
#: identity status. Self-measured; see the module docstring.
BASELINE = [
    ("pub127_fig4_slow", "SUPINE", 0, "OPEN", 2.113, 0.258, 0.000, "FILL_MEASURED"),
    ("pub127_fig4_slow", "SUPINE", 1, "STIPPLED", 2.938, 0.567, 0.148, "FILL_MEASURED"),
    ("pub127_fig4_slow", "SUPINE", 2, "SOLID", 1.959, 0.618, 0.754, "FILL_MEASURED"),
    ("pub127_fig4_slow", "STANDING", 0, "OPEN", 14.897, 6.340, 0.000, "FILL_MEASURED"),
    ("pub127_fig4_slow", "STANDING", 1, "STIPPLED", 13.247, 6.031, 0.153, "FILL_MEASURED"),
    ("pub127_fig4_slow", "STANDING", 2, "SOLID", 15.567, 4.845, 0.734, "FILL_MEASURED"),
    ("pub127_fig4_normal", "SUPINE", 0, "OPEN", 0.225, 0.093, None, "UNRESOLVED_NO_FILL"),
    ("pub127_fig4_normal", "SUPINE", 1, "STIPPLED", 0.426, 0.077, 0.144, "FILL_MEASURED"),
    ("pub127_fig4_normal", "SUPINE", 2, "SOLID", 0.240, 0.078, None, "UNRESOLVED_NO_FILL"),
    ("pub127_fig4_normal", "STANDING", 0, "OPEN", 2.858, 1.255, 0.000, "FILL_MEASURED"),
    ("pub127_fig4_normal", "STANDING", 1, "STIPPLED", 3.555, 1.704, 0.157, "FILL_MEASURED"),
    ("pub127_fig4_normal", "STANDING", 2, "SOLID", 2.471, 0.867, 0.742, "FILL_MEASURED"),
    ("pub127_fig4_lowfreq", "SUPINE", 0, "OPEN", 1.037, 0.287, 0.000, "FILL_MEASURED"),
    ("pub127_fig4_lowfreq", "SUPINE", 1, "STIPPLED", 1.961, 1.663, 0.153, "FILL_MEASURED"),
    ("pub127_fig4_lowfreq", "SUPINE", 2, "SOLID", 0.975, 0.226, 0.734, "FILL_MEASURED"),
    ("pub127_fig4_lowfreq", "STANDING", 0, "OPEN", 5.820, 1.294, 0.000, "FILL_MEASURED"),
    ("pub127_fig4_lowfreq", "STANDING", 1, "STIPPLED", 5.307, 2.854, 0.148, "FILL_MEASURED"),
    ("pub127_fig4_lowfreq", "STANDING", 2, "SOLID", 6.621, 1.868, 0.745, "FILL_MEASURED"),
]

#: A pixel on the widest of the three axes is 0.05 units, so a tolerance of
#: 0.15 is three pixels: enough for a different OpenCV build, not enough for a
#: moved anchor.
MEAN_TOLERANCE = 0.15
SE_TOLERANCE = 0.15
INK_TOLERANCE = 0.03

GEOMETRY_REFUSALS = ("GROUP_WINDOW_CLIPPED", "NO_SEED_SUPPORT",
                     "BAR_DIRECTION_UNRESOLVED", "STROKE_SCALE_UNRESOLVED")
EXTENT_REFUSALS = ("BAR_EXTENT_UNRESOLVED", "REMOTE_SUPPORT_UNRESOLVED")

FAILURES, PASSED = [], [0]


def check(name, ok, detail=""):
    print(("  ok   " if ok else "  FAIL ") + name + ("" if ok else "  <- " + detail))
    if ok:
        PASSED[0] += 1
    else:
        FAILURES.append(name)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--raster-root", default=os.environ.get("FDT_RASTER_ROOT", ""))
    args = ap.parse_args(argv)

    with open(GEOMETRY, encoding="utf-8") as fh:
        declared = json.load(fh)
    raster = declared[0]["path"]
    found = ""
    for root in [r for r in (args.raster_root, os.path.dirname(GEOMETRY), HERE) if r]:
        if os.path.exists(os.path.join(root, raster)):
            found = os.path.join(root, raster)
            break
    if not found:
        print("SKIP forward_test_127_mono_bar: %s is not on this machine.\n"
              "     It is a 600 DPI render of a publisher page and is not\n"
              "     redistributable. Re-run with --raster-root or FDT_RASTER_ROOT\n"
              "     pointing at the directory holding it; the geometry pins the\n"
              "     SHA-256 so the wrong render cannot be substituted." % raster)
        return 0
    with open(found, "rb") as fh:
        got = hashlib.sha256(fh.read()).hexdigest()
    want = str(declared[0].get("raster_sha256", "")).strip().lower()
    if got != want:
        print("FAIL: %s hashes %s..., the geometry was measured on %s..."
              % (found, got[:16], want[:16]), file=sys.stderr)
        return 2
    print("publication 127 Figure 4, raster %s... verified" % got[:16])
    for spec in declared:
        if not str(spec.get("source_pdf_sha256", "")).strip():
            print("  note  provenance is incomplete: the raster hash pins the "
                  "render, not which publisher PDF bytes produced it")
            break

    specs = M.load_specs([GEOMETRY], raster_root=args.raster_root)
    records = []
    for spec in specs:
        records.extend(M.measure_panel(spec))

    check("eighteen cells", len(records) == 18, "got %d" % len(records))
    check("no group refused for geometry",
          not [r for r in records if r.get("error") in GEOMETRY_REFUSALS],
          repr([(r["figure"], r.get("group"), r.get("error")) for r in records
                if r.get("error") in GEOMETRY_REFUSALS]))
    check("no cell whose extent is contradicted or unresolved",
          not [r for r in records if r.get("error") in EXTENT_REFUSALS],
          repr([(r["figure"], r.get("group"), r.get("slot"))
                for r in records if r.get("error") in EXTENT_REFUSALS]))
    check("every cell has a mean", all("value" in r for r in records),
          repr([r.get("error") for r in records if "value" not in r]))
    with_fill = [r for r in records if "ink_mass" in r]
    check("sixteen cells carry a fill and two are too short to sample",
          len(with_fill) == 16 and
          [r.get("error") for r in records if "ink_mass" not in r]
          == ["BAR_TOO_SMALL_TO_SAMPLE"] * 2,
          "%d with fill" % len(with_fill))

    missing = [r for r in records if "dispersion" not in r]
    check("every cell has an error-bar cap and the SE it implies", not missing,
          repr([(r["figure"], r.get("group"), r.get("slot")) for r in missing]))
    check("every cap hangs off a stem several times narrower than itself",
          all(c["cap_width_px"] >= 3 * c["stem_width_px"]
              for r in records for c in r.get("remote", [])
              if c["kind"] == "ERRORBAR_CAP"),
          repr([(r["figure"], c["stem_width_px"], c["cap_width_px"])
                for r in records for c in r.get("remote", [])
                if c["kind"] == "ERRORBAR_CAP"
                and c["cap_width_px"] < 3 * c["stem_width_px"]]))
    identified = [r for r in records if r.get("identity_status") == "FILL_MEASURED"]
    check("sixteen series identities, and two bars with a geometry and no identity",
          len(identified) == 16 and
          all(r.get("identity_status") == "UNRESOLVED_NO_FILL"
              for r in records if r not in identified),
          "%d identified" % len(identified))
    # Pinned PER PANEL. Asserting that the three agree passes when all three are
    # wrong together, and is false anyway - see expected_stroke_note.
    by_panel = {}
    for r in records:
        by_panel.setdefault(r["figure"], set()).add(r.get("stroke_px"))
    for spec in specs:
        want = spec.get("expected_stroke_px")
        got = by_panel.get(spec["tag"], set())
        check("%s measures its declared %s px stroke" % (spec["tag"], want),
              got == {want}, repr(sorted(got)))

    bands = {}
    for r in with_fill:
        bands.setdefault(r["declared"], []).append(r["ink_mass"])
    ordered = ["OPEN", "STIPPLED", "SOLID"]
    check("the three printed fills are all present",
          sorted(bands) == sorted(ordered), repr(sorted(bands)))
    if sorted(bands) == sorted(ordered):
        check("and they do not overlap in ink mass",
              all(max(bands[a]) < min(bands[b])
                  for a, b in zip(ordered, ordered[1:])),
              repr({k: (min(v), max(v)) for k, v in bands.items()}))
    declared_bands = next((s.get("expected") for s in specs if s.get("expected")), None)
    check("the geometry declares fill bands to be held to",
          bool(declared_bands), "no spec carries an `expected` block")
    for fill, want_band in sorted((declared_bands or {}).items()):
        seen = bands.get(fill, [])
        check("%s stays inside the band the geometry declares" % fill,
              bool(seen) and min(seen) >= want_band["ink_mass"][0]
              and max(seen) <= want_band["ink_mass"][1],
              "%r against %r" % ((min(seen), max(seen)) if seen else None,
                                 want_band["ink_mass"]))

    index = {(r["figure"], r.get("group"), r.get("slot")): r for r in records}
    drift = []
    for figure, group, slot, fill, mean, se, ink, identity in BASELINE:
        r = index.get((figure, group, slot))
        if r is None:
            drift.append("%s/%s/%d missing" % (figure, group, slot))
            continue
        if r.get("declared") != fill:
            drift.append("%s/%s/%d declared %s" % (figure, group, slot,
                                                   r.get("declared")))
        if abs(r.get("value", -999) - mean) > MEAN_TOLERANCE:
            drift.append("%s/%s/%d mean %s against %s"
                         % (figure, group, slot, r.get("value"), mean))
        if abs(r.get("dispersion", -999) - se) > SE_TOLERANCE:
            drift.append("%s/%s/%d SE %s against %s"
                         % (figure, group, slot, r.get("dispersion"), se))
        if r.get("identity_status") != identity:
            drift.append("%s/%s/%d identity %s against %s"
                         % (figure, group, slot, r.get("identity_status"), identity))
        if (ink is None) != ("ink_mass" not in r):
            drift.append("%s/%s/%d fill presence changed" % (figure, group, slot))
        elif ink is not None and abs(r["ink_mass"] - ink) > INK_TOLERANCE:
            drift.append("%s/%s/%d ink %s against %s"
                         % (figure, group, slot, r["ink_mass"], ink))
    check("no cell has drifted from the recorded baseline", not drift,
          "; ".join(drift[:4]))

    print("\n%d checks passed, %d failed" % (PASSED[0], len(FAILURES)))
    if FAILURES:
        for f in FAILURES:
            print("  FAILED: " + f)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
