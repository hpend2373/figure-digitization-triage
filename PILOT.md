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
           every question has the artifact ITS TIER requires: for an R2
               identity, the panel and geometry review artifacts its mode
               names; for an R3 reconstructed number, an inference manifest
               row AND a context picture
           the only answer problems are missing human answers

       The tiers are not asked the same thing and the check does not pretend
       they are. An R2 question has no `Inference_ID` and no cell crop - it is
       judged on the panel - so a runbook demanding a context picture for every
       question would describe a bundle the first pilot cannot produce.

       Anything else is a bundle to fix before a figure is opened. A reviewer
       who meets a refusal after signing has spent their afternoon twice.

    4  THE REVIEW ITSELF, one panel at a time. WHAT TO OPEN IS THE PANEL'S
       `Review_Mode`, not a habit - `review_queue.csv` names it, and the next
       section gives 127's in full. An `OVERLAY` panel is one picture:

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
       FINALIZED. On `--second FILE` see "Who does what": it compares the
       per-cell channel and nothing else, and on a run without one it now says
       so and exits 2 rather than reporting agreement.

    6  python3 finalize_batch.py OUT
       writes `figure_values_accepted.csv` and the stamp, or refuses and says
       why.

## What 127's reviewer opens, in order

127 Figure 4 is queued `BAR_MONO_GEOMETRY_RESOLVED`, and that mode is not an
overlay. It asks for `Marks_Checked`, `Axis_Labels_Checked`,
`Calibration_Checked` and `Identity_Checked`, and a person cannot make three of
those four claims from a panel overlay: the printed tick numbers, the ink inside
a 15 px bar, and somebody else's reading of a legend are each in a different
artifact. The mode registers six, and the order below is the order they answer
in.

    1  OUT/geometry-review/index.html
       GEOMETRY_REVIEW_INDEX, the contact sheet. It prints "N rows, M pictures,
       K panels" - and the
       three numbers agreeing is the check. A row with no picture is a row
       nobody can look at, and the sheet is the only place the count shows.

    2  OUT/geometry-review/panel__<Panel_ID>.png  and  panel__<Panel_ID>.json
       CALIBRATION_PANEL and CALIBRATION_PANEL_META, once per sub-panel: SLOW,
       NORMAL, LOWFREQ. The printed tick labels against the calibration's own
       idea of each round value. This is where a printed 30 entered as 3 shows,
       and nowhere else.
              -> Axis_Labels_Checked, Calibration_Checked

    3  OUT/geometry-review/<row>__slot<N>__<hash>.png
       GEOMETRY_ROW_CROP, one per bar. For NORMAL/SUPINE slots 0, 1 and 2 the
       question is the fill itself: OPEN, STIPPLED or SOLID, read off the ink
       inside the bar rather than off the label the run gave it.

    4  OUT/geometry-review/identity__<Panel_ID>.csv  and its Evidence_Artifact
       IDENTITY_RESOLUTION: the two 15 px bars whose fill could not be sampled,
       the series a PERSON named them, and the evidence behind that naming.
              -> Identity_Checked

    5  OUT/review/<Panel_ID>_overlay.png
       last, not first: the labels sitting on the marks, once the axis and the
       identities under them have been checked.
              -> Marks_Checked

`OUT/mono_bar_geometry.csv` is the sixth artifact, MONO_BAR_GEOMETRY. It is what
the pictures are drawn FROM and carries each row's `Geometry_Row_SHA256`; a
reviewer does not read it, and does not need to, because every row in it is
bound into `Review_Subject_SHA256` and the finalizer re-hashes the lot.

## Who does what

Two roles, and for the first pilot two PEOPLE:

    RESOLVER   recorded the OPEN/SOLID identity of the two 15 px bars in
               `identity_resolution.csv`, with the evidence file behind it
    APPROVER   confirms the overlay, the axis labels, the calibration and that
               identity resolution, and signs the panel

Whether one person may be both is not decided in this package, and the first
pilot is not the place it gets decided by default. **If a second person is not
available, 127 is run as a dry run and nothing is finalized.**

There is no `--second` fallback, and there was: v7.94 offered it, and it does
not work here. `--second` reads two `inference_review.csv` files, so the only
thing it can compare is the per-cell CONFIRMED/REJECTED channel - not the panel
decision, not the four confirmations this mode asks for, not the identity the
resolver wrote down. 127 has no R3 cell, so those two files are two empty
templates: they agree, the flag prints nothing, and one person doing both roles
reads as an independent check having happened. The tool now says how many cells
it compared and exits 2 when that is none.

Letting one person hold both roles would need a comparison this package does not
have - `--second-value-review`, `--second-identity-resolution`, or a whole
independent decision bundle diffed against the first. Until then the answer is
two people.

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
