# figure-digitization-triage — v7.28 (full package)

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

## v7.23 review — a guard on the outside is not a guard on the inside

`run_stamp.json` is checked at the top level: it must exist, decode as UTF-8,
parse as JSON, and hold an object. Each of these passes all four:

```json
{"Status": "RAN", "Run_Mode": "ATTESTED", "Output_SHA256": ["not", "a", "map"]}
```

`verify_run_outputs` then does `recorded.get(name)` on a list, which raises
`AttributeError` — after the accepted file and the previous stamp have been
deleted. The exact failure the top-level guard exists to prevent, one level
down. Reproduced for a list, a string, a boolean and a number; all four raised
with no stamp left behind.

`Output_SHA256` must be an object, and every value in it must be a string:
either way `RUN_STAMP_SCHEMA_INVALID`, refused with a stamp. The scenarios
assert the fixture is still valid JSON with an object at the root, so they
cannot pass by accident on the outer guard. Reverting the type check fails 1 and
crashes the suite; reverting the value check fails 1.

## v7.22 review — failure durability

No accepted-value defect this round. Four things that make a run harder to
audit or harder to hand over.

### 1. A run with nothing automatic in it wrote no figure manifest

The figure manifest's **write** sat inside `if projects_by_panel and
"WPD_Project_File" in figures.columns` — the condition that decides whether the
project column needs filling in. So a batch where every panel was manual,
unreadable or unsupported produced no `figure_manifest.csv` at all, while
`CANONICAL_OUTPUTS` and the documentation both call it a run output. The runs
with nothing automatic in them are exactly the ones somebody audits by hand.

Only the column is conditional now; the write is not. Revert: 1.

### 2. A moved run could not find its own manifests

Outputs became portable at 7.21, but `run_stamp.json` records `Manifest_Dir` as
the absolute path the run used — a directory on the machine the run happened
on. The 7.21 move test passed `--manifests` explicitly, so it never exercised
the default. A `manifests/` directory sitting inside the run travels with it and
is now looked for first: explicit `--manifests`, then `RUN_DIR/manifests` if it
exists, then the stamp's record. The move test no longer passes `--manifests`.
Revert: 1.

### 3. `run_stamp.json` was the one file read without a guard

Every other file this module reads is guarded — and the accepted file and the
previous stamp are deleted *before* the stamp is opened. So a truncated stamp,
a stamp holding a list, or one with bytes that are not UTF-8 raised out of the
finalizer and left the run with no result **and** no stamp explaining the
absence, which is the single outcome this module exists to make impossible.
Five malformed shapes, each a scenario. Revert: 10.

Output hashing moved from decoded text to bytes at the same time, on both
sides. That is not cosmetic: `sha256_of_text(open(path, encoding="utf-8")
.read())` *raises* on a file that is not valid UTF-8, so an output corrupted
with stray bytes came out of the verifier as a traceback rather than as
`RUN_ARTIFACT_MODIFIED`. Revert: 2.

### 4. One sentence in `SKILL.md` still promised an overlay

The run steps branch on `Review_Mode` correctly; the protocol body further down
still said "each passing panel also gets `review/<Panel_ID>_overlay.png`",
which is the contract the code stopped holding when `WPD_ONLY` appeared. The
suite now refuses both that sentence and the old unconditional instruction by
exact string, so the two halves of the document cannot drift apart again.

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
    # and, only if you will run the corpus walk over PDFs:
    #   python3 -m pip install -r requirements-intake.txt
    #   apt-get install poppler-utils   /   brew install poppler
    cp *.py *.md *.csv *.png *.jpeg *.json *.tar "$SKILL"/
    mkdir -p "$SKILL"/fixtures && cp fixtures/* "$SKILL"/fixtures/
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
- `LINE_MONO_STYLE` was a named `UNRELEASED_MARK_TYPE` here and has since
  shipped; the mechanism stays, and `UNRELEASED_MARK_TYPES` is empty. Naming an
  unbuilt reader beats silence: the alternative is `BAD_MARK_TYPE`, which reads
  as "you made that up".

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

## The monochrome geometry prototype, and what the second figure said

`measure_mono_bars.py` measures monochrome bar panels and decides nothing;
nothing in the package imports it. It exists because `_FILL_BANDS` and
`_INSIDE_MIN_DENSITY` in `mark_readers.py` were measured on ONE figure, and
publication 127 is the second. `test_measure_mono_bars.py` draws each trap on
purpose; every scenario in it was written by reverting the fix it guards and
confirming it fails, and the revert is named in a comment above it.

Six defects found by pointing it at a second figure, all of which would have
shipped a number rather than a refusal:

**`texture()` mixed box-relative rows with absolute columns.** Publication 127's
panels start at page rows 620, 1580 and 2510, so every fill number came from a
band up to 1159 px above the panel. It read white paper and reported
`ink_mass 0.000` for a solid black bar. This is the number the fill vocabulary
was about to be built on. Corrected, the four printed fills separate with no
overlap at all — OPEN 0.000, STIPPLED 0.144-0.157, HATCHED 0.262-0.318, SOLID
0.734-1.000 across 32 bars of three figures — and none of the bands
`mark_readers.py` currently ships is right.

**A stroke is the thickness of a CONTIGUOUS rule.** Measuring it as the thickest
band of rows whose dark pixel COUNT clears half the panel width makes a row that
crosses several bars a rule: three 100 px bars in a 400 px panel measured the
stroke at 124 px, and since every threshold in the file is a multiple of the
stroke, that panel then read one bar out of three. Half the panel width was also
a number the script had no business choosing — 397's panel box holds no rule
longer than a third of its width. The panel's own longest run is the reference
instead, and the band is the rows contiguous with it. Measured this way — off
the panel's longest line — 397 reads 2 px and the synthetic fixture 2 px.

That measurement was superseded in the same round by the baseline-bound one
below, which asks a different question and gets different answers: 397's MEN
panel reads 1 px and its WOMEN panel 2 px, and publication 127's three
sub-panels read 3, 3 and 4. Neither pair is a contradiction. The printed axis
lands on the pixel grid differently in every panel, so the stroke is a property
of the panel as rendered, and "all panels of a figure share a stroke" is false.
It is pinned per panel instead, in the geometry and in the forward tests.

**The seed band clears the rule's fade, not its core.** The stroke is the rule's
solid core; its inked extent at threshold 128 is wider. Standing one core-stroke
clear left the band on the fade, every column in the window read as seeded
including the paper at its edges, and the clipping guard fired on every group in
the figure. `rule_edge()` measures the clearance: a rule row is unbroken across
the window, or it is still inked and LESS inked than the row before it. A bar row
is as inked as the bar row before it, so the fade terminates on the first row
that stops fading.

**A truncated seed band is a different measurement, not a weak one.**
`SEED_SUPPORT` is a fraction of a band of depth `3 * stroke`, and a quarter of
two rows is one row. Publication 127's panel box ends three rows below its
baseline, and the rule's own fade in those rows outvoted 246 px of real upward
bar, so the direction test called the group ambiguous and refused a figure it
could read.

**`GROUP_WINDOW_CLIPPED`.** `footprints_from_seed` divides the span it can see by
the declared bar count. A window 22 px short on publication 127's middle panel
moved every boundary and put the stippled bar's right stroke inside the solid
bar's footprint; the solid bar then traced its neighbour's outline and read 3.37
where the bar is 2.47. The three sub-panels do not share an x-origin, which one
shared pair of anchors had assumed. Recentring the anchors is a fix to the
geometry spec; the guard is what makes the next one visible instead of plausible.

**A bar too short to have an interior gets no fill.** The bar's top rule and the
baseline rule are each a stroke thick, so on 15 px bars at a stroke of 5 the two
rules ARE the bar. An inset that collapsed back to the full bar when it left
nothing reported an OPEN bar at `ink_mass 0.517`.

And the fail-closed contract the classification always implied but did not
enforce: `BODY_CONTINUATION` means the bar top is known to be wrong,
`UNRESOLVED_REMOTE_SUPPORT` means it is not known to be right, and both now
suppress `value` and the whole texture block, leaving `provisional_value` for
audit. A body-shaped component separated from the bar by a gap small enough to
be a printing artefact is `UNRESOLVED_REMOTE_SUPPORT`; only distance
distinguishes it from the rule at the top of 397's panel, which is also wide,
spanning and thick.

Two more, found by review of the above:

**The stroke is the thickness of the BASELINE rule, not of the longest rule.** A
panel frame, a gridline and a box border are all as long as the axis and can be
drawn heavier, and `argmax` returns the first of the tied maxima - the one
nearest the top of the panel. The scenario in this package that draws an 8 px
frame above a 4 px baseline measured the stroke at 8, and seed depth, direction
margin, remote reach, minimum interior height, component thickness and gap
tolerance all doubled with it. It passed anyway, which is the point: a stroke
wrong by a factor of two does not fail, it drifts. `measure_panel` now computes
the axis calibration BEFORE the stroke and hands the calibrated zero to
`stroke_scale`, which searches 2% of the panel height around it and refuses if
nothing rule-shaped is there. On the five panels measured here the rule sits
within one pixel of the calibrated zero. 397's own baseline turns out to be 1 px in
the MEN panel and 2 px in the WOMEN panel - the 2 px it had been using globally
was measured off a gridline 165 rows away - and every value it reads is
unchanged. The two panels differ because the printed axis lands on the pixel
grid differently in each, so "all panels of a figure share a stroke" is FALSE
and is not asserted anywhere; publication 127 reads 3, 3 and 4 for the same
reason, pinned per panel in its geometry.

**Row coordinates now name their frame.** `remote_support` works inside the
panel crop, so its rows are panel-relative, and `cap_px` handed one to a caller
under the name the production reader uses for a PAGE row - which it feeds
straight to an axis calibration. On publication 127 that is an error of 620,
1580 or 2510 rows: the error bar drawn 25 px above a bar top reports a
dispersion of 142 units instead of 8.3. Every row-carrying field is now
`*_row_panel` or `*_px_image`, and `measure_panel` computes the dispersion
itself, because computing it is what proves the two rows are in the same frame.
Against the synthetic fixture's declared SDs of 6.0, 5.0 and 4.0 it reads
5.83-6.11, 4.72-5.00 and 3.61-3.89.

Publication 127 Figure 4 now reads 18 cells of 18, two of them value-only
because their bars are 15 px tall. The synthetic fixture's worst mean is 0.11
units on a 100-unit axis.

`forward_test_127_mono_bar.py` holds that result. It SKIPS loudly when the
raster is absent, FAILS on a hash mismatch, and otherwise checks structure -
eighteen cells, sixteen with a fill, no extent contradicted, no group refused
for geometry, one stroke across all three sub-panels, and three fills that do
not overlap - plus a per-cell baseline. **That baseline is self-measured, not an
independent reading**; 397 has an eye reading and 127 does not, and until it
does this file detects drift rather than validating the figure. Reverting the
recentred anchors fails it; reverting the texture ROI fails it; substituting a
different page of the same PDF exits 2.

The geometry's fill bands are the MIDPOINTS of the gaps between the measured
fills, not a fit to them - a band drawn at the gap admits a different render and
still excludes the neighbouring fill. `source_pdf_sha256` is declared and null:
the raster hash pins which render was measured, not which publisher PDF bytes
produced that render, and the forward test prints the gap rather than passing
over it.

## The error bars publication 127 had all along

The prototype read 18 means from publication 127 and **zero** dispersions, and
nothing said so, because the forward test checked means and fills only. The
figure has 18 error bars. What it does not have is caps 30% of the bar wide,
which is what the cap test demanded - a fraction fitted to the synthetic fixture
in this package, whose caps are 0.70 of the bar. Publication 397 draws its caps
at 0.18 of the bar and publication 127 at 0.17-0.19, so the test found none of
either figure's error bars and the prototype had been reporting no dispersion
for both since it was written.

An error bar is a NARROW stem carrying a WIDE cap, and that is the whole of the
distinction. Measured against its own stem instead of against the bar, every cap
in all three figures reads between 5 and 11 times the stem it hangs from, and
every non-cap row reads 1.0-1.2. Three further things had to be measured rather
than assumed before that worked:

**Where the bar ends and the error bar begins.** Skipping a fixed stroke of rows
is right when the bar's top rule is one stroke thick and wrong when the whole
error bar is short: on publication 127's SUPINE bars the stem is a SINGLE row
between the top rule and the cap, and the fixed skip stepped over it. The scan
now walks off the bar - past rows still as wide as the bar - and starts at the
first row that is not the bar.

**Which rows a cap may occupy.** "More than a stroke from the edge" was
consistent with the fixed skip and stopped being so once the skip was measured;
on a bar whose entire error bar is four rows it excluded the cap itself. It is
"beyond the bar" now, which is where the measured start already ends.

**The bar's own antialiased edge.** Nothing is printed thinner than one stroke,
so a sub-stroke component lying against the bar end is the row the walk stopped
just below, not a structure - `BAR_EDGE_REMNANT`. Both conditions are needed: a
one-pixel mark a hundred pixels away is a glyph and is still classified as one.

Publication 127 now yields 18 means and 18 SEs, publication 397 eight means and
five, and the synthetic fixture's SEs land within 0.39 units of the 6.0, 5.0 and
4.0 they were drawn at.

## Two panels of one figure, two strokes

Adding publication 397's WOMEN panel to the prototype - it had only ever
measured MEN - showed immediately that the two panels of one JPEG measure
different strokes: MEN's axis is one row at 118 px, WOMEN's is two rows at
116 px. Publication 127's three sub-panels read 3, 3 and 4 for the same reason.
The stroke is a property of the panel as rendered, "all panels of a figure agree"
is false, and the forward tests pin it per panel instead - which is the stronger
check anyway, since an invariant passes when every panel is wrong together.

The WOMEN panel also carries three defects that are PINNED RATHER THAN FIXED, in
`forward_test_397_mono_geometry.py`: one bar whose extent does not resolve
(correctly refused - the ink above it really is bar), and three cells whose caps
are not found, because the stem there is one to two pixels and runs off the
bar's centre line. Its four means are within 0.55 mmHg of the eye reading
regardless. Recording them is what stops them being rediscovered a third time.

## Series identity is not slot order

Two of publication 127's bars are 15 px tall, have a mean and an SE, and have no
measurable fill. A BAR_MONO series is identified BY its fill, so those two have a
geometry and no identity, and calling them OPEN and SOLID because of where they
sit would be identifying a series by position. Records carry
`identity_status`; the figure is 18 geometries and 16 identities, and the
forward test asserts both numbers rather than reporting 18 cells read.

`test_measure_mono_bars.py` also draws the fill publication 127 broke on and
that no fixture in this package had - a STIPPLED bar, interior under a tenth
inked, four blank rows in every six, over 180 px tall - and renders the whole
panel at half, one and double size. Everything in CI is drawn at a 1-2 px
stroke; the claim that every length is a multiple of the stroke had never been
checked at any other one.

## Figure-local one-to-one fill identity

`_FILL_BANDS` names a series by asking which absolute density band its bar falls
in. That works on the one figure the bands were measured on. `fill_identity()`
in `measure_mono_bars.py` asks a different question: given the fills this figure
DECLARES, which bar is which — decided from the figure's own samples, one bar to
one pattern, or not at all.

Four relations, and none of them is a measurement:

| word | what it means about the interior |
|---|---|
| `OPEN` | paper — the LEAST ink in its group |
| `SOLID` | ink — the MOST |
| `HATCHED` | continuous strokes, so no row of the interior is blank |
| `STIPPLED` | isolated islands, so some rows are blank |

The first two are relations within a group and say nothing about absolute
density. The last two are structural and say nothing about which is darker —
which matters, because a dense stipple carries more ink than a sparse hatch, so
ordering all four by ink would be a claim about typesetting rather than about
the words. A scenario draws exactly that inversion and both bars are still
named correctly.

**Two stages, because a bar too short to sample a fill would otherwise take the
identity of the slot it sits in.** Only groups where every slot yielded a fill
can be assigned from the relations — "least ink in the group" is not a statement
about a group with a hole in it — and those groups give the figure its own
prototype range per pattern. Every remaining sample is then matched against
those ranges, and only when it falls inside exactly one.

**The separation test needs no threshold.** Each pattern has a SPREAD across the
figure and each pair of patterns a GAP; the vocabulary is established only when
every gap exceeds the spreads it separates. On publication 127 the spreads are
0.000–0.020 and the smallest gap is 0.148. A pattern seen once has no spread and
inherits the widest in the figure, so it is held to the same standard rather
than to none.

**A figure, not a panel.** Publication 127's Figure 4 is three sub-panels, and
its middle panel alone offers one sample per pattern — one sample has no spread,
a figure with no spread cannot estimate its own noise, and nothing matches
against a prototype of zero width. Pooled across the figure, that panel's three
uncalibratable cells are named immediately. `figure_id` says which panels are
one figure and defaults to the panel tag.

Result on the whole corpus: publication 127 **16 of 18 cells named, none wrong**
— the two unnamed are the 15 px bars with no measurable fill — publication 397
7 of 8, and the synthetic fixture 12 of 12. Every figure reports ESTABLISHED.

## Five contracts closed before the reader is touched

Each of these is independent of the production rewrite and each would otherwise
have been carried into it, so they were closed first.

**A refusal must file itself under the right reason.** The STIPPLED refusal
raised `ValueError`, and `run_batch` maps that to `PANEL_GEOMETRY_UNRESOLVED` -
so "this reader has no STIPPLED" would be recorded as "this panel's geometry
cannot be trusted". Fail-closed with the wrong reason is the kind of thing a
reviewer acts on and a maintainer chases. It raises `UnsupportedCapabilityError`
now, which maps to `NO_READER_AVAILABLE`, and `test_run_batch.py` asserts the
terminal state end to end rather than the exception message at the reader.

**Sampling a fill is not naming a series.** One field called `identity_status`
answered "did this bar have an interior to sample" while the forward tests read
it as "was this series identified" and reported sixteen identities that were
sixteen samples. `measure_panel` sets `fill_sample_status`
(MEASURED / UNRESOLVED_NO_INTERIOR) and nothing else - it measures one panel and
identity is figure-local, so it cannot name anything.
`fill_identities_by_figure` sets `identity_status`
(RESOLVED / AMBIGUOUS / NOT_CALIBRATED / UNRESOLVED_NO_FILL) and
`resolved_fill_pattern`, and both forward tests now assert the real identity
against the declared fill.

**One figure per vocabulary.** `figure_id` was recorded and not used:
`fill_identity` pooled every record it was handed, so passing two publications
would silently build one figure-local vocabulary out of both. It refuses with
`MULTIPLE_FIGURES`, and `fill_identities_by_figure` is the entry point that
splits them.

**A prototype range needs a width before anything is matched against it.** One
complete group gives one sample per pattern, every spread is zero, and any
non-zero gap beats a zero floor - so a single group reported ESTABLISHED and
incomplete groups were matched against ranges of zero width. That is now
`DIRECT_ONLY`: the complete group keeps the identities it can force from
relations inside itself, and nothing leans on them. `ESTABLISHED` requires at
least two complete groups and a non-zero spread.

**A bar is never named a pattern its own group does not declare.** Partial
matching searched every prototype in the figure, so a group declaring OPEN and
STIPPLED could come back SOLID if its one sample reached that range. The search
is restricted to the group's declared set.

## Three more identity contracts, and a design point they exposed

**A complete group nobody can assign is AMBIGUOUS, not absent.** With nothing
assigned, `fill_identity` reported `NOT_ENOUGH_COMPLETE_GROUPS` whether the
figure had no complete group or had one and could not tell its patterns apart.
The second is a finding about the figure and the first is a finding about the
data, and the wrapper carried the confusion onto every bar as `NOT_CALIBRATED`
where the truth was `AMBIGUOUS`.

**A group is complete against its DECLARATION, not against what arrived.**
Completeness was decided from the records in hand, so a group of three whose
third record was lost to a defect looked like a complete group of two - every
record present had a fill, and the missing pattern had gone with its record.
Every record now carries `declared_group_size` and `declared_group_patterns`,
and a group whose arrivals do not match is `truncated`, named with the slots
that went missing, and never used to calibrate.

**Structure decides HATCHED against STIPPLED in partial matching too.** Complete
groups separate them by whether any interior row is blank; matching an
incomplete group used ink alone, which throws away the only evidence there is
and re-introduces the ordering this file refuses. A hatch at pitch 14 reads
0.357 - inside a stipple prototype's range and outside its own - and was renamed
on that. It is now held to `_structurally_possible` and left unnamed instead.

That change exposed a design point in the separation test. Requiring an ink gap
between HATCHED and STIPPLED is the same ordering smuggled in as a validity
check: a sparse hatch and a dense stipple are correctly named by structure and
have no gap to show. The gap test now applies to pairs decided on ink and
records `separated_by: STRUCTURE` for the pair that is not.

**And the floor is measured.** `ink_mass_tile_spread` is how much a bar's own
interior varies across its vertical tiles - a stipple's by a few hundredths, a
solid bar's by nothing. It is the measurement's uncertainty, taken from the bar,
and it joins the pooled spread as the floor a gap must clear. A figure with one
complete group has no cross-group spread, so without it any difference at all
forced "least" and "most": a bar inked only in its top third has a mean of 0.12
and varies by 0.35 across itself, and used to be called the darker of two with
confidence.

## A group is its declared slots, exactly

Completeness compared the slot COUNT and the pattern set. Slots {0, 1, 3}
against a declared three has the right count and the right patterns while
missing slot 2 and carrying a slot the panel never declared, and a slot that
arrives TWICE overwrites its predecessor in the dictionary - the group then
looks one record short while reporting no missing slot at all. The exact set is
compared now, the arrival list is kept beside the dictionary so a repeat is
visible, and a truncated group is named with its `missing_slots`,
`unexpected_slots` and `duplicate_slots`.

## What the reader writes and what a person may enter

`IDENTITY_EVIDENCE` held both halves, and one enum containing both says they are
interchangeable. `FILL_MEASURED` is what the READER produces; a person typing it
into `identity_resolution.csv` would be recording an automatic measurement for a
cell where the reader explicitly could not make one. `AUTO_IDENTITY_EVIDENCE`
and `HUMAN_IDENTITY_EVIDENCE` are separate now and only the second is accepted
in that file.

The trust order is written out as `IDENTITY_EVIDENCE_RANK` rather than implied
by tuple position, because the old comment said "ordered least to most trusted"
over a tuple whose LAST entry is the weakest evidence there is - a reviewer's own
reading, with no legend and no sentence behind it.

## STIPPLED is declarable before it is readable

`batch_manifests.BAR_FILL_PATTERNS` now accepts `STIPPLED`, and
`mark_readers.read_monochrome_bar_panel` refuses a series that declares it, by
name, with the reason.

That combination is deliberate. Without the word, whoever writes publication
127's manifest has to declare the nearest lie — `HATCHED`, on a fill that reads
0.144–0.157 against hatching's 0.262–0.318 — and a lie in the manifest is the
one class of error the QC layer cannot catch, because every check downstream
agrees with it. With the word but no refusal, the absolute-banded classifier
would put the bar in whichever band it happened to land in, which on this figure
is `HATCHED` again, silently. Refusing by name leaves the cells unread and
visible, which is the only honest state until the reader carries the identity
above.

## The whisker is centred on the series, not on the bar

Publication 397's WOMEN panel was losing three of its four dispersions, and the
reason was not the cap rule. Its whiskers are drawn at 39% of the bar's
footprint width; the stem trace looked in the bar's middle fifth and missed them
by two pixels. `stem_band()` finds the stem instead: among the narrow runs of
ink in the first rows above the bar, the one nearest the centre - narrow because
a stem is a hairline, and a run wider than a few strokes is the bar's own
antialiased top, which is what the first row above a solid bar holds at the stem
threshold.

Replacing the middle with the measured run found 397's stems and cost five of
publication 127's cells, whose stems are central and whose masks then left a
residue the classifier could not name. The band is the UNION of the two: it
never costs a trace and never leaves more behind.

Publication 397 now yields eight means and **seven** dispersions against five,
and both hatched cells are closed. What remains pinned is WOMEN PRE/SOLID, and it is now
diagnosed rather than merely recorded: the two bars of that group TOUCH. The
solid bar occupies columns 16-73 and the hatched one starts at 78, and the
hatched bar's leading diagonals reach back to column 74 on some rows. The seed
band reads those columns as inked, so the solid bar's footprint comes out 16-77
- four columns into its neighbour - and above the solid bar's top those four
columns carry the hatched bar's body. A structure inside the footprint that is
not this bar, correctly refused, and caused by the FOOTPRINT rather than by the
classifier.

`trim_to_own_bar` now closes the footprint half of it. Each column's VERTICAL
OCCUPANCY is measured in the body band between the provisional bar top and the
baseline - the part of the slot that is bar and nothing else - and compared with
the most inked column just inside it; the walk goes in from each end. That takes
WOMEN PRE/SOLID from 16-77 back to 16-73 and drops all four of the neighbour's
columns, and POST/SOLID three more.

Three things had to be right at once. The BAND has to exclude the error bar: an
earlier attempt compared each column's topmost ink instead, on the theory that a
bar's top is level, and the topmost ink in a column is the cap - the fixture
lost three bars per group and the corpus fell from 37 dispersions to 23. The
REFERENCE has to be local: a global median trims an open bar's own side strokes,
because its interior is paper, and a global maximum trimmed all four of 397's
hatched cells to nothing, because those bars have a top rule but no side strokes
and one column catching two diagonals outvotes the rest. And the inward REACH
has to scale with the footprint: two strokes suffices for a four-column bleed
and sits inside a forty-column one, so it is bounded at a quarter of the
footprint - beyond that a trim cannot repair the footprint and the convergence
guard refuses instead.

Two contracts the first version only claimed in a comment are now real. The
SECOND PASS: the trim needs an extent and the extent needs a footprint, so one
round of each proves nothing - trimming again from the re-traced extent must
leave the footprint where it is, or `FOOTPRINT_DID_NOT_CONVERGE`. The guard that
stood in for it only fired when the footprint had become narrower than four
strokes, which is a different fact under the same name. And the TRIM BUDGET is
separate from the look-ahead reach: a footprint whose outer quarter is somebody
else's bar is refused with `EXCESSIVE_TRIM` rather than measured from whatever
survived. That branch is implemented and NOT pinned by a scenario - a synthetic
bleed wide enough to spend the budget would not seed into the footprint at all -
and the docstring says so rather than claiming coverage.

The footprints are asserted exactly, in the forward test and in the synthetic
touching-bars scenario. "Something was trimmed and the mean survived" passes
just as well when the trim ate a third of the bar, because a solid bar's top
does not move when you narrow it.

### Both refusals, pinned

Two branches the trim can reach were implemented and not tested, and neither is
reachable from a raster: a bleed wide enough to spend the trim budget is too
faint to seed into a footprint at all, and a second pass that moves the footprint
again needs a figure nobody has found. So they are pinned in two places instead.

`trim_to_own_bar` takes a footprint, so `EXCESSIVE_TRIM` is pinned by calling the
primitive directly with a synthetic occupancy profile - a 40-column footprint
whose right eleven columns fade away - and asserting that the footprint comes
back untouched with the refusal named, and that the same figure inside budget
trims cleanly.

`refine_footprint` is the orchestration - one trim, one re-trace, one confirming
trim - extracted so its state transitions can be driven by fakes. That pins which
refusal, under which name, carrying which record: a footprint that settles is
used with both passes run, one that keeps moving is `FOOTPRINT_DID_NOT_CONVERGE`
with both footprints and both edge rows on the record, and a trim that overruns
its budget keeps the name `EXCESSIVE_TRIM` on either pass with
`convergence_stage` saying which. That last one was a real defect: an over-budget
trim hands back the footprint it was given, so filing it as a convergence failure
produced records claiming the two passes disagreed while showing two identical
footprints.

### And the structure that was left

Trimming was not enough for that cell, and the 2 px by 14 row structure at
columns 72-73 turned out not to be trimmable at all. Read across a wider span it
is the HATCHED BAR'S OWN TOP RULE: rows 219-221 are a continuous rule from
column 72 to column 129 while the solid bar occupies 16 to 74. The neighbour's
outline overhangs three columns to the left, above the solid bar's top, into
columns that BELOW that top are solid bar. No trim can take them - they are this
bar's columns.

So nothing inside the footprint can settle it, and the signal is what happens
OUTSIDE. A bar is never wider than its own footprint, so ink that continues past
it is not this bar's body: `NEIGHBOUR_STRUCTURE`, which does not refuse the cell.
It applies only to a component that does NOT look like a body - a footprint can
also UNDER-cover its bar, and then what lies beside it is this bar's own ink,
which is what a full-width hatch above a printing gap looked like before that
restriction went in.

**What "continues past it" means was wrong twice, and both are now fixed.** The
test was ADJACENCY, row by row: the component's own edge pixel and a pixel of
the two-stroke MARGIN beside it, inked on the same row. Two things are wrong
with that, and NEIGHBOUR_STRUCTURE is the one classification here that LIFTS a
refusal, so both return a number where one should have been withheld.

The margin is not a bar. A structure that leaves the footprint and stops two
pixels later in empty paper satisfies the test, and so does a footprint that
under-covers its own bar by two pixels - it hands its own side stroke away and
stops refusing itself over it. The test now asks whether the object reaches a
NEIGHBOURING BAR'S COLUMNS, which `geometry_rows` supplies from the group's
other seed footprints. A caller that does not say what is next door gets the
refusal, not the benefit of the doubt.

And the object was not an object. Components in the classifier are ROW BANDS -
everything inked in a range of rows - so a band holding a residual sliver in the
middle of the bar AND, on the same rows, a structure running out to the
neighbour was one component, and the residual inherited the crossing. The
question is now asked in 2-D over the whole group window, with the bar's own
stem and cap removed first so they cannot bridge two unrelated structures, and
of EVERY object the band holds inside the footprint: one that does not reach a
neighbouring bar is something this bar has not accounted for, and one is enough
to withhold the number.

An earlier note here said labelling could not supply this, on the grounds that
two horizontally adjacent pixels are eight-connected by definition so an
8-connected labelling of [margin | footprint | margin] returns the same answer
as the adjacency test. That was true of the labelling as it was scoped - three
strips, one row band at a time - and false of the question. Labelled over the
whole window, per object, against the neighbour's footprint rather than the
margin, it is a different answer in three of the four cases the scenarios draw.

The labelling is written out rather than taken from `cv2.connectedComponents`,
because cv2 is optional here and a classification that says one thing where it
is installed and another where it is not is not a classification. A scenario
checks the two agree, on a fixture with diagonal chains, single pixels and
structures touching both walls.

On the corpus this moves one classification and no value: publication 397's MEN
POST hatched cell had a component reaching its right-hand margin with no bar
beyond it - the panel's own furniture - and it is now ANNOTATION_OR_GLYPH.
Publication 397's WOMEN PRE/SOLID, the cell this whole section exists for, still
resolves, and now resolves because the hatched bar next to it really is next to
it. Both figures remain at 8/8 and 18/18.

**Publication 397 now reads 8 means and 8 dispersions**, worst mean 0.75 mmHg
against the independent eye reading, all eight series named. That is the invariant
the production reader has to hold while it is rewritten, and the prototype now
meets it. Publication 127 is unchanged at 18 and 18.

One scenario changed rather than being fixed: the fixture for "ink continuous
with the bar that is not shaped like the bar" was drawn as a narrow spur ending
in a wider blob, which is what an error bar IS. Once the stem was measured
rather than assumed, the reader read it as one - correctly. The fixture is now a
patch too wide to be a stem, too narrow to be the bar, and off to one side.

## Naming what the reader could not measure

Two of publication 127's bars are fifteen pixels tall. They have a mean, an SE,
and no interior to sample. A BAR_MONO series is identified BY its fill, so
naming them from the pixels would mean "first slot, therefore OPEN" - identity
by position, the one inference this package refuses. Publication 127 cannot be
finalized while they are unnamed, and no amount of work on the reader will name
them.

`identity_resolution` is the twelfth manifest: one row per
(`Panel_ID`, `Group_ID`, `Geometry_Slot`), carrying `Resolved_Series_ID`,
`Resolved_Fill_Pattern`, `Evidence_Type`, `Evidence_Artifact`,
`Evidence_Artifact_SHA256`, `Reviewer_ID` and `Reviewed_At`.

Three reasons it is an input rather than a decision inside an approval.

An approval says "the number the reader produced is right". This says "here is
something the reader did not produce". Those are different claims made on
different evidence, and a reviewer who can check a bar top against an overlay is
not thereby qualified to have read the legend.

It has to carry where the identity came from. `Evidence_Type` separates a legend
that labels the fills (`LEGEND_DECLARED`) from a sentence in the methods
(`TEXT_DECLARED`) from a reviewer's own reading (`REVIEWER_INSPECTION`), and the
artifact points at the thing that can be re-examined. The last of the three is
the weakest and is recorded as itself rather than as a fact.

And it has to be hashed with everything else, or a resolution can change after
the values were approved and silently re-label a series between the review and
the pooling.

The slot is how a row joins to a measurement; it is NOT what names the series.
There is deliberately no `Pattern_Slot_Order` column: a declared order is the
positional inference with a manifest around it.

**Not yet wired.** The schema, its template and its contract are in place and
tested; joining it into `run_batch`, the QC gate and the finalizer's subject
hash is part of the integration commit, because a resolution the finalizer does
not hash is worse than none.

## One measurement, two callers

The geometry is now `mono_bar_geometry.py`, imported by the diagnostic driver
and - once the integration lands - by the production reader. Two implementations
of one measurement drift, and this project has already paid for that: the
prototype read publication 397's WOMEN panel for weeks while the production
reader was never pointed at it, and the two disagreed about that panel's stroke,
its caps and its footprints with nothing in place to notice.

`measure_mono_bars.py` keeps the spec format, the corpus and the table.
`mono_bar_geometry.py` opens no figure and decides nothing: it measures and it
refuses. A scenario asserts that every geometry function the driver uses IS the
shared object rather than an equal copy, and that the shared module does not
carry the diagnostic corpus - a copy-paste back into the driver leaves every
other scenario passing and starts diverging on the next fix to either.

The panel loop went with it, as `geometry_rows` - taking an already-loaded
greyscale array and any object with `value_to_pixel` and `pixel_to_value`,
rather than a spec. Two reasons, and neither is tidiness. The production reader
can call it without adopting the diagnostic spec format, so it cannot end up
with its own copy of the loop. And a calibration OBJECT rather than tick points
means the module imports no axis module, so no cycle forms the moment
`mark_readers` imports it - a scenario asserts that no import line in the file
mentions `mark_readers`.

`geometry_rows` is the ANONYMOUS GRAIN: it names no series. Geometry is per
panel and identity is per figure, so a reader that names a series while it
measures a panel is naming it from the only thing a panel knows - where the bar
sits - which is the inference this package refuses. Its records come back
`NOT_CALIBRATED` with an empty `resolved_fill_pattern`, and
`fill_identities_by_figure` names them once every panel of the figure has been
measured. `measure_panel` is now four lines that supply the spec.

The split changed no number, and the record stream is byte-identical: 38 of 38
cells, 397 at 8 means and 8 dispersions, 127 at 18 and 18.

## The production module can now measure without naming

`mark_readers.read_monochrome_bar_geometry` is the second half of the extraction:
the production module measuring a panel through `mono_bar_geometry.geometry_rows`
and leaving the identity open. It sits BESIDE `read_monochrome_bar_panel` rather
than replacing it, because the two answer different questions and only one of
them can be answered by a panel.

The existing reader returns rows carrying a `series`. To do that it decides,
inside one panel, which bar is which, and the only evidence a panel holds is an
absolute fill density against `_FILL_BANDS` - measured on one figure and wrong on
the second. The new one returns `identity_status: NOT_CALIBRATED` and an empty
`resolved_fill_pattern` on every row, and naming happens afterwards across the
whole figure in `fill_identities_by_figure`, which needs samples from every panel
before it can say what the figure's fills look like. That is why this could not
simply be folded into the old reader: the CALLER has to collect panels first,
which is a change to `run_batch`, not to a reader.

`mark_readers` imports `mono_bar_geometry` and `mono_bar_geometry` imports
nothing from `mark_readers` - it takes a calibration object, not tick points - so
the dependency runs one way and a scenario asserts it.

What remains for publication 127 to reach FINALIZED is the caller: `run_batch`
collecting BAR_MONO panels by `Figure_ID`, resolving identity across them,
applying `identity_resolution.csv` to the cells the figure could not name, and
carrying that file through the validator, the grid gate, the run stamp and
`Review_Subject_SHA256`.

## Four contracts before the caller is written

Everything above measures. The four items here are about the SHAPE of what it
hands over, and all four were found by reading the record stream rather than by
a failing scenario - which is the point: each one produces a plausible answer.

**The measurement was not in the reproducibility stamp.** `run_batch` writes
`Pipeline_Code_SHA256` so a value that moved between two batches can be
attributed instead of argued about, and `mono_bar_geometry.py` - the whole
monochrome bar measurement, stroke to texture - was not among the files it
hashes. The function that decides where a bar top is could have been rewritten
between two runs and the stamp would have said the two were produced by
identical code. It is hashed now, and the scenario does not check the tuple
against a second hand-written copy of itself: it WALKS the modules `run_batch`
actually imports, keeps the ones that live in this package, and fails on any
that is not hashed. Then it appends one byte to `mono_bar_geometry.py`, checks
the hash moved, and puts the file back.

**A per-slot `declared` was a series named by position.** `geometry_rows` wrote
`declared=fills[k]` on every record. `fills` is a human's left-to-right reading
of the printed panel, so a per-slot copy of it inside the anonymous grain is
exactly the inference this package refuses - and it made the entire record
stream depend on the order the spec happened to list the fills in. The record
now carries only `declared_group_size` and `declared_group_patterns`, the
group's SORTED multiset, and `fill_identity` reads the group-level declaration
rather than assembling one from slot positions. Three scenarios hold it: the
same panel measured with the fills listed in three different orders produces
records that are identical field for field; a deliberately wrong `spec_fill` on
every record changes no identity; and two records of one group disagreeing about
their own declaration is now a finding (`INCONSISTENT`) rather than a longer
list, as is a group with no declaration at all (`MISSING`).

`spec_fill` is what the diagnostic driver staples on AFTER the measurement - the
pattern the SPEC lists for that slot, which is fixture truth and the only way to
check that `resolved_fill_pattern`, computed from ink and structure, agrees with
what a person reading the figure says is there. The permutation and the
scrambling scenarios are what keep it from quietly becoming an input again.

**A refusal was a different shape from a reading.** Error rows carried no
`figure_id`, no `slot`, and no identity fields. `fill_identities_by_figure`
buckets on `figure_id` and falls back to the panel, so a `STROKE_SCALE_UNRESOLVED`
row from one panel of a two-panel figure landed in a bucket of its own and the
figure came back with TWO verdicts - the second computed from a panel that had
already refused. Every row now comes from one `row()` base: `figure`,
`figure_id`, `group`, `slot`, the group declaration, `fill_sample_status`,
`identity_status` and `resolved_fill_pattern`, on refusals as much as on
readings. `NOT_SAMPLED` is a new value and is not `UNRESOLVED_NO_INTERIOR`: the
first says the bar never reached the sampler, the second that it did and there
was nothing to read. All four refusal paths are driven in the scenario, and the
two-panel case is built through the shared entry point with the figure named,
because re-labelling records afterwards is what hid the defect.

**`panel_id` and `figure_id` are required and keyword-only.** They defaulted to
`""`, which is the shape that made the same defect invisible from the other
side: a caller that forgot got one bucket named `""` holding every panel of
every figure it had measured, and those panels calibrate a SHARED fill
vocabulary. Two publications pooled into one vocabulary is not a crash - it is a
plausible answer computed from the wrong figure, and the only place it would
ever be noticed is a value in a meta-analysis. Blank is refused as loudly as
missing. The wrapper also takes an ndarray now, RGB or greyscale, so a caller
holding the array this package works in internally does not have to wrap it back
into a PIL Image to hand it over.

Deleted in the same round: a dead `_gray(path)` in `mono_bar_geometry.py` that
referenced `Image` without importing PIL. It was unreachable, so nothing failed;
it would have raised `NameError` the first time anyone called it.

**Two panels of one figure, through the production wrapper.** The grain the
whole design turns on had scenarios at the prototype and none at
`read_monochrome_bar_geometry`, which is what `run_batch` will call. Three
panels now go through it: one group each, two of them one figure and the third
a different publication. One panel alone is DIRECT_ONLY, because every prototype
range it produces has zero width; the two together are ESTABLISHED and name all
six bars; the third is answered separately, keeps its own single group, and does
not change what the first figure says. Pooling by panel instead of by figure
makes the pair DIRECT_ONLY and leaves publication 127's two unnameable bars
unnameable; pooling everything handed in makes the third publication part of the
first one's vocabulary.

## The option contract and the written-down row

Two things had to be settled before `run_batch` could be pointed at the new
reader, because both are cheapest to get wrong at the switchover.

**Every BAR_MONO option is a parameter of the successor.** The manifest declares
five for BAR_MONO - `threshold`, `stem_threshold`, `group_window`, `min_bar_px`,
`baseline_value` - and `read_monochrome_bar_geometry` took two of them. At the
switchover that is either a `TypeError` on the first batch or, worse, the
tempting fix: filter the options down to the ones the reader takes, which turns
three settings a person wrote in a manifest into three settings nobody applies.
`run_batch.SUCCESSOR_READERS` now declares the replacement before it is wired,
and the same introspection that guards `reader_functions()` guards it, so the
contract is checked today rather than discovered later.

The two ink thresholds are threaded all the way down - `stroke_scale`,
`seed_support`, `trace_extent`, `trim_to_own_bar`, `remote_support` - instead of
each helper defaulting its own. A panel read at one threshold and classified at
another is not one measurement. Nothing on the corpus moves, because every
figure this package can reach is dark ink on white paper and 128 separates them
all; the scenario that proves the option is not silently dropped is drawn in
GREY, at 170, where 128 sees nothing and 190 sees the figure. A second scenario
drops `stem_threshold` below the stem's own grey: the body still reads, the cap
loses the stem it hangs from, and the cell fails closed rather than quietly
returning a mean with no dispersion.

**`min_bar_px` changed grain, and had to.** In `read_monochrome_bar_panel` it is
a test on the whole group's inked span against `min_bar_px * n_series`, and a
group that fails it is SKIPPED - `continue`, no record, no error. The panel then
reports fewer bars than it declared and nothing says why, which is the exact
failure `NO_SEED_SUPPORT` was added to close. Here it is one bar's footprint,
measured after the trim, and a bar that fails is refused by name with its width
on the record: `BAR_TOO_NARROW`. The number means the same thing to a person and
the group no longer disappears around it. The narrowest footprint anywhere in
the corpus is 27 px, in the synthetic fixture; publication 127's are 182-188.

**`mono_bar_geometry.csv` is canonical or it is nothing.** A geometry record is
nested - `remote` is a list of dicts, `t96`..`t192` are dicts, `stroke` is a
dict - and handing that to a CSV writer stringifies it with `repr`: no parser,
dependent on dict ordering and float repr, and a hash over it moves when the
same numbers are written by a different interpreter. Sixteen columns are named,
everything else goes into `Diagnostics_JSON` as JSON with sorted keys, no
spaces, and numpy scalars converted to the numbers they are rather than through
a `default=str` that would quote them.

`Geometry_Row_SHA256` is stamped at the end of the measurement and covers the
ANONYMOUS record only. Identity is written onto records in place, so a hash over
the whole record would change the moment a series is named - and the question it
exists to answer, "is this the same measurement the reviewer approved", would
stop having one. Naming the series, and a human overriding that naming in
`identity_resolution.csv`, both leave it untouched; a value that moved by 0.001
does not.

Also settled: `prototype_ready` said "at least two complete groups AND a
non-zero spread" in the docstring and `len(complete) >= 2` in the code. Two
groups that reproduce each other exactly have a floor of zero, and matching an
incomplete group against a zero-width range with a zero tolerance is the luck
the group count was added to prevent, reached from the other side. It is both
halves now, with a fixture that draws its two groups at the same height.

And `geometry_rows` requires `panel_id` and `figure_id` as keyword-only
arguments too, not only the production wrapper. It is a public name that the
driver and the scenarios call directly, and the `figure_id = figure_id or
panel_id` fallback it used to have is the same "" bucket that pools two
publications into one fill vocabulary.

## Read at one threshold, classified at another

The threshold reached the geometry and stopped there. `texture` reports four
fixed blocks - `t96`, `t128`, `t160`, `t192` - and `_sample` took the STRUCTURAL
half of the identity from `t128` whatever the caller configured. So a panel read
at 190 was classified at 128, which is precisely what threading the option
through was supposed to stop.

The four blocks stay, because a feature that separates at one threshold and not
at another is an artefact of the cut point and seeing that needs all four. What
is new is an `identity_*` block computed at the threshold the panel was READ at,
and `_sample` takes `rows_all_inked` and `segment_density` from it. At the
default of 128 that block IS `t128`, which is why nothing in the corpus moves.

What it costs is not a refusal. A grey hatch has ink at 190 and none at 128, so
it came back `rows_all_inked = False` and HATCHED became structurally impossible
for it. Inside a complete group that is a refusal - the whole group goes
unassignable. Against prototypes another group has already established it is a
RENAMING: the bar is matched on ink alone against whichever pattern is still
structurally possible. The scenario draws exactly that - two black groups
establish the vocabulary, then a grey hatch at pitch 18 whose INK lands inside
the black stipple's prototype range - and with the fix reverted it comes back
STIPPLED.

## What the artifact refuses to write down

Two guards, both on `artifact_row`, both for things that produce a plausible
file rather than an error.

**A row that moved after it was stamped.** The hash was copied out of the record
while the columns were filled from the record as it then stood, so an edit
between the two wrote a changed `Mean` beside an unchanged
`Geometry_Row_SHA256`. A file attesting to a measurement it does not contain is
worse than a file carrying no hash. `artifact_row` now recomputes and refuses on
disagreement - `GEOMETRY_ROW_MODIFIED_AFTER_STAMP` - and because identity fields
are outside the hash, naming a series still passes. An unstamped record, from a
hand-built row or an older run, is hashed rather than refused.

**A row carrying a human identity.** `identity_resolution.csv` is where a
person's answer lives, with the evidence and the reviewer beside it. A caller
that applied it by overwriting `resolved_fill_pattern` and re-emitting the
geometry file would record a human decision in a column called
`Auto_Fill_Pattern` - an audit trail saying the machine decided something a
person did, in the one file that holds what the FIGURE said.
`fill_identities_by_figure` stamps `identity_source = AUTO` on every row it
touches and `artifact_row` refuses anything else, so the join has to happen
downstream where `Identity_Source` can be recorded honestly.

And the canonical serialiser got stricter in two ways it should have been from
the start. `allow_nan=False`, because Python will write `NaN` and `Infinity`
into what it calls JSON and no other language's parser will read them back - a
diagnostic that arrives as NaN is a measurement that went wrong, and here is
where to find that out. And `_plain` raises on a type it does not know instead
of falling back to `str(obj)`: a set, a Path, a dataclass would be folded into
the hash as text that looks like data, and the first time two runs disagreed the
difference would be a memory address.

## Three guards that only stop an honest caller

Each of the three below was a guard that worked against a caller doing the
right thing and not against the caller bug it exists for.

**A missing stamp was a way past the stale-row check.** `artifact_row` refused a
row whose hash disagreed with its contents and hashed a row that carried no hash
at all - so deleting one field laundered an edit into a canonical artifact:

    row = geometry_rows(...)[0]
    del row["geometry_row_sha256"]
    row["value"] += 1.0
    artifact_row(row)                # written, with a hash of the new value

`geometry_rows` stamps every row it returns, so an unstamped row is a row that
LOST its stamp. It is refused now - `GEOMETRY_ROW_UNSTAMPED` - and a migration
utility reading rows written before the stamp existed has to say so with
`allow_unstamped=True`. A batch run does not, because that is the default.

**`identity_source` only stops a caller telling the truth.** The join that goes
wrong does not set the source to HUMAN; it forgets to:

    fill_identities_by_figure(rows)          # identity_source = AUTO
    rec["resolved_fill_pattern"] = human     # the join overwrites the pattern
    rec["identity_status"] = "RESOLVED"      # and leaves the source alone
    artifact_row(rec)                        # a person's answer, filed as AUTO

So the auto answer attests to itself. `auto_identity_sha256` covers the row's
own measurement hash, the figure's verdict hash, and the two fields the answer
consists of; `artifact_row` recomputes it and refuses on disagreement. That
catches an overwritten pattern, an overwritten status, an identity nobody
attested to at all, one bar's name moved onto another, and a name carried over
from a different figure's verdict. A row measured and not yet named carries no
attestation and needs none - its identity fields are still at their
measurement-time defaults, and that is what the check requires of them.

`Domain_Identity_SHA256` and `Auto_Identity_SHA256` are both columns, so a
reader can recompute the attestation from the file rather than trusting it.

**Canonical JSON was strict about values and not about keys.** `str(k)` folds
`1` and `"1"` into one JSON key, so one of them disappears, and an object key
would arrive as its repr - the non-determinism the value branch had just
removed, back on the other side. Non-string keys raise.

## The order the stages are written in is not the order they run in

The obvious way to list the caller is: measure the panels, write
`mono_bar_geometry.csv`, resolve the identities. That order produces a
perfectly valid file in which `Domain_Identity_SHA256` and
`Auto_Identity_SHA256` are blank and every `Auto_Identity_Status` says
`NOT_CALIBRATED` - for a batch that resolved the identities in memory a moment
later and wrote them nowhere. The durable artifact would say the figure was
never asked.

`canonical_artifact_rows` is that constraint as a function rather than a flag
somebody has to remember. It refuses a row that has not been through
`fill_identities_by_figure`, so the file can only be written after the figure
has answered:

    measure every BAR_MONO panel        (anonymous, stamped here)
    collect the rows by Figure_ID
    fill_identities_by_figure           (verdict + attestation here)
    canonical_artifact_rows             (written once, here)
    read it back and verify
    identity_resolution.csv joined DOWNSTREAM, never back into this file

A diagnostic dump of pre-identity rows is still a legitimate thing to write, so
`artifact_rows` will still do it. A batch does not use `artifact_rows`.

**Half an auto identity is not an auto identity.** The attestation check treated
"no `auto_identity_sha256`" as "not resolved yet", which is only true if none of
the other identity fields are there either. A caller that deletes the answer and
leaves `identity_source` and `figure_identity_sha256` behind - or takes the
answer off the figure's verdict without attesting the row - writes a file that
cannot say whether auto resolution reached that row. There are exactly two
states now, `PRE_IDENTITY` and `ATTESTED`, and everything between them is
`AUTO_IDENTITY_PARTIAL`.

**A migrated row may not carry an attestation of a hash it has lost.** With
`allow_unstamped=True` the writer recomputes `Geometry_Row_SHA256` and fills the
column with it, while an attestation made earlier names the hash the row used to
have - empty, here. The writer would pass the row and a reader recomputing the
attestation from the eighteen columns would reject the file. So an unstamped row
carrying an attestation is refused outright: re-stamp the measurement and
resolve its figure again.

Note what `Domain_Identity_SHA256` does and does not prove today. It binds a
row's identity to the verdict the figure was answered with, so an answer cannot
be carried over from a figure that reached it differently. It does not prove the
verdict itself - that needs the durable reader to recompute `fill_identity` from
the rows in the file and get the same hash, which is part of the read-back
contract the caller integration owes.

## The file can be read back

A writer nobody can read back is a writer nobody can check, and the eighteen
denormalized columns could not carry the record on their own. A CSV holds text:
`cap_px_image` is written `1189` whether the record held the integer 1189 or the
float 1189.0, and the canonical JSON of those two is not the same string.
Measured on publication 127 that is exactly what happened, on the first row of
the file - a reader recomputed a different hash for a file it had just been
handed.

The alternative was a rule per field for what a blank cell means (key absent, or
key present and None) and what type to restore, with row types to
regression-test each rule against. Instead there is a nineteenth column,
`Anonymous_Record_JSON`, holding the measurement as the one text the hash is
taken over: `Geometry_Row_SHA256` is the SHA-256 of exactly those bytes.
Restoring is parsing one string. `Diagnostics_JSON` stays as the readable half
for a person or for SQL, and a scenario checks it is a strict subset of the
authoritative column rather than trusting that it is.

`read_artifact_row` verifies as it restores: the columns are the declared
columns in order, the record parses, its hash is the row's hash, and
re-projecting the restored record through `artifact_row` reproduces every other
column. That last check is what stops the convenience columns drifting - `Mean`
is there for a person, and a file whose `Mean` disagrees with the record its
hash covers says two things.

`verify_artifact` adds what only the whole file says: no two rows claim the same
`(Panel_ID, Group_ID, Geometry_Slot)`; every row of one `Figure_ID` carries the
same `Domain_Identity_SHA256`; and `fill_identity`, re-run on the restored
records, reproduces it. That last step is what turns the verdict hash from a
value that exists into a value that is TRUE - until it is recomputed from the
rows in the file, it only says the writer wrote something down.

The scenario's fixture holds every row type a real file does: a bar with a cap
and one without, BAR_TOO_SMALL_TO_SAMPLE, a slot-level refusal
(BAR_TOO_NARROW), a group-level refusal (NO_SEED_SUPPORT) and
STROKE_SCALE_UNRESOLVED. Reverting to a rebuild from the denormalized columns
fails on the first row with GEOMETRY_ROW_HASH_MISMATCH.

Two rows attested under DIFFERENT verdicts - which is what merging two runs of
one figure into a file produces - is a separate case from editing a hash in
place, because the row-level attestation catches the edit first. The scenario
builds it honestly, by resolving a subset of the figure and splicing one of its
rows back in.

## A picture per row

The panel overlay answers "did it put the marks in the right places" for a
PANEL. The geometry artifact is finer than that - one row per bar - and a
reviewer checking eighteen rows of `mono_bar_geometry.csv` against a 600 DPI
page render is doing arithmetic on page coordinates by hand.

`review_overlay.write_row_crops` writes a folder: one PNG per geometry row, this
bar cut from the page it was measured on, with the four numbers the row claims
drawn on it - the baseline, the bar top, the error-bar cap and the footprint's
own columns - and an `index.html` contact sheet. `measure_mono_bars --crops DIR`
produces it for any panel the package can reach. It takes `(image_path,
record)` pairs rather than one image and a list, because a figure is several
panels and possibly several pages - the first version rewrote `index.html` per
call, so a folder of eighteen pictures got a contact sheet listing the last
six, and a sheet that under-reports the folder it sits in is worse than no
sheet.

Same contract as the overlay: a crop is a review aid, it is never read back,
nothing is derived from it, and its absence cannot change a value. What it adds
is BINDING. The filename and the caption both carry `Geometry_Row_SHA256`, so a
picture cannot be quietly matched to the wrong row and a crop left over from an
earlier run cannot pass for this one - two runs that measured the same bar
differently write two files rather than one silently replacing the other.

**The record had to learn where it was.** `footprint` is window-relative,
because every array in `mono_bar_geometry` is, and `edge_px_image` is a page row
with no page COLUMN beside it - so a row said the bar top was at page row 296
without saying which columns, and no crop could be drawn from the record at all.
Every row now carries `panel_box` and `zero_px_image`, and every row with a
footprint carries `footprint_px_image`. That is not only for the picture: a row
that cannot locate itself needs the spec to be found again, and the spec is not
in the artifact.

Drawing from the record ALONE is the point. A crop that also took the spec could
be drawn from a different panel's geometry and look perfectly reasonable.

**And the panel, with the axis in frame.** A crop of one bar shows that the
reader found the bar. It cannot show that the reader knows what the bar is
WORTH - that is the axis, and the axis is printed OUTSIDE the panel box. A panel
read at the wrong scale has every bar wrong together and every bar still looks
like a bar, so the failure is invisible in every per-bar crop in the folder.

`draw_panel_geometry` crops wide enough to include the tick labels and then
draws, from the calibration each row now carries, a line at every round value
across the panel, labelled. If the line the calibration calls 30 does not sit on
the printed 30, the reviewer sees it immediately. On publication 127's slow
panel the four lines land exactly on the printed 0, 10, 20 and 30. Every bar's
measured top and cap are drawn too, labelled with the value the row carries, so
"the bar the reader called 5.31" can be read off the printed axis by eye.

That needed one more field. The record carried the value and not the
arithmetic - nobody reading the artifact could check that `Mean` is what
`Edge_Px_Image` MEANS, and nobody drawing the panel could show where the
calibration thinks the ticks are. Every row now carries `calibration`: slope,
intercept, scale and the fit's own max residual.

The scenario does not restate the calibration back to itself. The fixture draws
its bars at a known pixels-per-unit, so it asserts that the line the calibration
calls 50 lands on the row the FIXTURE drew 50 at, and that a panel whose rows
carry no calibration draws no lines at all.

A refusal gets a picture too, and gets the right one: a row that never found a
bar carries `zero_px_image` like every other row, and cropping to the baseline
alone gives a 48 px strip of the axis. `STROKE_SCALE_UNRESOLVED` and
`NO_SEED_SUPPORT` are shown their whole panel instead.

## Two scenarios that could not fail

One of them was mine, written in the round above:

    check("and the caption says how many such lines it drew",
          "axis lines from the calibration" in
          open(panel_png, "rb").read().decode("latin-1", "ignore") or True)

The `or True` makes it pass whatever the picture contains. Worse, the condition
it was disabling could never have worked: text drawn into a PNG is PIXELS, and
the string is not in the file - so the check would have failed on a CORRECT
picture, which is presumably why it acquired an `or True`. A scenario that
reports "ok" beside a sentence and asserts nothing is worse than no scenario,
because it is counted.

The second was `all(fid in str(v.get("prototypes", v)) or True for ...)` in the
figure-isolation check, which reduced to the clause beside it.

Both are gone, and `test_reproducibility` now PARSES every scenario file and
looks for a short-circuiting truth literal inside the condition of a `check(...)`
call or an `assert`. Parsed rather than grepped, because `condition or\n True`
and `condition or (True)` are the same mistake on two lines; scoped to the
condition, because `x or "fallback"` in a detail string is the ordinary Python
idiom for a default and flagging it would make the check something people route
around.

**What the picture drew now comes back as data.** `draw_panel_geometry` returns
a dict instead of a path and writes it beside the PNG as JSON:

    {"path": ..., "axis_ticks": [{"value": 0.0, "pixel": 1234.0}, ...],
     "axis_line_count": 4, "crop_box": [...], "crop_source": "DECLARED",
     "plot_left_in_crop": 88, "calibration": {...}}

`index.html` prints the same values in words. Nothing greps an image.

## The factor of ten, and the fixture that can catch it

The severe calibration failure is not a tick pixel a few rows out - that is 1.7%
on publication 127 at ten pixels, below the digitization noise. It is a tick
VALUE misread: a printed 30 typed as 3 makes every bar in the panel exactly ten
times too small, all together, and every bar still looks like a bar. No
arithmetic catches it: the mapping is self-consistent, and a third tick scales
with the other two so `max_residual` stays at zero. The only thing that catches
it is the number the calibration claims sitting beside the number the FIGURE
prints.

Which means the fixture has to print numbers, and until now none of them did -
so a scenario could only confirm the orange line was in the right PLACE, and a
line in the right place is exactly what a factor-of-ten error still produces.
`print_axis_labels` draws `0`, `50`, `100` beside the axis of a synthetic panel,
and the scenario reads it twice: once with the top tick declared 100 and once
with it declared 10. The first picture offers 0, 50, 100 back; the second offers
0, 5, 10 and never 100.

For that comparison to be possible the printed numbers have to survive. Nothing
is drawn left of the plot area now - the axis lines and the baseline start at
`plot_left_in_crop` and the value labels are written on the RIGHT - and the
scenario asserts the strip left of the plot area is reproduced pixel for pixel
from the source page. A separate scenario counts orange pixels in the band above
each line, so removing the labels while keeping the lines fails.

**The overlay draws the points somebody TYPED.** The orange lines were round
values invented by a nice-step rule and placed by the inverse calibration - so
a panel calibrated at 2.5 and 7.5 got lines at 3, 4, 5, 6, 7, and neither number
anybody had entered appeared anywhere. On a log axis it is worse: a linear step
over an axis printed 1, 10, 100, 1000 draws 200, 400, 600, 800, beside nothing.

The declared points are now the overlay - solid, three pixels, labelled - and
the round values are pale dashed guides that skip any value a declared point
already covers. The metadata separates them as
`declared_calibration_points` and `generated_reference_ticks`, and `index.html`
names the typed ones in bold. Guides on a LOG axis are 1, 2 and 5 times each
power of ten, and the footer says `px/log-unit` there rather than `px/unit`,
because the reciprocal of a log slope is a decade width in disguise.

That matters because the typed points are the whole of the calibration and the
only pair a reviewer can compare with the page. A printed 30 typed as 3 is a
wrong number sitting exactly there.

**And the calibration has to fit the points it says it came from.**
`check_calibration` used `slope` and `intercept` and nothing else, so a record
could carry points nobody fitted, an `n_points` counting something else and a
`max_residual` invented from nothing, and every value in the file would still
follow from the mapping. `validate_calibration` re-fits the points and refuses
on a slope, intercept or residual that does not come out; it also refuses a
scale that is not LINEAR or LOG, fewer than two points, one distinct pixel, a
non-finite number, and a non-positive value on a LOG axis. A canonical geometry
file may not contain a row without a calibration at all.

**The row's arithmetic is checked too.** `verify_artifact` now recomputes
`Mean` from the row's own `calibration` and `Edge_Px_Image`, and `Dispersion`
from `Cap_Px_Image`, refusing on disagreement; and every row of one `Panel_ID`
must carry the same `calibration`, `panel_box`, `zero_px_image` and
`review_crop_box`, because
`draw_panel_geometry` takes the axis and the crop off the first row it is
handed and draws every other row's bar against them - and it now refuses to
draw a panel whose rows disagree, because a diagnostic call does not go through
the reader. This does not check the calibration is RIGHT -
a mapping read off the wrong gridline is perfectly self-consistent. It catches
the other half: a value that does not follow from the mapping the row declares.

**The calibration keeps its points.** `AxisCalibration` stores the
`(value, pixel)` pairs it was fitted from, and the record carries them with
`n_points`. A slope and an intercept reproduce the mapping and not the two
numbers somebody read off the printed axis, so nothing could have compared a
declared tick pixel with a tick mark found on the page, or said which of four
points was the one that did not fit.

**The crop is declared where the caller declares it.** `geometry_rows` takes
`review_crop_box` and records it, and the picture reports `crop_source` as
`DECLARED` or `ESTIMATED`. The fraction-of-the-panel fallback is a guess: an
axis printed far from the plot box, a panel box drawn tightly around the bars,
a long tick label or a unit printed beside the numbers, and the picture crops
away the very thing it is for. `Axis_X_Region` and `Axis_Y_Region` are already
columns of `panel_manifest`; wiring them into this argument belongs with the
caller.

## An approval that says what was looked at

Two of the three things the BAR_MONO geometry review will need are contracts
the review layer did not have, and both are reachable today through the modes
that already exist - so they went in first, rather than being declared beside a
mode nothing can reach.

**A mode may require more than one artifact.** `REVIEW_MODES` mapped a mode to
ONE `panel_artifacts.csv` type. That is a limit of the table and not of review:
a mode that needs the numbers, the pictures and the index tying them together
could declare one of the three and be approved without the other two. It maps
to a tuple now and the finalizer refuses on any of them missing, naming which.

**An approval has to say what was checked.** `Decision=APPROVED` says a person
agreed. It does not say what they opened, and the whole reason a panel is
queued with an artifact is that somebody opens it - a column of APPROVED is
indistinguishable from a review. `value_review.csv` carries `Marks_Checked`,
`RB.REVIEW_CONFIRMATIONS` says which confirmations a mode requires, and the
finalizer refuses an approval that does not carry them
(`REVIEW_CONFIRMATION_MISSING`). Both shipped modes offer a picture of the
marks and nothing else, so both ask the one question that picture can answer;
the axis and calibration confirmations arrive with the mode that shows an axis,
because a confirmation field nobody can act on is worse than none.
`MIGRATION.md` has the column change.

## Four artifacts or it is not a review

`run_batch.write_geometry_review` writes the BAR_MONO geometry bundle once per
run and returns it per panel, ready for `panel_artifacts.csv`:

    MONO_BAR_GEOMETRY      the numbers, canonical and hash-verifiable
    GEOMETRY_REVIEW_INDEX  the contact sheet tying rows to pictures
    CALIBRATION_PANEL      the panel with the axis in frame
    CALIBRATION_PANEL_META what that picture drew, as data

All four, per panel. The CSV and the index are written once for the run and
registered against every panel they cover, because an approval is per panel and
"the file existed somewhere in the run" is not the claim being made.

It **raises** rather than returning half a review. An overlay is a review AID -
a panel with values and no picture is still reviewable through its WPD project,
which is why `draw_panel_overlay` never raises - and these are the review
itself. A panel missing one of them cannot be approved, so the run has to say
so rather than queue it and let the finalizer discover it after somebody has
typed APPROVED.

It also reads the file back before anyone is asked to approve it:
`verify_artifact` recomputes every row hash, the figure verdict and the
calibration arithmetic, so a geometry file that does not verify never reaches a
queue. And it goes through `canonical_artifact_rows`, so a bundle written
before `fill_identities_by_figure` has answered is refused rather than shipped
with `NOT_CALIBRATED` on every row.

**Every row crop is in the ledger too.** The four types above are fixed; the
row pictures are one per geometry row, under `GEOMETRY_ROW_CROP`. They have to
be registered because the finalizer re-hashes only what
`panel_artifacts.csv` names - leave them out and a row crop can be swapped for
a picture of a different bar while the index still links to it and the approval
still verifies. A panel whose rows did not all get a picture is refused, and so
is any drawing failure the bundle itself produced.

Only the failures the bundle produced. `OVERLAY._FAILURES` is the run's overlay
log, and resetting it inside the helper erases every panel overlay failure that
happened before - a helper that quietly depends on being called first, and a run
that reports a clean drawing pass it did not have.

**The bundle is on the cleanup list.** `mono_bar_geometry.csv` and
`geometry-review/` are removed before a run starts, like every other output. A
previous run's panel picture left in place passes the writer's existence check,
so an approval could be given against a picture of a different measurement.

**And `review_crop_box` reaches the successor reader.** It is deliberately not
a `READER_OPTIONS` entry - it is caller-derived context, the plot area unioned
with the manifest's `Axis_X_Region` and `Axis_Y_Region`, rather than a setting
somebody tunes - but it has to come through the shared entry point all the
same, or a caller wanting a declared review crop has to bypass it and call
`geometry_rows` directly, which is most of the reason the shared entry point
exists.

## The two-pass runner

`run_batch` measures every BAR_MONO panel of the batch BEFORE the panel loop,
groups the rows by `Figure_ID`, and lets the figure name the fills. The loop
then reads its values out of the answer. `reader_functions()["BAR_MONO"]` is
`read_monochrome_bar_geometry`; `SUCCESSOR_READERS` is empty and kept, because
the next reader built before it can be wired goes there and gets its option
contract checked several commits before the switchover instead of at it.

`_geometry_marks` turns resolved rows into the shape the loop already reads.
The series comes from matching `resolved_fill_pattern` - what the FIGURE said -
against the `Bar_Fill_Pattern` each series declares; a bar the figure could not
name, or one whose fill two series claim, yields no mark. Its cell goes missing
and is queued, which is the point: `identity_resolution.csv` is where a person
names it.

BAR_MONO panels are queued as `Review_Mode=BAR_MONO_GEOMETRY`, requiring all
five artifact types and three confirmations - `Marks_Checked`,
`Axis_Labels_Checked`, `Calibration_Checked`. This mode puts the axis in front
of the reviewer, so it asks about the axis: a printed 30 typed as 3 makes every
bar in the panel ten times too small together, no arithmetic catches it, and
the panel picture is the only place it shows.

**What it cost, in the open.** The 397 pilot read 48 values and now reads 36.
Three panels of Figure 4 - `P4_SV_WOMEN`, `P4_CO_MEN`, `P4_CO_WOMEN` - refuse
with `STROKE_SCALE_UNRESOLVED`: the two-pass reader measures the figure's own
line weight off the rule at the calibrated baseline, every threshold it uses is
a multiple of that number, and a panel whose stroke it cannot measure has no
scale for anything. The old reader needed no stroke and read them.

Nothing poolable was lost - all 48 were QC_FAILED anyway, because publication
397 does not say whether its error bars are SD or SEM - and the pin in
`test_compile_plan` records the three panel names so the number cannot drift
back without somebody noticing. Why the stroke fails on exactly those three,
whose declarations look like the ones that succeed, is worth a round of its own.

And a stipple is no longer a fill the pipeline refuses. That scenario asserted
`NO_READER_AVAILABLE` and was right to: the old reader classified fills by
absolute density and STIPPLED had no band. `UNIMPLEMENTED_FILL_PATTERNS` still
names it, and still should - it is that reader's limitation and that reader
still has it. What changed is which reader BAR_MONO goes to.

The bundle is written into the run directory rather than staging, like `raw/`,
`projects/` and `review/`. Written into staging, the ledger records
`.staging/mono_bar_geometry.csv` and the promotion moves the file out from
under that path.

**Four things the switchover left half-done**, all closed in the commit after
it.

The declared axis region now reaches the measurement. `Axis_X_Region` and
`Axis_Y_Region` exist so a person re-checking a calibration knows where to
look, which is the same rectangle the panel picture must include - and the
pre-pass was calling the reader without them, so every production panel got an
ESTIMATED crop while `Axis_Labels_Checked` was being made mandatory. A region
that does not parse refuses the panel: a field filled in and not used is worse
than one left blank.

`DEMO_OUTPUT_REFUSED` clears the geometry bundle. It removed three directories
by name, and the bundle is written at its final path like `raw/` and
`projects/` - so a refusal returned zero accepted values and left
`mono_bar_geometry.csv`, with every mean, dispersion and auto identity in it,
on disk. It calls `clear_outputs` now: the whole contract, not a list kept
beside it.

`GEOMETRY_REVIEW_FAILED` is a declared status with a CLI branch. It was neither:
it was absent from `RUN_STATUSES`, and its summary has no `states`,
`qc_problems` or `manual_queue` because the run stopped before there were any -
so the status reached a person as a `KeyError` traceback. And
`write_geometry_review` normalises what it can raise: `canonical_artifact_rows`
and `verify_artifact` raise `ValueError`, which a runner catching only
`GeometryReviewError` let straight past.

A pre-pass refusal keeps the panel's declaration and its reason. Returned from
the loop, the outcome carried `Cells_Declared=0` and no missing cells - the
same understatement the panel loop's own early returns were fixed for - so it
is applied inside `run_panel`, after the declaration is known. And a panel
whose geometry rows ALL carry an error is `PANEL_GEOMETRY_UNRESOLVED` with the
codes on it, not `MANUAL_POINT_READ` with "the reader resolved no marks": that
is what makes publication 397's three `STROKE_SCALE_UNRESOLVED` panels legible
from the run manifest instead of only from the geometry file.

All four are held by a batch that reads a monochrome bar panel *through the
manifests*, which the suite did not have: every earlier BAR_MONO scenario
either called the reader directly or pointed it at a raster with no bars in it,
so the runner path - pre-pass, review bundle, refusal branches, cleanup - was
only ever exercised on a panel that returned nothing, and none of these four
defects can be seen on such a panel. `P_MONO` reads twelve cells off the
fixture (worst error 0.6 units on a 100-unit axis), and the four fixes are
pinned by what happens to those twelve: the picture's crop rectangle is the
declared one rather than a fraction of the plot box, a DEMO refusal leaves only
`run_stamp.json`, a bundle that cannot be drawn exits 5 with the status on the
stamp, and an unparseable `Axis_Y_Region` refuses the panel while still
reporting `Cells_Declared=12` and queueing twelve cells.

### A series the reader could not name (v7.29-7.35)

Publication 127 prints two bars fifteen pixels tall. They have a mean and an SE,
and once the outline is taken off there is no interior left to classify - so a
BAR_MONO series, which is identified BY ITS FILL, has a geometry with no
identity. Naming it from the pixels would mean "first slot, therefore OPEN":
identity by position, the one inference this package refuses.

`identity_resolution.csv` is where a person names it, and it is now wired up.

**A complaint about the fill is not a complaint about the number.**
`BAR_TOO_SMALL_TO_SAMPLE` was filed in `error` with every other code, so the row
was dropped by everything downstream and 127's two values were lost for a reason
that was never about the values - the mean comes from the top edge and the
dispersion from the cap, measured exactly as on any other bar.
`FILL_ONLY_ERRORS` and `measurement_usable()` name that distinction, and only
codes in that tuple can be rescued by an identity.

**A resolution supplies an identity; it never overrules one.** Three things can
only be checked once the panel is measured, and each refuses the WHOLE panel
rather than the cell - a person naming a bar this measurement does not have was
reading a different measurement, and their other rows for it are then equally
unsafe:

| refusal | what it catches |
|---|---|
| `IDENTITY_RESOLUTION_NO_SUCH_ROW` | a bar the reader never found |
| `IDENTITY_RESOLUTION_OVERRIDES_MEASUREMENT` | a bar the figure named itself |
| `IDENTITY_RESOLUTION_STALE` | written against a different measurement |

The last one is why the schema gained `Geometry_Row_SHA256`. Without it
(Panel_ID, Group_ID, Geometry_Slot) is a POSITION: re-run after a threshold
change or a re-scan and the resolution silently names whatever bar now sits in
slot 2, which is identity by position one level up. Everything checkable on
paper - evidence type, the series and its declared fill, the evidence artifact's
hash and confinement to the corpus, a registered HUMAN reviewer, duplicates -
is a manifest problem, so the batch does not run at all.

**The provenance reaches the grain that gets pooled.** Six columns travel from
the mark to `figure_values_*` via `IDENTITY_CARRIED`: `Geometry_Row_SHA256`,
`Auto_Fill_Pattern`, `Resolved_Fill_Pattern`, `Identity_Source`,
`Identity_Evidence_Type`, `Resolution_ID`. Listed apart from `MARK_CARRIED`
because they are not universal - only a monochrome bar has them.
`Auto_Fill_Pattern` stays BLANK for a human-named bar: filling it in is the
audit trail saying the machine measured what a person read off a legend, and the
gate refuses a row that does both (`IDENTITY_OVERRODE_MEASUREMENT`), as it
refuses `Identity_Source`/`Identity_Evidence_Type` pairs that disagree. The
geometry artifact is untouched by any of it - it is what the FIGURE said.

**The review contract is per panel.** `BAR_MONO_GEOMETRY_RESOLVED` is the
resolved mode: the five geometry artifacts plus `IDENTITY_RESOLUTION`, and a
fourth confirmation, `Identity_Checked`. A separate mode rather than a sixth
required artifact everywhere, because most BAR_MONO panels have no human-named
cell and a mode that demanded the file from all of them would make it
mandatory - which is how a confirmation column becomes one everybody types
CONFIRMED into.

**A monochrome value must CARRY its provenance, not merely agree with itself.**
The gate's identity block only fires when one of the columns is filled - right
for a file that cannot know what drew the panel, since a line panel's rows say
nothing about fills, and wrong as the only defence. Delete the six columns and
the mean and the SE are still fine, the gate says nothing, and the value is
reviewable and poolable with no way to ask which bar it came from.
`identity_provenance_problems(values, mark_by_panel)` is the mark-aware half: it
requires a 64-hex `Geometry_Row_SHA256`, a `Resolved_Fill_Pattern` this reader
distinguishes, and a source/evidence/resolution combination that holds together,
for every value whose panel is BAR_MONO. It takes the two files a run writes, so
it can be re-run from `figure_values_raw.csv` and `run_manifest.csv`, and its
problems join the gate's - same `values:<row>` scope, same blame, same
`QC_FAILED`. `IDENTITY_FILL_MISMATCH` is in there too: for an automatic identity
`Auto_Fill_Pattern` and `Resolved_Fill_Pattern` are one fact, and nothing else in
the chain compared them.

**The evidence BYTES travel with the run.** Hashing the legend crop at
validation time protects the hash STRING in the manifest and nothing else: edit
or delete the file afterwards and `identity__<Panel_ID>.csv`, the ledger and
`Review_Subject_SHA256` are all unchanged, so `Identity_Checked=CONFIRMED` could
be given against evidence that no longer exists - and a run directory handed to
somebody else did not contain the picture its own review mode says to open. So
`LEGEND_DECLARED` and `TEXT_DECLARED` evidence is byte-copied into
`geometry-review/evidence__<Resolution_ID>__<basename>`, re-hashed after the
copy, and registered as `IDENTITY_EVIDENCE` - which the finalizer re-hashes with
every other ledger artifact, so a later edit is `RUN_ARTIFACT_MODIFIED`. A copy
that cannot be made or does not match refuses the whole review bundle
(`GEOMETRY_REVIEW_FAILED`): a review whose evidence cannot be reproduced is not a
review. `REVIEWER_INSPECTION` has no file to copy, which is what makes it the
weakest of the three, and carries a mandatory Note instead.

Three smaller ones closed with them. An auto identity and a human one naming the
same series in one group breaks no rule alone - the human's target really was
unnamed - and put two values in one cell, surfacing later as
`FACTORIAL_CELL_DUPLICATE`: blaming the grid for what the identities did. It is
now `IDENTITY_RESOLUTION_CONFLICTS_WITH_MEASUREMENT`, checked with the auto and
human answers together. A `Reviewed_At` in the future is refused, as the registry
and the final approval already do. And `Evidence_Artifact` without its hash, or
the hash without the path, is `IDENTITY_EVIDENCE_HALF_DECLARED` - a path with no
hash is an unverifiable file, a hash with no path is a claim about nothing.

**The panel binding decides which rules apply, so it is checked first.** A value
row whose `Run_Panel_ID` names a colour panel skips the identity rules entirely
and is then selected by the finalizer under THAT panel's approval - reviewed as
somebody else's panel and pooled. Every value, monochrome or not, must name a
declared panel whose `Unit_ID` is its own: `IDENTITY_PANEL_BINDING_MISSING`,
`_UNKNOWN`, `_CONTRADICTS_UNIT`.

**`Geometry_Row_SHA256` is a foreign key, not a format.** Sixty-four hex
characters establish that a value carries something hash-shaped; a fabricated
digest and another bar's real one pass a format check exactly as well. With the
geometry index in hand - `{(Panel_ID, hash): row}`, built from records or from
`mono_bar_geometry.csv` - the mean, the dispersion and the measured fill are
compared against the row the value names, and two values may not claim one bar
(`IDENTITY_GEOMETRY_ROW_UNKNOWN` / `_MISMATCH` / `_REUSED`). This is what makes
"this mean came out of that measurement" a checked statement rather than a
convention.

**The finalizer re-derives the evidence requirement.** A review mode's artifact
tuple cannot express "and the evidence for every file-backed resolution",
because a panel resolved only by `REVIEWER_INSPECTION` has no evidence file - so
a static requirement would refuse a correct panel, and its absence let any run
whose producer had not copied the evidence in be finalized, including every run
made before it started doing so. `identity_evidence_missing` reads the
`IDENTITY_RESOLUTION` rows, and for each `LEGEND_DECLARED`/`TEXT_DECLARED` row
requires an `IDENTITY_EVIDENCE` artifact whose hash is the one the resolution
declared. `panel_artifacts.csv` gained `Artifact_Reference` for the join -
matching on basename would work until two resolutions cite crops with the same
name. A panel that fails is withheld from approval (`REVIEW_EVIDENCE_MISSING`);
the run is not condemned for it.

**One contract for `REVIEWER_INSPECTION`.** Validation hashed an
`Evidence_Artifact` given on such a row and the writer, which copies only
`FILE_EVIDENCE_TYPES`, left it out of the run - checked once and then not
shipped, while the documentation said this type has no file at all. A row with a
file to point at is `LEGEND_DECLARED` or `TEXT_DECLARED`, and saying otherwise is
`IDENTITY_EVIDENCE_NOT_A_FILE`.

**Path confinement is not an option.** The validator's rule sits behind
`check_files`; skipping a content hash when file checking is off is a defensible
choice, letting a path escape the corpus is not. The writer - the code that
actually opens the file - re-derives it, so `--no-file-check` cannot copy an
arbitrary absolute path into the run and register it as evidence.

**A value moved between panels OF THE SAME UNIT.** Several panels may build one
unit - the package says so in as many words - so a `Unit_ID` check cannot see a
monochrome value re-stamped onto a line panel of that unit, and the panel it now
names skips every identity rule. What gives it away is the provenance columns
themselves: only a monochrome bar has them, so their presence on a row bound to
any other mark type is `IDENTITY_PANEL_BINDING_CONTRADICTS_MARK_TYPE`.
`Source_Panel_ID` is checked against the panel's declaration at the same time.

**The cell, not just the measurement.** Everything above ties a value to a bar;
none of it says the value is filed under the right heading. Two bars of one
panel, each citing its own row with its own mean and its own fill, and their
`Cell_Key`s exchanged: every other check passes, the grid is complete because
both timepoints are present, and the two numbers are swapped. This is the
failure with no arithmetic signature at all. So `geometry_index` keeps
`Group_ID`, and the check recomputes the cell a value must be filed under - the
position level from the group the bar was measured in, the series level from the
identity (for a human identity, from the series the RESOLUTION names) -
`IDENTITY_GEOMETRY_CELL_MISMATCH`. A caller who supplies no mapping gets
`IDENTITY_CELL_MAP_MISSING` rather than a pass.

**`Resolution_ID` as a foreign key.** Checked only for being non-blank it is a
label: exchange two of a panel's resolutions on their values and the numbers, the
hash and the fill all still agree while the accepted file cites the wrong
evidence, the wrong reviewer and the wrong reading. Both the runner and the
finalizer now look the row up and compare `Geometry_Row_SHA256`,
`Resolved_Fill_Pattern` and `Evidence_Type`
(`IDENTITY_RESOLUTION_FOREIGN_KEY_MISMATCH`,
`REVIEW_IDENTITY_RESOLUTION_UNKNOWN` / `_MISMATCH`). The finalizer does it
because nothing pins a minimum pipeline version: a run made by an older producer
arrives with a complete-looking ledger.

**The index comes from the file, not from memory.** `geometry_index_from_run`
reads `mono_bar_geometry.csv` - written, read back and verified - rather than the
records still in memory. Nothing today edits a record after the artifact is
written; if anything ever does, an index built from memory compares the edited
numbers with themselves and passes while the durable file says something else.

**One reference, one file.** The finalizer keyed evidence by
`Artifact_Reference` with an assignment, so a second entry for one
`Resolution_ID` replaced the first and which file a panel was approved against
depended on ledger order. Duplicates are refused instead.

**The finalizer re-runs the runner's own contract.** A run this module did not
produce is the case it exists for, and nothing pins a minimum pipeline version -
so a run made before a check existed arrives looking complete. In particular a
v7.29-v7.31 run carries per-bar hashes and means that all agree while its
`Cell_Key`s could have been exchanged, which is the failure with no arithmetic
signature. `value_contract_failures` calls the SAME
`identity_provenance_problems` on the verified files (the manifests are hashed
into the run stamp, `mono_bar_geometry.csv` is one of the run's own outputs), and
withholds the panels that fail. One function, two callers, one contract.

**The fail-open corners, closed.** A `Source_Panel_ID` deleted from a value
passed because the comparison required both sides to be non-blank - and that
column is the physical panel in the publisher's figure, so it has its own code
now (`IDENTITY_PANEL_BINDING_CONTRADICTS_SOURCE`). A missing geometry index
disabled the foreign key and the cell check silently, where a missing cell map
already refused: both refuse now (`IDENTITY_GEOMETRY_INDEX_MISSING`). A cell map
present but not covering the row was skipped rather than refused
(`IDENTITY_CELL_MAP_INCOMPLETE`). And in the finalizer, a panel with
human-named values and no `IDENTITY_RESOLUTION` artifact at all fell out of the
loop that was driven from the ledger - it is driven from the VALUES now - while
the resolution rows themselves were read with a dict comprehension that let a
repeated `Resolution_ID` win by file order and a blank key field act as a
wildcard.

**The manifests the finalizer re-derives from are verified first.**
`Manifest_SHA256` has been in the run stamp since the beginning and this module
never read it - defensible while the finalizer only read the reviewer registry,
and not defensible once it recomputes the value contract from the panel, series
and position manifests. Exchange two `Factor_Level`s in
`position_manifest.csv` after the run and the cell check is done against a
mapping nobody approved: it either refuses a correct run or blesses a wrong one.
`verify_manifest_inputs` compares every frame, including the optional
`identity_resolution.csv` - absent, it hashes as the empty frame
`load_manifests` substitutes, so adding or removing it after the run is a
changed set rather than a silent extra.

**A deleted `Unit_ID` is refused, like a deleted `Source_Panel_ID`.** The
comparison required both sides to be non-blank, and the finalizer selects values
by `Run_Panel_ID` alone - so a unit-less row under an approved panel reached the
accepted file. A panel that declares no unit at all is
`IDENTITY_PANEL_DECLARATION_INCOMPLETE`.

**One resolution parser, not two.** The finalizer checked six fields of a
resolution row where the manifest validator checks a dozen, so a row with a
blank `Evidence_Artifact_SHA256` (which makes the ledger comparison a no-op), no
`Reviewer_ID`, an unregistered reviewer, a future date or a `Geometry_Slot` of
"left one" passed the durable side and failed the runner. It calls
`check_identity_resolution` - the runner's own checker - on the run's copy of
the rows, with `check_files=False` because the evidence bytes are checked
against the ledger copy instead.

**One identifier, one decision, one copy.** `check_identity_resolution` keeps
`Resolution_ID` unique across the frame it is handed, so calling it once per
panel made the identifier unique per panel and global nowhere - two panels could
both hold IR001, and the evidence filenames are built from that identifier. It
is called once over every panel's copy now. And the copy is compared with the
manifest: `identity_resolution.csv` is verified against the run stamp and
`identity__<Panel_ID>.csv` against the ledger, and until now nothing compared
the two, so the run copy could name a different reviewer, evidence file or date,
be internally valid, hash correctly, and leave `Resolution_ID` pointing at two
different rows (`IDENTITY_RESOLUTION_COPY_MISMATCH`).

**The registry's own problems are not swallowed.** The reviewer index was built
with a callback that discarded every problem, and `check_reviewer_registry`
indexes a row before it validates it - so an entry with a malformed ORCID or a
mismatched record type still counted as "a registered HUMAN" for a resolution.

**The verified frames travel.** `verify_manifest_inputs` returns them and
`verify_run_outputs` hands them out; the checks that re-derive the contract read
those frames instead of opening the same files again, and a check handed no
frames refuses the run rather than proceeding. A blank `Source_Panel_ID` in the
panel DECLARATION is `IDENTITY_PANEL_DECLARATION_INCOMPLETE`, as `Unit_ID`
already was.

### The plan is a contract too (v7.36)

Publication 127's pilot lost an hour to `axis_x_region`. The compiler reads
`x_region`; nothing said so; the manifest's `Axis_X_Region` came out blank and
every panel picture was cropped by guesswork, cutting away the axis labels the
reviewer is asked to check. **A field somebody filled in and nothing read is as
wrong as a field read wrongly**, and this is the layer where a hundred
publications get authored. `PLAN_KEYS` lists what each plan object may carry,
an unknown key is `PLAN_UNKNOWN_KEY` with a did-you-mean, and
`axis_x_region`/`axis_y_region` are now canonical with the old spellings as
aliases (`PLAN_ALIAS_CONFLICT` if both appear and disagree).

**`Identity_Domain_ID` — which panels share a printed legend.** `Figure_ID` was
doing this job by accident: it is a provenance view, and
`fill_identities_by_figure` groups by it, so two meanings sat in one field. On
127 the three sub-panels of Figure 4 share one legend; giving each its own view
left the middle panel with one complete group where prototypes need two, and a
bar whose fill WAS measured came out unnamed. The reverse is worse - two panels
with different legends under one view would calibrate each other's fills. The
domain is declared (defaulting to the view, so old plans behave as before),
required for BAR_MONO, and validated: one raster per domain
(`IDENTITY_DOMAIN_SPANS_RASTERS`) and one meaning per fill inside it
(`IDENTITY_DOMAIN_FILL_CONFLICT`). The scenario that makes it real splits one
raster into two panels with two views and one legend: the half that cannot
calibrate alone reads 5 of 6 cells with the domain and 3 without.

**Where this stands.** A run made by this pipeline has a closed identity chain:
measurement, panel binding, geometry foreign key, cell, identity source,
resolution, evidence, review, approval. Finalizing a run made by an OLDER or a
different producer is held to the same contract by the finalizer's own re-run -
that is the part that keeps growing, because every check added to the runner has
to be re-derivable from the files a finished run leaves behind. What is left
there is not a known hole but a standing obligation: a check added on one side
belongs on the other.

### The step before the plan (v7.37)

`corpus_intake.py`. The corpus is 116 publications and roughly six hundred
figures, and every one of them needs a `source_figure_manifest` row before any
of it can be planned: publication 127 cost **forty source-panel rows to
digitize three panels**. That rule is right - it is what stops a figure
disappearing because nobody made a row for it - but it made the unit of work
the article, and until now the article was typed by hand.

So this reads the PDF's own text layer with coordinates, finds the blocks that
open with a figure label, links each to the page region above it, and writes one
draft row per candidate with where it came from, what it says, how it was found,
and who has checked it - which is nobody:

    python3 corpus_intake.py PDF [PDF ...] --out DRAFT_DIR

**It proposes and never asserts.** `Human_Verification_Status` starts at
`PENDING` and there is no path by which the module writes anything else.
`inventory_rows` turns a draft into `source_figure_manifest` rows only when
EVERY row says `CONFIRMED`, with a registered reviewer, a date and a panel
count; a draft still holding one `PENDING` row produces no inventory at all,
because "these seven figures are the article" is a claim about the whole
article and a partial one is worse than none. `Panel_Count_Method` comes out
`HUMAN_VISUAL` because that is what happened.

**The panel count is deliberately not proposed.** Counting the axes in a
printed figure is the single judgement the source inventory exists to record,
and a proposed count is a number a tired person clicks past. The draft carries
the figure's bounding box so the contact sheet can show the picture; the count
comes from the person looking at it.

**The confidence orders the sheet and says why in words.** Not a probability,
and it never removes a row - it decides what a person reads first. A body too
short to be a caption costs 0.4 and the reason counts the characters; a second
block **anywhere in the document** opening with the same label costs 0.3 and
the reason says how many; a label followed by a lower-case word costs 0.3 and
the reason quotes it; nothing printed above costs 0.1. `contact_sheet` sorts
lowest first, highlights everything under 0.6 and prints the sentence beside
the score.

Those last two rules are what the forward run on publication 127 bought. The
first version proposed **nine** figures for an article with seven: page 4 opens
a paragraph with "Figure 1 shows the pre- and post-flight recordings" and page 6
opens one with "Figure 7 shows the relationship between mean RRI and spectral
powers". The first scored 0.70 - the real Figure 1 caption is on the same page,
so the duplicate-label rule caught it - and **the second scored 1.00**, because
Figure 7's real caption is on page 9 and the count was per page. Counting per
document catches the pair; the lower-case rule catches the kind. A caption names
its subject ("Figure 5 Results from systolic arterial pressure"); a sentence
about a figure continues in the third person. Now all seven real figures come
out at 0.70-1.00 and both intruders at 0.40, under the threshold, each carrying
the sentence that says why.

Measured on fifteen publisher PDFs from the corpus: 62 candidate rows,
**9 (15%) below 0.6** - which is the number of rows a person rejects rather than
counts.

**A document that proposes nothing is reported, not skipped.** `2016-2-11.pdf`
read 357 text blocks and produced zero candidates, which on a walk of
ninety-seven articles looks exactly like an article with no figures. It is a
China Astronaut Research and Training Center review whose one figure is labelled
`图 1.`, with `Fig. 1.` on the line below. `图` and `圖` are now labels, and
`main` lists every document that read fine and proposed nothing under a line
saying that this is not the same as having no figures.

**The backend is optional, like `cv2`.** `pdfminer.six` if it is installed,
`pdftotext -bbox-layout` if it is not, a refusal naming both if neither is - and
`Extraction_Method` is recorded per row, because a caption box from one is not
a caption box from the other. A PDF with no text layer is `NotReadable`, which
is a different answer from `BackendUnavailable`: the first needs a page render
and a person, the second needs an install. A corpus walk reports both and stops
for neither. About 42% of this corpus is expected to land in the first bucket.

**What this does not do yet.** It does not render pages, so `Page_Raster` is
blank unless one is supplied; it does not read two-column layouts any better
than the block extractor does; and `Data_Shape_Expected` is still unfilled -
the caption text a screen would read is now available per figure, which is the
input `kernel.fig_screen_caption` has been waiting for.

### The plan key that nobody reads, and two identifiers in one column (v7.38)

Four boundaries, all of them the same mistake at different layers: **a field
that is allowed to exist and is not the thing it appears to be.**

**A key allowlist is not a binding contract.** `PLAN_KEYS` refuses a key nothing
reads. It said nothing about a key that IS allowed and that nothing reads
either, and there were seven: `figure.image_sha256`, `figure_view.note`,
`series.colour_tolerance`, `position.slot_index`, `position.display_order`,
`unit.sparse_justification`, `unit.display_hint`. The last of those is the one
that bites - a plan writing `"grid_rule": "SPARSE"` with its justification
passed every plan check and compiled to a unit row whose `Sparse_Justification`
was blank, which the gate then refuses as `SPARSE_WITHOUT_JUSTIFICATION`. The
mirror image was also true: the compiler READ `figure.caption`,
`unit.outcome_variable`, `unit.extraction_method` and `unit.extractor_1`, and
the allowlist rejected any plan that supplied them, so those code paths could
not be reached from a plan at all.

All eleven are closed, and the contract is now checked by PARSING the compiler
rather than by reading it: every allowed key must appear as a subscript or a
`.get()` on some object in `compile_plan.py`, and a comment mentioning it does
not count. Five of the seven are checked at value level as well - a sentinel in,
the named column out - because `.get("display_hint")` proves somebody looked at
the key, not that the answer reached a manifest. `image_sha256` never becomes
the manifest hash (that is read off the bytes, which is the point); it is the
author saying which rendering they measured against, and a mismatch is
`PLAN_IMAGE_SHA256_MISMATCH`.

**`figure_view` needed the boundary that `Identity_Domain_ID` got.** The
compiler builds a figure row from `members[0]` - source figure, raster, caption,
hash - and counts all the members as its worklist. One mistyped view name
grafted figure 4's panels onto figure 3's provenance and every downstream file
agreed with itself. `PLAN_FIGURE_VIEW_SPANS_SOURCE_FIGURES`.

**And the domain was bounded by `Image_Path`, which this corpus makes
meaningless.** Pages are rendered whole at 600 DPI, so figure 3 and figure 4
routinely share one PNG: two printed legends under one domain passed, because
there was only one raster. The boundary is the join
`Panel_ID → Source_Panel_ID → Source_Figure_ID`
(`IDENTITY_DOMAIN_SPANS_SOURCE_FIGURES`); the raster comparison stays underneath
it, because one figure spread over two renderings is a different mistake.

**A fill means a CELL, not a level.** `IDENTITY_DOMAIN_FILL_CONFLICT` compared
`Factor_Level` alone, so `OPEN → TIMEPOINT:PRE` in one panel and
`OPEN → PHASE:PRE` in another sat in one domain without a word - two different
cells calibrating each other off one screen. The meaning is
`(Factor_Name, Factor_Level)` and the message names both.

**The geometry artifact had put the domain in a column called `Figure_ID`.**
Splitting the two concepts at runtime was only half of it: the reader took ONE
identifier, and `ARTIFACT_FIELD_COLUMNS` mapped it to `Figure_ID`. The moment
two views shared a legend - the scenario the whole feature exists for -
`mono_bar_geometry.csv` lost the provenance view, disagreed with the panel
manifest under a column of the same name, and `Figure_Identity_SHA256` was a
domain verdict wearing a figure's name. So:

```text
Panel_ID  Figure_ID  Identity_Domain_ID  Domain_Identity_SHA256  Auto_Identity_SHA256
```

The record carries `figure_id` and `identity_domain_id` separately, blank rather
than duplicated when a caller does not know the view; `verify_artifact` groups
the verdict by the DOMAIN (it was reading `Figure_ID` and agreeing with itself)
and refuses a panel that claims two `(Figure_ID, Identity_Domain_ID)` pairs; and
the value-side foreign key compares BOTH identifiers on the geometry row against
the panel manifest, so a row that names another view or another domain is
`IDENTITY_GEOMETRY_ROW_MISMATCH` even though every hash recomputes.

**Finalizer.** The copy-versus-manifest comparison walked the run's copies, so a
panel the verified manifest resolves and the run never copied had no key to
compare and was compared against nothing. It walks the union.

### A marker its own error bar runs through (v7.39)

The first pilot with a PRINTED GROUND TRUTH. Beckers et al. 2007 (*Microgravity
sci. technol.* XIX-5/6, 98-101) tabulate approximate entropy as mean and SEM for
supine and standing at five sessions, and plot the same means with 95%
confidence intervals in Figures 1 and 2. Ten cells, each with a number the paper
prints. Three things in the released LINE_MONO reader stood between the figure
and those ten cells, and none of them was about accuracy.

**An error-bar stem is drawn THROUGH its own marker.** Every SPSS error-bar
chart in this corpus looks like this, and the enclosed white of an open square
then arrives as two slivers either side of the stem: neither is a square, and
two candidates in one x cell is "keep neither". Two of ten markers read.
`_one_interior_per_marker` joins them - but only across INK, only when the
bridge actually connects two parts, and only up to a declared `stem_px`. The
guard is what makes it safe: closing a lone interior is not a merge but a
reshaping, and on publication 386's dense four-series panel it filled an
ambiguous blob's concavities until it classified as a TRIANGLE 2.4 units from
its own series and 0.6 from somebody else's. `forward_test_real_monochrome.py`
caught that, which is what a forward test is for.

**The whisker search was a hard 28 px.** That is a distance in a rendering
nobody declared. At 300 DPI a 95% confidence interval reaches 60-90 px, so every
whisker came back absent and both panels ended `NO_VARIANCE` with their centres
read correctly - a refusal nobody can act on. `whisker_search_px`,
`marker_half_height` and `stem_px` are declared reader options now; the panel
box already bounds the search.

**`Marker_Shape=ANY`.** A twelve-pixel open square with rounded corners
classifies as CIRCLE about as often as SQUARE, and this panel has ONE series, so
the verdict decides nothing except whether the figure can be read at all. ANY is
a declaration - "there is nothing here to tell apart" - not a wildcard: two
series may not both use it (`MARKER_SHAPE_ANY_NEEDS_ONE_SERIES`), it still
refuses two candidates in one cell, and the artifact records the shape the
reader actually SAW, never the word ANY.

**What the ten cells came out as.** 10 read, 10 machine-QC passed, 0 QC
problems, both panels `AUTO_PASS`, run mode `ATTESTED`.

| | mean absolute error | worst |
|---|---|---|
| mean, against the printed table | **0.0028** | 0.0057 |
| 95% CI half-width, against 2.776 x printed SEM | 0.0072 | 0.0133 |

The y axis spans 1.1 units, so the worst mean is 0.5% of the axis out, and the
table prints two decimals - +/-0.005 is its own resolution. The dispersion
column is a second, independent check: the caption says 95% CI, the table says
SEM, n = 5, and reconstructing one from the other to within 0.013 says the
caption was telling the truth and the reader found the caps the caption meant.

### Nothing leaves the walk unaccounted for (v7.40)

Intake proposed a row per CAPTION, so the documents worth knowing about
contributed nothing to any file it wrote. A PDF that read fine and produced no
candidates, one with no text layer, one that is not a PDF at all - each printed
a console line and then vanished. On a walk of ninety-seven articles that reads
exactly like ninety-seven that worked.

`intake_document_status.csv` is one row per PDF, always:

```text
Source_Document_ID  Source_File  Source_File_SHA256
Text_Backend  Text_Backend_Status  Page_Count  Text_Block_Count
Caption_Candidate_Count  Low_Confidence_Count
Page_Render_Status  Page_Render_Count  Page_Raster_Dir
Required_Action  Detail
```

The status is one of `TEXT_LAYER_OK`, `ZERO_CAPTION_CANDIDATES`,
`NO_TEXT_LAYER`, `BACKEND_UNAVAILABLE`, `INTAKE_FAILED`, and the point of
keeping them apart is that each needs a different thing done to it - a person on
a contact sheet, a look at the caption style, a page render and an eye, an
install, or a stack trace. `Required_Action` is the column to sort on.
`ledger_problems` refuses a ledger that does not account for every file the walk
was given, holds a document twice, files no candidates as a clean read, or
leaves candidates waiting under an action that does not mention them; `main`
exits non-zero when any of that is true.

CI installs `requirements-lock.txt` and nothing else, so it may have no PDF
backend at all - which is why the completeness half of this file is checked
unconditionally and only the per-status half is gated. With no backend every
document comes back `BACKEND_UNAVAILABLE` / `INSTALL_A_PDF_BACKEND`, and the
ledger still accounts for all of them. That is the property, and the first
version of these scenarios asserted `TEXT_LAYER_OK` on a runner that had
neither pdfminer nor poppler.

**`--render` renders.** It was in the docstring and wired to nothing. Every page
becomes a PNG, the draft row carries the raster and its hash, and a figure crop
is cut per candidate and shown on the sheet. Confirming a figure from
`Figure_BBox` is agreeing with a number; the crop is the thing a person can
actually answer "yes, that is Figure 2, and it has three panels" from - which is
the 1,500-2,000 inventory rows the corpus needs.

**And the crops found the next defect.** `figure_bbox` took the nearest block
above the caption by y alone. This literature is two-column, so the block above
a left-column caption is usually a paragraph in the RIGHT column at almost the
same height, and the region collapsed to a strip of body text. Bounding the
search to blocks that horizontally overlap the caption needs no column
detection and degrades to the old behaviour on a single-column page. Measured
over fifteen corpus PDFs, 62 candidates:

| | median crop height | crops under 80 px |
|---|---|---|
| by y alone | 127 px | 29 |
| same column | **433 px** | 21 |

### The measurement is proposed; the reading is not (v7.41)

`geometry_proposer.py`. Per panel the plan needs a box, an axis region, two
tick pairs, an x pixel per group and a series spec. The compiler checks every
one and the runner refuses without them - and nothing proposed any of them.
Publication 127 cost an hour on three panels; the worklist is 189 B-shape
figures.

The split is between what can be measured and what has to be read:

```text
proposed       plot frame, axis regions, tick PIXEL rows, tick spacing,
               ladder coverage, group anchor x pixels
