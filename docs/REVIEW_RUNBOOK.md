# The human review: what a person does, in order

Everything about a review that a program may do is done by the pipeline. This
file is the part that is left: what a PERSON does, in what order, and what each
answer costs. A review whose procedure is improvised is a review nobody can
repeat.

**No review judgment, confirmation, rejection or attestation in this procedure
may be performed by an agent.** An agent may run the batch, generate the
templates and the review artifacts, and run the read-only preflight — those are
commands, not judgements. What it may not do is decide what the ink shows, or
sign that somebody looked.

The suite reads this file: every command below is parsed against the real
argument parsers, every `OUT/` file it names must be one the run writes, and the
exit codes it promises are the ones the tools return. Edit it like code.

## Before you start

You need a run that reached `MACHINE_QC_PASSED` (see [PROCEDURE.md](PROCEDURE.md),
steps 1–7) and a `reviewer_registry.csv` in the manifests that names you as a
`HUMAN` reviewer, with an ORCID as `Reviewer_Contact`. A run whose registry is a
`DEMO_IDENTITY` is `DEMO_ONLY`: it produces a queue and pictures, but nothing it
reads can ever be finalized.

Choose the first review for the review state machine, not for the science:

    the dispersion definition is settled     the methods or caption say mean ± SD,
                                             ± SE or a 95% CI in so many words.
                                             A first review that begins by
                                             guessing at a weight is not a test
                                             of the review
    it holds more than one review path       e.g. an R0 measured cell, an R2
                                             identity reasoned to, a cell a
                                             person resolved by hand
    its bundle is small                      three to fifteen questions, not
                                             dozens

## The order

    1  python3 fdt/run_batch.py MANIFESTS OUT
       stops at MACHINE_QC_PASSED. Nothing is poolable yet.

    2  python3 fdt/finalize_batch.py OUT --template
       writes `value_review.csv` with every identifier pre-filled, and writes
       `inference_review.csv` ONLY when the run holds R3 reconstructed cells.
       A run without R3 cells gets one file and there is nothing missing about
       that. A reviewer never types an `Inference_ID`: one transposed character
       is an answer to a question nobody asked.

    3  python3 fdt/review_preflight.py OUT --review OUT/value_review.csv
       THE PRE-REVIEW CHECK, and it is expected to exit 2 - the finalizer cannot
       say FINALIZED before a person has answered anything. What must be clean
       here is the BUNDLE:

           0 bundle problems
           every question has the artifact ITS TIER requires: for an R2
               identity, the panel and geometry review artifacts its mode
               names; for an R3 reconstructed number, an inference manifest
               row AND a context picture
           the only answer problems are missing human answers

       The tiers are not asked the same thing and the check does not pretend
       they are. An R2 question has no `Inference_ID` and no cell crop - it is
       judged on the panel.

       THIS STEP CANNOT BE REHEARSED ON A DEMONSTRATION. A `DEMO_ONLY` run is
       refused on its run mode before a single output is opened, so the BUNDLE
       and ANSWERS lines read `NOT EVALUATED` and the `WHY` line says which
       refusal stopped it. A rehearsal that reaches a real bundle diagnosis
       needs an attested run - the registry filled in for real.

       Anything else is a bundle to fix before a figure is opened. A reviewer
       who meets a refusal after signing has spent their afternoon twice.

    4  THE REVIEW ITSELF, one panel at a time. WHAT TO OPEN IS THE PANEL'S
       `Review_Mode`, not a habit - `review_queue.csv` names it, and the next
       section walks through the longest one in full. An `OVERLAY` panel is one
       picture:

       open  OUT/review/<Panel_ID>_overlay.png
             every mark this panel read, labelled with the series and cell it
             was filed under. The question is "is each label on the mark a
             reader would give it" - not "is the number right", which no overlay
             can show.

       then  OUT/inference-review/<Inference_ID>.png for each reconstructed cell
             a 3x crop: the two columns the value was interpolated between in
             blue, the placed value in red. The question is "would you have put
             it there".

       fill  value_review.csv     one row per panel: Decision, and the
                                  confirmations the mode asks for
             inference_review.csv one row per reconstructed cell: CONFIRMED or
                                  REJECTED, and nothing else

    5  python3 fdt/review_preflight.py OUT --review ... --distinct-reviewers
       THE POST-REVIEW CHECK, and this one must exit 0: no blank, no duplicate,
       no answer to a question this run did not ask, and the finalizer would say
       FINALIZED. `--distinct-reviewers` is the two-people contract asked in
       ADVANCE, and step 6 must be given the same flag or the two are answering
       different questions. On `--second FILE` see "Who does what": it compares
       the per-cell channel and nothing else, and it exits 2 unless every
       question was answered once on both sides and the two answers agree.

    6  python3 fdt/finalize_batch.py OUT --distinct-reviewers
       writes `figure_values_accepted.csv` and the stamp, or refuses and says
       why. The stamp records `Reviewer_Separation_Policy` either way -
       `NOT_DECLARED` when the flag is absent - so an accepted file can be asked
       afterwards which contract it was finalized under.

