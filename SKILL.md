---
name: figure-digitization-triage
description: "Plan, run and QC graph-only data extraction for a systematic review or meta-analysis: caption triage, typed plans, declared readers, a factorial gate, one-page decision bundles, and human approval before anything is pooled."
---

# Figure digitization triage

Use this when a study reports its outcome only as a graph and the numbers have
to be recovered, at a scale where doing it by hand once per paper is not a
protocol. It is a pipeline, not a helper: the point is that the number which
ends up in a meta-analysis can be traced to a raster, a calibration, a reader
version, an environment and a person who looked at the picture and said yes.

## Get the code

Every script named below lives in the repository, not in this skill:
https://github.com/hpend2373/figure-digitization-triage (branch
`approved-claude-checks` until it is merged into `main`). Clone it and run from
the clone; `python3 test_*.py` there is the check that the clone is whole. The
`kernel.py` and `test_kernel.py` that older copies of this skill carried are in
the repository too, with the rest of the pipeline built around them.

## Run it

```
INPUT      one extraction-plan JSON  (schema figure-digitization-triage/extraction-plan/1)
COMPILE    python3 compile_plan.py PLAN.json MANIFESTS/ --file-root .
RUN        python3 run_batch.py MANIFESTS/ OUT/ --file-root . [--doc-root PDFS/]  -> MACHINE_QC_PASSED
REVIEW     for every row of OUT/review_queue.csv, open what its Review_Mode names
           (OVERLAY -> Overlay_File, WPD_ONLY -> WPD_Project_File in WebPlotDigitizer),
           then fill Review_ID / Decision / Reviewer_ID / Reviewed_At in value_review.csv
FINALIZE   python3 finalize_batch.py OUT/ --review value_review.csv   -> FINALIZED
```

Reviewing is a branch, not a single instruction. `Review_Mode` says what the
run produced for this panel and therefore what to look at:

| `Review_Mode` | open | approve only if |
|---|---|---|
| `OVERLAY` | `Overlay_File` | every cross sits on the mark a reader would give it, and none is missed |
| `WPD_ONLY` | `WPD_Project_File`, in WebPlotDigitizer | the marks re-derive the values in the row |
| `BAR_MONO_GEOMETRY` | `geometry-review/index.html` — the panel picture, then every row crop | the drawn axis lines fall on the printed tick labels, and each bar's marked top and cap are where you would put them |
| `BAR_MONO_GEOMETRY_RESOLVED` | the same, plus `geometry-review/identity__<Panel_ID>.csv` and the `geometry-review/evidence__*` files it cites | all of the above, **and** each resolution's evidence really names that series |
| anything else, or the named file is absent | — | **do not approve.** The finalizer refuses it anyway (`REVIEW_MODE_UNKNOWN` / `REVIEW_ARTIFACT_MISSING`) |

`--doc-root` is where the source PDFs are when they are not under `--file-root`
(a run folder holds crops and rasters; the papers usually sit in a library folder
of their own). A `Source_File` is then a bare file name, looked up in that folder
or one level below it, and its SHA-256 is still checked; a name carrying a path,
or a link that leads out of the folder, is refused rather than followed. Without
it every document is `SOURCE_DOCUMENT_FILE_NOT_FOUND`, which is a setting, not a
finding.

`WPD_ONLY` is uncommon: it means the picture could not be drawn, which never
fails a panel that produced values but does change what a reviewer has to open.

The confirmation columns are separate claims, and the finalizer requires the
ones the mode declares: `Marks_Checked` always, plus `Axis_Labels_Checked` and
`Calibration_Checked` for the two geometry modes, plus `Identity_Checked` for
the resolved one. Write `CONFIRMED`; blank is not confirmed and `APPROVED` alone
is a signature on a filename.

**Three questions per cell, not two.** `Identity_Method` says how the SERIES was
named, `Value_Method` how the NUMBER was got, and `Dispersion_Method` how the
ERROR BAR was got — the last one decides the weight in a continuous
meta-analysis, and a cell whose mean came off the ink and whose cap no stem
connects to it is not a measured cell. The review tier is the worst of the three,
derived where it is needed and written into no file.

**And one more confirmation, asked by the VALUES rather than by the mode.** `Inference_Cells`
on the queue row is how many of this panel's cells had their series reasoned to
instead of measured — named by elimination, or matched against a fill prototype
formed elsewhere in the figure. When it is not zero, the same decision row also
needs `Inference_Checked=CONFIRMED`, whatever mode the panel is in. The overlay
stars those marks (`*`) and counts them in its footer; on a `BAR_MONO_GEOMETRY`
panel they are the bars whose `Auto_Fill_Pattern` came from another group's
prototypes. The number is measured; the row heading is not, and the row heading
decides which column of the analysis the number lands in — `Marks_Checked` says
the marks are in the right places, which is a different sentence.

A cell whose NUMBER was reconstructed goes one grain finer — interpolated across
a stretch the ink does not cross, or taken from the edge of a run too thick to be
one stroke. One wrong cell in twenty does not show up in a panel-level answer, so
each one is asked about by name in `inference-review/inference__<Panel_ID>.csv`:

    python3 finalize_batch.py OUT/ --template     # writes both review files
    # fill Reviewer_ID / Inference_Confirmed / Reviewed_At for EVERY row of
    # inference_review.csv - CONFIRMED or REJECTED
    python3 finalize_batch.py OUT/ --review value_review.csv

`--template` pre-fills `Inference_ID` from the run, so nobody types a hash. The
contract is an exact set: a missing answer, two answers for one cell, or an
answer for a cell this run did not produce holds the whole panel. `REJECTED` is
an answer — it drops that one value and keeps the rest, and the finalize stamp
counts them in `Values_Inference_Rejected`.

**Look at the picture, not the pixel numbers.** Beside each row the run writes
one crop — `inference-review/context__<Panel_ID>__<Cell_Key>.png`, registered in
`panel_artifacts.csv` against that row's `Inference_ID` — showing the stretch of
figure between the two supporting columns, each support in blue, and the column
and row where the value was placed in red. A value sitting outside its own two
supports is the defect the picture exists for. The finalizer refuses a panel
whose reconstructed cell has no such crop: the row alone gives the supports as
pixel coordinates, and confirming those against a printed figure by eye is
arithmetic nobody can check.

**Before a person starts, run the preflight.**

    python3 review_preflight.py OUT/ --review value_review.csv

It lists every cell that will be asked about and why, checks that each one has
its manifest row and its picture, checks the answers for blanks, duplicates and
answers to questions this run did not ask, and — with `--second FILE` — compares
two independent reviewers cell by cell. It prints what the finalizer WOULD say
first, by calling the finalizer's own decision function rather than a second
implementation of it, so a bundle the preflight calls clean is not one
`finalize_batch.py` then refuses. Pass `--manifests DIR` when the run has been
moved, exactly as you would to the finalizer. **Its exit code is the finalizer's
answer**: 0 if the run would finalize, 2 if it would not. A reconstruction a
person correctly REJECTED is a review done right — the run finalizes without that
cell — so it is printed as `EXCLUDED` and does not fail the preflight; use
`--require-all-values` when a batch is only acceptable whole. It writes nothing
and signs nothing: the
confirmations are a person's claim about what they saw, and a program filling one
in is the failure this whole package is built to prevent.

**Values no signature can finalize are work, not a footnote.**
`method_blocked_cells.csv` is written by the RUN, before anybody reviews: one row
per cell whose number was not read off the ink (`FIT_FALLBACK`,
`EXTRAPOLATED_CURVE_INK`, `NONLOCAL_INTERPOLATION`, or a reader that says
nothing), with `Cell_State=MODEL_ESTIMATE_ONLY`, `Next_Action=MANUAL_REDIGITIZATION`
and the raster to re-read it from. `Values_Method_Blocked` on `run_stamp.json` is
the count. The panel still goes to review — its other cells stand — but nobody
has to discover the refusal from a number on a finalize stamp after signing.

The axis question is the one worth being slow about. If a tick VALUE was typed
wrong — a printed 30 entered as 3 — every bar in the panel is ten times out
TOGETHER, no arithmetic can see it, and the panel picture is the only place it
shows.

**A bar whose fill could not be sampled.** A monochrome series is identified by
its FILL, and a bar too short to have an interior (fifteen pixels, say) has a
mean, an SE and no measurable fill. Its cell is queued, not guessed. To supply
the identity, read the row out of `OUT/mono_bar_geometry.csv` and add a line to
`MANIFESTS/identity_resolution.csv` — copying its `Geometry_Row_SHA256`, naming
the series, and recording the evidence (`LEGEND_DECLARED` for a legend crop,
`TEXT_DECLARED` for a sentence, `REVIEWER_INSPECTION` for your own reading,
which needs a Note saying what you saw) — then run again. The file is optional
and most batches have none. It may only supply an identity the reader could not
measure: naming a bar the reader named itself refuses the whole panel.

Paths in the queue and in the values are recorded **relative to the run
directory**, so a run can be moved or handed to somebody else with its
provenance intact. Resolve them against the run directory, not the working one.

**Success** is `OUT/figure_values_accepted.csv` beside an
`OUT/finalize_stamp.json` whose `Status` is `FINALIZED` and whose
`Accepted_SHA256` is the hash of that file. Nothing else is a result.

**Failure states, and what each means**

| where | status | means |
|---|---|---|
| compile | problems returned, no manifests written | the plan is wrong; fix the plan |
| run | `MANIFEST_REJECTED` | the manifests contradict each other or the files |
| run | `INPUT_LOAD_FAILED` | a manifest could not be read at all |
| run | `DEMO_OUTPUT_REFUSED` | the reviewer registry is a demo identity |
| run | `GEOMETRY_REVIEW_FAILED` | a BAR_MONO review bundle could not be written; nothing is reviewable |
| run | `INTERNAL_ERROR` | a reader has a defect; the whole batch stops |
| run | `RAN` | finished — read `run_stamp.json` for the verdict |
| finalize | `NOTHING_APPROVED` | no valid approval; the default |
| finalize | `RUN_NOT_FINALIZABLE` | not a completed ATTESTED run |
| finalize | `RUN_ARTIFACT_MODIFIED` | something changed after the run |
| finalize | `FINALIZED` | the only state that produces poolable values |

**Never**

- write the eleven manifests by hand — that is what `compile_plan.py` is for,
  and hand-written manifests are where two files quietly disagree
- pool `figure_values_machine_qc.csv` — machine QC finding nothing wrong is a
  different claim from anybody having looked at where the marks landed
- treat a `DEMO_ONLY` run as data
- add a rule keyed on a publication ID; every check here is keyed on a declared
  data type or a declared dimension, and a per-paper exception is a defect

## Files

```
compile_plan.py     one typed plan  -> eleven manifests (+ the optional axis and supplied-readings ones)
run_batch.py        manifests       -> values + review queue + artifact ledger
finalize_batch.py   decisions       -> figure_values_accepted.csv
grid_engine.py      the universal factorial gate
kernel.py           the field-level checks the gate is built from
mark_readers.py     readers for line, marker, box/violin and scatter panels
bar_reader.py       colour and monochrome bar readers
review_overlay.py   the picture a person judges
*_TEMPLATE.csv      every schema, generated from its column function

bundle_items.py     census problems -> one question each, measured or proposed
bundle_page.py      the decision bundle: one page, a proposal on every line
bundle_page.js      what counts as an answer on it (seen / approved / held)
bundle_route.py     the page's answers -> each gate's answer file, all or nothing
census_copy.py      the gates on a copy of the run, census before and after
record_outcomes.py  a drawn panel's outcome name, or "not a target" (R4)
record_legends.py   which panels of one figure share a printed legend
clip_frames.py      a drawn frame past the picture's edge, cut back on both cards
rehash_moved_pages.py  a row moved to the next page, still carrying the old page's hash
cross_check.py      a second check that never saw the proposals; agreed items written without the person
move_panels.py      drawn panels credited to the wrong figure, moved with their boxes, cards and names
supplied_readings_TEMPLATE.csv  the points an AI agent placed on a MANUAL panel (G01, read by run_batch)

panel_to_page.py    drawn panels (200 DPI crop boxes) -> 600 DPI rasters and regions
propose_run.py      geometry / identity proposals on those regions, budgeted and resumable;
                    `reframe` re-proposes identity on a frame someone redrew
axis_series_page.py the axis-and-series page: both proposals on one card, "as proposed" preselected
axis_series_page.js what counts as an answer on it (the two pages' own verdictOf); `recheck`
axis_series_recheck.mjs  the answers that came back, rebuilt from the page's proposals, row by row
route_axis_series.py  its answers -> record_geometry / record_identity answers (registered names,
                    a person's rename); `merge` appends the new proposals to the run's proposal files
```

