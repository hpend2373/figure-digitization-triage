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
| `source_document_manifest.csv` | main article/supplement/chapter | the whole file's `Source_File_SHA256` (or `NOT_HELD`), the page range inventoried, verified figure count, source role |
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

## v7.89 — the third verifier, and a fixture that had to say which reader it was

`LINE_COLOR` needed no new question. The colour pair is the one `BAR_COLOR`
answers with — no other declared mask over the ink, this series' own mask over
it, the mask being the one the run declares — so it is one function now
(`_colour_identity_problems`) and both readers call it. The value is the marker
centre through the panel's axis, which v7.87 already re-computes. The spread is
the two cap rows v7.87 started keeping.

What is different is WHERE. A bar is found anywhere and assigned to the nearest
declared anchor; a marker is looked for AT the declared column, so its own x must
BE that column rather than merely be nearest to it.

`read_line_marker_panel` records its own-colour evidence as a COUNT of the
series' own mask pixels across the marker it measured - already computed, as the
key the marker group is chosen by, and thrown away. A probe at the centre pixel
would have been wrong: an open marker is a ring, and its centre is the paper.

**`NO_DISPERSION` leaves `LINE_COLOR`'s contract.** This reader takes the
connected column through the marker as the extent, so every mark it emits has a
spread - the same reachability question `UNSTEMMED_CAP` failed for `BAR_COLOR`
in v7.84, asked of this reader while writing its verifier.

**And four scenarios had to say which reader they were about.** They test the
TIER GATE: a value that does not say how it was got is refused and counted,
whatever its reader. They ran on the colour fixture, and from this release a
colour panel refuses a blank method one step earlier - the mark contradicts it -
so the gate was never reached. Both refusals are right; the gate is what those
scenarios exist for, so their panel is now declared `LINE_MONO`, which has no
verifier yet, with a stand-in reader exactly as `LINE_MONO_STYLE` has had since
v7.68. `Values_Method_Unstated` is reachable for readers without a verifier and
for foreign producers, and no longer for the three that have one.

    reverted                                          scenarios that fail
    LINE_COLOR having no verifier again                1
    a marker need not be at its declared column        1
    a marker's definition not checked                  1
    LINE_COLOR claiming NO_DISPERSION again            1
    the colour reader dropping its own ink             2
    the support count being a probe at the centre      2

## v7.90 — the fourth verifier, and two fixtures that described impossible marks

`LINE_MONO` has no colour to name a series by, so it names it by the marker -
and WHICH of its three identity methods that is depends on what the manifest
declared:

    MEASURED_MARKER_SHAPE    the series declares a shape and the marker was
                             classified as that shape
    MEASURED_MARKER_FILL     no shape declared, a fill declared, and the marker
                             measured as that fill
    DECLARED_SINGLE_SERIES   neither: nothing about the mark was compared with
                             anything, which is R1 and not R0

All three re-derive from the measurement and the declaration together. The fill
state is checked against the RATIO the reader recorded it from
(`MARKER_FILLED_RATIO`, named once and shared), the position is nearest-anchor -
a monochrome marker is FOUND rather than looked up, so its x is a measurement -
and the numbers are re-computed like every other reader's.

**Two fixtures turned out to describe marks no reader can make.** Both were
found by the new verifier, which is what a verifier is for:

- a mark with `Errorbar_Stem_Confirmed=TRUE` beside `Dispersion_Method=
  UNSTEMMED_CAP` — a stem that was confirmed and a method that says no stem was
  found. It had stood since v7.71 as the R3-on-the-spread-axis fixture.
- the tier-gate fixtures, which is the deeper finding: **no producible
  dispersion method is both R3 and able to reach the finalizer.** `grid_engine`
  refuses any cell whose whisker the reader could not connect, so an
  `UNSTEMMED_CAP` value never survives machine QC, and the two R3 methods that
  would - `RESTORED_MASKED_CAP` and `INTERPOLATED_DISPERSION` - are reserved and
  producible by nobody. The scenario now checks the derivation where it lives
  and the gate's refusal end to end, and the gap is on the open list rather than
  hidden behind a fixture that could not happen.

Same for the blank-method scenarios: with a verifier on the reader, a value that
says nothing is refused by the MARK that contradicts it, one step before the
tier gate. `Values_Method_Unstated` is reachable for `BAR_MONO`, `SCATTER` and
foreign producers, and no longer for the four readers that re-derive.

    reverted                                          scenarios that fail
    LINE_MONO having no verifier again                 1
    a declared shape need not be the measured one      1
    a declared fill need not be the measured one       1
    the fill state need not match its own ratio        1
    a monochrome marker need not be near its anchor    1
    a spread that is half recorded accepted            1
    an undeclared series measured as one anyway        1

## v7.91 — the fifth verifier: every reader that joins to raw marks re-derives now

`BOX_VIOLIN` has the most literal evidence in the package - five horizontal
lines, three of them wide enough to be the box - and the reader already refuses
a panel that does not show all five, because a violin with a median dot is not a
five-number summary. It kept the five NUMBERS and threw the rows away, so the
refusal was something a checker had to trust rather than re-derive.

`Box_Line_Rows_Px` and `Box_Line_Widths_Px` are on the mark now, and the verifier
re-derives the whole reading:

    five lines, and exactly three at least BOX_LINE_MIN_WIDTH_PX wide
    the box between the two caps, because a whisker runs outward from it
    each of the five numbers being its own row through the panel's axis
    DECLARED_SINGLE_SERIES only if the run declares exactly ONE series for the
        panel - nothing about a box says which series it is, so "one was
        declared" is the claim, and it is checkable

    EVIDENCE_VERIFIERS == MARK_JOIN_REQUIRED

is now true, and a scenario says so: the five readers whose values join to raw
marks all re-derive their three methods and their numbers from those marks.
`BAR_MONO` and `SCATTER` are checked through their own durable artifacts -
`mono_bar_geometry.csv` and the point cloud - which is a different route and not
a missing one.

    reverted                                          scenarios that fail
    BOX_VIOLIN having no verifier again                1
    two declared series buying a single-series claim   1
    four lines being a five-number summary             1
    a violin with one wide line being a box            1
    the box not having to sit between its caps         1
    the five numbers not recomputed                    1
    the reader dropping its line rows                  1

## v7.92 — why there is no error bar, and what that says about a reserved method

`RESTORED_MASKED_CAP` has sat in the registry since v7.71 with a written list of
what it needs, ending in "a real figure where a cap is partly covered by exactly
one of them". Before writing the emitter, the reader was instrumented against
the only real line panel in the package. **There is no such cap on it.**

Publication 397 figure 1, 18 marks:

    CAP_READ                  3    a bar the reader followed to both caps
    MARKS_SHARE_A_COLUMN     12    the two curves are one column of ink, and no
                                   rule local to that column - and no person
                                   reading that figure - can say whose cap is
                                   whose
    NO_BOUNDED_CAP            3    a cap one pixel narrower than the rule takes

Not one is a cap interrupted by furniture. Writing the emitter would have been
writing a capability this corpus cannot exercise, which is what the reserved list
exists to prevent - so the measurement is the deliverable, and it is pinned in
the forward test rather than described here: a distribution that drifts is the
reader changing its mind about a figure nobody re-drew.

**The reason is part of the answer now.** `_bar_extent` returned the same `None`
for every one of those cases, so "this figure draws no error bar here" and
"nobody could say whose cap that is" were the same silence. `DISPERSION_REFUSALS`
names the five outcomes, the mark records which, and the `LINE_MONO_STYLE`
verifier requires one: **a mark that reports no spread and does not say why
cannot support `NO_DISPERSION`**, any more than a blank method can support a
tier. A cap that was read beside a stem that was not is two answers to one
question, and is refused as one.

The three one-pixel misses are NOT fixed by widening the rule. A cap of 9 pixels
where the reader requires 10 is a measurement this reader declines to make, and
widening a constant to make three cells pass is the failure this package is
built around. It is on the open list with its number.

    reverted                                          scenarios that fail
    no spread needing no reason                        1
    an unpriced reason accepted                        1
    a read cap beside no stem being one answer         1
    the reader not saying why                          3
    every refusal being the same refusal               the forward test on 397

## v7.93 — the runbook for the review a program may not do

Every part of a human review that a program may do is finished: the preflight
says which cells will be asked about and why, the templates pre-fill every
identifier, the crops are drawn, the finalizer refuses an incomplete answer set,
and the two-reviewer comparison works off content-derived ids. What was left was
the procedure, and an improvised procedure is a review nobody can repeat.

`PILOT.md` is the order a person works in - run, preflight, template, look,
answer, preflight again, finalize - with what each confirmation claims, what
CONFIRMED and REJECTED each cost, and what a reviewer is never asked (R4 cells
never reach them; they are work, not a signature). It opens by saying that none
of it may be done by an agent, because the failure this package is built around
is easiest to commit when the procedure is vague enough that filling in a
confirmation looks helpful.

It also states what a pilot needs before it starts, which is the honest reason
one has not run: a publication whose dispersion definition is settled in its
methods text. 397's is not, and a pilot that begins by guessing at a weight is
not a pilot of this package.

The suite parses the runbook: every command line in it is checked against the
real parsers, every flag against the module that would receive it, and every
file it tells a reviewer to open against what a run writes. A procedure that
names a flag nothing accepts is worse than none - the reviewer runs it, gets an
error, and improvises.

    reverted                                          scenarios that fail
    a command the runbook names that does not exist    1
    a flag no module accepts                           1
    a file no run writes                               1

## v7.94 — the pilot has a subject, and the runbook's promises are checked

v7.93's runbook was right about what a person does and wrong in three places
about how it is done. All three are corrected here, and the first pilot now has
a name.

**The prohibition was too wide to be followed.** "None of this may be done by an
agent" would have banned running the batch, which is a command, not a judgement.
It now reads: no review judgment, confirmation, rejection or attestation may be
performed by an agent — an agent may run the batch, generate the templates and
the review artifacts, and run the read-only preflight.

**The preflight is run twice, and the first run is expected to fail.** v7.93 put
the preflight before the template, which cannot be right: the finalizer cannot
say `FINALIZED` before a person has answered anything, so a check run there
always exits 2 and a reviewer taught to expect 0 learns to ignore it. The order
is run → `--template` → PRE-REVIEW preflight → review → POST-REVIEW preflight →
finalize. The pre-review run is *expected* to exit 2; what must be clean is the
bundle — 0 bundle problems, every question with its manifest row and its context
picture, and answer problems that are all of one kind, a person has not answered
yet. The post-review run must exit 0.

Both numbers are now read OUT OF `PILOT.md` by `test_finalize.py` and checked
against the real tools, on a real R3 run driven through `finalize_batch.py
--template`'s own CLI. Nothing else in the suite reads those two sentences, and
a runbook that promises the wrong code sends every reviewer to fix a bundle that
was never broken.

**A pilot may not require a rejection.** v7.93 asked for "at least one cell the
reviewer will REJECT". A reviewer who knows something must fail pushes an
ambiguous cell over, and the answer records a software path rather than a
reading. Nobody is told how many cells to reject, or which. The
partial-rejection path is exercised by fixtures today and is validated
operationally in a separate BLINDED exercise, against a cell an independent
manual reading has already found wrong.

**The first pilot is publication 127, Verheyden 2007, Figure 4** — named exactly
*the first production R2 + human-resolution pilot*. Its methods say mean ± SE in
so many words, it holds an R0 control group, an R2 identity named by a prototype
formed in another group and two 15 px bars a person resolved by hand, and its
bundle is the furthest along. SLOW and NORMAL are the finalization target;
LOWFREQ is withheld if its skewness QC problem stands and is not part of the
success condition, because mixing the QC-semantics question into the review
pilot would make a failure in either look like a failure of both. What 127
cannot test is written down where nobody can claim otherwise: the per-cell
CONFIRMED/REJECTED channel, the R3 context crop, and partial rejection. Resolver
and approver are separate roles and, for the first pilot, separate people; if
that is impossible they review independently and are compared with `--second`.
The second pilot is chosen for the per-cell channel, and the criteria are in the
file.

    reverted                                          scenarios that fail
    the runbook promises the wrong exit code           1
    step 2 hands the reviewer only half the templates  2
    a blank template row reads as an unasked question  1

## v7.95 — the runbook meets the mode the first pilot actually uses

v7.94 chose publication 127 and then described a review it does not get. Two
things were wrong, and both would have shown up on the day.

**`--second` cannot stand in for a second person, least of all here.** v7.94's
"Who does what" said: two people, and if a second is impossible, review
independently and compare with `--second`. But `--second` reads two
`inference_review.csv` files. The only channel it compares is per-cell
CONFIRMED/REJECTED — not the panel decision, not the confirmations a mode asks
for, not the identity the resolver wrote down; none of those columns is even in
the file it reads. And 127 has no R3 cell, which the same document says twice.
So the fallback was two empty templates agreeing with each other, printing
nothing, and one person holding both roles reading as an independent check.

The fallback is gone: **if a second person is not available, 127 runs as a dry
run and nothing is finalized.** `review_preflight.py` no longer lets the flag be
quietly useless either — it reports how many reconstructed cells it compared,
says in one line what that channel does not cover, and exits 2 when the answer
is none. Asking for an independent check and getting none is the case the exit
code exists for.

**The reviewer was sent to the wrong picture.** 127 Figure 4 is queued
`BAR_MONO_GEOMETRY_RESOLVED`, and v7.94's review step named an overlay and an
inference crop. That mode asks for `Marks_Checked`, `Axis_Labels_Checked`,
`Calibration_Checked` and `Identity_Checked`, and three of those four cannot be
made from a panel overlay: the printed tick numbers, the ink inside a 15 px bar,
and somebody else's reading of a legend are each in a different artifact. The
mode registers six, and `PILOT.md` now walks them in the order they answer in —
`geometry-review/index.html` and its row/picture/panel counts, the three
`CALIBRATION_PANEL`s against the printed ticks, the `GEOMETRY_ROW_CROP`s for
NORMAL/SUPINE slots 0–2, the `IDENTITY_RESOLUTION` file and its evidence, and
the overlay last, once the axis and the identities under it have been checked.

`test_documented_status.py` reads `REVIEW_MODES` and `REVIEW_CONFIRMATIONS` and
requires the section that names the mode to name every artifact it registers,
and to pair every confirmation against the picture that answers it — the
confirmations are checked on the `->` lines specifically, because the paragraph
above the steps lists all four by name and a whole-section check passed while
the mapping was deleted.

**And the pre-review promise was R3-shaped.** "Every question has its manifest
row and its context picture" is not true of an R2 identity: it has no
`Inference_ID` and no cell crop, it is judged at the panel, and `bundle_problems`
knows that. The first pilot is R2, so v7.94's own success condition described a
bundle 127 cannot produce. The wording is now per tier, and the R2 case is
pinned on the real `BAR_MONO_GEOMETRY_RESOLVED` run: an R2 question with a blank
`Inference_ID`, zero bundle problems, all six artifacts in the panel's ledger,
and an unfilled template that reports every one of the four confirmations as
missing.

    reverted                                          scenarios that fail
    --second is a substitute for a second person       1
    R2 is asked for a context crop it cannot have      1
    the runbook forgets an artifact the mode registers 1
    the runbook forgets a confirmation it asks for     1

## v7.96 — the runbook's promises become the software's refusals

v7.95 described 127's review correctly and left three of its promises as prose.
A runbook that says something the tools do not enforce is a runbook that gets
followed until the day somebody is in a hurry.

**`Marks_Checked` had no required picture behind it.** Both geometry modes ask
for it - "the labels sit on the marks a reader would give them" - and the only
artifact that shows a LABEL on a MARK is the panel overlay. `OVERLAY` was not in
either mode's required list: a row crop shows one bar with no label and the
calibration panel shows the axis, so a run holding the five geometry files and
no overlay satisfied the requirement, and `PILOT.md` sent its reviewer to a
picture the mode did not guarantee. Both modes require it now, which makes 127's
list seven artifacts, and an approval on a geometry run whose overlay is not in
the ledger is `REVIEW_ARTIFACT_MISSING` naming `OVERLAY`.

**The mode is not the whole list of confirmations.** A panel's own values add
`Inference_Checked` through `inference_confirmations` - derived from the rows, so
it composes with every mode instead of doubling the mode table - and 127's
NORMAL and SUPINE hold cells named `FIGURE_PROTOTYPE_MATCH`. Those panels ask
five things, not four, and v7.95's runbook mapped four: the reviewer had no
picture for the one piece of reasoning the first pilot is actually about. The
runbook now splits the row crops into two questions - a bar whose fill was
sampled, read against its own ink; a bar matched to a prototype pooled over the
whole figure, read beside a sampled bar's crop - and the check is made on a real
`BAR_MONO_GEOMETRY_RESOLVED` run against `REVIEW_CONFIRMATIONS` *plus* whatever
that panel's values add, not against the static tuple alone.

**"Two people" was a paragraph.** `identity_resolution.csv` carries the
Reviewer_ID of the person who named a series the reader could not, and
`value_review.csv` carries the Reviewer_ID of the person approving the panel
that naming lands in. Nothing compared them, so one person filling in both
finalized - `Identity_Checked=CONFIRMED` meaning "yes, I am still of the same
opinion". `--distinct-reviewers`, on the finalizer and on the preflight, refuses
`RESOLVER_IS_APPROVER`. It is DECLARED rather than defaulted, because whether one
person may hold both roles is a decision this package has not made; what it adds
is that a run declaring the contract has it enforced. The finalize stamp records
`Reviewer_Separation_Policy` either way - `NOT_DECLARED` is written out, not left
blank - so an accepted file can be asked afterwards which contract produced it.

**And `--second` was counting the wrong thing.** v7.95 counted the UNION of the
two files' cells, which over-reports in the one direction that matters: five
answers against an empty second file read as "5 compared". It now counts only
cells answered exactly once with a valid verdict on BOTH sides, prints that
against the number asked, and exits 2 unless every question was compared and the
two answers agree. A second reader who contradicts the first is not a passing
preflight - the finalizer only ever reads the first file, so the disagreement
changes nothing it can see, and reporting it while exiting 0 told a person the
review passed while the two readings of the ink contradicted each other.

The contact sheet wording is fixed too: rows must equal pictures, and panels is
a separate number that must equal the figure's panel count - three for 127.

    reverted                                          scenarios that fail
    the overlay is not required by the geometry mode   1
    the runbook drops the value-derived confirmation   1
    the resolver may sign their own reading            4
    the stamp stops recording the policy               1
    --second counts the union again                    3
    a --second that compared nothing passes            5
    a half-done or contradicted --second passes        3

## v7.97 — a governance record that cannot lie, and a second reader who has to be one

v7.96 built the separation contract and left three holes in it, each of the same
kind: a check that looks like it establishes something and does not.

**A policy the enforcement did not recognise was recorded as though it had been
applied.** `SEPARATION_POLICIES` was declared in v7.96 and never consulted -
enforcement was one exact string comparison, and the stamp echoed whatever the
caller passed. So `finalize(run_dir, separation_policy="DISTINCT_REVIEWERS")`
produced an accepted file whose stamp named a strict-sounding contract that ran
against nothing. That is the one way a governance record can fail: not by being
absent, but by being wrong. The policy is canonicalised before anything else is
read, an unrecognised token is `BAD_REVIEWER_SEPARATION_POLICY` and stops the
finalization, and the stamp records the canonical policy or `UNRECOGNIZED` -
never the caller's string.

**"Two people" was two Reviewer_IDs, and a Reviewer_ID identifies a row.** The
registry refuses a duplicated ID and nothing refuses a duplicated PERSON, so one
human registered twice satisfied the check - by a registry merge, an
ID-convention change, or on purpose. The comparison is on the normalized contact
now, and it requires an ORCID: an ORCID identifies a person, an email address
identifies a mailbox somebody may share or change, and two addresses prove
nothing. Where an ORCID is missing on either side the contract refuses with
`REVIEWER_IDENTITY_UNPROVABLE` instead of assuming. Runs that declare nothing are
unaffected.

**`--second` did not ask who wrote the second file.** Counting the cells both
files answered says the two files agree; it says nothing about where the second
came from, so `--inference A.csv --second A.csv` exited 0 on a complete answer
set, and so did a copy of A signed by the same person. It now refuses the same
file twice, two files whose cells carry the same `Reviewer_ID`, and a second
reading signed by somebody the registry does not carry as HUMAN - a
`DEMO_IDENTITY` included. And it says out loud what it is: a READ-ONLY
qualification check, not part of the finalization contract. The finalizer reads
`--inference` and never the second file, so nothing about the second reading is
bound into `Review_Subject_SHA256` or stamped. Making it a contract means the
finalizer taking the file and recording its hash, its reviewer and its
disagreement count, which is a decision rather than a flag.

Two documentation corrections, both of them R3 assumptions leaking into an R2
pilot: `--template` writes `inference_review.csv` only where there are
reconstructed cells - 127 has none, so the first pilot gets one file, and the
suite now requires the runbook to name each file rather than say "both" - and
`Inference_Checked` means different things at the two tiers. At R2 there is no
per-cell file and no `Inference_ID`; the confirmation IS the answer, made at the
panel. At R3 it asserts the question was not skipped and each cell is answered in
`inference_review.csv`. The grain is written properly too: 127's NORMAL panel,
SUPINE group.

    reverted                                          scenarios that fail
    an unrecognised policy token is accepted           3
    the stamp echoes the caller's policy string        1
    reviewers are compared as row identifiers again    1
    an unprovable identity is assumed to be a person   1
    --second accepts the same file twice               1
    --second does not ask who signed the second read   1
    --second accepts an unregistered second reader     2
    the second file's problems do not change the exit  4
    the runbook promises two template files everywhere 1

## v7.98 — the two checks that answer the same question answer it the same way

v7.97 moved the resolver-approver contract to ORCID person keys and left
`--second` comparing `Reviewer_ID`s, so one human registered twice was refused on
a panel signature and accepted as an independent reading. Both are the question
"are these two people", and there is no reason for two answers.

**`--second` compares people now.** Same `FIN.person_keys`, same rule: an ORCID
identifies a person, and where one is missing on either side the answer is
"cannot tell" rather than "yes". `RV_A` and `RV_B` sharing an ORCID are reported
as one person registered twice.

**And the second file is checked as a review record**, not as three columns.
v7.97 read `Inference_ID`, `Inference_Confirmed` and `Reviewer_ID` and looked at
nothing else, so a second reading could answer a question this run did not ask,
name another panel's `Cell_Key`, be answered twice, or carry no date at all.
`Inference_ID` binds the cell cryptographically so no NUMBER could move - but "a
registered person answered this question on this date" was never established, and
that is the whole content of an independent reading. Every question answered once,
each row naming this run's own panel, unit and cell, and a `Reviewed_At` that
parses and is not in the future.

**The registry comes from where the finalizer looks.** The preflight resolved it
as `--manifests or RUN/manifests` and never reached the stamp, so on a run whose
manifests live outside it the registry read as unreadable and the HUMAN check was
skipped in silence - an unregistered second reader passing the one flag that
exists to catch them, with nothing printed to say a check had been dropped.
`manifest_directory()` is now the single rule both tools call, and
`verified_registry()` is how a caller asks WHO without re-deriving WHERE. Two
copies of a path rule are two answers to one question.

**And the separation contract applies where the pair exists.** v7.97 checked every
approved panel, `mine` empty or not, which quietly turned
`DISTINCT_RESOLVER_APPROVER` into "and every approver under this policy holds an
ORCID" - a wider rule than its name, arrived at by accident rather than decided.
A panel nobody hand-resolved has no resolver for its approver to be distinct
FROM. If the wider rule is ever wanted it gets its own name in
`SEPARATION_POLICIES`.

    reverted                                          scenarios that fail
    the preflight resolves the manifest dir its own way 1
    the strict policy checks panels with no resolver   1
    --second compares Reviewer_IDs, not people         1
    --second accepts two unprovable identities         1
    the second file may name another run's cell        1
    the second file needs no date                      1
    a future date is a reading that happened           1
    the second file may answer an unasked question     1
    the stamp fallback is dropped from the one rule    2

## v7.99 — a blank key is not a match, and the registry is read once

Two holes in v7.98's `--second`, both of the same shape as the ones before them:
a check that reads as established and is not.

**A blank key passed as a matching one.** The comparison was `if got and got !=
expected`, which refuses a WRONG `Panel_ID` and accepts a MISSING one - and a
column left out of the header entirely arrives as blank through the same door.
So a second file carrying four columns satisfied a check whose whole claim is
"each row names this run's own panel, unit and cell". Exact equality now, blank
included; a header short of the schema is reported once by name; and a row with
no `Inference_ID` is an answer to nothing.

The fixture was the tell. `_answer()` never filled `Unit_ID` or `Cell_Key`
because nothing had ever looked at them - but `write_inference_template` fills
both, so the fixture was testing a file no reviewer would ever produce. It fills
them now, which is what made the exact-equality change visible at all.

**And the registry was read twice.** `verified_registry()` resolved the path and
re-read the file, which is one read too many: between the finalizer's verified
snapshot and the `--second` identity checks, an autosave, a symlink swap or a
delete puts those checks on rows the decider never saw - and a re-read that
simply FAILED returned None, whereupon the HUMAN and ORCID checks skipped
themselves in silence. This is the hash-then-reopen shape already closed on
decision files, manifests and run outputs; the name said `verified` and the
function verified nothing.

The `Verdict` carries `reviewers` now - the frame the decider was given, or None
on a refusal that never got that far - and `verdict_of()` hands the whole verdict
to `main` so status, problems and registry come from one decision.
`verified_registry()` is deleted rather than renamed. The scenario hooks
`RB.load_manifests` to return a registry on the second call in which the
unregistered second reader IS human: a preflight that re-reads accepts them.

**One guard was removed rather than kept.** A `registry is None` branch in the
`--second` path fired in no reachable state - a verdict that finalizes has
always verified the registry, so None implies the status is already a refusal
and the exit code is already 2. Reverting it broke nothing, which is the
definition of decoration here. What replaced it is the invariant itself, pinned
across four verdicts: every verdict that finalizes carries the rows it decided
against.

    reverted                                          scenarios that fail
    a blank key counts as a matching one               3
    the second file need not carry the key columns     1
    a row with no Inference_ID is not reported         1
    the registry is read again after the verdict       1
    the verdict stops carrying its registry            7

## v8.0 — one read, one snapshot, one moment

