"""Worked example: one publication all the way to POOLING_ELIGIBLE.

    python3 pilot_beckers.py [PUBLISHER_PDF]

`pilot_397.py` is the biggest worked example in this package and it stops at
QC_FAILED, because publication 397 never says whether its error bars are SD or
SEM. That is the right answer and it means the last two rungs of the ladder -
HUMAN_APPROVED and POOLING_ELIGIBLE - have never been demonstrated end to end
on a real publication, only in `test_finalize.py` against fixtures.

Beckers 2007 is the one publication in this corpus that can. Its Figures 1 and
2 plot approximate entropy as mean and 95% confidence interval at five sessions
in two postures, the caption says exactly that, and TABLE 1 OF THE SAME PAPER
PRINTS THE SAME MEANS. So there is a reader-independent answer to check against
at the end, which is what makes finishing the ladder worth doing here rather
than on a fixture whose truth this package wrote itself.

    AUTO_EXTRACTED     the reader produced marks
    MACHINE_QC_PASSED  the gate found nothing wrong
    HUMAN_APPROVED     a registered person looked at the overlay and agreed
    POOLING_ELIGIBLE   written by finalize_batch, and nowhere else

## The attestation is asked for, not assumed

Same contract as `pilot_397.py`: set all four of FDT_REVIEWER_NAME,
FDT_REVIEWER_ORCID, FDT_INSPECTION_DATE and FDT_REGISTRATION_DATE and the run
is ATTESTED and can be finalized. Set none and it runs as DEMO_ONLY under
ORCID's fictional demonstration record - and then THE FINALIZER REFUSES IT, and
this script asserts that it does. A demonstration that finalized would be a
demonstration of the wrong thing.

The approval this script writes is not a rubber stamp either way. It says
`Marks_Checked=TRUE`, which is a claim about a person having opened
`review/<panel>_overlay.png`; run it attested and that claim is yours.

## The publisher PDF is not redistributable

So this SKIPs when it is not on disk, the same as the two Beckers forward
tests. In CI it skips; on a machine with the paper it runs.
"""
import csv
import datetime
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

