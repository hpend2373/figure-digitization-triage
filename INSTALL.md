# figure-digitization-triage — v7.21 (full package)

The declarative execution layer, plus the monochrome bar reader, plus the
point-file hardening. Full package, not a patch.

**v7.7 adds physical-source completeness.** A reader manifest may split one
publisher figure into outcome-specific virtual figures, but it can no longer use
those splits to claim that the source was fully reviewed. Two mandatory source
manifests inventory every visible panel, enforce verified counts, retain explicit
non-target/manual/no-reader dispositions, and emit a one-row-per-panel coverage
ledger. Publication 397 now records all 36 visible panels although only 14 have
configured run panels.

**v7.6 is the first real pilot: publication 397, all five figures, one run.**
Two defects it found are fixed below. **v7.5 closed the two defects from the
v7.4 review**, on top of the three from
v7.3 and the four from v7.2. Every fix in every round was reverted in a scratch
copy and the suite re-run, so no scenario is decoration:

| reverted | scenarios that fail |
|---|---|
| manifests loaded before the clear-up | 18 |
| loader raising `SystemExit` again | 12 |
| commit marker not ordered last | 1 |
| no withdrawal after a failed promotion | 6 |
| no verify pass after promotion | 1 |
| clear-up moved back to the end of a run | 8 |
| no stamp on a rejected run | 4 |
| unit state keyed by the last panel seen | 1 |
| one values file, no status columns | 6 |
| `n_slots` back on BAR_MONO | 3 (including the introspection test) |
| option range checks removed | 4 |
| LINE_MONO accepting line style alone | 1 |

## HIGH (v7.8 review) — the attestation check could not spell the reviewer's name

`Inspector` was free text, and the rule that guarded it was

    len(re.sub(r"[^0-9A-Za-z]", "", who)) < 2

which is a statement that reviewers are named in the Latin alphabet. It got
both halves of its job backwards:

| written in `Inspector` | v7.8 | v7.9 |
|---|---|---|
| `김민엽`, `李明`, `홍길동` | **rejected** | registers |
| `AI`, `BOT`, `LLM`, `Codex`, `Claude` | **accepted** | refused |

Stripping every non-ASCII character left the empty string, so the person who
actually did this inventory could not record that they had — while five names
for the software that cannot do it passed on length alone.

Both halves are now structural rather than lexical.

**`reviewer_registry.csv`** is a new mandatory manifest, and `Reviewer_ID` on
the two source manifests is a foreign key into it (`REVIEWER_NOT_REGISTERED`).
A name, a contact and a human attestation are declared once, by a registered
registrar, instead of being retyped per row where nothing connects two
spellings of the same person. `Inspector` is gone; a manifest still carrying
the column is refused with `LEGACY_INSPECTOR_COLUMN` rather than having it
silently ignored.

**Names are compared after NFKC normalization, on Unicode `isalnum()` tokens.**
`김민엽`, `李明`, `홍길동`, `Ólafur Þórsson`, `О. Иванов` and `ＫＩＭ` all register.

The registry validates what can actually be validated: `Contact_Type` is EMAIL
or ORCID, an ORCID must pass its ISO 7064 MOD 11-2 check digit, and
`Human_Attestation=AUTOMATED_AGENT` is a legal declaration that is then refused
(`REVIEWER_NOT_HUMAN`) — an agent may be recorded, but it may not hold the
attestation.

The name-token check is a **courtesy, not the guarantee**, and the code says so.
It fires only when every letter-bearing token of a name is a software word, so
`Claude Bernard` registers and a bare `Claude` does not; `GPT-4` and `gpt4` are
caught by stripping trailing digits. That list is unbounded by construction and
anyone determined to write a person's name where there is no person will
succeed. What makes the attestation *auditable* is `Reviewer_Contact` plus a
registered `Human_Attestation` — a named, contactable person on the hook — not a
denylist.

**`Human_Attestation` is a declared enum, not a cryptographic signature.** It
records that someone typed `HUMAN_CONFIRMED` into a registry row alongside a
contact, and its whole value is that the row can be traced back to a person who
can be asked. It does not prove authorship of the row and is not evidence in any
stronger sense. If this package ever needs a real signature — a detached
key over the registry, or an ORCID-authenticated attestation — that is a new
field, not a reinterpretation of this one.

41 scenarios. Reverting the ASCII rule fails 6; removing the registry fails 32.

## Release gate (v7.16 review) — five conditions, all met

The review named five conditions for a 116-publication production batch. Each
is below with what was actually wrong.

### 1. CI green

`run_batch.py` returned exit 1 whenever `qc_problems > 0`. Publication 397 is
in the package *because* its dispersion definition is unresolved, so the one
step that proves the plan-to-run path works reproduced 108 expected problems
and CI called the whole workflow red.

A QC problem is a result, not a failed run. Exit 0 now means the run completed;
`run_stamp.json` carries the verdict. The CI step asserts the expected stamp —
`RAN`, 48 read, 0 machine-QC-passed, 108 problems — rather than a bare exit
code, because a green that did not read 48 values would be worse than a red.

The CLI banner also still said `ACCEPTED 0` and `pool from
figure_values_accepted.csv`, for a file this module has not written since 7.13.

### 2. The approval is bound to the values

`Panel_Fingerprint` hashed eight fields and its docstring claimed an approval
expired whenever "the image, the config, the reader or the pipeline" changed.
The guarantee was narrower than the sentence: it covered none of the Mean, the
`Cell_Key`, what `CONTROL` and `TREATED` mean, the panel box, the ticks, the
unit and grid manifests, the OpenCV version, or any artifact. An approval
survived swapping two factor labels and editing a value.

`Review_Subject_SHA256` covers the run row, every manifest hash, the
environment record, the raw mark file, the WPD project, and every machine-QC
value of the panel with its cell key. Manifests are taken whole rather than
sliced per panel — that expires some approvals that did not need to expire,
which is the right way round: re-approving costs an afternoon, a stale approval
surviving costs the analysis.

### 3. The finalizer verifies the run

It re-read four files to decide whether a value was poolable and trusted every
one, and `--manifests` took any directory. So: approve a correct overlay, edit
a Mean, finalize — the edited number came out `HUMAN_APPROVED`.

`run_stamp.json` records `Output_SHA256` for all four files and
`Reviewer_Registry_SHA256`. Both are recomputed before any decision is read;
either mismatching is `RUN_ARTIFACT_MODIFIED` / `REVIEWER_REGISTRY_CHANGED` and
no accepted file is written.

### 4. Finalization is atomic

The accepted file was written directly and the stamp after it, so a process
killed between the two left poolable values with a stale stamp or none — the
shape `run_batch` already fixed. Finalization now stages, records the accepted
file's own SHA-256 and the source run stamp's in the finalize stamp, and
promotes with the accepted file last as the commit marker. Fault injection at
each step.

### 5. Duplicate reviews are order-independent

Two decisions for one panel resolved to whichever came first, so
APPROVED-then-REJECTED approved and REJECTED-then-APPROVED did not. A
scientific result must not depend on CSV row order. A duplicated `Panel_ID`
now voids every decision for that panel, and a `Review_ID` used twice voids the
rows that share it.

**80 scenarios in `test_finalize.py`.** Reverting the subject hash fails 9; the
artifact verification 9; the duplicate rule 6.

Also from the same review: the run records `Manifest_Dir`, so the finalizer
finds the registry when the README's own three commands put manifests beside
the run rather than inside it; and `opencv-python` is out of the lock file,
since it and `opencv-python-headless` both provide `cv2`.

## v7.21 review — a scatter panel is all or nothing, and a run is portable

### P0. A sparse series made a panel lose the series that read cleanly

`_scatter_outcome` classified every series before writing — but the `short`
exit ran *after* the write block. So on a two-series panel:

    Series A: 10 points -> planned, point file written, records built
    Series B:  2 points -> short
    -> MANUAL_POINT_READ, carrying no values, no raw, no artifacts

Seven consequences, all reproduced: A's point JSON sat in `raw/` named by no
ledger and referenced by no run row; `Cells_Read` said 1 while
`figure_values_raw.csv` had none; and `missing` held only B — so
`manual_queue_cells.csv` told a hand digitizer to read series B and said
nothing about series A, whose numbers had just been discarded. Following the
queue, series A disappears from the review entirely.

There is no channel for merging a partial automatic result with a later hand
reading, so a partial result is not a result. Every refusal now happens before
a single file is written, and reports the **whole** panel as unread with every
declared cell queued. Revert: 4.

### P1. A run directory was portable only in its ledger

v7.20 made `panel_artifacts.csv` run-relative. Everything else still recorded
the path the run happened to have:

    review_queue.csv        Overlay_File, WPD_Project_File, Raw_Data_File
    figure_values_*.csv     Point_Data_Reference, WPD_Project_File
    run_manifest.csv        Raw_Data_File, WPD_Project_File

and the finalizer copies machine-QC rows straight into the accepted file. So a
finished dataset handed to another folder or another machine looked complete
while every provenance link in it pointed at a directory that exists nowhere.
The v7.20 move test only proved finalization succeeded; it never opened a queue
artifact or resolved an accepted row's reference afterwards.

Every output-facing path is now recorded relative to the run directory, and the
grid gate takes a `run_dir` root alongside `file_root` so it can still check
they exist. The move test now finalizes, then resolves every queue overlay and
every accepted `Point_Data_Reference` and `WPD_Project_File` in the new
location. Reverts: value paths 5, overlay path 4, the gate's run root 11.

`Artifact_ID` indirection was considered and not adopted. It would give a join
key, not new integrity: every artifact is already hashed in the ledger and every
one of a panel's artifacts is already inside `Review_Subject_SHA256`, so an
accepted row's point file is content-bound through the approval. Relative paths
close the portability gap; a second identifier for the same thing is a second
place to drift.

