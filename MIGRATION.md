# From shape-dispatched to factorial-grid validation

## Why

`fig_validate_extraction` branched on `Data_Shape`, so a figure that did not fit
its label needed a new rule. That is how `B_DUPLICATE_CELL` fired on a perfectly
well-formed 6-session x 2-posture figure, and how the next step would have been
`A_CONDITION_SET_ASYMMETRIC` — a rule about one study, wearing a shape's name.

A 6x2 session-by-posture figure, a 4x3 gravity-by-load figure and a two-cell
pre/post study differ in their factors and levels, not in their validation logic.

## The four grains

The four analytical grains are preceded by three source-completeness grains:

| Grain | One row per | Answers |
|---|---|---|
| source document manifest | main article/supplement/chapter | complete page range and how many physical figures it contains |
| source figure manifest | physical publisher figure | how many plot regions are actually visible, and who verified the full raster |
| source panel inventory | visually distinct source subpanel | target status and disposition, including non-data panels and panels not configured for a reader |

These use `Source_Figure_ID`/`Source_Panel_ID`.  Analytical `Figure_ID` may be
split by outcome and is never used to prove completeness.

| Grain | One row per | Answers |
|---|---|---|
| figure manifest | figure | the source, the image, the panel reconciliation |
| grid definitions | grid x factor x level | what the axes and series actually are |
| unit manifest | figure x panel x outcome x statistic | which panel fills it (`Panel_ID`, `Source_Panel_ID`), how it was read, and how the grid must behave |
| **figure values** | cell | the reading, addressed by `Cell_Key` |

A hand-curated set names these whatever suits it — `id323_figure_values.csv` in
the worked example. **A batch run does not.** `run_batch.py` writes the values
grain as several files and deliberately never as `figure_values.csv`:

| Output | Written by | Contains |
|---|---|---|
| `figure_values_raw.csv` | `run_batch.py` | every reading, each row carrying `Run_Panel_ID`, physical `Source_Panel_ID`, `Value_Status`, `QC_Codes` and `Pooling_Eligible` |
| `figure_values_machine_qc.csv` | `run_batch.py` | the rows the gate found nothing wrong with. **Not poolable** — machine QC is not a person having looked |
| `review_queue.csv` | `run_batch.py` | one row per panel awaiting review, with its `Review_Mode`, its artifacts and `Review_Subject_SHA256` |
| `panel_artifacts.csv` | `run_batch.py` | every overlay, project, mark file and point file, by run-relative path and SHA-256 |
| `figure_values_accepted.csv` | **`finalize_batch.py`** | only rows a registered human approved against that exact extraction — the only file to pool from |
| `source_panel_coverage.csv` | `run_batch.py` | every physical panel, including non-target, not-data, manual and no-reader dispositions |

Since 7.13 `run_batch.py` does **not** write `figure_values_accepted.csv`. It
stops at machine QC; the accepted file is `finalize_batch.py`'s output and
exists only where somebody looked at the extraction and said so. If you are
upgrading from a version whose runner wrote it directly, that is the one change
that alters what "the poolable file" means.

The plain name is gone on purpose. A single `figure_values.csv` once carried
eight means whose SD-versus-SEM was unresolved while the panels sat at
`QC_FAILED` in a different file, and anything that read "the values file" would
have pooled them.

`figure_extraction_template_v7.csv` is the flat single-table template of the
**pre-batch hand-extraction path**, which `kernel.fig_validate_extraction` still
serves and `build_id323.py` still demonstrates. It is not an input to
`run_batch.py` and never was. It is regenerated from `fig_template_columns()`
by the suite, so it cannot drift from the code, but do not start a batch from
it — start from an extraction plan.

`Cell_Key` is `FACTOR=LEVEL` pairs joined by `;`, canonicalised on parse — factor
order and case do not matter, so `POSTURE=supine;TIMEPOINT=b-1` and
`TIMEPOINT=B-1;POSTURE=SUPINE` are the same cell. Arbitrary arity: a three-factor
design needs no schema change.

## What the checker looks at

    are the figure's factors and levels DECLARED
    is every cell of the Cartesian product PRESENT
    is any combination DUPLICATED
    where cells are absent, is there a SPARSE justification that is not a placeholder
    panel / outcome / unit / dispersion / N / provenance complete
    R1 / R2 readings coherent with the consensus

It never asks whether the figure is called A, B, C or G.

## Universal codes

