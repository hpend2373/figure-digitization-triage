"""The same page at five renderings has to give the same ten numbers.

    python3 forward_test_beckers_dpi.py [PUBLISHER_PDF]

The marker reader used to accept a blob by absolute pixel area and side length
- 12 to 300 px of area, no side over 24 - which is a marker at 300 DPI and half
of one at 600. Measured on publication BF02919461 before the fix:

    300 DPI   10 of 10 cells
    450 DPI    2 of 10
    500 DPI    0 of 10

Nothing about that figure changed between those runs. The panel has ONE marker
size by construction, so `measure_marker_scale` reads it off the panel and the
limits become ratios, the way BAR_MONO has measured its stroke scale since it
shipped.

The ground truth is Table 1 of the same paper: ApEn as mean and SEM for supine
and standing at five sessions. This asserts that every rendering finds all ten
cells AND lands them on the printed values - a reader that agreed with itself
at five DPIs while being wrong at all of them would pass a self-consistency
test and fail this one.

The publisher PDF is not redistributable, so this SKIPs when it is not on disk.
"""
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

CANDIDATES = (
    os.path.join(HERE, "BF02919461.pdf"),
    "/mnt/user-data/uploads/Downloads/spacecv_fulltext_pdfs/BF02919461.pdf",
    "/Users/minyeop/Downloads/spacecv_fulltext_pdfs/BF02919461.pdf",
)
pdf = sys.argv[1] if len(sys.argv) > 1 else next(
    (p for p in CANDIDATES if os.path.exists(p)), CANDIDATES[0])
if not os.path.exists(pdf):
    print("SKIP: the publisher PDF is not on disk (%s)" % pdf, file=sys.stderr)
    raise SystemExit(0)
from shutil import which                                          # noqa: E402
if not which("pdftoppm"):
    print("SKIP: pdftoppm is not installed", file=sys.stderr)
    raise SystemExit(0)

from PIL import Image                                             # noqa: E402
import mark_readers as MR                                         # noqa: E402

#: Table 1, page 2. Mean ApEn; the SEM column is checked by the pilot report.
TRUTH = {
    "SUPINE": {"L-30": 0.98, "R+1": 0.90, "R+4": 0.97, "R+9": 0.99,
               "R+25": 0.96},
    "STANDING": {"L-30": 0.78, "R+1": 0.76, "R+4": 0.79, "R+9": 0.75,
                 "R+25": 0.72},
}
LABELS = ("L-30", "R+1", "R+4", "R+9", "R+25")

#: Measured by hand on the 300 DPI render, and scaled to whatever is asked for.
#: Geometry is not what is under test here - the same geometry is used at every
#: rendering, which is the point.
PANELS = {
    "SUPINE": dict(top=2019.5, bottom=2746.0, left=302, right=1179,
                   x=(459.5, 601.0, 741.5, 881.5, 1024.0)),
    "STANDING": dict(top=2049.5, bottom=2720.0, left=1446, right=2257,
                     x=(1591.0, 1721.5, 1851.5, 1981.5, 2113.0)),
}

DPIS = (200, 300, 450, 600, 720)
TOLERANCE = 0.01

work = tempfile.mkdtemp(prefix="fdt_dpi_")
failures = []
print("publication BF02919461, page 3, read at five renderings")
for dpi in DPIS:
    stem = os.path.join(work, "p%d" % dpi)
    subprocess.run(["pdftoppm", "-r", str(dpi), "-f", "3", "-l", "3", "-png",
                    pdf, stem], check=True, capture_output=True)
    png = next((os.path.join(work, n) for n in sorted(os.listdir(work))
                if n.startswith("p%d-" % dpi) and n.endswith(".png")), "")
    if not png:
        failures.append("%d DPI: pdftoppm produced nothing" % dpi)
        continue
    image = Image.open(png)
    k = dpi / 300.0
    read, worst = 0, 0.0
    for name, panel in PANELS.items():
        cal = MR.AxisCalibration.from_points(
            [(1.3, panel["top"] * k), (0.2, panel["bottom"] * k)])
        rows = MR.read_monochrome_marker_panel(
            image,
            [panel["left"] * k + 3, panel["right"] * k - 3,
             int(panel["top"] * k) + 2, int(panel["bottom"] * k) - 2],
            dict(zip(LABELS, [x * k for x in panel["x"]])), cal,
            [MR.SeriesSpec(name="S_APEN", marker="ANY", fill="OPEN")],
            threshold=170, x_window=max(6, int(18 * k)),
            stem_px=max(2, int(4 * k)),
            whisker_search_px=int((panel["bottom"] - panel["top"]) * k * 0.40))
        read += len(rows)
        for row in rows:
            worst = max(worst, abs(row["mean"] - TRUTH[name][row["x_label"]]))
    print("  %3d DPI  %2d of 10 cells  worst error against the table %s"
          % (dpi, read, ("%.4f" % worst) if read else "-"))
    if read != 10:
        failures.append("%d DPI: %d of 10 cells" % (dpi, read))
    elif worst > TOLERANCE:
        failures.append("%d DPI: worst error %.4f, over %.2f"
                        % (dpi, worst, TOLERANCE))

print()
if failures:
    for line in failures:
        print("FAIL %s" % line)
    raise SystemExit(1)
print("verdict: PASS - five renderings, ten cells each, every one within %.2f "
      "of the printed table. The reader's limits are the panel's own." % TOLERANCE)
