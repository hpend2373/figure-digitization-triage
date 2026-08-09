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
| unit manifest | figure x panel x outcome x statistic | how it was read, and how the grid must behave |
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