never          what a tick is WORTH, what a series MEANS, how many panels
               the figure has
```

**The tick values are the whole reason for the split.** A printed 30 read as 3
rescales every value in the panel by ten, leaves the calibration residual at
zero and makes the file self-consistent and wrong. So the module reports
"twelve ticks, evenly spaced, at these rows" and a person types the first and
last - **two numbers per panel** instead of a measurement session.
`calibration_from` joins the two halves and returns nothing until both exist.

**Nothing in the detection is a distance in pixels.** A tick is short relative
to its axis, a group is separated from the next by a gutter that is a fraction
of the plot, the plot area is inset from the frame by a fraction rather than by
two pixels, and the reach of a tick is compared against the spine's own
thickness. That is the defect the LINE_MONO marker limits still have - the same
figure reads at 300 DPI and not at 500 - and the suite renders every fixture at
1x and 4x to hold it.

**`Y_Tick_Coverage`, because the failure it catches is silent.** Ticks drawn
INSIDE a boxed frame put the corner tick and the frame line in the same ink, so
the ladder loses its ends - and it is still perfectly evenly spaced. A person
types the first and last value against the wrong two rows and every check
passes. Regularity cannot see that; coverage can.

**The release gate is the one figure whose answer is printed.**
`forward_test_beckers_geometry.py` holds the proposal against the geometry this
project measured by hand for BF02919461 - the geometry that read ten printed
values to 0.0028:

| | box delta | ticks | anchors | coverage |
|---|---|---|---|---|
| Fig 1 supine | 1.0 px | 12 of 12, ends within 0.5 px | 5 of 5, worst 0.5 px | 0.999 |
| Fig 2 standing | 1.0 px | 12 of 12, ends within 0.5 px | 5 of 5, worst 0.2 px | 0.999 |

And running the pipeline on the PROPOSED geometry, with the two typed numbers,
reads the same ten cells: **0.0002 mean difference from the hand-authored plan,
and the same 0.0028 against the printed table.** The hour of measuring is now
two numbers and a look at an overlay.

### The ledger is a work queue, not a list (v7.42)

The ledger accounted for every file and then filed several of them under the
wrong job. Five things, all of them the same shape: a column that exists and
does not mean what it says.

**A scanned paper is not a corrupt file.** `NO_TEXT_LAYER` was written only when
the parser RAISED, and pdfminer does not raise on an image-only page - it walks
it and returns nothing. So a real scanned PDF came back
`ZERO_CAPTION_CANDIDATES / CHECK_CAPTION_STYLE`, which asks somebody to look at
a caption pattern for a document that has no text at all; and a truncated
download came back `NO_TEXT_LAYER / RENDER_AND_INVENTORY_BY_EYE`, which asks
somebody to inventory figures in a file that is not a PDF. About 42% of this
corpus is expected to be the first. The two are separated by `is_a_pdf` - the
file's own header - and by whether the parse produced any blocks at all, not by
whether it threw.

**The page count is the file's.** It was `max(block page number)`, so a paper
whose last pages are scanned reported a shorter document and a wholly scanned
one reported zero pages - which reads exactly like a file that is not a PDF.
`page_count` reads the structure, via pypdf, pdfminer or `pdfinfo`.

**One status, one action.** Checking both against a vocabulary does not say
that each status needs a different thing done to it: `NO_TEXT_LAYER /
INSTALL_A_PDF_BACKEND` passed every check and sent a scanned page to whoever
installs software. `STATUS_ACTION` is the transition table, the counts have to
agree with the status they were filed under (`Text_Block_Count`,
`Caption_Candidate_Count`, a named backend under `BACKEND_UNAVAILABLE`, a
`Detail` under `INTAKE_FAILED`), and a count that is not a number is
`LEDGER_COUNT_NOT_A_NUMBER` instead of quietly becoming -1.

**A contact sheet with no picture on it is not ready to be confirmed.**
`--render` is optional, so the default walk told a person to confirm figures
from `Figure_BBox` strings - the thing rendering exists to stop. `TEXT_LAYER_OK`
now maps to `CONFIRM_ON_CONTACT_SHEET` only when the pages were rendered, to
`RENDER_CONTACT_SHEET` when they were not, and to `INSTALL_A_PAGE_RENDERER`
when a render was asked for and none came. The renderer and the text backend
are different tools and fail independently.

**And `documents.html`, because the candidate sheet cannot answer the question
the inventory asks.** Six confirmed candidates in a seven-figure paper is six
correct rows and a wrong inventory; `inventory_rows` checks the rows that
exist, and the missing figure never made one. The document sheet shows EVERY
rendered page, with each document's candidates listed beside them, and asks for
`Observed_Figure_Count` and `Pages_Checked` - a figure nothing pointed at is
visible precisely because the page is on the screen and nothing is on it.

Four smaller ones from the same review: completeness is keyed on the input PATH
(a corpus keeps `pub127/fulltext.pdf` beside `pub386/fulltext.pdf`, and on
basenames those are one document twice - which also hides a genuinely missing
paper behind the other's row); `Source_Document_ID` must be unique across the
walk, because it names the page directory and prefixes every `Draft_ID`;
`--document-id` refuses to name two files at once; the page directory is
cleared before a re-run, so a shorter document does not inherit the previous
one's tail; the text layer is parsed ONCE and handed to `draft_rows`; and a
crop with no page size behind it is refused rather than scaled to US Letter,
which on this A4 corpus put it 9% out in y.

### A marker is the size of the markers in its panel (v7.43)

The last absolute pixel count in a released reader. `read_monochrome_marker_panel`
accepted a blob by area 12-300 px with no side over 24, which is a marker at
300 DPI and half of one at 600 - so the SAME PAGE read differently depending on
how it had been rendered, and nothing said so. Measured on publication
BF02919461 before the fix:

| render | cells read |
|---|---|
| 300 DPI | 10 of 10 |
| 450 DPI | 2 of 10 |
| 500 DPI | 0 of 10 |

A panel has ONE marker size by construction - it is drawn by one plotting
program at one setting - so `measure_marker_scale` reads it off the panel in a
first pass and the limits become ratios of it. That is what BAR_MONO has done
with its stroke scale since it shipped.

**The biggest seed per x cell, not the median of every seed.** A median over
all of them is dragged down by antialiasing specks and by the dots inside a
stippled fill, and how many of those exist depends on the rendering - the very
thing being removed. At 450 DPI that median came out 6 px against a 16 px
marker and the panel read nothing. A declared x holds one marker per series, so
the largest seed at it is a marker, and the median across cells survives one
odd cell.

After, on the same page, against the printed Table 1:

```text
200 DPI  10 of 10   worst 0.0055
300 DPI  10 of 10   worst 0.0057
450 DPI  10 of 10   worst 0.0062
600 DPI  10 of 10   worst 0.0055
720 DPI  10 of 10   worst 0.0058
```

`forward_test_beckers_dpi.py` is that table, and it checks the values against
the paper rather than against each other: a reader that agreed with itself at
five renderings while being wrong at all of them would pass a self-consistency
test and fail this one.

An area floor was written alongside the side window and then removed - every
blob it would have rejected is already outside the window or under the seed
minimum, and a guard nothing can observe is decoration.

## Suites

All run with scipy hard-blocked by a `sys.meta_path` finder.

| suite | scenarios |
|---|---|
| `test_run_batch.py` | 698 |
| `test_kernel.py` | 232 |
| `test_measure_mono_bars.py` | 297 |
| `test_grid_engine.py` | 180 |
| `test_finalize.py` | 176 |
| `test_compile_plan.py` | 146 |
| `test_corpus_intake.py` | 123 |
| `test_geometry_proposer.py` | 45 |
| `test_mark_readers.py` | 116 |
| `test_bar_reader.py` | 73 |
| `test_mono_bar.py` | 55 |
| `test_integration.py` | 19 |
| `test_reproducibility.py` | 20 |
| **total** | **2184** |

Counted, not carried forward: `test_mark_readers.py` was listed at 92 and has
been 96 since the point-count audit scenarios went in.

Plus `crosscheck_id323.py` (0.50 px / 2.50 px over 72 bars, two independent
primitives), `forward_test_397_mono_bar.py` (the production reader) and
`forward_test_397_mono_geometry.py` (the prototype, which shares none of its
code), `forward_test_127_mono_bar.py` (SKIPs in CI: its raster is not
redistributable), and two worked examples:

- `build_id323.py` — 2 figures, 12 units, 107 values, 2 problems, both the known
  `TIMEPOINT=DI19` hole where two bars overlap past separating
- `build_397.py` is **removed**. It was a single-figure worked example, and the
  source inventory makes a partial example impossible on purpose: declare a
  document and every one of its figures must be inventoried, declare a figure
  and every one of its panels must be. Either it grew into a second copy of
  `pilot_397.py` or it had to go. `pilot_397.py` does everything it did.


## Shipped: LINE_MONO_STYLE, solid versus dashed

`line_style_mono.py`, dispatched as `LINE_MONO_STYLE`, out of `wip/` and into
the reader set. It is the figure type 121 of the worklist's 353 figures are:
two black curves, no markers at all, and a legend that says which is which.
`wip/` is gone.

**The discriminant is not the duty cycle.** That was the obvious answer and it
does not survive measurement — the fraction of columns a dash pattern inks
depends on where in its phase the fitting window opens, and on the fixture the
same dashed stroke measures 0.605 to 0.81, straight through the bottom of the
band a solid line occupies. The **longest run of skipped columns** does not
move: a solid stroke never has one, a dash pattern has one every period. Duty is
kept for the one thing it can do, which is separate DOTTED from DASHED.

**Four defects the drawn fixture could not show, all found on 397 Figure 1.**
This is why the release gate is `forward_test_397_line_style.py` and not the
fixture:

- **gridlines** measure duty 1.000 and gap 0. Four of them made five SOLID
  candidates at every x, the count was never one, and the reader emitted no
  solid cells anywhere on the figure while reporting no problem at all
- **error-bar stems** are removed before tracing, which takes the curve's own
  pixels with them; scored as misses that gave every solid curve a gap of 3,
  one over the limit. A column we cannot see through is not a column where the
  curve is absent, so it is skipped in both halves of the fraction
- **whisker caps** sit exactly where a curve turning down would have continued.
  A cap is a short horizontal stroke and so is a steep curve, so length cannot
  separate them: a cap has a stem under it, and it ends
- the value was read off the **fitted quadratic**, which rounds a corner. The
  fit now says where to look and the ink says how high

**Where it refuses.** 8 of 24 cells on the gate panel, at the four positions
where the two curves run within about two mmHg — at 6:00 they touch. A style
found somewhere on the panel is expected everywhere on it, and a position where
an expected style is missing while another was found is a position where they
merged: no cell for either series. The 16 it emits are all within 1.65 mmHg of
an independent eye reading on a 50 mmHg axis.

**A dispersion is the connected column of ink through the mark**, not the
nearest wide stroke either side. On a two-curve time course the neighbour's cap
is a wide stroke a few pixels away, and taking it gave a dispersion 1.99 units
short of the truth — a plausible number that is simply wrong. Where the two
bars touch, the run holds both marks, and the cell keeps its mean and reports
no dispersion.

**`GEOMETRY_NOT_AUTHORED`** is new in `SOURCE_PANEL_DISPOSITIONS`. Releasing
this reader turned eight of publication 397's panels from "we cannot read this"
into "we have not measured this", and `NO_READER_AVAILABLE` is a claim about
the package that stopped being true for them. It is a TARGET disposition, it is
not closed, and it shows as `AWAITING_GEOMETRY` in the source-panel inventory.
Those eight have since been measured, so nothing in this repository carries it
today — the disposition stays because the next reader will create the state
again.

All twelve panels' geometry is measured off its own raster. They had been
declared before any reader existed, with one box copied to every panel and
twelve x pixels spread evenly between the box edges — honest while nothing
could read them, and not geometry. Measuring twelve panels by hand trades one
silent error for twelve chances at a transcription one, so
`forward_test_397_line_geometry.py` checks every declared number against the
pixels: each calibration row has to be a printed gridline, each x has to be the
centre of its category interval (these are Excel category charts, so the point
is between the ticks and not on one), and the twelve intervals have to be
equal.

The yield is low and it is the right answer. 76 of 384 declared cells: several
of these panels run their two curves within a stroke of each other for most of
their length, and finger pulse volume in men is two lines about fourteen pixels
apart at nine of twelve positions. A cell nobody can attribute is a cell this
reader does not emit. Each is now measured off its own raster.

## Intake: the picture on the sheet, and the papers that have no picture at all

`Crop_Quality_Status` — ACCEPTABLE / THIN_CROP / NO_CROP — on every draft row,
and the contact sheet shows **the whole page** for anything that is not
ACCEPTABLE, saying so. `Figure_BBox` is the gap between a caption and whatever
is printed above it in the same column, and on fifteen staged articles 21 of 62
crops came out under a tenth of the page: a strip of white with the figure an
inch further up. A person shown that strip either confirms a figure they cannot
see or rejects one that is there. The threshold is a fraction of the page, not
a pixel count, so the same figure rendered at 150 and 300 DPI gets the same
answer.

`source_kind` replaces `is_a_pdf` with four answers instead of two, and the new
one is the one this corpus needed. Twelve of the 116 publications on the
worklist arrive as **JATS XML or plain text**, carrying 37 figures between them.
The captions are in the file and the pictures are not, so there is nothing to
render and nothing to crop however long anybody looks — and filed as
`INTAKE_FAILED`, all twelve went to whoever investigates broken downloads.

- `NO_RASTER_SOURCE` → `OBTAIN_PUBLISHER_FIGURE`
- a JATS `<fig>` is a better inventory than any caption regex: the label is
  marked up as a label and the caption as a caption, so nothing is guessed and
  the confidence is 1.00. The figure NUMBER comes from the document's own
  label, not from the position in the list — a paper whose body starts at
  Figure 2 is not a paper whose first figure is Figure 1
- what is missing is recorded where every other row records it,
  `Crop_Quality_Status=NO_CROP`, and the rows are `PENDING` like every other
  proposal
- an HTML "access denied" page saved as `.pdf`, an empty file and a binary blob
  are still `INTAKE_FAILED` → `INVESTIGATE`

## What scale the numbers are on, and what shape the distribution is

Three new unit columns, all read out of the METHODS TEXT and none of them
visible in any raster: `Analysis_Transformation`, `Distribution_Shape`,
`Transformation_Source`.

**`SE_IMPLIES_HUGE_SD` was firing on correct data.** "SD is half again the
mean" is impossible for a symmetric distribution over a ratio scale — most of
the mass would sit below zero, and the outcome cannot go there. For a
right-skewed one it is Tuesday: spectral power in ms² routinely has a
coefficient of variation over 1.5, and the check fired on every correct row of
it. A check that fires on correct data teaches a reader to ignore it, which
costs more than not having it. It now needs the distribution:

- `SYMMETRIC` → `SE_IMPLIES_HUGE_SD`, and the message says why it is impossible
- `RIGHT_SKEWED` / `LEFT_SKEWED` → nothing; this is what those look like
- `UNKNOWN` → `DISPERSION_IMPLIES_SKEW`, which asks for the shape instead of
  accusing the numbers: *either the outcome is skewed, and the unit should say
  so, or one of these numbers is wrong — undeclared, there is no way to tell*

**A mean of log10(x) is not a mean of x**, and the two carry the same axis
label. `Analysis_Transformation=UNKNOWN` blocks with
`TRANSFORMED_SCALE_UNRESOLVED`; a declared transformation blocks with
`TRANSFORMED_SCALE_NOT_POOLABLE` — the values may be perfectly read, and this
package does not back-transform, so they are recorded and pooled separately or
not at all. A transformation other than `UNTRANSFORMED` must quote the wording
that supports it (`TRANSFORMATION_UNSOURCED`), and a hedged quote is refused
the way a hedged `Errorbar_Definition_Source` is.

`UNTRANSFORMED`, not `NONE`. `NONE` is in `FIG_NULL_TOKENS` — one of the
spellings a coder uses for "I did not fill this in" — and "the authors did not
transform their outcome" is a positive claim that has to survive the blank
check. The first attempt used `NONE` and every correctly filled row came back
`BAD_ANALYSIS_TRANSFORMATION`.

Both validators carry the vocabulary and `test_kernel` pins that they agree: a
template the standalone validator accepts and the batch gate rejects is a
template nobody can fill.

## The last two rungs, on a real publication

`pilot_397.py` is the biggest worked example here and it stops at `QC_FAILED`,
because publication 397 never says whether its error bars are SD or SEM. That
is the right answer, and it meant `HUMAN_APPROVED` and `POOLING_ELIGIBLE` had
only ever been demonstrated against fixtures in `test_finalize.py`.

`pilot_beckers.py` finishes the ladder. Beckers 2007 plots approximate entropy
as mean and 95% CI at five sessions in two postures, the caption says exactly
that, and **Table 1 of the same paper prints the same means** — so there is a
reader-independent answer at the end, which is why it is worth doing here
rather than on a fixture whose truth this package wrote itself.

Attested, it runs `AUTO_EXTRACTED → MACHINE_QC_PASSED → HUMAN_APPROVED →
POOLING_ELIGIBLE` and writes ten accepted values:

    finalize: FINALIZED | panels approved 2 | values accepted 10
    worst mean 0.0057, worst half-width 0.0133

The half-width is the second, independent check. With n=5 a 95% interval is
2.776 SEM either side, so reconstructing the printed SEM from the digitized
whisker catches the failure a correct mean hides — a whisker measured off a
significance glyph.

Unattested it never gets that far, and the refusal is the runner's, not the
finalizer's: a `DEMO_ONLY` run whose values pass the machine gate has produced
exactly the artifact a demonstration must not leave behind, so `run_batch`
deletes its own output and stamps `DEMO_OUTPUT_REFUSED`. There is nothing to
review because there is nothing on disk to review.

**The reference table has to be transcribed, not remembered.** The first
version of `TABLE_1` in that file had the means right and half the SEM column
invented, and the half-width check failed by 0.17 against a reading that was
correct to 0.013. A fabricated reference does not merely fail — it accuses the
measurement.

The publisher PDF is not redistributable, so this SKIPs in CI like the two
Beckers forward tests, and `test_reproducibility` now checks that CI runs every
worked example as well as every test and forward test.

## v7.50 — a blinded window does not get to call a curve solid

`LINE_MONO_STYLE` classified the ink again at every position and believed the
answer. It should not have, and publication 397 Figure 1 said so at 0:30, where
the reader refused both cells and the release note called it a merge. It was
not a merge: **the two curves are four mmHg apart there and both plainly
traceable.** Two defects, neither of them about this paper.

**The panel box says where the panel is; the declared positions say where the
data is.** At the first plotted point half the fit window hangs over the axis,
and one stray pixel of axis furniture — sixteen columns from the nearest curve,
four pixels of ink — was collected as a sample of the curve. It stretched the
fitted span from column 95 back to 84, dragged the quadratic six pixels, and
the dashed curve came back at 90.7 where the eye reads 89.0: **inside the
forward test's tolerance, and wrong.** Clipped to the declared span ± one
`x_window`, it reads 89.4. On the drawn fixture the same four pixels used to
cost that position both its cells.

**Blinding hides gaps and cannot invent them.** Every column carrying furniture
is dropped from the duty accounting — it has to be, or the stems alone would
give every solid curve on this figure a gap of 3 — so the removal is not
symmetric. The dashed curve runs along the 90 mmHg gridline through 0:30; 68%
of that window is blinded, every dash gap with it, and it measured duty 1.000
gap 0. A perfect solid line. Two SOLID candidates at one x meant neither was
unique, and a correctly traced curve whose value was right to 0.4 mmHg was
thrown away.

A SOLID call made through a window that could not see half of itself is now
withheld. DASHED and DOTTED need no such guard: a gap that was SEEN is a gap.

What replaces the withheld call is **elimination, not continuity**. Where the
panel declares N series, the reader found N curves at that x, and N-1 measured
their own style, the last one has no choice left. Every emitted cell says which
way it was named, in `line_style_source`, and carries the blindness that
justifies it.

A track-voting version was written first, measured, and thrown away. It
recovered nothing on 397 that elimination does not, and it had a failure mode
elimination cannot have: where its fill assigned a style a candidate at that x
already carried, the count became two — the reader's own signal that it cannot
tell two curves apart — and six cells on the WOMEN finger-pulse-volume panel
that were about to be emitted were destroyed instead. An unobservable mechanism
with a way to go wrong is worse than no mechanism.

On the whole publication: **76 → 123 values**, 0:30 among them, and two panels
that reported `NO_VARIANCE` because they read too few cells to carry a
dispersion now report `QC_FAILED` with the rest of the paper. Nothing is
accepted either way — 397 still never says SD or SEM.

    reverted                                    scenarios that fail
    the data span clip                          2 + the forward test
    the blinded-window guard on SOLID           3 + the forward test
    naming the last curve by elimination        4 + the forward test

**Not fixed, and named in the reader.** At 4:30, 5:00 and 6:00 the two curves
are one run of ink. It is nine to ten pixels thick where a stroke is three, and
at 4:30 and 5:00 it separates again a few columns later — so its top and bottom
edges are the two curves, and which edge is which is exactly what continuity
would say. Six of twenty-four cells stay refused there. 6:00 is a genuine
touch: the eye reads both series at 98.0, and two different numbers out of one
seven-pixel stroke would be invention.

**`line_style_source` does not reach `figure_values_*.csv` yet.** The reader row
carries it and the forward test pins it; the values file has `Identity_Source`
for exactly this purpose and only BAR_MONO fills it. A reviewer approving a
line cell cannot currently see that its series was named by elimination.

## v7.51 — the picture a reviewer approves has to say what it does not know

v7.50 taught the reader to name a curve by elimination where the window was too
blinded to measure its stroke pattern, and recorded that in `line_style_source`
on the reader row. It stopped there. **The overlay is the artifact a reviewer
approves** — its whole question is "did it put the marks in the right places" —
and a mark whose SERIES was reasoned to rather than read looked exactly like
one read off the ink. The reviewer with the most reason to look twice had none.

Inferred marks are now starred on the label and counted in a footer key of
their own. On its own line, because appended to the subtitle it ran off the
right edge of a 570-pixel canvas and read `* 4 of them: the SERIE`.

A provenance token `review_overlay` has never heard of counts as an inference,
not as a measurement: a reader that grows a new way of naming a series is added
to `IDENTITY_SOURCE_FIELDS` on purpose, and until it is, the picture errs
towards asking.

**Three numbers in README were still the v7.49 numbers.** `76 read`,
`16 of 24 cells`, `refuses the other 8` — and `verify_documented_status.py`
passed the whole time, because it guards the scenario counts, the version and
the one status sentence, and these were three other sentences. The guard was
right about its own scope and the file was wrong; both are worth writing down,
because "CI is green" was not the same as "the README is true".

## v7.52 — the guard v7.51 documented was not the guard it had

v7.51 said this about the overlay's provenance registry:

> a provenance field this file has never heard of would otherwise pass as a
> measurement

**Backwards.** A whitelist of FIELD NAMES protects against an unknown TOKEN in
a field it knows and is blind to a field it does not. A future reader emitting
`marker_identity_source = "ELIMINATION"` and forgetting to register it would
have drawn a plain, unstarred mark — and the comment beside the list would have
said that could not happen. A guarantee written down and not implemented is
worse than the gap it describes, because it stops the next person looking.

The real guard is a naming convention, not the list: a key ending `_source` or
`_method` that `review_overlay` cannot interpret marks the label `?` and adds a
footer line naming the field, because registering it is the fix and the person
reading the picture is the one who can say so. A field named nothing like
either still slips through; that is now written down as a limit rather than as
a covered case.

## v7.53 — six of a hundred and eighty numbers were read off the ink

The review found that the reader's inferences do not move between the raw
marks, the overlay and the value file, and that this is not a
`LINE_MONO_STYLE` problem: `BAR_MONO` writes `AUTO / FILL_MEASURED` for a fill
it matched against a prototype formed in another group, `BOX_VIOLIN` and
single-series `SCATTER` and marker `ANY` name a series from a declaration
rather than from ink, and `Identity_Source` is a BAR_MONO field whose presence
on any other row is refused with `IDENTITY_PANEL_BINDING_CONTRADICTS_MARK_TYPE`.
All of that checks out against the code.

This release is the foundation the rest hangs off, and one measurement that
changes what the gates should be.

**Two questions, two fields, one derived tier.** `provenance.py` holds
`IDENTITY_METHODS` (HOW a series was named) and `VALUE_METHODS` (HOW the number
was arrived at), each mapped to a review tier R0-R4, and `review_tier()` is the
WORSE of the two. Derived, never read from a file: a tier a reader writes is a
tier a reader can lower. An unregistered method costs R4, not R0 - the fail-open
that v7.51's overlay whitelist had, refused here by construction. R4 is not
finalizable at any signature, because a reviewer looking at an overlay cannot
tell a fitted y from a read one; that is exactly what the picture cannot show.

**`_ink_at` had four paths and returned one thing.** Direct ink in the column,
interpolation between ink on both sides, the nearest ink when only one side has
any, and the fitted curve when there is none. All four left by the same door as
a measurement. They are now named, and the interpolated span is reported.

**Then the number.** Every `LINE_MONO_STYLE` cell on publication 397, twelve
panels:

    DIRECT_CURVE_INK          R0     6 cells
    INTERPOLATED_CURVE_INK    R3   160 cells    worst span 38 px
    EXTRAPOLATED_CURVE_INK    R4    14 cells

**Six of a hundred and eighty are direct observations.** And the span
distribution is not one population: 122 of the 160 interpolate across three
pixels or fewer, which is the error-bar stem this reader BLINDS AT EVERY DATUM -
the curve is occluded by furniture the reader removed itself, and stepping over
it restores a printed stroke. A tail of fifteen cells spans 14 to 38 px, and 38
px is wider than the 32.5 px between two plotted points: that is a guess about a
curve nobody sampled.

So the tier table cannot be applied as written yet. `INTERPOLATED_CURVE_INK` at
R3 with cell-level confirmation would put 160 of 180 cells into signature-by-
signature review, 122 of them for "the reader stepped over its own three-pixel
stem" - and a confirmation that fires on almost everything is the checkbox
people learn to click, which is the same failure the review warns about for
`Inference_Checked` on every panel, one level down. The span has to be compared
against a figure-derived reference - the width of the furniture removed at that
x, and the dash period - before the tier is assigned. That reference is the next
piece of work and it is not in this release.

Not in this release either, and named so it is not mistaken for done: the common
fields do not reach `figure_values_*.csv`, no gate consumes a tier, the overlay
still reads `line_style_source` rather than `Identity_Method`, and `BAR_MONO`,
`BOX_VIOLIN`, `SCATTER` and `LINE_MONO` emit no method at all.

    reverted                                        scenarios that fail
    the tier being the WORSE of the two             2
    an unknown method costing the highest tier      3
    R4 being unfinalizable                          3
    one-sided ink told apart from interpolation     1
    the fit admitting it made the number            1

## v7.54 — the reader that decides the number was not in the code hash

**P0.** `PIPELINE_CODE_FILES` did not contain `line_style_mono.py` or
`provenance.py`. `reader_functions()` dispatches `LINE_MONO_STYLE` to
`read_monochrome_line_panel`, whose `_ink_at` decides the mean of 174 of the 180
cells publication 397's line panels produce, and `provenance` decides the method
and tier every one of them carries. **Either could have been rewritten between
two batches and `Pipeline_Code_SHA256` would have said the runs were produced by
identical code** — from v7.44, when the reader shipped, to v7.53.

The same shape as `mono_bar_geometry.py`, which is what the reachability guard
in `test_run_batch` was written for after that one. It did not catch this one,
and the reason is worth more than the fix: it walked the module OBJECTS bound as
attributes of each module, and

    def reader_functions():
        from line_style_mono import read_monochrome_line_panel

imports inside the function — to break a cycle, deliberately — so what
`run_batch` binds is the FUNCTION. `line_style_mono` never appears in
`vars(run_batch)`, the walk never reached it, and the scenario reported that
every module run_batch reaches was hashed. It was telling the truth about a
question that was not the question.

The guard now follows the imports each file DECLARES, read out of the source
with `ast`. Where an import statement sits — module level, inside a function,
inside a `try` — is a property of the code that has nothing to do with whether
the module decides a number, and a guard that depends on it fails the moment
somebody moves an import to break a cycle. Which is exactly why that import is
where it is.

Two mutation scenarios per file, named rather than looped: a loop over
`PIPELINE_CODE_FILES` passes for every file in the tuple by construction, which
is what it would have been doing while these two were absent from it.

A third change was written and removed. Seeding the walk with
`reader_functions()`'s modules as well looked like a belt beside the brace, and
a revert of it failed nothing — a dispatch table cannot name a reader it does
not import, so the AST walk already reaches it. Decoration, deleted.

    reverted                                     scenarios that fail
    both files dropped from the hash             4
    the walk not following declared imports      1

## v7.55 — why a gap carried no ink is not the same question as how wide it is

Step 2 of the provenance programme. v7.53 measured that 160 of 180
`LINE_MONO_STYLE` cells on publication 397 interpolate, and that 122 of those
span three pixels or fewer — the width of the error-bar stem standing at every
datum. **A boolean union of stem, rule and cap cannot say whether such a gap is
a stroke this reader erased or a three-pixel dash gap the figure drew, and
neither can the span: they are the same width.** So the union is still what
blinds the accounting, and the PARTS are now kept.

    BLIND_CAUSES = ("ERRORBAR_STEM", "HORIZONTAL_RULE", "WHISKER_CAP")

`_ink_at` also reports the two columns its answer was measured between, and
`_occlusion_cause` says what covered the ones in between. **A cause is only
claimed when EVERY intervening column is covered by the SAME mask.** A gap
explained for two of its three columns is not an explained gap, and calling it
one is how a real dash gap would come to be treated as a stroke the reader had
erased. Partly covered, or covered by two kinds at once, is `MIXED`; covered by
nothing is `NONE` — the figure's own doing rather than the reader's.

Every cell now carries `Value_Support_Left_Px`, `Value_Support_Right_Px`,
`Occlusion_Cause` and `Occlusion_Width_Px`. Nothing consumes them yet: no tier
moved, no gate changed, and `pilot_397` reads the same 18/22/10/18/6/20/9/12/
24/8/12/21 cells it read at v7.54.

**What the separation shows on 397**, across all twelve line panels:

    cause              span<=3   4-9   10+    all
    ERRORBAR_STEM          120     1     0    121
    HORIZONTAL_RULE          0     1     7      8
    WHISKER_CAP              0     0     0      0
    MIXED                    2    21     8     31
    NONE                     0     0     0      0

121 of the 160 interpolations are fully explained by the stem. Eight by the
gridline — and seven of those span ten pixels or more, so furniture and LOCALITY
are genuinely independent axes rather than one axis measured twice. Thirty-one
are only partly explained and stay refused as furniture. And **two of the
span<=3 cells are MIXED, not stem**: a width rule would have called those two
restored furniture, which is the whole reason this is not a width rule.

**A scenario that passed and should not have.** The first version of the
cause-separation scenarios stayed green with `ERRORBAR_STEM` aliased to
`stem|rule|cap`, because on a figure whose only furniture at the data IS the
stem, a union and a part answer alike. The revert harness caught it: nothing
observed that the causes were DISTINCT rather than three names for one mask. The
gridline laid along the dashed curve at T7 is where they differ — a 35-column gap
the rule explains, which an aliased reader files under the stem — and that is now
a scenario.

    reverted                                      scenarios that fail
    the causes unioned back into one mask         1
    a partly covered gap counting as covered      2
    the supports not being reported               1

Next, in order: the reference widths (stroke, dash period, position spacing) on
the row, then `INTERPOLATED_CURVE_INK` split into restored-furniture,
local-interpolation and nonlocal-interpolation with fixed tiers.

## v7.56 — a span means nothing until it is compared with the figure's own scale

Step 3. Three pixels is a restored stroke at one rendering and a whole dash
period at another, so any fixed pixel threshold makes "is this gap local" depend
on the DPI somebody rendered at — the defect `forward_test_beckers_dpi` exists to
keep out of the values. The three things a span has to be judged against are now
measured on the figure and written on the row:

    Local_Stroke_Px          the ink that supplied the value, at the very
                             columns it came from
    Expected_Dash_Gap_Px     the median of every run of empty columns any window
                             found along a curve of this style, on this panel
    Position_Spacing_Px      the closest two declared positions

Measured per style, because a solid curve has no dashes to expect and a dashed
one does; one number for the panel would describe neither. On 397's twelve line
panels: spacing 32.5–35.0 px, dashed gap 4–5 px, solid 0–2 px (which is the
noise floor, not a dash pattern), stroke 1–9 px.

**And the first candidate rule for step 4 died on contact with the numbers.**
`span <= Local_Stroke_Px + Occlusion_Width_Px` looked like the natural test for
"this gap is the furniture we removed". It passes 160 of 160 interpolations,
including every `MIXED` one, because the span between two supports IS the
occluded columns plus one — arithmetic, not evidence. What separates is the
spacing:

    cause              cells   over half the position spacing
    ERRORBAR_STEM        121      0
    HORIZONTAL_RULE        8      6
    MIXED                 31      7

Not one stem gap reaches half the distance to the next datum; six of the eight
gridline gaps do. That is the locality axis, and it is independent of the cause
axis — which is why both are recorded and neither is judged here.

**`_line_fit_window` returns a dict.** It returned a tuple, and the tuple grew
from four fields to eleven in three releases; each growth silently reindexed
every caller, and two of those reindexings were caught by an arity assertion
rather than by anything that cared what the numbers meant. Thirteen named fields
now, pinned as a set by a scenario, so the next one added cannot move an
existing one.

Nothing consumes any of it. `pilot_397` reads the same cells, and a scenario
asserts every row's tier is still exactly what the registry derives from its two
methods.

    reverted                                          scenarios that fail
    the stroke measured at the supports                1
    every gap run collected, not just the longest      2
    the dash gap measured per style                    1
    the position spacing measured from the declaration 1
    the window reporting named fields                  1

Next: `INTERPOLATED_CURVE_INK` split into restored-furniture, local-
interpolation and nonlocal-interpolation, with a fixed tier each.

## v7.57 — one interpolation was three different claims, and 160 signatures became 5

Step 4, and the first release in which a tier moves.

`INTERPOLATED_CURVE_INK` covered 160 of publication 397's 180 cells at R3. As a
review tier that is useless: cell-level confirmation would have asked a reviewer
for **160 signatures, 121 of them for the reader stepping over its own
three-pixel error-bar stem.** A confirmation that fires on almost everything is
the checkbox people learn to click — the same failure the review warned about for
`Inference_Checked` on every panel, one level down.

Two independent questions, both measured on the row since v7.55/56:

    was the gap OURS?   the furniture this reader removed over EVERY column of
                        it, or NONE (the figure drew nothing there) or MIXED
                        (partly explained, which is not explained)
    was it LOCAL?       the span against THE FIGURE'S OWN DRAWING SCALE

    Value_Method                      tier   397 cells
    DIRECT_CURVE_INK                  R0             6
    RESTORED_MASKED_FURNITURE         R1           121
    RESTORED_LINE_PATTERN_GAP         R1             0
    LOCAL_BRACKETED_INTERPOLATION     R3             5
    NONLOCAL_INTERPOLATION            R4            34
    EXTRAPOLATED_CURVE_INK            R4            14

    tiers   R0 6 | R1 119 | R2 2 | R3 5 | R4 48   of 180
    cell-level signatures   160 -> 5
    finalizable             132 of 180

**Locality is `span <= max(stroke, dash_gap)`, and it is the third rule tried.**
The first two were measured and thrown away:

* `span <= stroke + occlusion_width` passes **160 of 160**, MIXED included,
  because the span between two supports IS the occluded columns plus one.
  Arithmetic, not evidence.
* a fraction of the position spacing is blunt: `< 0.25 * spacing` admits 144 and
  `< 0.5 * spacing` admits 147, including 23 and 24 of the 31 unattributable
  ones.

Against the drawing scale it admits all 121 stem restorations, **none of the 8
gridline gaps**, and 5 of the 31 MIXED. Both references are measured on the
figure, so it says the same thing at any rendering — a pixel constant would have
made the answer depend on the DPI somebody rendered at.

**Locality beats provenance.** A gridline is furniture this reader removed, and a
22-pixel gridline gap is still a guess about a curve nobody sampled. Six of the
eight gridline gaps reach past half the distance to the next datum; not one stem
gap does.

**48 cells are now R4 and cannot be finalized at any signature.** That is the
honest cost of the split, and on 397 it changes no outcome — the paper never says
whether its error bars are SD or SEM, so nothing was poolable anyway. On a paper
that does say, those 48 would have pooled silently before this release.

Two scenarios were written too strongly and corrected: "every stem gap is
restored furniture" failed on the fixture's own widest stem gap, correctly — a
stem that hides more than the curve's own width is not a stroke you can put back
either. Conditioning on the reach tests the rule instead of the fixture's
accidents.

    reverted                                        scenarios that fail
    the split not being applied                      5
    locality not beating provenance                 10
    a partly explained gap counting as furniture     1
    restored furniture priced as a cell review       2
    a nonlocal interpolation being finalizable       3

Still no gate reads a tier, and the value file still carries none of this.

## v7.58 — the answer no longer depends on which way the panel was swept

Step 5. The reader sweeps every panel twice, forward and backward, so a curve
missed at the first position still has a neighbour to be carried from. The two
traces were then concatenated and the first candidate within `_SAME_CURVE_PX`
won.

That was harmless while both directions returned only a y. **Since v7.53 they
also return how the number was got**, and on 397's twelve line panels, of 2472
same-position pairs:

    19  name a different Value_Method   (forward EXTRAPOLATED span 1 against
                                         backward INTERPOLATED span 21)
    49  differ on the span
    34  differ on the value by > 0.5 px
     2  differ on the value by > 2 px

Forward is the more conservative in **all 19**, so nothing the reader emitted was
wrong. That is luck, not a property: 19 to 0 on one publication is not a
guarantee about the next one, and a reader whose evidence depends on a loop
direction cannot be reasoned about at all.

**The value comes from the mode, the provenance from the worst case.** A cluster
is not a pair — several seeds converge on one curve, and between two curves a fit
sometimes lands on neither. The first version of this took the most conservative
member of the whole cluster, and at 5:30 on the MEN panel, where the curves sit
at rows 169 and 182 with spurious fits at 173 and 177 between them, that moved
the value onto a fit that traced nothing and **cost the position both its cells**.
Found by diffing the old and new merge cell by cell rather than by comparing
totals. So: cluster by sorted y, take the position the most members agree with,
and price it by the weakest claim among the members that agree.

**A disagreement between the sweeps is not a sweep producing extra fits.** If the
mode is a position only one sweep reached and the other put a candidate further
from it than the stroke is thick, the two are not reading the same stroke; the
position loses the cell rather than taking one of two readings for a reason that
amounts to loop order.

`_merge_traces(f, b) == _merge_traces(b, f)`, and which sweep won is dropped from
the answer — left on, it was the one field that still differed when the lists
were handed in the other way round, which would have made the equality this
function exists to provide true of everything except itself.

**397 is unchanged**: 180 cells, the same methods, the same tiers. Two cells now
record `CONSERVATIVE_OF_CONFLICTING_TRACES` in `Trace_Agreement`. The release
buys determinism, not a corrected number, and saying otherwise would be
overselling it.

Two of the five reverts were silent at first and are worth recording:

* every new scenario called `_merge_traces` directly, so **none of them noticed
  the panel reader going back to concatenate-and-keep-first** - the same gap that
  let an aliased blind mask pass in v7.55. There is now a wiring scenario that
  counts the calls.
* taking the value from the mode rather than from the conservative member is a
  difference of at most `_MODE_PX`, and the first scenarios for it happened to
  use a cluster where the two coincide. Sharpened until a revert fails.

    reverted                                       scenarios that fail
    first-wins, the way it was                      1
    the conservative pick                           2
    the value coming from the mode                  1
    the sweep-disagreement refusal                  1
    the direction left on the answer                1

## v7.59 — a tier is derived by whoever needs it and written down nowhere

Step 6, and the smallest release of the six.

`line_style_mono` wrote `Review_Tier` onto every row it emitted. The comment
beside that line said the tier is derived **so that nothing in a file can declare
its way to a weaker check** — while writing it into the row that becomes the file.
Nothing read it, so nothing was wrong yet; the moment it reached
`figure_values_*.csv` and a finalizer trusted it, the principle would have been
gone and the code would still have claimed it.

`provenance.review_tier(Identity_Method, Value_Method)` is one call. The overlay,
the gate and the finalizer each make it themselves. **A derived value that is also
stored is two answers to one question, and the stored one is the one somebody can
edit.**

**The guard is a source scan, not a check on one reader's output**, because the
readers that have not been written yet are the ones it has to hold for. Every
non-test module in the package is parsed and searched for a tier put INTO a
record — as a keyword argument, as a dict key, or as a subscript assignment. Three
synthetic modules prove the scan can see each of those three forms, and a fourth
that derives a tier instead proves it does not flag the correct pattern. A guard
that cannot fire is the shape this package has caught itself in twice now
(v7.51's field whitelist, v7.55's aliased blind mask).

Scenarios that read the tier off the row now derive it. `pilot_397` is unchanged.

    reverted                                       scenarios that fail
    the tier written back onto the row              2, in two suites
    the scan not looking at keyword arguments       1

That closes the six steps of the provenance programme as it was proposed. What is
still not done, and is the whole point of the next round: **no gate reads a tier.**
`Identity_Method` and `Value_Method` stop at the reader row, the R2 panel
confirmation and R3 cell confirmation do not exist, and an R4 value is refused by
nothing but arithmetic in a docstring. On 397 that is 48 cells whose numbers a
model made, which the pipeline would pool today if the paper had said SD or SEM.

## v7.60 — the two questions reach the grain that gets pooled

Step 7 of the review's order, and the first half of the thing the last six
releases were for: **no gate can read a tier that is not in the file.**

`Identity_Method` and `Value_Method` are now in `MARK_CARRIED` and in
`fig_values_columns()`, so `to_value_records` copies them and every value row in
`figure_values_raw.csv`, `figure_values_machine_qc.csv` and
`figure_values_accepted.csv` carries them. **The tier is not there**: it is
derived from the two by whoever needs it, which is what v7.59 was about.

Universal on purpose, and safe to make universal before every reader can answer:

    blank means "this reader does not say", and `provenance.review_tier`
    prices blank at R4 - the highest tier, not the lowest

so the two columns can only ever make a value HARDER to pool than it was before
they existed. An unregistered method is not evidence of safety. Only
`LINE_MONO_STYLE` fills them today; `BAR_MONO`, `LINE_MONO`, `LINE_COLOR`,
`SCATTER` and `BOX_VIOLIN` leave them blank, and that is visible in the file
rather than absent from it.

On publication 397 the values file now carries, per row, enough to derive:

    R0  2 | R1 55 | R2 2 | R3 2 | R4 62     of 123 rows

**62 rows a gate would refuse**, and nothing refuses them yet.

A scenario had to be corrected rather than satisfied. `test_mark_readers` asserted
that every field in `MARK_CARRIED` reaches the value row; with two fields added
that only one reader fills, that turns "the adapter drops nothing" into "every
reader answers everything" - a different and untrue claim. It now asserts what the
reader actually emitted, plus a case where a reader does name its methods, plus
that blank is priced at R4.

`figure_values_TEMPLATE.csv` is regenerated from the column function, which
`test_grid_engine` pins against each other.

    reverted                                        scenarios that fail
    the methods dropped from MARK_CARRIED            1
    the columns dropped from the values schema       3, in two suites

Next, and last: the gates. R2 wants a panel confirmation, R3 wants one per cell,
R4 wants refusing outright - and on 397 that last one is 62 rows whose numbers a
model made.

## v7.61 — an approval cannot buy a number a model made

Step 8, and the first gate that reads a tier. R4 only; R2 and R3 need a review
channel that does not exist yet.

`finalize` now prices every approved value with
`provenance.review_tier(Identity_Method, Value_Method)` and **refuses the ones no
signature can finalize**: the fitted curve produced the number, or the nearest
observation was carried sideways with nothing bracketing it. A reviewer looking at
an overlay cannot tell a fitted y from a read one — that is exactly what the
picture cannot show — so an APPROVED decision over such a value is a signature on
something nobody could have checked.

**It refuses values, not approvals.** The panel still finalizes; the blocked cells
do not reach `figure_values_accepted.csv`, and the stamp says how many:

    Values_Method_Blocked     refused because the number was not read off the ink
    Values_Method_Unstated    could not be asked, because their reader does not
                              answer these two questions yet

A run that accepted forty of forty is a different artifact from one that accepted
forty of a hundred, and the stamp said the same thing for both. `NOTHING_FINALIZABLE`
is a new status, distinct from `NOTHING_APPROVED`: the second is about the
decisions, the first about the evidence, and whoever reads the stamp needs
different answers to the two.

**A blank pair is not treated as R4 here, and that decision cost a build to
learn.** `review_tier("", "")` is R4, which is right where it is — an unregistered
method must not look safer than a registered bad one. Wired straight into this
gate it refused every value in the package: five of the six readers do not answer
yet, `test_finalize` went entirely dark and `pilot_beckers` would have stopped
reaching POOLING_ELIGIBLE. That is not a safety improvement, it is a shutdown. So
the gate refuses what it KNOWS — a pair that is stated and prices at R4 — and an
absence is counted and flagged (`VALUE_METHOD_UNSTATED`) rather than guessed at in
either direction. When the other readers can answer, the blank case becomes a
block and the count goes to zero on its own.

**The scenarios had to get the methods in legitimately.** Written onto
`figure_values_machine_qc.csv` after the run they trip `RUN_ARTIFACT_MODIFIED` —
the ledger hashes that file, and the first version of the scenario tripped it,
which is the tamper guard working. So the reader is wrapped for the length of one
run and answers the two questions the way a taught reader will.

    reverted                                          scenarios that fail
    the R4 block removed                               2
    blank treated as R4 and blocked too                2
    NOTHING_FINALIZABLE folded into NOTHING_APPROVED   2
    the counts dropped from the stamp                  2
    the unstated gap not flagged                       1

Still open, and now the only thing left of the review's list: **R2 and R3.** A
panel-level `Inference_Checked` and a per-cell `inference_review.csv` with an
exact-set contract against an `inference_manifest.csv`. On 397 that is 2 cells
wanting a panel confirmation and 5 wanting one each — the numbers the split in
v7.57 made small enough to be worth asking for.

## v7.62 — the reviewer is asked about the row heading, not only the marks

R2, the second of the three gates. A cell whose NUMBER came off the ink and whose
SERIES was reasoned to now puts a question in front of the person who signs for
the panel, and the finalizer will not take an approval that does not answer it.

`OVERLAY_INFERRED` is a new `Review_Mode`, chosen when any machine-QC value on
the panel prices at `R2` or `R3`. It needs **no new artifact** — the overlay has
starred those marks and counted them in its footer since v7.51, so the extra
question is one the reviewer can already act on — and it asks for one more
confirmation, `Inference_Checked`, beside `Marks_Checked`.

    Marks_Checked      the crosses sit on the marks a reader would give them
    Inference_Checked  and the starred marks belong to the series their labels
                       name — that series was reasoned to, not measured

Those are different sentences, and only the second one is about how the evidence
was got. The value is measured; the row heading is not, and it is the row heading
that decides which column of the analysis the number lands in.

**A mode, not a fifth question on `OVERLAY`.** The same reason
`BAR_MONO_GEOMETRY_RESOLVED` exists: a confirmation column every panel carries is
a column everybody types `CONFIRMED` into. Panels with nothing inferred are
queued `OVERLAY` and finalize without it, which two scenarios assert.

**Priced from the values, declared nowhere.** The mode is computed from the two
provenance fields the panel's values carry, so a panel cannot opt out of the
question by leaving a column blank. A statedness guard was written for that case
and then removed as decoration: a blank pair prices at `R4`, and `R4` is not a
tier that asks for a confirmation — it is the tier `finalize` refuses outright.
The reason is now pinned by a scenario in `test_provenance` rather than by a
branch nothing can reach.

On publication 397 that is **2 cells in 2 panels** — `P1_FPV_WOMEN` and
`P2_CO_WOMEN` at 0:30, both `COMPLEMENT_OF_DECLARED_STYLES` over
`RESTORED_MASKED_FURNITURE`. Neither panel reaches the queue today, because 397's
dispersion definition is unresolved and no value of its 123 passes machine QC; the
mode is exercised end to end by `test_finalize` instead, over a fixture whose
reader answers the two questions.

`SKILL.md` gains the mode in the table a reviewer reads and the column in the
confirmation paragraph — `test_reproducibility` refuses a mode the skill has not
heard of, because its table ends with "anything else → do not approve".
`value_review_TEMPLATE.csv` is regenerated from `VALUE_REVIEW_COLUMNS`.

    reverted                                          scenarios that fail
    the mode never chosen                              3
    the mode asks nothing extra                        2
    Inference_Checked not an accepted column           1 + 1, in two suites
    R2 not a panel-confirmation tier                   3 + 1, in two suites
    the mode chosen for every overlay panel            1

Still open of the review's list: **R3**, the per-cell confirmation — an
`inference_manifest.csv` derived from the values, an `inference_review.csv`, and
an exact-set contract in `finalize` so every R3 cell carries its own decision.
On 397 that is 2 cells.

## v7.63 — a reconstructed number is answered for by itself

R3, the last of the three gates and the last item on the review's list. A cell
whose NUMBER came from neighbouring ink rather than from ink at the cell now gets
a question of its own, and the panel's approval does not answer it.

`OVERLAY_INFERRED_CELLS` is a third overlay mode, chosen when a machine-QC value
on the panel prices at R3. It requires an artifact the other two do not:
`inference-review/inference__<Panel_ID>.csv`, one row per reconstructed cell,
written by the run and registered in `panel_artifacts.csv` — so the LIST OF
QUESTIONS is inside `Review_Subject_SHA256`. A run that reconstructs one more
cell than the run somebody signed for is `APPROVAL_STALE`, not an extra nobody
was asked about.

`Inference_ID` is content-derived from `(Panel_ID, Unit_ID, Cell_Key,
Identity_Method, Value_Method, Mean, Dispersion_Value)` — not a row number, which
would renumber when a cell is added and move every answer onto a different cell.
The number is in the recipe on purpose: a re-run that reconstructs the same cell
to a different value has not been confirmed.

`finalize_batch.py --template` writes `inference_review.csv` beside
`value_review.csv` with those ids pre-filled, and `finalize` enforces an exact
set over the approved panels:

    MISSING     an unanswered question HOLDS THE PANEL. Nobody said whether they
                looked, and a partial answer does not say which part.
    DUPLICATE   two answers for one cell cannot be told apart in an audit, and
                which one wins would be the order of the rows.
    UNKNOWN     an answer to a question this run did not ask means the person was
                working from a different list of cells.
    REJECTED    an answer, and it costs the CELL. A reviewer who can see that one
                reconstruction is wrong should not have to throw away the
                nineteen values beside it.

That last line is why `Inference_Confirmed` has two values rather than being a
`CONFIRMED`-or-blank column like the four on the panel review. With only
CONFIRMED and silence, a reviewer who spotted a bad interpolation could either
lie or lose the panel. The stamp counts them (`Values_Inference_Rejected`) and
records the per-cell file by content, like the panel one.

**Derived from the values, not read off the ledger.** Which cells need asking
about is recomputed in `finalize` from the two provenance fields, exactly as the
run computed it, and the run's own manifest is then checked AGAINST that set.
Nothing pins a minimum pipeline version, so taking the producer's list would make
an older or tampered run the fail-open case — the same reason
`identity_contract_failures` re-derives its requirement.

On publication 397 that is **2 cells in 2 panels** — `P1_MAP_WOMEN` and
`P1_FPV_MEN`, both at 1:00, both `LOCAL_BRACKETED_INTERPOLATION` over a masked
stretch. Neither panel reaches the queue today (397's dispersion definition is
unresolved), so the contract is exercised end to end by `test_finalize` over a
fixture whose reader answers the two questions, and by two direct calls for the
cases a tampered run would produce — `panel_artifacts.csv` cannot be edited on
disk without `RUN_ARTIFACT_MODIFIED` firing first.

`inference-review` joins `CANONICAL_DIRS`: a previous run's list left in place is
a list of questions about measurements that no longer exist, sitting where the
finalizer looks for this run's. `inference_review_TEMPLATE.csv` ships and is
pinned to `inference_review_columns()` by `test_reproducibility`, and `SKILL.md`
gains the mode, the two-step `--template` flow and the exact-set rule.

    reverted                                            scenarios that fail
    the contract never called                            10
    a missing answer allowed                              2
    a refused reconstruction accepted anyway               2
    two answers for one cell allowed                       1
    an answer to a question nobody asked ignored           1
    the mode never chosen                                  1
    the run writes no list of cells                        6
    the list written but not registered                    6
    the id not derived from the number                     2
    the list not on the cleanup list                       1, in test_run_batch

The review's eight-step order is done. What is left is not the ladder but the
readers: five of the six still answer neither provenance question, so their values
are counted as `VALUE_METHOD_UNSTATED` and no gate can price them.

## v7.64 — five of the six readers now say how they know

The ladder was finished in v7.63 and almost nothing could climb it: only
`LINE_MONO_STYLE` answered the two provenance questions, so every value the other
readers produced arrived at the gate as `VALUE_METHOD_UNSTATED` — counted,
flagged, and priced at no tier at all. This release teaches five of the six.

    reader        Identity_Method                       Value_Method
    LINE_COLOR    MEASURED_COLOUR                  R0   MARKER_CENTER        R0
    LINE_MONO     MEASURED_MARKER_SHAPE            R0   MARKER_CENTER        R0
      shape=ANY,  MEASURED_MARKER_FILL             R0   MARKER_CENTER        R0
      fill=OPEN
      shape=ANY,  DECLARED_SINGLE_SERIES           R1   MARKER_CENTER        R0
      fill=ANY
    BAR_COLOR     MEASURED_COLOUR                  R0   BAR_OUTLINE_CENTER   R0
    BOX_VIOLIN    DECLARED_SINGLE_SERIES           R1   BOX_GEOMETRY         R0
    SCATTER       MEASURED_COLOUR / DECLARED_       R0   POINT_CLOUD_         R0
                    SINGLE_SERIES, per point       R1     ASSOCIATION
    BAR_MONO      — not yet —

**What each reader may claim is fixed by what it actually compared.** A mask built
from a colour the manifest declares, matched at the mark, is `MEASURED_COLOUR` —
`MISSING_SERIES_DISCRIMINANT` is what makes that true of every `LINE_COLOR` and
`BAR_COLOR` series, because the manifest cannot decline to say what colour a
series is. `LINE_MONO` with `Marker_Shape=ANY` is the interesting one: the shape
was NOT a discriminant, so what remains depends on the fill. Declared `OPEN` or
`FILLED`, the candidates were filtered on a fill this reader measured, and the
identity is measured. Declared `ANY` as well, nothing about the mark was compared
with anything — `DECLARED_SINGLE_SERIES`, which is R1 and not R0.

`BOX_VIOLIN` is R1 for its identity however carefully its quartiles are measured:
the reader takes no series at all, reads one five-number summary per declared x
position, and whichever series the cell belongs to was declared for the whole
panel.

**`POINT_CLOUD_ASSOCIATION` is a new value method**, R0, and it exists because a
scatter's cell is not a mark. Each point is a measured marker centre; the value is
an r, a rho or a tau over the set of them. The points carry how their series was
named — `_scatter_outcome` reads it off them rather than re-deciding, so the value
row and its point file cannot disagree — and no per-point value method is emitted:
it would be true, carried nowhere, and consumed by nothing. Whether the reader
found ALL the study's points is a different question, gated by
`Point_Count_Agreement` and `Overplotting_Possible`, and a panel that fails them
produces no association rather than one at a worse tier.

Measured on the real monochrome figure the package ships: ID 386's HR panel reads
**13 of 13 cells as `MEASURED_MARKER_SHAPE` / `MARKER_CENTER`, all R0**, where
before every one of them was unstated. Publication 397 is unchanged at 87 stated
of 123 — its other 36 rows are `BAR_MONO`, the one reader still to be taught.

**Two scenarios had to be rewritten rather than satisfied**, both for the same
reason and both worth keeping as a pattern. `test_run_batch` asserted that every
value row in its fixture leaves the two columns blank, and `test_finalize` got its
blank case by simply running a fixture whose reader answered nothing. Both were
claims about WHICH READERS HAPPEN TO BE UNTAUGHT, so both went red the moment one
was taught — and would go red again on every future release that teaches another.
What replaces them is what has to hold regardless: a reader answers for every mark
it reads or for none of them (a half-answering reader would put blanks beside
methods and price its panel at R4 for a reason nobody could see), no reader may
emit a method the registry has not heard of, and the blank case is now PRODUCED by
a wrapper that strips the two keys rather than inherited from whichever reader is
behind.

    reverted                                          scenarios that fail
    LINE_COLOR silent again                            1 + 2 + 1, in three suites
    the ANY branch claiming the shape was measured      2
    a pure declaration priced as a measurement          1
    BOX_VIOLIN claiming a measured identity             1
    a black scatter claiming measured colour            1
    the association priced as one marker centre         1, end to end
    the per-point value method back                     2
    BAR_COLOR silent again                              1
    POINT_CLOUD_ASSOCIATION out of the registry         1 + 1, in two suites

## v7.65 — the last reader, and the question follows the values rather than the mode

Two halves, and the first forced the second.

**`BAR_MONO` answers now, and it has two answers.** `fill_identity` names a
figure's series in two passes, and they are not the same claim. A COMPLETE group —
every slot yielded a fill — is assigned from relations between samples measured in
that group, which is `MEASURED_FILL_RELATION` (R0). An INCOMPLETE group's
remaining samples are matched against prototype ranges formed in OTHER groups of
the figure: same answer, evidence one step further away, and that is
`FIGURE_PROTOTYPE_MATCH` (R2). A bar a person named in
`identity_resolution.csv` is `HUMAN_RESOLUTION` (R0) — not because a person cannot
be wrong, but because it is the strongest evidence the ladder has and there is no
further signature to ask for. Every BAR_MONO value carries
`BAR_OUTLINE_CENTER`.

The route is decided where the assignment happens, carried in the verdict — so it
is inside `Domain_Identity_SHA256`, and two figures that reach the same pattern by
different routes no longer share a bundle — written onto the record by
`fill_identities_by_figure`, and copied onto the mark by `_geometry_marks`. It is
in `UNHASHED_FIELDS` beside `resolved_fill_pattern`: written by identity, not by
measurement, so a human resolution arriving later must not move the hash that
answers "is this the same measurement".

**Publication 397 now states all 123 of its 123 rows.** Before v7.64 it stated 87;
before v7.60, none.

    R0  38   R1  55   R2  2   R3  2   R4  26

**And that broke the shape of the R2 gate, two releases old.** `OVERLAY_INFERRED`
and `OVERLAY_INFERRED_CELLS` were modes whose required artifacts were the ordinary
overlay's; what they actually carried was one extra question. That works until a
panel reviewed some other way holds an inferred cell — and teaching `BAR_MONO`
made exactly that panel, because a short bar with no fill leaves its group
incomplete and the bars beside it are then prototype-matched. Those panels are
queued `BAR_MONO_GEOMETRY`, where no overlay-shaped mode name reaches them. The
alternative was a combinatorial table: two geometry modes times inferred-or-not.

So the two modes are gone and the question follows the evidence.
`RB.inference_confirmations(values)` returns `("Inference_Checked",)` for a panel
whose own values price at R2 or R3, `finalize` adds it to whatever its mode
declares, and it composes with every mode there is or ever will be. This is the
shape `identity_contract_failures` already used for `IDENTITY_EVIDENCE`, for the
reason recorded there: the condition is in the rows, so the check reads the rows.
The R3 half needed no change at all — `inference_contract_failures` already
required `INFERENCE_MANIFEST` of a panel whose VALUES hold a reconstructed number,
and no review mode ever named that artifact.

The reviewer still has to be told, so the queue gains `Inference_Cells`: how many
of this panel's cells were reasoned to rather than measured. Informative, and
re-derived by the finalizer — a queue that could lower its own requirement by
printing 0 would be a requirement in name only.

    reverted                                            scenarios that fail
    the prototype route claiming the measured one        2 + 3, in two suites
    the route never written onto the record              1 + 3
    the mark dropping the route                          3
    a human resolution not named as one                  1
    BAR_MONO silent about its value                      3
    the question never asked of anybody                  1 + 3
    the finalizer asking only what the mode declares     1 + 2
    the queue not telling the reviewer                   1 + 2
    the route inside the row hash                        2 + 1

All six readers now answer both questions. What is left is not a reader but a
grain: `Dispersion_Method`.

## v7.66 — three holes in the producer-independent contract

All three were raised in review against v7.65, and all three are the same shape:
a check that is strict about what this package produces and lenient about what
something else might.

**A blank pair no longer buys a signature.** v7.61 blocked a value only if its
method pair was STATED and priced at an unfinalizable tier. `review_tier("", "")`
has always been R4, so a row with no methods at all — or with one of the two —
was counted, flagged and accepted. That exception was correct exactly once: five
of the six readers answered neither question, and blocking blank would have
refused every value in the package. It was written down as temporary in as many
words, and v7.64 and v7.65 discharged the condition — 397 states 123 of 123, the
count went to zero on its own. What the exception protected at the end was not
this package's output but an older producer's, a hand-built values file, or a
reader with a typo in a column name. A provenance gate that waives itself
whenever the provenance is missing is the one shape that cannot be
producer-independent.

Half-blank is blank: `review_tier` prices the pair, not the better half. The
refusals are per cell, coded `VALUE_METHOD_UNSTATED` rather than
`VALUE_METHOD_NOT_FINALIZABLE` — "nothing says how this number was got" and "this
is how, and it is not enough" are different findings. And the counts now travel
with a `NOTHING_FINALIZABLE` stamp, which used to report
`Values_Method_Blocked: 0` after refusing everything.

**`Inference_ID` binds the evidence, not just the answer.** It hashed the cell,
the two methods, the mean and the dispersion — the OUTPUT. Output and evidence
move independently: a re-run whose supports shift from 101–104 to 96–109 and
whose occlusion goes from `ERRORBAR_STEM` to `MIXED` can land on the same mean,
and over a few pixels of a smooth curve that is not much of a coincidence. The id
was then unchanged, and a cell confirmation given against the first
reconstruction attached itself to the second. The panel's
`Review_Subject_SHA256` does go stale — but the two files are filled in by
different people at different times, and nothing made the cell answer expire with
the panel one.

The recipe is now every column of the row the reviewer reads —
`INFERENCE_IDENTITY_FIELDS` is derived from `INFERENCE_MANIFEST_COLUMNS`, so a
column added to the manifest enters the identifier by construction — plus
`Trace_Agreement`, which the manifest now carries. Every field has to be one the
VALUE ROW carries, because `finalize` re-derives these identifiers from
`figure_values_machine_qc.csv` rather than trusting the manifest; that is why the
raster hash is not in it, and the panel signature covers the raster anyway.
Numbers are canonicalised through `float`, because the run derives these in
memory and the finalizer derives them again from a CSV.

**An occlusion cause the registry cannot name is a defect, not a tier.**
`interpolation_method` tested for `NONE` and `MIXED` and returned the FURNITURE
answer for everything else, so `ERROR_BAR_STEM` for `ERRORBAR_STEM` — one
character — would have priced an unexplained gap at R1, the tier that asks for no
signature at all. Everywhere else in `provenance.py` an unregistered token costs
the HIGHEST tier; the token these methods are DERIVED FROM had the opposite rule.
`OCCLUSION_CAUSES` is now the one vocabulary, `line_style_mono.BLIND_CAUSES` is
built from it rather than spelled again, and an unrecognised cause raises — a
reader that emits one is a defect in a reader, and this package already stops the
batch for those rather than mis-reading 115 more publications quietly.

    reverted                                          scenarios that fail
    the blank exception back                           4
    half-blank counted as stated                       1
    the counts dropped from the refusal stamp          3
    the id binding only the answer                     9
    no canonical spelling for a number                 1
    an unknown cause read as furniture                 5
    the reader spelling its vocabulary again           1 + 1, in two suites

Still open from the same review, and neither is a pooling-safety defect: a
refused R4 cell is not routed to anybody as a durable work item, and an R3
reviewer has pixel numbers rather than a picture of the two supports.

## v7.67 — a refused value is somebody's work, and a reconstructed one has a picture

The two items the review left open, and a defect found while closing the first
of them.

**v7.66's `Inference_ID` was bound to eight columns the value row did not carry.**
The recipe named `Value_Span_Px`, the two supports, the occlusion cause and width,
the stroke, the dash gap and `Trace_Agreement`, and the comment beside it said
"every field must be one the VALUE ROW carries, because `finalize` re-derives
these identifiers from `figure_values_machine_qc.csv`". Nothing checked that it
was true. Those eight lived on the reader's mark row and stopped there, so every
one of them hashed as the empty string and the identifier still bound only the
answer. The unit scenarios passed because they call `inference_id` with the
fields in hand — arithmetic, not evidence, and the same defect as v7.51's field
whitelist, found the same way: by opening the artifact and looking at it.

`INTERPOLATION_CARRIED` now carries the eight into the value row, as
`IDENTITY_CARRIED` does for the BAR_MONO identity fields and for the same reason
— only a reader that reconstructs a number HAS them. The value schema is 81
columns, and publication 397's two R3 cells now read, in the file:

    P1_MAP_WOMEN  1:00  span 4 px  supports 647-651  MIXED  stroke 2  AGREED
    P1_FPV_MEN    1:00  span 3 px  supports 137-140  MIXED  stroke 6  AGREED

**Every cell asked about by name now has a picture of itself.**
`inference-review/context__<Panel_ID>__<Cell_Key>.png` is a 3× crop of the
stretch of figure between the two supporting columns: each support drawn in blue,
the column and row where the value was placed in red, and the method, span,
supports and cause in the caption. A value sitting outside its own supports is
the defect it exists for.

Drawn in the panel loop, because that is the only place holding the raster, the
panel box and the mark's own pixels at once — the value row keeps the support
columns but not the row the value sits on, and the manifest is written after the
grid gate, by which point the image is closed. Registered against the
`Inference_ID` when the manifest is written, using `Artifact_Reference`, which
exists for exactly this join: `IDENTITY_EVIDENCE` is registered against its
`Resolution_ID` the same way. Keyed by cell rather than by id in between, because
the id depends on a value the grid gate may still reconcile.

`finalize` refuses a panel whose reconstructed cell has no crop
(`INFERENCE_CONTEXT_MISSING`). A reader that claims a bracketed interpolation
without saying which columns bracket it cannot be pictured, and a per-cell
confirmation against pixel coordinates nobody can see the figure behind is the
signature on a filename this package refuses everywhere else.

**And a refused value is work, at run time.** `method_blocked_cells.csv` is
written by the RUN — one row per machine-QC-passed cell no signature will be able
to finalize, with `Cell_State=MODEL_ESTIMATE_ONLY`,
`Next_Action=MANUAL_REDIGITIZATION`, the two methods, the cell key and the raster
to re-read it from. `Values_Method_Blocked` on `run_stamp.json` is the count, so
it is known before an afternoon is spent reviewing rather than after. The panel
still goes to the queue: its other cells stand, and the picture is still what
says so.

A separate file rather than rows in `manual_queue_cells.csv`, because the claim
differs at both grains: that queue is cells a reader could not read, on panels
that went to a person; these are cells a reader DID read, on panels that passed,
whose numbers a model made. Filing them together would put panels in the manual
queue that nobody needs to digitize by hand.

    reverted                                          scenarios that fail
    the evidence off the value row                     1
    no room for it in the value schema                 2 + 1, in two suites
    no picture drawn                                   2
    the picture drawn and not registered               2
    the finalizer not asking for one                   1
    a refused value becoming nobody's work             1
    the count off the run stamp                        1
    the work list surviving a re-run                   1

## v7.68 — a method is a claim about evidence, and the evidence gets a vote

Blank methods are refused and unregistered ones price at R4, so the remaining way
to buy a cheap tier is to write down a REGISTERED method that is not the one the
evidence supports:

    actually FIGURE_PROTOTYPE_MATCH        written MEASURED_FILL_RELATION   R2 -> R0
    actually COMPLEMENT_OF_DECLARED_STYLES written MEASURED_LINE_STYLE      R2 -> R0
    actually FIT_FALLBACK                  written DIRECT_CURVE_INK         R4 -> R0

Every hash in such a run is correct. The values were written that way by whoever
produced them, and re-hashing catches edits made AFTER a run, not a producer that
was never honest. Two checks now stand between that and the accepted file.

**The pair against the reader.** `provenance.METHOD_CONTRACT` says which
(identity, value) pairs each mark type produces — `LINE_COLOR` produces exactly
`MEASURED_COLOUR`/`MARKER_CENTER`, `BOX_VIOLIN` exactly
`DECLARED_SINGLE_SERIES`/`BOX_GEOMETRY`, `LINE_MONO_STYLE` the cross of three
identities and nine value methods. A pair outside its reader's set did not come
from the reader the queue says read it, and `finalize` withholds the panel
(`METHOD_NOT_POSSIBLE_FOR_READER`). A mark type the table has not heard of is not
an error: adding a reader should not be a two-file change with a failure in the
middle.

`HUMAN_RESOLUTION` is checked the other way round. It is R0, and the only thing
that makes it R0 is that a registered person signed a resolution row with
evidence behind it — so it must arrive with `Identity_Source=HUMAN` and a
`Resolution_ID`, which `identity_contract_failures` then joins to the resolution
and its evidence file.

**The pair against the evidence.** A pair the reader COULD have produced still
has to be the one THIS row's evidence supports, and only a durable artifact can
say. `BAR_MONO` now has one: `mono_bar_geometry.csv` carries
`Auto_Identity_Method` per row, inside `Auto_Identity_SHA256` — so the two routes
are distinguishable in the file the figure wrote, and a value claiming it read a
bar's fill in relation to its own group, for a bar the figure named by matching
another group's prototypes, is refused (`METHOD_CONTRADICTS_GEOMETRY`). The
column is restored on read-back, because a reader that dropped it would recompute
a different attestation and report every row of every file as tampered.

**What this does not do**, and the honest boundary is worth writing down: the
other five readers have no artifact comparable to the geometry file, so for them
the contract is the matrix and nothing more. A `LINE_MONO_STYLE` row claiming
`DIRECT_CURVE_INK` for a number a fit produced is inside its reader's set and
passes. Closing that needs a durable per-mark artifact — the raw marks JSON is
one, and joining values to it is the next step of this idea.

**The fixtures had to stop lying too.** Five scenarios declared a `LINE_COLOR`
panel and had it claim `MEASURED_LINE_STYLE` with a fit fallback, which is
exactly the pair the new gate exists to catch — so they now declare the panel
`LINE_MONO_STYLE` and a named stand-in reads the fixture's coloured marks in that
reader's place. The marks are still real, still calibrated, and still travel
through `to_value_records` and the grid gate; only the reader's name changed, and
it changed to the truth.

    reverted                                          scenarios that fail
    the contract never called                          2
    every pair possible for every reader               3
    HUMAN_RESOLUTION with nothing signed behind it     1
    the route off the geometry artifact                the artifact refuses itself
    the route written but not attested                 1
    the value's route never compared with the figure   1

## v7.69 — the picture reads the same vocabulary the gate does, and two colours have to be two colours

**The overlay was starring one reader's field.** `line_style_source` marks a
LINE_MONO_STYLE series named by elimination and says nothing about a BAR_MONO bar
named against another group's prototypes, or about a NUMBER that was interpolated
rather than read — both of which the ladder prices exactly as it prices the
first. So a panel could be asked for `Inference_Checked` while its picture showed
nothing to check.

The overlay now derives the tier from the two fields every reader answers, and
marks three different questions differently:

    *  the SERIES was reasoned to; the number is measured        R2
    +  the NUMBER was reconstructed from neighbouring ink        R3
    x  no signature can finalize this value at all               R4

with a footer line for each, naming `inference_review.csv` and
`method_blocked_cells.csv` where those are what the reviewer does next. ASCII,
because the default bitmap font is what is installed everywhere and a dagger that
renders as a box is worse than a plus. The reader-local field stays as the
fallback for a row that answers neither question.

**And the suffix check was case-sensitive.** `PROVENANCE_SUFFIXES` is lower case
and `Identity_Method` is not, so the two fields the overlay now reads were
themselves "provenance this overlay cannot read" — every mark in every panel
would have carried a question mark the moment a reader answered them. Case-folded,
with the two shared fields registered as known.

**The BAR_MONO row crop names the route.** That crop is the whole evidence a
BAR_MONO reviewer has, and its panel is asked for `Inference_Checked` precisely
because some of its bars were named against another group's prototypes. The
caption is now a function (`row_caption`) so what the picture says can be
asserted without reading pixels back out of a PNG — the route was added to it
once and nothing could tell whether it was there.

**Two colours that cannot be told apart do not name two series.** A colour reader
builds one mask per series — every pixel within `Colour_Tolerance` of the declared
hex — and reads each on its own. Two colours closer than the sum of their
tolerances put one printed mark in both masks, and the grid then comes out
COMPLETE with two series holding it: no cell missing, no count wrong, one number
under a series that was never there. `SCATTER` has measured this since it
shipped; `LINE_COLOR` and `BAR_COLOR` did not.

Two layers, because neither is enough:

    the manifest    two declared colours whose distance is no more than the sum
                    of the tolerances they will be read at -> SERIES_COLOURS_OVERLAP,
                    refused before a raster is opened
    the raster      the reader counts how many OTHER masks claim each mark it
                    found, and the batch layer drops the contested ones - the
                    cell goes missing, the panel is refused by the gate, and it
                    is queued for a person

The manifest arithmetic is complete for declared colours (a pixel in two masks
needs the centres within the sum of the tolerances), so the raster check is the
one that reaches `Mask_Key`, where two BUILT-IN masks overlap and no declared
colour exists for the arithmetic to refuse — `dark` covers a blue bar's outline.

Writing that check surfaced a drift it exists to prevent: it hard-coded 60.0
while the line reader was using 70.0, so a validator would have been checking a
figure the run does not read. `COLOUR_TOLERANCE_DEFAULTS` is now one table, per
mark type, that `run_batch` reads too, and the check resolves the tolerance in
the order the run does: series, then reader config, then default.

**And a QC failure stopped erasing the reader's reason.** The gate overwrote the
panel's `Detail` with its own, so a panel whose marks two colours claimed
reported `FACTORIAL_CELL_MISSING` and nothing about the colours — the cell went
missing for a reason the run had measured and then discarded. The two are
appended now: the gate says which check refused the unit, the reader says what
happened to the panel.

    reverted                                          scenarios that fail
    the overlay reading one reader's field only        3
    the footer silent about the tiers                  1
    the suffix check case-sensitive again              1
    the crop hiding the route                          1
    the manifest allowing colours that overlap         2
    the line reader not measuring the overlap          1
    a contested mark kept                              3

## v7.70 — the weight has provenance too, and two entry points stop disagreeing

**`Dispersion_Method` is the third axis.** The two that existed are both about the
MEAN. In a continuous meta-analysis the DISPERSION is often what decides the
weight, and a cell whose mean came straight off the ink and whose error bar was
read from a cap no stem connects to it priced R0 twice and went into the pool with
a weight nobody had examined. `Errorbar_Stem_Confirmed` is a boolean about one of
those cases and says nothing about the rest.

    DIRECT_CONNECTED_CAP     R0   a cap this reader followed a stem to
    DIRECT_BOUND_PAIR        R0   an interval drawn as two ends
    DIRECT_BOX_GEOMETRY      R0   the box's own quartile lines
    SOURCE_TRANSCRIBED       R0   copied from the paper, not measured
    UNSTEMMED_CAP            R3   ink at the right distance, nothing joining it -
                                  a cap, or a significance glyph, which sits
                                  exactly where a cap is and is the same colour
    RESTORED_MASKED_CAP      R3   restored across furniture this reader removed
    INTERPOLATED_DISPERSION  R3   from neighbouring cells, not this one's ink
    FITTED_DISPERSION        R4   a model produced it
    NO_DISPERSION            R0   this cell has none, and says so

`NO_DISPERSION` is R0 because nothing is claimed — whether a value without a
weight may be pooled is the unit's question and `NO_VARIANCE` already answers it.
A blank BESIDE a dispersion number is R4, the same rule the other two axes
follow. All six readers answer the new question; nothing emits
`FITTED_DISPERSION` or `RESTORED_MASKED_CAP` yet, and `DISPERSION_CONTRACT` says
so per reader rather than leaving the registry to imply otherwise.

**`row_tier(row)` is the question every gate now asks** — the worst of the three
axes, with "does this row have a dispersion at all" read off the row rather than
declared. Wiring it revealed that the runner and the finalizer had come apart: the
runner priced the per-cell queue on three axes and `finalize`'s exact-set contract
still priced it on two, so a cell that reached R3 through its error bar was asked
for no confirmation. A five-number summary's quartiles count as a dispersion, or a
box panel would skip the axis entirely.

The R3 CONTEXT CROP is required only where the NUMBER was reconstructed: the crop
pictures the two columns a value was interpolated between, which a cell that is R3
because of its cap does not have. Its evidence is the whisker on the panel
overlay, and demanding a support crop for it would refuse a panel for the absence
of a picture that cannot be drawn.

Publication 397 states the third axis on all 123 rows — 47 connected caps, 76
`NO_DISPERSION` — and its tiers are unchanged, which is what a new axis should do
to a corpus that was already honest about its error bars.

**`read_panel("BAR_MONO")` refuses instead of answering differently.** It
dispatched to the single-panel absolute-band reader while the pipeline read the
same panel in two passes through `mono_bar_geometry` — a different fill
vocabulary, no STIPPLED support, no identity route, no durable geometry row. An
agent reaching for the obvious entry point got a different answer from the
pipeline and nothing said so. It now raises `UnsupportedCapabilityError` naming
`geometry_rows`, `fill_identities_by_figure` and `run_batch`;
`read_monochrome_bar_panel` keeps its own name for diagnostics.

**The scatter point file records how its series was named.** The reader names each
POINT and the association row copies the answer; until the durable file carried
it, a summary claiming `MEASURED_COLOUR` over a cloud read from a grey threshold
could not be refuted from the artifact. Schema `/3`, one agreed method on the
record (empty where the points disagree), and `finalize` compares the row against
the cloud it cites (`METHOD_CONTRADICTS_POINTS`).

    reverted                                          scenarios that fail
    a blank spread priced safe again                   3
    the row priced on the two mean axes                2 + 4, in two suites
    quartiles not counted as a spread                  1
    the marker reader silent about its spread          1 + 1
    the box reader claiming a cap it never followed     1
    the axis off the value row                         1 + 1
    the finalizer pricing the mean                     1
    the per-cell contract pricing the mean             1
    BAR_MONO dispatching to the other reader           2
    the point file forgetting its method               1 + 1
    the association never compared with its cloud      1

## v7.71 — blank evidence is not consent, and the spread is part of the question

Both halves came out of the same review, and both are the same mistake made twice:
a check that compares two answers only when both are present.

**`if said and said != claimed` was the wrong shape.** The two evidence joins
v7.68 and v7.70 added refused an artifact that DISAGREED with a value's claim and
accepted one that said NOTHING — which is the fail-open they exist to close,
arrived at from the other side. Blank evidence does not mean "no reason to doubt
this"; it means the claim cannot be supported.

    the scatter point file  the record-level method is EMPTY BY DESIGN when the
                            points disagree, so a cloud that could not agree how
                            its series was named bought whatever the row claimed.
                            The methods are now re-derived from the points:
                            disagreement is METHOD_EVIDENCE_UNRESOLVED, and record,
                            points and value must all say the same thing
    the geometry file       a row that resolved a pattern and left
                            `Auto_Identity_Method` blank is internally consistent
                            and says nothing. `artifact_row` now refuses to WRITE
                            one (`AUTO_IDENTITY_ROUTE_MISSING`, and
                            `AUTO_IDENTITY_ROUTE_UNKNOWN` for a route the registry
                            cannot price), and the finalizer treats blank as
                            contradiction for a bar that named a pattern

**The spread joins the cell-level question.** `row_tier` has priced the
dispersion since v7.70, and `Inference_ID` did not — so a cell asked about at that
grain BECAUSE of its error bar kept the same identifier when the answer to that
question changed. `UNSTEMMED_CAP` and `RESTORED_MASKED_CAP` are different
questions about the same number. The manifest and therefore the identifier now
carry `Dispersion_Method`, `Errorbar_Lower`, `Errorbar_Upper` and
`Errorbar_Stem_Confirmed`; `method_blocked_cells.csv` carries `Dispersion_Method`
and its `Detail` names which axis refused the cell, so nobody is sent to re-read a
mean that was fine.

**And the overlay stops conflating the two halves of R3.** A row reaches it
because its NUMBER was reconstructed or because its SPREAD came off a cap nothing
connects to the mark, and the footer said only the first — describing a question
the reviewer was not being asked. `~` now marks and counts the spread case
separately from `+`. Registering `Dispersion_Method` as a field the picture can
read was part of the same change: without it every such mark carried a question
mark on top of its own suffix, which the unknown-provenance guard reported
correctly.

**`row_finalizable(row)` is the three-axis helper.** `finalizable(identity,
value)` stays for the scenarios that ask about the mean, with a docstring saying
which question it answers; nothing in the pipeline gates on it.

    reverted                                          scenarios that fail
    a blank point cloud read as consent                2
    the record trusted instead of re-derived           1 + 1, in two suites
    a blank geometry route read as consent             1
    the writer allowing a named bar with no route      1
    the spread off the cell identifier                 1
    the work list hiding which axis refused            1
    the footer conflating the two halves of R3         1
    the third shared field unregistered                1

## v7.72 — a value is joined to the mark it was made from

The method contract was a MATRIX for five of the seven readers: it said which
methods a reader COULD produce and nothing about which one THIS row's evidence
came to. `BAR_MONO` and `SCATTER` had durable artifacts to be checked against;
the rest were joinable to the raw marks only by panel, so a value could carry any
mark's number and any method the matrix allowed.

**`mark-data/2`** (superseded by `/3` in v7.82). Every mark in a panel's
raw-marks file now carries two hashes,
and the value rows carry both:

    Mark_Record_SHA256         WHAT WAS MEASURED - this mark's geometry, under
                               this panel box, this calibration and this raster
    Method_Attestation_SHA256  HOW IT WAS READ - the three methods, bound to that
                               measurement

Two hashes rather than one, for the reason `Geometry_Row_SHA256` and
`Auto_Identity_SHA256` are two: a method corrected later must not move the hash
that answers "is this the same measurement".

`finalize` then checks four things per value — the mark exists in the run, no two
values cite one mark, the three methods equal the mark's EXACTLY (blank included),
and the attestation recomputes from the mark's own fields. Then a fifth, where the
reader has one: **the methods are re-derived from the measurements**.
`expected_line_style_methods` recomputes all three for `LINE_MONO_STYLE` from the
support columns, the occlusion cause and the drawing scale that reader had to
measure anyway — no ink either side is `FIT_FALLBACK` whatever the row says, one
side is `EXTRAPOLATED_CURVE_INK`, and a bracketed span goes back through
`interpolation_method`. `EVIDENCE_VERIFIERS` has one entry today, and the mark
types absent from it are held to the matrix and the join, which is weaker and is
written down rather than implied away.

The fixtures had to stop lying again, in the same way and for the same reason:
five scenarios named a method and recorded no supports, which is now a reader
claiming an interpolation it cannot show. `_style_evidence` writes the
measurements each method rests on, in one place, so a scenario says one thing
rather than two. The picture requirement is still tested — through a crop that
could not be painted, which is the reason it can legitimately be missing.

**`RESTORED_MASKED_CAP` is reserved, and the file says so.** It sat in the
registry and in one reader's contract for a release looking exactly like a
capability, with no emitter and no forward test behind it. `RESERVED_METHODS`
names the five methods that are priced and not yet producible, the contract no
longer claims `LINE_MONO_STYLE` can emit it, and a scenario asserts every
dispersion method is either producible by some reader or reserved — never both,
never neither. What it needs to become a capability is written beside it: cap
masks kept apart instead of one `blind` union, ink on both sides of the covered
stretch, the whole stretch explained by ONE known mask, a restored width inside
the panel's own measured cap widths, and a real figure where that happens.

    reverted                                          scenarios that fail
    the mark join never consulted                      5
    a value citing a mark nothing carries              1
    one mark shared by two values                      1
    the methods not compared with the mark's           1
    the attestation not recomputed                     1
    the methods not re-derived from the evidence       1
    the two hashes collapsed into one                  1
    RESTORED_MASKED_CAP claimed as producible          2

## v7.73 — the derivation met a real figure, and the review got a preflight

**Running the new verifier against publication 397 disagreed with the reader on
9 of its 87 line marks**, and the reader was right. `_ink_at` reports the single
supporting column in BOTH support fields when the ink is on one side only, with
the span measuring how far the value was carried sideways; the verifier read
`left == right` as a direct observation. Nine `EXTRAPOLATED_CURVE_INK` cells —
R4, the tier that cannot be finalized at all — would have been re-derived as
`DIRECT_CURVE_INK` at R0, and the check written to catch a downgrade would have
performed one.

The fixtures agreed with the verifier perfectly, because the fixtures were
written from the same reading of the code. What found it was running the
derivation over a real figure's marks and diffing, which is the only test that
was ever going to.

    no supports at all              FIT_FALLBACK
    one column, span 0              DIRECT_CURVE_INK
    one column, span > 0            EXTRAPOLATED_CURVE_INK   <- the nine
    two columns                     interpolation_method(...)

**`review_preflight.py`** is everything about a review that can be checked
without looking at ink:

    which cells will be asked about, and WHY, in the words of the question
    whether every question has its manifest row and its context picture
    whether the answers are complete - no blank, no duplicate, no answer to a
        question this run did not ask
    where two independent reviewers disagree, cell by cell
    and nothing else: it writes no file and signs nothing

The last line is the point, and a scenario checks it by walking the run directory
before and after. A program that fills in a confirmation is the failure this
package exists to prevent; a program that tells a person exactly which twelve
cells to look at, and refuses to let a bundle reach them half-built, is the part
worth automating. `finalize` refuses a panel for eight different reasons and a
reviewer should meet none of them for the first time after signing.

Measured on 397 for the pilot that has to come next: **5 of 5 line panels hold
both a cell whose cap was followed and a cell where no cap was reachable** — 13
`DIRECT_CONNECTED_CAP` against 74 `NO_DISPERSION`. Some of those 74 are curves the
figure draws no error bar for, and some are caps this reader could not reach.
Telling those two apart is what `RESTORED_MASKED_CAP` needs, and the number says
the case is worth the work rather than assuming it.

    reverted                                          scenarios that fail
    one column read as a direct observation            2
    the preflight not naming what will be asked        3
    the bundle check dropped                           1
    the answer check dropped                           2
    the two-reviewer comparison dropped                1
    the preflight writing into the run                 1

## v7.74 — the mark join reaches the number and the cell, and the mark is checked against itself

v7.72 bound a value's three METHODS to the mark it was made from. It did not
bind the value's NUMBERS or its `Cell_Key`, and it read both of the mark's own
hashes off the artifact instead of recomputing them. Two consequences, and the
first is the one that mattered:

**Two values read the same way in one panel could exchange their marks and pass
every check.** Both hashes existed, neither was shared, the methods agreed
because they were identical, and nothing compared the means. A `Cell_Key`
exchange was worse: every number stays correct, every file hash stays correct,
and the figure now says the treated group did what the control group did. That
is the same failure v7.29–v7.31 runs are withheld for on the BAR_MONO side —
"per-bar hashes and means that agree while their `Cell_Key`s could have been
exchanged, the one failure with no arithmetic signature" — and the five join
readers were still open to it.

So the join now re-derives what the value should have been:

    Mean, Dispersion_Value, Errorbar_Lower/Upper,
    Median, Q1, Q3, Whisker_Lower/Upper       the mark's own, compared as NUMBERS
    Cell_Key                                  the mark's series and position ids,
                                              looked up in the VERIFIED manifests

`MARK_VALUE_FIELDS` is the second half of that table, and a scenario runs
`to_value_records` over a probe mark and asserts that every number the adapter
copies is a number the join checks — the drift `INTERPOLATION_CARRIED` was
written for, guarded this time rather than commented about.

A blank on the MARK side under a number on the value side is a mismatch, not a
skip. A blank on the VALUE side is skipped, because a continuous row does not
carry quartiles and a quantile row does not carry a mean; that asymmetry is
deliberate and is stated in the code.

**And the mark is now checked against itself.** Both hashes are RECOMPUTED from
the mark's own fields before it is indexed, and the index is keyed by the
recomputed value:

    MARK_RECORD_HASH_MISMATCH   the measurement, the calibration or the panel box
                                was changed after the run
    METHOD_ATTESTATION_STALE    a method inside the artifact was rewritten

Until now a doctored measurement whose hash was updated to match it joined
perfectly: the artifact was self-consistent, the value agreed with it, and the
only thing that would have disagreed — the pixels — was not in the comparison.
The record hash covers the panel box, the calibration and the raster hash for
exactly that reason, and it was not being used.

`MARK_CELL_UNDECLARED` is the fail-closed half of the cell check: a mark read as
a series or position the verified manifests do not declare yields no expected
key, so the value is refused rather than compared against a mapping nobody
approved. `cell_maps()` builds that mapping ONCE for both callers —
`value_contract_failures` re-derives the BAR_MONO identity contract from the same
frame — because two constructions could disagree about which level `S2` names,
and a value that satisfied one check against one mapping and the other against
another is the fail-open a shared frame exists to prevent.

Measured on publication 397, which is where a check like this either holds or
produces a wall of false refusals: **all 123 values pass the join clean**, and
the panel holds **23 groups of two or more values read by the same three
methods** — the exact population the method checks cannot tell apart. Every one
of the 23 mark-hash exchanges and every one of the 23 `Cell_Key`-only exchanges
is refused. Before v7.74, all 46 passed.

    reverted                                          scenarios that fail
    the numbers not compared at all                    5
    a blank number on the mark read as consent         1
    the cell key not compared                          3
    an undeclared series skipped instead of refused    1
    the mark's own record hash taken on trust          2
    the mark's own attestation taken on trust          1
    the finalizer not passing the verified manifests   4
    the join not wired into the contract              18
    the cell map built per caller instead of once      4

## v7.75 — the join is mandatory for the readers that have nothing else

Two doors were still open beside the one v7.74 closed, and both were the same
shape: a check that only ran when the producer had made it possible.

**A `RAW_MARKS` artifact written to any other schema was skipped.** The line read
`continue  # an older producer: the join is not there`, so a run written to
`mark-data/1` had no join, no numbers compared and no cell derived, and
finalized on the method matrix alone. `MARK_EVIDENCE_SCHEMA_UNSUPPORTED` refuses
it: the version that cannot be checked is the version that must not be
finalized, and a producer that wants the panel finalized can re-run it.