Everything below is the protocol: what each rule exists to prevent, stated
against the defect that produced it.


## Record HOW the mark was read

Two geometric facts decide whether a digitized number is right, and neither is
visible in the finished CSV unless it is recorded.

**A vector bar's data coordinate is the centre of its stroke.** The colour fill
stops inside the outline, so reading the fill edge puts every mean low by half
the stroke width — on a 4 px stroke that was 1.2 units on a 150-unit axis, in the
same direction on all 72 bars of one figure. Record `Bar_Top_Definition`:
`OUTLINE_CENTER` / `FILL_EDGE` / `MARKER_CENTER` / `NOT_A_BAR` / `FILL_ONLY`. `FILL_EDGE` is
flagged, not forbidden — declare it and the bias is auditable. `FILL_ONLY` is a bar
drawn with no outline stroke at all: its fill edge is its data coordinate, so there
is no half-stroke to lose and the gate takes it. The released bar reader measures an
outline centre, so a `FILL_ONLY` card is read by a person or agent
(`Read_Route=MANUAL`; `record_identity` refuses it on AUTO). Added on 2026-10-21 for
nine panels whose bars have no stroke (the person's decision E04).

`NOT_A_BAR`, not `NOT_APPLICABLE`: the latter is a null token, so `fig_is_blank`
would read a filled-in answer as an empty cell. No controlled vocabulary in this
kernel may contain a value `fig_is_blank` swallows, and a scenario asserts it.

**Significance glyphs sit where the error-bar cap sits.** `@`, `*`, `#` and
comparison brackets are the same colour as the whisker and float directly above
it. Accepting the topmost mark as the cap inflated dispersion by **+18 units
against a true SD of 3–5**. A cap counts only when a vertical stem physically
connects it to the mark. Record `Errorbar_Stem_Confirmed` TRUE/FALSE; a
dispersion recorded without confirmation fails the gate.

Both are required on `Extraction_Method=DIGITIZED` rows and skipped on
`TRANSCRIBED` ones, so `Extraction_Method` is itself a required column — a
template that omits it makes both checks inert.

## Inventory the physical figure before any outcome-specific split

Completeness is a different grain from extraction.  `Figure_ID` may be split by
outcome, sex, axis or reader configuration; it therefore cannot prove that the
publisher's physical figure was covered.  A set of virtual figures can each say
`2/2 MATCHED` while most of the original raster is absent.

Do not write the CSVs by hand.  Write one `extraction-plan` JSON per
publication and run `compile_plan.py`: hashes, figure rows and unit
calibrations are derived from the plan rather than retyped, which is where
several of this package's shipped defects came from.  `plan_397.json` is a
worked example.  The four source manifests below are what the compiler emits,
and what follows describes what the plan has to say.

Create four source manifests before creating any reader row:

    reviewer_registry.csv       one row per person allowed to attest an inventory
    source_document_manifest.csv one row per main article/supplement/chapter
    source_figure_manifest.csv  one row per physical publisher figure
    source_panel_inventory.csv  one row per visually distinct source subpanel

Use an immutable `Source_Document_ID` and record the complete target article or
supplement page range.  Its `Observed_Figure_Count` must equal the number of
physical source figures attached to it, which prevents an entire figure from
vanishing before the panel check begins.  `Source_File_SHA256` is the sha256 of
the WHOLE document file, whatever range `Article_Page_Range` names, or the literal
`NOT_HELD` when the corpus does not have the file — a figure inventory is a claim
about one article, and without the digest it is a claim about a filename that a
preprint and its version of record both satisfy.  Saying `NOT_HELD` about a file
that IS under `--file-root` is refused, and the run stamp records
`Source_Document_Bytes_Bound` so a NOT_HELD inventory cannot be read back later
as a byte-bound one.  Then use an immutable
`Source_Figure_ID` such as `PMID123_MAIN_FIG2`.  Count panels on the
full raster, not from the caption.  Count plots, photographs, schematics and
table/inset subpanels before deciding whether they contain target data.  A legend
or colour bar is not a panel, while an inset with its own independent content is.
If the source supplies no panel letters, assign stable reading-order labels
`P01`, `P02`, ... .  Record the count method, and the `Reviewer_ID` of the person
who did the counting.

`run_batch.py` stops at `figure_values_machine_qc.csv`.  Nothing it writes is
poolable.  Each passing panel gets one `review_queue.csv` row whose
`Review_Mode` names the artifact a reviewer must open — almost always
`review/<Panel_ID>_overlay.png`, the panel as printed with every mark the reader
placed drawn on it, and `WPD_ONLY` with the project when that picture could not
be drawn.  Every such row carries `Review_Subject_SHA256`: a hash over
the run row, every manifest, the environment record, every machine-QC value of
that panel with its `Cell_Key`, **and every artifact the panel produced**
(overlay, WPD project, raw marks, point files), each by content.  A person fills
`Review_ID`, `Decision`, `Reviewer_ID` and `Reviewed_At` in `value_review.csv`,
and `finalize_batch.py` writes `figure_values_accepted.csv` for the approved
panels only.  Re-run with different code and the old approvals are
`APPROVAL_STALE`, not inherited.

The finalizer re-hashes before it reads a single decision: the four run CSVs and
`panel_artifacts.csv` against `Output_SHA256` in the run stamp, the reviewer
registry against `Reviewer_Registry_SHA256`, and every artifact in the ledger
against its recorded hash.  Any mismatch is `RUN_ARTIFACT_MODIFIED` and no
accepted file is written.  This is what makes an approval a statement about a
specific picture: swapping `review/P1_overlay.png` after the fact used to
finalize, because the numbers were verified and the picture was not.

Whether a run may produce poolable values is decided by `Reviewer_Record_Type`
(`HUMAN` or `DEMO_IDENTITY`) on the rows the inventory names, not by a flag at
the call site — a flag does not travel with the manifests.  A run resting on a
`DEMO_IDENTITY` reviewer is DEMO_ONLY wherever it is launched from: it may
produce a queue, a coverage ledger and a list of QC failures, but if it reaches
the end holding values the gate accepted it writes none of them and returns
`DEMO_OUTPUT_REFUSED`.  `--demo-only` demotes a real registry; nothing promotes
a demo one.  Every stamp records `Run_Mode`.

That ID is a foreign key into `reviewer_registry.csv`, which holds the name, a
contact (EMAIL or a checksum-valid ORCID) and a `Human_Attestation` — a declared
enum, not a cryptographic signature: it records that a person typed
HUMAN_CONFIRMED next to a contact, which buys traceability, not proof.  Register
each extractor once.  Names are compared after NFKC normalization on Unicode
alphanumerics, so `김민엽` and `李明` are names like any other; what is refused is a
row where nobody contactable stands behind the count.  Machine
segmentation may propose boxes, but `Inventory_Status=VISUALLY_VERIFIED` is the
gate because captions and layout detectors both miss unlabeled panels.

Every visible panel receives exactly one disposition:

    AUTO_DIGITIZE          MANUAL_DIGITIZE       NO_READER_AVAILABLE
    ASSOCIATION_EXTRACT    BINARY_EXTRACT         NO_SUMMARY_STATISTIC
    NON_TARGET_OUTCOME     NOT_DATA               DUPLICATE_OR_DECORATIVE
    UNRESOLVED

`UNRESOLVED` and an unverified inventory block the run.  Non-target and not-data
panels are retained as closed rows rather than deleted.  Target panels routed to
automatic extraction must link to at least one `panel_manifest.csv` row through
`Source_Panel_ID`; multiple run panels may link to one physical panel when one
axes region yields several units.  Reader-unavailable and manual panels need no
dummy geometry: the batch emits them into `manual_queue.csv` from the source
inventory itself.

The mandatory equality is:

    Observed_Panel_Count == number of source_panel_inventory rows

It is evaluated only in the `Source_Figure_ID` namespace.  Counts on virtual
`Figure_ID` rows cannot satisfy it.  The run emits `source_panel_coverage.csv`,
one row per physical panel, so publication coverage and value acceptance remain
separate claims.  `figure_values_accepted.csv` says which numbers may be pooled;
it never says every source panel was considered.

For a large corpus, use two passes: (1) inventory every physical figure and close
or route every panel, then (2) configure readers only for the routed target
panels.  This bounds manual work without allowing a reader's capability to
determine what enters the evidence base.

## Reconcile panels against the worklist, per figure

A caption-derived panel list can only miss panels, never invent them, so the
worklist count is a lower bound and the screen is the truth. On ID 323 Figure 2
the worklist carried five panels; the figure has six, and PAP was absent
entirely — a whole outcome that would have vanished silently.

Record `Observed_Panel_Count`, `Worklist_Panel_Count`, `Unlisted_Panels` and
`Panel_Reconciliation_Status`. The status is fully determined by the counts:

    observed == worklist  ->  MATCHED
    observed >  worklist  ->  UNLISTED_PANELS_FOUND   (name them)
    observed <  worklist  ->  WORKLIST_OVERCOUNTS

Anything else is a contradiction, not a judgement call. Both counts are positive
integers, and every row of one `Publication_ID x Figure_Number` must carry the
same pair — two rows disagreeing about how many panels a figure has means it was
counted twice with different answers. Blank or `PENDING` fails the gate, so no
figure reaches master unless somebody counted its panels on screen.

## A non-answer is not an answer

`Errorbar_Definition_Source` exists to carry the source's own wording. A blank-only
check cannot tell an empty cell from `"TBD"`, `"assumed SE"` or
`"HARNESS PLACEHOLDER - unresolved"`, and all of those passed the gate while
`Dispersion_Type=SE` sat beside them — a guess, presented as a reading, on a field
where SD/SE confusion scales the meta-analytic weight by sqrt(n).
`UNRESOLVED_ERRORBAR_DEFINITION` blocks the placeholder vocabulary. Quote the
source, or record `NO_ERRORBAR` and keep the row out of the pooled variance.

The opposite mistake is as costly: a word that names a dispersion is not always
a statement about the bars. "HRV ... derived from heart period data using the
standard deviation of R-R intervals" names how a plotted variable (SDNN) was
computed; read as a definition, it made a figure whose caption goes on to say
"mean ± SEM" an SD figure, and the error-bar gate then refused the SEM a person
found, because the figure no longer looked undefined. `caption_fulltext` skips a
match that a deriving verb ("using", "calculated as", "defined as") puts in
front of and an "of" follows.

The same logic applies to `Unlisted_Panels`: matching panel COUNTS are not
agreement. Two rows of one figure that both say "6 of 5" while one names PAP and
the other MAP describe different figures, so the normalized name sets must match
too (`UNLISTED_PANELS_INCONSISTENT_IN_FIGURE`). Normalized, not literal — "pap ,
map" and "MAP;PAP" are the same answer, and a consistency check that says
otherwise has become a spelling check.

## Bundle what is left, so a person decides only what needs a person

At a hundred publications the census of the plans (`make_plan.py` ->
`compile_plan.py` -> `run_batch.py`, read for manifest problems only) leaves a
few hundred open questions: a figure nobody has disposed of, a drawn panel whose
outcome has no name, a monochrome bar whose fill was never declared, a marker
shape nobody named, a tick pair that lands outside its panel. Asked one page at a
time, each costs a person a context switch; asked without a proposal, each costs
them the reading as well. The decision bundle asks all of them on one page, and
**every line carries a proposal**, so the person's work shrinks to the lines
where the proposal is wrong.

    census_copy.py / any census   man_<pub>/ manifests + out_<pub>/manifest_problems.csv
      | bundle_items.py           one question per problem code; measures what the
      |                           raster can answer; the rest needs a proposal from
      |                           someone who LOOKED -> exit 2 and WORK/todo.json
      v                           until every question has one
    spec.json
      | bundle_page.py            one local page: picture, current state, options,
      v                           proposal, reason, who proposed it
    bundle_answers.csv            written by the page; nothing on it is pre-selected
      | bundle_route.py           answers -> one answer file per existing gate,
      v                           all or nothing
    *_answers.csv, unrouted.csv, held.csv, route_log.json
      | census_copy.py            the gates write to a COPY of the run; the same
      v                           census before and after
    compare.json                  what the answers WOULD change, per problem code
      | record_dispositions.py / record_errorbar.py / record_outcomes.py /
      | record_legends.py / record_identity.py --replace / record_geometry.py --replace
      v                           on the real run, --when = the day it was decided
    the next census

The questions, by problem code (`bundle_items.py`):

| section | problem | the question | gate |
|---|---|---|---|
| X | `SOURCE_PANEL_UNRESOLVED`, `SOURCE_PANEL_RUN_LINK_MISSING` | what to do with this figure | `record_dispositions` |
| C | `MISSING_TARGET_OUTCOME_LABEL` on a drawn panel | the outcome's name and unit, or not a target | `record_outcomes` |
| F | `MISSING_SERIES_DISCRIMINANT`, monochrome bars | each series' fill | `record_identity` |
| M | `MISSING_SERIES_DISCRIMINANT`, lines and markers | each series' marker | `record_identity` |
| L | `IDENTITY_DOMAIN_FILL_CONFLICT` | one figure, two legends | `record_legends`, or `record_identity` (MANUAL) |
| K | `CALIBRATION_OUTSIDE_PANEL` | move the tick pair, or the box | `record_geometry` (the box: none yet) |

**Measure what can be measured; ask for the rest.** K looks for tick marks
within 12 px of the pair (spine ticks, gridlines) and proposes PAIRS when every
pair moves onto one inside the panel, BOX otherwise - and BOX is a path still to
build, because neither card gate takes a box from an answer (below). F measures each bar's dark
fraction against the reader's own bands (`FILL_BANDS` must equal
`mark_readers._FILL_BANDS`, and a scenario holds them together): one band is a
proposal, mixed bands are MANUAL. The options are worded in the reader's terms,
because the reader's terms are not a person's: a bar filled white looks "solid"
and is OPEN to the reader, and a person who answered SOLID for black and white
bars meant two plain fills, which in one series is MANUAL. Everything else needs someone to look at the
figure, and `bundle_items.py` writes no spec while any question lacks a
proposal - the questions, the measurements and the pictures go to
`WORK/todo.json` for whoever (a person or an agent) writes them. A proposal for a
question this census did not ask is refused (`STALE_PROPOSAL`). Work that is not
a question - drawing the panels of a PARTIAL figure, a RECROP, a REDRAW, naming an
undrawn panel - goes into the spec's notes as a person's task.