The package closed hash-then-reopen four times, one file at a time:
`read_decisions` on the decision files (v7.79), `verify_manifest_inputs` on the
manifests (v7.80), the mark envelope on the run's conditions (v7.80), and v7.99
on the reviewer registry. Each fix was the same sentence — keep what you read
instead of opening the path again — and each was written locally, so the next
caller re-introduced it. This release makes the sentence a function and applies
it to everything left.

**`read_verified_csv(path)` is the whole idea**: one read, hash those bytes,
parse those bytes, return `(frame, sha256, error)`. `verify_run_outputs` uses it
for all five verified outputs and keeps the frames, where it used to call
`file_sha256(path)` and then open the path again.

**The decider stopped re-reading.** `validate_finalization` opened
`figure_values_machine_qc.csv`, `review_queue.csv` and `panel_artifacts.csv`
with `pd.read_csv` after they had been verified - a THIRD read of files already
read twice. It takes them from the verified frames now. So the ledger the run
stamp approved and the ledger the artifact checks run against are the same rows,
and the queue that carries `Review_Mode` and `Review_Subject_SHA256` cannot be
swapped between the hash and the decision.

**And the verdict carries the snapshot out.** `Verdict.reviewers` becomes
`Verdict.snapshot`, a `RunSnapshot` of the registry, the machine rows, the
queue, the ledger and both decision files - every field None until the read that
fills it, so a refusal that never got past the run stamp says so rather than
inviting the caller to open a path itself. `review_preflight.main` derives its
question list, its comparison and its identity checks from that snapshot, and
reads the second file exactly once through the same helper. It prints that
file's SHA-256, because nothing about the second reading is bound into
`Review_Subject_SHA256` or the stamp and the digest is the only record of which
bytes were compared.

Before this, `questions()` re-opened the machine rows, `second_comparison`
opened both decision files twice and `disagreements` a third time. An autosave
mid-run produced a verdict decided from one combination of bytes and a
qualification decided from another - a state that had never existed at any
instant, exiting 0.

The four scenarios that make it visible all swap a file the moment it is read:
the artifact ledger loses its `OVERLAY` row, the queue's `Review_Subject_SHA256`
is replaced, the second decision file is exchanged for a clean one, and the
machine rows grow a phantom reconstructed cell. Each finalizes or passes on the
pre-swap bytes and would refuse on the post-swap ones.

    reverted                                          scenarios that fail
    the run outputs are hashed and then re-opened      3
    the decider re-reads the queue and the machine     2
    the decider re-reads the artifact ledger           1
    the verdict stops carrying the rows it read        8
    the second file is opened by path, more than once  1
    the identity checks re-open both decision files    2
    the question list is derived from another read     1

## v8.1 — the stamp, the ledger and the diagnoses join the snapshot

v8.0 built the snapshot and left four files outside it. Each is the same defect:
hashed one way, interpreted another.

**`run_stamp.json` was the worst of them.** `file_sha256(path)` and then
`json.load(open(path))`: the digest named file A while `Status`, `Run_Mode`,
`Output_SHA256` and `Manifest_Dir` all came out of file B. A DEMO_ONLY run
hashed and an ATTESTED run parsed decides the entire finalization contract from
bytes the result does not name. `read_verified_bytes` is split out of
`read_verified_csv` and `read_verified_json` sits beside it, so the rule now
applies to a format other than CSV; the stamp joins the snapshot. Three
scenarios swap `Run_Mode`, `Status` and `Manifest_Dir` the instant the stamp is
read and require the pre-swap meaning every time.

**The artifact checks re-read the ledger.** `panel_artifacts.csv` was parsed in
the verification loop and opened again three lines later, so the ledger that
DECLARES a panel's artifacts and the ledger the artifact hashes are CHECKED
against were two reads apart. Strike a row from the second and that file stops
being hashed at all while the decision still counts it present. The scenario
does both halves: the `OVERLAY` row goes and the picture it named is
overwritten, and the run is refused.

**A verified output that will not parse was a silence.** Hashing says the bytes
did not change; it does not say they are a run output. Nothing downstream wants
`figure_values_raw.csv`, so a malformed one whose digest matched passed the loop
unmentioned. `RUN_OUTPUT_UNREADABLE` now, by name.

**And the registry was read twice** - once by `verify_manifest_inputs`, once
again beside it to compare against `Reviewer_Registry_SHA256`. It comes from the
verified frames.

**The preflight's diagnoses were the last path readers.** `PILOT.md` tells a
reviewer to require "0 bundle problems" and to check that the answer problems
are all of one kind, so those two lists are judgement inputs rather than
decoration - and they were derived from four more reads. They come from the
snapshot now, and where a field is absent the line says `NOT EVALUATED` rather
than falling back to a path: a snapshot field that is None means the decider
never got that far, and re-reading to fill the gap is the second read this layer
exists to remove. The second file's digest prints in full, because a
16-character prefix is a hint and that digest is the only record of which bytes
were compared.

**Still outside the snapshot,** and named here rather than implied: the
structured artifacts the ledger points at - `IDENTITY_RESOLUTION`,
`INFERENCE_MANIFEST`, `RAW_MARKS`, `POINT_DATA`, `MONO_BAR_GEOMETRY`. Their bytes
are hashed against the ledger and then re-opened by the contract checks that
interpret them. That is the same defect one level down, and it is the next
release rather than this one: it needs an artifact snapshot on `RunSnapshot` and
six contract functions taking it instead of a run directory.

    reverted                                          scenarios that fail
    the run stamp is hashed and then re-opened         2
    the artifact checks re-read the ledger             1
    a verified output that will not parse is a silence 1
    the registry is read again beside the manifests    1
    the bundle diagnosis falls back to the paths       1
    the answer diagnosis falls back to the paths       1
    the second digest is printed as a prefix           1

## v8.2 — the artifact chain joins the snapshot

The last layer. `verify_run_outputs` hashed every file the ledger names and then
each contract check that INTERPRETS one opened it again: the identity
resolutions, the inference manifest, the raw marks, the point cloud and the
geometry file - eight read sites in all, counting `geometry_index_from_run`,
which is the one that decides `IDENTITY_GEOMETRY_ROW_UNKNOWN`. A geometry file
swapped between the hash and the read becomes the evidence for a route it does
not support, with the ledger still naming the file that was hashed.

`STRUCTURED_ARTIFACTS` names the five types whose CONTENT this module reads.
Their bytes are kept from the read that hashed them, travel on
`RunSnapshot.artifacts`, and reach every check through `artifact_data`. A PNG, a
contact sheet or a WPD project is hashed and nothing more - the finalizer never
parses one, so its digest is the whole of what it needs, and keeping the bytes
of a raster would be holding a run's worth of images in memory for nothing.

`artifact_data` reads the path when no snapshot is given, which is what a direct
caller with no verified run behind it needs - `collect_inference_manifests` from
the template command, and the scenarios. `validate_finalization` always passes
the snapshot, so the finalization contract never takes that branch.

The scenarios swap a file the moment verification finishes, which is exactly the
window: hashed against the ledger, and every reader that opens the path again
gets whatever is there now.

    reverted                                          scenarios that fail
    the identity resolutions are opened again          2
    the inference manifest is opened again             1
    the resolver ids are read from the path again      1
    the geometry index is built from the run dir again 1
    the structured artifacts are hashed and not kept   1
    the decider stops passing the artifact bytes       1

TWO GAPS, recorded rather than papered over. `_geometry_route_failures` and
`geometry_index_of` read the same file; reverting the first alone changes
nothing on the current fixtures because the second refuses the swapped run
first, so only one of the two is independently pinned. And the RAW_MARKS join is
not raced: a swapped marks envelope is `RUN_ARTIFACT_MODIFIED` before the join is
reached - a true refusal, and not the question being asked. Both readers use the
snapshot; neither has a scenario that would notice if one stopped.

## v8.3 — the snapshot has an address that the filesystem cannot move

Two ways the snapshot could still be reached around, both closed here.

**The bytes were immutable and the address for them was not.** v8.2 keyed the
artifact snapshot on `os.path.realpath(path)` and looked it up the same way, so
the key was recomputed against the filesystem AFTER verification. Re-point a
symlink in between and the lookup misses - evidence that is present reads as
absent - or lands on another artifact's entry. `artifact_key` is the ledger's own
identity now: type, panel, reference, the run-relative path as recorded, and the
SHA-256 the run put beside it. `artifact_data` takes the LEDGER ROW rather than
a path, and with a snapshot it does not touch the filesystem at all. Containment
and the symlink target are checked once, in the verification loop, on the path
that was actually read.

The point cloud was matched the same way - a value's `Point_Data_Reference`
against `os.path.realpath` of the ledger's artifacts - and now matches on the
recorded path instead.

**And the bundle diagnosis re-read the manifests.** `review_preflight.main`
called `collect_inference_manifests(args.run_dir)` with nothing else, so the ONE
diagnosis `PILOT.md` tells a reviewer to require - "0 bundle problems" - was
built by re-reading the ledger and every inference manifest it points at, two
reads after the verdict printed above it. It takes `ledger=` and `artifacts=`
now, and the preflight passes the snapshot. The path fallback stays for the
template command, which has no verified run behind it.

    reverted                                          scenarios that fail
    the snapshot is addressed by a live realpath again  1
    the snapshot is stored under a live realpath again  1
    the bundle diagnosis re-reads the inference manifests 1
    collect_inference_manifests ignores its ledger       2

The symlink scenario builds a run whose resolution file is reached through a
link inside the run - recorded path and hash unchanged - and re-points that link
to a decoy the moment verification finishes. A mutation that computes the
address afterwards finds the decoy or nothing; the ledger key finds the bytes
that were hashed.

## v8.4 — the two recorded gaps, and the hash on a refusal

v8.2 shipped with two readers taking the snapshot and no scenario that would
notice if either stopped. Both are closed here, and neither needed the fix
weakened to do it — what each needed was a mutation only that reader can see.

**The geometry route.** `_geometry_route_failures` and `geometry_index_of` read
the same file, and v8.2's race rewrote `Geometry_Row_SHA256`, which the SECOND
reader refuses on first — so reverting the first alone was silent. The route
check compares one column the row hash does not cover: rewrite
`Auto_Identity_Method` after verification and every row still hashes to the name
it carries, the index still finds each value's row, and nothing in the run can
see the difference except the check that asks which route the figure took.

**The raw-mark join.** v8.2 recorded this as unaskable — a swapped marks
envelope reads as `RUN_ARTIFACT_MODIFIED` before the join. That was wrong, and it
was wrong for a reason worth writing down: the earlier attempt raced a fixture
whose reader is `BAR_MONO`, which is not in `MARK_JOIN_REQUIRED` and joins
nothing, and a second attempt was run against a directory a previous scenario had
left with a corrupted inference manifest, so the refusal it reported came from
somewhere else. The swap lands AFTER `verify_run_outputs`, so the artifact check
is already satisfied and the join is the only reader left. The scenario runs on
the `LINE_MONO_STYLE` fixture, rewrites every `Mark_Record_SHA256` in the
envelope, and first proves the mutation is visible at all by running the join
over a snapshot taken OVER the swapped bytes — a race whose swapped bytes nothing
reads is decoration.

**And a decision file that could not be read is named by no hash.** The refusal
branch of `read_decisions` fell back to `RB.file_sha256_or_blank(path)`, which
opens the path a SECOND time — so a read that failed produced a stamp saying
`REVIEW_FILE_UNREADABLE` beside a 64-character digest of bytes this run never
saw, and the digest named whatever the retry found. It is the same
hash-then-reopen shape as the whole v8.0–v8.3 arc, one level down, on the audit
record rather than on the values. If the bytes were read and only the PARSE
failed, `digest` is theirs and is still recorded — that half is kept, and pinned
by its own scenario. If the read failed, this run has no bytes to name and says
so.

    reverted                                          scenarios that fail
    the raw-mark join reopens the artifact path        1
    the geometry route check reopens the artifact path 1
    the route the figure took stops being compared     1
    an unreadable decision file is hashed from the path again  1

## v8.5 — one place says what the package runs, and it is checked

Three pieces of documentation had drifted away from the code, and the guard that
exists to stop exactly that had drifted itself.

**Two files went on quoting a package total nobody measured.**
`requirements-intake.txt` and `verify_documented_status.py` both said the package
runs 2244 under the lock file and 2282 with the intake backends. That was true
for one release. `verify_documented_status.py` makes README's total agree with
the measurement every CI run and nothing made the rest of the package agree with
README, so the numbers sat eleven releases stale one directory away from the
guard whose whole subject is stale numbers. Both now point at the two markers in
`README.md` instead of copying them. `requirements-intake.txt` keeps 111 against
149, because that difference is a property of THIS file - it is the gap the
backends open in `test_corpus_intake`, and it is the only number the file is
entitled to state.

**And the guard's own usage was two releases out of date.** Its docstring opened
with a command line that predated `--profile` and named
`<!-- CURRENT_SCENARIO_COUNT -->`, a marker the code has not looked for since
the count became per-profile. The one file whose job is documentation drift was
carrying its own.

Neither is fixed by an edit alone, so both are pinned in `test_reproducibility`,
which is where this package keeps its properties of the tree rather than of a
run:

- a shipped file may not state a package-wide scenario count unless it is one of
  README's current markers or its PARAGRAPH cites a version. Paragraphs, not
  lines: "the tree ran 2282 scenarios while the file said 2184 after v7.43" is
  one dated sentence written over two, and a line-by-line check would call its
  second half undated. README.md is exempt because it is measured; INSTALL.md
  because it is a history and its numbers are records on purpose; the suites
  because their paragraphs are full of fixture numbers, ORCIDs and dates - and a
  suite that drifts is caught by running it
- the invocation the guard's docstring SHOWS has to pass `--profile`, and every
  marker it names has to be one the code reads. The first draft asserted
  `"--profile" in __doc__`, which is true whatever the command line at the top
  says because the flag is explained further down - a check that could not fail,
  caught by reverting the usage line and watching it pass

**And `EVIDENCE_VERIFIERS` says how many it has.** The comment above it still
read "One entry today" with five readers in the table, and the open list still
said the other readers had no verifier. The table is now exactly
`MARK_JOIN_REQUIRED` - a reader that must join its values to its marks must also
be able to re-derive what those marks support - and `test_finalize` pins the two
sets equal, so a verifier removed is a failing scenario rather than a quiet
downgrade. `BAR_MONO` and `SCATTER` are the two that are genuinely not there,
which the next bullet of the open list already scoped correctly and now scopes
alone.

    reverted                                          scenarios that fail
    requirements-intake.txt's stale total restored     1
    the guard's stale total restored                   1
    the usage line without --profile restored          1
    the pre-split marker name restored                 1

## v8.6 — what the pilot rehearsal found

Two defects, both found by running `PILOT.md`'s six steps against real rasters
rather than fixtures: publication 397 Figures 1, 3 and 4, each sliced out of the
397 plan into its own run so the gates are per-figure rather than pooled. Neither
is reachable from a fixture, and neither would have been found by reading the
code.

**Two labels on one row, and one value unreadable.** The overlay placed each
label at `my - 5 + (index % 4 - 1.5) * 13`: a fixed fan added to the mark's OWN
row. That assumes the marks are at the same height. On Figure 4's `P4_HR_MEN` the
POST pair sits 11 px apart and the fan moved the lower one 13 px down - 2 px of
separation for an 11 px glyph, and `FLUID/POST 81.22` was drawn under
`NON_FLUID/POST 83.47`. Step 4 asks a reviewer whether each label sits on the
mark a reader would give it; they cannot answer that about a label they cannot
read, and the fan spreads four bars of equal height correctly while collapsing
two of different height - the failure it exists to prevent, inverted.

`label_row` resolves collisions instead: a label moves a row at a time, and only
when its x range actually overlaps a placed one, so marks far apart across a wide
panel each keep the row beside their own. UP first, because everything above a
bar top is white inside the panel - the old fan got that half right by accident,
`index % 4 - 1.5` being negative for the first two marks of every four. DOWN when
up runs out, because a dense line panel has more labels than the space above its
topmost curve: Figure 1's `P1_MAP_MEN` is 18 labels in a 300-pixel panel, and
upward-only left 12 pairs sharing a row against 0 with the fallback. Measured
across all 13 panels of the three figures: 65 colliding pairs before, 0 after,
and no panel worse.

**And the pre-review check named a cause nothing had looked at.** A run refused
on its run mode, its status or an unreadable stamp is stopped before any check
runs, so it produces no problem ROWS - only a `detail` on the verdict, which the
preflight never printed. Step 3 on a demonstration therefore showed a bare
`RUN_NOT_FINALIZABLE`, `0 refusal(s)`, and a BUNDLE line asserting "this run's
outputs did not verify" when nothing had opened an output. Every worked example
in this package is `DEMO_ONLY`, so the one check `PILOT.md` tells a reviewer to
read before opening a figure named the wrong cause on every rehearsal available
and sent them to re-run a batch whose artifacts were fine. The verdict's detail
now prints as `WHY`, and the two `NOT EVALUATED` lines point at it instead of
asserting a cause. `PILOT.md` step 3 says outright that it cannot be rehearsed on
a demonstration.

**The first scenario was decoration and the harness said so.** It called
`label_row` beside the drawer with the same arguments, so reverting the DRAWER to
the fan left the helper in place and every scenario passed - SILENT. It records
what `draw_panel_overlay` actually asks for, which is where the pixels are
decided.

    reverted                                          scenarios that fail
    the fixed fan restored in the drawer               1
    the downward fallback removed                      2
    the WHY line removed                               1
    the BUNDLE line's asserted cause restored          1

**What the rehearsal could not reach.** No figure in the shipped corpus gets past
step 3: 397's dispersion definition is unresolved, so `UNRESOLVED_ERRORBAR_DEFINITION`
holds every unit of all three figures and the review queue is empty. Figure 3 is
the closest - 8 QC problems, 6 of them that one declaration. Steps 4 and 5 stay
unexercised on a real publication until 127's raster is on disk or a plan exists
for a publication whose caption states its dispersion, which 323's does.

## v8.7 — the figure says where its categories are

The P0 recorded last release, fixed the way that release decided: by reading the
printed x axis.

**What was wrong.** `id323_figure_values.csv` shipped `323|FIG2|DAP` as `B-1,
DI7, DI14, DI19, R1` with `R5` absent. Looking at the figure settles it in a
second: six categories are printed, and `DI19`'s mean is ZERO - it draws an error
bar around the axis and no bar at all. `read_bar_panel` numbers its bars by
nearest DECLARED slot when it is given `x_positions` and by SEQUENCE over the runs
it found when it is not. `build_id323.py` passed none, so the row did not get a
hole, it got SHORTER, and the two bars after the gap inherited the labels before
them. `INSTALL.md`'s open list has named `DI19` since v7.2: the prose was right
for six releases and the shipped artifact was wrong.

**`bar_reader.x_category_columns`** slides a band down the panel and keeps the one
that yields EXACTLY the declared number of ink clusters at nearly even spacing.
That is deliberately not "find the labels": on a panel with a gap the bars CANNOT
produce an even row of six and the printed labels can, so the labels win without
the function having to know which it read. `axis_column` keeps the scan off the y
axis and its rotated label, which are ink at every row and read as one more
category otherwise. All twelve panels of publication 323 come in under a
coefficient of variation of 0.013.

**None rather than a guess.** No qualifying band means the panel does not say
where its categories are, and `build_id323.py` exits BLOCKED instead of falling
back - a grid fitted from the bars that WERE found is the reading that produced
the defect. That is also why the last release did not just borrow a sibling
panel's grid: `P2_PAP` and `P2_SV` share a panel box and their grids differ by
30 px, so "two panels in one box share an axis" is false on this very figure.

**Three cells move and nothing else does.** Regenerated, the worked example
differs from the shipped one in exactly `DI19` (now absent), `R1` (now 0.788 ±
2.719) and `R5` (now 2.974 ± 2.112). Every other value of the twelve units is
byte-identical, which is the tightest confirmation available that the fix is the
one the finding described.

**Two of the first three scenarios were decoration, and the harness said so.**
Reverting the `build_id323` wiring left every suite green, because that script
exits 0 whichever labels it writes - so the pin is on the SHIPPED FILE's cell
keys, in `test_reproducibility`, where this package keeps its properties of the
tree. And removing the uniformity gate changed nothing either: the best-scoring
band still wins, so the gate only decides whether an UNEVEN row is returned or
refused, and nothing exercised that. It has a panel of five bars at arbitrary x
now, which is a continuous axis and not a category one.

    reverted                                          scenarios that fail
    build_id323 stops passing the printed slots        1
    the uniformity gate removed                        1
    (the reader itself refusing) build_id323 BLOCKS, so CI is red

## v8.8 — the plan's slots come from the figure too

`build_id323.py` reads the printed category row since v8.7 and
`make_plan_323.py` did not: it averaged the x of the bars that WERE read and
fitted the rest, which is the same reading one layer up. It announced itself the
first time it met 323 FIG2 DAP - fitting five bars as slots 0..4 put the sixth at
x=2027, outside the panel, and only `POSITION_OUTSIDE_PANEL` stood between that
and a plan declaring a slot that does not exist. It takes `x_category_columns`
now and REFUSES when a panel does not print the number of categories its grid
declares. `test_compile_plan` pins both halves, and reverting to the averaging
version fails the two refusals.

**What still stops `pilot_323.py`, exactly.** The plan compiles and the run layer
accepts it, and two manifest problems are hard rejections rather than flags:

    SOURCE_DOCUMENT_NOT_VERIFIED       the inventory is PENDING
    SOURCE_FIGURE_COVERAGE_INCOMPLETE  4 visible figures, 2 in the manifest

Both are the v7.7 source-completeness rule working as designed, and neither is
something this package can clear by itself. The first needs a person to attest
that they opened the article - the same all-four-or-none environment
`pilot_397.py` already takes. The second needs Figures 3 and 4 inventoried, and
their PANEL counts are a human visual count: their captions say phase
synchronization spectra and PSI values, so `NON_TARGET` is very likely the
disposition, but how many panels each carries is not readable from a figure list
and a number invented here would be indistinguishable from one somebody counted.

So `pilot_323.py` is one attestation and one panel count away, not one design
away. Everything below the inventory is built and tested: 12 panels, 12 units,
`BAR_COLOR`, `SEM` declared from the methods text, and every category slot taken
from the printed axis.

    reverted                                          scenarios that fail
    the plan fits its slots from the bars again        2

## v8.9 — 323 reaches machine QC, and Figure 2 was blocked by a factor nobody declared

**102 values of publication 323 pass the gate.** That is the first real figure in
this corpus to get past `MACHINE_QC_PASSED`, and the only thing between them and a
review queue is now `DEMO_OUTPUT_REFUSED` - the reviewer registry is the
demonstration identity, and registering the person who inspected the figures is an
attestation this package does not make for anybody.

**Figure 2 contributed nothing until this release, for a reason no fixture could
show.** `_series_blocks` gave a single-series panel `Factor_Name=ARM` - 323 has no
arms - and the grid copied `build_id323`'s factor table, which for Figure 2 is
`{TIMEPOINT}` alone. The runner puts a series factor into every `Cell_Key`
whether or not the series is alone, so every value came out as
`ARM=RESPONSE;TIMEPOINT=B-1` against a grid that declared no `ARM`, and the grid
gate refused all of them as `FACTOR_SET_INCONSISTENT`. It is now `SERIES`, which
is what it is, and the grid declares it beside `TIMEPOINT`. The cell count is
unchanged at 6x1. Measured: 72 values passed before, 102 after, and reverting the
grid line puts it back to 72.

**The document record is bounded rather than widened.** The article has four
figures; Figures 3 and 4 are a PSI spectrum and three panels of PSI and spectral
density, and their rasters are not held here. The source layer refuses - in
`compile_plan` and again in `batch_manifests` - to inventory a figure whose raster
the package does not have, which is the right rule. So `Article_Page_Range` says
pages 4-5 and `observed_figure_count` is 2, and within that range the inventory is
complete: a narrower true claim instead of a wider unverifiable one. Whether those
two figures are in scope for this review is undecided and is not decided here.

**`x_category_columns` refuses `count < 2`** instead of returning None. The
contract is a SPACING and one cluster has none, so None read as "this panel does
not say" when the truth was that the function cannot be asked. And the module
docstring said `observed_figure_count` is 0 and that `pilot_323.py` reads a count
from the environment; neither was true of the code and `pilot_323.py` does not
exist.

    reverted                                          scenarios that fail
    count < 2 returns None again                       1
    the grid stops declaring SERIES                    0  -- see below

**THE FACTOR FIX IS NOT PINNED BY A SCENARIO, and that is the honest state.**
Reverting it drops the run from 102 values to 72, which is a measurement taken by
hand: nothing in the suite builds this plan, compiles it and runs it, so the suite
stays green either way. `test_compile_plan` checks `_positions` with prepared
centres and no more. What is needed is an end-to-end scenario -
`make_plan_323.build()` -> `compile_plan` -> `run_batch`, asserting zero
`FACTOR_SET_INCONSISTENT`, `DAP/DI19` absent and `DAP/R1` at 0.788 - and, better,
a plan-validation refusal (`PLAN_PANEL_FACTOR_SET_MISMATCH`) so the factor grains
are compared before a raster is opened rather than after. Both are the next
release. Until then this fix rests on one hand measurement, which is exactly the
kind of thing this package refuses to call verified.

**Also still open on `x_category_columns`:** `band`, `step` and `gap` are pixel
constants tuned to 323's render DPI. Fine for a versioned raster and wrong for a
corpus-wide proposer, where they would have to be relative to glyph height or
panel scale.

## v9.0 — the two factor grains are compared before a raster is opened

v8.9 shipped a fix that nothing pinned: declaring `SERIES` in Figure 2's grid took
publication 323 from 72 values to 102, and reverting it left the suite green
because no scenario built that plan and ran it. Both halves are closed here, and
the better half turned out to be the earlier one.

**`PLAN_PANEL_FACTOR_SET_MISMATCH`.** The runner writes a panel's series factor
AND its position factor into every `Cell_Key` - whether or not the series is alone
- and the grid gate then requires the value's factor set to equal the grid's
exactly. Nothing compared the two at plan time. So a panel naming a factor its
unit's grid did not declare compiled cleanly, ran, read its marks off the raster,
and had every value of that panel refused as `FACTOR_SET_INCONSISTENT` - a
diagnosis of the VALUES rather than of the declaration that caused them, arriving
after all the work. `compile_plan` now compares the two sets and refuses, naming
both, before a raster is opened. 323's Figure 2 spent a release like that and 30
values were thrown away after the reading.

