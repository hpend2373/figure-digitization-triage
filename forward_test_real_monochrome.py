"""Forward test on the real four-series monochrome plot from publication 386.

Four black series told apart by marker shape and open/filled state, which is
what the released LINE_MONO reader is for. Overlapping marks are expected to
stay missing rather than be assigned to a series - that is the property under
test, not an accuracy figure.

    python3 forward_test_real_monochrome.py [PATH]

The raster ships with the package, so it looks beside this file first. A
forward test that SKIPs because it was pointed at somebody else's Downloads
folder is a forward test nobody runs.
"""
import os
import sys

from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mark_readers import (AxisCalibration, SeriesSpec,             # noqa: E402
                          read_monochrome_marker_panel)

HERE = os.path.dirname(os.path.abspath(__file__))
CANDIDATES = (os.path.join(HERE, "ID386_Fig2_publisher_898x1662.png"),
              "/Users/minyeop/Downloads/ID386_Fig2_publisher_898x1662.png")
path = sys.argv[1] if len(sys.argv) > 1 else next(
    (p for p in CANDIDATES if os.path.exists(p)), CANDIDATES[0])
# A PUBLISHER FIGURE, AND THIS REPOSITORY IS PUBLIC.
import raster_root as RR                                          # noqa: E402
# AN EXPLICIT PATH IS AN INSTRUCTION, not a hint: a caller who names a file and
# is handed a different one has been answered about the wrong figure.
_want = sys.argv[1] if len(sys.argv) > 1 else ""
if _want and not os.path.exists(_want):
    print(RR.skip_note('ID386_Fig2_publisher_898x1662.png'))
    raise SystemExit(0)
path, _note = RR.check('ID386_Fig2_publisher_898x1662.png', extra=os.path.dirname(_want) if _want else "")
if not path:
    print(RR.skip_note("ID386_Fig2_publisher_898x1662.png"))
    raise SystemExit(0)
print(_note)

image = Image.open(path).convert("RGB")
x_positions = dict(zip(
    ("BL", "25", "50", "75", "100", "C1", "C2", "R"),
    (221, 306, 390, 474, 558, 642, 725, 808),
))
ycal = AxisCalibration.from_points([(90, 161), (50, 421)])
series = [
    SeriesSpec("HA", marker="CIRCLE", fill="OPEN"),
    SeriesSpec("HB", marker="CIRCLE", fill="FILLED"),
    SeriesSpec("NA", marker="TRIANGLE", fill="OPEN"),
    SeriesSpec("NB", marker="TRIANGLE", fill="FILLED"),
]
rows = read_monochrome_marker_panel(
    image, panel_box=(180, 840, 150, 385), x_positions=x_positions,
    y_calibration=ycal, series=series, threshold=170,
)

# Approximate centres independently read from the plotted marks.  Only cells
# emitted by the automatic reader are compared: missing cells must stay missing
# and are the desired fail-closed behaviour for overlapping marks.
expected = {
    ("HA", "BL"): 58, ("HA", "25"): 61, ("HA", "50"): 63,
    ("HA", "75"): 64, ("HA", "100"): 65, ("HA", "C1"): 57,
    ("HA", "C2"): 56, ("HA", "R"): 61,
    ("HB", "BL"): 61, ("HB", "25"): 66, ("HB", "50"): 68,
    ("HB", "75"): 71, ("HB", "100"): 73, ("HB", "C1"): 60,
    ("HB", "C2"): 61, ("HB", "R"): 62,
    ("NA", "BL"): 63, ("NA", "25"): 67, ("NA", "50"): 71,
    ("NA", "75"): 74, ("NA", "100"): 76, ("NA", "C1"): 59,
    ("NA", "C2"): 58, ("NA", "R"): 63,
    ("NB", "BL"): 67, ("NB", "25"): 72, ("NB", "50"): 75,
    ("NB", "75"): 79, ("NB", "100"): 83, ("NB", "C1"): 62,
    ("NB", "C2"): 62, ("NB", "R"): 67,
}
keys = [(r["series"], r["x_label"]) for r in rows]
assert len(keys) == len(set(keys)), "reader emitted duplicate series/x cells"
assert len(rows) < len(expected), "this low-resolution overlap fixture should fail closed"
errors = [abs(r["mean"] - expected[(r["series"], r["x_label"])]) for r in rows]
nearest = []
for row in rows:
    own_key = (row["series"], row["x_label"])
    own_distance = abs(row["mean"] - expected[own_key])
    other_distance = min(
        abs(row["mean"] - value)
        for (series_name, x_label), value in expected.items()
        if x_label == row["x_label"] and series_name != row["series"]
    )
    nearest.append((own_key, own_distance, other_distance))
assert rows and all(own < other for _, own, other in nearest), (
    "at least one emitted marker is closer to another series at the same x: %r"
    % [item for item in nearest if item[1] >= item[2]])

print("real ID386 HR panel")
print("  declared cells : %d" % len(expected))
print("  auto-emitted   : %d" % len(rows))
print("  manual fallback: %d" % (len(expected) - len(rows)))
print("  max difference from an independent approximate reading: %.2f bpm" % max(errors))
print("  nearest-series identity check: %d/%d" %
      (sum(own < other for _, own, other in nearest), len(nearest)))
print("  verdict: PASS — unresolved overlap remains missing, never shifted")