`FACTOR_LEVEL_MISSING`, `FACTORIAL_CELL_MISSING`, `FACTORIAL_CELL_DUPLICATE`,
`FACTOR_SET_INCONSISTENT`, `UNDECLARED_FACTOR_LEVEL`,
`EXPECTED_CELL_COUNT_MISMATCH`, plus `DUPLICATE_FACTOR_LEVEL`,
`DUPLICATE_FIGURE_UID`, `BAD_CELL_KEY`, `SPARSE_WITHOUT_JUSTIFICATION`,
`BAD_GRID_RULE`, `BAD_STATISTIC_TYPE`, `BAD_DISPLAY_HINT`.

Retired: `B_PHASE_MISSING`, `B_POSTURE_SET_ASYMMETRIC`, `B_GRID_COLLAPSED`,
`B_DUPLICATE_CELL`, `A_PHASE_INCOMPLETE`, `A_SINGLE_POINT_SERIES`,
`C_NO_BASELINE`, `C_NO_FOLLOWUP`, `C_MISSING_DAYS`, `D_NO_PREPOST_PAIR`,
`D_DELTA_MIXED_WITH_LEVELS`, `G_*`, `MIXED_SHAPE_IN_UNIT`.

## What survives

`Statistic_Type` (`CONTINUOUS` / `BINARY_EVENT` / `ASSOCIATION`) still selects
which value columns are required — an event count and a correlation coefficient
are not means. The grid rules above are identical across all three.

`Display_Hint` keeps the A–G vocabulary as advice to whoever opens WPD. A typo is
flagged (`BAD_DISPLAY_HINT`); nothing branches on the value. `test_grid_engine.py`
asserts that: the same bundle under five different hints yields the same verdict,
clean and failing.

## Sparse grids

`Grid_Rule=SPARSE` excuses a hole in the product and requires
`Sparse_Justification` — real text, checked against the placeholder vocabulary.
It does NOT excuse a declared level that appears in zero cells: that is a
declaration error, and `FACTOR_LEVEL_MISSING` still fires.

## Per figure, a human declares this once

    Figure_UID              323|FIGURE 1|SAP
    Statistic_Type          CONTINUOUS
    Display_Hint            G_FACTORIAL_CONDITIONS      (advice only)
    Grid_Rule               FULL
    Expected_Cell_Count     12
    TIMEPOINT               B-1, DI7, DI14, DI19, R1, R5
    POSTURE                 SUPINE, ORTHOSTASIS

Everything after that — completeness, duplication, the grid, dispersion,
provenance, dual reading — is the same engine for all 160 papers.

## Worked example

`id323_fig1_figure_{manifest,dimensions,values}.csv`: 6 panels, 48 declared
levels, 72 cells, **0 problems**. The same data previously raised
`B_DUPLICATE_CELL` purely because six sessions do not fold onto a two-phase label.

## `min_bar_px` on BAR_MONO changed grain in v7.25

The option is still accepted and still an integer number of pixels, and a
manifest carrying the old value keeps working. What it measures and what
happens when a bar fails it both changed, so a person reading a run's refusals
should know which one they are looking at.

| | `read_monochrome_bar_panel` (before) | `read_monochrome_bar_geometry` (v7.25) |
|---|---|---|
| measured | the whole group's inked span, against `min_bar_px * n_series` | ONE bar's footprint, after the trim |
| on failure | the group is skipped: no record, no error | the bar is refused: `BAR_TOO_NARROW`, with `footprint_width` and `min_bar_px` on the row |
| the panel then | reports fewer bars than it declared, silently | reports every bar it declared, one of them refused |

The old behaviour is the failure `NO_SEED_SUPPORT` exists to close, reachable
through a config file. Nothing in the measured corpus is near the default of 12:
the narrowest footprint anywhere is 27 px, in the synthetic fixture, and
publication 127's bars are 182-188 px wide.

**No action is needed for existing manifests.** If a manifest set `min_bar_px`
in order to make a group disappear, that group will now appear with a named
refusal instead - which is the intended change, and the row can be resolved by a
reviewer like any other.

## `value_review.csv` gains `Marks_Checked` in v7.27

An approval said a person agreed. It did not say what they LOOKED at, and the
two are different claims: the whole reason a panel is queued with an artifact
is that somebody opens it, and `Decision=APPROVED` typed down a column is
indistinguishable from a review that happened.

`value_review.csv` now carries `Marks_Checked`, and the finalizer refuses an
approval that does not say `CONFIRMED` there - `REVIEW_CONFIRMATION_MISSING`.
Which confirmations a panel needs comes from its `Review_Mode`, so a mode that
puts more in front of a reviewer can ask about more.