### P1. `SKILL.md` told an agent to open a file that may not exist

The run steps still said "open `review/<Panel_ID>_overlay.png` for every row",
while the code has allowed `Review_Mode=WPD_ONLY` since v7.20. The review step
is now a branch — mode, what to open, and what "approve only if" means for each
— with an explicit *do not approve* row for a missing artifact. The README's
"each passing panel gets an overlay PNG" is corrected the same way, and the
relative-path rule is stated where a reviewer will hit it.

### P2. The finalizer parsed before it verified

`figure_values_machine_qc.csv` was parsed, then hashed. A file with a broken
quote raised out of `pd.read_csv` — after the previous accepted file and stamp
had already been deleted, so the run ended with neither a result nor a stamp
saying why, against a system rule that every failure is a structured stamp.
Bytes are hashed first; parsing failures on verified bytes are
`RUN_NOT_FINALIZABLE` with a stamp. Malformed `figure_values_machine_qc.csv`,
`review_queue.csv` and `panel_artifacts.csv` are each a scenario. Revert: 4.

### P2. Overlay failures leaked between runs

`review_overlay._FAILURES` is module state with no reset, and an agent working
through 116 publications in one process is the normal case — so the second
run's stamp inherited the first run's "3 overlays could not be drawn", naming
panels it never saw. `reset_failures()` at the top of every run. Revert: 2.

### Documents

`MIGRATION.md` still said `run_batch.py` writes `figure_values_accepted.csv`,
which stopped being true at 7.13; it now lists every values-grain output with
which module writes it, and says plainly that the accepted file is the
finalizer's. `figure_extraction_template_v7.csv` is the flat template of the
pre-batch hand path — it is generated from `fig_template_columns()` and now
checked against it by name, since it does not follow the `*_TEMPLATE.csv`
convention the sweep globs.

## v7.20 review — the scatter path, and what a queued panel promises

### 1. A scatter was queued for review with no picture (HIGH)

`_scatter_outcome` was never passed a review directory, so a scatter reached
`review_queue.csv` with `Overlay_File=""` and no `OVERLAY` row in the artifact
ledger — while the protocol said, for every queued row, "open
`review/<Panel_ID>_overlay.png` and approve only if each mark sits on the mark a
reader would give it". The instruction pointed at nothing. The overlay code has
handled `point_px_x`/`point_px_y` since it was written; nobody called it.

Scatter panels now draw their cloud, unlabelled — thirty labelled crosses cover
the cloud they exist to show — and the overlay joins the ledger like any other
artifact, so tampering with it is `RUN_ARTIFACT_MODIFIED`.

The contract is now explicit rather than assumed. Every queued row carries
`Review_Mode` (`OVERLAY` or `WPD_ONLY`), and the finalizer refuses an approval
whose declared artifact is not in the run's own ledger
(`REVIEW_ARTIFACT_MISSING`) or whose mode is blank (`REVIEW_MODE_UNKNOWN`).
`WPD_ONLY` exists because `draw_panel_overlay` deliberately never raises — a
picture that cannot be painted must not fail a panel that produced values — so
any panel can legitimately arrive with a project and no overlay. What none may
do is arrive claiming a review nobody can perform.

The runner has no separate demotion for "neither artifact", because there is no
such panel: a digitized value with no saved project is already
`MISSING_PROVENANCE` at the gate. An unreachable branch is decoration, so it is
not there; the finalizer refuses a blank mode instead of trusting that ordering.

Reverts: the scatter overlay 3, the declared mode 1, the finalizer's check 3.

### 2. Overplotting with nothing to check the count against (HIGH)

The audit detected a blob too wide to be one marker and set
`Overplotting_Possible=TRUE` — and the runner computed the association anyway,
because only a count *mismatch* halted it. Where the paper gives no n there is
no count to mismatch. Reproduced: a ten-point cloud with one doubled marker,
`N_Outcome` blank, r = 0.9915, `MACHINE_QC_PASSED` — off a cloud that may have
had points hidden inside points, and (before item 1) with no overlay for anybody
to notice.

`Overplotting_Possible=TRUE` **with** `Point_Count_Agreement=NO_SOURCE_N` now
halts the calculation. A matching declared n still passes: detected == expected
is exactly what makes a merged blob tolerable, and blocking it would send every
figure with variable marker sizes to manual for no reason. Revert: 2.

### 3. The shipped review template was two schemas old

`value_review_TEMPLATE.csv` still offered `Panel_Fingerprint`, gone since 7.16.
Anyone starting from it got `REVIEW_SCHEMA_INCOMPLETE` — safe, but the shipped
artifact contradicted the running code, and 1275 scenarios passed because
nothing tested a static file.

It is regenerated, and the suite now checks **every** `*_TEMPLATE.csv` on disk
against its column function, with an unmapped template counting as a failure —
so a new template cannot ship without a function behind it. Thirteen templates,
one check. Revert: the suite aborts naming the missing and stale columns.

### 4. `figure_views` values

The outer object was checked and its values were not, while the compiler does
`views.get(view, {}).get("caption")`. A view written as a bare caption string —
the obvious way to write it — validated clean and raised `AttributeError` inside
the compiler. Values must be objects and keys must be strings. Revert: 5.

### 5. The artifact ledger depended on the working directory

Paths were recorded as the run saw them and checked with `os.path.exists`. Run
with a relative output directory, finalize from anywhere else, and every
artifact reported `RUN_ARTIFACT_MODIFIED` — a false refusal, safe but
unactionable, and schedulers and agents change working directory as a matter of
course.

The ledger records paths relative to the run directory, and the finalizer
resolves them against it, refusing anything that escapes
(`ARTIFACT_PATH_OUTSIDE_RUN`). The review-mode check reads the ledger rather
than the queue's own path column for the same reason. A whole run directory can
now be moved and finalized from an unrelated working directory. Revert: 2.

### 6. Point files a run wrote and did not admit to

`_scatter_outcome` wrote each series' point JSON inside the loop, so a
two-series panel whose second series could not be reconciled returned
`MANUAL_POINT_READ` with the first series' file already on disk — named by no
ledger, referenced by no run row, sitting in `raw/` looking like data. Every
series is now audited and summarized before anything is written. Revert: 2.

### 7. The skill was an addendum, not a skill

`SKILL_ADDENDUM.md` began "sections to add — insert after…", so what an agent
installed depended on somebody pasting it correctly into a document that lived
somewhere else. It is now `SKILL.md`: front matter, the five-line run path, the
success condition, a table of every failure state and what it means, the four
prohibitions, and the file map — then the protocol. The suite asserts it is
standalone, names all three entrypoints, and explains every terminal status;
shipping both files at once is itself a failure, so one cannot go stale behind
the other.

## v7.19 review — the artifact the person approved

### 1. The picture was not part of the approval (BLOCKING, now closed)

`Review_Subject_SHA256` covered the run row, every manifest, the environment
and every machine-QC value of the panel. Its docstring also claimed it covered
"the raw mark JSON, the WPD project and the overlay PNG". It covered the first
two by path off the run row and the overlay not at all — and the finalizer
re-hashed four CSVs and nothing else. So:

    run → replace review/P1_overlay.png with a red rectangle → approve → finalize
    FINALIZED, 8 values accepted

The same for the WPD tar and the raw marks. The numbers could not be edited
after the fact; the picture could, and an approval is a statement about a
picture.

A multi-series scatter was worse still. `Raw_Data_File` is several point-file
paths joined with `;`, and the subject hashed that string as one path — it does
not exist, so it hashed to the empty string and the point clouds were not in
the subject at all.

`panel_artifacts.csv` is a new run output: one row per artifact per panel
(`OVERLAY` / `WPD_PROJECT` / `RAW_MARKS` / `POINT_DATA`) with its SHA-256,
hashed the moment it is written. It is folded into `Review_Subject_SHA256` by
content and by type, it joins `Output_SHA256` in the run stamp — so the ledger
cannot be rewritten to agree with a tampered file — and the finalizer re-hashes
every artifact it names before it reads a single decision. `finalize_stamp.json`
also records `Review_File_SHA256`, so which decisions produced an accepted file
is answerable without trusting that nobody edited the answer.

Reverting: the subject without artifacts fails 5; the finalizer not re-hashing
them 9; the ledger outside the verified set 1; the review-file hash 1.

### 2. `Mask_Key` was accepted unchecked

The three built-in BAR_COLOR masks are keyed `blue`, `red`, `dark`.
`Mask_Key=BLUE` — the obvious spelling, and the way every other vocabulary
column in these manifests is written — validated, reached `masks["BLUE"]`,
raised `KeyError`, and became an `InternalReaderError`. That aborts the **whole
batch**: 115 other publications stop because one manifest cell has capitals in
it. A manifest typo must not be reported as a defect in the reader.

`Mask_Key` is now case-folded and checked against the reader's own list
(`BAD_MASK_KEY`), the runner case-folds what it passes down, and declaring both
`Mask_Key` and `Colour_Hex` is `SERIES_DISCRIMINANT_AMBIGUOUS` rather than a
silent precedence. Reverting the check fails 3; reverting the case-fold fails 6,
including an end-to-end run over the frozen 12-bar fixture.

### 3. One panel could hold two terminal states

A panel that read most of its cells returns `AUTO_PASS` with a missing list, so
it entered the manual queue as `AUTO_PASS`. The grid gate then found the same
missing cells, flipped the run row to `QC_FAILED`, and **appended** a second
queue row — with the removed `Missing_Cells` key, so its count came out blank.
One panel, two rows, contradictory states, and `manual_queue_cells.csv` filing
the missing cells under the state `run_manifest.csv` had already withdrawn.