**And the whole chain runs in the suite.** `test_compile_plan` builds 323's plan
off its own rasters, validates it, compiles it and runs the batch, asserting 102
values past the gate, 107 read, 2 QC problems, and `DEMO_OUTPUT_REFUSED` with
nothing written. The count lives in the stamp's `Detail` because a refusal zeroes
`Values_Machine_QC_Passed` - the run kept nothing, so the field for how many it
kept says 0, and the sentence is the only place the gate's own tally survives.

**Reverting the grid declaration now fails twice** - the plan validation and the
compile - instead of failing nothing. The 102-against-72 measurement is no longer
the evidence; it is a consequence.

    reverted                                          scenarios that fail
    the grid stops declaring SERIES                    2
    a panel names a factor its grid does not           1
    a grid drops a factor its panels name              1

**What is left on 323 is one attestation.** The plan builds, validates, compiles
and runs; 102 of its 107 values pass the gate; the five that do not are the cell
the figure does not print and the four this package has recorded as unpaired since
v7.2. `DEMO_OUTPUT_REFUSED` is the only thing standing between those values and a
review queue, and it lifts when the person who inspected the figures is
registered. That is now a claim the suite makes rather than one this release
asserts.

## v9.1 — a unit names the panel that fills it

**Two panels of one figure could exchange their units and nothing would notice.**
`panel.read.unit_id` and `unit.panel_id` say the same thing and only the first
existed. Swap them and: each panel's measurements are still right, every value
still matches its own mark hash, the factor sets and cell counts are identical,
and both units are still filled by exactly one panel. Reproduced on
`plan_397.json` - `validate_plan` returned zero problems - and the consequence is
that two panels' numbers arrive under each other's outcome with nothing in the run
disagreeing. It is the heading exchange this package has caught four times at
other grains, surviving at the panel-unit boundary, and it was silent by
construction: a swap preserves every invariant that was being checked.

`unit.panel_id` is now part of the plan schema and three refusals stand on it:

    PLAN_UNIT_NAMES_NO_PANEL       a unit filled by a panel that it does not name
    PLAN_PANEL_UNIT_MISMATCH       the two sides name different panels
    PLAN_PANEL_UNIT_VIEW_MISMATCH  the unit belongs to another figure

**And one panel per unit.** The unit calibration is built from the FIRST panel
that claimed the unit, so a second claimant contributes its marks to the unit and
its axis to nothing - values calibrated against a panel they were not measured in.
`PLAN_UNIT_FILLED_TWICE`.

Both plan generators emit the key and `plan_397.json` is regenerated; the diff is
26 `panel_id` lines and nothing else.

    reverted                                          scenarios that fail
    the binding check removed                          3
    one-panel-per-unit removed                         1

**The other three items of the review are NOT in this release.** Source-document
bytes are still unhashed, the run stamp still zeroes its machine-QC tally on a
refusal, and the plan still compares factor NAMES without their LEVELS. Each is
real; none of them can put a right number under a wrong outcome, which is why this
one went first alone. *(All three are closed in v9.2, which is where the third
one turned out to be able to do exactly that. This paragraph is left as it was
written: it is the record of what was true at the time.)*

## v9.2 — the review's last three items, and the third one found Figure 5

**An inventory now names the bytes it was taken from.** Every raster in this
package has been hashed since the first release, and the article they were cut
out of was a filename. So "publication 397 has five figures and these are they"
was a claim about the string `397.pdf`: a preprint and its version of record
produce the same manifest, the same figure count, the same panel counts and the
same attestation, and the inventory reads as verified against whichever one the
reviewer happened to have open. `Source_File_SHA256` is now part of the
`source_document_manifest` schema and of the plan document, and four refusals
stand on it:

    BAD_SOURCE_FILE_SHA256                  neither a digest nor NOT_HELD
    SOURCE_DOCUMENT_HASH_MISMATCH           the file on disk is a different article
    SOURCE_DOCUMENT_FILE_NOT_FOUND          a digest claimed for bytes nobody holds
    SOURCE_DOCUMENT_BYTES_HELD_BUT_UNHASHED NOT_HELD about a file under file_root
    PLAN_DOCUMENT_BYTES_UNDECLARED          a plan that does not say, at plan time

**THE DIGEST IS OVER THE WHOLE FILE, AND `Article_Page_Range` IS UNCHANGED.**
The two claims are deliberately independent. Publication 323's document record
covers pages 4-5 of a four-figure article whose other two rasters this package
does not hold (v8.9), and the honest form of that is a whole-file digest beside a
narrower range - not a digest of two pages, which is a hash of an artefact no
publisher ever issued and which nobody could reproduce from the PDF they have.
The range says what was inventoried; the digest says what it was inventoried
*from*.

**`NOT_HELD` is a state, not a blank.** This repository ships rasters and no
PDFs, so 323 and 397 both declare it, and their run stamps say
`Source_Document_Bytes_Bound=NONE`. Recorded rather than left empty, because a
blank column reads as "nobody got round to it" and this one has to read as "the
bytes behind this inventory are not here". It is not a free pass either:
`SOURCE_DOCUMENT_BYTES_HELD_BUT_UNHASHED` refuses a row that says NOT_HELD about
a file the corpus is holding, which is what stops every producer that would
rather not hash its document from writing NOT_HELD and meeting no disagreement.
Two more bindings make the digest reach the rasters rather than sit beside them:
`DUPLICATE_SOURCE_DOCUMENT_BYTES` (one article inventoried under two IDs counts
its figures twice in every coverage check below it) and
`SOURCE_FIGURE_DOCUMENT_FILE_MISMATCH` (a figure carries its own `Source_File`,
so it could name a different article while pointing at a document row whose bytes
are hashed).

**Two tallies, because a refusal separates them.** `Values_Machine_QC_Passed` is
how many gate-passing values a run KEPT, and a refusal keeps none - so on
`DEMO_OUTPUT_REFUSED` it is 0, which is correct and was the only tally the stamp
had. The gate's own count survived in the `Detail` sentence and nowhere a program
could read it, and the proof of the cost is in the suite: `test_compile_plan`
asserted 323's 102 values by matching a regular expression against English prose.
`Values_Gate_Passed` is now a field, the scenario reads it, and the stamp schema
is `run-stamp/8`. `Source_Document_Bytes_Bound` is written on every outcome for
the same reason - a refused run still says what its inventory would have rested
on.

**And the plan compares factor levels, which is where the third item stopped
being harmless.** v9.0 compared the two factor SETS before a raster is opened;
that compares headings. A panel whose TIMEPOINT positions are `0_30..6_00`
against a grid declaring `0:30..6:00` matches on `{ARM, TIMEPOINT}` and shares
not one cell with it, and the runner writes the level into every `Cell_Key` - so
the marks are read off the raster and refused one by one as
`UNDECLARED_FACTOR_LEVEL`, the same after-all-the-work diagnosis v9.0 removed one
grain up. `PLAN_PANEL_FACTOR_LEVEL_UNDECLARED` refuses it at plan time.

**Its first catch was in `plan_397.json`.** Figure 5's two curves are the two
individuals its caption names, and they were declared `factor=ARM, level=Y01` and
`level=Y07` against `G_HDT`, whose ARM levels are `FLUID` and `NON_FLUID`. The
factor names matched the grid exactly and not one of the twenty-four cells
existed. It survived nine releases because the fluid/non-fluid split in Figure 5
is between its two PANELS and what varies inside a panel is which person is
drawn - so calling a subject an arm was consistent at the grain anything looked
at. Figure 5 is `NO_SUMMARY_STATISTIC` and MANUAL, so no value was ever filed
under a cell that does not exist; had those panels been AUTO, every reading would
have come back refused. Both units now name `G_P5_SUBJECT`, a grid of
`SUBJECT x TIMEPOINT`, and the old declaration is a scenario.

The reverse direction is NOT checked, on purpose: a level a grid declares and no
mark fills is an EMPTY cell, which the gate reports against the unit as
`FACTOR_LEVEL_MISSING` once the reading is in, and 323 has a legitimate one - the
cell its Figure 2 does not print, recorded since v7.2. Refusing that at plan time
would refuse 323.

    reverted                                          scenarios that fail
    the document digest check removed                  10
    the required column removed                         1
    the NOT_HELD guard removed                          1
    the duplicate-bytes check removed                   1
    the figure-document file binding removed            1
    the plan-time digest check removed                  3
    the gate tally field removed                        4
    the level comparison removed                        8
    Figure 5 restored to ARM against G_HDT              2

**What this does NOT close.** `corpus_intake` has computed
`Source_File_SHA256` in its ledger since the intake layer existed, and there is
still no emitter that turns a ledger row into a `source_document_manifest` row -
`inventory_rows` produces figure rows only. So the digest is hand-carried by
whoever writes the plan, which is the same shape of gap the raster hash does not
have (the compiler reads that off the bytes). Until that emitter exists,
`Source_Document_Bytes_Bound=ALL` is exercised by fixtures and by nothing in the
shipped corpus. And `NOT_HELD` is still a declaration a producer makes about
files outside `file_root`: the guard can only ask the corpus what it is holding.

*(This section also removes two duplicate `## Still open` headings that had
accumulated above it.)*

## v9.3 — the plan's protections come down to the grain a third party writes

**v9.1 and v9.2 both closed real defects in `validate_plan`, which protects
manifests the compiler wrote and nothing else.** A hand-written set, a migrated
set, a set from somebody else's producer, or `finalize_batch` reading a directory
whose plan nobody has - none of those pass through the plan validator. So the
panel-unit exchange v9.1 caught was still live one layer down: `unit_manifest`
carried a free-text `Panel` LABEL and no `Panel_ID`, which is to say the
manifests contained no statement of which panel each unit was. Exchange the
`Unit_ID` of two panels of one figure in such a set and every check passes - the
measurements are right, each value matches its own mark hash, the factor sets and
cell counts are identical - and the SAP panel's correct numbers arrive under the
DAP outcome. `Panel_ID` and `Source_Panel_ID` are now part of the unit schema and
`validate_batch_manifests` requires a bijection:

    UNIT_NAMES_NO_PANEL                 the unit does not say which panel fills it
    UNIT_PANEL_NOT_FOUND                it names a panel the manifest does not have
    PANEL_UNIT_MISMATCH                 the two rows name each other's panel
    PANEL_UNIT_SOURCE_PANEL_MISMATCH    they disagree about the physical panel
    PANEL_UNIT_VIEW_MISMATCH            they disagree about the figure view
    UNIT_FILLED_TWICE                   two panels read one unit

The last one is v9.1's one-panel-per-unit rule arriving at the same grain, and it
retired a fixture: `test_run_batch` had a two-panels-one-unit batch pinning what
the runner did with it. That set cannot run any more, so the scenario now pins the
refusal and the run-time behaviour it used to cover is re-pinned on two panels
with a unit each.

**A document could satisfy its own figure count with a figure missing.** Source
completeness compares `Observed_Figure_Count` against the NUMBER OF ROWS under
the document, so three rows satisfy a count of three - including rows numbered
FIG1, FIG2 and FIG2 while the article's FIG3 is absent. The two FIG2 rows carry
different `Source_Figure_ID`s and different rasters, so the duplicate-ID check
never sees them, and the one thing this layer exists to prevent - a whole figure
disappearing before the panel check begins - happens with every count agreeing.
`DUPLICATE_SOURCE_FIGURE_NUMBER`, on `(Source_Document_ID, normalized
Figure_Number)`: `FIG2`, `fig 2` and `Fig. 2` are one figure, and an article and
its supplement may both have a Figure 1. Raster-hash uniqueness would have been
the wrong rule - two figures can be cropped from one page raster.

**A unit nobody fills could pass.** `PLAN_UNIT_HAS_NO_PANEL` asked whether any
panel read the unit's VIEW, which is a weaker question than the one it means: a
unit belonging to a view another panel occupies had zero claimants and compiled -
declared, priced by a grid, filled by nobody. The contract is now
`len(claimed[unit_id]) == 1` for every unit, counted against the panels that name
it.

**And two plan-time checks about what a `Cell_Key` can hold.**
`PLAN_FACTOR_ON_BOTH_AXES` - the runner builds one `Cell_Key` mapping from the
series factor and the position factor, so a factor naming both axes is written
twice and one of the two readings is lost; with a single series it is lost
silently, because nothing downstream is then missing a cell to complain about.
`batch_manifests` has refused this since the series layer existed, and saying it
at plan time reports the defect against the line that has it rather than against a
generated CSV. `PLAN_DUPLICATE_FACTOR_LEVEL_ASSIGNMENT` - two marks of one panel
declaring the same `(factor, level)` are two readings of one cell. The grid gate
catches that as `FACTORIAL_CELL_DUPLICATE` after both have been measured, and
which of the two numbers the cell should hold is not a question it can answer; the
declaration says the same thing twice, which is answerable here.

**A false refusal v9.2 introduced.** `fig_cell_key` upper-cases the factor AND
the level, and `grid_engine` upper-cases what a grid declares - so `Pre` in a grid
against `PRE` on a mark is one cell downstream. v9.2's new level check compared
the text as written and would have refused that plan: not a wrong number, but a
contract that differed between two layers of one package, and the kind of
difference that teaches people to work around the stricter layer. Both sides are
upper-cased now, and a scenario asserts the two spellings really do produce one
`Cell_Key`.

    reverted                                          scenarios that fail
    the manifest bijection removed                      8
    Panel_ID dropped from the unit schema               25
    the duplicate figure-number check removed            5
    the zero-claimant count reverted to the view test    2
    the plan-time axis-overlap check removed              1
    the duplicate-cell assignment check removed           4
    the level case normalization reverted                 1

**What this does NOT close.** The inventory's SCOPE is still a free-text
`Article_Page_Range`. v9.2 bound the document's BYTES; nothing can check that the
range names pages the file has, that a figure's `Source_Page` falls inside it, or
that a partial record declares itself partial - `Scope_Type`, `Start_Page`,
`End_Page` and a parent document ID would be the structure for that, and it is a
schema change with a migration rather than a check. The grid-level direction of
the level comparison is still deliberately unchecked (see v9.2). And the document
digest still has no producer inside the package.

## v9.4 — a run is finalized under today's contract, not the one it was made under

**Every contract this package has added since a run was produced was a contract
that run escaped.** `verify_manifest_inputs` answers one question - are these the
manifests the run validated - and it answers it well: frame hashes for all twelve
inputs, compared as frames so a re-saved CSV is the same manifest. It says
nothing about whether what they DECLARE is coherent, because the run's own
validator answered that, in whatever version it happened to be. Nothing in
`finalize_batch` re-ran `validate_batch_manifests`.

So a completed run from a v9.0-era producer could carry the panel-unit exchange
v9.1 closed in the plan layer and v9.3 closed in the manifests: two panels of one
figure with their units swapped, every measurement right, every hash right, and
one panel's numbers under the other panel's outcome. The finalizer confirmed the
hashes and, given an approval, wrote them into `figure_values_accepted.csv` - the
one file this whole package exists to be careful about. The current validator now
runs over the VERIFIED frames, and a run that does not satisfy it is refused with
its own status rather than a borrowed one:

    RUN_MANIFEST_CONTRACT_INVALID   the manifests are the ones this run
                                    validated and they do not satisfy the
                                    contract this package holds now

It is a separate status from `RUN_ARTIFACT_MODIFIED` deliberately. Nothing was
modified - the sentence "the run this approval refers to is not the run on disk"
would be false, and what such a run needs is a re-run, not an investigation into
who edited what. `check_files=False`: this is a check on what the manifests say,
and re-reading rasters would make an approval depend on a corpus directory the
approver does not need to have.

**And `Figure_Number` was normalized by stripping punctuation, which is not the
same as canonicalizing it.** `FIG2` and `Fig. 2` collapsed; `Figure 2` became
`FIGURE2`, `2` stayed `2`, and `图 2` became `2`. So the v9.3 duplicate check -
whose whole purpose is that a document cannot satisfy its own
`Observed_Figure_Count` with one figure listed twice while another is missing -
reopened on a spelling: two rows for Figure 2, one written `Fig. 2` and one
`Figure 2`, counted as two figures. Not hypothetical for this corpus:
`corpus_intake.CAPTION_RE` accepts `Fig`, `Figure`, `图` and `圖` because the China
Astronaut Research and Training Center papers print `图 1.` with an English
`Fig. 1.` underneath, so both spellings of one figure are in circulation for one
article. `BM.normalize_figure_number` is now the one definition - NFKC, strip the
label, keep the panel suffix - so `2`, `FIG2`, `Fig. 2`, `Figure 2`, `图 2`, `圖2`
and `２` are one figure and `Figure 2A` is not `Figure 2`.

**Two smaller halves of v9.3 finished.** `DUPLICATE_FACTOR_LEVEL_ASSIGNMENT` is
now checked in the manifests as well as in a plan: two series (or two positions)
of one panel declaring one `(Factor_Name, Factor_Level)` are two readings of one
cell, and the grid gate only says so after both marks have been measured - when
which number belongs in the cell is no longer a question it can answer.
`UNIT_NAMES_NO_SOURCE_PANEL` refuses a blank `Source_Panel_ID` on a unit: v9.3
compared the physical grain only when both sides filled it in, so the second half
of the pairing could simply go unstated, and a column that may be blank does not
make the claim the schema makes.

    reverted                                          scenarios that fail
    the finalizer's re-validation removed                4
    figure-number label stripping reverted               7
    the manifest duplicate-cell check removed            3
    the blank Source_Panel_ID check removed              1

**What this does NOT close.** The re-validation is `check_files=False`, so a
finalization still does not re-verify that the rasters on disk are the ones the
inventory hashed - the review subject covers the panel's own raster, which is the
narrower true claim. `Article_Page_Range` is still free text (see v9.3). And the
finalizer now depends on the manifest validator staying decidable from the
manifests alone: a future check that needs the corpus would have to be split
rather than added, or every historical run becomes unfinalizable for want of a
directory.

*(v9.4's sentence was "a run is finalized under today's contract". It was true of
the source and run-manifest contract and not of the data contract, which v9.5
finishes.)*

## v9.5 — and the data half of today's contract

**`validate_batch_manifests` is never given `grid_definitions`.** So the
re-validation v9.4 added cannot see the one thing a grid is for. A historical
producer whose grid declares `ARM = CONTROL | TREATED` and whose series declares
`ARM=PLACEBO` writes values whose `Cell_Key` is `ARM=PLACEBO`: the marks agree
with the values, the values agree with the manifests they were built from, every
hash in the run stamp matches, and there is no arithmetic signature anywhere in
it. The current gate says `UNDECLARED_FACTOR_LEVEL` in one line - and the
finalizer never asked it. Alongside that code sit `FACTOR_SET_INCONSISTENT`,
`FACTORIAL_CELL_DUPLICATE`, `DUPLICATE_FACTOR_LEVEL`, `BAD_LEVEL_ORDER`,
`UNRESOLVED_ERRORBAR_DEFINITION`, `BAD_DISPERSION_TYPE`, `N_INVALID` and the rest
of the data contract, all of them the version in force when the run was made.

`GE.fig_validate_bundle` now runs again over the verified run, and a unit that
fails it withholds its panel: `RUN_GRID_CONTRACT_INVALID`. Three choices make it
a check rather than a blunt instrument, and each of them is a scenario.

**The gate is re-run on the RAW values**, which is the frame the runner gave it.
Re-running it on `figure_values_machine_qc.csv` would judge cell coverage against
a file the run's own gate had already filtered, so every unit that legitimately
lost a cell would come back `FACTORIAL_CELL_MISSING` - a refusal manufactured by
the re-check rather than found by it.

**Only a unit with something left to lose is charged.** A run whose own gate
refused every value of a unit has nothing in `figure_values_machine_qc.csv` for
it, so no approval can turn those values into accepted ones. Publication 397 is
that run today - every panel QC_FAILED for an unresolved SD/SEM - and charging its
panels for failing today's gate as well would fill the problem list with refusals
naming panels nobody can act on, which is how a problem list stops being read.

**The figures frame is rebuilt the way the runner built it.** `run_batch` fills
`WPD_Project_File` on the figure from the projects its own panels wrote - an
automated run has no human-saved project, so it saves one - and the copy in the
manifest directory has that column blank. The first version of this check re-ran
the gate against the manifest copy and reported `MISSING_PROVENANCE` on every
digitized unit of every healthy run: it refused two of this suite's own fixtures
before it refused anything real. The projects are named by the run's own verified
value rows, so they are read from there.

    reverted                                          scenarios that fail
    the finalizer's grid re-run removed                  2
    the at-risk restriction removed                      1
    the figures-frame rebuild removed                    2

**What this does NOT close.** `check_files=False` here too, for the same reason:
an approval must not depend on a corpus directory the approver does not have. So
the re-run gate does not check that the rasters and point files the manifests name
are on disk - the review subject covers the panel's own raster, and
`Point_Data_Reference` existence is checked at run time and not again. And the
same dependency v9.4 introduced now covers the gate as well: a future data-contract
check that needs the corpus would make every historical run unfinalizable for want
of a directory, so it would have to be split rather than added.

## v9.6 — the candidates are gated, and the fingerprint is re-derived

**v9.5 gated the raw file, and the raw file is not what gets accepted.** It has
to be the frame the gate sees - cell coverage can only be judged against the whole
reading - and for a run this package produced that is also a check on the
candidates, because `figure_values_machine_qc.csv` is a row subset of the raw file
and nothing else. A foreign producer is under no such obligation, and the
finalizer exists for foreign producers. The bypass: ship a raw file that passes
today's gate (`ARM=CONTROL`, `ARM=TREATED`) and a candidate row filed under
`ARM=PLACEBO`, matching a series manifest that also says PLACEBO. Marks agree with
values, values agree with the manifests they name, every hash agrees, the raw gate
is clean, and the row that would be accepted sits in a cell no grid declares.

    MACHINE_QC_NOT_DERIVED_FROM_RAW   a candidate that is not in the raw file
                                      it claims to be a subset of

Counted as a multiset, so two identical candidates against one raw row is one
value counted twice. And every candidate is put through today's gate on its own
row - only the row-scoped problems, because a `unit:` problem here would be about
cells the run's own gate legitimately dropped, which is the refusal v9.5 exists to
avoid manufacturing.

**And the strongest sentence in the README rested on the producer's arithmetic.**
"The approval names the extraction, not the panel" holds because
`Review_Subject_SHA256` covers the values, every manifest, the artifacts and the
environment - and the finalizer only ever compared the APPROVAL's copy of that
hash against the QUEUE's copy. Both are written by the same producer. A producer
whose formula leaves the Mean out writes one subject for two runs with different
numbers, and an approval of the first finalizes the second: every hash in the
second run's own stamp agrees, its marks and values agree, and the person who
signed was looking at a different number. The subject is now RE-DERIVED with
`RB.review_subject_sha256` - the same function the runner calls - from the
verified run-manifest row, the verified candidates, the manifest hashes and
environment the stamp records, and the verified artifact ledger:

    QUEUE_REVIEW_SUBJECT_INVALID   the queue's fingerprint is not a fingerprint
                                   of this run

**Which found that the subject was not recomputable at all.** The material line
for a value was `"%s=%s" % (k, row.get(k, ""))`, so a Python `None` in the
runner's own dict hashed as the four characters `None` while the CSV a reviewer
opens - and the CSV the finalizer re-reads - has an empty cell there. Every
BAR_MONO panel in this suite has such a cell (`Errorbar_Lower`), so the first
version of the re-derivation refused two healthy fixtures. A fingerprint only its
producer can compute is not a fingerprint, so `_blank_text` now makes `None` and
NaN both the empty string, and the subject is over the text the files carry.

**This expires some approvals, and that is the migration.** A run produced before
v9.6 whose candidates carry an empty numeric cell has a queue fingerprint computed
the old way, so today's finalizer refuses it with
`QUEUE_REVIEW_SUBJECT_INVALID` - correctly, since nobody but that run can check
it. Re-run and re-approve; there is no back-fill worth writing, because computing
the old hash to match it would be reinstating the thing the check is for.

    reverted                                          scenarios that fail
    the candidate derivation check removed               1
    the candidate row gate removed                       1
    the queue subject re-derivation removed              3
    the None-is-blank normalization reverted             1

**What this does NOT close.** The re-derived subject uses the manifest
hashes and the environment RECORDED IN THE STAMP rather than recomputed from the
manifests themselves - the manifests are verified against those same recorded hashes a few
lines earlier, so the stamp is not being trusted for their content, but a stamp
whose `Environment` was never true of any machine is still a stamp this check
takes at its word. And the artifact ledger's own rows are the subject's artifact
material: their bytes are verified, and what type each artifact IS remains the
producer's statement.

## v9.7 — the queue does not decide how much a reviewer has to check

**`Review_Mode` chooses the confirmations an approval must carry, and the queue is
the producer's file.** `OVERLAY` asks for `Marks_Checked`;
`BAR_MONO_GEOMETRY_RESOLVED` asks for that plus `Axis_Labels_Checked`,
`Calibration_Checked` and `Identity_Checked`. The review subject does not cover
the mode - it hashes the artifacts and the values - so downgrading a geometry
panel's queue row to `OVERLAY` leaves every fingerprint in the run intact, and an
approval asserting one thing finalizes a panel whose axis and calibration nobody
confirmed. Publication 127's pilot is exactly a `BAR_MONO_GEOMETRY_RESOLVED`
review, so this is the mode the first real reviewer will be working in.

The mode is now re-derived from the run - which artifacts the verified ledger
holds for the panel, whether the verified `identity_resolution.csv` names it,
whether its run row has a project - by the same four-way choice `run_batch`
makes: `QUEUE_REVIEW_MODE_CONTRADICTS_RUN`.

**And one queue row per panel.** `review_mode` and the expected-subject map are
both dict comprehensions over the queue, so two rows for one panel resolve to
whichever comes last - and the two rows may declare different modes. That is the
defect `DUPLICATE_REVIEW` already refuses in the decision file, one file upstream:
`QUEUE_DUPLICATE_PANEL`. Both orderings are scenarios, because the whole point is
that row order decides nothing.

    reverted                                          scenarios that fail
    the mode re-derivation removed                       2
    the queue duplicate check removed                    2

**What this does NOT close.** The derived mode is only as good as the ledger's
`Artifact_Type` column, which is the producer's statement about what each verified
file IS - a run that labels its calibration panel `OVERLAY` derives `OVERLAY` and
agrees with itself. The bytes are hashed; the type is not derivable from them.