**A blank `Mark_Record_SHA256` on the value was skipped too**, as "a reader that
does not stamp its marks". That was true of every reader once and is true of
none of the five now, so the blank had quietly changed meaning — from "this
reader has not been taught yet" to "this value opted out of the only evidence it
has". Two rules now:

    PROV.MARK_JOIN_REQUIRED    LINE_COLOR, LINE_MONO, LINE_MONO_STYLE,
                               BAR_COLOR, BOX_VIOLIN - the readers whose raw
                               marks are their ONLY durable record
    the panel is joinable      whatever its type, if this run's own marks carry
                               a record hash then its values must cite one

`BAR_MONO` and `SCATTER` are deliberately not in the first list — they have
`mono_bar_geometry.csv` and the point cloud, joined by hashes that predate the
mark join — but they are caught by the second whenever their marks are stamped,
which they are. The second rule is what makes this a property of the RUN rather
than of a list somebody has to remember to extend.

    reverted                                          scenarios that fail
    an unjoinable schema skipped instead of refused    1
    a blank mark hash read as an exemption             2
    only the five named readers held to the join       1

## v7.76 — the re-derivation is total, and a span of zero is a span

`expected_line_style_methods` returned the axes it could answer and omitted the
rest, and `evidence_failure` compared what it was given. An axis the mark could
not answer for was therefore not a weaker check than one it could — it was **no
check at all**, and from outside it looked identical to agreement. A mark with no
`Errorbar_Stem_Confirmed` bought whatever `Dispersion_Method` the value claimed.