## The longest review mode: a resolved monochrome bar panel

A monochrome bar panel whose identities needed a person is queued
`BAR_MONO_GEOMETRY_RESOLVED`, and that mode is not an overlay. It asks for
`Marks_Checked`, `Axis_Labels_Checked`, `Calibration_Checked` and
`Identity_Checked`, and a person cannot make three of those four claims from a
panel overlay: the printed tick numbers, the ink inside a 15 px bar, and somebody
else's reading of a legend are each in a different artifact. The mode registers
seven.

**And the mode is not the whole list.** A panel's own VALUES add
`Inference_Checked` when any of them was reasoned to rather than measured -
`run_batch.inference_confirmations` derives it from the rows, so it composes
with every mode instead of doubling the mode table. A panel holding cells named
`FIGURE_PROTOTYPE_MATCH` asks for FIVE confirmations, not four. Count them off
the run, not off this file: `review_queue.csv` prints `Inference_Cells` per
panel and `figure_values_machine_qc.csv` names the method on every row.

    1  OUT/geometry-review/index.html
       GEOMETRY_REVIEW_INDEX, the contact sheet. It prints "N rows, M pictures,
       K panels". Rows must equal pictures - a row with no picture is a row
       nobody can look at, and the sheet is the only place that shortfall shows.
       Panels is a separate number and must equal the panels this figure has.

    2  OUT/geometry-review/panel__<Panel_ID>.png  and  panel__<Panel_ID>.json
       CALIBRATION_PANEL and CALIBRATION_PANEL_META, once per sub-panel. The
       printed tick labels against the calibration's own idea of each round
       value. This is where a printed 30 entered as 3 shows, and nowhere else.
              -> Axis_Labels_Checked, Calibration_Checked

    3  OUT/geometry-review/<row>__slot<N>__<hash>.png
       GEOMETRY_ROW_CROP, one per bar. Two different questions land on these
       pictures, and the run says which bar is which - do not go by slot number.

       a bar whose fill the reader SAMPLED
             read the ink inside it: OPEN, STIPPLED or SOLID, against the fill
             the run gave it rather than against the label

       a bar the run named FIGURE_PROTOTYPE_MATCH
             the reader could not resolve it inside its own group and matched it
             to a fill prototype pooled over the whole FIGURE. So the question is
             comparative: open this crop beside the crop of a bar that WAS
             sampled and ask whether the two inks are the same fill.
              -> Inference_Checked

    4  OUT/geometry-review/identity__<Panel_ID>.csv  and its Evidence_Artifact
       IDENTITY_RESOLUTION: the bars whose fill could not be sampled at all, the
       series a PERSON named them, and the evidence behind that naming.
       Different claim from step 3: there the reader made a match and you are
       checking it, here the reader made nothing and somebody else did.
              -> Identity_Checked

    5  OUT/review/<Panel_ID>_overlay.png
       last, not first: the labels sitting on the marks, once the axis and the
       identities under them have been checked. This is the seventh artifact,
       OVERLAY, and it is the only picture in the bundle that shows a LABEL on a
       MARK - which is what `Marks_Checked` claims.
              -> Marks_Checked

`OUT/mono_bar_geometry.csv` is the remaining artifact, MONO_BAR_GEOMETRY. It is
what the pictures are drawn FROM and carries each row's `Geometry_Row_SHA256`; a
reviewer does not read it, and does not need to, because every row in it is
bound into `Review_Subject_SHA256` and the finalizer re-hashes the lot.