## v9.8 — an outline is ink the bar runs into

**A real figure read its own error bars as its means, and said nothing.** The
first pilot outside the two worked examples is publication 177, whose Figure 3 is
what this pipeline is for: three groups by three test days, a bar and a whisker
per cell, and a caption that states the dispersion ("Values are means ± SE").
`BAR_COLOR` read its women/preflight cell as **314 against a printed 205** - 53%
high, with no refusal and no flag.

The reader takes the end of the series' colour mask as the end of the bar. That
is the bar's top only while the whisker is drawn in some OTHER colour. Greyscale
print draws a black bar's error bar in the same ink, and then the end of the mask
is the whisker's TIP: the reader recovered the real top by looking for a wide row
within 70 pixels above it, found none 93 pixels away, and fell back to the tip.

The obvious repair - look further - is what the second fixture is for. Widen the
window and the first wide row above the bar is a SIGNIFICANCE BRACKET, a rule
belonging to a p value, floating over the panel in the same ink. Its short
descenders even join two bars into one run, which then reads as a single bar
whose top is the bracket.

Two rules, and neither is a distance:

    a bar's column carries ink AT THE BASELINE      a bracket floats
    an outline is ink the fill RUNS INTO            a bracket has white under it

The second is measured rather than chosen: over publication 323's 72 frozen bars
the run from outline into fill has no unmarked row in 70 of them and exactly one
in the other two, against more than a hundred for the bracket. Two orders of
magnitude apart, so the line is two rows.

**And the ink level is the figure's, not the reader's.** `dark` was `mean < 110`,
tuned on one publication. 177 draws its whiskers at grey 128, so at the default
they are not ink at all and every cell of the figure came back with no
dispersion. `threshold` is now declarable for BAR_COLOR as it already was for
BAR_MONO and the line readers, and `bar_reader.read_bar_colour_panel` is the
entry point that keeps `READER_OPTIONS`' promise - every option applying to a
mark type names a parameter of that mark's reader.

    reverted                                          scenarios that fail
    the outline-connectedness rule removed              4
    the baseline-anchored columns removed               1
    the declarable ink threshold ignored                1

Publication 323's 72 frozen values are unchanged, and that is the point of the
release: `make_whisker_fixture.py` draws the three panels this needed - a
same-colour whisker, the same with a bracket over it, and a whisker at grey 128 -
so the rules are pinned by figures rather than by the reader's own last output.

**What this does NOT close.** 177 still does not pass machine QC: ten of its
eighteen cells now read with means and dispersions that match the print, and two
panels still lose a series to the antialiased edge of its neighbour. That is a
colour-separation question and it is next. `x_category_columns`' band/step/gap
are still DPI-bound, and so is `max_whisker_px` - 177 declares 180 at 600 dpi to
mean the same distance the default means at 300.

## v9.9 — a bar is a solid block of ink joined to the baseline

**The third group of a greyscale figure was reading everybody else's edges.**
v9.8 got publication 177's means off its whiskers and left two cells plainly
wrong: `NE/landing day/nonpresyncopal men` came back **656 pg/ml against a
printed 380**, and `EPI/landing day` **100 against 24**. Both are the dark grey
group, and the cause is not the reader's arithmetic — it is what a mask means on
a page that was rasterised and then JPEG'd.

A three-group palette is `#000000`, `#b2b2b2`, `#666666`. The middle one is 102,
and 102 is a grey the ramp from black to white passes through, and the ramp from
light grey to white, and the ringing around every hard edge. So the third
group's mask marks the other two groups' edges, the baseline rule's own fade,
the descenders of the significance brackets, and specks of paper where nothing
is drawn. Every one of them has some pixel near the axis in its column, so `a
bar grows from the baseline` accepted them all, the fragment-merge rule joined
them, and one bar came back as a run **540 pixels wide** — three bars and the
gaps between them — read at the top of whichever bar was tallest.

Narrowing the declared `colour_tolerance` from 25 to 8 was worth doing and did
not fix it: the fills are one flat value each, so a narrow net is the accurate
one, and it took the cells read from 10 to 18 — but the smear is *at* 102, not
near it. What separates a bar from a smear is not how close the colour is.

Three statements, none of them about a publication, a colour or a distance:

    ink not JOINED to the baseline is not part of a bar    dust is not joined
    a column of the RULE is not a column of a bar          the rule spans the row
    a run with no ink above the rule needs an error bar    or it is the rule

The third exists because the second would otherwise delete two real readings.
Publication 323 has bars whose value is zero: `-0.318` and `0.421`, two and three
rows of colour lying inside the line with a whisker standing on them. A rule-only
run is a bar when something is drawn on it and the rule's own fade when nothing
is — which is the same stem test every other whisker gets, not a new one.

    reverted                                          scenarios that fail
    ink joined to the baseline -> the column test       5
    the rule's rows count as bar columns again          6
    a rule-only run kept with no error bar on it        7

**Publication 323 is unchanged: 107 values, every mean and every dispersion
identical to the digit, and `crosscheck_id323` still AGREEs on all 72 frozen
bars.** Bar centres move by a pixel on eleven of them, which is the run no longer
including the furniture beside it; the width of a bar is not a number this
package records.

`make_greyscale_fixture.py` draws what was needed, and it is a JPEG on purpose.
Written as a PNG the same drawing has clean edges and none of this happens — the
trap is in the file format the source is actually in, at quality 80, the
comfortable end of what a publisher embeds. It also carries a **legend key**
inside the axes: a solid block of a series' exact colour with no bar under it,
which is the plainest case there is of ink that is not a bar, and the one the
join test is for. Reverting that test alone puts the key back in the record as a
bar at 92.25 on a panel whose tallest bar is 55.

**What this does and does not close for 177.** All eighteen cells now read, each
with a mean that matches the print and a stem-confirmed dispersion; three pass
the value gate where none did. The nine remaining problems are all the same
check, `DISPERSION_IMPLIES_SKEW`, and it is right to fire: the caption gives
`n = 4`, `6` and `22` by group and a unit carries one `N_Outcome`, so every cell
is being checked against the total, 32. The gap is the manifest's, not the
figure's — there is no per-series n field — and the plan says so in `n_source`
rather than papering over it. That is a schema decision and it is not made here.

## v9.10 — a whisker the reader cannot finish reading is not a dispersion

**Verifying v9.9 found two dispersions that were measured off nothing.** Every
one of publication 177's eighteen means lands on its own bar - checked not by a
second reader (two attempts at one reproduced the reader's own traps, which
proves nothing) but by a predicate asked of the figure at the row each number
points to: the outline stroke is the ink that is not the fill, and its centre is
where the claim should sit. Sixteen of the eighteen dispersions land on their
cap the same way, within 0.6 pixels. Two did not, and both were produced by one
line:

    cap_c = (caps[0] + caps[-1]) / 2.0 if caps else float(far)

`far` is the far end of the STEM. When no row near it is wide enough to be a
cap, the reader reported the stem's own end as one - and stamped it
`Dispersion_Method=DIRECT_CONNECTED_CAP`, which says a cap was measured.

Publication 177 breaks it two ways, and both are ordinary print:

    the cap is grey 215 and the declared ink level is 160, so only the stem is
    ink. Reported 8.3, off by half a stroke, under a false label.

    a JPEG drops four rows out of the stem. A stem is followed across a gap of
    two, so the run stops at the hole and its end is the MIDDLE of the whisker.
    Reported 2.2 pg/ml against a printed 6.

Widening the run-gap to jump the hole is not the fix - that is choosing a
constant so a cell passes, and the constant is exactly what tells a stem from a
significance bracket's descender. **No cap means no dispersion.** The cell goes
to a person, which is what a figure the reader cannot finish reading is supposed
to produce. The stem stays a separate fact in its own field: something was drawn
on that bar and the reader saw it; what it could not do is measure where the
whisker ends.

`Dispersion_Method` is re-ordered with it. Asking about the stem first let a
stem-confirmed bar with no cap say `DIRECT_CONNECTED_CAP` beside an empty
dispersion; the method describes what produced the number, so with no number
there is no method.

    reverted                                          scenarios that fail
    the stem's end reported as a cap again               8
    the method asks about the stem first again           4

`make_whisker_fixture.py` draws both: `whisker_pale_cap_fixture.png`, whose cap
is grey 215, and `whisker_broken_fixture.png`, whose stem is missing four rows in
the middle. Under v9.9 they read 11.5 and 44.5 against a drawn 12 and 45, and
4.75 and 21.25 against the same - a number less than half the truth, wearing the
label that says it was measured.

Publication 323 is untouched: 107 values, every mean and dispersion identical,
`crosscheck_id323` AGREEs on all 72. On 177 the two cells lose their dispersion
and keep their mean, and the other sixteen are unchanged.

## v9.11 — a marker is not a number of pixels, and a printed r is not a marker

**The scatter reader had never been shown a printed scatter.** Every one of its
scenarios ran on a single synthetic panel: 800 by 520, ten hard-edged blue
circles, no annotation and no fitted line. That is where `BAR_COLOR` was before
v9.9, and the first real figure said the same thing.

Publication 177 Figure 4 is on the same page as the bar pilot, is three scatter
panels, and — the reason it was chosen — **prints its own answer**: `r = 0.91`,
`r = 0.57`, `r = 0.17`, with n in the caption. The reader returned

    panel A   r = -0.47   against a printed 0.91
    panel B   r = -0.84   against a printed 0.57
    panel C   r = -0.08   against a printed 0.17

and in panel A **not one of the four marks it found was a data point.** All four
were letters of `r = 0.91` and `P < 0.001`.

**A marker is not a number of pixels.** `read_scatter_panel` decided what a
marker is with four absolute numbers — area between 12 and 500 square pixels,
bounding box under 35 across and over 3. None of them is a property of a figure;
they are a marker at one rendering. At 600 dpi 177's markers are 28 to 36 across
and about 600 square, so the AREA CEILING rejected every data point in the panel
and left only the annotation. The size is measured off the panel now, through
the same net the line readers have used since v8.7 — bigger than three pixels,
smaller than a tenth of the panel, both ratios of the panel — and a candidate is
kept when its side is near the panel's own marker. `min_marker_area` and
`max_marker_area` survive as absolute bounds a person may add ON TOP, which is
what an option is for; they are no longer what the reader falls back on.

**And a printed `r` is not a marker.** A journal prints its statistics inside the
axes and the glyphs are marker-sized: on 177 Figure 4 they measure 28x44 and
32x48 against markers of 28x28. There is no measurement that separates them —
`0` IS a small circle — so this is not something a reader can be made cleverer
about. It is something the panel declares, like its axes: `Annotation_Boxes` on
the panel manifest, `annotation_boxes` in the plan, boxes of `x0,x1,y0,y1` inside
the plot area holding ink that is not data. The manifest layer checks each one
against the panel it belongs to, because a rectangle typed by hand off a figure
can miss the plot area or swallow it and both fail silently.

    reverted                                          scenarios that fail
    the four absolute pixel numbers are back            2
    the declared annotation is not blanked              2
    the manifest stops checking the declared boxes      4

`make_scatter_fixture.py` draws twelve pairs TWICE, three times apart in scale,
with the statistics printed inside the axes. One rendering used to return 22
marks and the other 4, off one drawing; both now return 12, every pair within 1%
of the axis span, and the two agree with each other — which is the scenario the
absolute numbers cannot pass and the reason the fixture is two files.

**What this does NOT close, and it is most of 177 Figure 4.** Three panels, three
remaining structural failures, each needing its own rule and its own fixture:

    a fitted regression line runs through the cloud and welds every marker into
    one contour - panel A is a single blob 308 by 279 at 600 dpi and 154 by 141
    at 300, so this is not a resolution to be turned up

    overlapping markers merge - panel C declares 24 and the reader finds 41, two
    of them clusters of 104x195 and 68x96

    open markers have no thick core at all, so the primitive that finds a filled
    circle finds nothing on a ring; `_one_interior_per_marker` is the one that
    does, and the scatter reader does not use it yet

Until those land a printed scatter goes to a person, and the count audit is what
sends it there — provided the source declares n. Where it does not, and where
nothing looks overplotted, an association is still computed from whatever was
found: on 177 panel B that is r = -0.84 against a printed 0.57, with no flag.
That hole is named here and not closed here.

## v9.12 — a marker is an interior, not an outline

**Publication 177 Figure 4 now reads what the paper printed.**

    panel     printed r     v9.11        v9.12      marks
    A            0.91       -0.47        0.911          9
    B            0.57       -0.84        0.561         12
    C            0.17       -0.08        0.276         45 against a declared 24

Reading a scatter as CONTOURS OF INK - one blob, one mark - is defeated three
ways by a printed figure, and that row of three panels has all of them.

    A fitted regression line runs THROUGH the cloud and touches every marker it
    passes, so the ink is one contour. Panel A is a single blob 308 by 279
    pixels at 600 dpi and 154 by 141 at 300 - the same blob, and not a
    resolution to be turned up.

    Two markers that touch have one outline between them, and its centroid is a
    point at neither of them.

    An OPEN marker - a ring or a triangle, which is how a journal draws a second
    and third group - has no thick middle at all, so the primitive that finds a
    filled circle finds nothing on it.

**An interior answers all three, because it is what a marker is.** A filled
marker's interior is a thick core of ink; an open marker's is the white it
shuts in; a fitted line has neither, being thin and enclosing nothing. Two
touching markers have two interiors. So the reader takes seeds rather than
contours, and the centre of each seed is a point.

The seeds are the PEAKS of the distance transform, not the components of a
threshold above it: at a centre gap of 13 to 31 pixels against a marker 33
across a threshold gives ONE component where a person plainly sees two markers,
and the peaks give two. Measured at neighbourhoods of 0.6, 0.8 and 1.0 of the
marker, the count is the same, so the one chosen is not a knife edge.

**An interior is smaller than its marker**, and holding it to the marker's own
size window is what made panel B read ONE mark in twelve: 177's triangles leave
an interior 12 across against a marker of 32. A third is the floor, and it is
geometry rather than a fitted number - an outline thicker than a third of the
marker on each side has filled it in and it is not an open marker any more.
177's triangles sit at 0.375 of theirs; its rings and the fixture's at 0.72.

    reverted                                          scenarios that fail
    the seeds become components of a threshold          1
    the enclosed-white family is removed                7
    an interior is held to the marker's size window     2

`make_scatter_fixture.py` now draws six panels off the same twelve pairs: two
scales, a fitted line, rings, bold triangles whose interiors are 0.38 of their
marker as a printed one's are, and one extra pair 22 pixels from its neighbour.
Every one reads every drawn pair and the association it was drawn from.

**What this does NOT close.** Panel C is a dense cluster of two dozen
overlapping rings and the reader finds 45 marks in it; `MORE_DETECTED` sends the
panel to a person, which is the right answer for a cloud whose count a reader
cannot vouch for. And the count audit still needs the source to declare n:
where a caption gives none and nothing looks overplotted, an association is
computed from whatever was found and no flag says so.

**One more thing this pilot found, and it is a declaration and not a reader.**
177's caption gives n as SUBJECTS - 5, 6 and 24 - while the panels plot one
point per subject per test day, so the point count is about twice that and
`Point_Count_Agreement` reads `MORE_DETECTED` even where the reading is right.
For an association cell `N_Outcome` has to be the number of PAIRS. Nothing in
the manifest says which of the two it is.

## v9.13 — the paper prints the answer, and the run is held to it

**Publication 177 Figure 4, all three panels, against what the paper printed:**

    panel    pairs   found   count    computed r   printed r   verdict
    A          10      10    MATCH       0.907        0.91      accepted
    B          12      12    MATCH       0.561        0.57      accepted
    C          48      48    MATCH       0.250        0.17      REFUSED

Two things got it there, and the second exists because of the first.

**A slightly overlapping pair is two markers.** The peak-suppression radius -
how close two seeds may be before the lower is taken for the higher one's noise
- was 0.8 of a marker, and what that swallows is marks 5 to 10 pixels apart on a
marker 32 across. Panel A lost one of its ten that way and panel C three of its
forty-eight. The fixtures could not see it: they read every drawn pair anywhere
from 0.30 to 0.80. A printed figure can, and its three panels are right across
0.40 to 0.50 and wrong on either side:

    0.30   10  12  50        0.60   10  12  46
    0.40   10  12  48        0.70    9  12  46
    0.50   10  12  48        0.80    9  12  45

0.45 is the middle of that plateau, and `scatter_fixture_overlap.jpeg` now
carries a pair TEN pixels apart - the separation panel A prints - so the suite
can tell one setting from the other.

Those counts are also the first independent confirmation of something the last
release could only assert: 10, 12 and 48 are exactly twice the caption's 5, 6
and 24, which is what "individual data points from testing preflight and on
landing day" means. `N_Outcome` on an association cell is the number of PAIRS.

**And a count says how many marks were found, not where they are.** With the
radius fixed, panel C matches its 48 exactly and still computes 0.25 against a
printed 0.17: two dozen overlapping rings resolve into the right NUMBER of seeds
in the wrong places. No count can catch that. What can is the figure itself - a
panel that prints `r = 0.17` beside its cloud has declared the answer, the same
way a caption declares what its error bars are. `Association_Value_Printed` on
the panel manifest, `association_value_printed` in the plan, and a cell whose
digitized points do not reproduce it goes to a person with both numbers in the
refusal.

The tolerance is 0.02. A printed value is rounded to two decimals so half a
hundredth is unavoidable; 177's two readable panels land 0.003 and 0.009 away
and the one whose cloud the reader cannot resolve lands 0.080 - an order of
magnitude apart, so nothing sits near the line. Tight is the safe direction,
because it sends work to a person.

    reverted                                          scenarios that fail
    the suppression radius goes back to 0.80            1
    the printed value is not compared with the computed 3
    the manifest stops checking the printed value       3

**What this does NOT close.** Panel C is still read wrong - it is refused rather
than corrected, and a cluster of two dozen overlapping rings is where this
reader stops. And the check only exists where the paper prints a value: a
scatter with no printed statistic and no declared n still emits whatever the
points give.

## v9.14 — the gridline guard has a margin, and the margin was never measured

Bars and scatter got six releases of real-figure hardening; the line reader had
not been looked at since v7.9x, and it is verified on exactly one publication at
exactly one scale. Asked "does it still hold", it does - and one thing it holds by
two hundredths turns out not to be scale-invariant.

**What is fine.** `test_line_style_mono` 123 scenarios, `test_mark_readers` 168,
`forward_test_397_line_style` PASS at 18 of 24 cells with a worst error of 1.65
mmHg on a 50 mmHg axis, `forward_test_397_line_geometry` PASS on all 12 panels.
The overlay checked against the ink at 3x: red on the solid curve, blue on the
dashed, caps where the caps are. The gridline guard from v7.55 is present and was
itself a real-figure finding.

**What is not.** `_horizontal_rules` calls a row a rule when its ink spans
`_RULE_COVERAGE` = 0.9 of the panel WIDTH, and the ink it is shown is clipped to
the DATA SPAN - the declared positions plus one `x_window` of margin either side,
because a curve exists between its own end points. A gridline running the full
printed panel can therefore only ever present `span / width` of it. That ratio is
now measured by `rule_coverage_ceiling`, and on one synthetic panel drawn NATIVELY
at four scales - stroke, dash period and rules all scaled with it:

    1x  0.9215  PASS        3x  0.8947  BELOW 0.9
    2x  0.9014  PASS        4x  0.8908  BELOW 0.9

Under the threshold the gridlines stop being rules. They are perfect solid lines,
so each becomes a SOLID candidate at every x, no x has exactly one, and the reader
emits NOTHING for the panel - the v7.55 defect returning through the guard's own
margin rather than through its absence.

**It is the INSET, and scale only erodes it.** `x_window` is a pixel constant and
the panel width is not, so a finer render grows the unmasked margin's SHARE.
Publication 397 Figure 1 measures 0.9720 and is nowhere near the edge - its
declared positions sit close to the axis ends. A panel whose first and last
categories sit at interval centres, which is the ordinary categorical layout,
starts near the threshold and crosses it. That is why one publication at one scale
could not show this.

**PINNED, NOT FIXED, and that is a decision.** Four repairs were tried and each
was worse than the defect:

    growing the rule mask to its own antialiased edges   no effect at 3x or 4x
    deriving the stem threshold from stroke width        no effect: 11..40 identical
    scaling `_column_runs`'s max thickness               no effect: 7..28 identical
    scoping coverage to the columns actually masked      3x went 0 cells -> 2 cells,
                                                        one of them 10.96 mmHg wrong

The fourth is why this release does not ship a fix. Turning silence into a wrong
number is the one direction this package will not trade in, and widening
`_RULE_COVERAGE` to admit the failing panels is the constant-widening the testing
rules forbid. The margin is now a number a scenario holds and a run prints.

**And the silence names itself.** A panel that emits no rows is fail-closed and
right to be; `run_batch` routes it to `MANUAL_POINT_READ`, and the detail read
"the reader resolved no marks in this panel" - which is exactly where a figure's
worth of gridlines-read-as-curves hid the first time. `line_style_mono` records
`LINE_RULE_COVERAGE_UNREACHABLE`, `LINE_NO_RULES_FOUND` or
`LINE_NOTHING_SEPARABLE` with the measured ceiling in it, cleared per panel, and
`run_batch` folds it into the reason. Same shape as
`review_overlay.reset_failures`, for the same reason.

    reverted                                          scenarios that fail
    the reader stops naming why it read nothing        1
    run_batch stops folding the note into the reason   1
    run_batch stops clearing the note per panel        1

**One pin is weaker than the others and is labelled so.** The two `run_batch`
lines are asserted STRUCTURALLY - the branches that need the calls have them -
because a behavioural pin needs a run whose LINE_MONO_STYLE panel reads nothing,
and that manifest fixture does not exist yet. The scenario says this in its own
comment rather than looking like the stronger thing.

## v9.15 — a rule nobody could remove is not a series

v9.14 measured the ceiling the clipped mask puts on rule coverage and reported it
when the panel emitted nothing. The report was GATED ON SILENCE, and silence is
not the dangerous case.

**What was wrong.** The same synthetic panel, drawn natively at 8x, is not silent:

    s          ceiling   reachable   cells   worst error   note
    0.5 - 2.0  0.9014+   yes         12-14   <= 0.96 mmHg  -
    2.5 - 6.0  0.8873+   NO          0       -             LINE_RULE_COVERAGE_UNREACHABLE
    8.0        0.8856    NO          8       27.95 mmHg    NONE AT ALL

All eight cells are `119.95` — the 120 mmHg gridline, read as the SOLID series at
all eight positions. 8x escapes the silence because there the drawn stroke is 24
px, so `_vertical_strokes` takes both curves away as error-bar stems, the
unremoved gridline is the ONLY candidate left at each x, uniqueness is satisfied,
and the furniture is emitted as data. v9.14's diagnosis was already correct about
this panel and its own gate stopped it being printed.

**What ships.** `unremovable_rule_rows` names the rows that ARE rules over the
columns the mask contains and are NOT rules over the panel width — the pair the
mismatch creates — and a cell whose value sits on one of those rows is refused
with `LINE_VALUE_ON_UNREMOVABLE_RULE`, which reports the ceiling and every value
it dropped. `run_batch` now clears the note ONCE PER PANEL in the panel loop and
folds it into the outcome detail on EVERY exit rather than only on silence.

**What deliberately does NOT ship: refusing the panel.** A panel whose data covers
the middle 70-80% of its box — an inset, a legend column, a wide y label — has the
same unreachable ceiling and the same unremovable gridlines, and the reader still
emits 7 of 16 cells, every one within 0.25 mmHg of the drawn truth. The unremoved
rules make it MORE conservative, not less: they are extra SOLID candidates that
spoil uniqueness. Refusing on their presence costs seven correct numbers to
prevent a wrong one that did not happen. What is refused is the CELL that lands on
the rule.

**The first end-to-end LINE_MONO_STYLE run in CI.** v9.14 said its two `run_batch`
lines were pinned structurally because a manifest set with a line panel did not
exist in `test_run_batch`. It does now: two declared series, only the dashed one
drawn, data over the middle 70%, one gridline at 100 mmHg, error bars on the
series the figure draws. Reverting the refusal puts eight rows of
`99.99999999999997` for `ARM=FLUID;TIMEPOINT=T1..T8` back into
`figure_values_raw.csv` — a series the figure does not contain. That run marks the
panel QC_FAILED, but for a DIFFERENT reason (a gridline has no error bar, so those
cells carry no weight), which is not the same as knowing the numbers are
furniture, and it leaves them in the file every downstream step reads.

    reverted                                          scenarios that fail
    the cell-level refusal                            3 reader + 4 batch
    the pair condition (rules over the span only)      2, incl. one from v7.5x
    run_batch stops folding the note                   1
    run_batch clears the note inside the reader again   1
    refusing the whole panel instead of the cell       2
    the stroke-derived tolerance -> exact row          NOTHING, so it was removed

The last line is the standing rule applied to this release's own code: an
unobservable guard is decoration. The tolerance also had a cost — a curve drawn
one pixel clear of a gridline is at the position it was drawn at, and refusing it
would lose a cell the figure does contain.

**The release gate is blind to all of this.** `forward_test_397_line_style` passes
identically before and after (18 of 24 cells, worst 1.65 mmHg) because 397's
ceiling is 0.9720 and no row of its panel qualifies. One publication at one scale
cannot show a scale-dependent defect; the scaled fixture is what does.

**Two defects found in the same investigation are recorded, not fixed.** Both are
in "Still open" with their measured numbers.

## The segmentation harness, and the six statements that put a panel back together

`HARNESS.md` is the full document; this is what changed in the package and why it
is testable at all.

A figure arrives as a raster and has to become panels before anything can be
measured in it. The whitespace cut that does that is one rule, and one rule is
wrong on 187 heterogeneous figures in six different ways — a box short of its own
axis, a box that clipped its spine and measured a grid line instead, a row the cut
cannot place, a caption swallowed as data, the whole plate offered as one of its
own panels, and a piece torn off and discarded. Eight checks now look at what the
cut PRODUCED, find where that contradicts the figure, and repair it. Each is an
additional CANDIDATE rather than a replacement, each writes its reason into the
`harness` column, and the tick ladder still gates what is used: **a harness you
cannot check is not a harness**, and one that decides alone is not a proposal.