It now returns an `EvidenceVerdict(expected, problems)` and every axis ends with
one or the other:

    line_style_source missing        how the series was named cannot be re-derived
    supports and no Value_Span_Px    a value read off the ink cannot be told from
                                     one carried sideways to it
    two columns, unpriced cause      the interpolation cannot be classified
    Errorbar_Stem_Confirmed missing  how the spread was got cannot be re-derived

and the caller reports them as `METHOD_EVIDENCE_INCOMPLETE` rather than as a
contradiction, because "your evidence says something else" and "your evidence
says nothing" ask a reviewer for different work. `_axes_are_total` asserts the
invariant by dropping each field of a complete mark in turn, so the next axis
added cannot be silent by omission.

**The blank span no longer defaults to `"0"`.** That default was the one-sided
downgrade v7.73 closed, still open from the other side: a mark with a support
column and no span read as a direct observation at R0.

**And taking the default away exposed the bug it had been hiding.**
`str(mark.get(name) or "")` turns the integer `0` into the empty string, and zero
is the most important number this function reads — it is exactly what makes a
support column a direct observation rather than a carry. Every real
`DIRECT_CURVE_INK` mark, whose span `line_style_mono` writes as `value_span or 0`,
was about to be refused as evidence that was never recorded. The fix reads the
field rather than its truthiness; the scenario is a span of literal `0`.

