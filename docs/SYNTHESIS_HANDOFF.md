# Link extraction to methods and outcome-specific analysis inputs

Use after [ANALYSIS_RECONCILIATION.md](ANALYSIS_RECONCILIATION.md) when the request
extends to existing protocol/screening/risk-of-bias records or final-input
preparation. Coordinate with an available meta-analysis skill for the broader
review; do not require an unavailable named skill or run a DTA workflow on
continuous physiological outcomes. Prepare the authorized linkage and tables
even when a later synthesis gate remains open. Do not fit a model, register a
protocol or change a final pool lock unless that action is in scope.

## Find existing evidence before restarting work

Inventory the connected project, handoffs, workbooks and versioned exports.
Read relevant sheets as well as filenames: an old-looking workbook can contain
the only preserved methods, exclusions, duplicate map or reviewer fields. Compare
IDs, content and hashes to establish lineage. Reopen the current pointer and its
referenced artifacts; do not choose authority from version number or mtime alone.
Keep project-specific paths in the handoff, not in this public procedure.

Separate protocol draft, registration record, actual approved answer, source
fact, AI assessment and final human consensus. A retrospective draft is not
prospective registration or evidence of completed registration. Record unknown
registration status without inventing an ID/date. Reconcile later actual policies
with earlier proposed methods, retaining the scope of each approval. Discovering
a proposed model does not authorize fitting it.

Identify adjacent projects by title/DOI/PMID, identifier namespace and subject
matter. A file called `screening_decisions.csv` is not automatically this review's
screening source. Keep unrelated records out of the analysis and publication set.

## Reconcile inclusion at the right grain

Build an enumerable ID crosswalk among the search bibliography, retrieval targets,
screened reports, workbook analysis rows, exclusions, duplicate aliases, recorded
eligible set and effect-contributing publications. Keep a stable publication ID
separate from workbook row/arm IDs and bibliographic-record IDs.

- Use DOI/PMID/full-title evidence and recorded duplicate mappings. Preserve all
  matching bibliographic records; do not choose the first duplicate hit. A title
  comparison may remove a documented internal annotation without editing the raw
  title. Do not assign publication IDs from row positions.
- When identifiers conflict, retain the conflicting values and match basis.
  Concordant title/PMID evidence can support an explicit link with a DOI conflict;
  it does not make the raw DOI correct. No exact hit and several consistent hits
  are different states. Do not turn either into silent loss or new publications.
- Explain each change from an older included set with added/removed IDs and the
  recorded reason/source. Apply a previously approved eligibility category only
  within its conditions. A recorded duplicate alias can explain an apparent gap;
  preserve its original record and canonical target instead of silently deleting it.
- Compare ID sets as well as counts. Recompute a recorded hash using its actual
  normalization, numeric/lexical sort, serialization and separator. Different hash
  encodings are not themselves an eligibility change. If the recipe cannot be
  established, say that the hash claim is unverified.
- A retrieval target is not a retrieved report or a completed fulltext assessment.
  A preserved bibliography does not reconstruct missing database names, Boolean
  queries, execution dates, per-database counts or individual screening decisions.
  Keep these reporting limitations explicit; never fabricate a retrospective log.
- A recorded eligible study without a prepared numerical effect remains on the
  study register. Missing effects, non-target panels and excluded publications
  are different dispositions. A subset with effects is not the whole review pool.