**The one that needed a different shape is the eighth.** The cut fell in the gap
before publication 345 figure 4's Earth bars, kept the left piece because it held
the y axis, and discarded the right one — 38 px of bars with no axis. The panel was
then reported COMPLETE with a quarter of its data outside the box, which is a
correct reading of an incomplete plot and the worst kind of wrong. Censusing the
discard pile found 6,052 blocks over four modes: 1,976 below, 1,909 left, 942
above, 295 right.

"Split where there is white space" has no counterexample, because the band between
two bar GROUPS and the gutter between two PANELS are the same white space. So
`continuity.py` measures continuity instead, as six statements each recorded
separately: do the baselines continue, do the pieces share the same rows, does one
carry data ink but no axis, are the marks in the same coordinates, are both above
the same caption, is the merged result more regular. NECESSARY is 3 ∧ 2 ∧ (5 not
false); EVIDENCE is at least one of 1 and 4 — proximity is never the evidence;
6 may veto and never adopts on its own. An unknown neither supports nor vetoes,
which is why an unread caption does not refuse.

**Statement 1 is the heart of it and it carries no constant.** The crossing gap is
compared against the largest gap ALREADY INSIDE this panel's own baseline: 26 px
against 27 on 345 figure 4. A break no wider than one the panel already holds is
not a boundary. The panel calibrates its own threshold.

### What the suite adds, and the two things it found

The corpus is not in this repository — the figures are publisher rasters — so
every number above is unreproducible from a clone. `test_continuity.py` pins the
judgement against figures drawn with PIL instead: 47 scenarios, no corpus, no OCR,
no network. Both failure directions are drawn, because a suite that only proves a
fragment gets put back can be passed by adopting everything:

    a fragment REFUSED    the panel loses data and nothing says so
    a neighbour ADOPTED   two panels become one and the axis assignment shifts

and the neighbour is drawn in the SAME ROW BAND as the panel. That is the harder
version: statement 2 stops helping, and the refusal has to come from statement 1
and statement 3 alone. Every geometric scenario runs at two scales and must give
the same verdict at both — the fixture's 19 px break at 1x and 38 px at 2x are the
same figure, and nothing in this harness may be a distance in pixels.

Two things turned up in the writing, both now in the tree:

**Statement 4 is narrower than it reads.** Its `inside` term compares ink in the
axis band against ink in the piece over the same columns, so for any piece whose
box lies inside the panel's rows it is 1.0 by construction and statement 2 has
already decided. It speaks only in the window statement 2 leaves open — a box
reaching up to 12% past the panel's rows, with ink lying in that overhang. The
scenario is written on that window, since a scenario anywhere else would have
passed with statement 4 deleted, and a guard nothing can observe is decoration.

**And OCR became optional, because none of this needs it.** `axis_reader` imported
`pytesseract` at module level, which put panels, spines, baselines and continuity
behind a system package that `requirements-lock.txt` does not install. The import
is soft now. Asked for a tick NUMERAL without it, `_ocr_numerals` RAISES rather
than returning none: "no numerals here" and "nothing looked" are different answers
and only one of them is a fact about the figure, and a ladder silently built from
zero numerals is the fail-open shape this package refuses everywhere else. The
size floor still answers first — a strip too small to read is refused for being
too small, not for the backend. Both are scenarios, and the missing backend is
taken away inside the test rather than looked for, so the count is a property of
the tree and not of the machine.

    reverted                                          scenarios that fail
    the self-calibrating gap replaced by a constant    1
    rows measured against the axis alone               1
    rows measured against the box alone                1
    a piece with its own axis still an orphan          4
    the coordinates always agreeing                    3
    an unread caption reading as false                 2
    regularity allowed to veto nothing                 1
    regularity answering when nothing was added        2
    proximity accepted as the evidence                 1
    a missing OCR backend reading as no numerals       1

## The baseline is not always at the bottom of the axis

Publication 475's figure 2 draws ΔTPR, ΔLVR and ΔCVRi as bars going UP and DOWN
from a zero line through the MIDDLE of each panel, with the y axis running on past
it to the bottom of the scale. Four defects were live on that one figure, and all
four are the same mistake: asking about "the baseline" at the foot of the axis,
where that figure has no ink at all.

**Criteria 1 and 6 were measuring an empty row.** Both took `run[1] - 1`. On panel
E that is row 898 and every bar in it stands on row 786, so criterion 1 answered
"this piece has no ink on the baseline row" - a refusal that was really an empty
measurement - and criterion 6 found zero marks and declined to speak. The heart of
the judgement and its arbiter were both silent on all six panels, and the adoptions
that did happen there rested on criterion 4 without anyone noticing.

`continuity.baseline_row` now picks between the axis's foot and the baseline the
reader sees, using the panel alone: a baseline runs most of the panel's width, a
bar top runs one bar's worth, so the row with more of the panel's own columns inked
wins. That preserves the reason the foot was chosen originally - on a short box
`spine_and_baseline` answers with a bar top, and a bar top loses this comparison.

**A constant was standing in front of the self-calibrating test.** `ADOPT_GAP` is
34 px; panel E's third bar group sits 37 px past the box edge, so the piece was
refused before any of the six statements were asked - by exactly the kind of fixed
distance criterion 1 exists to do without. The panel already says how wide its own
bar-group gaps are: 74 px here. That is the reach now, with the old constant kept
as the FLOOR where a baseline shows no gaps at all. Nothing was widened; the gate
stopped overruling the test.

**A slab never got an adoption pass.** Adoption is step 8 and `broad_slabs` builds
at step 6, so every box the row cut could not place was offered the discarded
pieces exactly zero times - and panel E's box is a slab. It did not exist when the
orphans were handed out. The second pass is offered the SLABS ONLY.

**`cut_through_axis` was wrong in both directions at once.** It MISSED panel E: it
probes three pixels and the sliced-off group is 37 px away, across the gap the cut
mistook for a boundary, so the severance this check exists to catch went
unreported. And it CRIED WOLF on panels A, C and F, because that figure prints its
zero line 51 px past the plotting area into the gutter with no bar anywhere in the
overrun - three correct panels demoted out of `AUTO_DIGITIZE` for a rule leaving
the box. A rule leaving the box is not data leaving the box: what makes a box a
fragment is MARKS outside it. The reach is now the panel's own widest baseline gap,
the ink out there has to be more than the rule itself, and where the box's left
edge IS its axis the question is not asked on that side - everything there is the
label strip and the axis title.

    475 figure 2                    before      after
    fragment-flagged panels              3          0
    panel E box                  103-299    103-402
    ladders                              6          6

    eight-figure sample             before      after
    fragment flags                      26         12   (25 removed, 5 added)
    panels / statuses / ladders     52 / -/ 47  52 / same / 47

The five added flags are all on 475 figure 1, which really is severed - eleven
boxes for six panels.

    reverted                                          scenarios that fail
    criterion 1 back to the axis's foot                1
    criterion 6 back to the axis's foot                1
    the fragment rule back to any ink at three pixels  2
    any ink outside counting as marks                  1
    the label strip asked about again                  1
    the adoption reach back to the constant            1

**Still open on that figure.** Panel E is adopted on criterion 4, not criterion 1:
measured at the right row the crossing gap is 75 px against a widest internal gap
of 74 - a one-pixel miss, so the strongest statement abstains and the weakest
carries it. And 475 figure 1 is cut HORIZONTALLY at the zero line into an
above-zero and a below-zero piece; adoption looks left and right only, so nothing
can put those back. The measurement that closed off up-and-down adoption predates
`continuity.py` - it was about pulling in TITLES - and criterion 3 now separates
data ink from a title, so it is worth re-running.

3203 core / 3241 full, both verified against the tree.

## One number for 187 presses

`INK = 140` decides what is ink. Publication 475's figure 1 draws the y axes of its
left column at a grey around 155: column x=179 of panel A carries 238 rows of
continuous axis, of which 140 admits TWO. Three of its six panels therefore have no
axis at all, the plate comes back as eleven boxes - and the eleven-box reading WON,
because each fragment read a ladder off the shared label column and `n_ok` is
unbounded upward. Publication 70's figure 1 is the same illness and comes back with
nothing at all.

**Otsu is not a replacement for 140, and the corpus is why.** Re-running all 187 at
the threshold each figure states moves the candidate count on 76 of them and drops
the figures whose count matches the axes a person recorded from 39 to 35: on a figure
printed in solid black, 140 is the better answer and Otsu drifts up into the
anti-aliasing. The measurement that does hold is one-sided - on the 11 figures that
come back SHORT, Otsu never gives fewer candidates, gives more on 5, reaches the
recorded count on 3, and exactly ONE already-fine figure would break.

So `figure_ink` is asked as a SECOND QUESTION, of a figure that came up short, through
the same four modes and the same score, with the ladder still deciding; a figure
decided that way carries `RE_INKED` in its `harness` column. It returns Otsu PLUS ONE,
because `_dark` asks `a < INK` and a figure whose axis sits exactly at the split level
would otherwise be excluded one grey lower - the same failure, reintroduced. A clip of
one grey has nothing to separate, so it answers with the shipped threshold rather than
raising into the caller.

**The mode score had to change with it.** A re-inked reading of five panels lost to a
shredded reading of eleven, because more boxes meant more ladders meant a better
score. You cannot read more axes than the figure has: `mode_score` now puts distance
from the human-authored count first and lets ladders break ties inside it. This is the
existing count-match rule from the other side - that one refuses a segmentation that
hits the number while every cell refuses the ladder.

Measured on a 20-figure sample, 11 of them the short ones and 9 already working:

    figures closer to the recorded count            7
    figures further from it                         0
    ladders read                              75 -> 82
    figures matching the recorded count        8 -> 9
    475 Fig.1  panels / ladders / fragments   11/11/8 -> 7/5/1

Three figures that produced NOTHING - 345 Figure 3, 345 Figure 6, 528 Figure 1 - now
produce panels. Every figure that already worked is unchanged row for row. Still at
zero: 70 Figure 1 and 533 Figure 2, where the figure's own threshold does not rescue
the axis either.

    reverted                                          scenarios that fail
    the count-distance term removed                    1
    the off-by-one on a strict `<` reintroduced        1
    a blank clip allowed to raise                      1 (the suite aborts)

`REINK=0` and `NEAR=0` are driver switches, so the suite cannot observe them; it pins
`figure_ink` and `mode_score` directly and the corpus revert runs observe the rest.
Both were moved out of `propose.py` into `axis_reader` for exactly that reason - a
policy nothing can import is a policy nothing can test.

3214 core / 3252 full, both verified against the tree.

## Criterion 4 was reading three wrong things at once

Publication 475's figure 1 shows all three. Its bars hang DOWN from a zero line drawn
through the middle of each panel, and the columns they stand in also carry the column
title above and the plate's x labels below.

THE ROW. The previous round moved criteria 1 and 6 to the row the marks stand on and
left this one at the foot of the axis. On that plate the bars stand on row 835 and the
foot is at 967.

ONE END ONLY. "Standing on the baseline" was written as *the column's last inked row
is the baseline row*. True of a bar that goes UP; false of every bar here, whose last
ink is its far end. A mark stands on the baseline when EITHER end is at it.

THE WHOLE COLUMN. `dark[:, ox0:ox1]` asked where the ink in these columns begins and
ends anywhere on the plate - the title above, the tick labels below. The piece's own
rows are the question, and `inside` had always restricted itself that way while the
feet term had not.

Together they answered 0.01 for a piece every column of which stands on the panel's
zero line. Corrected, they answer 1.00 and the piece is adopted.

On the 20-figure sample: ladders 82 -> 84, and one figure changes - publication 397's
figure 1 goes from 7 panels reading 4 ladders to 6 reading 6, both short of its 8.
Everything else identical row for row.

    reverted                                          scenarios that fail
    criterion 4 back to the axis's foot                2
    only the last end of a column counted              2
    the whole column asked about again                 2

TWO REPAIRS MEASURED AND NOT KEPT, recorded here so the next reader does not spend the
afternoon on them again.

Reaching as far as the panel is wide. The self-calibrating reach asks the panel for
the widest gap already in its baseline row, and where the figure DRAWS a zero line
that row has no gaps at all - so it degenerates to the old constant, and 475 figure 1's
pieces are never offered to the six statements at all. Bounding the reach by the
panel's own width does offer them, and on the sample it bought exactly one figure -
475 figure 1 at six boxes for six axes - BY CANCELLING TWO ERRORS: panel A returned
twice and panel C not at all. It cost publication 397's figure 1 a panel. A count that
matches because two mistakes agree is what the count-match rule exists to refuse.

A panel does not contain another panel. Added to `collapse_same_axis` to remove that
duplicate; on the sample it cost publication 68's figure 2 a panel and changed nothing
else. Removed rather than kept behind a flag.

So 475 figure 1's panels C and E are still boxed to a third of their width, and D and
F still refuse their ladders. What is now KNOWN about that figure: the pieces are
pieces by all six statements, and the only thing between them and their panels is a
pre-filter that cannot state a distance on a plate with a drawn zero line.

3220 core / 3258 full, both verified against the tree. (History: that is
what v9.15 ran. The CURRENT pair is the markers in `README.md`.)

## Four ways round one gate, and why none of them is in the tree

Publication 475's figure 1 still boxes panels C and E to a third of their width. The
six statements accept those pieces; the pre-filter never offers them, because it asks
the panel for the widest gap already in its baseline row and that plate DRAWS a zero
line - so the row has no gaps, the reach falls back to `ADOPT_GAP`, and the pieces are
refused before anything is asked. Four ways round it were measured this round and the
last. All four failed, and all four failed in the same place.

    tried                                        measured
    reach = the panel's own width                475 fig 1 reaches 6 boxes BY
                                                 CANCELLING TWO ERRORS - panel A
                                                 twice, panel C absent - and costs
                                                 397 fig 1 a panel
    a panel does not contain another panel       costs 68 fig 2 a panel, changes
                                                 nothing else
    adjacency instead of a distance, with a      475 fig 2, which was exactly right,
    guard for another panel's label strip        is rebuilt WRONG: panel A shrinks
                                                 from x1=403 to 314 and loses its
                                                 third bar group, and 397 fig 1 grows
                                                 one box across BOTH columns
                                                 (x1 577 -> 1086)
    criterion 4's foot term widened to           475 fig 2's y label strip scores
    "crosses the baseline", then to              0.86, then 0.68 - as high as real
    "inked at the baseline"                      bars

THE COMMON POINT OF FAILURE IS CRITERION 4. Its band term - ink lying between the axis
top and the baseline - is 1.0 by construction for any piece inside the panel's rows, so
it accepts whatever the gate lets through. On a six-figure probe, ALL THREE adoptions
were carried by the band term alone, at a foot share of 0.00. And the foot term cannot
be widened to take the load, because a column of y numerals has ink above and below any
row you pick.

So the distance gate is load-bearing precisely because criterion 4 is not.

AND CRITERION 4 CANNOT BE TIGHTENED EITHER. The primitive looked missing - telling a
MARK from a LABEL - but geometry already states it: there are no marks left of a spine.
A panel's plot runs from its spine to its right edge, so ink on the far side is the
label strip by definition and the band term should say nothing there. Applied, it does
exactly what it should to the two adoptions in question: 475 figure 2's label strips go
from adopted to refused. And the figure gets worse.

                              shipped   plot-side only   ...and reach widened
    475 fig 2                 6 panels  6 panels         6 panels
      panel C right edge      x1=403    x1=297 (loses    x1=297
                                        its third group)
    475 fig 1 boxes           7         8                8
    fragment flags (6 figs)   3         4                8
    ladders                   35        36               38

Those label-strip adoptions add no ladder. The WIDER BOX they produce is what keeps
`collapse_same_axis` and the mode score landing on the right geometry afterwards - so
the harness is getting 475 figure 2's panels right for a reason that is not the stated
one, and making the criterion honest removes the accident that was helping. The extra
ladders in the last two columns are the same trap `mode_score` exists to refuse,
appearing inside one figure rather than across modes: more boxes, more ladders, worse
panels.

SO THE REPAIR IS NOT IN CRITERION 4. A panel's box should contain its own label strip
BY CONSTRUCTION - the way `label_band` already reads numerals left of the spine when
measuring - rather than by an adoption that criterion 4 then has to justify. Growing
every box to its own label strip as a definition would retire the left-side adoptions,
let the band term be restricted to the plot side honestly, and only then let the reach
be revisited. That is a change to the segmentation, not to the six statements, and it
is the next thing to build.

The third row is also a warning about how this harness gets judged. On 475 figure 2 the
panel count and the ladder count were both unchanged while the boxes moved to the wrong
places. Counting panels is not checking them, and a sample comparison that only counts
would have called that experiment neutral.

Nothing in this section is a code change; the two rejected readings of the foot term are
recorded in `continuity.same_coordinates` so the next reader does not re-derive them.

## The baseline was a process I thought I had killed

A round of this work compared a fifteen-figure run before and after a change, read
fragment flags 21 -> 9, and called it a repair. The change touches `cut_through_axis`,
which fills one reporting column and nothing else - and the PANEL COUNTS moved. That
cannot happen, and it is the only reason this was caught.

Three identical runs, byte for byte:

    c827263b3a6649ce3aa337a5b3d817ef  det_1.csv
    c827263b3a6649ce3aa337a5b3d817ef  det_2.csv
    c827263b3a6649ce3aa337a5b3d817ef  det_3.csv

So the pipeline is deterministic and the code was not what differed. The BEFORE file
was: an earlier run of the same command, started before `capscan.py` had written
`captions.csv`, which survived the `pkill` that was supposed to end it and finished
after its replacement. Every figure whose caption was later found had run without a
caption floor. The 21 flags, the GRID modes, four `FIGURE_BOX_REFUSED` rows and
publication 476's figure 1 at three panels were all that, and none of it was real.

Re-measured against a clean baseline, the change is a NO-OP: with the flag on and off
the fifteen-figure output is byte-identical. It is not in the tree.

    RULE. A comparison is only as good as its baseline, and a baseline is a claim
    about a process that ran. Re-run it, or stamp the inputs into the output, before
    reading a difference as a result.

### What the harness is actually worth, measured cleanly

Fifteen figures, harness off against harness on, same inputs, same build:

                     panels   ladders   fragment flags   count == recorded axes
    no harness           58        50               36                        5
    harness              71        63               15                        6

### And a correction to the previous section

Publication 397's figure 1 was recorded there as a case where the harness LOSES a
panel - 7 boxes down to 6, against 8 recorded axes. Judged by the boxes rather than
the count, it is the opposite. Without the harness that figure returns eight boxes of
width 54, 54, 100, 100, 129, 129, 195 and 195 px, in duplicate pairs, every one of
them flagged `panels cover only 8% of the raster`. With it, six boxes of width 464 to
494 px, every one reading a ladder. Eight fragments are not closer to eight panels
than six panels are.

That correction is the same mistake this file warned about two sections earlier -
counting panels is not checking them - made by the person who wrote the warning.

## The comparison is now a program, and it refuses

The previous section ends in a rule - re-run the baseline, or stamp the inputs into
the output, before reading a difference as a result - and a rule that lives only in a
document is a rule that is followed until the run takes three hours. So it is a file:

    harness_compare.py --base-ref REF_A --candidate-ref REF_B \
                       --figures "475|Fig. 2;345|Figure 4" \
                       --out RUN_ROOT --vary code --replay 2

It decides nothing about panels. Its whole job is to make the A/B honest, and every
guard in it is one clause of the sentence that describes how the last one was not:

    started before captions.csv existed  ->  the input manifest, and the gate that
                                             refuses to compare arms whose inputs
                                             differ outside `--vary`
    survived the pkill                   ->  each arm runs in its own session, and
                                             anything left alive in its process
                                             group when it exits is a refusal
    overwrote the shared output path     ->  there is no shared output path. Each
                                             replicate writes `output.repN.<run
                                             id>.csv`, promoted by `os.replace`
                                             from a `.partial` only on exit 0, and
                                             re-hashed before the comparison
    three re-runs were byte-identical    ->  `--replay 2` makes that a
                                             PRECONDITION rather than a discovery

The refusal codes are the whole interface: `INPUT_MISMATCH`, `NONDETERMINISTIC`,
`SURVIVING_PROCESS`, `ARM_FAILED`, `NO_OUTPUT`, `OUTPUT_CHANGED_AFTER_RUN`. Any one of
them and no comparison is written at all. A refused comparison is the product: the
numbers you were about to read were not measuring what you asked.

### Absent is a value, not a silence

`captions.csv` did not exist when the ghost run started. If a manifest lists only the
files it found, that fact has nowhere to live - two arms that read different worlds
produce manifests that agree. So every declared input is hashed, and one that is not
there hashes to `None`, which is a value that can differ from a hash. The rasters are
hashed too, but only the ones the selected figures name: hashing the whole clip
directory would make every unrelated file a reason to refuse.

`--vary` is the other half. The caller declares which manifest keys are the
experiment - `code`, or `code,env.WIDE2` - and every other difference is fatal. A gate
that refuses everything refuses the experiment too, so that is a scenario in the suite
as well.

### Counting is not checking, as a metric table

The four numbers the last section quoted - panels, ladders, fragment flags, count ==
recorded axes - cannot see the failure that made this necessary: publication 475's
figure 2 kept its panel count and its ladder count while panel C lost a bar group. So
the comparison is per axis, not per row:

    panel_count            rows, which is what the old comparison saw
    unique_axis_count      distinct (spine_x, baseline_y) buckets
    duplicate_axis_count   rows beyond the first standing on one spine
    ladder_pass_count
    fragment_flag_count
    foreign_axis_count     boxes containing a spine that is not theirs
    moved_boxes            matched axes whose box moved, with dx0/dx1/dy0/dy1,
                           the widths either side, and the IoU

A panel's identity is its axis, not its box. A box that shrinks is the same axis
measured worse; two boxes on one spine are one axis segmented twice. That distinction
is what publication 397's figure 1 needed and did not have: eight boxes,
`unique_axis_count` 4, against six boxes with `unique_axis_count` 6. Rows are matched
across arms by nearest axis rather than by panel number, because `propose.py` numbers
panels in discovery order and any segmentation change reorders them - matched by
index, every reorder reads as a moved box.

The report's `verdict` field is the string `DEMO_ONLY`, and it is the only value it
ever takes. Which arm is right is an attestation, and attestations are human-only.

### The suite, and how each scenario was checked for being decoration

`test_harness_compare.py`, 15 scenarios, no corpus, no network, ~2 s. Each is paired
with exactly one guard, named in its docstring. Then each guard was reverted in turn
and the suite re-run:

    box_diff reports no moved boxes              -> test_box_moves_while_every_count_holds_still
    unique_axis_count = panel_count              -> test_duplicate_boxes_on_one_spine_are_not_two_panels
    foreign_axis_count always 0                  -> test_a_box_that_swallows_another_spine_is_flagged
    match rows by index                          -> test_renumbered_panels_are_not_reported_as_moved
    absent input omitted instead of hashed        -> test_a_file_the_arm_could_not_find_is_recorded_as_a_value
    no INPUT_MISMATCH refusal                    -> test_an_undeclared_difference_refuses_the_whole_comparison
    lock ignores whether the holder is alive     -> test_a_live_holder_is_fatal
    lock never reclaims a stale file             -> test_a_dead_holder_is_reclaimed
    promote the partial file on failure          -> test_a_crashed_arm_promotes_nothing
    no survivor scan                             -> test_a_child_the_arm_leaked_is_caught
    no replay determinism check                  -> test_an_arm_that_does_not_repeat_itself_is_not_compared
    no post-run output re-hash                   -> test_an_output_rewritten_after_its_run_is_caught
    tree ref taken over the directory listing    -> test_an_unrelated_file_beside_the_tree_is_not_a_code_change

Thirteen guards, thirteen reverts, thirteen red suites, and no guard without an
observing scenario. The first draft of the comparability scenarios did not survive this: they
asserted against hand-built dictionaries, so deleting the refusal loop in the driver
left them green. They were rewritten to run the driver.

The process-group check is the narrow half of the ghost and is documented as such. A
child THIS run leaked is in its group and is caught; a process from an earlier session
is not, and is caught instead by there being no shared path for it to land on and by
the post-run re-hash.

### The first thing it was pointed at, and what it saw

Two figures, the arms differing only in `WIDE2` - the second adoption pass over the
slab - declared as `--vary code,env.WIDE2`, two replicates each:

    metric                       base  candidate    delta
    panel_count                    12         12       +0
    unique_axis_count              12         12       +0
    duplicate_axis_count            0          0       +0
    ladder_pass_count              12         12       +0
    fragment_flag_count             0          1       +1
    foreign_axis_count              0          0       +0

    boxes that moved while counts held still: 1 (max boundary delta 103 px)
    475 Fig. 2, axis (105, 786): (103, 402, 652, 924) -> (103, 299, 652, 924)
                                 width 299 -> 196, IoU 0.66, LADDER_OK both sides

That axis is publication 475's figure 2 panel E: the panel whose box cut off the 0.01
group in the first report of this defect. Turning one flag off puts the cut back, and
EVERY COUNT IN THE OLD COMPARISON STAYS THE SAME. `fragment_flag_count` moves by one,
which is the only hint the four-number table would have carried, and a hint of one
flag across two figures is exactly the size of noise that gets read past.

Both arms replayed byte for byte:

    baseline   4511e30e7ab69d786d46fb7b522ed6409bb6fec6c8e070891f9d540c9a594b64  x2
    candidate  01a0e6b11715a5b90c46d171f1a7af8572fd108353716e4c89a23a49d8086744  x2

and the manifest differed at exactly two keys, `code.ref` and `env.WIDE2`, both
declared. `inputs.captions.csv` reads `null` in both: the caption scan was lost with a
container and this run had none. That is a REAL difference from the fifteen-figure
numbers quoted above, and it is legible in the manifest instead of having to be
remembered - which is the whole point.

### What this does not do

It does not find a panel. Publication 475's figure 1 still returns seven boxes for six
axes, 476's figure 1 still refuses two ladders on boxes that are correct, 70's figure 1
and 533's figure 2 still return nothing. This file only makes the next attempt at those
measurable - which is the precondition the last four attempts did not have, and the
reason one of them was reported as a repair.

### The shape the next attempt is expected to take

Recorded here because it is a decision about representation, not a threshold, and the
four rejected approaches were all thresholds:

    a panel is not one box. It is a plot core, an OWNED label strip, and an axis
    signature (spine, axis run, baseline, ladder). The label strip is derived from
    the axis - the side `label_band` already reads from, bounded by the nearest
    column gutter and the caption floor - not adopted as an orphan by criterion 4.