**Undrawn panels are drawn on the panel page, with a proposal on every box.**
`panel_page.py` takes a queue (`pid,fig,axes`) and a proposals file (one JSON line
per figure: crop size and SHA-256, boxes with kind and count, and a note from
whoever proposed them); `record_panels.py` records the answers into
`seg/panel_decisions.csv`. A drawing answers the disposition that asked for it:
`make_plan.py` takes a PARTIAL figure drawn on or after the day of its disposition,
and a REDRAW figure drawn on a later day, as an ordinary figure standing on the
drawn panels, and notes on the figure which disposition the drawing answered
(`drawing_answers`). The panels a PARTIAL figure does not read are drawn as
"no values to read", or - when they hold data that is not a target - drawn with
their kind and closed through `record_outcomes.py` as NON_TARGET. A RECROP is not
answered by a drawing: the crop itself was judged wrong. The records keep days,
not hours, so a REDRAW drawing from the decision's own day is not taken; it may
be the drawing that was refused.

**Three kinds of answer, and `bundle_page.js` decides which.** The page moves
values; the rules are a pure module with its own node suite, as on every other
review page.

- **seen** - the person pressed "직접 보았다" (I looked myself): `Seen_By_Person=1`.
- **approved observation** - the person chose the proposal without looking:
  `Seen_By_Person=0`, `Observed_By` = whoever made the proposal (planted on the
  item), `Approval_Ref` = this answers file, the approver and the date. The gates
  accept it as an approval (`approval.py`) and refuse it when the observer is the
  approver (`OBSERVER_IS_APPROVER`).
- **held** - HOLD writes nothing and claims nothing.

An answer that differs from the proposal is not an answer without "seen": a
choice nobody looked at is nobody's observation - the proposer did not see it
that way, and the person did not see it. A rewritten name (EDIT) is text a person
typed, so it is always seen. "Fill with the proposals" fills empty lines only;
overwriting a line the person chose differently would turn it into an approval
they never gave. The spec itself is refused before a page is built when a line
has no proposal (`NO_PROPOSAL`), no reason (`NO_REASON`) or nobody who proposed
it (`NO_OBSERVER`).

**Every answer names the question it answers.** The CSV carries `Item_SHA256`
(target, current state, options, proposal, reason, proposer) and `Image_SHA256`
(the picture shown). `bundle_route.py` refuses an answer to a page built from
another census (`STALE_ITEM`), an item answered twice, an unseen change
(`UNSEEN_CHANGE`), an approval naming someone other than the proposer
(`OBSERVER_MISMATCH`), an unseen EDIT, an edit to a card that does not exist
(`MISSING_CARD`), two items setting one field differently
(`CONFLICTING_EFFECTS`), and one card touched by a seen answer and an approval,
or by two people (`MIXED_PROVENANCE`) - a card row carries one provenance. **One
refused row and no gate file is written**: a bundle recorded half-way is worse
than one not recorded. A card file named on the command line but absent stops
it, rather than turning every card answer into `MISSING_CARD`.

**A card answer can only change what the gate takes.** `record_identity` and
`record_geometry` rebuild the card from their PROPOSAL row and lay on it only the
fields a person gives - the series, the factors, the read route; the verdict, the
tick values and pairs. A box, an axis region or anything else set in an answer
is silently dropped, so `bundle_page.CARD_TAKES` lists what each gate copies, a
scenario reads those names off the two gates' code, the page refuses an option
that sets anything else (`BAD_EFFECT`) and the router refuses it again
(`FIELD_NOT_TAKEN`). The same rebuild is why a geometry card on a frame a person
drew (`Frame_Source=DRAWN`) goes with its frame as `Drawn_Frame`: without it the
gate stands the new tick pairs on the READER's frame, and the frame the person
drew is gone while only the pairs were meant to change. Both were found by
recording a real bundle on a copy and diffing the cards - a census of problem
counts did not show either.

**No route is not a route.** An answer whose gate does not exist yet goes to
`unrouted.csv` with what it needs. It is not dropped, and it is not written into
a record where it does not belong. The small fixes (below) stay there: their
answer is the approval, and the tool that does the fix is run by hand.