Run against publication 397's figure 1: **all 18 marks derive all three axes,
with no problems and no disagreements** — the totality costs nothing on a figure
whose reader records what it measured, which is the only evidence worth having
that a fail-closed check is not a fail-everything check.

    reverted                                          scenarios that fail
    an axis the evidence cannot answer stays silent    4
    a missing span defaults to zero again              2
    a span of zero read as a missing span              3

## v7.77 — one function decides, and the preflight calls it

`review_preflight` answered overlapping questions in its own code, so it could
report a clean bundle that `finalize` then refused. That is the worst failure a
preflight has: the reviewer trusts it and signs, and finds out afterwards.

`finalize` is now a wrapper. `validate_finalization(run_dir, review_path,
manifest_dir, today, inference_review_path)` does the deciding and returns a
`Verdict(status, detail, problems, approved, keep, blocked, unstated,
inference_rejected, run_stamp_sha)`; `finalize` removes the previous
finalization, calls it, writes the stamp and promotes the accepted file last.
The preflight calls the same function and prints what it says.

Lifting it out meant separating two things that had been interleaved since v6:
the finalizer DELETES the previous accepted file and stamp before it decides
anything, and a decider that still deleted would take a reviewer's bundle apart
every time they asked what would happen. A scenario fingerprints every file
under the run by content — not by name, which misses a rewrite — before and
after both calls.