The queue is keyed by panel and assembled once, after every state revision. A
later pass revises the entry instead of contradicting it, and the missing cells
survive the revision. Reverting fails 6.

### 4. The plan validator now checks shape at every depth

Top-level sections and their rows were checked; what was *inside* a row was not.
`factors: {"ARM": 3}` is an object, so it passed, and then `for level in levels`
raised `TypeError` **inside the compiler**. Seven more shapes did the same: a
`series` of strings, a scalar `positions`, a string in `reader_configs`, a
non-object `options`, an `x_calibration` of bare numbers, a pair of the wrong
length, a NaN pixel.

Every nested structure the compiler walks is checked before it walks it. The
property behind the scenarios is now tested directly: every field in the shipped
plan, given nine wrong values each — over 1500 probes — must be *reported* and
never *raised*. Reverting the shape pass fails 25.

### 5. The point-count audit is a contract, not a courtesy

The five audit fields were validated when present and not required when absent,
so a hand-assembled bundle, a new reader or an adapter that dropped a column
would be judged on the numbers alone — which is the state the audit exists to
end. A `DIGITIZED` association must now carry all five
(`MISSING_POINT_COUNT_AUDIT`); a source that gives no n says so explicitly with
`Point_Count_Agreement=NO_SOURCE_N`, and saying that beside a declared n is
`POINT_COUNT_AUDIT_CONTRADICTS_SOURCE`. A transcribed association has no point
cloud and is not asked.

`N_Outcome` on an association is validated as blank or a positive whole number,
and the audit no longer reaches it through `int(float(n))` — `"10.5"` quietly
became `10` and the comparison then agreed with itself. A declared n the audit
cannot use, it does not use. Reverting the requirement fails 6, the truncation 3,
the `N_Outcome` check 4.

### 6. The agent-facing documents match the code

`SKILL_ADDENDUM.md` (now `SKILL.md`) still described `Panel_Fingerprint`, a field that has not
existed since 7.16, and gave no entrypoint contract at all — an agent following
it would generate the wrong review schema. It now opens with the five-line path
(plan → compile → run → review → finalize), what counts as success, and the
three things never to do. The README's scenario count and 397's declared-cell
count are current.

### 7. A decision with no identifier

A duplicated `Review_ID` voided its rows; a **blank** one did not. So the
identifier a decision is audited by could simply be left out, and every accepted
value carried `Review_ID=""`. `Review_ID` is now required on an approval and
takes the same `SAFE_ID` rule as every other identifier here, since it lands in
a column somebody will join on. Reverting fails 8.

## Items 7–11 of the release-gate review, in the order they were written

### 7. `Slot_Index` without `X_Pixel`

A position row could declare a slot and no pixel. The runner needs a pixel, so
the panel failed later with `MISSING_POSITION_GEOMETRY` — a message about a
missing declaration, for a row that had declared something the reader cannot
use. `Slot_Index` alone is now `UNSUPPORTED_CAPABILITY` at manifest validation,
named for what it is: a capability this package does not have. Reverting fails
1 scenario.

### 8. BAR_COLOR reads any declared colour

The reader had three hard-coded masks — blue, red, dark — so a figure drawn in
green and purple was unreadable by a package whose manifest has had a
`Colour_Hex` column all along. `colour_mask()` takes `#rrggbb` and a tolerance
in Euclidean RGB distance; `colour_masks(rgb, declared=…)` builds one mask per
declared series, and the runner passes what the series manifest says. The three
built-ins remain for manifests that name them by `Mask_Key`. New green/purple
fixture; `test_bar_reader.py` is at 66 scenarios and reverting raises
`KeyError: 'GREEN'`.

### 9. A manual panel declared zero cells

`Declared_Cells` was computed *after* the UNRELEASED, MANUAL and
geometry-failure exits, so every panel that did not run reported `0/0` — the
one number that says how much of the figure is still missing was zero exactly
when it mattered. Publication 397 went from 144 declared cells to **192**: two
manual panels in Figure 5 were reporting 0 for 24 cells each.

While there, `Missing_Cells` was a `;`-joined string of cell keys — and a cell
key is itself `FACTOR=LEVEL` pairs joined by `;`, so the field was ambiguous by
construction. It is now `Missing_Cell_Count`, beside a new
`manual_queue_cells.csv` with one row per missing cell. Reverting fails 5
scenarios.

### 10. The plan validator checks shape before content

`compile_plan.validate_plan()` read `row["panel_id"]` on rows it had not
established were objects, so a plan with a string where a list belonged raised
`TypeError` out of the validator instead of being reported as a bad plan. Shape
checks run first (`PLAN_SECTION_NOT_A_LIST`, `PLAN_ROW_NOT_AN_OBJECT`,
`PLAN_BAD_FIELD_TYPE`), NaN and infinity are rejected as non-finite, and boxes
and ticks are checked structurally. `test_compile_plan.py` is at 80 scenarios,
17 of them malformed structures, each asserting the plan was *reported* and not
*raised*.

### 11. One approximation stood beside five different statistics

Every association p — Pearson, Spearman, Kendall's asymptotic branch, R² and
slope — was the Fisher-z normal approximation, and every row said
`FISHER_Z_APPROX`. The label was accurate and the statistics were not: a
six-point r of 0.94 is p=0.0053 by the t and p=0.0026 by the z. Off by a factor
of two, in the direction that makes a finding look stronger, on exactly the
sample sizes a digitized scatter has.

Each statistic now gets its own test, computed from a hand-rolled regularized
incomplete beta (this package does not import scipy): `PEARSON_T_TEST`,
`SPEARMAN_T_APPROX` (untied only — a tied Spearman keeps its rho and refuses a
p, the rule Kendall already had), `R_SQUARED_F_TEST` from the model F, and
`SLOPE_T_TEST` from the regression's own residual variance. The gate refuses a
method that does not belong to its statistic. The t and F tails are checked
against published critical values, and the three derivations that must coincide
for a one-predictor fit are asserted to coincide.

**`N_Pairs` cannot audit itself.** It is however many contours survived the area
filter — the same number the association was computed from, so it agrees with
itself by construction. Five fields sit beside it: `Expected_N_From_Source` (the
unit's `N_Outcome`), `Detected_Unique_Point_Count` (after coincident centroids
are merged), `Point_Count_Agreement`, `Overplotting_Possible` and
`Series_Mask_Overlap_Count`. A disagreement **halts the calculation**: the panel
goes to `MANUAL_POINT_READ` naming both numbers, rather than publishing an r
computed from a point set that is not the study's. The gate reaches the same
verdict from the file alone, because a hand-edited values file never went
through the runner.

Reverting, one change at a time: the per-statistic tests fail 5 scenarios; the
count halt 4; the gate's per-statistic table 8; the gate's count checks 8; the
mask-overlap detection 2; the coincident-centroid merge 1; the merged-blob
heuristic 1; the carry into the value row 1; the new columns 7.

## P1-9 (v7.11 review) — one typed plan in, eleven manifests out

Everything before this assumed the manifests already existed. Writing them is
the part an agent actually has to do, and asking one to fill eleven CSVs by
hand is asking it to hold the whole foreign-key graph in its head:
`Source_Panel_ID` in two files, `Figure_ID` in three, `Grid_ID` in two, a
SHA-256 typed twice, a calibration typed once as ticks and again as four
numbers. Several of the defects in this review were exactly that.

`compile_plan.py` takes one JSON document per publication and writes all
eleven. The split is the point:

**The plan says what is true about the paper** — which figures exist, how many
panels each has, who counted them, what the caption does and does not say about
the error bars, where the boxes and ticks are, what each series and position
means.

**The compiler says what follows.** Hashes are read off the files, never typed.
A unit's `Axis_Calib_*` is derived from the ticks of the panel that fills it, so
the gate's copy and the reader's copy cannot drift. A `Figure_ID` row is built
from the panels that claim it, with counts reconciled rather than asserted — a
plan cannot say `MATCHED`, because a plan never says `MATCHED`.

What it will not do is invent an observation: it never guesses a panel count,
never fills a blank `Errorbar_Definition_Source`, and never promotes a
`MANUAL_DIGITIZE` disposition because a reader happens to exist.

    python3 compile_plan.py plan_397.json MANIFEST_DIR --file-root .
    python3 run_batch.py MANIFEST_DIR OUT --file-root .

The acceptance test is publication 397. `plan_397.json` describes it once;
compiled and run, it produces **the same 48 values as the hand-written pilot,
cell for cell** — same panel count, same three terminal states, all 36 physical
panels still accounted for, still `ACCEPTED 0` because the paper still does not
say whether its bars are SD or SEM.

46 scenarios. Fifteen ways a plan can be wrong are refused at the plan, against
the thing the author typed, and none of them writes a manifest.

## P1-10 (v7.11 review) — what the run ran on

The stamp recorded the pipeline's own code hash and nothing about the
environment. Contour finding, raster decoding and least-squares fitting all
live in libraries pinned only by a lower bound, and a bar top found at row 312
by one OpenCV and row 313 by the next is a different number in the accepted
file.

Every stamp now carries `Environment`: Python version and implementation, the
platform, and the versions of numpy, pandas, Pillow and OpenCV actually
imported. `requirements-lock.txt` pins the versions the shipped results were
produced on; `requirements.txt` keeps the lower bounds and says plainly that
they are not what a run is reproducible against.

`.github/workflows/suite.yml` installs the lock file, prints the environment,
and runs every test file, every forward test, and the plan-to-run path. A test
asserts CI covers every `test_*.py` in the package — a suite nobody runs is a
suite that will be broken the next time somebody looks.

## P1-12 (v7.11 review) — a defect in a reader is not a difficult figure

