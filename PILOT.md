# The first real R2/R3 review

Everything in this package that a program may do about a human review is
finished. This file is the part that is left: what a PERSON does, in what order,
and what each answer costs. It exists because a review whose procedure is
improvised is a review nobody can repeat, and because the failure this whole
package is built to prevent — a program filling in a confirmation — is easiest
to commit when the procedure is vague enough that filling one in looks helpful.

**Nothing in this file may be done by an agent.** Not the confirmations, not the
rejections, not the signature. An agent may run the preflight, build the bundle,
and answer questions about what a cell means. It may not decide what the ink
shows.

## What a pilot needs before it starts

    a publication whose DISPERSION DEFINITION IS SETTLED
        the methods text says SD or SEM in so many words. 397 does not - its two
        cells of each fail machine QC for that reason, and a pilot that begins by
        guessing at a weight is not a pilot of this package
    at least one cell the reviewer will REJECT
        the partial-rejection path costs one value and keeps its panel. If every
        answer is CONFIRMED the path is exercised by fixtures and by nobody
    a registered reviewer
        a row in `reviewer_registry.csv` with `Reviewer_Record_Type=HUMAN`. A
        demonstration identity cannot confirm a reconstruction, and the finalizer
        says so rather than accepting it

## The order

    1  python3 run_batch.py MANIFESTS OUT
       the run stops at MACHINE_QC_PASSED. Nothing here is poolable yet.

    2  python3 review_preflight.py OUT --review OUT/value_review.csv
       reads: which cells will be asked about and WHY, whether every question
       has its manifest row and its context picture, and what the finalizer
       would say today. Exit 0 means the run would finalize; 2 means it would
       not. Fix what it reports BEFORE anybody opens a figure - a reviewer who
       meets a refusal after signing has spent their afternoon twice.

    3  python3 finalize_batch.py OUT --template
       writes the two decision files with every identifier pre-filled. A
       reviewer never types an `Inference_ID`: one transposed character is an
       answer to a question nobody asked.

    4  THE REVIEW ITSELF, one panel at a time:

       open  OUT/review/<Panel_ID>_overlay.png
             every mark this panel read, labelled with the series and cell it
             was filed under. The question this picture answers is "is each
             label on the mark a reader would give it" - not "is the number
             right", which no overlay can show.

       then  OUT/inference-review/<Inference_ID>.png for each reconstructed cell
             a 3x crop: the two columns the value was interpolated between in
             blue, the placed value in red. The question is "would you have put
             it there".

       fill  value_review.csv    one row per panel: Decision, and the
                                 confirmations the mode asks for
             inference_review.csv one row per reconstructed cell: CONFIRMED or
                                 REJECTED, and nothing else

    5  python3 review_preflight.py OUT --review ... --inference ...
       again, with the answers in place. It reports blanks, duplicates, answers
       to questions this run did not ask, and - with `--second FILE` - where two
       independent reviewers disagree, cell by cell.

    6  python3 finalize_batch.py OUT
       writes `figure_values_accepted.csv` and the stamp, or refuses and says
       why. A REJECTED cell is dropped and its panel still finalizes; the stamp
       counts it under `Values_Inference_Rejected`.

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

## Two people, or one

`--second FILE` compares two reviewers cell by cell. The identifiers are derived
from the content of the cell, so two people working from two copies of the bundle
produce comparable answers without having agreed on anything first. Where they
differ, the preflight prints the cell and both verdicts; resolving it is a
conversation, not a merge.

## What a reviewer is NOT asked

R4 cells never reach them. A value the fit produced, or one carried sideways from
the nearest ink, is refused by the run itself and written into
`method_blocked_cells.csv` as work: the raster to re-read, and the cell to
re-read. An overlay cannot show a person the difference between a fitted y and a
read one, so asking them to approve it would be asking for a signature on
something nobody could check.