| | before | v7.27 |
|---|---|---|
| columns | `Review_ID, Panel_ID, Review_Subject_SHA256, Reviewer_ID, Decision, Reviewed_At, Note` | ... `Decision, Marks_Checked, Reviewed_At, Note` |
| an APPROVED row with the column blank | finalized | `REVIEW_CONFIRMATION_MISSING` |

**Existing review files need one column added.** The value is `CONFIRMED`
(case-insensitive) for a panel whose marks were actually checked. There is no
back-fill worth doing automatically: a script that writes `CONFIRMED` into every
row of an old file reproduces exactly the ambiguity the column exists to remove.

`REVIEW_MODES` also became mode -> a TUPLE of required artifact types rather
than one. Nothing about the two shipped modes changes; a mode that needs the
numbers, the pictures and the index tying them together now has somewhere to
say so.


# v9.3: `unit_manifest` names the panel that fills it

## Why

v9.1 made the panel-unit binding two-sided in the PLAN: `unit.panel_id` beside
`panel.read.unit_id`, so exchanging the units of two panels of one figure is
refused before a raster is opened. `unit_manifest.csv` was not changed, and it
carried a free-text `Panel` label - which means a manifest set that did not come
through `compile_plan.py` contained no statement of which panel each unit was.
Exchange two panels' `Unit_ID` there and every check passes: the measurements are
right, each value matches its own mark hash, the factor sets and cell counts are
identical, and one panel's correct numbers arrive under the other's outcome.

## What changed

Two columns, and a bijection `validate_batch_manifests` now requires.

| | before | v9.3 |
|---|---|---|
| columns | `Unit_ID, Figure_ID, Grid_ID, Panel, ...` | `Unit_ID, Figure_ID, Grid_ID, Panel_ID, Source_Panel_ID, Panel, ...` |
| a unit with no `Panel_ID` | ran | `UNIT_NAMES_NO_PANEL` |
| two panels reading one unit | ran, the second overwrote the first's calibration | `UNIT_FILLED_TWICE` |
| the units of two panels exchanged | ran, values under the wrong outcome | `PANEL_UNIT_MISMATCH` |

`Panel` is unchanged and still a human label ("MEN", "NO_FLUID_HDT"). It was
never a foreign key and is not one now.

**Existing unit manifests need two columns added.** For a set whose panels each
fill one unit, the back-fill is mechanical and safe - take
`panel_manifest.Panel_ID` and `panel_manifest.Source_Panel_ID` from the row whose
`Unit_ID` matches:

    python3 - <<'PY'
    import csv, sys
    panels = {r["Unit_ID"]: r for r in csv.DictReader(open("panel_manifest.csv"))}
    rows = list(csv.DictReader(open("unit_manifest.csv")))
    out = []
    for r in rows:
        p = panels.get(r["Unit_ID"])
        if p is None:
            sys.exit("no panel reads %s - the pairing is a decision, not a "
                     "back-fill" % r["Unit_ID"])
        r["Panel_ID"], r["Source_Panel_ID"] = p["Panel_ID"], p["Source_Panel_ID"]
        out.append(r)
    ...
    PY

It stops rather than guessing in the two cases where the answer is a decision: a
unit no panel reads, and a unit two panels read. Those are the states the new
checks exist to name, and a script that picks one of the two panels reproduces
exactly the ambiguity the columns remove. `compile_plan.py` fills both columns
from the plan, so a plan-driven set needs no migration at all - recompile it.


# v9.6: an approval's fingerprint is re-derived, so some old approvals expire

## Why

`Review_Subject_SHA256` is what makes an approval an approval of an EXTRACTION
rather than of a panel name. The finalizer compared the approval's copy of it
against the review queue's copy - and both were written by the same producer, so
the guarantee reduced to that producer's arithmetic being right. It is now
re-derived from the verified run with `run_batch.review_subject_sha256`.

Re-deriving it showed the formula was not derivable at all: a value cell holding
Python `None` hashed as the text `None`, while the CSV that same run wrote - and
that a reviewer and the finalizer both read - carries an empty cell there. So the
subject could only ever be recomputed by the process that happened to hold the
None. `None` and NaN are now both the empty string (`run_batch._blank_text`).

## What changed for a run you already have

| | before | v9.6 |
|---|---|---|
| the queue's fingerprint | trusted | re-derived; `QUEUE_REVIEW_SUBJECT_INVALID` when it does not match |
| a value cell holding `None` | hashed as `None` | hashed as empty, like the CSV |

