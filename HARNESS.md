# The segmentation harness

The whitespace cut (XY-cut) is one rule, and on 187 heterogeneous figures there is
no single rule that is always right. The harness looks at what the cut PRODUCED,
finds where that contradicts the figure itself, and repairs it. Every check repairs
rather than merely flags, and every repair writes why into the `harness` column of
`proposals.csv` — a harness you cannot check is not a harness.

Nothing here is a per-publication rule. Nothing here decides alone: every repair is
an additional CANDIDATE, and the tick ladder is still the gate.

## How the cut severs a panel

Every one of these is the same illness: the cut sees only the absence of ink, and
cannot tell the boundary of a panel from the whitespace INSIDE one.

| How it is severed | What happens | Check |
|---|---|---|
| short vertically | the cut lands in the blank rows between the trace and the x axis; the lowest tick labels fall outside the box | `snap_to_spine` |
| loses its own axis | inside a short box the panel's spine is CLIPPED, so a grid line becomes the longest vertical and the middle of the plot is measured as the axis | `axis_anchor` |
| cannot place a row | the gap between panel rows is no wider than the gap inside a panel | `broad_slabs` |
| a piece is torn off | the piece has no axis, fails every panel test, and is DISCARDED | `adopt_orphans` |
| swallows the caption | a paragraph is just ink, so the box grows down over it | `caption_floor_trim` |
| the plate as one panel | the figure is offered as one of its own panels | `figure_is_not_a_panel` |

## The checks

**1 `merge_split_panels`** — two pieces of one plot. The test is not "are they close"
but whether THE BASELINE RUNS UNBROKEN from one into the other. `MERGE_GAP = 28` px,
vertical overlap 60%, baselines within 4 rows, ≥85% ink across the gap.

**2 `column_siblings`** — a figure is a grid, so a column holding one panel usually
holds more. Restrict the search to that panel's x range and cut on rows only.

**3 `snap_to_spine`** — a box that stops before its own axis line does is a fragment.
ADDITIVE: growing is not always right, so both boxes are offered and the ladder picks.

**3b `collapse_same_axis`** (propose.py) — one axis line is one panel. Rows sitting on
the same spine run and overlapping are collapsed, and the survivor is chosen on what
was MEASURED: a passing ladder, then more labels, then the larger box.

**4 caption** (`caption.py`) — a figure is a caption and the panels the caption
describes. That relation is written down rather than inferred, and the cut cannot see
it. A caption is found by what a caption IS: a band of text with no rule in it, ≥60%
of the figure's width, ≥55% dense, below every drawn structure (horizontal AND
vertical rules), **and readable as a caption sentence** — 93 of 187 clips hold one.
`caption_floor_trim` cuts a box back above it; `figure_is_not_a_panel` refuses a box
covering ≥75% of the plate in both directions, and only when other boxes remain, and
records the refusal as a `FIGURE_BOX_REFUSED` row.

**5 `axis_anchor`** — a run touching the top or bottom EDGE of a box is not evidence
of an axis, it is evidence that the box has cut something. Among the runs ending
inside the box, the leftmost one in its left 60% is the y axis. Publication 397's
figure 2 was losing six of eight panels to this.

**6 `broad_slabs`** — where the row cut cannot choose, DON'T CHOOSE. The axes say
which rows hold a panel, so the break goes at the midpoint of the empty space between
two of them and the slab takes everything between. Redundancy is two-way `IoU ≥ 0.85`
— containment is the defect the slab repairs. The mode gate counts panels, not
candidates, and the count-match term requires `n_ok > 0`: **a segmentation that hits
the number while every cell refuses the ladder has not found the panels, it has found
the number.**

**7 `_same_baseline`** — a panel has one x axis. Two boxes standing on one baseline
row and overlapping in x are one panel however they were measured. Stacked panels
differ in baseline, side-by-side panels do not overlap in x, and an inset has its own
baseline — so this is not a nesting test.

**8 `adopt_orphans`** — see below.

## 8. Putting back the piece the cut tore off

    하나의 패널
      → 막대 그룹 사이·곡선 아래·캡션 위의 빈 공간을 패널 경계로 오인
      → 왼쪽 조각 + 오른쪽 조각으로 분할
      → 한쪽만 y축을 보유
      → 축 없는 조각은 패널 필터에서 탈락
      → 데이터가 사라지거나 뒤 패널의 이름·축 배정까지 밀림

