# figure-digitization-triage

A reproducible figure-digitization and QC system for a systematic review of
cardiovascular responses to spaceflight and head-down bed rest. The figure-level
worklist holds 116 publications and 637 figure rows, of which 95 publications
and 353 figures are to be digitized. Many of the included studies report their
outcomes only as plots, so the numbers have to be read off the figures — and a
number read off a figure is only usable if the pipeline that produced it can say
exactly what it did.

**Private research repository.** It contains publisher figure rasters from
three publications (323, 386, 397), held for reproducibility of the extraction.
They are not licensed for redistribution.

## The path a number takes

    plan_397.json                one typed document per publication
      | compile_plan.py          hashes, figure rows and calibrations DERIVED
      v
    eleven manifests             validated before a raster is opened
      | run_batch.py
      v
    figure_values_machine_qc.csv the gate found nothing wrong. NOT poolable.
    review/<Panel_ID>_overlay.png what the reader saw, drawn on what it read
      | a person looks, and fills value_review.csv
      | finalize_batch.py
      v
    figure_values_accepted.csv   the only file to pool from

## What it does

    reviewer_registry.csv        who may attest an inventory, and how to reach them
    source_document_manifest.csv one row per article / supplement / chapter
    source_figure_manifest.csv   one row per physical publisher figure
    source_panel_inventory.csv   one row per visible panel, including the ones
                                 that will never be digitized
    ────────────────────────────────────────────────────────────────────────────
    figure_manifest.csv          the figure a value came from
    grid_definitions.csv         the factors and levels a figure declares
    unit_manifest.csv            Figure × Panel × Outcome × Statistic
    figure_values.csv            Unit_ID × Cell_Key
    ────────────────────────────────────────────────────────────────────────────
    panel_manifest.csv           panel box, mark type, axis calibration
    series_manifest.csv          how the reader tells a series apart, and what
                                 that series MEANS
    position_manifest.csv        x pixel or slot, and what that position MEANS
    reader_config.csv            long-form reader options, one row per option

`compile_plan.py` writes all eleven from one plan. `run_batch.py` executes the
run layer, gates the result against the data grains, and reports what it could
not do. `finalize_batch.py` turns approved panels into poolable values, and
nothing else does.

## Three rules

**No per-publication exception rules.** `Data_Shape` (A–G) is a display hint;
validation is a universal factorial grid keyed on declared dimensions. Exception
codes exist per *data type*, never per paper.

**Identity is declared, never inferred.** A series is a factor level because the
manifest says so, not because it was drawn second. When a reader cannot resolve
a mark, the cell stays empty and the grid gate names the hole — nothing shifts
to fill it.

**Fail closed, and loudly.** Every panel lands on exactly one terminal state,
and everything short of `AUTO_PASS` goes to `manual_queue.csv` with the reason
attached. A panel the reader could not do is louder than one it could — and a
defect in a reader stops the batch rather than arriving in somebody's queue as
"go and look at this figure again".

## Running it

    pip install -r requirements-lock.txt     # the versions results were produced on
    python3 pilot_397.py                     # the worked example, publication 397

    python3 compile_plan.py plan_397.json MANIFEST_DIR --file-root .
    python3 run_batch.py MANIFEST_DIR OUT --file-root .
    python3 finalize_batch.py OUT --template # then fill in the decisions
    python3 finalize_batch.py OUT

Every test file is a standalone script:

    for t in test_*.py; do python3 "$t"; done

<!-- CURRENT_PIPELINE_VERSION: 9.1 -->
<!-- CURRENT_SCENARIO_COUNT_CORE: 2940 -->
<!-- CURRENT_SCENARIO_COUNT_FULL: 2978 -->

2940 scenarios on main after v9.1 under `requirements-lock.txt`, and 2978 with
the intake backends — `test_corpus_intake` skips its PDF adapter, per-status,
renderer and crop sections where none is installed. **CI runs both**, in two
jobs that install what their profile names rather than inheriting it from the
runner image: `core` removes poppler-utils and the Python backends before it
starts, `intake-full` installs `requirements-intake.txt` and poppler-utils. A
count that depends on what `ubuntu-latest` happens to ship is not a property of
this repository.

Both are verified in a clean room with scipy blocked — the statistics are
hand-rolled in NumPy so a missing scipy cannot silently change a p-value. Every
run records the Python, platform and library versions it used;
`requirements-lock.txt` pins what the shipped results were produced on, because
a bar top found at row 312 by one OpenCV and row 313 by the next is a different
number in the accepted file.