Every reader call sat inside `except Exception`, and whatever came out was
reported as `PANEL_GEOMETRY_UNRESOLVED`. A `TypeError` from a misspelled
keyword, a `KeyError` from a renamed field and a genuinely unreadable axis all
reached a human as the same queue row: go and look at this figure again. Over
116 publications that turns a defect in this package into hours of correct
manual work nobody knows was unnecessary — and leaves the defect in place.

Readers now raise a typed error for conditions they were built to meet:

| raised | run state |
|---|---|
| `GeometryResolutionError` (also a `ValueError`) | `PANEL_GEOMETRY_UNRESOLVED` |
| `SeriesIdentityError` | `SERIES_IDENTITY_UNRESOLVED` |
| `UnsupportedCapabilityError` | `NO_READER_AVAILABLE` |
| anything else | **`InternalReaderError` — the batch stops** |

An internal error clears the outputs, writes `Status=INTERNAL_ERROR` with the
exception named, keeps the traceback and exits 5. A bug in a reader is not
confined to the panel that tripped it, and 115 more publications read by the
same broken code is a worse outcome than a loud halt.

18 scenarios by fault injection. Collapsing back to one broad handler fails 14.

## P1-11 (v7.11 review) — the WPD project was recorded per figure

`projects_by_figure.setdefault(Figure_ID, outcome.project)` kept whichever
panel of a figure finished first, and the gate then looked the project up **on
the figure**. On publication 397's Figure 3 that meant every value named the
MEN panel's tar — somebody else's marks, read off somebody else's calibration —
and the other panels' projects were not written down anywhere the gate could
see. The saved project also stored `parse_ticks(...)[:2]`, so a panel
calibrated on four ticks produced an artifact that could not reproduce its own
fit.

`WPD_Project_File` is now a **value-grain** column: each row names the project
that re-derives it, and the gate checks that first, falling back to the figure
only for a hand-assembled bundle. The figure column lists every panel project,
semicolon-separated, and every tick is saved.

7 scenarios. Reverting the grain fails 2; reverting the tick slice fails 1.

## P1-8 (v7.11 review) — BOX_VIOLIN's series contract did not exist

The batch layer requires a series row on every positional panel. The released
box/violin reader returns positions and no series at all. So a two-series box
panel validated, ran, and produced half a grid — every cell of the second
series missing, reported as a difficult figure rather than as a capability this
package does not have.

One declared series is honoured (the reader's positions carry that series'
factor level). Two or more is `UNSUPPORTED_CAPABILITY` before the run, naming
the reader limit and the two ways out: declare one series for the panel, or set
`Panel_Mode=MANUAL` until a grouped box reader ships.

## P1-9 (v7.11 review) — a capability matrix, so the gap is a sentence

`grid_engine` validates four statistic types; the batch layer has raster
readers for three. `BINARY_EVENT` has a source-panel disposition
(`BINARY_EXTRACT`) and a validator and no reader, and `run_batch` sends every
AUTO panel to a raster reader — so a coherent declaration went to a reader that
could not produce it and came back as a difficult figure.

`CAPABILITY_MATRIX` names every statistic the gate validates as either
`AUTO_SUPPORTED` (with which readers) or `VALIDATOR_ONLY` (with what to do
instead). An AUTO panel declaring a `VALIDATOR_ONLY` statistic is refused
before the run; the same panel declared `MANUAL` goes to the queue as it
should. A test asserts the matrix covers `FIG_STATISTIC_TYPES` exactly, so a
fifth statistic cannot be added to the gate without saying whether the runner
can execute it.

## P0-4 (v7.11 review) — three numeric defects in BAR_COLOR

**Log axes were read linearly.** `Axis_Y_Scale=LOG` has validated since v7.1,
and BAR_COLOR was the one reader that did not take the shared
`AxisCalibration` — it re-fitted the ticks with `np.polyfit`. On decade ticks
1/10/100/1000, pixel row 350 read **277.75** instead of **31.62**, with a saved
WPD project recording `scale: LOG` beside it. The default baseline of 0 was
inverted through a second linear fit into a row *inside* the panel, and used
silently to decide which way every bar grew. Every reader now takes the same
calibration object; a baseline of zero on a log axis is refused rather than
invented.

**Slots were rebuilt from the bars that happened to be detected** — global
min/max for the pitch, each series' own leftmost bar for the origin. Two silent
failures, measured on the signed fixture:

| what was missing | before | now |
|---|---|---|
| a series' first bar | every later bar shifted one label left | the hole is where the bar is |
| a whole slot | pitch collapsed 123 px → 108 px, slot 4 emitted as **slot 5** | slot simply absent |
| a middle bar | already correct | unchanged |

Bars are now matched to the pixels in `position_manifest.csv`, nearest anchor
within a tolerance, and a bar near no anchor is **dropped** so the cell stays
missing. Two bars of one series claiming one position are both dropped —
ambiguity, not duplication. `n_slots` is gone: it existed so a reader could
reconstruct its own x spacing, which is inference. Counting off left to right
is still reachable for a direct caller working one figure by hand, and every
such row is stamped `Position_Assignment=SEQUENTIAL`, which the batch layer
refuses and the grid gate flags as `POSITION_INFERRED`.

**Downward bars produced negative dispersion.** The sign was deliberate and
asserted by `test_bar_reader`; `grid_engine` rejects `Dispersion_Value <= 0`.
Two components, each with a passing test, asserting opposite contracts — so a
correctly-read change-from-zero bar failed end to end with
`DISPERSION_NONPOSITIVE`, which reads as a bad extraction. `dispersion` is now
a magnitude, the direction stays in `Bar_Direction`, and the raw difference in
`dispersion_signed`.

15 new scenarios in `test_bar_reader.py`, including a log-axis fixture with
known values. Reverting the shared calibration fails the log case; reverting
the anchor matching fails 5.

## P0-5 (v7.11 review) — mark-level findings reached the value rows

`to_value_records` copied mean, dispersion and bounds and dropped everything
else, so `Errorbar_Stem_Confirmed` — which the readers produce **per mark** —
never became a value. `run_panel` only flagged `NO_VARIANCE` when *all* marks
were unconfirmed, and the gate then consulted a single human-typed field on the
unit manifest. A panel with three confirmed whiskers and one unconfirmed passed
on the strength of the three.

Six fields now travel with every cell: `Errorbar_Stem_Confirmed`,
`Bar_Top_Definition`, `Bar_Direction`, `Position_Assignment`,
`Calibration_Max_Residual`, `Slot_Assignment_Residual_Px`. The gate reads the
cell's own finding (`CELL_ERRORBAR_STEM_UNCONFIRMED`) rather than the unit's
assertion, and names only the cell that failed.

`calib_max_resid` and `slot_residual_px` were computed and returned under names
nothing read. `AxisCalibration` now carries `max_residual` and the runner stamps
it on every value row — on the log axis misread as linear it is 332 axis units,
the loudest single number available, and it was going straight into the bin.

8 scenarios. Reverting the carry raises `KeyError`; reverting the stamp fails 1;
reverting the per-cell gate fails 3.

## P0-3 (v7.11 review) — a person approves the values, or there are none

`run_batch.py` no longer writes `figure_values_accepted.csv`. It stops at
`figure_values_machine_qc.csv`, and the name is the point: the gate found
nothing wrong, which is a different claim from anybody having looked at where
the marks landed. Those two claims used to be the same file.

    AUTO_EXTRACTED      the reader produced marks
    MACHINE_QC_PASSED   the gate found nothing wrong          <- run_batch ends
    HUMAN_APPROVED      a registered person looked and agreed <- value_review.csv
    POOLING_ELIGIBLE    written by finalize_batch.py, nowhere else

**Every passing panel gets a picture.** `review/<Panel_ID>_overlay.png` is the
panel as printed with every mark the reader placed drawn on it, each labelled
with the identity the manifest gave it and the value that identity will carry
into the analysis. A WebPlotDigitizer project is the right artifact for
re-deriving a number and the wrong one for the question a reviewer has 116
times, which is whether `FLUID / POST` is sitting on the bar a human would call
`FLUID / POST`. That question is answered by looking.

**The approval names the extraction, not the panel.** Each review row carries a
`Panel_Fingerprint` over the image hash, the config hash, the reader version,
the pipeline code hash and the cell count. Re-run with different code and the
approval is `APPROVAL_STALE`, not inherited.

    python3 finalize_batch.py RUN_DIR --template   # unfilled decision file
    # fill Decision / Reviewer_ID / Reviewed_At
    python3 finalize_batch.py RUN_DIR

Four refusals, each with a scenario behind it: an unregistered or
`DEMO_IDENTITY` approver; an approval whose fingerprint does not match this run;
a decision for a panel that never passed machine QC; and a DEMO_ONLY run, which
no number of approvals promotes. Absence is refusal — a panel with no decision
row is not approved, and the default output is the empty file.

On the dispersion-resolved ID397 copy: 12 panels awaiting review, 11 approved
and 1 rejected → `FINALIZED | panels approved 11 | values accepted 44`. Bump
`READER_VERSION` and re-run with the same decisions → `APPROVAL_STALE`,
`NOTHING_APPROVED`, no accepted file.

45 scenarios in `test_finalize.py`, on a fixture that does accept values.
Reverting the split fails 3 run scenarios and the reproducibility suite;
narrowing the fingerprint to the panel ID fails 2.

## P0-2 (v7.11 review) — one raster, one hash, checked end to end

The same fact was declared in four places and joined in none: the source
figure's `Source_Image`, the figure manifest's `Source_Image`, the panel's
`Image_Path`, and the hash written beside them. Each file was individually
valid, so a panel could read raster A while its inventory row, its
reconciliation and its provenance all described raster B.