Publication 345's figure 4 draws four bar groups per panel — Micro, Moon, Mars,
Earth — and the cut fell in the gap before Earth. The left piece kept the y axis and
was offered as a panel; the right piece, 38 px of bars with no axis, was discarded.
The panel was then reported COMPLETE with a quarter of its data outside the box: a
correct reading of an incomplete plot, which is the worst kind of wrong.

Censusing the discard pile (6,052 blocks over four modes) showed the
same cut on every side — 1,976 below, 1,909 left, 942 above, 295 right. The right,
the one first repaired, was the smallest.

### Six statements, not one threshold (`continuity.py`)

"Split where there is white space" has no counterexample: the band between bar groups
and the gutter between panels are the same white space. So the harness measures
CONTINUITY instead, split into six independent statements, each recorded:

| # | Statement | How it is measured |
|---|---|---|
| 1 | do the two pieces' baselines continue | the crossing gap against **the largest gap already inside this panel's own baseline** |
| 2 | do they share the same row range | overlap ≥ 0.5 of the union of the box and its axis run, and no more than 12% outside |
| 3 | does one piece lack an axis but carry data ink | `_has_y_axis` fails ∧ ink ≥ `PLOT_INK_MIN` |
| 4 | are the marks in the same axis coordinates | ≥60% of columns standing on the baseline, or ≥90% of ink inside the axis band |
| 5 | do both belong to the same caption | both above the caption floor (unread caption ⇒ unknown, not false) |
| 6 | is the merged result more consistent | more marks AND the spacing CV no worse |

**Statement 1 is the heart of it.** Measured absolutely, the bar-group gap and the
panel gutter are the same number — which is why the cut fails. Compared against the
gaps the panel already contains, they are not: in 345 Fig.4 the crossing gap is 26 px
and the largest gap inside the panel is 27 px. A break no wider than one the panel
already holds is not a boundary. **The panel calibrates its own threshold**, and the
constant disappears.

How they add up: NECESSARY 3 ∧ 2 ∧ (5 not false); EVIDENCE at least one of 1 and 4
positively saying the two are one plot — proximity alone is never enough; ARBITER 6
may veto but never adopts on its own. Unknown neither supports nor vetoes.

Adversarially: feeding a real neighbouring panel in as if it were a fragment is
refused on three independent grounds on the corpus case (1: 108 px against 27;
2: rows; 3: it has an axis) and on two in the HARDER version, drawn as a fixture in
`test_continuity.py` — a neighbour occupying the same row band as the panel, where
statement 2 no longer helps and the refusal rests on 1 and 3 alone. Both are
scenarios; the easy version was not left standing as the proof.

**Statement 4 is narrower than it reads, and the suite is how that is known.** Its
`inside` term compares ink in the axis band against ink in the piece, both over the
piece's own columns — so for any piece whose box lies within the panel's rows it is
1.0 by construction, and statement 2 has already decided. What it adds is the window
statement 2 leaves open: a box may reach 12% past the panel's rows and still pass,
and ink lying IN that overhang — a stray label block below the baseline — is drawn
against nothing in this plot. That is the case the scenario pins, and it is the only
one where deleting statement 4 changes an answer.

### The signed bar chart, where the baseline is not at the bottom

Publication 475's figure 2 is six panels of ΔTPR, ΔLVR and ΔCVRi: bars that go UP
and DOWN from a zero line drawn through the MIDDLE of the panel, while the y axis
runs on past it to the bottom of the scale. Four things were wrong there at once,
and every one of them was the same mistake — asking about "the baseline" at the
foot of the axis, where that figure has no ink at all.

**Criteria 1 and 6 were measuring an empty row.** Both took `run[1] - 1`, the
bottom of the spine. On panel E that is row 898 and every bar in it stands on row
786, so criterion 1 answered "this piece has no ink on the baseline row" — a
refusal that was really an empty measurement — and criterion 6 found zero marks and
declined. **The heart of the judgement and its arbiter were both silent on all six
panels.** `baseline_row` now picks between the axis's foot and the baseline the
reader sees, on the panel alone: a baseline runs most of the panel's width, a bar
top runs one bar's worth, so the row with more of the panel's own columns inked
wins. That keeps the reason the foot was chosen in the first place — on a short box
`spine_and_baseline` answers with a bar top, and a bar top loses this comparison.

