# The procedure, step by step

This is the order of work for digitizing figures from a set of papers, from the
PDFs to a file of accepted values. Each step names **who** does it:

- **AI** — a script or an AI agent may do it unattended.
- **Person** — a human looks at the figure and decides. No script or agent
  fills in a person's answer, signature, date or confirmation.
- **AI → Person** — the AI proposes, the person confirms or corrects.
  An independent second AI check that agrees with the proposal may be recorded
  without the person, but only as an *approved observation* under a standing
  approval the person gave (see `SKILL.md`, "What the AI carries on without the
  person"); disagreements always go to the person.

Every command is `python3 fdt/<script>.py`; add `--help` to any of them for the
full option list. The protocol behind each step — what each check prevents and
why — is in [`SKILL.md`](../SKILL.md). Try the last two stages on a synthetic
figure first: [`examples/quickstart`](../examples/quickstart/).

## 0. Set up

    git clone https://github.com/hpend2373/figure-digitization-triage
    cd figure-digitization-triage
    python3 -m pip install -r requirements-lock.txt            # the exact versions results were produced on
    python3 -m pip install -r requirements-intake.txt          # only for the PDF intake steps
    sudo apt-get install poppler-utils tesseract-ocr           # only for the PDF intake and tick OCR
    bash .github/run_suites.sh                                 # the check that the clone is whole

**Keep your papers, figures, runs and answers outside the clone.** The
repository is public; publisher PDFs and figures are not redistributable, and the
suite refuses to track them. Below, `PDFS/` is your folder of papers and `RUN/`
is a working folder for one corpus, both outside the repository.

## Overview

| # | Stage | Who | Main commands | What comes out |
|---|---|---|---|---|
| 1 | Intake | AI | `corpus_intake.py`, `caption_fulltext.py` | a draft inventory of figures, crops and captions |
| 2 | Count and draw panels | Person | `fdt/sheet/`, `panel_page.py` → `record_panels.py` → `panel_to_page.py` | the panels a person drew, as 600 DPI rasters |
| 3 | Axes and series | AI → Person | `propose_run.py` → `axis_series_page.py` → `route_axis_series.py` → `record_geometry.py`, `record_identity.py` | confirmed ticks, frames, x labels, series |
| 4 | Error bars and dispositions | AI → Person | `errorbar_review_page.py` → `record_errorbar.py`; `decision_page.py` → `record_decisions.py`, `record_*.py` | what the error bars are; which panels are targets |
| 5 | Plans, and what is left | AI → Person | `make_plan.py`, `bundle_items.py` → `cross_check.py` → `bundle_page.py` → `bundle_route.py` → `census_copy.py` | one extraction plan per paper; one page of remaining questions |
| 6 | Compile and read | AI | `compile_plan.py` → `run_batch.py` | values that passed machine QC, overlays, a review queue |
| 7 | Panels no reader can read | AI → Person | supplied readings → `run_batch.py` → `value_page.py` | agent-placed points, confirmed by the person |
| 8 | Review and finalize | Person | `finalize_batch.py --template` → `review_preflight.py` → `finalize_batch.py` | `figure_values_accepted.csv` — the only file to pool from |
| 9 | After the numbers | AI → Person | [`ANALYSIS_RECONCILIATION.md`](ANALYSIS_RECONCILIATION.md), [`SYNTHESIS_HANDOFF.md`](SYNTHESIS_HANDOFF.md) | linkage to the analysis, synthesis inputs |

## 1. Intake — AI

    python3 fdt/corpus_intake.py PDFS/*.pdf --out RUN --render 200
    python3 fdt/caption_fulltext.py RUN --pdf-root PDFS

A **draft** inventory: one row per figure the PDF's text says is there, a crop
of where it probably is, and the whole caption with what it says the error bars
are (SD, SEM, 95% CI, or nothing). Nothing here is a decision; every crop is a
"look here", not a measurement.

## 2. Count and draw panels — Person

No software can count the panels in an arbitrary published figure, so the
inventory reduces to a person having opened it and looked.

- **Count** — `fdt/sheet/` builds a contact sheet where a person enters, per
  figure, how many panels it has; rows whose crop is wrong are blocked from
  taking a number. See [`fdt/sheet/README.md`](../fdt/sheet/README.md).
- **Draw** — on the panel page a person draws a box around every panel and says
  what is drawn in it (bars, lines, scatter, not data):

      python3 fdt/panel_page.py --run RUN --queue RUN/seg/dig.csv --out RUN/seg/panels_1.html [--proposals RUN/seg/boxes.jsonl]
      python3 fdt/record_panels.py --run RUN --queue RUN/seg/dig.csv --answers panel_answers.csv --when YYYY-MM-DD
      python3 fdt/panel_to_page.py --run RUN --decisions RUN/seg/panel_decisions.csv --pdfs RUN/seg/_pdf_locations.json --out RUN/seg/regions600

  `--proposals` is optional: automatic panel boxes, if you have them, are shown
  as suggestions. `panel_to_page.py` moves the drawn boxes from the 200 DPI crops
  onto 600 DPI renders of the page.

## 3. Axes and series — AI proposes, Person confirms

    python3 fdt/propose_run.py geometry --run RUN --regions REGIONS.csv --out GDIR
    python3 fdt/propose_run.py identity --run RUN --regions REGIONS.csv --geometry GDIR/geometry_proposal.csv --out IDIR
    python3 fdt/axis_series_page.py --run RUN --geometry GDIR --identity IDIR --proposals PROPOSALS.json --out PAGE.html

The proposers read the frame, the tick rows, what the y axis says (OCR, checked
against the tick grid), the x labels, the legend entries matched to the plot's
colours, the y title split into outcome and unit, and n from the caption — or
refuse. The page puts both proposals on one card per panel. The person answers
"as proposed", "needs fixing" or "hold", and names the two things nobody can
read off the picture: what the x axis is and what the series are.

    python3 fdt/route_axis_series.py route --answers ANSWERS.csv --proposals PROPOSALS.json --geometry GDIR --identity IDIR --out OUT
    python3 fdt/record_geometry.py --proposals GDIR --answers OUT/geometry_answers.csv --when YYYY-MM-DD
    python3 fdt/record_identity.py --proposals IDIR --answers OUT/identity_answers.csv --when YYYY-MM-DD

Record on a copy of the run first (`census_copy.py`, stage 5) when the answers
come in bulk. Separate pages for the two cards also exist
(`geometry_page.py`, `identity_page.py`).

## 4. Error bars and dispositions — AI proposes, Person confirms

    python3 fdt/errorbar_review_page.py --run RUN --pdf-root PDFS --out RUN/errorbar_review.html
    python3 fdt/record_errorbar.py --run RUN --answers errorbar_found.csv --pdf-root PDFS
    python3 fdt/decision_page.py --run RUN --plans RUN/plans_DATE --out RUN/decisions.html
    python3 fdt/record_decisions.py --run RUN --plans RUN/plans_DATE --answers RUN/figure_decisions_in.csv --when YYYY-MM-DD

The error-bar definition decides the weight of every value in a meta-analysis,
so it is quoted from the paper, never assumed. Other small gates record a
person's answer the same way (`--run --plans --answers --when`):
`record_dispositions.py` (a figure's disposition), `record_outcomes.py` (a
panel's outcome, or "not a target"), `record_legends.py` (which panels share a
legend), `record_inventory.py` (figure and panel counts), `record_shape.py`
(the scale a panel's values are on), `record_block_reviews.py` (blocked draft
rows looked at again).

## 5. Plans, and what is left — AI assembles, Person answers what is left

    python3 fdt/make_plan.py --run RUN --out PLANS --crop-root RUN --run-date YYYY-MM-DD
    python3 fdt/worklist_page.py --run RUN --plans PLANS --out RUN/worklist.html

`make_plan.py` writes one typed extraction plan per paper from everything
confirmed so far, and names every panel still missing an answer in
`plan_panels.csv`. What the census of those plans leaves open is asked **once,
on one page, with a proposal on every line**:

    python3 fdt/bundle_items.py --census CENSUS/ --run RUN --plans PLANS/ --work WORK/ --spec WORK/spec.json
    python3 fdt/cross_check.py brief --spec WORK/spec.json --out BRIEF.json     # a second check that never saw the proposals
    python3 fdt/cross_check.py split ...                                         # agreed + HIGH + evidenced -> recorded as approved observations
    python3 fdt/bundle_page.py WORK/person_spec.json --out PAGE.html --items ITEMS.json   # only what is left, for the person
    python3 fdt/cross_check.py merge ...
    python3 fdt/bundle_route.py --items ITEMS.json --answers bundle_answers.csv --out ROUTED
    python3 fdt/census_copy.py --run RUN --routed ROUTED --when YYYY-MM-DD --reviewers reviewers.json --out COPY

`census_copy.py` writes the answers through the real gates on a **copy** of the
run and runs the plan census before and after, so the effect of the answers is
seen before anything real is written. Then the same answers go through the
`record_*.py` gates on the run itself. Small repair tools, run by hand once
approved: `clip_frames.py`, `rehash_moved_pages.py`, `move_panels.py`.

## 6. Compile and read — AI

    python3 fdt/compile_plan.py PLANS/plan_<paper>.json MANIFESTS --file-root RUN
    python3 fdt/run_batch.py MANIFESTS OUT --file-root RUN --doc-root PDFS

`compile_plan.py` writes the eleven manifests (never write them by hand).
`run_batch.py` reads every declared panel, gates the values against the declared
grid, and ends every panel in exactly one state. It stops at
**`MACHINE_QC_PASSED`**, which means the gate found nothing wrong — not that
anybody looked. What it could not do is in `manual_queue.csv` with the reason;
cells whose number was not read off the ink are in `method_blocked_cells.csv`.

## 7. Panels no reader can read — AI reads, Person confirms

A panel routed to MANUAL (no released reader separates its series) is read by an
AI agent: it places points on the 600 DPI raster in
`seg/readings600/supplied_readings.csv` (schema:
[`templates/supplied_readings_TEMPLATE.csv`](../templates/supplied_readings_TEMPLATE.csv)),
`make_plan.py` / `compile_plan.py` carry them into the manifests, and
`run_batch.py` turns each pixel into a value through the panel's calibration.
The person then looks:

    python3 fdt/value_page.py --run OUT --out OUT/values.html

A symbol the agent could not place can be placed by the person in the same file
(`Reader_Kind=PERSON`). See `SKILL.md`, "A panel no reader can read".

## 8. Review and finalize — Person

Follow [`REVIEW_RUNBOOK.md`](REVIEW_RUNBOOK.md). In short:

    python3 fdt/finalize_batch.py OUT --template                       # pre-filled review files
    python3 fdt/review_preflight.py OUT --review OUT/value_review.csv  # before review: exits 2, bundle must be clean
    #  the person opens what each panel's Review_Mode names and fills value_review.csv
    python3 fdt/review_preflight.py OUT --review OUT/value_review.csv  # after review: must exit 0
    python3 fdt/finalize_batch.py OUT --review OUT/value_review.csv    # -> figure_values_accepted.csv

**Success** is `OUT/figure_values_accepted.csv` beside an
`OUT/finalize_stamp.json` whose `Status` is `FINALIZED`. Nothing else is a
result. The approval is bound to the exact values, manifests, marks and
environment it was given on: change any of them and it is `APPROVAL_STALE`.

## 9. After the numbers

Linking accepted figures to an existing analysis, checking duplicate
measurements and preparing synthesis inputs:
[`ANALYSIS_RECONCILIATION.md`](ANALYSIS_RECONCILIATION.md), then
[`SYNTHESIS_HANDOFF.md`](SYNTHESIS_HANDOFF.md). Source checks for missing or
overlapping markers: [`MARKER_REVIEW.md`](MARKER_REVIEW.md). Factor names,
frames and review-state repairs:
[`IDENTITY_GEOMETRY_REVIEW.md`](IDENTITY_GEOMETRY_REVIEW.md).
