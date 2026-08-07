# figure-digitization-triage — v7.1 (full package)

This is the **whole system**, not a patch. `field_provenance_gate_1.zip` was four
files; this replaces the skill folder wholesale, so there is no version of
`grid_engine.py` and `mark_readers.py` that can drift apart from each other.

Both HIGH defects from the last review are fixed, and each one has a test that
**fails against the old code**. That was checked by reverting the fix in a scratch
copy and re-running — evidence in "Proof the tests are load-bearing" below.

## Install

Runtime dependencies are in `requirements.txt`. SciPy is deliberately not
required; association summaries use NumPy and the standard library.

    SKILL=~/.claude-science/orgs/dd143201-4dc0-4233-9a3f-240a058d710f/skills/figure-digitization-triage
    python3 -m pip install -r requirements.txt
    cp *.py *.md *.csv *.png *.json *.tar "$SKILL"/
    mkdir -p "$SKILL"/fixtures && cp fixtures/* "$SKILL"/fixtures/
    cd "$SKILL" && for t in test_reproducibility test_kernel test_grid_engine \
        test_bar_reader test_mark_readers test_integration crosscheck_id323; \
        do python3 $t.py || break; done

Then append `SKILL_ADDENDUM.md` and `MIGRATION.md` to `SKILL.md`.

I cannot write into the skill folder from this session — skill files here are a
read-only cache. Until you run the copy the active skill is unchanged.

## HIGH 1 — the adapter dropped three provenance fields

`to_value_records()`'s ASSOCIATION branch copied five of the seven fields the
reader emits and the validator requires. `P_Value_Extraction_Method`,
`Ties_Present` and `Point_Data_Reference` died in transit, between a reader that
filled them correctly and a gate that demanded them.

The shape of the bug matters more than the three names. A per-statistic
`record.update(a=..., b=...)` has no relationship to `fig_values_columns()`, so
adding a column to the reader and to the validator leaves a third place nobody
edits and no suite covers. Both halves passed their own suites. The batch would
not have.

Fixed by declaring the set once and copying it:

```python
ASSOCIATION_CARRIED = (
    "Association_Type", "Association_Value", "P_Value", "P_Value_Method",
    "N_Pairs", "P_Value_Extraction_Method", "Ties_Present",
    "Point_Data_Reference",
)
...
elif kind == "ASSOCIATION":
    for key in ASSOCIATION_CARRIED:
        record[key] = row.get(key)
    if not record.get("Point_Data_Reference") and point_data_reference:
        record["Point_Data_Reference"] = point_data_reference
```

`test_mark_readers.py` asserts `set(ASSOCIATION_CARRIED) <=
set(fig_values_columns())`, so a name in the adapter that the schema does not
ship fails the suite rather than the run.

**Where the path comes from.** `summarize_association()` cannot know where the
caller chose to write the points, so it cannot emit `Point_Data_Reference`. Two
things close that: `write_point_data(points, path)` persists the cloud and
returns the path, and `to_value_records(..., point_data_reference=path)` fills
the column on rows that do not already carry one. A path already on the reader
row wins — the adapter default never overwrites a real reading.

The regression the review asked for, run end to end:

```python
summary = summarize_association(points, "KENDALL_TAU")
path    = write_point_data(points, ".../UA_points.json")
record  = to_value_records([summary], "ASSOCIATION", "UA",
                           cell_levels={"PANEL": "ALL"},
                           point_data_reference=path)[0]
assert record["P_Value_Extraction_Method"]
assert record["Ties_Present"]
assert record["Point_Data_Reference"]
```

The record then goes straight into `fig_validate_bundle()` on a DIGITIZED unit
with nothing hand-filled: **0 problems**. Blanking any one of the three in transit
raises `MISSING_POINT_DATA_REFERENCE`, `MISSING_P_VALUE_PROVENANCE` or
`MISSING_TIES_PRESENT` respectively — the chain is covered at the join now, not
only at each end.

One thing the first draft of this test got wrong, worth keeping: a **tied**
Kendall has no computed p, so `P_Value_Extraction_Method` is legitimately `""` and
the assert fails on it. That is correct behaviour — a blank p attributes nothing.
The fixture is asserted untied, and a separate scenario covers the tied row, where
the tie claim and the point file are exactly what make the blank provenance
legitimate and so must still arrive.

## HIGH 2 — a digitized association could pass without its points

The old rule was `P_Value_Extraction_Method == DIGITIZED and P_Value_Method in
COMPUTED`. Reworded: *a computed p needs its points*. The correction is right, and
the reasoning is worth stating because the two rules sound equivalent:

The point cloud is the record of the **effect**, not of the p. A digitized r is a
claim about coordinates nobody else can see, whatever the p's origin — or whether
there is a p at all. Gating on the p provenance let two classes through:

- a digitized effect whose p was transcribed from the running text
- a digitized Kendall with ties, `SOURCE_P_REQUIRED_TIES`, and no p

Both were fully valid rows under every other check. Now:

```python
if digitized and blank(row.get("Point_Data_Reference")):
    flag(line, "MISSING_POINT_DATA_REFERENCE", ...)
```

where `digitized` is the **unit's** `Extraction_Method`, and the branch is already
inside `Statistic_Type == ASSOCIATION`. Nothing about the p enters it.

The condition keys on `== "DIGITIZED"`, not on `!= "TRANSCRIBED"`. A blank
`Extraction_Method` must not back into a point-file requirement — it has its own
code, and one missing field should raise one error.

## Proof the tests are load-bearing

Both fixes were reverted in a scratch copy and the suites re-run. A test that
passes before and after the fix is decoration.

| reverted | result |
|---|---|
| HIGH 2 → old p-gated condition | 3 FAILED, exactly the three classes named above |
| HIGH 1 → old five-field `update()` | `KeyError: 'P_Value_Extraction_Method'` at the first assert |

This is the check that was skipped when a column patch silently no-opped earlier
in this project. Every string patch in this round asserted its anchor first.

## Suites

All run with scipy hard-blocked by a `sys.meta_path` finder that raises on
`scipy` and `scipy.*`.

| suite | scenarios |
|---|---|
| `test_kernel.py` | 222 |
| `test_grid_engine.py` | 132 |
| `test_bar_reader.py` | 42 |
| `test_mark_readers.py` | 43 |
| `test_integration.py` | 19 |
| `test_reproducibility.py` | 2 |
| **total** | **460** |

New since the last package: **+5** grid scenarios (the broadened point-file rule,
including the two negative cases that must still pass) and **+14** reader
scenarios (the adapter contract and the reader→adapter→gate chain).

`crosscheck_id323.py` exits 0: max |Δmean| 0.50 px, max |Δdispersion| 2.50 px over
72 bars, two independent primitives.

`build_id323.py` — 2 figures, 14 grid rows, 12 units, 107 values, **2 problems**,
both the same known hole: `FACTOR_LEVEL_MISSING` / `FACTORIAL_CELL_MISSING` for
`TIMEPOINT=DI19` on FIG2 DAP, where two bars overlap past separating. That is
fail-closed working — the cell is named, not guessed.

## What is in the package

| File | Role |
|---|---|
| `kernel.py` | shared primitives: null tokens, vocabularies, normalizers |
| `grid_engine.py` | the four-grain validator — figures / grids / units / values |
| `mark_readers.py` | non-bar readers, `summarize_association`, the value adapter |
| `bar_reader.py` | colour bar panels, outline-centre tops, stem-confirmed caps |
| `crosscheck_id323.py` | second independent reading of one figure, different primitive |
| `build_id323.py` | worked example: raster → four CSVs → gate |
| `make_wpd_project.py` | emit a WebPlotDigitizer project from a calibration |
| `make_bar_fixture.py` | synthetic bar rasters with known truth |
| `forward_test_real_monochrome.py` | forward challenge on a publisher raster (not redistributed) |
| `*_TEMPLATE.csv` | the four blank grain templates, generated from the column functions |
| `fixtures/`, `*.jpeg`, `*.png`, `*.tar` | rasters, panel geometry, WPD projects |

## Not in this package, deliberately

`read_monochrome_bar_panel` (BAR_MONO — hatched / solid / open monochrome bars,
found missing during the 397 pilot) stays on the pilot branch. It works on 397
Figure 3 live, but it has no synthetic fixture and no regression scenarios, and
shipping an unhardened reader inside a release whose whole point is that fields
cannot drift silently would be the same mistake in a new place. It comes next,
with a fixture.

## Still open

- 397 Figures 3–4: 12 panels × 4 cells, pending BAR_MONO hardening
- 397 Figures 1, 2, 5: solid-vs-dashed `LINE_MONO`, 8 panels × 24 cells
- 386 Figures 3–4
- ID 323 FIG2 DAP DI19 (1 cell) and 4 unpaired cells need a human reading
- the declarative batch layer (`panel_manifest.csv`, `series_manifest.csv`,
  `position_manifest.csv`, `reader_config`, `run_batch.py`) is designed, not built