**A constant was standing in front of the self-calibrating test.** `ADOPT_GAP` is
34 px and panel E's third bar group sits 37 px past the box, so the piece was
refused before any of the six statements were asked — by exactly the kind of fixed
distance criterion 1 exists to do without. The panel already says how wide its own
bar-group gaps are: 74 px. That is now the reach, with the old constant kept as the
FLOOR for panels whose baseline shows no gaps at all. This widens nothing; it stops
the gate from overruling the test.

**A slab never got an adoption pass.** Adoption is step 8 and the slab is built at
step 6, so every box the row cut could not place was offered the discarded pieces
exactly zero times — and panel E's box is a slab. It did not exist when the orphans
were handed out. The second pass is offered the SLABS ONLY, so nothing that already
had its turn gets another.

**And `cut_through_axis` was wrong in both directions on the same figure.** It
missed panel E's severance, because it probes three pixels and the sliced-off group
is 37 px away across the gap the cut mistook for a boundary; the reach is now the
panel's own widest baseline gap. And it called panels A, C and F fragments because
that figure prints its zero line 51 px PAST the plotting area into the gutter with
no bar anywhere in the overrun — three correct panels demoted out of
`AUTO_DIGITIZE` for it. **A rule leaving the box is not data leaving the box:** what
makes a box a fragment is MARKS outside it. Where the box's left edge IS its axis,
the question is not asked on that side at all — everything there is the label strip
and the axis title.

Measured on that figure: fragment flags 3 → 0, panel E's box 103–299 → 103–402, six
ladders before and six after. On an eight-figure sample: 25 flags removed, 5 added
(all five on 475 figure 1, which really is severed), no panel gained or lost, no
status changed, 47 ladders before and after.

**Still open there.** Panel E is adopted on criterion 4, not criterion 1: measured
at the right row the crossing gap is 75 px against a widest internal gap of 74 — a
one-pixel miss, so the strongest statement abstains and the weakest carries it. And
475 figure 1 is cut HORIZONTALLY at the zero line into an above-zero and a
below-zero piece, eleven boxes for six panels; adoption looks left and right only,
so nothing can put those back. The measurement that closed off up-and-down adoption
predates `continuity.py` — it was about pulling in TITLES — and criterion 3 now
separates data ink from a title, so it is worth re-running.

### Two more things the rule needs

**Ambiguity, not direction.** A block between two stacked panels could be the lower
edge of one or the title of the other, and ink cannot say which — so a block touching
more than one panel within a gutter's width is left alone. This is also why the check
cannot quietly merge two panels.

**An orphan is defined by what it is.** Taking `leaves − keep − extra` is wrong in
GRID mode, where `keep` comes from the rules rather than the leaves: a real
neighbouring panel then appeared in the orphan list and was adopted whole.

**Left and right only.** All four sides were tried on the corpus. Above and below cost
ten ladders to gain nine x readings — what sits there is the panel title and the axis
title, pulling them in moves the top edge the y label strip is measured from, and
there is no way to test them. Left and right hold the plot's own data and numerals and
CAN be tested. Evidence, not symmetry.

## 9. The threshold the figure states

`INK = 140` is one number for 187 figures printed by 187 different presses, and where
it is wrong it is not wrong by a little.

Publication 475's figure 1 draws the y axes of its left column at a grey around 155.
Column x=179 of panel A carries **238 rows of continuous axis, of which 140 admits
two.** Three of its six panels therefore have no axis at all, the plate comes back as
eleven boxes, and — because the mode score rewarded ladders without bound — the
eleven-box reading WON, each fragment reading a ladder off the shared label column.
Publication 70's figure 1 is the same illness and comes back with nothing.

**Otsu is not a replacement for 140, and the corpus is why.** Re-running all 187 at
the figure's own threshold moves the candidate count on 76 of them and drops the
figures whose count matches the axes a person recorded from **39 to 35**: on a figure
printed in solid black, 140 is the better answer and Otsu drifts up into the
anti-aliasing. What the corpus says is one-sided instead — on the 11 figures that come
back SHORT, Otsu never gives fewer candidates, gives more on 5, reaches the recorded
count on 3, and only ONE already-fine figure would break.

So it is a SECOND QUESTION, asked only of a figure that came up short, through the
same four modes and the same score, with the ladder still deciding. A figure decided
that way says so in its `harness` column as `RE_INKED`.