**A panel's outcome and a figure's legends are records of their own.** A panel a
person reads by hand (`MANUAL_DIGITIZE`), or one in a figure set aside for want of
an error definition, never passes the identity page, so nothing gave it the name
the plan requires of every target panel. `record_outcomes.py` takes, per panel
(`<Draft_ID>_P<n>`, the plan's name), LABEL with the name the paper printed, or
NON_TARGET; `make_plan.py` puts the name on a target panel that is not read
automatically - an automatic panel keeps the name its identity card confirmed -
and closes a NON_TARGET panel as `NON_TARGET_OUTCOME` before it gets a unit. A
guess ("TBD", "unknown", "assumed") is refused as a name: a panel that looks named
and is not is worse than one that is plainly unnamed. A name on a panel the plan
has closed is refused too; reopening it is the figure's disposition's job.
`record_legends.py` takes the legend groups of one figure (`p1,p3|p2`); `make_plan`
gives each group its own `Identity_Domain_ID` (`F_<figure>__L<n>`), so the same
hatching may mean "before bed rest" in panel A and "before diuretic" in panel B
without the fill check stopping the figure. One group is the default and is not
written; a panel in two groups is refused.

**Small fixes are tools, each with the evidence it needs.** `clip_frames.py`
cuts a drawn frame back to the picture (a frame drawn to a region that ends at
the picture's edge can overshoot by a few pixels, and the reader stops on a box
outside the image). It moves both cards together - `make_plan` reads identity
only on the frame geometry stands on - by re-recording them through their own
gates, rehearsed in a temporary folder first; a re-recorded card that differs
from the old one anywhere but the frame and the record's who/when means the
proposal was re-made since, and nothing is written. The card keeps the weaker
provenance: a card that was an approved observation stays one even when a person
saw the clip. `rehash_moved_pages.py` repairs rows the review sheet moved to the
next page before it learned to move the page's hash with the page: it rewrites a
hash only when it is exactly the moved-from page's, and stops on anything else.

**Census on a copy, then record.** `census_copy.py` builds a link tree of the
run, real-copies only the files the gates write, records with the gates
themselves (not a re-implementation of them), and runs the same census before
and after. The run's own gate files are hashed before and after, and a change is
`RUN_CHANGED` - a gate wrote to the run instead of the copy. Any gate refusal
stops it before the second census, and so does a gate that falls over
(`GATE_FAILED`, written to `recorded.json` with the others). What a gate is known
to need is checked before the first census, which takes minutes: error-bar
answers need `--pdf-root` and the run's `errorbar_unstated.csv`. Read `compare.json` - every problem code that
moves, by publication - before the gates touch the real run.

**The page holds publisher figures.** It is a local file for the person
deciding; it is not committed, published or shared.

    python3 bundle_items.py --census CENSUS/ --run RUN --plans PLANS/ --work WORK/ \
        [--proposals proposals.json] --spec WORK/spec.json      # exit 2: WORK/todo.json
    python3 bundle_page.py WORK/spec.json --out bundle.html --items WORK/items.json --root WORK
    # the person answers on bundle.html and saves bundle_answers.csv
    python3 bundle_route.py --items WORK/items.json --answers bundle_answers.csv \
        --identity RUN/seg/identity600/identity_decisions.csv \
        --geometry RUN/seg/geometry600/geometry_decisions.csv --out ROUTED/
    python3 census_copy.py --run RUN --routed ROUTED/ --when YYYY-MM-DD \
        --reviewers reviewers.json --out CHECK/ [--pdf-root PDFS/]
    # outcomes and legends are recorded against the plans they answered
    python3 record_outcomes.py --run RUN --plans PLANS/ --answers ROUTED/outcome_answers.csv --when YYYY-MM-DD
    python3 record_legends.py --run RUN --plans PLANS/ --answers ROUTED/legend_answers.csv --when YYYY-MM-DD
    # small fixes, each approved on the page and run by hand
    python3 clip_frames.py --run RUN --answers clip_answers.csv --when YYYY-MM-DD
    python3 rehash_moved_pages.py --run RUN [--write]

## Drawn panels to axes and series, on one page

A panel drawn on the panel page is a box on a 200 DPI crop. Before `make_plan` can
plan it, it needs a 600 DPI raster, a confirmed geometry (frame and a tick pair)
and a confirmed identity (x positions and labels, series and their marks, outcome
and unit) on the same frame. This is the path from the one to the other, and it
asks the person one thing per panel: look at two pictures and say whether the
proposal is right.

    # 1. 600 DPI, into a NEW folder - nothing of the run changes
    python3 panel_to_page.py --run RUN --decisions RUN/seg/panel_decisions.csv \
        --pdfs RUN/seg/_pdf_locations.json --out RUN/seg/regions600_DATE \
        --verified-at DATE --outcomes RUN/outcome_decisions.csv \
        --pages RUN/pages --doc-root PDFS/ --budget 150 [--resume]
    # 2. reader proposals (call again until "남음 0"; a remote shell that dies at 3 min is why)
    python3 propose_run.py geometry --run RUN --regions RUN/seg/regions600_DATE/panel_regions_600.csv \
        --out RUN/seg/geometry600_DATE --budget 150
    python3 propose_run.py identity --run RUN --regions .../panel_regions_600.csv \
        --geometry RUN/seg/geometry600_DATE/geometry_proposal.csv --out RUN/seg/identity600_DATE --budget 150
    # 3. a proposal on every panel (PROPOSALS.json, schema in axis_series_page.py), then
    python3 propose_run.py reframe --run RUN --geometry .../geometry_proposal.csv \
        --identity RUN/seg/identity600_DATE --frames PROPOSALS.json
    # 4. the page - a local file, it holds publisher figures
    python3 axis_series_page.py --run RUN --geometry RUN/seg/geometry600_DATE \
        --identity RUN/seg/identity600_DATE --proposals PROPOSALS.json --out axis_series.html --date DATE
    # 5. the answers: rebuilt and compared, routed; the new proposals appended - on a COPY first
    node axis_series_recheck.mjs axis_series.html axis_series_answers_DATE.csv
    python3 route_axis_series.py route --answers axis_series_answers_DATE.csv --proposals PROPOSALS.json \
        --geometry RUN/seg/geometry600_DATE --identity RUN/seg/identity600_DATE --out ROUTED/ \
        --reviewers reviewers.json [--rename TYPED=REGISTERED]
    python3 route_axis_series.py merge --run COPY --geometry ... --identity ... \
        --regions .../panel_regions_600.csv --when DAY --write
    python3 record_geometry.py --proposals COPY/seg/geometry600 --answers ROUTED/geometry_answers.csv --when DAY
    python3 record_identity.py --proposals COPY/seg/identity600 --answers ROUTED/identity_answers.csv --when DAY
    # census on the copy, compare, then the same on the run with backups

**Only the panels that need it, from a new folder.** `--verified-at` takes one
panel page's drawings; `--outcomes` leaves out the panels already closed as
NON_TARGET, which would otherwise get proposals and come back to a person. The
rasters, regions and proposals go into dated folders; the run's own
`seg/regions600`, `seg/geometry600` and `seg/identity600` are touched only by
`merge`, with a backup, after the answers.

**Find the inputs; never guess them.** A draft's `Page_Raster` can be the absolute
path of the session that made the run. `--pages` looks for the part after `/pages/`
under the run's page folder and takes it only when its SHA-256 is the draft's
`Page_Raster_SHA256` (`PAGE_RASTER_CHANGED` otherwise). A PDF missing from the
locations file is found by name under `--doc-root` or one folder below it,
compared in NFC because a Mac may store the name decomposed; its SHA-256 is
checked against the draft as always.

**The proposals are written by looking, not by reading numbers.** Whoever writes
PROPOSALS.json (an agent, as a rule) looks at the whole figure and at both
overlays of every panel, and measures on the raster what the picture shows. The
rules that made the 2026-10-16 batch (96 panels, 27 figures) pass both gates:

- **Precedent first.** The same paper's confirmed cards decide the factor names, the
  series names and marks, the outcome naming (a breathing condition or a group in
  the outcome's name, as the paper's other figures have it) and MANUAL. A new
  factor name is taken from the corpus vocabulary before it is invented.
- **The reader's tick values stand when they agree with the print.** When the reader
  refused, or its residual is a few pixels, type the top and bottom values at the
  reader's measured tick rows, or at the tick rows measured on the raster (`rows`).
- **Redraw a frame that is not the plot**: one that takes in the title or the x
  labels, or cuts a group in two. On the axis lines, in whole pixels (the geometry
  gate rounds and the identity proposer truncates, so a .5 frame splits the two
  cards), then `reframe` - `axis_series_page.py` stops on `FRAMES_DISAGREE` otherwise.
- **Not read by the reader** (identity REJECTED, read by a person) when x is a
  measured value per point (correlation scatters, Starling curves, anything on a
  continuous measured axis) or the curve is a dense time course. Name the
  precedent in `say`.
- **Only what is drawn as a series is a series.** Individual lines are not series;
  a mean drawn apart is ("Mean", R6). Series that share colour and marker, or use a
  shape the reader does not know (TRIANGLE_DOWN, STAR, a circle with a cross), are
  MANUAL with a `cue` for each.
- **x is where the marks are**: group centres for bars and boxes, the mean symbol's
  column when means are drawn beside the labels, the data columns when the axis is
  numeric (`GRAVITY_LEVEL` at 0, 0.16, 0.38, 1 G). Measured on the raster - tick
  marks, bar tops, error-bar columns - not from a screenshot.
- **What a person must see goes in `look`**, not into the decision: a figure whose
  values repeat another's, a one-position x axis, a group name taken from the
  caption. Duplicates are closed later as outcomes, not here.
- **SCATTER only when x is a measured value.** Individual points beside a mean, at
  two or three category positions (before/after), are a positional mark: LINE_MONO
  with the mean as the series, as the corpus's 54 such cards have it. SCATTER there
  makes the plan an association and the census charges four codes per panel.
- **Leave `line_style` blank on LINE_MONO.** Its reader matches by marker only, and a
  line style it will not apply stops the plan (`LINE_STYLE_NOT_READ`); series that
  differ only by line style are LINE_MONO_STYLE.

**The page asks to look, and preselects the rest.** Every card opens with "as
proposed" chosen for both parts; "I looked at both pictures" is never preselected,
because choosing is judgement and looking is a witness. A wrong part is switched
to "needs fixing" with a note, or held; those come back in `not_accepted.csv` and
are asked again on a page of their own (`--subset`). "As proposed" exports the
gate row the geometry and identity pages' own `verdictOf` build - the page adds no
rule of its own except emptying a unit the reader read where the figure has none
(`unitBlank`, written into the Note).

**Route all or nothing; merge, then record, on a copy.** `route` refuses an answer
that was not seen, has no name, answers a panel twice, or carries a gate row for a
different panel, reviewer, witness or verdict than the proposal - and then writes
nothing. `merge` refuses a Proposal_ID already in the run, a target that is a link,
a column the target lacks that a new row fills (a column every new row leaves blank -
a decision column the proposer gained after the run's file was written - is left
out), a different picture under the same name, and a backup that already exists. In the 2026-10-16 batch the routed test answers were taken by
both gates for all 96 panels on a copy, and every confirmed identity stood on the
geometry's frame.

## When the answers come back

The page's answers are a person's claim; before anything is written, check that
they answer the questions the page asked, under a name the records know, and find
out what they will change - on a copy.

1. **Rebuild every row.** `node axis_series_recheck.mjs PAGE.html ANSWERS.csv` takes the
   proposals out of the page and rebuilds each "as proposed" gate row with this
   checkout's `verdictOf`; every row must be the same, field for field, and "fix" or
   "hold" rows must carry none. A difference means another page, another proposals
   file or a hand-edited answer. (A page built by an older version may differ for
   that reason alone - rebuild it with this version and compare again.)
2. **Names against the registry.** `route --reviewers` stops on a name the registry
   does not have (`UNREGISTERED_REVIEWER`). The 2026-10-17 answers came in as `miyeop`
   for `minyeop`; the gates write names as typed, so a typo becomes a second person.
   The fix is a person's call, made once (run2: "검토자 이름은 모두 minyeop으로 통일") and
   passed as `--rename miyeop=minyeop`: the answer and its gate row change together,
   the gate row's Note says so, and the downloaded file stays as it was typed.
3. **Merge and record on a copy, then the census.** A link tree of the run with real
   copies of the files `merge` and the two gates write (never a link to a directory
   of the run); `merge --write`, `record_geometry`, `record_identity`; the run's own
   `seg/*600` fingerprints compared before and after; `census_copy.census` on the run
   and the copy, with `--file-root` the run itself (`compile_plan` refuses files that
   resolve outside the file root, and a link tree's files do). On 2026-10-17: 192
   rows, recheck 192/192, both gates 96/96 with nothing refused and no old row
   changed, census 98 -> 70.
4. **The next bundle comes from that copy's census.** What the census still asks is
   the next page (`bundle_items.py` on the copy's census, with proposals): outcome
   names of the panels a person will read, cards the census charged, error
   definitions. Questions no question code covers go in as `extra_items` with an
   effect on an existing gate, or `{"gate": null, "needs": ...}` when no gate takes
   them yet. Answer the page with every proposal (name TEST) in a browser, route it,
   and run `census_copy.py --run COPY --file-root RUN` on top of the first copy: on
   2026-10-17, 56 items, nothing refused, census 70 -> 2 (one RECROP left, a person's).

Rules that came out of that bundle:

- **Names come from the axis title and the panel title**, so a name question shows
  the panel with a margin wide enough for both (`bundle_items.NAME_PAD`).
- **Close a panel whose y values repeat another's.** The same means plotted against a
  second x (calf resistance against burst rate, then against total MSNA) is one
  outcome twice: name the first, close the second as NON_TARGET with the reason.
- **A continuous trace whose stage means are drawn elsewhere with their errors** (a
  14-subject mean time course beside bars of the same stages) is proposed NON_TARGET:
  reading it by hand adds no summary statistic. The person can still name it.
- **"95% confidence intervals" in a caption is not always the error bar.** In a
  caption about regression ("broken lines show the 95% confidence intervals") it is
  the band of a fitted line; the bars are whatever the statistics section says
  ("Data are given as the mean ± SD"). Two such figures read as CI95 in run2.

**Error definitions the old pending list does not know.** `errorbar_unstated.csv` was
made before the panels were counted, so a figure opened later, or one whose caption
a rule misread, used to be `NOT_PENDING`. `record_errorbar --plans PLANS/` (the plan
folder of the current census) also takes:

- a figure the plan is still waiting on - no definition found anywhere (in run2 one
  figure with no bars, NO_ERRORBAR, and one with bars and no definition, DROP);
- a figure whose definition a rule read from the caption or the document, as a
  correction: a figure answer only, the reason in `Note` (`CORRECTION_UNEXPLAINED`),
  and a type other than the reading (`SAME_AS_READING`). The two run2 figures read
  as CI95 from a regression band are of this kind; their statistics sections say SD.

A document-level answer never reaches a figure that came from the plan, and a figure
a person already decided is not pending (that is `--replace`). `census_copy` gives
the gate the census's own plans. `bundle_page` asks a quote only of an answer that
names a dispersion: DROP must not carry one (`record_errorbar` refuses it) and
NO_ERRORBAR needs none, so a bundle can route both.

`make_plan` no longer falls back to the 200 dpi crop when a region's `Raster_600` file
is missing (the 600 dpi boxes then sat on the wrong picture, and the run stopped only at
reading time, `INTERNAL_ERROR`): the panel stays unauthored with `RASTER_600_MISSING`
and the file's path, on the panel and on the figure.

## A second check that did not see the proposal, before the person

On 2026-10-18 the person answered a 54-item bundle, chose the proposal on 53, and
said checks like these should be automated: "이 정도 검사는 ai로 자동화하는 게 좋을 거
같아. 앞으로 그렇게 해주도록". The standing approval they chose: **an item is written
without the person when a second check that never saw the proposal answers it the
same way, with evidence and HIGH confidence; everything else goes to the person.**
`cross_check.py` is that rule.

    spec.json + items.json            (bundle_page.py, as before)
      | cross_check.py brief          question, target, options WITHOUT effects, pictures,
      v                               the review's rules - no proposal, why, facts, now,
    brief.json                        or who proposed (BLINDED, checked by the scenarios)
      | a second agent answers it     choice, HIGH/LOW, evidence (quote + page, a card or
      v                               plan fact, what was measured), a name if it names
    verdicts.json
      | cross_check.py split          agreed + HIGH + evidence -> auto_answers.csv
      v                               the rest -> person_spec.json (with the second
    auto_answers.csv, person_spec.json, cross_check.json      check's answer in its facts)
      | bundle_page.py person_spec.json -> the person answers only those
      | cross_check.py merge          one answers file -> bundle_route.py with the
      v                               ORIGINAL items.json, then census_copy, then the gates

An automatic line is an **approved observation** (`approval`), never a seen one:
`Seen_By_Person=0`, `Observed_By` = whoever proposed it (the item's own, so
`bundle_route` checks it as it checks any approved line), `Verified_By` = the person
who gave the standing approval, `Approval_Ref` = where that approval is, which second
check agreed, and the hash of its verdicts file. Its `Note` carries the second
check's evidence. A name (LABEL) is written as the proposal wrote it, and only when
the second check wrote the same name and unit (case and spacing aside).

Still the person's, however sure both checks are:

- **new paths and code changes** - an item whose target is `fdt:...`, or one marked
  `person_only`;
- **a person's own text** - an EDIT proposal (`bundle_route` refuses an unseen EDIT);
- **disagreement, LOW confidence, no evidence, a different name, a hold, no answer**;
- **an item on the same identity or geometry card as an item the person still has**
  (`SHARED_CARD`): two answer files built from one card row overwrite each other, so a
  card is answered from one side only;
- anything a gate takes only as seen (`record_panels`, the seen-box of any page) -
  those gates never see an approved observation.

`split` stops when the second check has the proposer's name, when the proposer has
the approver's name, when the verdicts do not say who checked, when the standing
approval or its reference is missing, on two answers to one item, on an answer to an
item the brief did not ask, and on a spec and items file from different builds.

What independence means here: the brief carries nothing of the proposal, and the
prompt that starts the second check names what it may open - the brief, the
pictures, the paper's text, the run's records (cards, plans, earlier decisions) - and
what it may not: the spec, the items file, the bundle's own notes and answers. Two
instances of one model are independent in what they saw, not in how they reason; a
habit both share will agree with itself. That is why the evidence is kept on the
line and the person's page shows the second check's answer next to the proposal.

    python3 cross_check.py brief --spec WORK/spec.json --out WORK/brief.json --rules rules.md
    # second check(s): answer WORK/brief.json -> verdicts.json {"verifier": ..., "verdicts": [...]}
    python3 cross_check.py split --spec WORK/spec.json --items WORK/items.json --verdicts verdicts.json \
        --approver NAME --approval-ref "where the standing approval is" --when YYYY-MM-DD \
        --answers-file bundle_answers.csv --out XC/
    python3 bundle_page.py XC/person_spec.json --out person.html --items XC/person_items.json --root WORK
    python3 cross_check.py merge --auto XC/auto_answers.csv --person person_answers.csv \
        --record XC/cross_check.json --out bundle_answers.csv
    python3 bundle_route.py --items WORK/items.json --answers bundle_answers.csv ... --out ROUTED/

**Measured once, on a bundle the person had already answered** (run2, 2026-10-18; four
blinded agents, 52 verdicts for the 52 items that are not `fdt:` paths). The rule would
have written 43 items without the person and sent 11: 2 new paths, 3 disagreements, 6
LOW. Of the 43, 42 are what the person chose. The one that is not is the only item on
which the person had departed from the proposal - a panel both checks closed as "not a
before/after comparison", which the person chose to read. So agreement between two
instances of one model is not agreement with the person; it is a cheaper first filter,
and the line says so (`Seen_By_Person=0`, both names, the evidence). The three
disagreements were worth a person's look: in one, the second check measured the bars
and showed that reading them as SD makes a difference the paper calls non-significant
come out at p < 0.01 - evidence the proposal had not weighed. Merged with the person's
own answers to the other 11, the automatic file routes in one pass against the
original items with nothing refused.

### The same idea before the value review: a second look at every overlay

The value review asks a person to look at each queued panel's overlay. Before the
page is built, two agents look at every overlay separately (run2, 2026-10-19: 156
panels, two passes of eight agents). Each sees only the overlay and the read numbers
of its panel - no reading notes, confidence or earlier answers - enlarges every mark,
and answers OK or LOOK with the cells and a one-line reason in Korean. A panel goes to
the front of the page when either pass says LOOK or is not HIGH. **This orders the
page and says where to look; it approves nothing and fills no confirmation box.**

On run2 the two passes agreed on 148 of 156 panels (87 OK, 61 LOOK), and what they
found was mostly not for the person to reject one by one but for the code to fix:

- **Box whiskers ended at the far edge of the point on the cap, not at the cap.**
  S41467 draws its minimum and maximum subject on the caps; `read_box_violin_panel`
  took the stem's last row, 5-7 px past the cap on every capped whisker. It now takes
  the middle of the cap the stem ends in (`_cap_at_stem_end`; no cap, the stem's end).
- **The stem was looked for at the declared x.** Four pixels off, the three-pixel
  column found only the points stacked on it and read whiskers 15-23 px short. It is
  now looked for at the middle of the box's own rules (`_box_middle`) - rules that
  cross the group's column, so a box glyph beside it is still not its box. Two grey-box
  panels whose declared colour was the points' orange, read before as rows of points,
  are now refused instead.
- **A marker reader's error-bar ends were never drawn.** The line and point readers
  report `Errorbar_Top_Px`/`Errorbar_Bottom_Px`; the overlay drew only `cap_px`, so
  neither the person nor the checks could see the ends. `review_overlay` now draws
  them for any mark that carries no cap of its own.

After the fixes (816513b) the Mac census ran again (98 publications clean, 154
panels, 1,329 values). The 103 panels whose overlay and values were byte-identical
kept their checks; the 51 that changed were checked again by two fresh passes. The
page then had 29 panels in front and 125 behind, against 69 and 87 before the
fixes. What stayed in front is for the person: a few readers' marker centres 10-24
px off (one paper), box rules read on rows of points (two panels), a collapsed lower
whisker read on a point, bar styles that may or may not be one series. Where a check
asked about the order of position labels, the printed axis was looked up and the
answer written on the card as a fact with who checked it - not as a verdict.

Found by `finalize_batch` after the person answered: all eight approved panels of
publication 323 were refused for METHOD_EVIDENCE_INCOMPLETE. The colour bar reader
asked its own mask about one pixel - the middle column, four rows under the top -
and 323 draws two-sided black error bars down the middle of red and blue bars, so
that pixel was black on all 141 bars and `own_mask_hit` was 0. It now asks at three
points (the middle and a quarter of the width either side) on the first row of the
bar's body, below the outline and its ramp; the 141 bars read the same numbers and
now carry `own_mask_hit=1`, `mask_overlap=0`. `matrix_bar_colour_evidence.json`.

Found while testing the page end to end, not by the checks: a value page built
without `--when` exports `Reviewed_At=""`, which `finalize_batch` refuses on every
row; the page exports HOLD, which `finalize_batch` takes only as APPROVED/REJECTED
(it flags HOLD and goes on); and `finalize_batch` removes the previous run's stamp
first, which a folder that forbids deletion (the Mac bridge) refuses - move it aside.

## What the AI carries on without the person

After the bundles of 2026-10-18 the person said the rest could go to the AI: "남은 건 ai로
자동으로 넘길 수 있을 거 같은데". What was left was of three kinds, and they are not the
same:

1. **A path the person already approved on a page** (an item whose answer was BUILD,
   FIX, MOVE, or whose effect was `needs`). It is built without asking again. The gate is
   the package's own: scenarios for every way the path could write wrongly, a mutation
   matrix with nothing unobserved, both CI profiles green. Then the answers that waited
   for it are recorded the usual way - on a copy first, the run's own fingerprints
   guarded, the census before and after, backups, then the runs - and the person gets a
   report, not a page.
2. **What the papers state**, missing from the records (a group's n, a unit). It goes
   through an existing gate as a bundle item, and the cross-check rule above decides:
   agreed, HIGH and evidenced is written; the rest is the person's page.
3. **Still the person's**: a judgment the two checks do not share; anything that changes
   the review's protocol; and **values entering the pool** - `finalize_batch` takes a
   registered person's look at the overlay, and nothing here changes that without the
   person deciding it in so many words.

The three paths built under (1) on 2026-10-18:

- **A panel this gate closed, reopened by this gate.** `record_outcomes --replace` takes
  LABEL on a panel the plan closed *only* because of this file's own NON_TARGET row (the
  plan's reason starts `outcome_decisions:`). A figure's disposition, NOT_DATA, an answer
  without `--replace`, or a plan saying so with no NON_TARGET row in the record is still
  `PANEL_CLOSED`. (run2: a panel closed as the duplicate of another figure's column had to
  come back when that column's axis turned out to be borrowed.)
- **`RASTER_600_MISSING`** in `make_plan` (above).
- **`move_panels.py` - a drawn panel credited to the wrong figure.** A crop that holds two
  figures gets panels drawn for both; the ones that belong to the other figure move to it
  with everything that names them: the drawn boxes and 600 dpi regions (Draft_ID, index),
  every geometry and identity CSV - proposals as well as decisions, because `--replace`
  rebuilds a card from its proposal row - including other columns that name a moved card
  (a shared axis), the outcome rows, and the overlay images (copied, not removed). The
  target's "no panels" row goes. It refuses a move onto itself, across papers, of a panel
  the source does not have, onto a figure already drawn, over any name already taken,
  from a figure with legend groups (written by panel number), and without an approval
  reference; and without `--write` it only shows. The target's disposition (a RECROP, say)
  is changed through `record_dispositions`, not here.

    python3 move_panels.py --run RUN --from DRAFT_A --panels 2,4 --to DRAFT_B --when YYYY-MM-DD \
        --approval-ref "where the person chose MOVE" [--write] [--log moved.json]

Recorded the same day on run2, with no page: the reopened panel (an approved observation
naming the answer that chose it) and the move with its RECROP withdrawn, rehearsed on a
copy, then the container and the Mac with the same fingerprints. A run may hold old review
CSVs among the cards that the copy did not have; the move renames inside them too, and
their before and after go in the log rather than the comparison. The census on real crops
went from 2 manifest problems to none: 98 of 98 papers compile and run clean.

**What the census says about the values, before anyone reads them.** The census is not a
reading run - it is read for manifest problems - but its runs do read, and on run2
(2026-10-18, real crops, 98 papers) no value passed machine QC. The reasons are not the
readers' alone: `N_Outcome` is missing on 804 units in 76 papers (nobody has entered the
groups' n), 4,635 declared factor levels were never read (the reader found fewer marks
than the card declares), and 705 grids miss cells. The n is category (2) above: stated
in the papers, carried by the identity card (`N_Outcome` is a field the card gate takes),
so it can go through a bundle and the cross-check. The unread levels are the reading
path's: G01, decided by the person on 2026-10-18 ("1로 가자") - the section below.

**The n, recorded on run2 (2026-10-19).** 808 units without `N_Outcome`, one item per
identity card, options N (the number goes in the item's text, so the blinded check writes
its own and `TEXT_DIFFERS` compares them), NOT_ONE_N, NOT_STATED, UNCLEAR. Four proposer
instances read the papers' methods, captions, tables and results with quotes and pages;
four checkers that never saw a proposal answered the same brief from the text, the panel
and the packet. 627 agreed with HIGH and evidence: 411 cards got their n through
`record_identity --replace` (rehearsed with `census_copy`, the same fingerprint on the
container and the Mac), and 216 agreed there is no single n. 181 went to the person on a
second page whose options carry both checks' numbers, so whichever the person picks goes
through the same gate. Sent to the person whatever the checks said: a proposal of
"unclear", an n derived only from an ANOVA's degrees of freedom, and an n of 1 on a panel of
individual subjects (whether such panels enter the pool is the review's protocol, not a
paper's statement). The two instances disagreed on individual-subject panels - the
proposers wrote 1 per plotted point, the checkers the number of subjects drawn - which is
exactly why that kind stays the person's.

**A group's own n (built 2026-10-19; the person: "1은 만들어주고").** `N_Outcome` is one
number per card, and a panel whose series are groups of different size (women and men,
finishers and non-finishers) has none - its values failed machine QC however well they
were read. Each group now carries its own:

    identity card    Series[i].n, a positive whole number; all series or none
                     (SERIES_N_PARTIAL), never beside the card's N_Outcome (N_TWICE),
                     never anything else (SERIES_N_BAD) - `record_identity`
    make_plan        the plan's series get n_outcome and n_source; a bad value is
                     carried as written so the batch layer refuses it out loud
    compile_plan     series_n.csv (Panel_ID, Series_ID, N_Outcome, N_Source), an optional
                     manifest written with its header when nobody has one, hashed either way
    batch layer      unknown panel or series, a series twice, not a whole number, no
                     source, some series but not all, beside the unit's n, a unit that is
                     not continuous or a quantile summary - all refused before the run
    run_batch        each value carries its group's n as N_Cell, found by the level its
                     series puts in the Cell_Key (a value row names no series)
    grid gate        a unit whose cells carry their n is not missing one; a cell without
                     it beside cells with theirs is; N_Cell must be a whole number and is
                     never beside the unit's n; the SE-implies-SD check reads the cell's n
    finalize         re-gates the raw file with N_Cell, and a candidate whose N_Cell is
                     not the raw row's is not derived from it

Filled from the papers the same way as the card's n - a bundle item per card whose
BY_SERIES answer is the text `name=n; name=n` in the card's series order, proposals with
quotes, a second check that never saw them, the cross-check rule - and what it does not
cover stays without n: an n that changes along the x axis (time points with dropouts,
groups laid out on the x axis) is per cell, not per series.

Recorded on run2 the same day: of 267 cards where a check had said the n differs per
mean, 185 agreed with HIGH and evidence - 103 got each group's n (303 series) and 82
agreed the n changes along the axis - and 82 went to the person, merged with what was
left from the first n bundle into one page whose every offered number goes through the
identity gate. Rehearsed with `census_copy`, the same fingerprint on the container and the
Mac; the Mac census (real crops, all 98 papers clean) went from 619 values passing machine
QC to 1,195, 576 of them carrying a group's own n.

**And a cell's own n (built 2026-10-19; the person: "9개로 해야할 거 같아", "화살표로
분마다 n").** A time course drawn "until 50% of the subjects had finished", with an arrow
at each subject's finish, has a different n at every minute, and each group stops at a
different minute. The same path, one level down:

    identity card    Series[i].n_by_x = {x label: n}; keys are the card's x labels
                     (SERIES_N_X_UNKNOWN), never beside the series' n (SERIES_N_TWICE)
                     or the card's (N_TWICE); a series with n_by_x counts as having its
                     n for SERIES_N_PARTIAL; a series may say n and another n_by_x
    make_plan        n_by_position keyed by position id; an x label a series does not
                     name is a cell it is not drawn at, so the unit's grid is SPARSE,
                     with the justification spelled out per series
    compile_plan     one series_n.csv row per cell, with Position_ID - a column written
                     only when some cell has its own n, so every other batch is byte for
                     byte what it was (BM.SERIES_N_OPTIONAL_COLUMNS)
    batch layer      a position the panel does not declare (SERIES_N_POSITION_UNKNOWN),
                     a series said both per series and per cell (SERIES_N_LEVEL_MIXED),
                     a cell twice (SERIES_N_DUPLICATE)
    run_batch        N_Cell from the cell's own row (series AND x level in the Cell_Key),
                     else the series' row

`test_series_n.py` +27, `matrix_series_n.json` +13.

Which minute an arrow counts against is a reading, not arithmetic, so check it against the
figure. Count n(m) as the subjects still testing at some moment of the minute that ends at
m, `#{finish > m-1}`, not `#{finish > m}`: under the stated rule a curve stops at the last
minute with n > N/2, and in the figure this was built for the after-bed-rest curves of all
three groups stop exactly there under (m-1, m] and none does under [m, m+1). The
before-bed-rest curves run one or two minutes past it in two groups under either count;
the card's note says so instead of bending the count to fit. Two blinded readers per
figure read the arrows (counts equal to the caption's n, times within 0.05 min); an arrow
within 0.15 min of a minute boundary can move that cell's n by one, and the note lists
those cells. A cell whose two error ends are both hidden has a mean and no spread: it is
left out of the card (the grid is SPARSE) rather than given a guessed end.

## A panel no reader can read, read by an AI agent, confirmed by the person

A panel a person routed to MANUAL (`Read_Route=MANUAL` on the identity card, so
`Panel_Mode=MANUAL`) used to stop at `MANUAL_POINT_READ` with every cell in the queue.
The person chose (2026-10-18, option 1 of G01): **the AI agent reads the points first, on
the 600 dpi raster, and the person confirms them on the overlay through the ordinary value
review and `finalize_batch`.** Nothing about the door into the pool changed: a registered
person's approval of the panel's overlay, bound to the run's fingerprint, is still the only
way a value becomes poolable. What changed is that the person is confirming placed points
instead of placing them.

**What the agent writes.** `seg/readings600/supplied_readings.csv` in the run, one row per
cell, by the names the person confirmed on the identity card:

    Proposal_ID, Series (legend name), X_Label (x label as confirmed),
    Mark_X_Px, Mark_Y_Px          the mark's centre / a bar's top edge, 600 dpi raster pixels
    Upper_Y_Px, Lower_Y_Px        the error-bar ends above / below it; blank if not drawn
                                  or hidden (a bar hiding its lower whisker)
    Reader_Kind=AI_AGENT, Read_By (the agent, e.g. claude-opus-5-5), Read_At (YYYY-MM-DD),
    Raster_SHA256 (the raster the pixels are on), Note

No number is written. `make_plan` carries the rows into the plan under the plan's own
series and position ids, `compile_plan` writes `supplied_readings.csv` (an optional manifest,
empty when nothing was read, hashed into the stamp either way), and `run_batch` reads a
MANUAL panel from its readings: the number is the panel's calibration at the pixel; the
spread is half the distance between two placed ends, or one end's distance from the mean.
A MANUAL panel with no readings is queued exactly as before.

**What it costs the reviewer, and why.** Every placed point is R2: `AI_PLACED_POINT`, its
ends `AI_PLACED_CAP`, and on a panel with more than one series `AI_ASSIGNED_SERIES` (one
series is `DECLARED_SINGLE_SERIES`). The arithmetic is re-made at finalization; where the
agent looked is not re-measured by anything, so it is not `MANUAL_DIGITIZED` (R0, a person's
own digitizing - a different claim, not built). R2 means the panel's approval needs
`Inference_Checked=CONFIRMED` beside `Marks_Checked`: the overlay draws every placed point
and both placed ends, labels them with `@`, and its footer counts them as placed by an AI
agent. An approval without it finalizes nothing.

**What is refused, and where.** Before the run (`batch_manifests.check_supplied_readings`):
a reading on a reader's (AUTO) panel, on a non-continuous unit, of an undeclared panel,
series or position, a cell read twice, a Reading_ID used twice, a pixel that is not a finite
number or lies outside the plot area, an upper end below the mark or a lower end above it,
a point nearer another position's column than its own, a raster that is not the panel's, a
`Reader_Kind` with no method, no `Read_By`, a `Read_At` that is not a date. At
finalization: the route's own contract (`provenance.route_of` - a MANUAL panel is held to
`SUPPLIED`, so a reader's panel cannot claim a placed point and a supplied panel cannot
claim a reader's measurement), and a verifier that compares each mark with its declared
reading field by field and re-makes every number from the reading's pixels. A reading edited
after the run is a manifest the run did not validate (`RUN_MANIFEST_MODIFIED`).

**What the agent should do to read well.** Place points on the 600 dpi raster the panel's
box and ticks were confirmed on (the region raster in `panel_regions_600.csv`), never on the
200 dpi crop. Put a bar's point on the top edge of its outline (the unit's
`Bar_Top_Definition`), a marker's on its centre. Leave an end blank rather than guess one
hidden by a bar or another series; leave a cell out rather than guess a mark it cannot see -
an unread cell is a missing cell the queue names, not an error. One reading per printed mark.
The agent does not fill the review's confirmation columns; those are the person's.

**Recorded on run2 (2026-10-19).** 229 continuous MANUAL panels: 36 declared NO_ERRORBAR were
not read; 20 were skipped whole because no error bar is drawn although a dispersion is
declared (individual-subject lines or bars, step plots, fitted lines); 173 were read into
1,676 readings. Every bar panel the automatic measurement passed was looked at again by a
second instance (88 of 94 needed corrections), every failed one was read by hand, and every
line panel was read by eye. Rehearsed on a copy, then the run gained one new file and no
changed record. On the Mac (real crops, all 98 papers clean) 321 placed values pass machine
QC; the rest wait on a group's n, on an end that could not be seen, or on cells left out.
What reading taught, for the next agent:

- **A cap is wider than its stem.** Counting any row a few pixels wide as cap takes a thick
  stem's own rows, and the cap lands 1.5-2 px toward the mark - short whiskers lose up to a
  tenth of their spread. Take the stem's width as the median over its rows (not the
  narrowest: an antialias row is one pixel) and the cap as rows at least 4 px wider.
- **A snap that cannot isolate a mark must say so.** Where ink fills the search window
  (overlapping marks, a marker larger than the window) the "centre" is the pick itself.
  Read those on a zoomed pixel ruler and give them as placed.
- **Put the point where its own whisker is symmetric.** Triangles differ by plotting
  program - some centre the data on the bounding box, some on the centroid - and the caps
  say which. With two marks on one column, give each the pair of caps symmetric about it,
  and only when the other pairing is clearly worse; otherwise leave both ends blank.
- **Faint marks need their own threshold** (light-grey markers and whiskers vanish at the
  usual dark cut), and blocky upsampled scans limit placement to about the block size.
- **A drawn point nearer another position's column is refused by the run** (the anchor
  check). Skip that cell and say why; do not move the point.
- **A bar whose outline is the fill's colour** has no visible outline centre. These were
  read at the fill edge, as the released readers read; a unit declaring OUTLINE_CENTER sits
  half an outline (1.5-3.5 px here) further in. One rule for every reader is the person's
  call.

**A point the person placed (built 2026-10-20; the person, holding one panel: "중간에
빼먹은 거 있어서 이거 내가 추가적으로 찍을 수 있게 해줘").** Where the agent left a cell out
- both error ends merged into the other series' caps, so no spread could be read - the
person can place it, on the same raster, into the same `supplied_readings.csv`:

    Reader_Kind=PERSON     Read_By must be a HUMAN in reviewer_registry.csv
                           (SUPPLIED_READER_NOT_REGISTERED, SUPPLIED_READER_NOT_HUMAN);
                           Read_At not after today (SUPPLIED_READING_DATE_FUTURE)
    methods                MANUAL_DIGITIZED, MANUAL_PLACED_CAP, and PERSON_ASSIGNED_SERIES
                           on a panel of several series - all R0, the person's own
                           digitization. One table (`provenance.SUPPLIED_KIND_METHODS`)
                           for the run and the finalizer, and the finalizer takes the
                           kind from the DECLARED reading, not the mark's copy
    overlay, value page    `P` where an agent's point is `@`; a panel with any agent's
                           point still asks `Inference_Checked`

The page the person places from shows the 600 dpi panel at 1-6x with the agent's points
thin, a dashed guide at the cell's calibrated column, and three clicks per cell (centre,
upper end, lower end - an end may be "not visible", both may not); the ID and the date are
typed, never filled. The cell's n comes from the arrows like every other minute.
`test_supplied_readings.py` +20, `matrix_supplied_readings.json` +17.

**And a box (built 2026-10-20; the person: "1,2 둘다 하나로 만들어줘", where 1 was the 28
MANUAL panels nobody had read - every one a box plot of two series, which the box reader
cannot read: it takes one series per position).** The same file, two optional columns
(`BM.SUPPLIED_BOX_COLUMNS`, written only when some reading is a box's, so every other
batch is byte for byte what it was):

    Mark_Y_Px                the median line
    Box_Upper_Y_Px/Lower     the box's two edges on the page - required for a
                             QUANTILE_SUMMARY unit (SUPPLIED_READING_BOX_EDGES_MISSING),
                             refused on a mean (SUPPLIED_READING_BOX_ON_MEAN)
    Upper_Y_Px/Lower_Y_Px    the whisker ends
    order                    whisker, box top, median, box bottom, whisker, top to bottom
                             (SUPPLIED_READING_BOX_INVERTED; the median may sit on an edge
                             and a whisker may have no length - a box is asked this order,
                             never a mean's strict two-ends rule)

The run makes the five numbers with `provenance.supplied_box_numbers` (quartiles sorted, so
an inverted axis does not swap them; two whisker ends are the lower and the upper in value
order; a lone whisker keeps its side and the grid gate says WHISKER_HALF_FILLED) and the
finalizer makes them again; the overlay draws the five rows. The first real batch found both
rules too strict for a box whose median, first quartile and lowest value share one row: the
mean's ends rule refused the whole batch, and sorting the ends by the median put the lowest
value on the upper side (2026-10-20, `test_supplied_readings.py` +4).
A mean's mark gets no box key at all - a null key would still have changed every existing
`Mark_Record_SHA256`. A whisker that is not drawn because the extreme IS the box edge (a box
sitting on zero) is that edge, not a blank: blank means nobody could see it.

**And an end nobody can see (built 2026-10-21; the person: "끝이 없는 칸도 넣어줘야해").** A
mean whose error bar is hidden - inside its own marker, under other marks, or on a bar two
series share - goes in with its ends set at the edge of what hides them, and the optional
column `End_Basis` says so: blank or `CAP` = printed caps, as before; `BOUND` = an UPPER
BOUND on the spread. The number is made exactly as a cap's; the value's `Dispersion_Method`
is `BOUND_HIDDEN_END` (R3) whoever placed it, so a bound never passes for a cap, the run asks
about each bounded cell on its own (`inference-review/`, `Inference_Confirmed` per cell), and a
sensitivity analysis can drop them by method. Refused before the run: an End_Basis this file
does not define (SUPPLIED_END_BASIS_UNKNOWN), a bound with neither end
(SUPPLIED_END_BOUND_WITHOUT_END), a bound on a box's whiskers (SUPPLIED_END_BOUND_ON_BOX).
Written only when some reading has it, so every other batch is byte for byte what it was.
A cell with no error bar drawn at all has nothing to bound and stays out.

**Three paths the person opened on 2026-10-20 (decision page v8: D01, D14, D15).**

    MEASURED definition   `record_errorbar` Definition_Basis=MEASURED: the dispersion type was
                          measured on the figure, not read from a sentence (the paper said SD;
                          two independent checks found the bars equal to the SE of the plotted
                          individual values in 22 cells). The quote cell describes the
                          measurement and is not looked up in the source; Note and Verified_By
                          are required. `make_plan` carries MEASURED_NOTE to the unit, like
                          BORROWED_NOTE, so a sensitivity analysis can drop those values.
    one categorical slot  A panel with a single x position is calibrated on that slot alone:
                          `make_plan` writes x_calibration [[0, px]] and the gate takes
                          X1 = slot 0 at a pixel with X2 blank as a whole x calibration.
                          Any other blank in the four X/Y cells is still MISSING_PROVENANCE.
    shape and scale       `record_shape` writes `shape_decisions.csv` (run root):
                          Distribution_Shape (RIGHT_SKEWED / LEFT_SKEWED / SYMMETRIC / UNKNOWN),
                          Value_Scale (RATIO / CHANGE) and the basis (no hedging words), with
                          the approval cells. `make_plan` puts them on the unit, the basis in its
                          note. A large SE on a right-skewed outcome then passes
                          DISPERSION_IMPLIES_SKEW, and a change score leaves the ratio-scale check.

## Provenance is per FIELD, not per row

One row can be two readings. The commonest real case is a correlation whose r
was digitized off a scatter and whose p was copied out of the running text —
`Extraction_Method` alone cannot say that, and forcing one label onto the row
means either the r or the p is mislabelled.

`Extraction_Method` stays on the **unit** and describes how the effect was
obtained. `P_Value_Extraction_Method` (`DIGITIZED` / `TRANSCRIBED`) sits on the
**value row** and describes only the p. They may differ, and the gate checks
each against the method that produced it:

- a computed method (`PEARSON_T_TEST`, `SPEARMAN_T_APPROX`, `SLOPE_T_TEST`,
  `R_SQUARED_F_TEST`, `FISHER_Z_APPROX`, `KENDALL_EXACT_PERMUTATION`,
  `KENDALL_NORMAL_APPROX_N_GT_200`) beside `TRANSCRIBED` is a contradiction
- `SOURCE_REPORTED` beside `DIGITIZED` is a contradiction
- `DIGITIZED` on a unit whose `Extraction_Method=TRANSCRIBED` is a contradiction:
  there is no point cloud to compute from
- a blank p attributes nothing, so the provenance may be blank too

`Ties_Present` TRUE/FALSE is required on every **rank** row — Kendall and
Spearman both — because a rank statistic's null distribution depends on it. It is
not a note: the gate contradicts the reader with it. `KENDALL_EXACT_PERMUTATION`
or `SPEARMAN_T_APPROX` beside `Ties_Present=TRUE` fails, and so does
`SOURCE_P_REQUIRED_TIES` beside `Ties_Present=FALSE`.

## Every statistic has its own null distribution

One label used to stand beside all five association types: every p — Pearson,
Spearman, Kendall's asymptotic branch, R², slope — was the Fisher-z normal
approximation, recorded as `FISHER_Z_APPROX`. On the ten to thirty points a
digitized scatter actually carries, that is not a rounding difference. A
six-point r of 0.94 is p=0.0053 by the t and p=0.0026 by the z — a factor of two,
in the direction that makes the finding look stronger.

Each statistic now names the test that produced its p, and the gate refuses any
other:

| `Association_Type` | `P_Value_Method` | test |
|---|---|---|
| `PEARSON_R` | `PEARSON_T_TEST` | t = r√((n−2)/(1−r²)) on n−2 df |
| `SPEARMAN_RHO` | `SPEARMAN_T_APPROX` | the same t on the rank correlation — **untied only** |
| `SPEARMAN_RHO` (tied) | `SOURCE_P_REQUIRED_TIES` | no p; average ranks change the null |
| `KENDALL_TAU` | `KENDALL_EXACT_PERMUTATION` / `KENDALL_NORMAL_APPROX_N_GT_200` | selected by n |
| `R_SQUARED` | `R_SQUARED_F_TEST` | F = R²/(1−R²)·(n−2) on 1 and n−2 df |
| `SLOPE` | `SLOPE_T_TEST` | t = b/SE(b) from the regression's residual variance |

`FISHER_Z_APPROX` survives in the vocabulary for `PEARSON_R` only, because a
paper may report one. Beside a slope, an R² or a rank correlation it is
`P_METHOD_WRONG_FOR_STATISTIC`.

The t and F tails are computed from a hand-rolled regularized incomplete beta —
this package does not import scipy, and an exact tail written out is preferable
to a normal approximation wearing an exact name.

## `N_Pairs` is the reader's own count, so something else has to check it

`N_Pairs` is however many contours survived the area filter. It cannot show that
the reader missed a point, because it *is* the number the association was
computed from: it agrees with itself by construction. Five fields sit beside it:

- `Expected_N_From_Source` — the unit's `N_Outcome`, i.e. what the paper says
- `Detected_Unique_Point_Count` — distinct marker positions, after centroids
  closer than 3 px are merged (a marker crossed by a gridline is two contours)
- `Point_Count_Agreement` — `MATCH` / `FEWER_DETECTED` / `MORE_DETECTED` /
  `NO_SOURCE_N`
- `Overplotting_Possible` — TRUE when marks are missing, when a blob is more than
  1.6× the median marker area, or when coincident contours were merged
- `Series_Mask_Overlap_Count` — marks that fall inside another series' colour
  mask, so colour does not establish which series they belong to

A disagreeing count **halts the calculation**. The panel goes to
`MANUAL_POINT_READ` with both numbers in its detail rather than publishing an
association computed from a point set that is not the study's. The gate reaches
the same verdict independently from the file
(`POINT_COUNT_DISAGREES_WITH_SOURCE`), because a hand-edited values file never
went through the runner.

## A digitized association without its points is not evidence

`Point_Data_Reference` is required whenever `Statistic_Type=ASSOCIATION` **and**
the unit's `Extraction_Method=DIGITIZED` — regardless of where the p came from,
and regardless of whether there is a p at all.

This rule was first written as "a computed p needs its points", which sounds
equivalent and is not. Two whole classes walked through it: a digitized r whose
p was transcribed, and a digitized Kendall with ties and no p. In both the
**effect** is a claim about a set of coordinates nobody else can see, and the
p's origin has nothing to do with it. The points are the record of the effect,
not an accessory to the p. `mark_readers.write_point_data(points, path)` writes
them; the gate then checks the path resolves on disk (`SOURCE_FILE_NOT_FOUND`),
so a reference to a file that is not there is worse than useless and says so.

A wholly transcribed association — value and p both copied from the text — needs
no point file, and the rule keys on `DIGITIZED` explicitly rather than on "not
TRANSCRIBED", so a blank `Extraction_Method` cannot back into the requirement.

## The adapter is a place where fields die

`to_value_records()` is the only thing between a reader and the value table, and
it is a per-statistic `record.update(...)`. Add a column to the reader and to the
validator, forget the adapter, and both halves pass their own suites while the
field never arrives — the gate sees a blank and, for optional fields, reads it as
"not applicable". That is exactly how `P_Value_Extraction_Method`, `Ties_Present`
and `Point_Data_Reference` were emitted, required, and silently lost.

The ASSOCIATION branch now copies a declared tuple, `ASSOCIATION_CARRIED`, and
`test_mark_readers.py` asserts both that the adapter carries all of it and that
every name in it exists in `fig_values_columns()`. Adding a field to the reader
and not to the schema now fails the suite instead of the batch.

## Declare the run before you make it

Eight files describe source completeness and the RUN, as distinct from the data. They are separate
from the four data grains on purpose: a values file has to be reviewable by
someone who never touches a raster, and a run has to be re-executable by someone
who never reads the paper.

    reviewer_registry.csv  who may attest an inventory, and how to reach them
    source_document_manifest.csv article/supplement/chapter figure inventory
    source_figure_manifest.csv physical publisher figures and verified counts
    source_panel_inventory.csv every visible panel and its disposition
    panel_manifest.csv     panel box, Mark_Type, axis calibration, and the unit
                           it fills
    series_manifest.csv    colour / marker / fill / line style / bar fill, and
                           the factor level the series IS
    position_manifest.csv  x pixel or slot, and the factor level the position IS
    reader_config.csv      long-form options, one row per option

**Identity is declared, never inferred.** A series is `ARM=FLUID` because the
manifest says so, not because it was drawn first. A bar is `SESSION=POST`
because the manifest says so, not because it is the second from the left. This
is the same principle as the grid engine's, moved one layer earlier: when a
reader cannot resolve a mark, no row appears and the gate names the hole.

**Options are validated against the reader that will receive them.** A
misspelled option, or a real option that means nothing to this mark type, is an
error before the run rather than a default silently applied during it. `run_batch`
validates every manifest before it opens a single raster, because discovering on
figure 140 that a Config_ID was mistyped is an expensive way to learn it.

**Every panel lands on exactly one state**, and anything short of `AUTO_PASS`
goes to `manual_queue.csv` with the reason and the coordinates a human needs:

    AUTO_PASS  MANUAL_POINT_READ  SERIES_IDENTITY_UNRESOLVED
    PANEL_GEOMETRY_UNRESOLVED  NO_VARIANCE  NOT_CONVERTIBLE  QC_FAILED

`SERIES_IDENTITY_UNRESOLVED` is the one worth knowing about. If one declared
series produces marks and another produces none, the panel does not contribute
half its cells - it contributes none. A reader that can find one of two curves
cannot be trusted about which curve it found.

## Only one output file is safe to pool from

A run writes **`figure_values_accepted.csv`** and **`figure_values_raw.csv`**,
and deliberately nothing called `figure_values.csv`. The accepted file holds
only rows whose panel reached `AUTO_PASS` and whose unit drew no gate problem;
the raw file holds every reading, each row carrying `Value_Status`, `QC_Codes`
and `Pooling_Eligible`.

The reason for two files rather than one flagged file is that the failure mode
is a *script*, not a person. A single `figure_values.csv` once carried eight
means whose SD-versus-SEM was unresolved while the panels sat at `QC_FAILED` in
a different file; anything that read "the values file" and pooled it would have
been wrong by a factor of sqrt(n) and would never have known. The safe file now
has the plainest name, and the unsafe one answers the question in every row so
nobody has to know to join.

Any gate problem charged to a unit disqualifies **all** of that unit's cells.
The individual readings may be fine; a unit with a hole in its grid is not
poolable, and the raw file keeps the numbers for whoever resolves it.

Every value row also carries `Source_Panel_ID`, and is judged by **its own**
panel plus the worst state among every panel building that unit. Keying state by
`Unit_ID` alone once let the last panel seen overwrite the first, so a unit whose
readable half filled the whole grid came out accepted while its unreadable half
was never mentioned. Nobody knows whether the panel that could not be read would
have agreed.

**One panel per unit, stated on both rows.** `unit_manifest.Panel_ID` and
`panel_manifest.Unit_ID` have to name each other, and exactly one panel may read
a unit (`UNIT_FILLED_TWICE`). Without the unit's half of that, exchanging the
`Unit_ID` of two panels of one figure produces a manifest set in which every
measurement is right, every hash matches, and one panel's numbers sit under the
other's outcome — which no downstream check can see, because nothing else
disagrees. `Source_Panel_ID` on the unit says the same pairing at the physical
grain.

**Clearing up happens at the START of a run, before anything can fail** —
including reading the manifests. A run that tidies
after itself only tidies when it gets that far: reject a manifest and the
previous run's `figure_values_accepted.csv` is still sitting there, and nothing
inside that file says it belongs to a run that has since been superseded by a
failure. Every output is removed before validation, the summary CSVs are built
in a staging directory and promoted in one move, and a rejected run still writes
`run_stamp.json` with `Status=MANIFEST_REJECTED` and zero counts. A stamp that
is absent when things go wrong is only ever there to reassure.

Reading the manifests first looked harmless and was not: a missing directory or
a malformed CSV raised before the clearing ever happened, so a run that never
started left the previous run's accepted file and its `Status=RAN` stamp intact.
`Status` is one of `RAN` / `MANIFEST_REJECTED` / `INPUT_LOAD_FAILED` /
`PROMOTE_FAILED`, and only `RAN` may have an accepted file beside it.

The loader raises a plain `ManifestLoadError`. It used to raise `SystemExit`,
which derives from `BaseException` — so the obvious `except Exception` around
the load sails straight past it and the caller never gets to record what
happened. A test catches `BaseException` and asserts the type, so a regression
fails a scenario rather than taking the suite down.

**Promotion is ordered, because it cannot be atomic.** A directory rename would
be atomic and is not available: value rows NAME their point files and WPD
projects, so those must be written at their final paths. What is available is an
order. `figure_values_accepted.csv` moves last and nothing depends on it, so it
is a commit marker — die partway and the pooling file is the one thing that is
not there. Everything that explains a result is promoted before it, the arrival
of every file is verified afterwards, and a failure withdraws the marker and
stamps `PROMOTE_FAILED`. A fault-injection test kills the promotion at three
points and asserts the directory is not poolable after any of them.

## A run has to be re-runnable, and that costs more than a timestamp

`run_manifest.csv` records, per panel: the image SHA-256, the config SHA-256, the
reader version, the raw data file, the WPD project, and the run date.
`run_stamp.json` adds a hash of every input manifest. A second run over the same
inputs produces identical outputs, and the suite asserts it.

Two pieces are worth calling out.

**The run saves its own WebPlotDigitizer project.** The gate requires a
re-openable project on every digitized row, and it is right to - "the reader said
so" is not something a second person can check. An automated run has no
human-saved project, so it writes one: the raster, the calibration it used, and
every mark it placed. A reviewer opens it in WPD and sees where the reader
thought the marks were, which is the only cheap way to catch a systematically
misplaced series.

**A point file stores pixels, not just values.** Calibrated x/y alone are the
reader's answer: if the calibration was wrong, the saved values are wrong in
exactly the same way and nothing in the file disagrees with anything else.
`write_point_data` requires the raw pixel of every point, both calibrations, the
image hash, the Unit_ID and the Cell_Key, and it re-derives every value from its
own pixel before writing - a file whose numbers do not follow from its own
pixels is rejected at write time. `read_point_data` re-checks the same thing on
load, so a file edited afterwards does not pass silently.

## Monochrome bars are named by fill, and the cap is not the bar

A black-and-white bar chart names its series by FILL PATTERN - solid, hatched,
open - and no colour mask can see the difference. Interior dark density
separates the three, sampled INSIDE the outline: including the two side strokes
lifted an open bar from 0.02 to 0.16, into the hatched band, and the reader then
named the wrong series with complete confidence.

Finding the bar's end by "the first row spanning half the slot" looks right and
is not. An error-bar cap is drawn about 70% of the bar's width, so on a narrow
bar the cap clears that test and the whisker tip becomes the value - every mean
high by a whole SD, in one direction, silently. Walking UP FROM THE BASELINE
removes the cap from the question: a bar has two side strokes continuous from
the baseline to its end and a floating cap has none, so the walk stops before it
ever reaches one.

**The stem gets its own threshold, and that is not a fudge.** Grey level is ink
coverage: a filled bar reads near 0, a one-pixel hairline stem at 60% coverage
reads about 140 on the same figure. Thresholding both at 128 found every cap and
no stem, so on publication 397 the reader confirmed nothing and returned no
dispersion at all - a fail-closed answer produced by a measurement error rather
than by the figure.

## Caption screening, carried from the first version

The first version of this skill was the caption screen and the row validator
that `kernel.py` still is; `make_plan.py` calls the screen for every figure. What
it learned still holds:

- `fig_screen_caption` gives a route per figure: `DIGITIZE`,
  `PARTIAL_PANEL_TARGET`, `ASSOCIATION_ONLY_NOT_TARGET`, `BINARY_EVENT_NOT_MEAN`,
  `NO_TARGET_OUTCOME`, `NOT_DATA`. The last two are screening verdicts from
  caption text, which is often truncated - a visual check closes them, not the
  screen.
- A scatter or regression plot read with the mean template fabricates a mean
  difference out of an association; it needs its own schema.
- Target terms name outcomes, never groups or timepoints ("presyncopal men" is a
  cohort). Qualify an ambiguous noun rather than truncating it, and after any
  term-list edit diff the routes of the whole corpus and read every caption whose
  route changed.
- `Exposure_Phase` is declared (`PRE` / `DURING` / `POST` / `RECOVERY` / `DELTA`),
  never inferred from a label: `FD15` or `HDT30` is DURING, not follow-up.
- No error bar is `NO_ERRORBAR`, never `NONE`, which the blank-token rule reads as
  an empty cell. A CSV blank is float nan, whose `str()` is "NAN" - validate
  through a CSV round-trip, never an in-memory frame.

## The four suites, and why there are four

    python3 test_kernel.py          # validator against hand-built rows
    python3 test_grid_engine.py     # four-grain grid + value engine
    python3 test_bar_reader.py      # colour bar reader against real rasters
    python3 test_mark_readers.py    # non-bar readers, adapter, reader->gate chain
    python3 test_mono_bar.py        # monochrome bars, fill patterns, cap trap
    python3 test_integration.py     # template -> reader -> CSV -> validator
    python3 test_run_batch.py       # source inventory -> manifests -> values -> gate -> queue
    python3 test_reproducibility.py # clean-room import, no scipy
    python3 crosscheck_id323.py     # second independent reading of one figure
    python3 forward_test_397_mono_bar.py   # a real publisher raster

Run all of them after ANY edit. They fail in different ways on purpose.

`test_run_batch.py` includes the completeness counterexample: a physical figure
declares 36 visible panels while 14 virtual rows each appear internally complete.
The batch must fail with `SOURCE_PANEL_COVERAGE_INCOMPLETE`.  A second fixture
shows that unconfigured manual/no-reader panels survive in the source coverage
ledger and queue instead of blocking readable panels or disappearing.

A synthetic fixture proves a reader is self-consistent. It cannot prove the
reader survives JPEG softening, a 1 px hatch outline that misses the threshold,
or two panels of one figure whose axes are four pixels apart - and every one of
those broke the monochrome bar reader the first time it met a real figure. That
is what the forward tests are for, and why a reader without one is not released.

**A unit suite cannot see a template that disagrees with the validator.** The
geometry checks above shipped once with `Extraction_Method` absent from
`fig_template_columns()`. Every scenario passed, because the fixtures added the
key from outside the template — and on a real 51-column CSV both checks silently
skipped. `test_integration.py` exists for exactly that gap: it builds the CSV
from `fig_template_columns()` and nothing else, and `crow()` now raises if a
fixture references a column the template does not ship.

**A frozen fixture proves stability, not accuracy.** `fixtures/id323_fig2_*` locks
72 bars against whatever the reader currently produces; that catches regressions
and nothing else. `crosscheck_id323.py` re-reads the same raster by a different
primitive — column scan and median instead of row profile and run centre — and
the two agree to **0.50 px** on the means. Independence belongs in the primitive,
not in the definition: when the two used different cap definitions they differed
by 3 px, and aligning the definition while keeping the methods distinct is what
made the comparison meaningful.

**Reproduce the defect, do not merely assert the fix.** `read_bar_panel` takes
`stem_required=False` to restore the broken behaviour on demand, so the suite can
show the glyph trap costing +18 units and, on a glyph-free chart, show the rule
costing nothing.