**An approved run made before v9.6 whose candidates have an empty numeric cell
will be refused.** Every BAR_MONO panel has one (`Errorbar_Lower`). The fix is to
re-run and re-approve. There is deliberately no back-fill: a script that
recomputed the old hash so the old approval matched would be reinstating exactly
the thing the check exists to stop, and the approval it preserved would be an
approval nobody can verify.

Runs whose candidate rows have no empty cells are unaffected, and every run
produced by v9.6 or later re-derives exactly.


# v9.16: the fill is decided inside the shape, so routed point files change shape

## Why

`marker_routing.route` asked two questions of a monochrome scatter: a SHAPE
split over every mark's radial third harmonic, and a FILL split over every
mark's interior ink. Both were taken over the WHOLE PANEL, and the second one
should not have been.

Interior ink is read in a window at the mark's centroid. A ring encloses white;
a triangle inscribed in the same box puts two of its own edges through that
window. So a panel drawing rings, discs, hollow triangles and solid triangles
has four bands in one distribution, not two — measured on `twin_scatter_s3.jpeg`
and matched one-to-one against what was drawn:

    CIRCLE   OPEN     0.048 - 0.295
    TRIANGLE OPEN     0.333 - 0.510
    TRIANGLE FILLED   0.857 - 0.932
    CIRCLE   FILLED   1.000

A panel-wide split pools those into two clusters, so the spread it scores as one
cluster's is two clusters'. On every rendering this repository carried before
v9.16 the largest gap was still the one between OPEN and FILLED, so the grain
was wrong in principle and right in every observed case.
`split_grain_confounded.jpeg` is the case where it is wrong in fact: its open
triangles are printed with the heavier outline journals use, the largest pooled
gap then falls between the two OPEN classes, and the panel-wide rule calls all
five open triangles FILLED and routes them to the filled-triangle series. Asked
inside each measured shape the same panel is right about all twenty-five marks.

Three candidates were compared in one harness (`compare_split_grain.py`) before
anything changed. Relaxing the minimum class size — the reading of publication
464 Figure 2 as "the floor is too high" — is the only rule that invents a class
on `split_grain_outlier.jpeg`, where one fill class was drawn and two marks are
crossed by a rule. Adding an absolute support of three refuses classes the
existing fixture routes and gives three different answers to one drawing at
three scales. Conditioning on the shape reaches wrong = 0 and leaves every
`twin_scatter` rendering answering exactly as it did.

## What changed

| | before | v9.16 |
|---|---|---|
| the fill split | one, over the whole panel | one per RESOLVED shape, over that shape's marks |
| the panel-wide split | what routed every mark | recorded as a diagnostic, routes nothing |
| a shape declared with ONE fill | named from the manifest and stamped `MEASURED_MARKER_SHAPE_FILL` | refused `MARKER_FILL_DECLARED_NOT_MEASURED` |
| `_split` on identical values | separated, with `between = 0.0` | one class |
| `Routing_Evidence_SHA256` | 18 fields | 29 — the group's threshold, spread, counts, floor, verdict and this mark's margin |
| `scatter_points.csv` | 33 columns | 44 |
| SCATTER's `METHOD_CONTRACT` | no routed pair | `MEASURED_MARKER_SHAPE_FILL/POINT_CLOUD_ASSOCIATION` |

## What changed for a run you already have

**Every `scatter_points.csv` written before v9.16 is refused.** Its rows carry
neither the eleven group columns nor the hashes over them, so
`Routing_Evidence_SHA256` and `Point_Record_SHA256` both differ and
`scatter_points.verify_artifact` reports every row. There is no back-fill and
there deliberately cannot be one: the group a mark's fill was decided in is a
measurement over the OTHER marks of its shape, and a script that recomputed it
from a stored row would be inventing the evidence the columns exist to carry.
Re-run the panel.

**A panel whose axis manifest declares one fill for a shape now reads nothing on
that shape.** Before v9.16 those marks were named from the manifest and carried
an identity method whose name says the ink decided. What they need is a
provenance method that says "shape measured, fill declared" with its own
reviewer contract and its own verifier; until that exists they are refused.
A panel that declares two fills per shape is unaffected.