That is why criterion 4 cannot be made honest on its own: publication 475's figure 2
is correct BECAUSE a label strip was wrongly adopted and the widened box happened to
push mode selection the right way. Reject the strip honestly and the bar group goes
with it. The order that follows from this - experiment harness, then the geometry
split, then label ownership, then candidate scoring on axis signature rather than box
area, then vertical fragments whose role is proven to be DATA - is in `HARNESS.md`.

## A panel is three boxes, and the first draft of them was empty

The section above ends by naming the repair as a change of REPRESENTATION rather
than of threshold: a panel is a plot core, an owned label strip, and an axis
signature. This is that change, and it is deliberately additive - `propose.py`
writes eighteen new columns and every old one is untouched.

    plot_x0/x1/y0/y1        where marks are: bars, curves, points, continuity
    label_x0/x1/y0/y1       what the panel owns on the label side of its axis
    label_side              LEFT or RIGHT
    numeral_x0/x1           the tighter strip OCR is pointed at, inside that
    review_x0/x1/y0/y1      the union - what a person is shown
    axis_sig, ladder_sig    the physical axis, and the values it read
    geom_note               why any of the above is blank

### Ownership and OCR are two questions

The first version answered both with `label_band`, and reported NO LABEL STRIP ON
ANY OF THE TWELVE REAL PANELS it was pointed at. The cause is the same on both
figures. Publication 475's figure 2, panel E, rows 654-899, the ink left of the
spine at x=105:

    37-54    the rotated axis title
    72-94    the numerals
    102-103  the tick marks
    105      the spine

`label_band` walks left from x=103, finds the tick marks, meets seven blank
columns at 95-101, stops, measures a band one pixel wide and refuses it. It never
reaches the numerals. Publication 345's figure 4 panel F is the same shape: title
1118-1135, numerals 1141-1157, a tick mark at 1165, spine 1178.

That is not a bug in `label_band`. A strip handed to tesseract has to be tight,
and its two pixel constants belong to the question "is this a column of digits".

    A tight strip is the right answer to "where do I read digits". It is the
    wrong answer to "what does this panel own". A panel owns its axis title as
    much as it owns its numerals - neither is data, both are its own.

So ownership reaches from the axis to the panel's boundary and takes everything
between; `numeral_band` stays exactly `label_band` and is reported in its own
columns. A panel whose digits cannot be isolated still has a label box, and the
two failures are told apart in the output instead of both showing as blank.

On these two figures `numeral_x0` is empty on all twelve panels while every one
of them reads a ladder - `y_tick_labels` tries several strip geometries and one
of the others works. Isolating the numeral column from the tick marks is not
solved here and is not needed for ownership.

### The boundary is the neighbour's EDGE, not its spine

The first draft bounded a left-side strip at the nearest spine to its left. On
475's figure 2 that gave panel D a label box starting at x=427 - inside panel C,
which ends at 403. A panel to the left ends at its right-hand edge; stopping at
its axis hands its whole plot to the panel next door. Bounded at the edge, panel
D's strip starts at 404. Only a panel that SHARES ROWS with the strip can bound
it: one stacked above takes nothing away, however close its columns are.

### Reach is the panel's own width

`label_band` defaults to 180 px, which is right for digits at a printed size and
wrong for ownership: the same figure scanned at twice the resolution would own
half as much. Ownership reaches `x1 - x0`. Both scenarios in the suite run at two
scales and must give the same verdict at both.

### Measured to be additive

Two figures, base at `28a74a9`, candidate with this change, `--vary code`, two
replicates each:

    panel_count               12 -> 12        boxes moved                   0
    unique_axis_count         12 -> 12        max boundary delta         0 px
    ladder_pass_count         12 -> 12        SHARED COLUMN MISMATCHES      0
    fragment_flag_count        0 ->  0        columns only in candidate    18

Both arms replayed byte for byte. `shared_column_mismatches` is the number this
step was built to make zero: it compares every column BOTH arms wrote, for
matched axes, and no count can see whether an "additive" change was additive.
It was added to `harness_compare` for exactly this and has its own scenario.

### The ghost, unstaged

Relaunching that comparison, a `kill` aimed at the wrong process group left the
previous run's arm alive. It was still writing while the new run worked, into the
same directory:

    output.rep1.20260825T035452-11326.csv.partial   the orphan
    output.rep0.20260825T035550-12996.csv.partial   the live run

Under the old scheme both of those are `proposals.csv`. This was not a test; it
happened while relaunching a job, which is how it happened the first time.

### The suite

`test_panel_geometry.py`, 20 scenarios run at two scales for 38 in total, drawn
fixtures only. Thirteen guards, thirteen reverts, thirteen red suites:

    label_side decided by ink, not the baseline   -> a sparse plot keeps its side
    ownership answered by label_band              -> eight scenarios
    no neighbour bound                            -> the neighbour's far edge
    a panel above counts as a neighbour           -> rows must overlap
    reach is a pixel constant again               -> the wide-panel scenario
    no caption floor clamp                        -> the floor ends the strip
    right-hand band not implemented               -> the mirror
    plot core not clamped at the spine            -> two scenarios
    review box is just the box                    -> the strip outside the box
    plot core keeps the strip                     -> the strip inside the box
    axis extent from the box, not the spine run   -> two panels, one signature
    ladder hash follows pixels, not values        -> identity survives a better read
    numeral band not reported separately          -> its own cells

Two of those reverts survived the first matrix - the reach constant and the
numeral cells had no scenario watching them - and two scenarios were written to
close them.

### What does not use any of this yet

Nothing. `collapse_same_axis` and `mode_score` still rank on box area;
segmentation still produces one box; the four figures that were wrong are still
wrong in the same way. This step only makes the next two possible, and it is
recorded as measured rather than as done.

## The four steps the record called the repair, measured

`HARNESS.md` set out five steps. Step 1 is `harness_compare.py`, step 2 is
`panel_geometry.py`, and steps 3, 4 and 5 were the ones the record had been
circling for four rounds:

    3  the panel's box contains its owned label strip, so criterion 4's band term
       can be restricted to the plot side without costing a bar group
    4  `collapse_same_axis` and `mode_score` rank on axis signature, marks and
       foreign axes rather than on box area
    5  the vertical direction is offered to the same six statements, since a
       title fails criterion 4 once that term is honest

All three were built, each behind its own flag - `OWN`, `PLOTSIDE`, `RANK`,
`VERT` - and each was measured. NONE OF THEM IS AN IMPROVEMENT, and none of them
is in the tree. This section is what was measured, because the code is not here
to be read.

### The revert test first

Two figures, shipped `599dbb8` against the new tree with all four flags OFF:

    panel_count 12 -> 12, unique_axis_count 12 -> 12, ladder_pass 12 -> 12
    boxes moved 0, max boundary delta 0 px, shared column mismatches 0

So the four flags are the whole of the difference, and everything below is
attributable to them rather than to anything that came along for the ride.

### All four together, six figures, two replicates each

                          off    on
    panel_count            40    40
    unique_axis_count      40    40
    ladder_pass_count      36    31      -5
    fragment_flag_count    11    19      +8
    foreign_axis_count      2     4      +2
    boxes moved                  17      max boundary delta 339 px

Panel counts identical, ladders down five, flags up eight. And all six of
publication 475 figure 2's boxes moved - the figure that was RIGHT before the
change - at IoU 0.63 to 0.76.

### One flag at a time, on the two figures that were worst

Publication 397 figure 1 and 475 figure 1, against all four off:

    flag                panels   ladders   frag flags   foreign   boxes moved
    OWN                 13 -> 15  11 -> 8    3 -> 10     0 -> 1        5
    PLOTSIDE            13 -> 14  11 -> 12   3 -> 4      0 -> 1        1
    RANK                13 -> 11  11 -> 11   3 -> 5      0 -> 1        2
    VERT (PLOTSIDE off) no change - see below
    VERT (PLOTSIDE on)  14 -> 14  12 -> 12   4 -> 4      1 -> 1        0

`OWN` is the one the record predicted would work, and it is the worst of the
four: three ladders lost and seven new fragment flags. Growing a box to the
leftmost ink in its axis rows takes in the rotated axis title and whatever else
stands beside it, and the wider box then trips the guards that measure whether a
box is a panel. THE STRIP IS NOT THE PROBLEM. The box being one rectangle is.

`VERT` measured as EXACTLY NOTHING twice over, and the first time it was my own
gate: vertical candidates are only offered while `PLOTSIDE` is on, and the
attribution run had it off, so that measurement was vacuous. Re-run with the
gate open it is still nothing - the signed halves of 475 figure 1 are not
offered at all, because the reach is the widest gap in the panel's own baseline
and a figure that draws a zero line has no gaps in that row. That is the
degenerate case already recorded against `SELFGAP`, reached from the other
direction.

### And the one that looked like an improvement

`PLOTSIDE` alone, six figures:

    panel_count 40 -> 41, ladder_pass 36 -> 37, fragment flags 11 -> 12,
    foreign axes 2 -> 3, boxes moved 6

Read as counts that is a small gain: one more panel, one more ladder. Read as
boxes it is the failure the record predicted in the same words four rounds ago.
Only one figure's counts change at all - 475 figure 1, 7 boxes to 8 for 6
recorded axes - while 475 figure 2's counts are IDENTICAL and five of its six
boxes move:

    axis (105, 476)   width 381 -> 275     panel C, its third bar group gone
    axis (606, 765)   width 366 -> 259
    axis (105, 786)   width 299 -> 418
    axis (607, 155)   width 371 -> 332
    axis (607, 472)   width 433 -> 395

    RULE. A change that trades a box for a count is not an improvement, and the
    four numbers this project used for a year cannot see the trade. That is what
    the box-level comparison is for, and this is the first time it has been the
    thing that decided.

### What this settles

The diagnosis in "Criterion 4 was reading three wrong things at once" was that
the repair belongs in segmentation, not in the criterion: a panel's box should
contain its own label strip by construction. That is now built, measured, and
WRONG AS STATED. Ownership can be derived correctly - `panel_geometry` does it,
and its columns are in the output - but growing the single box to cover it does
not reproduce the geometry the accidental adoption was producing. The two are not
the same widening.

What follows is that the box has to stop being one rectangle for the CONSUMERS
too, not just in the report:

    `_is_plot`, `holds_data`, the fragment-area guard and `collapse_same_axis`
    all measure the whole box. Widening it to include the label strip changes
    every one of those answers at once, which is why `OWN` loses ladders it has
    no business touching. They have to read `plot_box` first.

That is a change to five call sites, each of which alters a measurement, and
each of which needs its own arm. It is not this round's work, and guessing at it
would repeat what this section documents.

### Six approaches, and now ten

The earlier count of rejected approaches to this gate was six. With `OWN`,
`PLOTSIDE`, `RANK` and `VERT` it is ten, and the four new ones are the first that
were rejected on BOX-LEVEL evidence rather than on counts. The scenarios written
for them - fourteen in `test_continuity`, eighteen in `test_panel_geometry`, every
one paired with a guard and each guard reverted to red - went out of the tree with
the code they pinned. Two findings from writing them are worth keeping:

- `axis_reader` memoises spine runs and axis anchors under `id(dark)`. In the
  driver each `dark` lives for a whole figure and that is sound. In a suite that
  builds a fresh array per scenario, CPython reuses the address of a freed array
  and the next scenario reads the previous one's cached runs: two scenarios that
  pass alone fail together. Nothing in the shipped suites hits it today.
- criterion 4's band term compared `band` over the whole axis run against
  `whole` over the piece's rows, so the ratio counted the PANEL's ink over the
  PIECE's and exceeded 1 whenever anything was drawn in the same columns higher
  up - a panel title 113 rows above the axis top scored 2.44 on a term that asks
  for 0.90. It is only reachable through the vertical direction, which is not in
  the tree, so the fix went with it.

## Two defects found by writing scenarios for a rejected round

Neither is a threshold and neither is in the segmentation argument. Both were
found while writing the scenarios for `OWN`/`PLOTSIDE`/`RANK`/`VERT`, and both
outlive that round.

### The memo key could not tell one raster from another

`spine_run` and `axis_anchor` are memoised under `id(dark)`. `id()` is unique
only while the object is alive, and CPython hands a freed address straight to the
next allocation. The driver's own pattern, measured on two corpus rasters:

    arrays created 8, distinct ids 2, cross-figure reuses 6

Every figure after the first inherited the previous figure's id. So a cache hit
after the first figure could be answering about a DIFFERENT RASTER, and had been
able to since the caches were added.

`figure_key` now registers a weak reference whose callback drops that id's
entries. The callback runs while the referent is being deallocated, before the
address can be handed out again. An object weakref cannot hold falls back to the
old behaviour rather than to an exception - the caches are an optimisation and
must never be the reason a figure fails to measure.

What it changes, measured against `65a781a`:

    two figures    boxes 12 -> 12, ladders 12 -> 12, boxes moved 0
                   BUT axis_sig and the label band rows moved on 345 figure 4:
                   1178:178-330:211 -> 1178:178-333:211, label_y1 330 -> 333
                   1178:579-727:726 -> 1178:577-727:726, label_y0 579 -> 577
    six figures    nothing beyond the added diagnostic text

Both are true, and together they say what kind of defect this is: the stale entry
is always THERE and is only sometimes HIT, because whether it is depends on the
allocation pattern, which depends on the figure set. That is the worst kind, and
the reason to fix it rather than to measure whether being wrong is better. The
thing it moved is `axis_sig` - the identity key the next phase is supposed to
rest on.

    A NOTE ON THE ROUND BEFORE THIS ONE. The `OWN`/`PLOTSIDE`/`RANK`/`VERT`
    measurements were made with this defect present in BOTH arms. It is
    deterministic for a given figure set, and both arms ran the same set in the
    same order, so the comparisons stand as comparisons. But `OWN` changes the
    boxes that key `axis_anchor`, so it changes which entries are asked for, and
    a stale hit could land differently in the two arms. The direction of that
    result - three ladders lost, seven fragment flags gained - is far larger than
    anything this could account for, and the conclusion does not move. It is
    recorded here rather than left for someone to notice.

    A scenario that depends on the allocator handing back the same address is not
    a scenario, so the suite pins the EVICTION - entries present while the raster
    lives, gone when it dies, and untouched when a different raster dies - and
    the collision above is evidence in this file rather than a test.

### Criterion 4's band term was a ratio of two different regions

    band  = dark[axis_top - 2 : axis_bottom + 2, piece_x0 : piece_x1]
    whole = dark[piece_y0 : piece_y1,            piece_x0 : piece_x1]
    inside = band.sum() / whole.sum()

The numerator spans the whole axis run and the denominator spans the piece's
rows, so the value counts the PANEL's ink over the PIECE's. It is not a
proportion and it is not bounded: a panel title 113 rows above the axis top
scores 2.44 on a term that asks for 0.90.

`inside_shares(dark, orphan, run)` now returns both readings - the legacy one and
the intersection, which is what the criterion's own docstring describes and is in
[0, 1] by construction. Ten fixtures hold it to that range, and one of them is
required to break the legacy value, so the section cannot quietly stop proving
anything.

    THE DECISION STILL USES THE LEGACY VALUE, and that is deliberate. Swapping it
    changes which pieces are adopted, which is an arm of its own - and the round
    that tried four such changes at once is the section above this one. This is
    the diagnostic that has to exist before that arm can be run; it is not that
    arm. It costs five `harness` strings on six figures and moves no box.

### And the experiment is data now, not only sentences

Four rejected approaches are documented in this file as prose because every run
root was thrown away with the container it ran in. `harness_compare --record ID`
writes `experiments/ID.json` and `experiments/ID_boxes.csv`: the arms' code and
input hashes, the flag combination, the replay hashes, the per-figure metrics,
and one row per box that moved or that exists in only one arm. NO RASTER GOES IN -
the figures are publisher material, so what is kept is hashes, flags, metrics and
boxes, and a scenario pins that.

The four rejected approaches predate the recorder and their numbers live only in
the section above. Everything from here on has a record.

### One more thing `harness_compare` now says out loud

`outputs_identical`. `VERT` was reported as "no effect" twice and the first
reading was a gate of mine that was shut, so nothing had been evaluated at all.
"Evaluated and agreed" and "never reached" are not the same result and must not
print the same. Telling them apart properly needs counters from inside the tree
under test - candidates discovered, offered, and where each was refused - which
is the next thing the harness needs. This field is the half that can be measured
from outside.

### A count that is not wrong

A reader took `3220 core / 3258 full` from this file as the current status and
compared it with the commit narrative's 3274/3312. Both are correct. The line in
this file is release history - what was true at v9.15, before `test_harness_compare`
and `test_panel_geometry` existed - and this file is deliberately never rewritten
to match today. The CURRENT status is the pair of markers in `README.md`, which
`verify_documented_status.py` compares against the suites' own reported totals in
CI, and nothing else in the repository is allowed to claim it.

## The trace, and what publication 475's figure 1 turned out to be

The overlay for that figure draws one red box for three different failures and
the footer counts two of them, so the picture says the harness failed and not
WHERE. Four rounds were spent guessing at that difference. `gate_trace.py` stops
the guessing: with `TRACE=path` set, `propose.py` writes one row per thing that
happened to a component.

    AXIS_CANDIDATES   every long vertical the anchor search saw, which one it
                      took, and why
    ORPHAN            every piece the cut discarded, and whether it was OFFERED
                      to the six statements or refused before them
    GATE / GATE_WHY   the six verdicts, and their sentences, for a piece offered
    POST              what happened to an accepted piece afterwards
    SELECTED_PASS     which mode and ink WON - so a reader can filter to it
    SELECTED          the rows that survived into the proposal

With `TRACE` unset every call is a branch not taken. Measured against `5a11b5f`
on two figures, two replicates: 12 -> 12 panels, 12 -> 12 ladders, 0 boxes moved,
**0 shared-column mismatches, outputs byte-identical.** Recorded as
`experiments/gate-trace-off.json`.

### 475 figure 1, traced

Selected pass `mode=OFF ink=151`, score `(0, -1, 5, -7)`, seven boxes for six
recorded axes. In that pass the cut discarded eleven pieces:

    reached the six statements       1
    refused before reaching them    10

So the six statements are not what is failing on this figure. The prefilter is.
The three largest refused pieces, with the numbers the refusal now carries:

    99,384,370,664    285 x 294 px   left 44px  share 1.00 reach 34 [gap]
    565,850,373,669   285 x 296 px   right 65px share 1.00 reach 34 [gap]
    553,852,695,981   299 x 286 px   right 280px share 1.00 reach 34 [gap]

Every one has a PERFECT row overlap and fails only on distance, against a reach
that has degenerated to the `ADOPT_GAP` floor of 34 px because the figure draws a
continuous zero line and that row therefore has no gaps to measure. One of them
misses by 10 px. That is the same degenerate case already recorded against
`SELFGAP`, and it is why `VERT` measured as nothing: the vertical direction was
never the thing being refused.

    THE FIRST VERSION OF THAT NOTE SAID NOTHING. It reported the NEAREST panel,
    which is always an overlapping one at 0 px, so every refusal read
    "overlap 0 px, share 0.00". A refusal has to name which of the two conditions
    failed - the gap or the shared rows - or it cannot be acted on.

### And the axis was chosen by a rule nobody had written down as a risk

`_axis_anchor` prefers a run that ends INSIDE the box over one clipped by its
edge, because a clipped run is evidence the box cut something. On this figure
that preference is what picks the wrong column:

    P03 (panel D)  4 candidates: x=795 and 796 free (rows 406-515),
                   x=678 and 679 clipped (rows 513-619).
                   x=678 IS the panel's own left axis, clipped by the box's
                   bottom edge - so x=795, a shorter run standing on a bar,
                   won as "leftmost of the 2 free runs".  LADDER_REFUSED, 2 labels.
    P06 (panel F)  the same rule, the same shape, and here it picked the true
                   left axis x=679 over a clipped x=796.  LADDER_OK.
    P07            0 free candidates, 2 clipped. A vertical cut by BOTH box edges
                   became a panel axis. A box whose every candidate is cut by its
                   own edges is a box that contains no axis, and nothing says so.
    P04 (panel C)  no candidate passed at all, so the spine came from the plain
                   longest-vertical fallback - a third state the overlay had been
                   drawing the same as the other two.

So this figure breaks three assumptions at once, and they are not the same
repair:

    a fragment keeps a trustworthy axis        - P03, P06, P07 say otherwise
    severed data is inside the self-gap reach  - C and E say otherwise, by 10 px
    a panel can be recovered from its own box  - the 2x3 repetition says otherwise

### What this settles about the next arm

The arm named in `HARNESS.md` - mark detection and the component-role tests read
`plot_box` - is still the right FIRST arm, and it is not the arm that fixes this
figure. Nothing it touches runs before the prefilter that refuses C and E, and
nothing it touches chooses an axis. Evaluating it against 475 figure 1 would
score it on work it does not do.

What this figure needs, in the order the trace makes visible:

    1  a box whose only axis candidates are clipped at both edges is not a panel.
       That is P07, and it is a statement about the candidate, not a threshold
    2  the axis is a HYPOTHESIS until something supports it - tick marks on one
       side, a ladder that reads, agreement with the axis column of the other
       panels in its row. Free-beats-clipped is a tie-break masquerading as that
    3  the reach is the wrong question for C and E. They already have a valid
       axis; what is wrong is that the plot belonging to that axis is incomplete.
       "Is this piece near?" cannot see that. "Is this axis's plot whole?" can

None of the three is in this commit. What is in this commit is the rows that say
so, and they are checkable: `test_gate_trace.py`, 11 scenarios, each paired with
one guard, each guard reverted to red.

## Four axis states, and the axis the search rejected reads better

`4397cad` separated a refused ladder from a fragment flag. It did not separate
these, and it should have: a spine that came from the plain longest-vertical
fallback, a spine that is a run with no ladder behind it, and a spine whose every
candidate was cut by the box's own edges were all drawn as the same blue line.
`gate_trace.axis_status` names them.

    AXIS_ATTESTED        a candidate whose ladder reads
    AXIS_GEOMETRY_ONLY   looks like an axis, no ladder behind it
    AXIS_FALLBACK        `_axis_anchor` returned nothing; the spine is the plain
                         longest vertical, and the trace now records that search's
                         own candidates and tie rule
    AXIS_UNRESOLVED      every candidate cut by the box's edges

REPORTED, NEVER ACTED ON. Promoting or demoting a box on this is a change to what
the pipeline returns, and that is its own arm.

Publication 475's figure 1, selected pass `OFF/151`:

    P01  AXIS_ATTESTED       P05  AXIS_ATTESTED
    P02  AXIS_ATTESTED       P06  AXIS_ATTESTED
    P03  AXIS_GEOMETRY_ONLY  P07  AXIS_UNRESOLVED
    P04  AXIS_FALLBACK

Four of seven boxes have a defended axis. THAT is this figure's number, not
"seven boxes for six recorded axes".

### Arm B: a ladder read off every candidate, and nothing changed

`SHADOW=1` alongside `TRACE` reads a ladder off EVERY axis candidate a box had,
not only the one the search took, and records all of them. Production still uses
the chosen one. On 475 figure 1:

    P03  box 609,967,403,619   production took x=795
         x=795  free      2 labels   ladder REFUSED   <- chosen
         x=796  free      1 label    ladder REFUSED
         x=678  clipped   3 labels   ladder OK    residual 0.03 px   cv 0.0008
         x=679  clipped   6 labels   ladder OK    residual 0.03 px   cv 0.0012

    P06  box 609,967,738,938   production took x=679
         x=679  free      3 labels   ladder OK    residual 0.56 px   <- chosen
         x=796  clipped   2 labels   ladder REFUSED

    P07  box 428,500,834,951   production took x=444
         x=444  clipped   0 labels   ladder REFUSED   <- chosen
         x=445  clipped   1 label    ladder REFUSED

    P04  box 101,268,499,627   only the fallback column exists, and it reads a
         ladder: 3 labels, residual 0.11 px. Panel C is a third of its width.

Read together those four boxes say one thing:

    LADDER VALIDITY DECIDES BOTH P03 AND P06 CORRECTLY. `free` beating `clipped`
    decides only P06. The preference is a tie-break that had been making the
    primary-axis choice, and on P03 it chose a short run standing on a bar over
    the panel's own axis - which reads six numerals at a residual of 0.03 px.

    P07 HAS NO CANDIDATE THAT READS ANYTHING. Under a ladder-first ranking it
    would have no attested axis at all, which is what should stop it being
    counted as a seventh panel. `mode_score` uses `len(recs)`, so today it is.

    AND P04 SEPARATES TWO THINGS THAT HAD BEEN ONE. Its `LADDER_OK` means a
    column of numerals was found beside x=212. It does not mean x=212 is the
    panel's axis, and it does not mean panel C was found. Ladder correctness is
    not panel completeness.

None of this is a change to the pipeline. Measured against `4397cad` on two
figures, two replicates: 12 -> 12 panels, 12 -> 12 ladders, 0 boxes moved, 0
shared-column mismatches, outputs byte-identical
(`experiments/trace-round-2-off.json`).

### A contradiction of mine, and the fix

`test_gate_trace.py` said a box whose every candidate is cut by its own edges
"is a box that contains no axis". The runtime says `pick = free or clipped` and
returns one. The prose asserted a contract the code does not have, which is the
decoration problem one level up - a scenario whose docstring is aspirational
teaches the next reader something false. The scenario now pins what the code
does, asserts the returned candidate, and names the state `AXIS_UNRESOLVED`;
what the function SHOULD return is an arm, not a docstring.

Two smaller ones from the same review: `KINDS` was missing `GATE_WHY` and
`SELECTED_PASS`, so `summary()` never mentioned two kinds the recorder writes -
a scenario now checks the tuple against the list of kinds actually written. And
the fragment flag now writes a `FRAGMENT_DECISION` row with the rule, the
measured value and the threshold, instead of only a sentence on the panel row.

    A SESSION HAZARD WORTH WRITING DOWN. The fallback trace appeared not to fire
    while its source clearly contained the call. It was a stale `__pycache__`
    entry: `inspect.getsource` reads the `.py` and proves nothing about what is
    executing, and the mtime granularity is one second. Any mutation run that
    edits a module and re-runs a suite within the same second can measure the
    old bytecode - so the mutation harness now clears `__pycache__` between arms.

### What is still not traced

    the cut's lineage - which two leaves were siblings of one cut, which gutter
    split them, and which of the pair kept the axis. Without it "this piece is a
    direct sibling of that panel" cannot be asked, and that is the only
    structural reason to offer C and E's data past a distance prefilter
    the fragment-area guard's per-box share, as opposed to the figure-wide one
    the x reader's own gates

