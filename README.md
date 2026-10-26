# figure-digitization-triage (fdt)

A reproducible pipeline for reading numbers off published figures for a
systematic review, with quality control that fails closed. Many studies report
their outcomes only as plots, and a number read off a plot is only usable if the
pipeline that produced it can say exactly what it did: which raster, which
calibration, which reader, which environment, and which person looked at it.

It was built for a review of cardiovascular responses to spaceflight and
head-down bed rest, but nothing in it is specific to one paper or one field:
every check is keyed on a declared data type or dimension, never on a
publication.

```
PDFs ─▶ draft inventory ─▶ panels a person drew ─▶ axes & series a person confirmed
     ─▶ one extraction plan per paper ─▶ manifests ─▶ values that passed machine QC
     ─▶ a person reviews the overlays ─▶ figure_values_accepted.csv
```

## Three rules

1. **No per-publication exception rules.** Validation is one factorial grid keyed
   on declared dimensions; exceptions exist per data type, never per paper.
2. **Identity is declared, never inferred.** A series is a factor level because
   the plan says so. When a reader cannot resolve a mark, the cell stays empty
   and the gate names the hole.
3. **Fail closed, and loudly.** Every panel ends in exactly one state, and
   anything short of a pass goes to a queue with its reason. Machine QC is not
   approval: only `finalize_batch.py`, given a registered person's review, writes
   values you may pool.

## Install

Python 3.11 and Node.js (for the review pages' logic tests).

    git clone https://github.com/hpend2373/figure-digitization-triage
    cd figure-digitization-triage
    python3 -m pip install -r requirements-lock.txt     # the exact versions results are reproducible on
    # only for reading PDFs (intake) and OCR of tick labels:
    python3 -m pip install -r requirements-intake.txt
    sudo apt-get install poppler-utils tesseract-ocr

No scipy: the statistics are written in NumPy so a missing scipy cannot silently
change a number.

## Try it in two minutes

    python3 examples/quickstart/quickstart.py /tmp/fdt-quickstart

This draws a synthetic bar chart (heart rate, two postures, six sessions,
mean ± SD — every true value known), compiles its plan, and reads it. Run as is,
it ends in `DEMO_OUTPUT_REFUSED`: the plan's only reviewer is a demonstration
identity, and a demonstration identity cannot stand behind a poolable value.
Set your own name, ORCID and dates and it stops at `MACHINE_QC_PASSED` with an
overlay for you to review — see [`examples/quickstart`](examples/quickstart/).

## Use it on your papers

Follow **[docs/PROCEDURE.md](docs/PROCEDURE.md)** — nine stages from PDFs to
accepted values, each marked with who does it (a script, an AI agent, or a
person). The human review itself is in
[docs/REVIEW_RUNBOOK.md](docs/REVIEW_RUNBOOK.md). The core of the last two
stages is:

    python3 fdt/compile_plan.py PLAN.json MANIFESTS --file-root RUN
    python3 fdt/run_batch.py MANIFESTS OUT --file-root RUN --doc-root PDFS
    python3 fdt/finalize_batch.py OUT --template
    #  a person opens what each row of OUT/review_queue.csv names, fills OUT/value_review.csv
    python3 fdt/review_preflight.py OUT --review OUT/value_review.csv
    python3 fdt/finalize_batch.py OUT --review OUT/value_review.csv

Success is `OUT/figure_values_accepted.csv` beside a `finalize_stamp.json` whose
`Status` is `FINALIZED`. Nothing else is a result.

**Keep papers, figures, runs and review answers outside the clone.** This
repository is public, publisher material is not redistributable, and the test
suite refuses a tracked PDF or any picture outside `tests/`.

## For AI agents

[`SKILL.md`](SKILL.md) is the whole protocol as an agent reads it, installable
as a skill: the run contract, every review mode and failure state, what an agent
may do without the person, and the defect behind each rule. An agent may run
commands, propose, and record an independent check that agrees under a standing
approval; it never fills in a person's review answer, signature, date or
confirmation.

## Repository layout

    fdt/            the pipeline: every command is `python3 fdt/<script>.py` (--help for options)
    fdt/sheet/      the panel-count contact sheet used during intake
    templates/      every CSV schema, generated from the code's column functions
    docs/           PROCEDURE.md, REVIEW_RUNBOOK.md and the review guides
    examples/       quickstart: a synthetic figure through compile -> run -> review
    tests/          the suites (standalone scripts) and their synthetic fixtures
    SKILL.md        the protocol for agents

## Tests

    bash .github/run_suites.sh                                   # every Python suite
    for t in tests/test_*.mjs tests/sheet/test_*.mjs; do node "$t"; done

Every suite is a standalone script that exits non-zero on its first failure and
prints one `FDT_SCENARIOS_RUN=N` line. CI runs them in two environments: the
pinned core with the PDF backends removed, and the full intake profile.

## Attestation, briefly

`reviewer_registry.csv` records who inspected a figure, with a contact (ORCID)
and `Reviewer_Record_Type` ∈ `HUMAN | DEMO_IDENTITY`. A run resting on a demo
identity is `DEMO_ONLY` and never writes accepted values. An approval is bound to
`Review_Subject_SHA256` — the values, every manifest, the raw marks and the
environment — so changing any of them after review makes it `APPROVAL_STALE`
rather than inherited. `Human_Attestation` is a declared record, not a
cryptographic signature: it buys traceability, not proof of authorship.

## 한국어 요약

체계적 문헌고찰에서 **그림으로만 보고된 수치**를 읽어 내는 파이프라인입니다.
읽은 값마다 어느 그림·눈금·판독기·환경에서 나왔고 누가 확인했는지가 남으며,
근거가 부족하면 값을 만들지 않고 이유와 함께 대기열로 보냅니다.

- 처음이면 `python3 examples/quickstart/quickstart.py /tmp/fdt-quickstart`로 합성 그림
  하나를 끝까지 돌려 보세요.
- 실제 논문에는 [docs/PROCEDURE.md](docs/PROCEDURE.md)의 9단계를 따르세요. 단계마다
  누가(스크립트·AI·사람) 하는지 적혀 있습니다.
- 사람이 하는 검토는 [docs/REVIEW_RUNBOOK.md](docs/REVIEW_RUNBOOK.md)에 있습니다.
  검토자·날짜·확인 칸은 사람만 채웁니다.
- 원문 PDF·그림·실행 결과·답안은 저장소 밖에 두세요(공개 저장소입니다).