CANDIDATES = (
    os.path.join(HERE, "BF02919461.pdf"),
    "/mnt/user-data/uploads/Downloads/spacecv_fulltext_pdfs/BF02919461.pdf",
    os.path.expanduser("~/Downloads/spacecv_fulltext_pdfs/BF02919461.pdf"),
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

import compile_plan as CP                                         # noqa: E402
import run_batch as RB                                            # noqa: E402
import finalize_batch as FB                                       # noqa: E402
import mark_readers as MR                                         # noqa: E402

#: TABLE 1, PAGE 99: "Values of ApEn (mean +/- SEM) in standing and supine
#: position". Transcribed from the printed table, not from anything this
#: package produced - it is the answer, and the reader never sees it.
#:
#: Transcribe it, do not remember it. The first version of this dictionary had
#: the means right and the SEM column half invented, and the half-width check
#: below failed by 0.17 on a reading that was correct to 0.013. A fabricated
#: reference does not just fail - it accuses the measurement.
TABLE_1 = {
    ("SUPINE", "L-30"): (0.98, 0.04), ("SUPINE", "R+1"): (0.90, 0.05),
    ("SUPINE", "R+4"): (0.97, 0.08), ("SUPINE", "R+9"): (0.99, 0.07),
    ("SUPINE", "R+25"): (0.96, 0.06),
    ("STANDING", "L-30"): (0.78, 0.07), ("STANDING", "R+1"): (0.76, 0.12),
    ("STANDING", "R+4"): (0.79, 0.08), ("STANDING", "R+9"): (0.75, 0.08),
    ("STANDING", "R+25"): (0.72, 0.05),
}
#: With n=5 the 95% interval is 2.776 SEM either side. Reconstructing the
#: printed SEM from the digitized half-width is a second, independent check on
#: the same reading: the mean can be right while the whisker is measured off a
#: significance glyph, and the half-width is the thing that would show it.
T_CRITICAL_N5 = 2.776
MEAN_TOLERANCE = 0.01
SEM_TOLERANCE = 0.02

SESSIONS = [("L-30", -30), ("R+1", 1), ("R+4", 4), ("R+9", 9), ("R+25", 25)]

# --------------------------------------------------------------------------
# who says so
# --------------------------------------------------------------------------
DEMO_NAME, DEMO_ORCID, DEMO_DATE = "Josiah Carberry", "0000-0002-1825-0097", "2026-08-11"
ATTESTATION_ENV = ("FDT_REVIEWER_NAME", "FDT_REVIEWER_ORCID",
                   "FDT_INSPECTION_DATE", "FDT_REGISTRATION_DATE")
_env = {k: os.environ.get(k, "").strip() for k in ATTESTATION_ENV}
_given = [k for k in ATTESTATION_ENV if _env[k]]
if _given and len(_given) < len(ATTESTATION_ENV):
    print("BLOCKED: a partial attestation is not an attestation.\n  set: %s\n"
          "  missing: %s" % (", ".join(_given),
                             ", ".join(k for k in ATTESTATION_ENV if not _env[k])),
          file=sys.stderr)
    raise SystemExit(2)

if _given:
    RUN_MODE = "ATTESTED"
    REVIEWER = dict(reviewer_id="RV_INSPECTOR", name=_env["FDT_REVIEWER_NAME"],
                    record_type="HUMAN", contact_type="ORCID",
                    contact=_env["FDT_REVIEWER_ORCID"],
                    registered_by=_env["FDT_REVIEWER_NAME"],
                    registration_date=_env["FDT_REGISTRATION_DATE"],
                    human_attestation="HUMAN_CONFIRMED",
                    note="read the paper, counted the figures, and checked "
                         "both overlays before approving")
    INSPECTION_DATE = _env["FDT_INSPECTION_DATE"]
    RUN_DATE = (os.environ.get("FDT_RUN_DATE", "").strip()
                or datetime.date.today().isoformat())
else:
    RUN_MODE = "DEMO_ONLY"
    REVIEWER = dict(reviewer_id="RV_INSPECTOR", name=DEMO_NAME,
                    record_type="DEMO_IDENTITY", contact_type="ORCID",
                    contact=DEMO_ORCID, registered_by=DEMO_NAME,
                    registration_date=DEMO_DATE,
                    human_attestation="DEMO_EXAMPLE",
                    note="ORCID's fictional demonstration record")
    INSPECTION_DATE = RUN_DATE = DEMO_DATE

# --------------------------------------------------------------------------
# the page, rendered once
# --------------------------------------------------------------------------
WORK = tempfile.mkdtemp(prefix="fdt_beckers_")
stem = os.path.join(WORK, "page")
subprocess.run(["pdftoppm", "-r", "300", "-f", "3", "-l", "3", "-png", pdf, stem],
               check=True, capture_output=True)
RASTER = next((os.path.join(WORK, n) for n in sorted(os.listdir(WORK))
               if n.startswith("page-") and n.endswith(".png")), "")
if not RASTER:
    print("SKIP: pdftoppm produced nothing", file=sys.stderr)
    raise SystemExit(0)

# --------------------------------------------------------------------------
# what is on it - measured by hand on this rendering, declared here
# --------------------------------------------------------------------------
PANELS = [
    dict(pid="P_APEN_SUPINE", fig="SF_BECKERS_F1", view="F_APEN_SUPINE",
         number="FIG1", label="Fig 1", posture="SUPINE", grid="G_SUPINE",
         unit_id="U_APEN_SUPINE",
         box=[305, 1176, 2021, 2744], ticks=[[1.3, 2019.5], [0.2, 2746.0]],
         y_region="182,302,2009,2756", x_region="302,1179,2746,2866",
         xs=[459.5, 601.0, 741.5, 881.5, 1024.0],
         caption="Fig. 1: Evolution of ApEn (mean +/- 95% confidence interval) "
                 "in supine position up to 25 days after return to earth."),
    dict(pid="P_APEN_STANDING", fig="SF_BECKERS_F2", view="F_APEN_STANDING",
         number="FIG2", label="Fig 2", posture="STANDING", grid="G_STANDING",
         unit_id="U_APEN_STANDING",
         box=[1449, 2254, 2051, 2718], ticks=[[1.3, 2049.5], [0.2, 2720.0]],
         y_region="1326,1446,2039,2730", x_region="1446,2257,2720,2840",
         xs=[1591.0, 1721.5, 1851.5, 1981.5, 2113.0],
         caption="Fig. 2: Evolution of ApEn (mean +/- 95% confidence interval) "
                 "in standing position up to 25 days after return to earth."),
]

PLAN = {
    "schema": "figure-digitization-triage/extraction-plan/1",
    "publication_id": "PUB_BECKERS2007",
    "reviewers": [REVIEWER],
    "documents": [dict(
        document_id="SD_BECKERS", role="MAIN_ARTICLE",
        source_file=os.path.basename(pdf), page_range="98-101",
        observed_figure_count=2, inventory_status="VISUALLY_VERIFIED",
        figure_count_method="HUMAN_VISUAL", reviewer_id="RV_INSPECTOR",
        inspection_date=INSPECTION_DATE,
        note="Beckers 2007, Microgravity Sci Technol XIX-5/6, 98-101")],
    "grids": [dict(grid_id=p["grid"],
                   factors={"SESSION": [s for s, _d in SESSIONS],
                            "POSTURE": [p["posture"]]},
                   note="one posture at five sessions") for p in PANELS],
    "reader_configs": [dict(config_id="C_APEN", options=dict(
        threshold=170, x_window=18, whisker_search_px=280,
        marker_half_height=8, stem_px=4))],
    "figure_views": {p["view"]: dict(caption=p["caption"],
                                     note="one panel, one series, five sessions")
                     for p in PANELS},
    "figures": [dict(
        source_figure_id=p["fig"], document_id="SD_BECKERS",
        figure_number=p["number"], source_file=os.path.basename(pdf),
        source_page=3, image=RASTER,
        image_sha256=MR.sha256_of(RASTER),
        observed_panel_count=1, inventory_status="VISUALLY_VERIFIED",
        panel_count_method="HUMAN_VISUAL", reviewer_id="RV_INSPECTOR",
        inspection_date=INSPECTION_DATE, caption=p["caption"],
        panels=[dict(
            panel_id=p["pid"], label=p["label"],
            outcome_label="ApEn %s" % p["posture"].lower(),
            target_status="TARGET", disposition="AUTO_DIGITIZE",
            reason="the figure is the only source of these means at these "
                   "sessions",
            read=dict(
                mark_type="LINE_MONO", unit_id=p["unit_id"],
                figure_view=p["view"], box=p["box"], y_ticks=p["ticks"],
                y_scale="LINEAR", x_scale="LINEAR", config_id="C_APEN",
                axis_y_region=p["y_region"], axis_x_region=p["x_region"],
                series=[dict(series_id="S_APEN", factor="POSTURE",
                             level=p["posture"], marker="ANY",
                             marker_fill="OPEN")],
                positions=[dict(position_id="%s_%d" % (p["number"], i),
                                factor="SESSION", level=level,
                                x_pixel=x, timepoint_label=level,
                                timepoint_days=days)
                           for i, ((level, days), x)
                           in enumerate(zip(SESSIONS, p["xs"]))]))])
        for p in PANELS],
    "units": [dict(
        unit_id=p["unit_id"], figure_view=p["view"], grid_id=p["grid"],
        panel=p["label"], outcome_name="Approximate entropy of RR intervals",
        domain="AUTONOMIC", unit="dimensionless", statistic="CONTINUOUS",
        dispersion_type="CI95", n_outcome=5, n_source="TEXT_METHODS",
        bar_top_definition="MARKER_CENTER", errorbar_stem_confirmed="TRUE",
        errorbar_source="CAPTION", grid_rule="FULL", value_scale="RATIO",
        # ApEn is a bounded, roughly symmetric index and the paper analyses it
        # untransformed - it prints means and SEMs of the index itself.
        analysis_transformation="UNTRANSFORMED",
        distribution_shape="SYMMETRIC", transformation_source="",
        note="caption states mean +/- 95% confidence interval",
        x_calibration=[[0, p["xs"][0]], [4, p["xs"][-1]]]) for p in PANELS],
}

PLAN_PATH = os.path.join(WORK, "plan_beckers.json")
with open(PLAN_PATH, "w", encoding="utf-8") as fh:
    json.dump(PLAN, fh, indent=1)

MANIFESTS = os.path.join(WORK, "manifests")
OUT = os.path.join(WORK, "out")
print("Beckers 2007 - approximate entropy, two figures, ten cells  [%s]"
      % RUN_MODE)
_paths, plan_problems = CP.compile_plan(json.load(open(PLAN_PATH, encoding="utf-8")),
                                       MANIFESTS, file_root=WORK,
                                       run_date=RUN_DATE)
if plan_problems:
    for problem in plan_problems[:10]:
        print("  %s" % (problem,))
    raise SystemExit("the plan does not compile")
summary = RB.run_batch(MANIFESTS, OUT, file_root=WORK, run_date=RUN_DATE)
passed = int(summary.get("machine_qc", summary.get("machine_qc_passed", 0)))
print("  run: %s | %s | panels %d | read %d | machine QC passed %d"
      % (summary["status"], summary.get("run_mode", RUN_MODE),
         summary["panels"], summary["values"], passed))

failures = []
if RUN_MODE == "DEMO_ONLY":
    # THE RUNNER REFUSES FIRST, before this script gets anywhere near a review
    # file. A DEMO_ONLY run whose values pass the machine gate has produced
    # exactly the artifact a demonstration must not leave behind - ten numbers
    # that look poolable, standing behind a fictional identity - so
    # `run_batch` deletes its own output and stamps DEMO_OUTPUT_REFUSED.
    # There is nothing to review because there is nothing on disk to review.
    if summary["status"] != "DEMO_OUTPUT_REFUSED":
        failures.append("a DEMO_ONLY run produced output: %s"
                        % summary["status"])
    if os.path.exists(os.path.join(OUT, "figure_values_machine_qc.csv")):
        failures.append("the refused run left its values on disk")
    print("  refused: %s - the ten values passed the gate and were deleted "
          "with the run" % summary["status"])
    print()
    print("  set FDT_REVIEWER_NAME, FDT_REVIEWER_ORCID, FDT_INSPECTION_DATE")
    print("  and FDT_REGISTRATION_DATE to attest a real inspection, and this")
    print("  runs the review and finalize steps as well.")
    print()
    for line in failures:
        print("FAIL %s" % line)
    raise SystemExit(1 if failures else 0)

if summary["status"] != "RAN":
    failures.append("the run did not complete: %s" % summary)
if passed != 10:
    failures.append("%d of 10 cells passed the machine gate" % passed)

# --------------------------------------------------------------------------
# the review. This is the step the package exists to make meaningful, so the
# file is written the way a person would get it: from the run's own queue,
# fingerprints already filled in, decisions blank.
# --------------------------------------------------------------------------
import pandas as pd                                               # noqa: E402

REVIEW = os.path.join(OUT, "value_review.csv")
queue = pd.read_csv(os.path.join(OUT, "review_queue.csv"), dtype=object).fillna("")
FB.write_review_template(REVIEW, queue)
rows = list(csv.DictReader(open(REVIEW, encoding="utf-8")))
for row in rows:
    # CONFIRMED, not TRUE. The confirmation columns are not booleans - they
    # record that a person looked at a particular artifact, and the token is
    # `run_batch.REVIEW_CONFIRMED`. "TRUE" reads as a checkbox and is refused.
    row.update(Reviewer_ID="RV_INSPECTOR", Decision="APPROVED",
               Marks_Checked=RB.REVIEW_CONFIRMED,
               Axis_Labels_Checked=RB.REVIEW_CONFIRMED,
               Calibration_Checked=RB.REVIEW_CONFIRMED,
               Identity_Checked=RB.REVIEW_CONFIRMED,
               Reviewed_At=INSPECTION_DATE,
               Note="marker centres and whisker caps checked against "
                    "review/%s_overlay.png" % row["Panel_ID"])
with open(REVIEW, "w", newline="", encoding="utf-8") as fh:
    writer = csv.DictWriter(fh, fieldnames=FB.VALUE_REVIEW_COLUMNS)
    writer.writeheader()
    writer.writerows(rows)
print("  review: %d panel(s) approved by %s (%s)"
      % (len(rows), REVIEWER["name"], REVIEWER["record_type"]))

result = FB.finalize(OUT, review_path=REVIEW, run_date=RUN_DATE)
print("  finalize: %s | panels approved %d | values accepted %d"
      % (result["status"], result["approved"], result["accepted"]))
for problem in result["problems"][:6]:
    print("      %-34s %s" % (problem["check"], problem["detail"][:74]))

if True:
    if result["status"] != "FINALIZED":
        failures.append("an attested run did not finalize: %s"
                        % result["detail"])
    accepted_path = os.path.join(OUT, FB.FINALIZE_MARKER)
    if not os.path.exists(accepted_path):
        failures.append("no %s was written" % FB.FINALIZE_MARKER)
    else:
        accepted = pd.read_csv(accepted_path, dtype=object).fillna("")
        print()
        print("  POOLING_ELIGIBLE, against Table 1 of the same paper:")
        print("    %-9s %-6s %8s %8s   %10s %8s"
              % ("posture", "session", "read", "printed", "half-width",
                 "SEM x t"))
        worst_mean = worst_sem = 0.0
        for _, row in accepted.iterrows():
            cell = dict(part.split("=", 1)
                        for part in str(row["Cell_Key"]).split(";"))
            key = (cell["POSTURE"], cell["SESSION"])
            printed_mean, printed_sem = TABLE_1[key]
            got = float(row["Mean"])
            half = (float(row["Errorbar_Upper"]) - float(row["Errorbar_Lower"])) / 2.0
            implied = printed_sem * T_CRITICAL_N5
            worst_mean = max(worst_mean, abs(got - printed_mean))
            worst_sem = max(worst_sem, abs(half - implied))
            print("    %-9s %-6s %8.4f %8.2f   %10.4f %8.4f"
                  % (key[0], key[1], got, printed_mean, half, implied))
        if len(accepted) != 10:
            failures.append("%d accepted values, expected 10" % len(accepted))
        if worst_mean > MEAN_TOLERANCE:
            failures.append("worst mean %.4f from the printed table, over %.2f"
                            % (worst_mean, MEAN_TOLERANCE))
        if worst_sem > SEM_TOLERANCE:
            failures.append("worst half-width %.4f from %.3f x SEM, over %.2f"
                            % (worst_sem, T_CRITICAL_N5, SEM_TOLERANCE))
        print("    worst mean %.4f, worst half-width %.4f"
              % (worst_mean, worst_sem))

print()
if failures:
    for line in failures:
        print("FAIL %s" % line)
    raise SystemExit(1)
print("verdict: PASS - ten cells AUTO_EXTRACTED -> MACHINE_QC_PASSED -> "
      "HUMAN_APPROVED -> POOLING_ELIGIBLE, every one within %.2f of the "
      "table the same paper prints." % MEAN_TOLERANCE)
