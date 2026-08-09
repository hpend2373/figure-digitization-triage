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

1600 scenarios on main after v7.24, verified in a clean room with scipy blocked — the
statistics are hand-rolled in NumPy so a missing scipy cannot silently change a
p-value. Every run records the Python, platform and library versions it used;
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
`MIGRATION.md` covers the schema changes.

## Status

Publication 397 runs end to end: 18 panels, 192 declared cells, 48 read,
**0 accepted**. That is the correct answer, not a failure — the running text
gives "30-min means and SEMs" for the line figures, while the Figure 3/4
captions say only "(3-min means)". Whether the bars are SD or SEM is not in the
paper, so all 48 cells sit at `QC_FAILED` pending an author query.

Open work: the solid/dashed `LINE_MONO_STYLE` reader (blocks 397 Figures 1–2,
288 declared cells; measured state in `wip/`), publication 386 Figures 3–4, and
five cells of publication 323 that need a human reading.