PARITY IS CHECKED PER MUTATION, because two code paths agree on the happy path
by construction. Eight mutations, each asserting that the preflight's status and
set of refusal codes are the finalizer's:

    a complete bundle                 a rejected reconstruction
    one cell unanswered               an unregistered approver
    a cell answered twice             an approval of a different run
    no panel decision at all          the inference confirmation withheld

**`disagreements()` no longer merges a duplicate.** It built each side with a
dict comprehension, so a reviewer file answering one cell twice kept the last row
silently — and two reviewers who each contradicted themselves were reported as
agreeing. The duplicate is what the answer check refuses one function away.
`--second` also says FILE in its help text, which is what the code has always
wanted.

    reverted                                          scenarios that fail
    the preflight answering with its own code again    7
    the decision function deleting like the writer      1
    a duplicate answer merged instead of reported       1

## v7.78 — the preflight's answer is the finalizer's answer

Two gaps left over from v7.77, and the first one aimed straight at the pilot that
has to come next.

**A correctly REJECTED reconstruction failed the preflight.** The exit code was
"any problem at all", and `INFERENCE_REJECTED` is in the finalizer's problem list
— so a reviewer who did exactly what the pilot is designed to exercise, refusing
one reconstruction while the panel's other values stand, got:

    the finalizer would say FINALIZED
    Values_Inference_Rejected = 1
    review_preflight exit = 2

