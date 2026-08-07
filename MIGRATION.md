# From shape-dispatched to factorial-grid validation

## Why

`fig_validate_extraction` branched on `Data_Shape`, so a figure that did not fit
its label needed a new rule. That is how `B_DUPLICATE_CELL` fired on a perfectly
well-formed 6-session x 2-posture figure, and how the next step would have been
`A_CONDITION_SET_ASYMMETRIC` — a rule about one study, wearing a shape's name.

A 6x2 session-by-posture figure, a 4x3 gravity-by-load figure and a two-cell
pre/post study differ in their factors and levels, not in their validation logic.

## The four grains

| Grain | One row per | Answers |
|---|---|---|
| figure manifest | figure | the source, the image, the panel reconciliation |
| grid definitions | grid x factor x level | what the axes and series actually are |
| unit manifest | figure x panel x outcome x statistic | how it was read, and how the grid must behave |
| **figure values** | cell | the reading, addressed by `Cell_Key` |

A hand-curated set names these whatever suits it — `id323_figure_values.csv` in
the worked example. **A batch run does not.** `run_batch.py` writes the values
grain as two files and deliberately never as `figure_values.csv`:

| Output | Contains |
|---|---|
| `figure_values_accepted.csv` | only rows whose panel reached `AUTO_PASS` and whose unit drew no gate problem — the only file to pool from |
| `figure_values_raw.csv` | every reading, each row carrying `Source_Panel_ID`, `Value_Status`, `QC_Codes` and `Pooling_Eligible` |

The plain name is gone on purpose. A single `figure_values.csv` once carried
eight means whose SD-versus-SEM was unresolved while the panels sat at
`QC_FAILED` in a different file, and anything that read "the values file" would
have pooled them.

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