## Attestation

No software can count the panels in an arbitrary published figure, so the
inventory reduces to a person having opened it and looked. `reviewer_registry.csv`
records who that was, with a contact and `Reviewer_Record_Type` ∈
`HUMAN | DEMO_IDENTITY`. A run resting on a `DEMO_IDENTITY` reviewer is
`DEMO_ONLY` wherever it is launched from: it may produce a queue, a coverage
ledger and a list of QC failures, but if it reaches the end holding values the
gate accepted it writes none of them.

`Human_Attestation` is a declared enum, not a cryptographic signature. It buys
traceability — a row that can be asked about — not proof of authorship.

Machine QC is not approval. `run_batch.py` stops at `MACHINE_QC_PASSED`, which
means the gate found nothing wrong; it does not mean anybody looked at where
the marks landed, and a reader that puts a plausible number on the wrong bar
produces exactly the output the gate has nothing to say about. Each passing
panel is queued with a `Review_Mode` naming what to open — an overlay PNG in
almost every case, the WPD project when the picture could not be drawn — and
`finalize_batch.py` writes the accepted file for panels a registered human
approved against that specific extraction.

What the approval is bound to is `Review_Subject_SHA256`: the values themselves
with their cell keys, every manifest, the raw marks, the WPD project and the
environment that produced them. Change any of it — swap what `CONTROL` and
`TREATED` mean, nudge a tick, upgrade OpenCV — and the approval is
`APPROVAL_STALE`, not inherited. The finalizer also re-hashes everything it
reads before consulting a decision, so editing a value after approving the
overlay is `RUN_ARTIFACT_MODIFIED` rather than an input.

**Hashed and parsed from the same bytes, once.** A hash check that re-opens the
path names one file and decides from another, and a save landing between the two
is all it takes. Every verified input goes through `read_verified_bytes` — one
read, hash those bytes, parse those bytes, as CSV or as JSON — and the frames
travel out of the decision as a `RunSnapshot` on the verdict: the run stamp, the
registry, the machine rows, the queue, the artifact ledger and both decision
files. `review_preflight.py` derives its questions, its bundle and answer
diagnoses, its comparison and its identity checks from that snapshot rather than
opening the paths again, and says `NOT EVALUATED` where a field is absent rather
than falling back to a second read. So the finalizer's answer and everything
printed beside it come from one moment.

That now reaches the structured artifacts the ledger points at — identity
resolutions, inference manifests, raw marks, point data, the geometry file. Each
is kept from the read that hashed it and handed to the contract check that
interprets it, so a geometry file swapped after verification cannot become the
evidence for a route it does not support. A picture or a contact sheet is hashed
and nothing more: this module never parses one, so its digest is the whole of
what the finalizer needs. The bytes are addressed by what the LEDGER recorded —
type, panel, reference, run-relative path, digest — not by a realpath computed
afterwards, so re-pointing a symlink between the hash and the read cannot move
which entry a row resolves to.

To run the pilot as attested work:

    export FDT_REVIEWER_NAME="..." FDT_REVIEWER_ORCID="0000-0000-0000-0000"
    export FDT_INSPECTION_DATE=YYYY-MM-DD FDT_REGISTRATION_DATE=YYYY-MM-DD
    python3 pilot_397.py

All four or none. A partial attestation exits 2.

## History

Each commit is a packaged snapshot rather than an incremental patch, so the
diffs are wider than a normal working history. What every commit does carry is a
state the whole suite passed in, and a message naming the review round that
produced it. Every fix in every round was reverted in a scratch copy and the
suite re-run — a test that passes before and after a fix is decoration, and the
commit messages record how many scenarios each revert broke.

`INSTALL.md` is the long-form version of that record. `SKILL.md` is the whole
protocol as an extractor - or an agent - reads it, standalone and installable;
`MIGRATION.md` covers the schema changes; `PILOT.md` is the order a PERSON works
in for the one part of this package a program may not do.

That order now names its first subject and runs the preflight twice. Publication
127, Verheyden 2007 Figure 4, is **the first production R2 + human-resolution
pilot** — not an R3 partial-rejection pilot, and the runbook does not let anyone
claim it was one. Before a figure is opened, `review_preflight.py` is run on the
templates and is *expected* to exit 2: the finalizer cannot say `FINALIZED`
before a person has answered anything, so what must be clean at that point is
the bundle. Run again on the filled-in answers it must exit 0. Both numbers are
read out of `PILOT.md` by the suite and checked against the tools, because a
runbook that promises the wrong exit code sends every reviewer to fix a bundle
that was never broken.