A tool that calls a correct review a failure is a tool the reviewer learns to
ignore. The exit code now follows the finalizer's STATUS — 0 if the run would
finalize, 2 if it would not — and `NONFATAL_CHECKS` groups the three findings
that exclude a VALUE from a run that still finalizes (`INFERENCE_REJECTED`,
`VALUE_METHOD_NOT_FINALIZABLE`, `VALUE_METHOD_UNSTATED`) so they print as
`EXCLUDED` rather than as refusals. `--require-all-values` is there for a batch
that is only acceptable whole. The grouping never gates: a panel refused while
another finalizes puts a refusal code in a FINALIZED run's problem list, so the
status is the only thing that can decide.

**And the two shared a decider without sharing its inputs.** `--manifests` exists
on the finalizer for a run that has been moved — the stamp records an absolute
path on the machine that produced it — and the preflight had no such argument, so
the same run could fail one and pass the other with one decision function between
them. It has the argument now, and a scenario builds the actual shape: the
manifests moved out of the run and the stamp pointing at a directory that does
not exist.

The preflight also calls the shared verdict FIRST and reads its own CSVs
afterwards, with `_read` guarded. Unguarded and run last, a malformed
`value_review.csv` raised a traceback out of the preflight where the finalizer
gives `REVIEW_FILE_UNREADABLE` and a filename.

    reverted                                          scenarios that fail
    the preflight failing on a correct rejection       1
    --require-all-values not requiring them            1
    the preflight not passing the manifest directory   1
    a malformed decision file raising                  1

