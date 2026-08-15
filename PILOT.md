# The first production review

Everything about a human review that a program may do is finished. This file is
the part that is left: what a PERSON does, in what order, and what each answer
costs. A review whose procedure is improvised is a review nobody can repeat.

**No review judgment, confirmation, rejection or attestation in this procedure
may be performed by an agent.** An agent may run the batch, generate the
templates and the review artifacts, and run the read-only preflight — those are
commands, not judgements. What it may not do is decide what the ink shows, or
sign that somebody looked.

## The first pilot: publication 127, Verheyden 2007, Figure 4

Named exactly: **the first production R2 + human-resolution pilot.** It is not
an R3 partial-rejection pilot, and this document does not let anyone claim it
was one.

Why 127 and not the others:

    the dispersion definition is settled     the methods say mean ± SE in so
                                             many words. 397's does not, and a
                                             pilot that begins by guessing at a
                                             weight is not a pilot of this
    it holds three review paths at once      an R0 control group, an R2 identity
                                             named by a prototype formed in
                                             another group, and two bars a
                                             person resolved by hand
    its bundle is the furthest along         three panels, eighteen cells, mean
                                             and SE read on all of them, sixteen
                                             fills sampled automatically and two
                                             15 px bars that cannot be

Scope. The three sub-panels are one identity domain, so all three are measured.
The finalization target is narrower:

    SLOW       finalize - the R0 control
    NORMAL     finalize - the R2 prototype match and both human resolutions
    LOWFREQ    withheld if its known skewness QC problem stands; NOT part of the
               pilot's success condition

Mixing the QC-semantics question into the review pilot would make a failure in
either look like a failure of both. The first pilot is about the review state
machine.

**What 127 does not test, and what nobody may claim from it:**

    the per-cell CONFIRMED / REJECTED channel      no R3 cell here
    the R3 context crop                            nothing is reconstructed
    partial rejection - one cell dropped, its
        panel finalized                            same reason

`FIGURE_PROTOTYPE_MATCH` infers a series IDENTITY, which is R2 and answered at
the panel. The means and the SEs were measured off the ink.

## The order

    1  python3 run_batch.py MANIFESTS OUT
       stops at MACHINE_QC_PASSED. Nothing is poolable yet.

    2  python3 finalize_batch.py OUT --template
       writes both decision files with every identifier pre-filled. A reviewer
       never types an `Inference_ID`: one transposed character is an answer to a
       question nobody asked.

    3  python3 review_preflight.py OUT --review OUT/value_review.csv
       THE PRE-REVIEW CHECK, and it is expected to exit 2 - the finalizer cannot
       say FINALIZED before a person has answered anything. What must be clean
       here is the BUNDLE:

           0 bundle problems
           every question has its manifest row and its context picture
           the only answer problems are missing human answers

       Anything else is a bundle to fix before a figure is opened. A reviewer
       who meets a refusal after signing has spent their afternoon twice.

    4  THE REVIEW ITSELF, one panel at a time:

       open  OUT/review/<Panel_ID>_overlay.png
             every mark this panel read, labelled with the series and cell it
             was filed under. The question is "is each label on the mark a
             reader would give it" - not "is the number right", which no overlay
             can show.

       then  OUT/inference-review/<Inference_ID>.png for each reconstructed cell
             a 3x crop: the two columns the value was interpolated between in
             blue, the placed value in red. The question is "would you have put
             it there". 127 has none of these; the second pilot will.

       fill  value_review.csv     one row per panel: Decision, and the
                                  confirmations the mode asks for
             inference_review.csv one row per reconstructed cell: CONFIRMED or
                                  REJECTED, and nothing else

    5  python3 review_preflight.py OUT --review ... --inference ...
       THE POST-REVIEW CHECK, and this one must exit 0: no blank, no duplicate,
       no answer to a question this run did not ask, and the finalizer would say
       FINALIZED. With `--second FILE` it also reports where two independent
       reviewers differ, cell by cell.

    6  python3 finalize_batch.py OUT
       writes `figure_values_accepted.csv` and the stamp, or refuses and says
       why.

## Who does what

Two roles, and for the first pilot two people:

    RESOLVER   recorded the OPEN/SOLID identity of the two 15 px bars in
               `identity_resolution.csv`, with the evidence file behind it
    APPROVER   confirms the overlay, the axis labels, the calibration and that
               identity resolution, and signs the panel

Whether one person may be both is not decided in this package, and the first
pilot should not be the place it is decided by default. If a second person is
impossible, they must at least review independently and be compared with
`--second`.

## What the answers mean

    Marks_Checked        the labels sit on the marks a reader would give them
    Axis_Labels_Checked  the tick VALUES are what the figure prints. A printed 30
                         entered as 3 puts every bar in the panel ten times out
                         TOGETHER, and no arithmetic can see it
    Calibration_Checked  the axis is the axis the marks were measured against
    Identity_Checked     for a bar whose fill could not be sampled: the series
                         named in `identity_resolution.csv` is the one the legend
                         gives it
    Inference_Checked    the panel's reasoned cells were looked at. The per-cell
                         file is where each one is answered; this says the
                         question was not skipped

    CONFIRMED   I looked at this and it is what I would have read
    REJECTED    I looked at this and it is not. The value is dropped; the panel
                keeps its other cells

There is no third answer, and a blank is not one. The finalizer refuses a run
whose answers are incomplete rather than treating silence as consent.

## What a reviewer is never told

**Nobody is told how many cells to reject, or which.** A pilot that requires a
rejection in advance produces one: the reviewer knows something must fail, an
ambiguous cell is pushed over, and the answer records a software path rather
than a reading. The partial-rejection path is exercised by fixtures today, and
is validated operationally in a BLINDED exercise, separately:

    a cell an independent manual reading has already found wrong
    the reviewer is not told which cell, or that there is one
    or a non-production validation bundle with a known-negative cell

A production pilot never manufactures a rejection.

## What a reviewer is not asked at all

R4 cells never reach them. A value the fit produced, or one carried sideways
from the nearest ink, is refused by the run itself and written into
`method_blocked_cells.csv` as work: the raster to re-read, and the cell to
re-read. An overlay cannot show a person the difference between a fitted y and a
read one, so asking them to approve it would be asking for a signature on
something nobody could check.

## Choosing the second pilot: a real R3 review

127 cannot test the per-cell channel, so the next one is chosen for it. An agent
may shortlist and build the bundles; the choice and the ink are a person's.

    Mark_Type = LINE_MONO_STYLE
    the methods or the caption names SD, SEM, SE or a 95% CI
    at least one R3 cell that PASSES machine QC
    R0 or R1 cells in the same panel, so the panel is not all inference
    no panel of nothing but R4
    three to fifteen review questions in total - not dozens
    a context crop where the two supports are visible to the eye

The R3 methods worth meeting first are `LOCAL_BRACKETED_INTERPOLATION`,
`MERGED_RUN_EDGE` and `CONTINUITY_TRACK`. A publication with a handful of
reconstructed cells teaches more than one with fifty, because every question in
the first pilot is a question somebody has to answer carefully.