**And the score had to change with it**, because a re-inked reading of five panels
lost to a shredded reading of eleven. `n_ok` is unbounded upward, so more boxes meant
more ladders meant a better score. **You cannot read more axes than the figure has:**
distance from the human-authored count now comes first, and ladders break ties inside
it. This is the count-match rule from the other side — the existing one refuses a
segmentation that hits the number while every cell refuses the ladder.

Measured on a 20-figure sample, half of them the short ones and half already working:

| | before | after |
|---|---|---|
| figures closer to the recorded count | — | **7** |
| figures further from it | — | **0** |
| ladders read | 75 | 82 |
| figures matching the recorded count exactly | 8 | 9 |
| 475 Fig.1 panels / ladders / fragment flags | 11 / 11 / 8 | 7 / 5 / 1 |

Three figures that produced **nothing at all** — 345 Figure 3, 345 Figure 6 and 528
Figure 1 — now produce panels. Every figure that was already working is unchanged row
for row. Still at zero: 70 Figure 1 and 533 Figure 2, where the figure's own threshold
does not rescue the axis either.

    REINK=0   the second threshold is never asked
    NEAR=0    distance from the recorded count is ignored

Both are driver switches, so `test_continuity.py` cannot observe them — it pins
`figure_ink` and `mode_score` directly, and the corpus revert runs observe the rest.

## 10. What "in this plot's coordinates" is measured on

Criterion 4 was reading three wrong things at once, and publication 475's figure 1
shows all three. Its bars hang DOWN from a zero line drawn through the middle of each
panel, and the columns they stand in also carry the column title above and the
plate's x labels below.

**The row.** Round 9 moved criteria 1 and 6 to the row the marks stand on and left
this one at the foot of the axis. On that plate the bars stand on row 835 and the
foot is at 967.

**One end only.** "Standing on the baseline" was written as *the column's last inked
row is the baseline row*. That is true of a bar that goes UP and false of every bar
here, whose last ink is its far end. A mark stands on the baseline when EITHER end is
at it.

**The whole column.** `dark[:, ox0:ox1]` asked where the ink in these columns begins
and ends anywhere on the plate — which is the title above and the tick labels below.
The piece's own rows are the question; `inside` had always restricted itself that way
and the feet term had not.

Together these answered **0.01** for a piece every column of which stands on the
panel's zero line. Corrected, they answer **1.00**, and the piece is adopted.

Measured on the same 20-figure sample: ladders **82 → 84**, and one figure changes —
publication 397's figure 1 goes from 7 panels reading 4 ladders to 6 reading 6, both
short of its 8. Everything else is identical row for row.

### Two repairs measured and NOT kept

**Reaching as far as the panel is wide.** The self-calibrating reach asks the panel
for the widest gap already in its baseline row, and where the figure DRAWS a zero line
that row has no gaps at all — so it degenerates to the old constant, which is why 475
figure 1's pieces are still not offered to the six statements. Bounding the reach by
the panel's own width offers them, and on the sample it bought one figure — 475 figure
1 at six boxes for six axes — **by cancelling two errors: panel A returned twice and
panel C not at all.** It cost publication 397's figure 1 a panel. A count that matches
because two mistakes agree is the exact thing the count-match rule exists to refuse,
so the gate stays narrow and the degenerate case stays open.

**A panel does not contain another panel.** Added to `collapse_same_axis` to remove
the duplicate above; on the sample it cost publication 68's figure 2 a panel and
changed nothing else. Removed.

So 475 figure 1's panels C and E are still boxed to a third of their width, and D and
F still refuse their ladders. What is now known about that figure: the pieces ARE
pieces by all six statements, and the only thing standing between them and their
panels is a pre-filter that cannot state a distance on a plate with a drawn zero line.

## 11. Why the distance gate cannot be loosened yet

Publication 475's figure 1 still boxes panels C and E to a third of their width. The
six statements accept those pieces; the pre-filter never offers them, because it asks
the panel for the widest gap already in its baseline row and that plate DRAWS a zero
line, so the row has no gaps and the reach falls back to the constant. Four ways round
it were measured. All four failed, and all four failed in the same place.

| tried | what it did | measured |
|---|---|---|
| reach = the panel's own width | offers them | 475 fig 1 reaches 6 boxes **by cancelling two errors** — panel A twice, panel C absent; costs 397 fig 1 a panel |
| a panel does not contain another panel | removes that duplicate | costs 68 fig 2 a panel, changes nothing else |
| adjacency instead of a distance, plus a guard for label strips | offers them | 475 fig **2**, which was exactly right, is rebuilt wrong — panel A shrinks from x1=403 to 314 and loses its third group; 397 fig 1 grows one box across BOTH columns (x1 577 → 1086) |
| criterion 4's foot term widened to "crosses the baseline", then to "inked at the baseline" | would let the foot term carry the judgement | 475 fig 2's y label strip scores **0.86**, then **0.68** — as high as real bars |