## Who does what

Two roles, and when a panel carries a hand-resolved identity, two PEOPLE:

    RESOLVER   recorded the identity of the bars the reader could not sample in
               `identity_resolution.csv`, with the evidence file behind it
    APPROVER   confirms the overlay, the axis labels, the calibration and that
               identity resolution, and signs the panel

Whether one person may be both is not decided in this package. **If a second
person is not available, run it as a dry run and finalize nothing.**

**And this is a contract, not a paragraph.** `--distinct-reviewers` on both
tools compares the person in `identity_resolution.csv` against the one signing
the panel that naming lands in - by normalized ORCID, because a `Reviewer_ID`
identifies a row and one human registered twice would otherwise read as two
people. Where an ORCID is missing it refuses `REVIEWER_IDENTITY_UNPROVABLE`
rather than treating two mailboxes as two people. It applies to panels that
CARRY a hand-resolved identity: a panel nobody resolved has no resolver for its
approver to be distinct from, and is satisfied with nothing to check. It refuses
`RESOLVER_IS_APPROVER` when they are the same person: one reading of a legend
confirming itself is not a second reading of it. Run without the flag the
finalizer permits it, and the stamp then records
`Reviewer_Separation_Policy = NOT_DECLARED` rather than nothing, so what a run
was finalized under is a question the accepted file can answer.

There is no `--second` fallback. `--second` reads two `inference_review.csv`
files, so the only thing it can compare is the per-cell CONFIRMED/REJECTED
channel - not the panel decision, not the confirmations a mode asks for, not the
identity the resolver wrote down. The tool prints how many of the asked cells
were answered on BOTH sides and exits 2 unless all of them were and the two
answers agree.

`--second` also refuses to be handed the same file twice, two readings by the
same PERSON (compared by ORCID), a reader the registry does not carry as HUMAN,
or a second file that is not a complete review record: every question answered
once, each row naming this run's own panel, unit and cell, and a `Reviewed_At`
that is a real date and not in the future. Even so it is a READ-ONLY
QUALIFICATION CHECK and not part of the finalization contract: the finalizer
reads `--inference` and never the second file, so nothing about the second
reading is bound into `Review_Subject_SHA256` or recorded in the stamp.

## What the answers mean

    Marks_Checked        the labels sit on the marks a reader would give them
    Axis_Labels_Checked  the tick VALUES are what the figure prints. A printed 30
                         entered as 3 puts every bar in the panel ten times out
                         TOGETHER, and no arithmetic can see it
    Calibration_Checked  the axis is the axis the marks were measured against
    Identity_Checked     for a bar whose fill could not be sampled: the series
                         named in `identity_resolution.csv` is the one the legend
                         gives it
    Inference_Checked    the panel's reasoned cells were looked at. What it
                         means depends on the tier:

                         R2 - a series the reader reasoned to. There is no
                         per-cell file and no `Inference_ID`; this confirmation
                         IS the answer, made at the panel

                         R3 - a number the reader reconstructed. This says the
                         question was not skipped, and each cell's own
                         CONFIRMED / REJECTED is in `inference_review.csv`

    CONFIRMED   I looked at this and it is what I would have read
    REJECTED    I looked at this and it is not. The value is dropped; the panel
                keeps its other cells

There is no third answer, and a blank is not one. The finalizer refuses a run
whose answers are incomplete rather than treating silence as consent.

## What a reviewer is never told

**Nobody is told how many cells to reject, or which.** A review that requires a
rejection in advance produces one: the reviewer knows something must fail, an
ambiguous cell is pushed over, and the answer records a software path rather
than a reading. The partial-rejection path is exercised by fixtures; validate it
operationally in a BLINDED exercise, separately:

    a cell an independent manual reading has already found wrong
    the reviewer is not told which cell, or that there is one
    or a non-production validation bundle with a known-negative cell

A production review never manufactures a rejection.

## What a reviewer is not asked at all

R4 cells never reach them. A value the fit produced, or one carried sideways
from the nearest ink, is refused by the run itself and written into
`method_blocked_cells.csv` as work: the raster to re-read, and the cell to
re-read. An overlay cannot show a person the difference between a fitted y and a
read one, so asking them to approve it would be asking for a signature on
something nobody could check.