## Arm A: the cut remembers its halves, and the gate is asked without a distance

`_cut` kept only its leaves. Which two of them were the halves of ONE cut - the
single fact that makes a distance unnecessary - was not recoverable downstream at
any price. `CUT_LINEAGE` keeps it: for each half, the cut's id, the other half,
the axis, and the gutter it split on. `cut_sibling_of(piece, panel)` then asks the
only structural question there is - is that panel inside the other half of the cut
that made this piece - and `SHADOWGATE=1` puts the six statements to every such
pair the DISTANCE prefilter refused. It adopts nothing: `_shadow_gate` is never
handed the output list, and a scenario asserts its signature.

Measured against `88dba15` on two figures, two replicates: 12 -> 12 panels,
12 -> 12 ladders, 0 boxes moved, 0 shared-column mismatches, outputs
byte-identical (`experiments/arm-a-lineage-off.json`).

### What the gate says when the distance is out of the way

Publication 475's figure 1, selected pass `OFF/151`. Ten pieces were refused
before the gate. Of those, FOUR have a cut-sibling among the panel boxes:

    piece 311,383,834,975    72x141    cut 7  col  gutter 38 px   GATE ACCEPTS
        data_no_axis O   rows O (overlap 1.00)   coords O (foot 1.00, band 0.86)
        baseline X   caption -   regular -
        NECESSARY(3 and 2 and 5) + EVIDENCE(coords), no veto -> adopt
    piece 99,384,370,664    285x294    cut 5  col  gutter 44 px   GATE REFUSES
    piece 142,487,317,341   345x24     cut 4  row  gutter 20 px   GATE REFUSES
    piece 435,469,961,975    34x14     cut 8  row  gutter 10 px   GATE REFUSES

    397 figure 1   7 shadow verdicts, 0 accepted
    475 figure 2   no cut-sibling pairs at all, so nothing to say

So the route is sound in the direction that matters: it does not loosen the two
figures that are already right, and on the figure that is wrong it recovers a
piece that the reach missed by four pixels. `reach` was 34 and the gutter is 38.

### And it does NOT recover panel C, for a reason worth having

Panel C's missing 285 x 294 block IS a cut sibling - cut 5, a column cut on a
44 px gutter - so it reached the gate. The gate refused it, and the trace says
why: the panel the relation paired it with is

    428,500,510,664    72 x 154

which is not panel C's box (`101,268,499,627`). The sibling half had been cut
again, and the box that survived into `boxes` is a fragment inside it rather than
the panel. Judged against that fragment, `rows` fails (the piece spans 370-664,
the fragment 510-664), `coords` reads a foot share of 0.07, and `baseline` sees a
61 px crossing against an internal maximum of 18.

    SO THE RELATION IS RIGHT AND THE PARTNER IS WRONG. `cut_sibling_of` accepts
    ANY box contained in the sibling half, and when that half has been cut into
    several pieces the first one it finds need not be the panel. The next question
    is not a threshold either: it is how to pick, among the boxes inside the
    sibling half, the one that IS the panel - most of the half's area, or the one
    holding the axis, or the one the assignment layer would name.

That is the whole finding. Arm A as specified is necessary and not sufficient, and
what it is missing is now a named question with a measurement behind it rather
than a guess.

    SIX OF THE TEN REFUSED PIECES HAVE NO CUT SIBLING AMONG THE PANELS AT ALL,
    including the three largest (299x286, 285x296, 74x477). Their sibling halves
    were merged, grown or replaced before the panel list was built, so the lineage
    points at boxes that no longer exist as panels. Whether to follow the lineage
    through those transforms is a second question, and it is bigger than this one.

### A bug this found in itself

The first run recorded ZERO shadow verdicts. `panels` trims every leaf before
offering it as an orphan, so the piece handed to the gate is not the half the cut
made and its tuple is not a key in the lineage. `cut_sibling_of` now falls back to
the SMALLEST recorded half that contains the piece - smallest, because a piece is
inside every ancestor half and the one it came out of is the innermost. Two
scenarios pin both halves of that: the trimmed lookup, and the smallest-wins rule.

    AND THE LADDER SHADOW MOVED TO ITS OWN FLAG. `SHADOW=1` reads a ladder off
    every axis candidate and pays for OCR per candidate; `SHADOWGATE=1` asks the
    six statements and pays for geometry. Sharing one flag made Arm A cost forty
    minutes for measurements it did not use.

## A correction: panel C was never in the relation's search space

The previous section said the cut-sibling relation found the wrong partner for
publication 475's figure 1 panel C, and called that a ranking problem. It is not.
The coordinates settle it:

    the piece               99,384,370,664
    panel C's selected box  101,268,499,627

The panel is INSIDE the piece. `cut_sibling_of` asks one question - is the panel
in the OTHER half of the cut that made this piece - so panel C could never be the
answer, and the box that question does find (`428,500,510,664`, 72 x 154) is
simply the only thing over there. The relation was right and the search space was
wrong.

So the ten refused pieces are not one problem. They are classified now, and the
five values are five REPAIRS rather than five scores:

    OPPOSITE_HALF_UNIQUE_PANEL      exactly one panel in the other half
    OPPOSITE_HALF_MULTIPLE_PANELS   two or more, and choosing by area or discovery
                                    order is the tie-break this project keeps
                                    having to withdraw
    SAME_HALF_NESTED_PANEL          the panel is inside the piece
    OPPOSITE_AND_NESTED             both at once - two repairs apply and the pair
                                    names neither
    NO_SELECTED_PANEL_DESCENDANT    no final panel stands in either relation
    CUT_LINEAGE_AMBIGUOUS           two equal-sized halves contain the piece, so
                                    the answer would depend on dict order

`OPPOSITE_AND_NESTED` is the value that had to exist. Asking "opposite?" first and
answering yes is exactly how the fragment got named as C's partner, and only that
pair is now withheld from the gate - `offer_to_shadow_gate` returns a panel only
for the unambiguous case.

### The three figures, classified

    475 figure 1   OFF/151    10 refused
                   6  NO_SELECTED_PANEL_DESCENDANT
                   3  OPPOSITE_HALF_UNIQUE   -> offered, 1 accepted
                   1  OPPOSITE_AND_NESTED    -> panel C, not offered

    397 figure 1   OFF/158    11 refused
                   10 NO_SELECTED_PANEL_DESCENDANT
                   1  OPPOSITE_AND_NESTED    -> not offered
                   0 accepted

    475 figure 2   PLAIN/140   7 refused, all NO_SELECTED_PANEL_DESCENDANT

Shadow verdicts fell from 112 to 39 across the three figures, and every one that
disappeared was a verdict about a pair that names two different repairs. The one
acceptance is unchanged: `311,383,834,975` into P05, cut 7, a 38 px gutter against
a reach of 34.

    AND THE "SIX WERE MERGED OR GROWN" CLAIM IS WITHDRAWN. What the trace supports
    is `NO_SELECTED_PANEL_DESCENDANT`: no final panel stands in either relation to
    those pieces. WHICH transform lost the lineage - trim, merge, grow, snap, slab,
    a different mode - is not measured, and saying it was would be the same kind of
    overreach this file keeps recording. It needs a region-provenance record that
    survives every transform, which is a bigger change than this one.

## Three harness defects, one of which ran the experiment I turned off

    SHADOWGATE=0 TURNED THE EXPERIMENT ON. `bool(os.environ.get("SHADOWGATE"))` is
    True for the string "0", so the one value a person reaches for to disable a
    flag was the value that ran it. `SHADOW` and `TRACE` had the same shape.
    All three now read the way every other flag in the package reads, and a
    scenario pins unset, "0" and "1" for each.

    THE MANIFEST DID NOT RECORD WHETHER AN ARM WAS OBSERVED. `ENV_KEYS` had none
    of the new flags, so an arm run under `SHADOWGATE` and one run without it
    stamped identically. `TRACE` names a path, so stamping its value would make
    two arms differ over a filename; what is stamped instead is three derived
    booleans - `TRACE_ENABLED`, `SHADOW_ENABLED`, `SHADOW_GATE_ENABLED`.

    `gate_trace.py` WAS NOT PART OF AN ARM'S CODE. It decides nothing, and it is
    what turns a run into a conclusion, so a change to it that moves a reported
    number has to move the arm's code reference. It is in `CODE_FILES` now, along
    with `panel_geometry.py`, which had also been missing.

Re-measured against `ae45ece` on two figures, two replicates: 12 -> 12 panels,
12 -> 12 ladders, 0 boxes moved, 0 shared-column mismatches, outputs
byte-identical, and the manifest now differs at `code.gate_trace.py` where before
it could not (`experiments/relation-enum-off.json`).

### And the tool failed to catch me deleting its lock

Between killing a run and relaunching it I ran `rm -rf` on the run root. The lock
lives inside the root, so it went with it, and two comparisons then interleaved in
one directory until the second removed the first's staging out from under it:

    FileNotFoundError: run_rel/candidate/input_manifest.json

Which is precisely the failure this whole file was built to prevent, arriving
through the one door it had left open. `assert_lock_still_ours` is called after
each arm: the lock must still exist and still name this run. Two scenarios pin it -
one on the function, one on the driver, where the base arm deletes the lock while
it runs and the driver has to refuse.

## The region DAG, and the cause it settles

`CUT_LINEAGE` answers "which two halves were one cut". It cannot answer "what
became of that half", because a box is a VALUE: a trim that changes nothing, a
merge whose result equals an input and two modes producing the same rectangle all
look identical afterwards. `REGIONS` is the DAG - one entry per box a transform
produced, with its transform and its parents - and it is written only while the
trace is on.

    CUT_HALF   TRIM   MERGE   COLUMN_SIBLING   ADOPT   CAPTION_TRIM
    BROAD_SLAB   SNAP_TO_SPINE   RULE_CELL   DROPPED

A box that survives a whole-list transform unchanged is registered as a
pass-through, so the DAG records that the step SAW it; a box the step removed is
registered as `DROPPED` with the removed box as its parent. A new box gets the
boxes it overlaps as parents, and the note says so - that is as much as a
list-in list-out transform can honestly report without each one being rewritten
to name its own inputs.

### What it settles

Last round said six of publication 475 figure 1's refused pieces had sibling
halves that "were merged, grown or replaced", and then withdrew the claim as
unmeasured. Now it is measured. `fate_of` walks the descendants of the sibling
half and lists the transforms its line went through:

    475 figure 1   six NO_SELECTED_PANEL_DESCENDANT pieces,
                   sibling line: CUT_HALF;TRIM   and it stops there
    397 figure 1   six stop at CUT_HALF;TRIM, two never reach TRIM at all,
                   two go the whole way: ...MERGE;COLUMN_SIBLING;ADOPT;CAPTION_TRIM
    475 figure 2   four stop at CUT_HALF;TRIM, three go the whole way

So on 475 figure 1 the answer is not merge, not grow, not replace. THE SIBLING
HALF WAS FILTERED OUT BEFORE THE CANDIDATE LIST EXISTED - it was trimmed and then
failed `_is_plot` or `holds_data`, and `keep` never contained it. No route built
on lineage can reach a panel that was never a candidate, which is a different
question again from the two this round is about, and a smaller one than the guess
it replaces.

    THE FOUR PIECES WITH A LIVE LINEAGE on that figure all read
    `CUT_HALF;TRIM;MERGE;COLUMN_SIBLING` - the sibling half survived to the
    candidate list and was merged with its column siblings. Those are the four
    the relation could classify at all.

## The post-adoption shadow: a gate accept is one step, not a repair

`_shadow_gate` stopped at the six statements. A union that passes them can still
duplicate an existing box, swallow a neighbouring panel, take in a foreign axis
or move the spine the ladder was read from - and recording the accept alone would
be claiming the repair on the strength of its first step.
`_shadow_post_adoption` builds the union production would build and measures what
production would check next. It is never handed the output list either.

The one accepted piece on 475 figure 1:

    piece 311,383,834,975  into panel 92,273,695,975  ->  union 92,383,695,975
    width                    181 -> 291
    duplicate                False
    contains another panel   0
    foreign axes in union    0
    spine                    173 -> 173, unmoved
    would production refuse  False

So this one survives its own post-checks: the widening does not move the axis the
ladder was read from and does not reach anything else's.

    WHAT IS STILL NOT MEASURED IS THE LADDER ITSELF. Re-reading it on the union
    costs OCR, which `_shadow_gate` deliberately does not pay - it runs inside
    `adopt_orphans`, four modes deep. Spine stability is a proxy and is reported
    as one. And this is ONE true positive on ONE figure against two controls;
    promoting the route needs the fifteen-figure comparison, with accepted-pair
    counts, unique-partner share, post-adoption ladder change, foreign-axis change
    and gold-box boundary change - none of which one accept can stand for.

## What the next arm is, now that the DAG can define it

Publication 475 figure 1's panel C is `OPPOSITE_AND_NESTED`: its selected box is
INSIDE the piece. The union of the two is the piece, so there is nothing for an
adoption to add. What is missing is the data in the piece that lies OUTSIDE the
panel's plot core, and the question is

    ancestor region  minus  the selected panel's plot region
    -> residual connected components
    -> each one asked, against that panel's attested axis, whether it is data

That is `ANCESTOR_REGION_COMPLETION` and it is not `CUT_SIBLING`. It needs the
plot region, which `panel_geometry` computes and nothing yet consumes, and the
ancestor region, which the DAG now provides. It is the first thing this project
has been able to state precisely rather than approach through a threshold.

## ANCESTOR_REGION_COMPLETION, measured - and the premise it falsifies

Built as designed, `RESIDUAL=1`, shadow only: `_shadow_residual` is never handed
the output list, the box list comes back unchanged, and with the flag off every
call is a branch not taken. Five statements per blob, all five required:

    plot_side         on the side of the spine the marks are on
    no_own_axis       no thin, long vertical rule of its own
    shares_axis_rows  beside the axis run, not above or below it
    no_foreign_spine  no other panel's spine in its columns
    above_caption     not in the caption

`no_own_axis` is `_rules`, not `_has_y_axis`. The second asks for a vertical run
covering `AXIS_RUN` of the box's OWN height, and a single bar is exactly that, so
every bar in the residual would have reported itself as carrying an axis. A spine
is thin: 1 to 4 columns, `RULE_MIN_LEN` long.

### What it found on publication 475 figure 1

The piece is `99,384,370,664`, panel C is `101,268,499,627`, and the plot core the
subtraction uses is `212,268,499,627`. Fifty-six components, thirty-one of them
larger than `ADOPT_MIN` in both directions, and ONE passes:

    349,384,510,630   491 px   DATA        the 0.005 box plot, whole
    311,348,448,512   350 px   refused     axis rows        (share 0.031)
    191,214,375,400   278 px   refused     plot side, axis rows
    198,210,649,664   132 px   refused     plot side, axis rows
    ... 27 more, 24 of which are refused by `shares_axis_rows`

The blobs ARE the missing data - the picture shows the second and third box-plot
groups sitting outside a panel box drawn around the first - and the clause doing
almost all of the refusing is `shares_axis_rows`. Which is where the row stops
being about panel C and starts being about its axis.

### The summary row refuses to let that pass unnamed

    axis_anchored=False   axis_n_free=0   axis_n_clipped=0
    spine_x=212           axis_run=510-575

`_axis_anchor` found NO candidate at all - not a clipped one, not a bad one - so
the spine is the plain longest-vertical fallback, and the run it reports is 65 px
of a 128 px box. `shares_axis_rows` asks for `ADOPT_SHARE` of the shorter side
against THAT window, so a 64 px box plot 60 px away scores 0.031 and is refused.
This is why the axis provenance is recorded beside the verdicts instead of being
asserted: without those three numbers the round would have read as "the residual
completion refuses the data", and what it actually says is "the residual
completion was measured against a column nothing attested".

### And the name is wrong, which the DAG is what proves

    ancestor_region 33  ->  panel_region 59   descends = False

Region 33 is the piece, `TRIM` of `CUT_HALF` 9. Region 59 is panel C's box, and
its provenance line reads `COLUMN_SIBLING, parents (none), from 0 overlapping`:
the box overlaps NOTHING in the list `column_siblings` was handed. Panel C's box
was not cut out of the piece and was not derived from any region at all - it was
CONSTRUCTED from the other panels' column geometry to fill a slot.

So the piece is not the panel's ancestor. The containment that `classify_piece`
reports is geometric, established from `CUT_LINEAGE`, and the DAG says there is no
genealogy behind it. `ANCESTOR_REGION_COMPLETION` names a relation this figure
does not have, and the honest name for what was measured is
`ENCLOSING_PIECE_COMPLETION`. The field that says so is in every summary row, and
it was put there to be read rather than to be right.

That also explains the fallback axis: a box nobody found from ink has no reason to
have an axis in it. The two facts are one fact.

### What this closes and what it opens

CLOSED: completion is not blocked by the components being hard to find. They are
found, they are the right ones, and the geometry is not the problem.

OPEN, and now in the order the measurement puts them:

1. Panel C's box is a `column_siblings` construction with a fallback axis. Until
   that box is either attested or withdrawn, every measurement inside it inherits
   an unattested column - including this one.
2. `shares_axis_rows` measured against `spine_run` is measured against whatever
   the axis search returned. Against an `AXIS_ATTESTED` spine it is the right
   question; against `AXIS_FALLBACK` it is a coin.
3. The piece stops at x=384 and the figure's third group starts at x=680. Even a
   perfect completion of this piece recovers two groups of three.

None of this is a threshold, and none of it was reachable before the trace, the
relation enum and the DAG were in place - which is the argument for having built
them in that order.

## Where the boxes came from, on 25 figures - and the reading the picture refused

The last round ended by saying panel C's box was a `column_siblings` construction
with a fallback axis, and that until such a box is attested or withdrawn every
measurement inside it inherits an unattested column. That is one figure. This
round asks how often it happens, and the asking needed two joins fixed first.

### Two joins were naming the wrong pass

`gate_trace.last` matches on the fields it is handed and nothing else, so the
axis candidates behind a SELECTED row were joined by BOX ALONE - and the row that
wins is written after the mode loop has moved on. 475 figure 1 wins on OFF and
ends on GRID; a box both modes produced was joined to GRID's candidates under
OFF's name. `last_in_pass` merges the whole context into the match, `png` and
`fig` included, because two figures in one run share mode and ink and can share a
box value.

`REGIONS` had the same shape of defect one structure over: `panels()` clears the
DAG per call, so after the loop it holds the LOSING pass's provenance.
`snapshot_regions` / `restore_regions` keep one per pass and put back the
winner's. Both are the mislabelled-SELECTED defect again, and both were found by
looking for it rather than by being surprised.

### What the DAG says about the boxes

`roots_of(rid)` returns the transforms of a region's PARENTLESS ancestors.
`CUT_HALF` is the honest root: the box came out of the whitespace cut. Anything
else means a transform INVENTED the box. `constructed` is written as "not every
root is CUT_HALF" rather than as a list of the transforms that count, because the
list is what gets forgotten when the next transform is added.

Twenty-five figures, 91 selected panels:

    roots                    n
    CUT_HALF                57
    COLUMN_SIBLING          13
    BROAD_SLAB              12
    RULE_CELL                5
    BROAD_SLAB;CUT_HALF      4

**34 of 91 selected panels - 37% - sit in a box no cut produced, on 12 of the 25
figures.** That number was not measurable before this round, and it is the
finding.

### The first reading of the table, and why it is wrong

    ALL 91          ATTESTED  GEOMETRY_ONLY  FALLBACK  UNRESOLVED   n   ladder
    cut                   43              9         2           3  57   47/57
    constructed           18             10         5           1  34   23/34

Read alone that says invented boxes carry worse axes. Publication 177's figure 2
supplies 8 of the 13 `COLUMN_SIBLING` panels, so the picture was drawn - and the
picture says the ladder fails on ELEVEN of its fifteen panels REGARDLESS of how
the box arrived. It is a five-by-three grid, and it prints its y axis numerals
ONCE PER ROW. P02, P03, P05, P06 are cut boxes and refuse; P08, P09, P10, P11,
P12, P14, P15 are invented ones and refuse; P01, P04, P07, P13 are the leftmost
of their rows and read. The discriminator is the COLUMN, not the origin.

CORRECTION, and it matters more than a count. The first version of this section
said TEN and listed ten, leaving out P10 - which was in the data the whole time
and is the one panel the shared-axis explanation does NOT cover:

    P10  210,439,840,1072  INVENTED  ink 17  no left reader  LADDER_REFUSED

P10 is the LEFTMOST panel of row 4, so nothing to its left can lend it a
calibration, and 17 inked columns beside its axis is not a blank strip. Row 4 is
therefore not a shared-axis row with two dependants; it is a row with NO
provider, and P11 and P12 cannot be explained by the layout either. Writing
"ten" turned the one real failure on this figure into part of the artefact, which
is exactly the mistake the section is about.

`AXIS_ATTESTED` is defined as "a candidate whose ladder reads". A panel that
shares its row's axis therefore cannot be attested however well its box is drawn,
and a table that does not hold those apart is measuring the figure's layout.

### So the strip is measured: is there anything printed to read

`panel_geometry.label_ink` counts inked columns where numerals sit - over the
AXIS RUN and not the box, within `LABEL_BAND_MAX` of the spine, skipping the
`RULE_MAX_W` columns the tick marks occupy. On 177 figure 2 the two populations
are not close: the four panels that read measure 32, 32, 29, 28, and the panels
with a bare spine measure 2, 3, 3, 3, 3, 4.

Across the corpus, of the 21 refused ladders **8 have four or fewer inked columns
beside the axis** - refusals of a blank strip, which is the figure's layout and
not a failure. NOTHING TURNS THE COUNT INTO A VERDICT: the values run
2, 3, 4, 16, 17, 18, 20, 22, 24, 26, 27, 32, 34, 48, 56, and any line drawn
through that is a constant nobody measured. The count is reported, and so is
`row_left_reader` - whether a panel in the same rows to the left reads a ladder -
which is structural and needs no threshold at all.

    NO LEFT READER  ATTESTED  GEOMETRY_ONLY  FALLBACK  UNRESOLVED   n   ladder
    cut                   29              4         2           2  37   33/37
    constructed           15              6         4           0  25   19/25

    by root, same subset
    CUT_HALF              29              4         2           2  37   33/37
    BROAD_SLAB             5              3         2           0  10    7/10
    COLUMN_SIBLING         2              3         2           0   7    4/7
    BROAD_SLAB;CUT_HALF    4              0         0           0   4    4/4
    RULE_CELL              4              0         0           0   4    4/4

The gap narrows and the per-transform rows are 4, 4, 7 and 10 panels wide. NO
RANKING OF THE TRANSFORMS IS SUPPORTED AT THESE NUMBERS, and the round does not
make one. What survives is the 37%, the fact that it is now visible per panel,
and the fact that the first reading of it was an artefact that a picture caught.

### And panel C is still panel C

    475 Fig. 1  P04  101,268,499,627  INVENTED  AXIS_FALLBACK  ink 23 from x=207
                                      no left reader           LADDER_OK

Its strip is not blank - 23 inked columns, five pixels from the spine - and its
ladder reads. Its box covers one of the panel's three box-plot groups. So the
shared-axis explanation does not cover it, and the previous round's reading of it
stands unchanged.

### Two losses worth recording

The container was reclaimed mid-round and the working directory went with it.
Everything through `2f481aa` was pushed, so the code came back from the
repository and the restored container reproduced the recorded output hash
`c8e073ad...` exactly - which is what `experiments/*.json` is for. What did NOT
come back was `png/capt.py`, which had never been committed, so every renderer in
that folder stopped running from a clean checkout. It is committed now. The
caption scan `captions.csv` was already gone the same way, and is recorded as
absent rather than quietly missing.

## The owner of a y scale is a row group, not a panel

The correction above is not only a count. If publication 177's figure 2 prints
its y axis numerals once per row, then the pipeline's assumption - every panel
carries its own ladder - is wrong about the figure, and no amount of better
reading fixes it. This round drops that assumption, in the order the review set.

### One value was answering three questions

`axis_status` mixed how the spine was found, whether numerals were read beside
it, and nothing about whether the box is the whole panel. On a grid figure the
value it produced was a fact about the LAYOUT: a middle panel with a correct box
and a correctly anchored spine came back `AXIS_GEOMETRY_ONLY`, which reads as a
defect in the panel and is not one. Three cells now, and `axis_geometry` does not
take the ladder as an argument at all - that absence is the fix, and a scenario
holds it by asserting the signature:

    axis_geometry     ANCHOR_FREE | ANCHOR_CLIPPED | FALLBACK_LONGEST
                      | GEOMETRY_UNRESOLVED | GEOMETRY_UNOBSERVED
    calibration       LOCAL_LADDER | NONE            (SHARED_ROW is proposed by
                                                      the shadow; MANUAL is
                                                      human-only)
    panel_completeness  COMPLETE | FRAGMENT | UNKNOWN

`AXIS_ATTESTED` is retired for `LOCAL_LADDER_ATTESTED`, because what it ever
meant is that a ladder was read beside the axis - which a shared-axis panel
cannot do however well its box is drawn.

Re-measured on eight figures, 46 panels, the split says what the composite was
hiding:

    old composite        new axis_geometry      calibration       n
    AXIS_ATTESTED        ANCHOR_FREE            LOCAL_LADDER     26
    AXIS_GEOMETRY_ONLY   ANCHOR_FREE            NONE             14
    AXIS_FALLBACK        GEOMETRY_UNOBSERVED    LOCAL_LADDER      3
    AXIS_FALLBACK        GEOMETRY_UNOBSERVED    NONE              1
    AXIS_FALLBACK        FALLBACK_LONGEST       LOCAL_LADDER      1
    AXIS_UNRESOLVED      ANCHOR_CLIPPED         NONE              1

All fourteen `AXIS_GEOMETRY_ONLY` panels have the STRONGEST geometry available -
a free anchored run - and simply no numerals printed beside them. And four of the
five `AXIS_FALLBACK` panels were never fallbacks: no candidate row exists for
those boxes in the winning pass at all, because the box was produced after the
anchor search ran. Three of the four read a ladder. `GEOMETRY_UNOBSERVED` exists
so a join that found nothing stops being reported as a measurement that found
nothing.

### Y_SCALE_GROUP: proposed, measured, applied to nothing