`source_figure_manifest.csv` gains a mandatory `Source_Image_SHA256`, checked
against the bytes on disk (`SOURCE_IMAGE_HASH_MISMATCH`). Every panel's
`Image_Path` is then hashed and compared against the source figure its
`Source_Panel_ID` belongs to (`PANEL_IMAGE_NOT_ITS_SOURCE_FIGURE`). Moving a
raster is fine; moving it without its hash is not.

The first thing the check caught was the regression fixture itself, which put
four panels drawn on four different files under a single `Source_Figure_ID`
whose `Source_Image` was one of them — a physical figure that was four files at
once. That is a fair result for the check.

5 scenarios.

## HIGH (v7.11 review) — figure-grain QC never reached the values

The single worst defect found so far, and it was found by a static read.

`_units_named_by()` resolved a gate problem to a Unit_ID by looking at the
`where` string. It understood `unit:`, `units:` and `values:` — and silently
dropped everything coarser. `IMAGE_HASH_MISMATCH` is charged to `figures:2`.

Reproduced on a dispersion-resolved copy of ID397, where the batch does accept
values. Corrupt every figure hash in the manifest and replay:

    panels 18 | values read 48 | ACCEPTED 48 | qc problems 105
    IMAGE_HASH_MISMATCH        9

Forty-eight poolable rows from an image the batch had been told, nine times,
was not the image the manifest names. The same hole applied to
`PANEL_RECONCILIATION_PENDING`, `SOURCE_FILE_NOT_FOUND`,
`PANEL_STATUS_CONTRADICTS_COUNTS` and `UNLISTED_PANELS_NOT_RECORDED`.

Now:

    panels 18 | values read 48 | ACCEPTED 0 | qc problems 105
    QC_FAILED 12 | NO_READER_AVAILABLE 4 | MANUAL_POINT_READ 2

Two rules, both in `_units_named_by`:

**Inheritance is downward and total.** A `figures:` problem condemns every unit
of that figure; a `grid:`/`grids:` problem condemns every unit declaring that
grid. Not sideways: a unit on another grid was not measured less carefully
because this one is broken.

**An unrecognised scope condemns everything.** A grain the resolver has not
been taught yields `UNATTRIBUTED_QC_SCOPE:<where>` charged to every unit. The
original defect was a string prefix failing to match and nothing noticing; the
next grain the gate grows will fail closed instead.

Both call sites were changed — the run-manifest pass and the pass that writes
`Pooling_Eligible` onto each row. A narrower view in the second would have put
a value in the accepted file that the run manifest already called QC_FAILED.

13 scenarios. Reverting the resolver fails 8.

## HIGH (v7.11 review) — an identifier could write outside the output directory

`Panel_ID` and `Series_ID` are interpolated straight into artifact names —
`{Panel_ID}_marks.json`, `{Panel_ID}.tar`, `{Panel_ID}_{Series_ID}_points.json`
— and nothing checked them. `Panel_ID="../../escaped"` wrote `escaped.tar` and
`escaped_marks.json` two directories above the output root, and the run still
reported `ACCEPTED`. The image resolver had the mirror problem: it tried the
declared string as given *before* joining `file_root`, so an absolute path
anywhere on the machine resolved happily.

`SAFE_ID` (`^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$`) is now checked on every
path-forming column before anything is written, and `resolve()` confines every
image to the realpath of `file_root`. In a workflow where an agent drafts the
manifests, a mistyped ID is enough; it does not take malice.

9 scenarios. Reverting either half fails them.

## HIGH (v7.10 review) — the run mode was the caller's promise, not the manifest's property

`run_batch(..., run_mode="DEMO_ONLY")` is a statement made at one call site.
The manifests it describes are files, and files walk away from call sites:

    python3 pilot_397.py                        -> Run_Mode=DEMO_ONLY
    python3 run_batch.py out_pilot_397/manifests out
                                                -> Status=RAN, Run_Mode=ATTESTED

Same fictional Josiah Carberry, now unqualified. Accepted was 0 only because
ID397's dispersion is unresolved — the same coincidence as the round before,
one layer out.

**The mode is now derived from `reviewer_registry.csv`.** A new mandatory
column, `Reviewer_Record_Type` ∈ `HUMAN | DEMO_IDENTITY`, travels with the
manifests. If any reviewer the source inventory *names* is a DEMO_IDENTITY, the
run is DEMO_ONLY wherever it is launched from. A demo row sitting unreferenced
in a registry demotes nothing.

`Human_Attestation` gains `DEMO_EXAMPLE`, and the two columns must agree:

| record type | attestation | verdict |
|---|---|---|
| HUMAN | HUMAN_CONFIRMED | runs |
| HUMAN | AUTOMATED_AGENT | `REVIEWER_NOT_HUMAN` |
| HUMAN | DEMO_EXAMPLE | `REVIEWER_RECORD_TYPE_MISMATCH` |
| DEMO_IDENTITY | HUMAN_CONFIRMED | `REVIEWER_RECORD_TYPE_MISMATCH` |
| DEMO_IDENTITY | DEMO_EXAMPLE | runs as DEMO_ONLY |

so editing one column alone cannot quietly change what a row means.

**Demotion yes, promotion no.** `run_mode="DEMO_ONLY"` (`--demo-only`) still
demotes a real registry — throwing results away is always allowed. Asserting
`ATTESTED` (`--attested`) over a demo registry is `RUN_MODE_REVIEWER_MISMATCH`
and rejects the batch before a raster is opened, rather than being silently
corrected: the point of saying ATTESTED out loud is that somebody believed it.

On the dispersion-resolved scratch copy, replaying the demo pilot's own
manifests through the plain CLI:

    DEMO_OUTPUT_REFUSED: 48 values passed the gate under a DEMO_ONLY
    reviewer registry ...                                        (exit 4)
    files left in the output directory: ['run_stamp.json']

11 scenarios, on a fixture that *does* accept values. Reverting the derivation
fails 4; reverting the promotion block fails 1.

## HIGH (v7.9.1 review) — the demo identity was only harmless by coincidence

Replacing the personal Gmail with a fictional reviewer and a `Note` reading
`EXAMPLE - replace before treating any output as data` fixed the privacy
problem and left a worse one. A note is a request, not a gate, and three paths
walked straight through it:

| environment | v7.9.1 | v7.10 |
|---|---|---|
| `FDT_REVIEWER_NAME` only | a real name vouching for a fictional ORCID | `BLOCKED`, exit 2 |
| `FDT_REVIEWER_ORCID` only | a fictional name against a real ORCID, `Note` flipped to "opened all five rasters" | `BLOCKED`, exit 2 |
| neither | a fictional person `HUMAN_CONFIRMED`, `Status=RAN` | `DEMO_ONLY`, accepted forced to 0 |

The third was safe only because ID397's dispersion definition happens to be
unresolved, so nothing is accepted. **A safety property that holds by
coincidence is not a property.** Resolving it in a scratch copy — one edit to
`BAR_ERRORBAR_SOURCE`, as if the author had answered the query — makes the same
fictional row sign off 48 poolable values.

Three changes, in the two places that can actually enforce them.

**All four or none.** `FDT_REVIEWER_NAME`, `FDT_REVIEWER_ORCID`,
`FDT_INSPECTION_DATE`, `FDT_REGISTRATION_DATE`. A partial attestation is not an
attestation; the pilot names which are set, which are missing, and exits 2.

**`DEMO_ONLY` is a run mode the runner knows about**, not a comment in a
script. `run_batch(..., run_mode="DEMO_ONLY")` (CLI: `--demo-only`) executes in
full — a demo should show what the pipeline does — but if it reaches the end
holding values the grid gate accepted, it writes none of them and returns
`DEMO_OUTPUT_REFUSED` (exit 4). The refusal drops `raw/` and `projects/` too: a
point cloud is the reading, not a note about it, so a refusal that kept them
would refuse the summary and keep the measurements. Every stamp carries
`Run_Mode` (schema `run-stamp/5`).

On the dispersion-resolved scratch copy:

    DEMO_ONLY  -> DEMO_OUTPUT_REFUSED: 48 values passed the gate under a
                  DEMO_ONLY reviewer registry ... (exit 4)
    ATTESTED   -> panels 18 | cells declared 144 | read 48 | ACCEPTED 48

**The dates are asked for, not assumed.** `Inspection_Date` and
`Registration_Date` were hardcoded `2026-08-07`, which is a false record on
every run after the day it was written — and an inspection date is the one
field whose entire purpose is to be comparable later. `Run_Date` follows the
clock in attested mode and stays fixed in demo mode, so the demonstration stays
reproducible.

Ten scenarios. Reverting the demo gate fails 7; allowing a partial attestation
fails the name-only case; rehardcoding the dates fails the registry check.

## Non-blocking cleanup (v7.9 review)

- **No personal address ships in the package.** `pilot_397.py` registered a
  private Gmail; a worked example that travels with somebody's mailbox
  publishes it to everyone the zip reaches. The example row now uses ORCID's
  own fictional demonstration record (Josiah Carberry, `0000-0002-1825-0097`)
  and labels itself `EXAMPLE identity - replace before treating any output as
  data`. `FDT_REVIEWER_NAME` and `FDT_REVIEWER_ORCID` override it for a real
  run.
- **The runner's usage text lists all eleven mandatory manifests**, plus
  `source_panel_coverage.csv` and `figure_manifest.csv` on the output side. Two
  scenarios now assert the docstring against `MANIFEST_FILES`, because a usage
  list that can drift is a usage list that will — it fell one file behind the
  moment `reviewer_registry.csv` was added.
- **`Human_Attestation` is described as a declared enum, not a signature**, in
  INSTALL.md, SKILL.md and the code. It records that a person typed
  `HUMAN_CONFIRMED` next to a contact; it buys traceability, not proof of
  authorship. A real signature would be a new field.