**Values from a routed panel finalize for the first time.** The pair
`MEASURED_MARKER_SHAPE_FILL/POINT_CLOUD_ASSOCIATION` was missing from
`provenance.METHOD_CONTRACT["SCATTER"]`, so any routed value reaching
`method_contract_failures` would have been withheld for a method its reader had
in fact produced. Nothing had reached it: the finalizer's scatter gate was
called by `method_contract_failures` and exercised by no scenario, which is why
removing that call broke nothing. Both are fixed here, and both have a scenario
that dies when they are reverted.

Panels with no `axis_manifest.csv` do not take the routed reader at all and are
byte-for-byte unaffected.


# v9.17: the point file and the raster have to be the same SET

## Why

Three things v9.16 shipped were narrower than they read.

**The raster check compared row by row.** `current_evidence_failures` found each
row's own nearest current mark, independently. Nothing asked whether ONE mark had
answered for TWO rows, and nothing asked whether a mark the raster routes had a
row at all. So a producer could drop mark B, write mark A's row twice, re-derive
both hashes, recompute the association over the file it had just made and the
file hash over that — and every check in this package agreed. Both rows sat on a
real marker. The cloud was not the figure's.

**The check asked the panel-wide split.** v9.16 moved routing to a per-shape fill
split and left `SPLIT_GONE` reading `fill_split["separates"]` — the grain it had
just replaced. `split_grain_group_only.jpeg` is the panel that shows the cost:
its panel-wide split does not separate, both of its shape groups do, thirty marks
route correctly, and the verifier rejected all thirty rows.

**The identity method was the widest one that fit.** Every routed mark carried
`MEASURED_MARKER_SHAPE_FILL`, including on a panel of ONE declared shape, where
the shape came off the manifest and only the fill was read from the ink. A
method's name is a claim about what was measured and R0 is the tier that can be
finalized, so the claim has to be the narrow true one.

## What changed

| | v9.16 | v9.17 |
|---|---|---|
| rows against current marks | each row's nearest, independently | minimum-cost maximum ONE-TO-ONE matching |
| a mark the file omits | not looked for | `ROUTED_MARK_MISSING_FROM_ARTIFACT` |
| two rows that are one point | not looked for | `DUPLICATE_POINT_RECORD`, in the raster check AND in `verify_artifact` |
| matching population | routed marks only | every `SINGLE_MARKER` candidate, so a lost group reads as `SPLIT_GONE` and not as `NO_MARK_NOW` |
| `THE_PANEL_NO_LONGER_SEPARATES` | panel-wide fill split | the row's own shape group |
| identity, one shape / two fills | `MEASURED_MARKER_SHAPE_FILL` | `MEASURED_MARKER_FILL` |
| identity, shape declared with one fill | refused `MARKER_FILL_DECLARED_NOT_MEASURED` | `MEASURED_MARKER_SHAPE`, `Marker_Fill` blank |
| identity, one series | refused | `DECLARED_SINGLE_SERIES` |
| SCATTER's `METHOD_CONTRACT` | one routed pair | all four |
| the finalizer's scatter gate | keyed on one identity name | keyed on `scatter_points.IDENTITY_METHODS` |

## What changed for a run you already have

**A v9.16 `scatter_points.csv` still verifies, and its rows may now carry a
different method.** The columns and hashes are unchanged, so an existing file is
not refused by this release — but a panel of one declared shape re-run under
v9.17 writes `MEASURED_MARKER_FILL` where it wrote `MEASURED_MARKER_SHAPE_FILL`,
and the value rows built from it change with it. Both are R0 and both are in
SCATTER's contract, so nothing is withheld either way; the difference is what the
row claims, which is the point.

**A shape declared with one fill now produces points where v9.16 produced
none.** Those marks are named by a shape the ink was measured on, and their
`Marker_Fill` is blank because nothing measured it. If you have a v9.16 run whose
panel came back with `MARKER_FILL_DECLARED_NOT_MEASURED` on every mark of a
shape, re-run it.

**A file that omitted or duplicated a point is now refused.** No back-fill: the
fix is to re-run the panel, because the missing point's evidence was never
written down.

Panels with no `axis_manifest.csv` are still byte-for-byte unaffected.

## 464 Figure 2

`forward_test_464_scatter.py` no longer prints a fixed conclusion. It reports the
panel-wide diagnostic, each shape's own group, the routed count by series and the
unresolved count by reason, and its verdict follows the count it observed. Its
docstring says what is true: v9.15 measured a negative on the pinned clip under a
grain this package no longer uses, and **the clip has not been measured under the
per-shape grain**. A non-zero routed count would still not make it a positive
forward test — that needs a human-reviewed marker truth file bound to the clip's
SHA-256, and there is none.