`YGROUP=1`. Panels are banded by the row overlap of their AXIS RUNS - over the
runs and not the boxes, because an invented box can be far taller than the axis
inside it and would pull in the row above - and each band gets one row plus one
row per member. Three outcomes, none of which needs a tolerance:

    SHARED_ROW_CANDIDATE        exactly one calibration among the members
    Y_SCALE_GROUP_NO_PROVIDER   no member read a ladder
    Y_SCALE_GROUP_AMBIGUOUS     two members read DIFFERENT ladders

NO TOLERANCE IS APPLIED TO ANY RESIDUAL, which is the instruction and also the
only honest option: the distribution does not exist yet. What is recorded per
member is `overlap_share`, `d_baseline`, `d_axis_top`, `d_axis_bottom`,
`d_height`, and the TICK ROW SIGNATURE - the row centres of the short marks
abutting the spine, which is the one piece of evidence a panel with no numerals
can still offer. The tick window starts at the end of the spine's own measured
rule rather than at the reported spine column, because `spine_and_baseline`
returns one column of a rule that may be three wide, and a fixed window taken
backwards from the wrong end sits inside the rule and makes every row a tick.

Single linkage can chain one row into the next through overlapping middles. That
is not forbidden - forbidding it needs a tolerance - it is REPORTED, as the
group's weakest pair (`min_pair_overlap`), so a chained band is visible in the
output instead of being asserted away.

### What it says about publication 177's figure 2

    G1  SHARED_ROW_CANDIDATE   provider P01   members P01 P02 P03
    G2  SHARED_ROW_CANDIDATE   provider P04   members P04 P05 P06
    G3  SHARED_ROW_CANDIDATE   provider P07   members P07 P08 P09
    G4  Y_SCALE_GROUP_NO_PROVIDER              members P10 P11 P12
    G5  SHARED_ROW_CANDIDATE   provider P13   members P13 P14 P15

    local ladder providers        4
    shared-calibration candidates 8
    currently calibratable panels 12
    unresolved panels             3
    unresolved scale groups       1
    ladder_pass_count             4

`ladder_pass_count = 4` and "12 of 15 panels have a defensible route to a y
scale" are both true, and the second is the one that describes the figure. Row 4
is the exception and it is named as one rather than folded into the layout
explanation.

The residuals for the eight panels a transfer would actually serve are tight:
`tick_residual_max` 1 to 3 px, `d_baseline` 1 to 3, `d_axis_top` 1 to 16,
`overlap_share` 1.00 throughout. Measured against EVERY dependant on the eight
figures - including rows where each panel reads its own numerals and no transfer
is wanted - the same fields run to 47, 38 and 87. So the distribution separates,
and it separates WITHOUT a tolerance having been applied, which is the argument
for building it before deciding rather than after.

    A row where every panel reads its own ladder comes back AMBIGUOUS, and that
    is not a defect - it means no transfer is needed. Four of the 28 groups are
    that case. Counting them as problems would count a well-labelled figure as
    one.

### What is NOT promoted

Nothing writes `SHARED_ROW` into a panel's `calibration` cell. There is no
transfer, no `a` and `b`, no `Calibration_Source_Panel_ID` in the proposal
output. `SHARED_ROW_EXACT` and `SHARED_ROW_AFFINE` are named in HARNESS.md as the
two shapes a transfer could take and neither is built. The gate on building them
is the metamorphic corpus the review specifies: take figures whose numerals ARE
repeated on every panel, mask the dependant's labels, transfer from the provider,
and compare slope, intercept and digitized values against the panel's own
reading - with negative fixtures for a shared row at two different scales, linear
against log, an axis break on one side only, a dual axis, an inset, two providers
that disagree, and a row with no provider. Seven of those exist as drawn
scenarios already; the corpus experiment does not.

### P10, diagnosed on its own

Row 4 is not a shared-axis row and P10 is not an unreadable one. Every fact the
review asked for, from `SHADOW=1` on that figure:

    box            210,439,840,1072        origin COLUMN_SIBLING
    axis_geometry  ANCHOR_FREE             one free candidate at x=239, run 843-1069
    candidates     1 free, 0 clipped       nothing was rejected in its favour
    tick rows      842, 917, 993, 1059     four, evenly spaced
    label ink      15 columns, 14 of them INSIDE the box; leftmost at 179
    numerals       printed: 4, 3, 2, 1     read: 1, at y=1069.3
    shadow ladder  "only 1 label(s); 3 needed to check a ladder"
    completeness   COMPLETE

The geometry is right, the box does not clip the numerals, and the ticks are
found. **Publication 177's figure 2 labels its fourth row with SINGLE DIGITS -
4, 3, 2, 1 - and the reader returned one of the four.** The other three panels of
that column print two and three digit numbers and read three labels each.

So P10 is an OCR round on single-glyph numerals, not a segmentation round and not
a calibration-transfer round. Which also means row 4's provider is RECOVERABLE:
if P10 reads its own ladder, G4 becomes a SHARED_ROW_CANDIDATE like the other
four and the figure's twelve calibratable panels become fifteen. Until then P11
and P12 must not be calibrated automatically, and sending that row to manual
calibration is the safe answer.

## Four things the row-group shadow was claiming and could not

The last round's picture read as though a shared y scale had been verified on
publication 177's figure 2. It had not, and four separate mechanisms were
overstating it. Each is closed here; none of them changes what the pipeline
returns.

### 1. The summary added the proposals to the facts

    currently calibratable panels 12

Four panels on that figure have a calibration. The other eight had a PROPOSAL
against an unvalidated transfer, and adding the two produced a number that reads
as twelve calibrated panels. The lines are now separate, and the picture is amber
rather than green - green is reserved for a transfer that has passed a corpus:

    actually calibrated panels (local ladder)
    shadow transfer candidates (UNVALIDATED)
    conditionally calibratable after review
    unresolved panels
    bands with no eligible provider

### 2. The calibration hash hashed the numbers, not the mapping

`ladder_hash` covers the VALUES a ladder read, and the group was comparing
providers on it. Both of its answers were wrong in a knowable way:

    0 at 300px, 50 at 200px, 100 at 100px
    0 at 400px, 50 at 250px, 100 at 100px

are one hash and two calibrations - and one OCR miss changes the hash of a panel
whose mapping has not moved. `panel_geometry.calibration` now returns two:
`value_set_sha` over the numbers, and `calibration_sha` over the ordered
(value, pixel) PAIRS with the point count, the scale check and the axis-break
state. It also returns slope, intercept and the fit residual in PIXELS.

`scale_type` is `LINEAR_CHECKED` only when the ladder passed with three or more
points, because what `axis_reader.ladder` checks IS constant value-per-pixel - a
log axis fails it - and a refused ladder says nothing about the scale.

`Y_SCALE_GROUP_AMBIGUOUS` is retired rather than repaired. Deciding whether two
providers are one scale needs a tolerance; the band now reports
`n_eligible_providers` and `cross_provider_max_resid_px` - how far the second
provider's points sit from the first's line - and decides nothing.

### 3. The tick residual was one-way, so a missing tick was invisible

    provider P01  36 111 187 248 253 261
    target   P02  37 112 188          -> old residual: 1 px

Three of the provider's marks have no counterpart in the target at all, and a
one-way nearest-neighbour distance cannot see that. `match_ticks` pairs mutual
nearest neighbours - one to one, and needing no skip penalty, which a dynamic
program would have needed and which would have been a constant - and reports
`tick_match_count`, `target_unmatched`, `provider_unmatched`,
`target_to_provider_max`, `provider_to_target_max`, `symmetric_max` and
`matched_max`. The same pair now reads `symmetric_max 73` with three provider
ticks unmatched.

`line_residual_px` is added beside them: where the target's own values would land
on the provider's line against where the target read them. It is the only
comparison of two calibrations that needs no tolerance, and on one of these pairs
it reads 295.7 px.

### 4. A tick was ink near the spine, and a provider was any panel that read

`tick_runs` walks OUTWARD from the spine rule's own edge and stops at the first
blank column, with one stroke of slack - `RULE_MAX_W`, the constant that already
means "a rule is 1 to 4 columns" - because strict adjacency was measured and it
dropped two of P01's four real ticks to an antialiased column. Lengths are
RECORDED per mark, never capped: `tick_lengths` beside `ticks`, so a 1 px mark
and a 6 px one stop counting alike.

And `eligibility` decides whether a reader may lend its ladder at all. A ladder
proves numerals were read beside SOME column; it does not prove the column is the
panel's axis, that the box is whole, or that the axis is unbroken. Refused when
`axis_geometry` is FALLBACK_LONGEST, GEOMETRY_UNOBSERVED or GEOMETRY_UNRESOLVED,
when the box is a FRAGMENT, or when the axis is broken - and UNKNOWN, never
ELIGIBLE, when the cells were not supplied.

### What the gate does to the figure it was built on

    G1  ROW_BAND_ONE_PROVIDER            P01 lends;  P02 P03 are candidates
    G2  ROW_BAND_NO_ELIGIBLE_PROVIDER    P04 reads a ladder and may NOT lend it
    G3  ROW_BAND_NO_ELIGIBLE_PROVIDER    P07 reads a ladder and may NOT lend it
    G4  ROW_BAND_NO_PROVIDER             nobody reads: P10, P11, P12
    G5  ROW_BAND_NO_ELIGIBLE_PROVIDER    P13 reads a ladder and may NOT lend it

**Three of the four providers are ineligible, all for the same reason:
`GEOMETRY_UNOBSERVED`.** No candidate row exists for those boxes in the winning
pass - `column_siblings` and the transforms after it produce boxes AFTER the
anchor search has run, so their axis column was never checked by it. Their spine
came from the plain longest-vertical fallback.

So last round's "eight shared-calibration candidates" is really TWO, and the
figure's honest state is: one panel calibrated and lending, two candidates
against an unvalidated transfer, and twelve panels whose y scale has no
defensible route at all yet. That is a worse number than the one before it and it
is the one the evidence supports.

It also names the next repair precisely, and it is not about calibration: RUN THE
ANCHOR SEARCH ON THE FINAL BOX LIST. Three panels of five on this figure have
never had their axis column examined by the search that exists to examine it.
That changes what the pipeline returns and belongs to its own arm.

## Tick-anchored OCR: built, measured, and it recovers nothing

Publication 177's figure 2 row 4 is labelled 4, 3, 2, 1 and the strip reader
returned one of the four. Everything else about that panel is right - box,
spine, four tick marks, fourteen of fifteen inked label columns inside the box -
so the review's diagnosis was that the question is being asked wrong: one OCR
attempt over a 226 px strip, where it should be one attempt per TICK.

Built as specified. `TICKOCR=1`, shadow only, never handed the proposal list.
Per tick: a crop centred on that tick and bounded by half the SMALLEST measured
gap to its neighbours, at 4x, 6x and 8x, in greyscale and binarised, with
tesseract asked to read one line, one word, or one character. Every attempt that
produced a number is kept with its confidence, scale, rendering and psm.

Then `axis_reader.ladder` decides - the same monotone-and-constant-step test
every ladder here has to pass - over every combination of one read value per row.
**The progression may only CHOOSE among values that were read.** A row that read
nothing stays empty and is never filled from the sequence; a value off the line
is refused, not snapped onto it; and `allow_subset=False`, because a contiguous
subset would quietly drop a misread row while its tick kept the wrong number.
Two combinations that both form a ladder are refused rather than tie-broken.

### The result, on six figures and 32 panels

    both routes read          3
    tick-anchored ONLY        0
    strip reader ONLY        10
    neither                  19

**It recovers nothing.** Not P10, which is the panel it was built for.

The diagnosis is specific and it is not about OCR. Run against the raster the
WINNING PASS produced, P10's four tick rows come out at 842, 917, 993 and 1059,
and the crop centred on 1059 misses the glyph: its candidates are 4, 7 and 5, and
no combination of 4, 3, 2 and one of those forms a ladder. Run at the shipped ink
the same panel's ticks fall at 843, 917, 992 and 1068 and all four digits read -
`4:843 3:917 2:992 1:1068`, a clean ladder.

The pass's ink is the reason. Publication 177's figure 2 wins on PLAIN at ink 173
because `REINK` re-cut it when it came up short of its declared fifteen axes -
a SEGMENTATION decision - and at 173 the single digits erode and the tick runs
shift. Adding the shipped threshold to the binarisation sweep (both are
already-measured numbers; neither is new) took P10 from three rows read to four,
and it still refuses, because the tick ROW moved and the crop moved with it.

    the segmentation pass chooses the raster
    the raster chooses where the ticks are
    the tick chooses where the crop is
    the crop chooses whether the glyph reads

So the next thing to try is not a better reader. It is to detect the ticks and
read the labels on a raster chosen for READING, independent of the one the cut
chose - which is a real change with a real risk, because the tick rows are what
`Y_SCALE_GROUP` compares panels on, and two rasters would mean two signatures.

### Why it is kept

Nothing is promoted. With `TICKOCR` unset every call is a branch not taken and
the output is byte-identical (`experiments/tick-ocr-off.json`). What it buys is
the diagnosis above, which no amount of reasoning about the strip reader would
have produced, and a route that already reads four of five labels on panels the
strip reader also reads - so the failure is narrow and named rather than general.

FOUR ROUNDS OF THIS PROJECT MEASURED WORSE AND WERE WITHDRAWN. This one measures
worse and is kept as a shadow, which is a different decision and rests on the
flag: a shadow that changes nothing costs the corpus nothing, and the alternative
is deleting the instrument that produced the only precise account of why the
panel fails.

## The mutation harness moves into the repository, because it failed

`mutate.py`. The matrix is what decides which guards in this package are real,
and it had been a script in `/tmp` with no lock, no declared baseline and a
restore that only ran on the happy path. All three failed in one round:

    two copies were started over one tree; the first was still restoring when the
      second applied its mutation
    a run killed by a timeout left `SCALES = (3,)` in `tick_ocr.py`
    the next matrix took that leftover as its baseline and reported one guard
      unobserved and another observed by a scenario failing for a third reason

So: a LOCK, refused rather than waited on, because two matrices over one tree is
not a slower run but a wrong answer. A DECLARED HASH per file in the matrix
itself - the only check that can see a leftover, since a hash taken at start-up
would take the leftover AS the baseline - with `--stamp` to write it. And RESTORE
ON SIGNAL, because the way it actually died was a kill.

A per-mutation re-check of the hash was written too, and removed: the restore in
the `finally` repairs any drift a suite could cause before the next mutation reads
it, so reverting the check turned nothing red. Decoration by this package's own
rule, and it is the lock that guards the hazard.

`test_mutate.py` holds the three failures as scenarios, including a kill mid-run
that must leave the tree clean and the lock gone.

### The count that CI caught

`74e6b44` went red on the one check that exists for exactly this: README claimed
3435 core scenarios and the core profile ran 3432. `test_tick_ocr` has three
scenarios that read real glyphs, and the `core` job strips the Python backends -
so they skip there and run in `intake-full`, which is the same shape as
`test_corpus_intake`'s PDF sections and is now said out loud in the README
sentence rather than left to be rediscovered.

The local suite was green when the round was pushed, which is precisely why the
check is not a local one.

## The metamorphic corpus, and what it says about transferring a calibration

The gate on promoting `SHARED_ROW` was a masked-label corpus: take figures whose
numerals ARE repeated on every panel, hide one panel's labels, transfer from the
provider, and compare against that panel's own reading. **No masking is needed.**
The corpus already contains row bands where BOTH panels read their own ladder,
and every such ordered pair carries its own ground truth: fit the source's
(value, pixel) line, evaluate it at the target's own tick pixels, and compare
with what the target actually read there.

`TRANSFER_CHECK`, one row per ordered pair. The error is reported twice, because
neither form is comparable alone: `transfer_max_abs` in the target's own units,
and `transfer_max_rel` over the target's own value RANGE - dimensionless, so a
panel in mmHg and one in l/min/m2 go into one distribution.

### 18 figures, 77 panels, 38 ordered pairs

    transfer_max_rel   min 0.0003   q1 0.0004   med 0.019   q3 0.359   max 8.8

    within 0.001 : 12 of 38 (32%)
    within 0.01  : 16 of 38 (42%)
    within 0.05  : 28 of 38 (74%)
    within 1.0   : 34 of 38 (89%)

**"One row band" does not imply "one y scale".** Fewer than half the pairs
transfer within one per cent of the target's own range, a quarter are off by more
than ten per cent, and the worst - publication 36's figure 1, P03 from P04 - is
wrong by **8.8 times the target's entire axis**. Had `SHARED_ROW` been promoted on
the band relation, that is the number it would have written into a panel.

The `calibration_sha` split is exact on this sample:

    calibrations agree (8 pairs)   median rel 0.0003   max 0.0
    calibrations differ (30)       median rel 0.022    max 8.8

which vindicates hashing the (value, pixel) PAIRS rather than the values - and is
useless as a licence, because a pair whose calibrations agree is a pair that both
READ and needs no transfer.

### So: is there a signal a ladderless target would still have?

That is the question that decides the line, and the pair rows carry the answer.
Split each field at its median and compare the transfer error of the better half
against the worse:

    field                better half   worse half
    provider_unmatched      0.0004        0.359     <- source ticks the target has none of
    matched_max             0.0004        0.045
    symmetric_max           0.0004        0.028
    d_axis_top              0.0004        0.022
    d_baseline              0.022         0.008     <- no signal, and inverted
    overlap_share           0.017         0.022     <- no signal

**The tick signature predicts the transfer error; the row overlap does not.**
`provider_unmatched` - how many of the source's tick marks have no counterpart in
the target - separates the two halves by a factor of 900, and it is pure geometry:
available exactly when the target reads nothing, which is the case a transfer is
for. `overlap_share`, which is what `bands()` groups on, separates nothing.

That is the finding, and it is also the reason nothing is promoted here. Thirty
-eight pairs is not a distribution to cut a tolerance from, and the field that
would carry it was not the one the grouping is built on. The next round's work is
named by it: group on the tick signature rather than on the row overlap, measure
the same pairs again, and only then ask what threshold the distribution supports.

The seven negative fixtures the review asked for - two scales in one row, linear
against log, a one-sided axis break, a dual axis, an inset, two disagreeing
providers, a row with none - are drawn scenarios and were already in place; what
this adds is the positive corpus they were waiting on.

## Still open

- THE DUTY WINDOW IS A PIXEL CONSTANT AND A DASH PERIOD IS NOT. `fit_half=22`
  makes a 45-column window; at 3x this fixture's dash period is 27 px of ink and
  18 px of gap, also 45. The window then sits inside one dash, the scored span is
  trimmed to the columns that carry ink, the trailing gap leaves the denominator,
  and the DASHED curve measures duty 1.000 gap 0 with `gaps=()` - a perfect solid.
  The true solid curve is blinded past `_BLIND_MAX_FOR_SOLID`, declines to name
  itself, and takes DASHED by elimination: THE TWO SERIES EXCHANGE VALUES, 10.96
  mmHg apart, which is why v9.14 shipped no fix. Four constants are in the same
  class - `fit_half=22`, `_vertical_strokes(min_run=11)` (a 12 px STROKE at 4x is
  removed as an error-bar stem), `_column_runs(max_thickness=7)`, and the rule
  coverage the mismatch above measures. Scaled by the TRUE factor the fixture reads
  16 of 16 cells at 4x within 0.26 mmHg, and 13 of 16 at 8x where today's reader
  answers 27.95 mmHg wrong. Scaled by a factor MEASURED off the raster it does not
  work: an estimator that strips the rules and takes the median ink run reads 1.67
  on 397 Figure 1, whose truth is 1.00, because two curves running close together
  merge into 9-10 px runs - and at 1.67 the release gate drops from 18 cells to 13,
  the worst error goes 1.65 -> 3.41 mmHg, and it emits numbers at 4:30 and 6:00
  where the curves are one run of ink and refusal is the correct answer. The route
  that stays honest is a DECLARED rendering scale (per rendering, not per
  publication), so 397 stays at exactly 1.00 and nothing about it changes. Not a
  guess: measured, and written down here rather than shipped
- THE MISMATCH ITSELF IS STILL THERE. v9.15 refuses the cell that lands on an
  unremovable rule; it does not make the rule removable. A panel whose data covers
  the middle 80% of its box emits 7 of 16 cells - the nine it loses are lost to
  gridline candidates spoiling uniqueness, not to a wrong number. Measuring
  coverage over the columns the mask actually contains recovers them and is the
  obvious repair, and it is blocked on the item above: it was tried, and at 3x it
  turned 0 cells into 2 cells one of which was 10.96 mmHg wrong
- 323's SD/SEM wording IS resolved, and only 397's is not. The Statistics section
  of 10.3389/fphys.2020.00455 reads "The values are given as mean and SEM, besides
  anthropometric data and time intervals which are given as mean and SD", and the
  hemodynamic values of its Figures 1 and 2 are the former - which agrees with the
  caption `build_id323` has always cited. 397's own methods are silent, so its
  source string still contains `NOT STATED` and its units are still held. The
  bullet further down that names both publications is therefore half stale and is
  narrowed by this one rather than rewritten, because it is a record.

- `make_plan_323.py` writes a plan and nothing runs it yet. There is no
  `pilot_323.py` and no CI wiring. The P0 that blocked them is closed in v8.7, so
  what remains is a human attestation and the panel counts of Figures 3 and 4 -
  see v8.8, which names both. What the plan
  layer accepts 323 - 12 panels, 12 units, `BAR_COLOR`, `SEM` declared from the
  methods text - so the first real figure to reach a review queue is one fix away
  rather than one design away. Its document inventory is `PENDING` on purpose:
  the article's four figures were read off the publisher's figure list, not
  counted by a person opening it, and two of the four are outside this plan.

- `--second` is a qualification check and not a finalization contract. To make
  it one the finalizer would have to take the second file and stamp
  `Second_Inference_Review_File_SHA256`, the second reviewer, the compared count
  and the disagreement count — at which point an independent reading becomes part
  of what an accepted value rests on. That is a decision about what this package
  requires, not a missing flag
- letting ONE person hold both the resolver and the approver role would need a
  comparison this package does not have: `--second-value-review`,
  `--second-identity-resolution`, or a whole independent decision bundle diffed
  against the first. `--second` is the R3 per-cell channel and nothing else, and
  v7.95 makes it say so rather than extending it — the shape of an independent
  panel-level check is a decision, not a flag. v7.96 adds the other half:
  `--distinct-reviewers` can now REFUSE the same person in both roles, which is
  not the same as being able to compare two people who each did the whole thing
- and the separation policy is a run-time declaration recorded in the finalize
  stamp, not a hashed input. It is therefore not part of `Review_Subject_SHA256`:
  two finalizations of one approved run under two different policies produce two
  stamps and the same subject hash. Binding the policy into the subject would
  mean an approval is only valid under the policy it was given, which is
  probably right and is a schema change
- 397 Figure 5 is two named individuals beat by beat — no summary statistic
  exists to read, and it stays MANUAL. Since v9.2 it is at least declared as what
  it is: `SUBJECT=Y01|Y07` against its own grid, rather than two ARM levels of
  the fluid grid that shared no cell with it
- the source-document digest has no producer inside the package: `corpus_intake`
  computes `Source_File_SHA256` for every PDF it walks and nothing turns a ledger
  row into a `source_document_manifest` row. Until it does, every document digest
  is typed by whoever writes the plan — the one hash in this package that is not
  read off the bytes by the code that needs it
- 397 Figure 4, 386 Figures 3–4
- ID 323 FIG2 DAP DI19 (1 cell) and 4 unpaired cells need a human reading
- ID 323 and 397 both need their SD/SEM wording resolved from the methods text
- 397 Figure 1 at 4:30, 5:00 and 6:00: the merged run is thicker than one
  stroke and its edges are the two curves, unread
- 397 figure 1's three `NO_BOUNDED_CAP` marks miss the cap-width rule by ONE
  PIXEL (9 against 10). The rule is `max(4, half_window)` and half_window is the
  reader's x window; whether that coupling is right is a question about the
  reader, and widening the constant to admit three cells is not the way to answer
  it
- `RESERVED_METHODS` is five methods deep: `RESTORED_MASKED_CAP`,
  `INTERPOLATED_DISPERSION`, `FITTED_DISPERSION`, `DIRECT_BOUND_PAIR` and
  `SOURCE_TRANSCRIBED` are priced and not producible. The first needs the reader
  to keep its cap masks apart instead of one `blind` union, and a real figure
  where a cap is partly covered by exactly one of them
- the R3 context crop draws the two supports and the placed value, and NOT the
  occlusion mask: the mask lives in the reader's memory at read time and nothing
  downstream has it, so the cause is named in the caption rather than shaded
- no R3 or R2 cell in the shipped corpus has reached a review queue yet.
  `PILOT.md` is the procedure, everything a program may do is built, and the
  first subject is chosen - publication 127, whose methods settle the dispersion
  definition 397's does not. But 127 has no R3 cell, so the per-cell
  CONFIRMED/REJECTED channel stays exercised end to end by fixtures rather than
  by a person until the second pilot. A production pilot may not manufacture the
  rejection that would exercise it; that belongs to a blinded exercise against a
  cell an independent reading has already found wrong
- `HUMAN_RESOLUTION` has a review channel - `BAR_MONO_GEOMETRY_RESOLVED` asks
  for `Identity_Checked`, and v7.68 requires the row to cite the resolution it
  rests on. Whether the approver and the resolver may be the same person is
  still not decided in the package - v7.94 only rules that the first pilot is
  not the place it gets decided by default, and uses two people - and a
  resolution still has no cell-level confirmation of its own the way a
  reconstructed value does
- `BAR_MONO` and `SCATTER` re-derive nothing from their marks: they are checked
  through `mono_bar_geometry.csv` and the point cloud, which bind the identity
  route and the association but not the arithmetic - a bar's `Mean` is not
  re-computed from its own top row the way `BAR_COLOR`'s now is
- NO PRODUCIBLE DISPERSION METHOD IS BOTH R3 AND ABLE TO REACH THE FINALIZER.
  `grid_engine` refuses any cell whose whisker the reader could not connect, so
  an `UNSTEMMED_CAP` value never survives machine QC; the two R3 methods that
  would are reserved. Either the gate should let an unstemmed cap through AS R3 -
  a cell-level question a person can answer from the picture - or the tier is
  decoration on that axis. Found in v7.90 by a fixture that could not happen
- the hand-reconciled worked examples (`id323_figure_values.csv`) carry no
  methods either: they come from two raster readings reconciled to a midpoint,
  which is a `MANUAL_DIGITIZED` value with no reader behind it and no channel
  yet for saying so