## v7.79 — the evidence has to agree with itself, and the hash is of the bytes that were read

**The verifier read each field on its own.** Is there a support, are there two,
is the span zero — every question answered separately, so a mark whose numbers
are internally impossible answered all of them and got a tier:

    x = 140, left = right = 130, span = 0   ->  DIRECT_CURVE_INK at R0

which is a ten-pixel carry. That is the general form of the nine one-sided
carries v7.73 found on 397: there the span was ignored, here the span is
believed without checking it against the columns and the value's own x. Three
relations now have to hold, and `_geometry_problem` refuses the mark when one
does not:

    one column     span == |support - x|      the carry distance
    two columns    left < x < right           they BRACKET the value
    two columns    span == right - left       the gap they bracket

Measured before it was made a refusal, because a consistency check nobody has run
against a real figure is a prediction: **all 18 of publication 397 figure 1's
marks satisfy all three exactly.** `PIXEL_EPSILON` is 1e-9 and is float noise -
`right - left` and a recorded span are the same subtraction done twice - not a
tolerance; a scenario pins that a hundredth of a pixel passes and a whole one
does not.

**And the stamp hashed the decision files again, after deciding from them.**
`validate_finalization` read them; `finalize` re-opened the paths to hash. A
spreadsheet autosave landing in between produced an accepted file decided from
one set of decisions and a `Review_File_SHA256` naming another — the exact
question the hash exists to answer, answered wrong, with nothing in the run
saying so. `read_decisions` now hashes the bytes and parses THOSE bytes, and the
verdict carries both hashes out to the stamp.

Both ends of the window are scenarios rather than claims: one lands a save the
moment the file has been read, the other lands it between the hash and the parse
by giving the loader a `hashlib` that saves when it hashes. The second is what
makes parsing from the bytes rather than from the path an observable property
instead of a comment.

`disagreements()` also counts duplicates properly: it deduplicated the list of
duplicates and then counted occurrences in that list, so three answers to one
cell reported as two.

    reverted                                          scenarios that fail
    the geometry of the evidence not checked           6
    supports need not bracket the value                2
    the span need not match the gap                    2
    the one-sided carry distance not checked           2
    the stamp hashing the path again after deciding    1
    parsing from the path, not the hashed bytes        1

## v7.80 — the conditions a mark was measured under are the run's, not the artifact's

`Mark_Record_SHA256` covers the panel box, both calibrations and the raster
hash. That is right — a pixel is only a measurement relative to them — and the
finalizer re-hashed **the artifact's own copy of them**. So a producer could:

    panel_manifest.csv    tick mapping A, panel box A, raster A
    mark-data/2           calibration B, box B, raster hash B, marks hashed under B
    figure_values         the same numbers, citing those hashes

and every check in this module passed. The marks agreed with themselves, the
values agreed with the marks, both hashes recomputed, the cell keys matched. The
only thing that disagreed was the manifest the run was validated against, and
nothing compared them.

`run_batch.mark_envelope_header(panel, image_sha256, reader_version)` now builds
the envelope, and `finalize_batch.panel_expectations` re-derives it from the
VERIFIED panel manifest and the run manifest to compare — one construction, two
callers, the same shape `cell_maps` has. `Image_SHA256` and `Reader_Version` come
from the run's own manifest row rather than from this process, because a run made
by an older reader is still a run this module has to be able to check.
`MARK_ENVELOPE_CONTRADICTS_RUN` names the fields that differ, and a panel the run
manifest has no row for is refused rather than measured against a declaration
nobody made.

Four mutations, each re-stamping the marks and rebinding the values so the
artifact is internally perfect: a Y calibration nobody declared, a panel box
nobody declared, a raster this run did not read, and a panel that is not in the
manifests. All four are refused.

The comparison is numeric where numbers are numbers — `12` and `12.0` are the
same pixel, and refusing that spelling would be inventing a disagreement out of a
JSON encoder's habits — and exact where tokens are tokens: marks hashed under a
`linear` scale were hashed under a string this run's manifests do not produce.
Both directions are scenarios.

Publication 397, re-run under this release: **123 values, no refusals.**

    reverted                                          scenarios that fail
    the envelope taken from the artifact itself        4
    a panel the run does not declare not refused       1
    a number spelled differently is a different one    1
    the case of a declaration stops mattering          1

## v7.81 — the shape of the evidence is a contract, and the last two re-reads are closed

**The geometry check was exact and its guard was not.** v7.79 checked three
relations and returned "" whenever a field was missing or unparseable, and the
caller then fell through to a branch that derived a method anyway. So the two
shapes no reader in this package produces were the two that bought a tier:

    left=130, right=""        read as one-sided -> DIRECT_CURVE_INK at R0
    left="foo", right="bar"   read as bracketed -> method from span and cause

`support_shape()` decides the shape FIRST and names only three:

    NO_SUPPORT    both blank                    -> FIT_FALLBACK
    ONE_COLUMN    same column in both fields,   -> span 0 is DIRECT,
                  all four numeric,                anything else is a carry
                  span == |support - x|
    TWO_COLUMNS   all four numeric,             -> interpolation_method(cause)
                  left < x < right,
                  span == right - left

Everything else is `METHOD_EVIDENCE_INCOMPLETE`, and the two mistakes are
diagnosed apart: a blank column is "neither shape", a column reading `foo` is
"not a number". A reviewer handed the wrong one goes looking for the wrong thing.
397 figure 1: 18 marks, 0 problems.

**And `run_manifest.csv` was hashed and then opened again.** `panel_expectations`
re-derives the conditions a panel was measured under from that file — the check
v7.80 added — and read it by path after `verify_run_outputs` had verified its
bytes. The same hash-then-reopen window the decision files and the manifest
frames were both closed against, on the file that now decides whether an
artifact's calibration was declared. The verification keeps the ROWS of every
output it hashes under `verified["outputs"]`, and the expectation is built from
those.

Two smaller ones:

- `read_decisions` declared its digest before the try, so a refusal names the
  bytes that CAUSED it. The parse branch re-hashed the path, which named whatever
  was on disk afterwards — the audit rather than the accepted values, and the
  same shape. Observed by giving `file_sha256_or_blank` a hook that saves over
  the file: only reachable if the refusal does re-open it.
- `--require-all-values` now means what it says: it fails on any excluded value
  AND on any refused panel. Checking only the exclusions let a run pass strict
  mode with one panel refused beside the one that finalized — values lost, and
  the flag that exists to notice that said nothing.

The `PIXEL_EPSILON` scenario also says what it measures: the fixture is a
ten-billionth of a pixel, and the description called it a hundredth — two orders
of magnitude looser than the constant.

    reverted                                          scenarios that fail
    a half-recorded support read as one-sided          1
    supports that are not numbers skipped              2
    the shape decided after the method                 2
    the envelope checker opening run_manifest again    1
    the verification not handing on the rows it hashed 1
    a refusal hashing the path again                   1
    strict mode ignoring a refused panel               1

## v7.82 — `mark-data/3`: the whole instruction is bound to the marks

v7.80 bound the conditions a pixel is a measurement relative to: the panel box,
the two calibrations, the raster. Those are not all the instructions a panel is
read under. `Baseline_Value` decides where a bar is measured FROM. The reader
options decide the threshold, the search radius and the colour tolerances. The
series rows decide what counts as which series. `X_Pixel` decides which column a
position IS. None of them were bound to the marks, so a producer could declare
one set, read the figure under another, and hash the marks under the second with
every check in the module passing.

`Measurement_Declaration_SHA256` is taken over the panel row, its series rows,
its position rows, its reader-config rows, the raster hash and the reader
version — **whole rows, not a curated subset**, because a list of the
measurement-relevant columns is a list that drifts behind the manifests: a column
added next year would be outside the digest by default and nothing would say so.

It sits in the envelope AND inside `Mark_Record_SHA256`, which is the schema
bump. Beside the hash rather than inside it, two artifacts of the same figure
read under two declarations would hash their marks identically, and a value could
be joined to a mark from the other one. `finalize_batch` re-derives the digest
from the verified manifests exactly as it re-derives the rest of the envelope.

What this binds is the CLAIM. Marks read under one declaration cannot be
presented under another; it does not prove a producer obeyed its own
declaration, and nothing in an artifact can. That is written down in the
function rather than implied.

Publication 397 re-runs clean: 123 values, no refusals, `mark-data/3`.

    reverted                                          scenarios that fail
    the declaration not in the mark's own hash         1
    the declaration not in the envelope at all         1
    the digest ignoring the series and position rows   1
    the digest ignoring the reader options             1
    the checker building it without the declared rows  1

## v7.83 — the second reader whose methods are re-derived from its own evidence

`BAR_COLOR` reaches R0 on all three axes, which means every one of its cells goes
into a pool on the strength of three words nothing re-derived. It records enough
to re-derive all three, so `expected_bar_colour_methods` does:

    identity     the bar was found in a mask built from this series' declared
                 colour - UNLESS another declared colour's mask claims the same
                 ink, and then the bar is evidence of neither identity. The run
                 drops a contested mark rather than choosing; a producer that
                 kept one is claiming MEASURED_COLOUR for ink that measured as
                 two colours
    value        `Bar_Top_Definition` says which edge the number came from, and
                 the reader records what the number WOULD have been at the fill
                 edge. A mean equal to that one, from a bar whose fill edge is a
                 different pixel row, was not read at the outline centre whatever
                 the field says - a second number the same mark carries, which is
                 what makes the claim checkable at all
    dispersion   the stem and the cap: a cap with a stem is
                 DIRECT_CONNECTED_CAP, a cap without one is UNSTEMMED_CAP at R3,
                 no cap is NO_DISPERSION

`Position_Assignment` is checked too, when the mark carries one. It is not a
method - it says whether the bar's x label came from a declared anchor or from
counting bars left to right - and `grid_engine` refuses a VALUE that admits to
counting. A value that DROPS the column passes that gate; the mark cannot,
because it is hashed.

Run against every bar fixture in the package - 37 marks across the plain, signed,
glyph-free and vanishing-bar rasters - the derivation agrees with the reader on
every mark and reports no problems.

The join is table-driven (`EVIDENCE_VERIFIERS[mark_type]`), so what v7.83 adds at
the call site is an entry; the LINE_MONO_STYLE scenarios cover the wiring, and
these cover that the entry answers in the two codes the finalizer branches on.

    reverted                                          scenarios that fail
    BAR_COLOR having no verifier again                 2
    contested ink still naming a colour                2
    the fill-edge reading not compared                 1
    an unstemmed cap priced as a followed one          2
    a counted x label not refused                      1

## v7.84 — a verifier that only refutes can be starved

v7.83 asked whether each field CONTRADICTED the claim and let a missing one
through. So a mark like this took all three methods at R0:

    mask_overlap  "garbage"      not a positive number, so not contested
    fill_top_px   ""             the fill-edge comparison was skipped
    cap_px        ""             never read; a dispersion number was enough
    Position_...  ""             checked only when filled in

Every field the BAR_COLOR verifier decides from is now REQUIRED, and the
diagnosis says which one is missing:

    mask_overlap   a finite non-negative integer, and MEASURED_COLOUR only at 0
    the value      top_px, fill_top_px, mean and mean_if_read_at_fill_edge, all
                   four finite - the fill-edge reading is the only thing on the
                   mark that can tell an outline-centre reading from a fill-edge
                   one, so a mark without it cannot support the claim
    the spread     DIRECT_CONNECTED_CAP needs cap_px AND dispersion; NO_DISPERSION
                   needs neither; a cap with no stem is a contradiction
    the position   DECLARED_ANCHOR whenever the mark sits at an x_label, blank
                   only when the panel has no position dimension

**`UNSTEMMED_CAP` is out of `BAR_COLOR`'s contract.** `bar_reader` sets `cap_px`
only inside the branch that also confirms the stem, so a cap without one is a
shape it cannot produce - and listing it said this reader could, which is what a
contract is for saying. The line readers keep it: theirs is reachable
(`_marker_and_errorbar` returns a whisker extent with `stem=False` whenever the
caps are not on both sides).

**NaN is not a number, in either verifier.** `float("nan")` succeeds and every
comparison against NaN is False, so a mark carrying one passed each
`abs(a - b) > EPSILON` check silently: a geometry that cannot be checked read as
a geometry that agrees. `finite_number` is shared by both verifiers, and the
raw-mark writer uses `allow_nan=False` - a reader that computes a NaN now stops
the batch with `InternalReaderError` naming the panel, which is the answer this
module already gives a KeyError from a renamed field. A defect here is not a
difficult figure, and a run that quietly refused the panel would hide it behind a
queue row somebody would spend an afternoon re-reading by hand.

    reverted                                          scenarios that fail
    a non-numeric overlap counting as no overlap       2
    the fill-edge evidence optional again              2
    a stem needing no cap under it                     2
    a cap with no stem priced instead of refused       1
    a bar at a label not saying how it got there       2
    BAR_COLOR claiming an unstemmed cap again          1
    nan being a number again                           2
    the writer accepting a NaN into an artifact        3

## v7.85 — the numbers on a bar mark are re-computed from the axis the run declared

v7.84 made the BAR_COLOR verifier total on the FIELDS. It still checked the
numbers only against each other: a mean of 999 passed as long as it was not
equal to the fill-edge reading, and a dispersion passed as long as some number
was there. Every number on a bar mark is a pixel row put through the panel's y
calibration, and v7.80–v7.82 had already bound that calibration to the mark —
so the arithmetic can be re-run:

    mean                        == calibration(top_px)
    mean_if_read_at_fill_edge   == calibration(fill_top_px)
    dispersion                  == |calibration(cap_px) - calibration(top_px)|

The verifiers now take `(mark, context)`, and `finalize_batch` hands them the
envelope IT re-derived from the verified manifests — not the artifact's own copy,
because a verifier recomputing a mark's numbers under the producer's calibration
would be checking the artifact against itself. A mark with no axis behind it is
refused rather than compared to itself: "the two numbers I made up agree" is not
evidence that a pixel row became a value.

`mark_readers.calibration_from_record` rebuilds the calibration OBJECT from the
three numbers in the envelope, so the conversion exists once. A copied
`slope * pixel + intercept` is the wrong answer on a log axis, and a scenario
runs the whole derivation on one.

**And the finalizer's side of this is exercised by a real BAR_COLOR run.** The
bar fixture is now declared as a panel — box, ticks, mask keys, session anchors —
and goes through `run_batch` end to end: 12 values, all `MEASURED_COLOUR` /
`BAR_OUTLINE_CENTER`, all passing the join. Without it the verifier was reached
only by direct calls, and passing the context could be dropped with nothing to
notice; that mutation now fails a scenario. Three edits to the artifact, each
re-stamped and rebound so the marks and the values agree with each other, are
refused: a top row that no longer produces the mean, a cap that is not the
distance the dispersion claims, and a stem the mark itself denies.

    reverted                                          scenarios that fail
    the mean not recomputed from its pixel row         4
    the dispersion not recomputed from the cap         1
    a missing calibration assumed away                 1
    a missing calibration assumed away, spread side    1
    the finalizer not handing over its context         1
    a stem needing no top row to measure from          1
    the log axis converted as a linear one             1

## v7.86 — a bar has to BE at the position it says it is, and measured from the baseline

Two things the BAR_COLOR verifier still took on trust, both at the boundary
between a pixel and a declaration.

**`DECLARED_ANCHOR` was half an answer.** It says the reader used declared
anchors; it does not say THIS mark is at the one it names. So two bars in a
panel could exchange their `x_label`s, have their cells and every hash
recomputed to match, and pass: the numbers still matched their marks, the cells
still matched the labels, and nothing compared a mark's own x column to the
anchors. The heading exchange v7.74 closed, reopened one layer down.

`bar_reader` assigns the nearest declared column within a tolerance and records
the distance it accepted, so all of it re-derives from the verified position
rows:

    the label IS the nearest anchor        and no other is equally near
    slot_residual_px IS that distance      recorded, and required
    the distance is inside the tolerance   the config's, or the reader's own
                                           default - half the smallest gap
                                           between anchors, the panel's width
                                           when there is only one

**And the baseline decides which end of the bar was measured.** Re-computing
`calibrate(top_px)` says the number matches the row; it does not say the row was
the right end. Move the cap to between the top and the baseline, update the
dispersion to the new distance, re-stamp everything, and the arithmetic is
perfect while the cap is not an error bar's. So:

    Bar_Direction agrees with which side of the baseline the top row is on
    the cap is FURTHER from the baseline than the top - an error bar is
        measured outward from the data end
    top, fill and cap are inside the panel box this run declares

The declaration reaches the verifier through a context that is a SUPERSET of the
hashed envelope - anchors, tolerance, baseline - and deliberately not part of
it: adding them to the artifact would only give a producer one more field to
write correctly. The tolerance is read through `READER_OPTIONS`' own parser, not
a second `float()`.

The end-to-end regression is the one the review named: two of the bar fixture's
marks exchange their `x_label`s, the artifact is re-stamped, and the values are
rebound with the cell keys the manifests give the labels they now claim. Refused.

    reverted                                          scenarios that fail
    the label need not be the nearest anchor           1
    a tie between two anchors decided by order         1
    the recorded residual not being the distance       1
    a mark beyond the tolerance accepted               2
    the anchors not asked for at all                   7
    the cap allowed between the top and the baseline   1
    the bar allowed to grow either way                 1
    a row outside the panel box measured anyway        1
    the baseline not asked about                       3
    the finalizer handing over the envelope only       1

## v7.87 — a curve's numbers are re-computed too, and the cap rows are kept

`expected_line_style_methods` said it did not use its context: a curve's value is
read off ink at a column, so there was nothing to re-calibrate. That was wrong
about the reader's own record. Every line mark carries `marker_center_px`, and
its mean IS that row put through the panel's y calibration - on publication 397,
exactly, for all 18 marks and every value method, including the reconstructed
ones (the reconstruction happens in pixel space and the conversion happens once).

So the same third party arrives: re-deriving the METHOD from the support columns
says how the number was got, and re-computing the number says it is the one those
pixels produce. A producer could otherwise move `marker_center_px`, keep the
mean, re-stamp everything, and the value-to-mark join would find two fields
agreeing with each other.

**The cap rows are now on the mark.** All four marker/curve readers kept the
calibrated bounds and threw the pixels away, so `dispersion` was a conversion
nothing downstream could repeat. `Errorbar_Top_Px` and `Errorbar_Bottom_Px` are
recorded beside them - and only when there is a spread to have measured - so:

    mean         == calibrate(marker_center_px)
    dispersion   == |calibrate(top) - calibrate(bottom)| / 2

Both verified against the real readers before being made a refusal: 397's 18
line marks and the style fixture's capped marks all reproduce their own numbers.

    reverted                                          scenarios that fail
    a curve's mean not recomputed                      1
    a curve's dispersion not recomputed                1
    a dispersion with no cap rows accepted             2
    the curve arithmetic not asked for                 3
    the marker reader dropping its cap rows            1
    the style reader dropping its cap rows             1

## v7.88 — the other half of the colour evidence

`mask_overlap=0` says no OTHER declared colour covers this bar's ink. It does not
say the colour THIS series declares does — and `MEASURED_COLOUR` is a claim about
the second. The reader always knew, because it found the bar in that mask; it
wrote nothing down, so the identity rested on an execution path rather than on
evidence.

`bar_reader` now records the pair from the same sample point:

    mask_overlap    how many OTHER declared masks cover this pixel
    own_mask_hit    whether this series' own mask covers it
    own_mask_key    WHICH mask that was

and the verifier requires all three: no other claim, its own claim, and the mask
it was found in being the one this run declares for that series — a named
built-in under `Mask_Key`, or the mask built from `Colour_Hex` and keyed by the
series id. The declaration reaches the verifier through the same context the
anchors and the baseline do.

All 37 marks across the four bar fixtures record `own_mask_hit=1`,
`mask_overlap=0`, and the mask their series declares.

    reverted                                          scenarios that fail
    the own-mask hit not required                      2
    the mask found in need not be the declared one     2
    the reader dropping its own-mask hit               2
    the reader dropping which mask                     2
    the discriminants never reaching the verifier      1

## Still open

- 397 Figure 5 is two named individuals beat by beat — no summary statistic
  exists to read, and it stays MANUAL
- 397 Figure 4, 386 Figures 3–4
- ID 323 FIG2 DAP DI19 (1 cell) and 4 unpaired cells need a human reading
- ID 323 and 397 both need their SD/SEM wording resolved from the methods text
- 397 Figure 1 at 4:30, 5:00 and 6:00: the merged run is thicker than one
  stroke and its edges are the two curves, unread
- `RESERVED_METHODS` is five methods deep: `RESTORED_MASKED_CAP`,
  `INTERPOLATED_DISPERSION`, `FITTED_DISPERSION`, `DIRECT_BOUND_PAIR` and
  `SOURCE_TRANSCRIBED` are priced and not producible. The first needs the reader
  to keep its cap masks apart instead of one `blind` union, and a real figure
  where a cap is partly covered by exactly one of them
- the R3 context crop draws the two supports and the placed value, and NOT the
  occlusion mask: the mask lives in the reader's memory at read time and nothing
  downstream has it, so the cause is named in the caption rather than shaded
- no R3 or R2 cell in the shipped corpus has reached a review queue yet, so the
  first pilot needs a publication whose dispersion definition is settled - and
  should include at least one cell the reviewer REJECTS, or the partial-rejection
  path is exercised by nobody - 397's
  dispersion definition is unresolved, so its two of each fail machine QC - and
  the per-cell channel is therefore exercised end to end by fixtures rather than
  by a person
- `HUMAN_RESOLUTION` has a review channel - `BAR_MONO_GEOMETRY_RESOLVED` asks
  for `Identity_Checked`, and v7.68 requires the row to cite the resolution it
  rests on. What is not decided is whether the approver and the resolver may be
  the same person, and whether a resolution needs its own cell-level
  confirmation the way a reconstructed value does
- the numbers are re-computed from the pixels for `BAR_COLOR` and
  `LINE_MONO_STYLE`; the other readers record the rows now but nothing re-derives
  them yet, because they have no verifier to do it in
- the methods are RE-DERIVED from the evidence for two readers of the seven,
  `LINE_MONO_STYLE` and `BAR_COLOR`. The other five are held to the matrix, to the
  mark join and to the value-to-cell binding, and not to a derivation from their
  own measurements - a real difference in strength. THREE are left, not two:
  `LINE_COLOR`, `LINE_MONO` and `BOX_VIOLIN`, in that order - `LINE_COLOR` reuses
  the colour evidence with marker centres and cap geometry - while `BAR_MONO` and
  `SCATTER` have their own durable artifacts checked instead
- the hand-reconciled worked examples (`id323_figure_values.csv`) carry no
  methods either: they come from two raster readings reconciled to a midpoint,
  which is a `MANUAL_DIGITIZED` value with no reader behind it and no channel
  yet for saying so
