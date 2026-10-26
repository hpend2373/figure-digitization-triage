# Source-backed analysis reconciliation

Use this after numerical review when connecting accepted figures to an existing
analysis, checking duplicate measurements, or preparing synthesis inputs. The
outcome is an evidence-backed status table and the smallest useful decision
queue. Apply this alongside the extraction gates; it does not create a person's
signature or make accepted measurements clinically eligible.

## Finish evidence work before asking

Within the user's authorized task, the AI should inspect the source and resolve
what it can. Keep three kinds of work separate:

| Work | AI action | Ask the person when |
|---|---|---|
| Source facts: exposure, group, visit, denominator, statistic, units | Inspect the original paper, full figure/caption and relevant tables/supplement. Under an existing delegation, record independently checked, agreeing HIGH findings with source hashes and locators. | A genuine decision needs the person's knowledge or choice. A missing source fact alone is not a request to guess it. |
| Application of an existing policy | Read the actual approved rule, its scope and exceptions. Check its conditions against the source, then apply the rule and report the affected set. | The rule is confined to named targets, its conditions are not met, or a new category would change the estimand/protocol. |
| New methodological or clinical choice | Prepare the alternatives, consequences and evidence. | No applicable approval/delegation exists, or the proposed change exceeds it. |

A newly found paper or panel is not by itself a new policy decision. If the
person approved a category rule, apply it to verified members of that category;
keep the exact affected identifiers in the receipt. Conversely, approval for a
named list does not silently become a category rule. Check later user
instructions and delegation before deciding to ask again. Carry out an
explicitly requested implementation within its authorized scope; do not send it
back as a new question merely because it requires code.

For example, an approved exposure-category rule can assign newly verified
members to an auxiliary analysis role. An existing paired-correlation policy can
be applied after its design and denominator conditions are established. Retain
the distinction between a correlation reported by a paper and an assumed one,
and retain the approved sensitivity values. Do not ask the person to re-select
an unchanged approved method for every new panel.

An absent denominator, conflicting group label, or unknown record window stays
`SOURCE_HOLD` with the specific follow-up evidence needed. Do not turn it into a
forced binary approval or ask the person to invent a number. Resolve disagreements
from the source where possible; otherwise preserve both findings and the limit.
Existing mean-only, neutral-label and pixel-coordinate decisions remain in force.

## Verify the comparison baseline

Find the latest relevant local snapshot and any successors to the proposed
version. Compare identifiers, source lineage, numerical fields and dependencies;
check that the files actually belong together. A larger version number, newer
mtime, a filename saying "final", or a passing numerical check does not prove
human approval. Record technical snapshot status separately from approval or
locking status. Use an unapproved snapshot only for the authorized comparison,
without creating a new final pool lock. Recheck for a newer relevant snapshot
before consuming later answers.

## Match the measurement before subtracting values

Link publications from stable identifiers such as DOI/PMID and source evidence.
Then establish outcome, unit, arm/cohort, visit, challenge/dose, record window,
axis and statistic. Publication matches are not cell matches, and cell matches
are not proof that two samples are independent.

- Keep raw names and factor labels, including non-Latin characters. An alias is
  a search aid; it must not erase a different arm, outcome or temporal meaning.
- Compare arithmetic values only for a confirmed same-cell/statistic pair.
  Preserve both numbers, signed differences, source precision and any pixel
  conversion. A count of agreeing names is not a count of agreeing judgments.
- Keep raw means, change scores, medians/quantiles, adjusted model estimates and
  challenge responses separate. A reported model CI is not an individual SD.
  A model estimate published by the study is also different from a digitizer
  fitting an unobserved value; existing blocked-reader rules still apply.
- A paper can display the same measurements in a bar plot and as data markers in
  another plot. Map the repeated cells explicitly, distinguish the extra cells
  and fitted lines, and prevent double counting without deleting the sources.
- Equal values, similar pixels or an exact expected count do not establish
  identity. A candidate without a confirmed match is not "no duplicate".
- Preserve cohort overlap, shared baselines, multiple visits and contrasts
  derived from existing raw levels. More coordinates do not mean more subjects.

Use an existing source-priority rule after confirming equivalence. If no rule
covers an actual source conflict, verify the original table/text and reconcile
what the evidence settles; surface only a selection that remains consequential.
A printed table verified against the source may support a more precise candidate
than digitization, but it does not authorize an unrelated statistic or overwrite
historic accepted values.

Keep a source-contribution identifier separate from the representation identifier.
An exact source contrast can appear as a printed endpoint pair, digitized values,
a native-unit change and a standardized effect. Retain the alternatives and
enforce at most one contribution of that contrast to a given synthesis. Choosing
the more faithful source does not select the final effect metric. A catalogue-only
alias is still a known measurement, even when absent from the current primary
effect file. Do not compare a standardized effect numerically with a native MD,
or physically rescale standardized g using the endpoint's native-unit factor.

For matched endpoint differences, compare means with means in compatible units
and uncertainty only with the same uncertainty type. The SE of a change is not
the SE of either endpoint. Record corrections by stable level/effect identifiers;
retain the historical numbers, corrected candidate, signed difference and scope
of any quarantine. An internal SE-squared/variance check does not verify the source.

## Preserve the construct and the clock