**The common point of failure is criterion 4.** Its band term — *ink lying between the
axis top and the baseline* — is 1.0 by construction for any piece inside the panel's
rows, so it accepts whatever the gate lets through; on a six-figure probe **all three
adoptions were carried by the band term alone, with a foot share of 0.00.** And the
foot term cannot be widened to take the load, because a column of y numerals has ink
above and below any row you pick.

So the distance gate is load-bearing precisely because criterion 4 is not. **The
missing primitive is telling a MARK from a LABEL** — the same discrimination
`cut_through_axis` needed and got by subtracting the rule from the band. Until
criterion 4 can make it, neither the gate nor the criterion may be loosened, and
475 figure 1's panels C and E stay short.

The third row of that table is also a warning about how this harness is judged: on 475
figure 2 the panel COUNT and the ladder count were unchanged while the boxes moved to
the wrong places. Counting panels is not checking them.

## Order

```
leaves  = everything the cut produced
keep    = _is_plot ∧ holds_data
extra   = _has_y_axis ∧ holds_data
orphans = blocks with no axis of their own

allb = merge_split_panels(keep + extra)            # 1
allb = allb + column_siblings(allb)                # 2
allb = adopt_orphans(allb, orphans)                # 8
allb = caption_floor_trim(allb, CAP_FLOOR)         # 4a
allb = allb + broad_slabs(allb, CAP_FLOOR, TARGET) # 6
allb = snap_to_spine(allb)                         # 3   last additive step
allb = figure_is_not_a_panel(allb, ...)            # 4b  the only removal
...
sx   = axis_anchor(box) or spine_and_baseline(box) # 5   just before measuring
recs = collapse_same_axis(recs)                    # 3b·7 after measuring
```

Order matters. Step 3 is purely additive and step 2 is not — the column rescan refuses
a cell overlapping a box already in the list, so offering it a grown box first makes
it skip the panel it was there to find. Step 4b is last because it is the only step
that removes. And the mode gate counts what the CUT produced, not what the harness put
back: counting the adopted piece cost publication 139's figure 3 every one of its modes.

## Revert test

Every round is gated by an environment flag and re-run with it off; the off path must
reproduce the pre-repair result ROW FOR ROW.

    SNAP=0   checks 3 and 3b        (verified: 40 figures, 155 rows identical)
    CAP=0    checks 4 and 5         (verified: 12 figures, 50 rows identical)
    BROAD=0  checks 6 and 7         (verified: 42 figures, 171 rows identical)
    WIDE=0   check 8

## What is in the repository, and what is not

    axis_reader.py    the measurement core and checks 1, 2, 3, 4a, 4b, 5, 6, 8
    continuity.py     the six statements and how they add up
    x_reader.py       tick marks, tick labels and bar centres; statement 6 uses it
    caption.py        the caption band, by definition rather than by position
    propose.py        the driver: one proposal row per detected panel
    test_continuity.py

NOT here: the corpus. `propose.py` reads a worklist, a clip index and a caption
scan of a particular 187-figure set (`DIG`, `CLIPS`, `CAPS` name them, so it is
pointable at another), and the figures themselves are publisher rasters and are not
redistributable. Every number quoted in this document is from that corpus and
cannot be re-derived from a clone — which is exactly why the judgement is pinned
against drawn fixtures instead:

    python3 test_continuity.py

74 scenarios, none of which need the corpus, OCR, or a network. The geometric ones
run at two scales and must give the same verdict at both: nothing in this harness
is allowed to be a distance in pixels. The two failure directions are drawn
separately — a fragment REFUSED loses the panel's data silently, a neighbour
ADOPTED shifts the axis assignment of everything after it — because a suite that
only proves the first can be passed by adopting everything.

Reading a tick NUMERAL needs tesseract, which the locked environment does not
install; asked without it, `_ocr_numerals` raises rather than returning no
numerals, because a ladder silently built from zero numerals is the fail-open shape
this package refuses everywhere else. Panels, spines, baselines and continuity are
geometry and call none of it.
