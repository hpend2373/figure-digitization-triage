# SKILL.md — sections to add

Insert after "## Extraction protocol (hand this to whoever reads the figures)".

---

## Record HOW the mark was read

Two geometric facts decide whether a digitized number is right, and neither is
visible in the finished CSV unless it is recorded.

**A vector bar's data coordinate is the centre of its stroke.** The colour fill
stops inside the outline, so reading the fill edge puts every mean low by half
the stroke width — on a 4 px stroke that was 1.2 units on a 150-unit axis, in the
same direction on all 72 bars of one figure. Record `Bar_Top_Definition`:
`OUTLINE_CENTER` / `FILL_EDGE` / `MARKER_CENTER` / `NOT_A_BAR`. `FILL_EDGE` is
flagged, not forbidden — declare it and the bias is auditable.

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

Create four source manifests before creating any reader row:

    reviewer_registry.csv       one row per person allowed to attest an inventory
    source_document_manifest.csv one row per main article/supplement/chapter
    source_figure_manifest.csv  one row per physical publisher figure
    source_panel_inventory.csv  one row per visually distinct source subpanel

Use an immutable `Source_Document_ID` and record the complete target article or
supplement page range.  Its `Observed_Figure_Count` must equal the number of
physical source figures attached to it, which prevents an entire figure from
vanishing before the panel check begins.  Then use an immutable
`Source_Figure_ID` such as `PMID123_MAIN_FIG2`.  Count panels on the
full raster, not from the caption.  Count plots, photographs, schematics and
table/inset subpanels before deciding whether they contain target data.  A legend
or colour bar is not a panel, while an inset with its own independent content is.
If the source supplies no panel letters, assign stable reading-order labels
`P01`, `P02`, ... .  Record the count method, and the `Reviewer_ID` of the person
who did the counting.

That ID is a foreign key into `reviewer_registry.csv`, which holds the name, a
contact (EMAIL or a checksum-valid ORCID) and a `Human_Attestation`.  Register
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

The same logic applies to `Unlisted_Panels`: matching panel COUNTS are not
agreement. Two rows of one figure that both say "6 of 5" while one names PAP and
the other MAP describe different figures, so the normalized name sets must match
too (`UNLISTED_PANELS_INCONSISTENT_IN_FIGURE`). Normalized, not literal — "pap ,
map" and "MAP;PAP" are the same answer, and a consistency check that says
otherwise has become a spelling check.

## Provenance is per FIELD, not per row

One row can be two readings. The commonest real case is a correlation whose r
was digitized off a scatter and whose p was copied out of the running text —
`Extraction_Method` alone cannot say that, and forcing one label onto the row
means either the r or the p is mislabelled.

`Extraction_Method` stays on the **unit** and describes how the effect was
obtained. `P_Value_Extraction_Method` (`DIGITIZED` / `TRANSCRIBED`) sits on the
**value row** and describes only the p. They may differ, and the gate checks
each against the method that produced it:

- a computed method (`FISHER_Z_APPROX`, `KENDALL_EXACT_PERMUTATION`,
  `KENDALL_NORMAL_APPROX_N_GT_200`) beside `TRANSCRIBED` is a contradiction
- `SOURCE_REPORTED` beside `DIGITIZED` is a contradiction
- `DIGITIZED` on a unit whose `Extraction_Method=TRANSCRIBED` is a contradiction:
  there is no point cloud to compute from
- a blank p attributes nothing, so the provenance may be blank too

`Ties_Present` TRUE/FALSE is required on every Kendall row, because Kendall's
null distribution depends on it. It is not a note — the gate contradicts the
reader with it: `KENDALL_EXACT_PERMUTATION` beside `Ties_Present=TRUE` fails, and
so does `SOURCE_P_REQUIRED_TIES` beside `Ties_Present=FALSE`.

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
panel plus the worst state among every panel building that unit. Two panels can
feed one unit; keying state by `Unit_ID` alone let the last panel seen overwrite
the first, so a unit whose readable half filled the whole grid came out accepted
while its unreadable half was never mentioned. Nobody knows whether the panel
that could not be read would have agreed.

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
