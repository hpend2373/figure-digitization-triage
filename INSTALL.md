# figure-digitization-triage — v7.12 (full package)

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
  INSTALL.md, SKILL_ADDENDUM.md and the code. It records that a person typed
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

Then append `SKILL_ADDENDUM.md` and `MIGRATION.md` to `SKILL.md`.

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
| `test_kernel.py` | 232 |
| `test_grid_engine.py` | 132 |
| `test_run_batch.py` | 204 |
| `test_mark_readers.py` | 60 |
| `test_bar_reader.py` | 42 |
| `test_mono_bar.py` | 26 |
| `test_integration.py` | 19 |
| `test_reproducibility.py` | 2 |
| **total** | **717** |

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