A compatible outcome needs more than a common variable name or unit. Carry the
measured construct and response form, anatomical site/indexing, actual posture,
challenge/dose, breathing frequency/spectral band, record window, exposure phase,
visit, intervention and population partition. Keep source wording and structured
interpretation separately. A model-derived index is not automatically a measured
body-size-indexed quantity; an AUC or challenge response is not a resting level.

- Separate study follow-up from elapsed test time and named test stages. Preserve
  the event defining each record window: test start, fixed-stage end, presyncope,
  fatigue, ischemia or recovery. Equal durations with different origins are not
  equal windows. A recording interval and an FFT/model-evaluation window can both
  be correct at different grains; retain both rather than labeling one an error.
- Keep preparation/stabilization duration separate from the averaging interval.
  A cohort mean time with an SD is not an individual lower/upper bound. Calendar
  days, elapsed hours and a mixed reported range should retain their actual basis.
- Within an approved follow-up category, apply the actual representative-visit
  rule only after cohort, outcome and other conditions match. Do not drop posture
  or protocol context from a compound visit label, choose by effect size, or
  force a source interval across a category boundary. A source's internal date
  conflict remains visible even when the approved nominal label is retained.
- Preserve exercise limb, phase, intensity and the reference MVC or absolute
  force. Before/after exposure, before/after training and recovery within a test
  are different axes. Similar force wording does not establish an unreported
  reference definition.
- Assigned arms, posthoc phenotypes, sex strata and outcome-completeness subsets
  are separate population axes. Do not copy whole-cohort sex composition or N to
  an outcome subset. A subset can inherit a property only when source evidence
  establishes the enclosing group's property and the subset relationship.

Unknown protocol facts do not match each other merely because both are blank.
Report known differences as separate strata and absent/contradictory facts as
source requirements. Keep these limits distinct from value-reading approval.

## Prepare inputs without granting synthesis eligibility

Report panel counts separately from scalar coordinate or row counts. Keep a
panel linkage/duplicate/difference table, a readiness table, source evidence,
constraints and actual coverage. A table for the whole inventory does not claim
that every source figure was visually reinspected.

Distinguish usable summary inputs from a validated contrast and from permission
to pool. Before applying an existing paired-variance rule, establish the same
participants, conditions, relevant visits and actual paired denominator; equal
sample sizes alone do not establish pairing. Prefer the reported change variance
where the approved method requires it. Mean-only, censored bounds, non-specific
maximum SD, quantiles, model CIs and unresolved denominators do not become raw
mean/SD inputs by applying a routine formula.

Source/statistic/unit conflicts can be quarantined in an append-only readiness
overlay. Record affected level/effect identifiers and retain the original values;
do not silently rescale them or stamp the unchecked remainder as passed. Direction
harmonization, clinical scope, dependence and source holds remain separate gates.

Use explicit AI provenance (`Observed_By`, evidence/check references, applicable
`Approval_Ref`); do not fill `Seen_By_Person`, `HUMAN_CONFIRMED`, a human review date
or an unprovided signature. Delegated factual recording and execution of an
already approved policy are not fresh value approval or blanket pooling approval.
Rehearse changes in a copy, compare actual bytes, and prove a clean rerun. Keep
real sources/answers private; public skill examples and tests use synthetic data.

Use explicit columns and deterministic ordering for new tables and set receipts.
Compare outputs from separate processes when unordered collections can affect
serialization. Record the hash recipe, including identifier normalization, sort
order and separator. A different recipe is not an ID-set change. Promote a current
state pointer only after all referenced outputs have been written and read back.
Validate the deployed bytes and clean rerun, not just the rehearsal copy.

When resuming across machines, reproduce calibration-sensitive acceptance in an
isolated environment before touching the real run. Check the actual interpreter,
numeric/image/PDF backends and pinned inputs. A floating-point or environment
drift is not permission to change accepted measurements until a gate passes.
Preserve historical runtime/run records and the user's cleanup constraints;
validate a current workflow without rerunning old accepted outputs in place.

For panel-status reports, count panels, cells, coordinates, comparisons, effect
representations, source contrasts, publications and cohort blocks separately.
Distinguish mean-only values, auxiliary outcomes, scope exclusions, user opt-outs,
existing-domain skips, source holds and genuinely unsupported measurement types.
No current prepared contrast does not mean that an approved panel is unreadable.
Finding an image file does not prove readability either. Report the actual
source-reinspection coverage; a complete inventory is not complete visual review.

When connecting extraction to the wider systematic-review workflow, continue with
[SYNTHESIS_HANDOFF.md](SYNTHESIS_HANDOFF.md). Do not turn an extraction ledger into
a new final pool lock or silently extend a figure-specific rule to legacy effects.

## Build a decision page only for what is left

Show newly necessary human choices with their scope and consequences. Do not
repeat answered policies, source checks the AI can complete, or routine
calculations under an approved method. A source hold can be shown read-only with
its evidence requirement. If no genuine choice remains, provide a completion
report instead of an empty next-version questionnaire.

New forms start with reviewer, date, choices and checks blank, keep answered
cards visible, and bind exported answers to the evidence and exact scope. Read
returned notes as well as choices before recording them. Preserve raw approvals,
policy approvals, AI fact findings and synthesis eligibility as distinct records.