- **No `__pycache__` in the zip** (the v7.9 archive was already clean; the
  packaging step drops it explicitly).

## MEDIUM (v7.8 review) — three scripts, three different answers to a missing raster

| script | v7.8 | v7.9 |
|---|---|---|
| `forward_test_real_monochrome.py` | `BLOCKED`, exit 2 | unchanged |
| `forward_test_397_mono_bar.py` | `SKIP`, **exit 0** | `BLOCKED`, exit 2 |
| `pilot_397.py` | guard unreachable, **traceback, exit 1** | `BLOCKED`, exit 2 |

Exit 0 on a missing input is the worst available answer: a suite that never
opened a figure reports the same green as one that read every cell correctly.

The pilot's guard was worse than wrong, it was dead. It checked three of the
five rasters and sat at the *bottom* of the file — but the manifests hash their
own rasters as they are assembled, two hundred lines earlier, so a missing
figure raised `FileNotFoundError` out of `sha256_of` long before the guard could
run. A guard that can only execute once its subject has already crashed is
decoration.

It now checks all five ahead of the first open, names the absent files, and
takes an optional raster directory as `argv[2]` so the empty case is testable at
all. `test_reproducibility.py` runs all three scripts against a missing raster
and requires exit 2 *and* the word `BLOCKED` in the output; reverting either
SKIP fails it.

## HIGH (v7.7 review) — the inventory attestation accepted non-answers

The source-inventory layer is right, and it rests on one thing software cannot
do: a person opened the figure and counted the panels. Every guarantee above it
— coverage, routing, the queue — is only as good as that attestation, which
makes the reviewer field and `Inspection_Date` the two most load-bearing fields
in the package.

They were checked for blankness and nothing else. All of these ran:

    Inspector = TBD          Inspection_Date = soon
    Inspector = TODO         Inspection_Date = later
    Inspector = ?            Inspection_Date = 2026-13-45
    Inspector = x            Inspection_Date = 2099-01-01

That is the hedged-`Errorbar_Definition_Source` defect again, in the field that
can least afford it — a non-answer occupying the slot that is supposed to hold
the answer, with no second source to fall back on.

`check_attestation()` now runs both fields through the unresolved-marker
vocabulary (`UNRESOLVED_INVENTORY_ATTESTATION`), requires a real name — the
point of the field is that somebody can be *asked* about the count — and parses `Inspection_Date` as an ISO date that is not in the
future (`BAD_INSPECTION_DATE`). A free-text date cannot be compared with
anything, which is the only reason to record one. 20 scenarios; reverting the
two call sites fails all 20.

## MEDIUM (v7.7 review) — `build_397.py` no longer ran, and could not

Exit 1, `ManifestLoadError`: the three source manifests are mandatory and it
wrote none. Making them optional would reopen the bypass they exist to close,
so that was never the fix.

The deeper point is that **the inventory makes a partial worked example
impossible on purpose**. Declare a document and every one of its figures must be
inventoried; declare a figure and every one of its panels must be. `build_397.py`
covered Figure 3 of a five-figure publication, so it either grew into a second
copy of `pilot_397.py` or it went. It is removed; `pilot_397.py` does everything
it did, on all five figures.

## MEDIUM (v7.7 review) — 16 extractable cells were still routed to manual

The inventory recorded Figure 3's TPR and finger-pulse-volume panels, which is
the improvement — they were invisible before. But it marked all four
`MANUAL_DIGITIZE` when the released BAR_MONO reader reads them without changes.
Recording a panel as manual when a reader can do it is a quieter loss than
omitting it, and a real one: four boxes and four calibrations were the whole
cost.

They are configured. **The pilot reads 48 cells, not 32** — TPR men 52.71 /
67.71 / 47.60 / 60.10, finger pulse volume women 1233 / 660 / 988 / 830, all
within a unit of the printed figure by eye.

## What the review confirmed about the inventory layer

Adversarial probes against the completeness claim, all **blocked**: dropping a
panel from the inventory, dropping a whole figure from the figure manifest,
dropping a run panel while leaving it inventoried, blanking a `Source_Panel_ID`,
pointing a run panel at a source panel nobody declared, an inventory marked
`PENDING`, a `Panel_Count_Method` of `ASSUMED`/`GUESSED`/`not checked`. Fourteen
virtual figures cannot satisfy a 36-panel physical figure — the architecture
does what it claims.

The one probe that ran is the acknowledged limit: lowering `Observed_Panel_Count`
to match a short inventory. No software can count the panels in an arbitrary
figure, which is exactly why the attestation had to be tightened.

## What the pilot did

    python3 pilot_397.py

14 panels, 128 declared cells, one run.

| | panels | cells |
|---|---|---|
| read, all 4 of 4 cells each (BAR_MONO) | 8 | 32 |
| `NO_READER_AVAILABLE` — solid/dashed lines | 4 | 96 declared, 0 read |
| `MANUAL_POINT_READ` — single-subject traces | 2 | n/a |
| **`ACCEPTED`** | | **0** |

Zero accepted, and that is the correct answer. Every one of the 32 readings is
right — spot-checked against the printed figures, worst disagreement under
1 unit on every axis — and every one is blocked by a single unresolved fact:
Figures 3 and 4 never say whether their whiskers are SD or SEM.

That is not a guess by the system. The paper's running text defines the bars for
the *line* figures — "physiological responses (30-min means and SEMs)" — and the
captions for the *bar* figures give only the averaging window: "Cardiovascular
responses to pre-HDT stand tests and post-HDT stand tests (3-min means)". Two
different figures, one definition, and the definition does not reach the other.
One sentence from a human unblocks all 32 cells.

### Defect 1 the pilot found: one unreadable panel stopped every readable one

`MARK_TYPE_NOT_RELEASED` was a manifest *error*, so declaring the two
solid/dashed line figures honestly rejected the whole batch — including the 32
bar cells that read perfectly. That is backwards. The manifest is correct; the
software is behind it. An unreleased mark type now validates and the RUN gives
it `NO_READER_AVAILABLE`, a new run state, with its declared cells named in the
manual queue and a pointer to where the work stands.

The distinction it preserves is worth having: Figures 1–2 are
`NO_READER_AVAILABLE` (a software gap this project will close), Figure 5 is
`MANUAL_POINT_READ` (two named individuals plotted beat by beat — not a summary
statistic, and no reader will ever change that). Counting them separately is how
you decide what to build next.

Its series are still validated on the rules that reader *will* use — line style
declared, and two series not sharing one — so the manifest is right the day the
reader ships rather than wrong and unnoticed.

### Defect 2 the pilot found: a hedge passed where a placeholder was blocked

`UNRESOLVED_ERRORBAR_DEFINITION` blocked "TBD", "assumed SE" and "not stated".
It did **not** block `"probably SEM"`, `"LIKELY SEM"`, `"inferred from the
Figure 1 caption"`, `"by analogy with Figure 1"` or `"taken to be SEM"` — which
are exactly what a careful extractor writes when a paper is silent, because
leaving the cell blank feels like losing information.

A hedge is a non-answer in a politer register, and on this field it decides the
pooled weight by sqrt(n). Twelve hedging forms are now blocked. `"ESTIMATED"` is
deliberately **not** among them: "estimated marginal means ± SE" is a real
caption, and a check that rejects it has stopped being a check and become a word
filter. Eight scenarios; reverting the vocabulary fails all eight.

### Also exercised

`forward_test_real_monochrome.py` (publication 386, four black series told apart
by marker shape and fill) defaulted to a path in one person's Downloads folder
and had been silently SKIPping. The raster ships with the package; it now looks
beside itself first and runs: 13 of 32 cells auto-emitted, 19 left missing where
marks overlap, 13/13 correct series identity, worst 0.87 bpm against an
independent reading. Failing closed on overlap is the property under test.

## HIGH (v7.4) — an input that could not be loaded left the previous result

Reproduced: clean run, then a run pointed at a manifest directory that does not
exist, and `figure_values_accepted.csv` still held eight rows under a
`Status=RAN` stamp. `load_manifests` was called before `clear_outputs`, so a
missing directory, a malformed CSV or a permissions error raised before the
clearing ever happened — and "nothing outlives the run that replaces it" only
holds if the clearing is the first thing the run does. It now is.

Two details that the obvious fix would have got wrong:

- **the loader raises a plain `ManifestLoadError`, not `SystemExit`.** It used
  to raise `SystemExit`, which derives from `BaseException`, so an
  `except Exception` around the load sails straight past it and the stamp never
  gets written. The scenarios catch `BaseException` and assert the type, so a
  regression fails a check instead of taking the suite down with it.
- **`Status=INPUT_LOAD_FAILED` carries a `Detail`.** An empty directory with a
  stamp that says only "failed" tells a returning user nothing about whether to
  re-run or go looking for a file.

`RUN_STATUSES` is now declared: `RAN` / `MANIFEST_REJECTED` /
`INPUT_LOAD_FAILED` / `PROMOTE_FAILED`. Only `RAN` may have an accepted file
beside it. `main()` exits 3 on a load failure with a message pointing at the
stamp.

Nine scenarios per failure mode, over all three the review named: a missing
directory, a deleted manifest file, and a malformed CSV.

## MEDIUM (v7.4) — promotion moved files one at a time

`promote()` walked `os.listdir()` and moved each file, so a process killed
partway could leave the accepted file complete beside a missing run manifest.

A directory rename would be genuinely atomic and is not available here: value
rows NAME their point files and WPD projects, so those have to be written at
their final paths, and a rename would only cover the summary CSVs. What is
available is an order:

- **`figure_values_accepted.csv` moves last, as a commit marker.** Nothing
  depends on it, so dying partway means the pooling file is the one thing that
  is not there. The failure mode is "no result", not "a result missing its
  audit trail".