Report evaluator numbers, independence and automation as actually recorded.
PRISMA 2020 reporting items 8, 9 and 11 request those process details; they do not
universally require a kappa statistic. A project's planned human review is a
separate requirement and is not satisfied by machine agreement. Consult the
[official checklist](https://www.prisma-statement.org/prisma-2020-checklist) when
revising reporting language; do not copy an older project's assertion as a rule.

## Link risk of bias without creating consensus

Find the actual assessment grain and version: study, analysis row, outcome domain,
or specific result/timepoint. Retain tool assignment, design triage, both raters,
source locators, corrections and any remaining recalculation requirement. Tool
assignments and provisional overall grades do not become validated because a join
succeeds. Two AI passes remain AI passes, even when they agree.

Use exact stable keys where possible. Distinguish an exact analysis-row/domain
parent link, same-publication/domain candidates, a domain mismatch and a
publication-only link. Do not copy a broad or sibling judgment onto a new outcome,
visit, measurement method or outcome-specific denominator. A parent's completed
rating is not automatically a completed result-level rating.

Keep human reviewer names, dates and consensus blank unless actually provided.
Record delegated checks and any authorized final-grade decision with their actual
mechanism, scope and provenance; never label AI consensus human. When
existing policy requires human ratings, prepare the evidence-linked worklist and
leave that gate open rather than supplying signatures or dropping the studies.

Corrections to a domain can require recomputation of the overall grade. Evidence
of presyncope, a full-protocol completion statement or an instrument name alone
does not establish analyzed-outcome missingness or low measurement bias. Keep
source analyzed/enrolled denominators and the measurement method distinct from
within-dataset maxima, broad text hits and domain labels.

## Produce a staged input bank, not a silent final pool

At minimum, retain the following inspectable relationships. Column names may
follow the project's schema; do not invent aliases that erase meaning.

| Record | Keep |
|---|---|
| Method/evidence register | document/hash/locator, proposal versus actual approval, scope, unresolved reporting evidence |
| Publication register | stable ID, bibliographic links, recorded disposition/reason, aliases, change history, effect coverage |
| Effect-to-RoB crosswalk | exact/candidate/mismatch scope, assessment IDs, actual provenance, final-consensus status |
| Representation bank | source contribution ID, alternative metrics, original and prepared numbers/units, source/QC constraints |
| Outcome input table | construct/site/response, metric/scale, conditions/visits/arms, denominator basis, dependence, source representative role |
| Outcome inventory | member IDs, counts at their named grains, conditions and open gates; no automatic pool declaration |

Retain all effect representations. If an existing source-priority rule selects a
verified source representative, keep alternative standardized/native metrics in
an exclusion-linked bank and enforce maximum one contribution per source contrast
within each analysis/scenario. Preparing that source representative is not final
metric selection. Baseline, r/scenario and alternate-visit rows are not extra
participants. Do not merge blank level IDs or infer actual paired N from equal
reported group counts.

Use original versus already-authorized canonical numeric columns consistently:
each value, SE and variance must retain the corresponding unit and scale. Keep
MD, standardized effects, log effects, reported change statistics and other
constructs separate. Preserve existing signs and direction status; a universal
clinical-worsening multiplier is a separate methodological choice. Do not apply
new numerical conversions just to fill the table.

Preserve registry cohort links and source-backed campaign relationships as
different evidence. Repeated outcomes/visits, crossed publication/cohort structure,
shared baselines, family pairing and uncertain cross-publication overlap require
explicit dependence handling. A campaign block or registry component is not an
exact participant set or a proven independent-study count. Never sum N or reuse
pre/post correlation as between-effect covariance on that basis.

An outcome family or an exact raw-label group is for navigation until construct,
unit, state, load, window and population compatibility are established. Unknown
conditions are not compatible by default. Do not claim fresh source review for
the legacy remainder merely because it was included in a complete workbook or
internal arithmetic check. The preparation table can be complete while individual
source, RoB, metric, dependence and final-lock gates remain open.

## Verify and report the boundary actually crossed

Compare original numeric fields and prior approvals before/after linkage. Exercise
the duplicate-contribution guard with alternatives together and with the permitted
source representative set. Validate denominator provenance, raw versus canonical
units, empty-ID behavior, unresolved condition/RoB links and set transitions.

For workbook delivery, inspect the actual exported data and cached formulas;
test promised recalculation with a temporary input change and restore it. Render
representative views. Record library checks separately from native-app behavior.
For HTML, retain the review-subject/answer rules in the other references and
distinguish static/pure-JS checks from actual browser interaction. Do not report
unexecuted UI or native-app tests as passed.

Keep a machine-readable manifest/current pointer, explicit scopes and remaining
gates. Rehearse append-only outputs, read back the deployed bytes, then update the
pointer last and verify a clean rerun. A workbook export, high version number or
technical PASS does not authorize a new final pool lock. Preserve source files,
historical locks and the user's actual decisions.

If only source requirements or later synthesis gates remain, provide a read-only
completion report and linked worklists. Create a new questionnaire only for
genuinely new decisions needed for the authorized task. Do not re-ask approved
categories, ask users to guess missing source facts, or call all remaining panels
unreadable. Publish only generalized procedures and synthetic examples when a
skill update is authorized; private chats, sources, answers and study data stay
outside the public tree.
