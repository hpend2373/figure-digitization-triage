# Identity, geometry and review-state checks

Read this when verifying factor proposals, replacing review pages or repairing
frames/series. Use [MARKER_REVIEW.md](MARKER_REVIEW.md) for source-coordinate and
overlapping-marker work. These are source and review-state procedures, not a
grant to change accepted values or fill a person's signature.

## Declare what was actually inspected

Separate mechanical validation, OCR/reader output, AI visual inspection and human
confirmation. Count actually viewed panels, including their resolution and source
context. Use `NOT_REVIEWED` when not viewed and an uncertainty state when the source
was viewed but cannot settle the question. A contact sheet can locate a problem;
it does not support a claim of full-resolution inspection. Inspect the original
page/figure, full legend and native-resolution crop where needed.

For a blinded comparison, save the independent observation before exposing the
proposal. Preserve it when later source review corrects an error. Report both
original observations and the adjudication, not a rewritten history of agreement.
If the project requires a particular independent-check mechanism, use it or mark
the requirement unmet. Separate sessions of one model family are not independent
human reviewers; a subagent run is not a separate CLI execution unless it was one.

## Compare meaning before counting agreement

Check x/series roles, omitted dimensions, number and order of levels, actual
discriminants and study design. Spelling normalization is only a search aid.
`ARM`, within-person `CONDITION`, posthoc `GROUP` and `SUBJECT` are not interchangeable
labels. Distinguish a naming preference from a different design or factor structure;
record semantic disagreements separately from exact-name agreement. Apply a
stated alias rule consistently within its declared context.

Time labels need source interpretation. A sequence such as `B1/B2/R1` is not a
time factor because of its letters alone. Establish its meaning from the schedule
and the panel. Separate study `TIMEPOINT`, elapsed `TEST_TIME`, actual `CLOCK_TIME`
and named stages. Use the project's approved stage name (for example `TEST_STAGE`)
rather than renaming a second dimension to an already-used factor to satisfy a
schema. Preserve original labels and the adopted vocabulary rule.

For parallel-arm versus crossover claims, inspect Methods. For uncertain outcome
names, value range alone is a provisional interpretation, not an explicit caption.
A caption/axis mismatch is not proof of which printed element is wrong. A source
quote must be present at its locator; keep legibility limits and normalization used
to verify the quote. Do not substitute generic boilerplate for observed evidence.

## Reader incompleteness must not become the declared figure

A partially read legend does not outrank a complete source-supported proposal.
Reconcile declared series and observed marks; retain actual user edits. Match
detected colors to verified names rather than assigning by list order. Account
for black/gray, fill pattern, marker shape and line style when a color-only palette
is incomplete. Do not invent colors or unique markers for visually identical
traces, or silently discard the unrecognized series.

If multiple outcomes reuse the same marker, keep their identities separate.
Use real source-supported spatial units when separation preserves the marks,
error ends and required calibration ticks. Do not duplicate an identical box merely
to evade a uniqueness gate. If geometry cannot represent the distinction, use an
authorized manual/coordinate route or retain the representation limit.

## Reframe before recording dependent identity

Inspect what is inside the proposed frame, including all x locations, not just
the left half or a reduced overlay. A break in an axis can expose a different
outcome rather than a misframed continuation. Preserve baseline/anchor semantics
and the target axis when cropping or splitting. Missing source artwork in the
available PDF remains a source-acquisition requirement; excluding its duplicate
crop must not imply that no target panel exists in the publication.

Do not zip the first/last OCR tick values to the first/last detected pixel rows.
Verify each value/pixel pair against the printed axis. For a perspective bar,
state the measured face and the edge away from its baseline; a negative bar's
value-bearing edge need not be its upper edge. Never use an adjacent axis without
documented shared-axis evidence and a supported contract.

Check all relevant points before a panel-level stem judgment. Some points can
have connected stems while others have only caps. Preserve per-point exceptions;
a panel-wide switch must not erase readable error ends elsewhere. A disconnected
cap does not establish its owning mean. Apply any explicitly approved cap-only or
mean-only policy at its actual scope, without inventing error lengths.

## Keep proposals and prior answers distinct

Use separate provenance for reader output, AI proposal, user edit and accepted
answer. Auto-filled labels/positions must not say that a person entered or checked
them. A proposal refresh may fill unanswered fields under the page contract; it
must not replace an intentional user edit, resurrect a cleared proposal, or
silently rewrite an existing confirmed/held/rejected answer.

Changes to source image, frame, calibration, identity, axis interpretation or
point scope need a new bound review subject. An old affirmative answer cannot
authorize the new geometry. A warning alone is insufficient if the old answer
can still export as confirmed. Persist answer state by the actual subject/bundle,
and keep answered cards visible unless the user explicitly filters the view.
Read [MARKER_REVIEW.md](MARKER_REVIEW.md) for explicit point selection and mapping
conflicts in direct entry.

Read the submitted notes as well as decisions. Interpret deliberate blanks by the
actual page contract and user instruction: a delegated blank can retain an AI
proposal without claiming a new human point, while a missing required answer is
not implicit approval. Use the reviewer's requested language for human-facing
evidence and questions. Record an actual human decision date in its relevant
timezone, not the file mtime or the machine's incidental local date.

Validate the full path: source/proposal data, blank and existing stored states,
exported CSV, recorder schema and actual recorded result. A page can render valid
names that an older recorder rejects. When a frame changes, rehearse geometry
recording as well as identity recording in the correct dependency order. Passing
the identity recorder is not evidence that the new geometry was recorded.

Report static checks, pure-JS logic, browser/DOM interaction, visual inspection,
recorder dry runs and deployed-file readback as separate scopes. Tests not run
stay `NOT_RUN`; byte identity or a clean UI cannot prove source interpretation.