- **everything that explains a result is promoted before it** — the stamp, the
  run manifest, the QC problems, the queue, the raw values. If the marker lands,
  the files that justify it already have.
- **every file's arrival is verified after the moves.** A marker whose evidence
  is incomplete is worse than no marker, so a missing file raises.
- **a failure withdraws the commit**: the accepted file is removed whether or
  not it arrived, the staging directory is dropped, and the stamp is rewritten
  to `PROMOTE_FAILED` with zero accepted.

`run_batch(fault_after=N)` is a test hook that aborts promotion partway. The
suite kills it at three points and asserts the directory is not poolable after
any of them, then kills `promote()` directly with a stub set whose alphabetical
order puts the marker second — so the ordering is proven independently of the
withdrawal, and vice versa. A monkey-patched `shutil.move` that silently loses
a file proves the verify pass.

## HIGH (v7.3) — a failed re-run left the previous run's accepted file in place

Reproduced exactly as described: a clean run into a directory, then a rejected
run into the same directory, and `figure_values_accepted.csv` still held eight
rows with a `run_stamp.json` claiming `Values_Accepted=8`. Nothing inside either
file said it belonged to a run that had since been superseded by a failure.

The ordering was the whole defect. A run that tidies up after itself only tidies
when it gets that far, and a rejected run returns before it gets anywhere.

Three changes, all of them required:

- **`clear_outputs()` runs before validation**, not after the work. Every
  canonical output — the two values files, the run manifest, the queue, the QC
  problems, the stamp, the completed figure manifest, and the `raw/` and
  `projects/` directories — is removed the moment the run starts. Nothing a
  previous run produced can outlive the run that replaces it, whatever happens
  next, including a crash.
- **the summary CSVs are staged and promoted in one move.** They are built under
  `.staging` and moved into place only once the run has finished, so an
  interruption leaves the directory empty rather than half-populated with files
  that look like a result. The point clouds and WPD projects are written at
  their final paths deliberately: value rows *name* those files, and staging a
  file whose path is recorded inside another file means rewriting paths, which
  is exactly where a stale reference survives.
- **a rejected run still writes `run_stamp.json`**, with
  `Status=MANIFEST_REJECTED`, `Values_Read=0`, `Values_Accepted=0` and the
  manifest problem count. A stamp that is absent when things go wrong is worse
  than no stamp — it is only ever there to reassure. `Status` is new, so a
  reader can tell a rejection from a run that legitimately accepted nothing.

The `run_batch()` return value now carries `values` and `accepted` on the
rejection path too, so a caller cannot hit a missing key and fall back to a
stale number.

Nine scenarios fix the sequence: clean run → rejected run → nothing stale, and
then rejected run → clean run → the rejection's own outputs gone.

## MEDIUM (v7.3) — a unit's state was whichever panel came last

`{r["Unit_ID"]: r["Run_State"] for r in run_rows}` keeps the last panel's state.
Two panels feeding one unit, first one failing, second passing, and the unit
read as `AUTO_PASS`.

Fixed the robust way rather than by forbidding the structure — a unit whose
cells genuinely come from two panels is legal in this schema, and blocking it
would be a schema change to paper over a bookkeeping bug:

- **every value row carries `Source_Panel_ID`**, stamped where the panel is
  known, and is judged by that panel's state
- **and by the worst state among all panels building its unit.** This is the
  half that is easy to miss: when the readable panel fills the entire grid the
  gate has nothing to complain about, but nobody knows whether the panel that
  could not be read would have agreed with the one that could. "The readable
  half says so" is not a reading of the figure.

## LOW (v7.3) — MIGRATION.md still described `figure_values.csv`

Rewritten. It described three grains where there are now four, and named the
values file by a name the batch layer deliberately no longer writes. It now
distinguishes the values *grain* (which a hand-curated set may name what it
likes, as `build_id323.py` does) from the batch *outputs*, which are always the
accepted/raw pair.

## HIGH (v7.2) — a QC-failed value could reach master by reading one file

`figure_values.csv` held every value the readers produced, whatever the gate
said about them. On publication 397 that file carried eight means whose
SD-versus-SEM was unresolved, while both panels sat at `QC_FAILED` in a
different file. Reading "the values file" — the obvious thing for a downstream
script to do — would have pooled them, and SD/SEM confusion scales the
meta-analytic weight by sqrt(n).

**There is no file called `figure_values.csv` any more.** The run writes two,
and if a stale one is present in the output directory it is deleted:

- **`figure_values_accepted.csv`** — the only file to pool from. A row is here
  only if its panel reached `AUTO_PASS` **and** its unit drew no gate problem.
- **`figure_values_raw.csv`** — everything read, for the audit trail, with
  `Value_Status` (`ACCEPTED` / `QC_FAILED` / `PANEL_NOT_PASSED`), `QC_Codes`
  (the gate codes charged to that unit) and `Pooling_Eligible` on **every row**.

Both were done rather than either: the safe file has the plainest name, and the
unsafe one carries its own verdict in every row so nobody needs to know to join
against `run_manifest.csv`. `run_stamp.json` reports `Values_Read` and
`Values_Accepted` separately, and the `run_batch()` return value carries both,
so a caller cannot read one count and assume the other.

The blame rule is deliberately conservative: **any** gate problem charged to a
unit disqualifies **all** of that unit's cells. The individual readings may be
perfectly good, but a unit with a hole in its grid is not poolable, and the raw
file keeps every number for whoever resolves it.

On publication 397 `figure_values_accepted.csv` is **0 rows**, and
`pilot_397.py` exits non-zero unless that is true.