127 is queued `BAR_MONO_GEOMETRY_RESOLVED`, which is not an overlay: three of
the four confirmations that mode asks for cannot be made from a panel picture,
so the runbook walks its reviewer through the seven artifacts it registers — the
contact sheet, the calibration panels, the row crops, the identity resolution
and its evidence, the overlay last — and a fifth confirmation the mode does not
ask for at all. `Inference_Checked` is derived from the panel's own values, so
the suite checks the runbook against `REVIEW_CONFIRMATIONS` *plus*
`inference_confirmations` on a real prototype-matched panel, and requires every
one to be paired against the picture that answers it.

**Two people, and the tools now check it.** `--distinct-reviewers` on the
finalizer and the preflight refuses `RESOLVER_IS_APPROVER` when the person who
named a series in `identity_resolution.csv` is the person signing the panel that
naming lands in — compared as PEOPLE, by normalized ORCID, because a
`Reviewer_ID` identifies a row and one human registered twice under two IDs read
as two reviewers. Where an ORCID is absent the contract refuses
(`REVIEWER_IDENTITY_UNPROVABLE`) rather than treating two mailboxes as two
people, and it applies to panels that carry a hand-resolved identity: a panel
nobody resolved has no resolver for its approver to be distinct from. The policy
itself is checked against `SEPARATION_POLICIES` and an unrecognised token stops
the finalization, so the stamp's `Reviewer_Separation_Policy` can never name a
contract that was applied to nothing.

There is no `--second` fallback: that flag reads two `inference_review.csv`
files, so it sees the per-cell channel and nothing else. It exits 2 unless every
question was answered once on both sides, the two answers agree, the two files
are two files, the two readers are two PEOPLE by ORCID, and the second file is a
complete review record — this run's own panel, unit and cell on every row,
matched exactly rather than "matching or blank", and a `Reviewed_At` that is a
real past date. The registry those identity checks run against travels out of
the finalizer's verdict, so it is the snapshot the decider verified rather than
a second reading of the same path. It remains a read-only qualification check:
the finalizer never reads the second file, so nothing in it is bound into
`Review_Subject_SHA256` or stamped.

## Status

Publication 397 runs end to end: 26 panels, 384 declared cells, 123 read,
**0 accepted**. That is the correct answer, not a failure — the running text
gives "30-min means and SEMs" for the line figures, while the Figure 3/4
captions say only "(3-min means)". Whether the bars are SD or SEM is not in the
paper, so every read cell sits at `QC_FAILED` pending an author query.

`LINE_MONO_STYLE` shipped and all twelve two-black-curve panels of Figures 1
and 2 now read. Against an independent eye reading of Figure 1's MEN mean
arterial pressure it lands 18 of 24 cells within 1.65 mmHg on a 50 mmHg axis
and refuses the other 6, at the three positions where the two curves are one
run of ink — nine to ten pixels thick where a stroke is three.

**Four of those eighteen have their series named by elimination, and say so.**
Furniture is dropped from the duty accounting, which hides a dashed curve's
gaps and cannot invent them, so a curve running along a gridline measures a
perfect solid line. A SOLID call made through a window that could not see half
of itself is withheld; where the panel declares two styles and the reader found
two curves, naming one names the other. Every such cell carries
`line_style_source`, and the review overlay stars it.

**123 of 384 declared cells is a low yield and the right one.** Several of
these panels run their two curves within a stroke of each other for much of
their length, and a cell nobody can attribute is a cell this reader does not
emit. The geometry behind all twelve is checked against the rasters by
`forward_test_397_line_geometry.py`: every declared calibration row is a
printed gridline and every declared x is the centre of its category interval.

`pilot_beckers.py` finishes the ladder on a different paper. Beckers 2007 plots
approximate entropy as mean and 95% CI, and Table 1 of the same paper prints
the same means, so there is a reader-independent answer at the end. Attested it
runs `AUTO_EXTRACTED → MACHINE_QC_PASSED → HUMAN_APPROVED → POOLING_ELIGIBLE`
and writes ten accepted values, worst mean 0.0057 and worst CI half-width
0.0133 against 2.776 × the printed SEM. Unattested, `run_batch` deletes its own
output and stamps `DEMO_OUTPUT_REFUSED` — a demonstration identity cannot stand
behind a poolable value.

Open work: publication 386 Figures 3–4, and five cells of publication 323 that
need a human reading.
