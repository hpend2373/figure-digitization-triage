# Quickstart: one synthetic figure, end to end

`plan.json` is a complete extraction plan for one figure: a colour bar chart of
heart rate in two postures at six sessions, mean ± SD, n = 10. The figure itself
is drawn by `tests/make_bar_fixture.py`, so every true value is known
(`bar_fixture_truth.json` is written beside it).

## As a demonstration

    python3 examples/quickstart/quickstart.py /tmp/fdt-quickstart

Compiles the plan, reads the figure, and ends in `DEMO_OUTPUT_REFUSED`. That is
the expected result: the plan's only reviewer is ORCID's fictional demo record,
and a demonstration identity can never stand behind a poolable value. CI runs
exactly this.

## As your own review

Open `/tmp/fdt-quickstart/bar_fixture.png` after the first run and check that it
has one panel. Then run again as yourself — all four variables or none:

    FDT_REVIEWER_NAME="Your Name" \
    FDT_REVIEWER_ORCID="0000-0000-0000-0000" \
    FDT_INSPECTION_DATE=YYYY-MM-DD \
    FDT_REGISTRATION_DATE=YYYY-MM-DD \
    python3 examples/quickstart/quickstart.py /tmp/fdt-quickstart

The run is now `ATTESTED` and stops at `MACHINE_QC_PASSED` with:

    out/review_queue.csv        one row per panel; Review_Mode says what to open
    out/review/P1_overlay.png   every mark the reader read, labelled with its cell
    out/value_review.csv        identifiers pre-filled, answers blank

The rest is yours, as in a real review ([docs/REVIEW_RUNBOOK.md](../../docs/REVIEW_RUNBOOK.md)):
look at the overlay, fill in `value_review.csv`, then

    python3 fdt/review_preflight.py /tmp/fdt-quickstart/out --review /tmp/fdt-quickstart/out/value_review.csv
    python3 fdt/finalize_batch.py /tmp/fdt-quickstart/out --review /tmp/fdt-quickstart/out/value_review.csv

and compare `figure_values_accepted.csv` with `bar_fixture_truth.json`.

## Writing a plan for your own figure

Copy `plan.json` and change, per figure: the document and figure records (who
inspected them and when), the panel's `box` and `y_ticks` (pixel rows of printed
tick values), the `series` (what each colour or fill means) and `positions` (what
each x position means), and the unit's outcome, unit, dispersion type, n and the
quoted source of the error-bar definition. `compile_plan.py` refuses a key it
does not read and names the nearest one it does.