## Install

    SKILL=~/.claude-science/orgs/dd143201-4dc0-4233-9a3f-240a058d710f/skills/figure-digitization-triage
    python3 -m pip install -r requirements.txt
    cp *.py *.md *.csv *.png *.jpeg *.json *.tar "$SKILL"/
    mkdir -p "$SKILL"/fixtures && cp fixtures/* "$SKILL"/fixtures/
    mkdir -p "$SKILL"/wip && cp wip/* "$SKILL"/wip/
    cd "$SKILL" && for t in test_reproducibility test_kernel test_grid_engine \
        test_bar_reader test_mark_readers test_mono_bar test_integration \
        test_run_batch crosscheck_id323 forward_test_397_mono_bar; \
        do python3 $t.py || break; done

`SKILL.md` is complete and standalone - copy it as it is. `MIGRATION.md` covers the schema changes if you are upgrading an existing skill folder.

I cannot write into the skill folder from this session — skill files here are a
read-only cache. Until you run the copy the active skill is unchanged.

## The declarative execution layer

Three manifests prove SOURCE COMPLETENESS and four describe the RUN, kept separate from the four grains that
describe the DATA. A values file has to be reviewable by someone who never
touches a raster; a run has to be re-executable by someone who never reads the
paper.

| file | one row per | carries |
|---|---|---|
| `source_document_manifest.csv` | main article/supplement/chapter | complete page range, verified figure count, source role |
| `source_figure_manifest.csv` | physical publisher figure | immutable ID, full-raster panel count, visual verification method and verifier |
| `source_panel_inventory.csv` | visually distinct source subpanel | outcome, target status, and a mandatory disposition even when no reader exists |
| `panel_manifest.csv` | readable/configured panel | physical `Source_Panel_ID`, box, `Mark_Type`, axis ticks and scale, baseline, `Unit_ID`, `Panel_Mode` |
| `series_manifest.csv` | series in a panel | colour / mask key / marker shape / marker fill / line style / bar fill pattern, and the `Factor_Name`+`Factor_Level` it IS |
| `position_manifest.csv` | x position in a panel | pixel or slot, display order, and the `Factor_Name`+`Factor_Level` it IS |
| `reader_config.csv` | option | long form, so a reader's options are extensible without a schema change |

`run_batch.py` loads all ten manifests, validates document→figure→panel completeness,
dispatches configured panels by `Mark_Type`,
saves the raw marks, converts to the standard value grain, runs the grid gate,
and writes `figure_values_accepted.csv`, `figure_values_raw.csv`,
`run_manifest.csv`, `manual_queue.csv`, `source_panel_coverage.csv`,
`qc_problems.csv`, `run_stamp.json`,
`raw/` and `projects/`.

Four design commitments, each of which is a scenario in `test_run_batch.py`:

**The complete source range is inventoried before virtual splitting.** Every
main article/supplement/chapter declares its total physical figure count; every visible
plot region is a `Source_Panel_ID`; the count must equal the verified count on
its `Source_Figure_ID`. Outcome-specific `Figure_ID` rows cannot satisfy this
gate. A 36-panel source represented by only 14 virtual declarations is rejected
before any reader runs. Non-target, not-data, manual and no-reader panels stay in
the coverage ledger instead of disappearing.

**Manifests are validated before a raster is opened.** 34 rejection scenarios: a
box that does not fit its image, ticks outside the panel they calibrate, a
misspelled option, an option that is real but meaningless for this reader, two
series told apart by nothing, a factor on both the series and the position axis,
a scatter with declared x positions. Discovering on figure 140 that a Config_ID
was mistyped is an expensive way to learn it.

**Identity is declared, never inferred.** The reader is never told what a series
means; the manifest maps `Series_ID` and `Position_ID` onto factor levels after
the fact. A test asserts the Cell_Keys come from the manifest and not from the
reader's own labels.

**Every panel lands on exactly one state**, and everything short of `AUTO_PASS`
goes to the manual queue with its reason and coordinates:

    AUTO_PASS  MANUAL_POINT_READ  SERIES_IDENTITY_UNRESOLVED
    PANEL_GEOMETRY_UNRESOLVED  NO_VARIANCE  NOT_CONVERTIBLE  QC_FAILED

Each is reachable and each has a scenario. `SERIES_IDENTITY_UNRESOLVED` is the
one worth knowing: if one declared series produces marks and another produces
none, the panel contributes **no** cells, not half of them. A reader that finds
one of two curves cannot be trusted about which one it found.

`QC_FAILED` exists so `run_manifest.csv` and `qc_problems.csv` cannot tell a
reviewer two different stories — a panel whose values the gate rejected is
re-stated as failed, whatever the reader thought of them.

### Reproducibility is recorded, and checked

`run_manifest.csv` carries per panel: image SHA-256, config SHA-256, reader
version, raw data file, WPD project, run date. `run_stamp.json` adds a hash of
every input manifest. A second run over the same inputs is asserted identical.

**The run saves its own WebPlotDigitizer project.** The gate requires a
re-openable project on every digitized row, and it is right to: "the reader said
so" is not something a second person can check. An automated run has no
human-saved one, so it writes the raster, the calibration it used and every mark
it placed into a real `.tar` that opens in WPD. That is the only cheap way to
catch a systematically misplaced series — a reviewer looks at where the reader
thought the marks were.

## MEDIUM 1 (v7.2) — `n_slots` was offered to a reader that has no such parameter

`read_monochrome_bar_panel` derives its slot count from the number of declared
series and takes no `n_slots`. The option table said otherwise, so the manifest
validated and the run then raised `TypeError`, which the runner reported as
`PANEL_GEOMETRY_UNRESOLVED` — a message about the figure for a defect in a table.

`n_slots` is now BAR_COLOR only. More usefully, the class is closed: declaring
that an option "applies to" a mark type is a promise about a function signature,
so `reader_functions()` maps every mark type to the callable that actually
receives the keywords, and a scenario asserts by `inspect.signature` that every
option names a parameter its reader accepts. A future table edit that repeats
this fails the suite instead of the batch.

## MEDIUM 2 (v7.2) — the manifest allowed a figure the shipped reader cannot read

`Mark_Type=LINE_MONO` with `Marker_Shape=NONE` and series told apart by
`SOLID`/`DASHED` validated cleanly. The released LINE_MONO reader matches by
marker geometry and never looks at `Line_Style`, so the run would have matched
those marks by shape alone. The documentation said the solid/dashed reader was
not shipped; the manifest contract said the opposite.

Both halves fixed:

- LINE_MONO now **requires** `Marker_Shape` (`MISSING_SERIES_DISCRIMINANT`), and
  the message names what such a figure would need instead
- a LINE_MONO series that also sets `Line_Style` gets `LINE_STYLE_NOT_READ` —
  recording a discriminant the run will not apply is a promise the file cannot
  keep
- `LINE_MONO_STYLE` is a named `UNRELEASED_MARK_TYPE`. Declaring it yields
  `MARK_TYPE_NOT_RELEASED` with what it is, why it is held back, and where the
  work sits. Naming it beats silence: the alternative is `BAD_MARK_TYPE`, which
  reads as "you made that up".

## MEDIUM 3 (v7.2) — options were type-checked but never range-checked

`threshold=-1`, `threshold=300`, `x_window=0`, `colour_tolerance=-5` and
`min_marker_area=500` beside `max_marker_area=10` all parsed cleanly. Each then
selects nothing at all, and an empty panel is indistinguishable downstream from
an unreadable figure.

Every entry in `READER_OPTIONS` now carries a range check as well as a parser —
greys 0–255, windows and areas and bar widths positive, tolerances non-negative,
`n_slots` at least 1 — and `PAIRED_OPTION_RULES` catches
`min_marker_area >= max_marker_area`, which no single-value check can see.

## `write_point_data` — the minor item, taken further than asked

The review asked for pixel coordinates, series, `Unit_ID`, `Cell_Key`, image hash
and calibration. All are stored, and all are **required** rather than optional,
because the reason is stronger than convenience:

Calibrated x/y alone are already the reader's answer. If the calibration was
wrong, the saved values are wrong in exactly the same way and nothing in the file
disagrees with anything else — the file is self-consistent and useless. Storing
the raw pixel next to the calibration is what makes the value *checkable*, so
the function refuses to write a point that has no pixel.

Two further checks fall straight out of that:

- **at write time**, every value is re-derived from its own pixel under the given
  calibration; a mismatch raises. A file whose numbers do not follow from its own
  pixels is internally inconsistent, and the moment to find out is before it is
  written.
- **at read time**, `read_point_data` re-checks the same thing, so a file edited
  after the fact does not load silently. The old values-only schema is refused
  outright rather than half-understood.

`sha256_of()` is exported for the image identity. 15 scenarios cover it,
including "the association recomputes from the file alone".

## BAR_MONO — monochrome grouped bars, with a real forward test

Held back from the last release for having no fixture. It has two now, plus a
publisher raster.

A black-and-white bar chart names its series by FILL PATTERN — solid, hatched,
open — and no colour mask sees the difference. `SeriesSpec.bar_fill` is separate
from `SeriesSpec.fill`: overloading one field meant an open circle and an
unfilled bar were the same declaration, and a panel carrying both could not be
described at all.

Three things it gets right that are easy to get wrong:

**The cap is not the bar.** Finding the bar's end by "the first row spanning half
the slot" clears an error-bar cap, which is drawn about 70% of the bar's width —
so the whisker tip becomes the value and every mean reads high by a whole SD, in
one direction, silently. The reader walks UP FROM THE BASELINE instead: a bar has
two side strokes continuous from the baseline to its end and a floating cap has
none, so the walk stops before it ever reaches one. `edge_rule="FIRST_WIDE_ROW"`
reproduces the defect on demand, and the suite measures its cost rather than
asserting the fix — on a plain bar it lands on the cap one SD high, and on a bar
carrying a significance glyph it goes higher still.

**The interior is sampled inside the outline.** Including the two side strokes
lifted an open bar's density from 0.02 to 0.16, into the hatched band, and the
reader then named the wrong series with complete confidence.

**The stem gets its own threshold.** Grey level is ink coverage: a filled bar
reads near 0, a one-pixel hairline stem at 60% coverage reads about 140 on the
same figure. Thresholding both at 128 found every cap and no stem, so on
publication 397 the reader confirmed nothing and returned no dispersion at all —
a fail-closed answer produced by a measurement error rather than by the figure.

`forward_test_397_mono_bar.py` reads all 8 cells of publication 397 Figure 3,
worst mean **0.75 mmHg** from an independent eye reading on a 100 mmHg axis, all
8 error bars stem-confirmed. The two panels' axes are four pixels apart; sharing
one calibration between them put the second panel's baseline below its own bars
and returned nothing for all four of its cells. Panel geometry is per panel, and
the forward test says so.

## A defect the batch layer found on its way through

`read_line_marker_panel` returned `errorbar_lower`/`errorbar_upper` in
patch-relative rows while returning the centre in image rows. On a panel starting
at row 40 both bounds sat 11 units high — and their **difference**, the
dispersion, was exactly right. Every mean-and-dispersion check passed. The first
thing to notice was the grid gate saying a mean sat outside its own error bar,
which only happened once whole panels started flowing through it.

Two scenarios now guard the bounds themselves, not just their spread.

## Suites

All run with scipy hard-blocked by a `sys.meta_path` finder.

| suite | scenarios |
|---|---|
| `test_run_batch.py` | 451 |
| `test_kernel.py` | 232 |
| `test_grid_engine.py` | 171 |
| `test_finalize.py` | 129 |
| `test_compile_plan.py` | 123 |
| `test_mark_readers.py` | 92 |
| `test_bar_reader.py` | 73 |
| `test_mono_bar.py` | 26 |
| `test_integration.py` | 19 |
| `test_reproducibility.py` | 18 |
| **total** | **1334** |

Plus `crosscheck_id323.py` (0.50 px / 2.50 px over 72 bars, two independent
primitives), `forward_test_397_mono_bar.py`, and two worked examples:

- `build_id323.py` — 2 figures, 12 units, 107 values, 2 problems, both the known
  `TIMEPOINT=DI19` hole where two bars overlap past separating
- `build_397.py` is **removed**. It was a single-figure worked example, and the
  source inventory makes a partial example impossible on purpose: declare a
  document and every one of its figures must be inventoried, declare a figure
  and every one of its panels must be. Either it grew into a second copy of
  `pilot_397.py` or it had to go. `pilot_397.py` does everything it did.


## Not shipped: solid/dashed LINE_MONO

It is built, it is measured, and it is in `wip/` rather than in the reader set.

On a synthetic fixture it reads 16 of 18 separable cells, assigns both styles
correctly and recovers means within 1.5 units on a 50-unit axis. That is close
to working and not the same as working:

- at a deliberate **crossing**, where the two curves land on the same value, it
  emits both cells instead of dropping them. The whole design of this system is
  that an unresolvable mark produces no row; this one produces two
- 2 of 18 separable cells go missing and the reason is not characterised
- it has not been run against publication 397 at all

Shipping it would put numbers in a values file nobody can defend — the same
reason BAR_MONO was held back last time, and the standard BAR_MONO has now met.
`wip/line_style_mono.py` records what was learned so the next attempt does not
restart: a whole-panel sequential tracer does not work (a dash *tip* biases the
run centre enough to lose a steep curve, and one miss fragments the series); a
short windowed fit does, provided it is quadratic, counts only the span the ink
covers, and lets the collection band follow the first fit.

`wip/test_line_style_mono.py` runs and reports 6 failures. It is deliberately
not in the release gate.

## Still open

- 397 Figures 1, 2, 5 — solid/dashed, blocked on the above
- 397 Figure 4, 386 Figures 3–4
- ID 323 FIG2 DAP DI19 (1 cell) and 4 unpaired cells need a human reading
- ID 323 and 397 both need their SD/SEM wording resolved from the methods text
