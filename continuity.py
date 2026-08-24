# -*- coding: utf-8 -*-
"""Is this piece part of that panel? Six statements, each measured separately.

The defect these answer is structural, not optical:

    하나의 패널
      → 막대 그룹 사이·곡선 아래·캡션 위의 빈 공간을 패널 경계로 오인
      → 왼쪽 조각 + 오른쪽 조각으로 분할
      → 한쪽만 y축을 보유
      → 축 없는 조각은 패널 필터에서 탈락
      → 데이터가 사라지거나 뒤 패널의 이름·축 배정까지 밀림

"흰 공간이 있으면 나눈다"는 규칙에는 반례가 없다 - 막대 그룹 사이의 띠와 두 패널
사이의 거터는 같은 흰 공간이다. 그래서 흰 공간을 재는 대신 **연속성을 재고**, 그
판단을 하나의 임계값이 아니라 서로 독립인 여섯 개의 진술로 나눈다. 각 진술은
`proposals.csv`의 harness 열에 그대로 남아, 왜 붙였는지가 사람에게 보인다.

Nothing here has a per-publication rule and nothing here decides on its own: the
verdict is a stated combination of the six, and the ladder still gates what is used.
"""
import numpy as np
import axis_reader as A

PAD_SHARE = 0.12          # how far outside the panel's rows a piece may still reach
BAR_FOOT = 3              # px: a bar's foot is "on" the baseline within this
FOOT_SHARE = 0.60         # this much of a piece's columns standing on the baseline
INSIDE_SHARE = 0.90       # or this much of its ink lying inside the panel's rows
LABEL_STRIP_EVIDENCE = False   # see same_coordinates - measured, not assumed
CV_SLACK = 0.15           # merging may not make the mark spacing this much worse
MIN_MARKS = 3             # fewer marks than this and regularity is not measurable


def _row_gaps(row, x_from, x_to):
    """Widths of the blank runs on this row between x_from and x_to."""
    gaps, run = [], 0
    for x in range(max(0, x_from), max(0, x_to)):
        if row[x]:
            if run:
                gaps.append(run)
            run = 0
        else:
            run += 1
    return gaps


def _cv(vals):
    if len(vals) < 2:
        return None
    m = sum(vals) / len(vals)
    if m <= 0:
        return None
    var = sum((v - m) ** 2 for v in vals) / len(vals)
    return (var ** 0.5) / m


def baseline_row(dark, panel, sx, run):
    """The row the panel's marks stand on, which is not always the axis's bottom.

    A signed bar chart draws its zero line THROUGH the middle of the panel and the
    bars stand on that, not on the foot of the y axis. Publication 475's figure 2 is
    six of them: the spine of panel E runs to row 898 and every bar in it stands on
    row 786, so measuring the baseline at 898 asked about a row with no ink in it at
    all and answered "this piece has none either" - a refusal that was really an
    empty measurement. Criterion 1 was doing no work on that whole figure.

    The two candidates are the axis's own foot and the baseline the reader sees, and
    the panel decides between them WITHOUT looking at the piece: a baseline runs
    most of the panel's width, a bar top runs one bar's worth. So take the row with
    more of the panel's own columns inked. That also keeps the reason the foot was
    chosen in the first place - on a short box `spine_and_baseline` answers with a
    bar top, and a bar top loses this comparison.
    """
    lo, hi = int(sx), int(panel[1])
    cands = [run[1] - 1]
    try:
        import axis_reader as _A
        cands.append(int(_A.spine_and_baseline(dark, panel)[1]))
    except Exception:
        pass

    def width(by):
        if not (0 <= by < dark.shape[0]) or hi - lo < 1:
            return -1
        return int(dark[max(0, by - 1):by + 2, lo:hi].any(axis=0).sum())

    return max(cands, key=width)


def baseline_continues(dark, panel, orphan, sx, run):
    """1. 두 조각의 기준선이 이어지는가.

    NOT "is the gap small". The gap between two bar GROUPS inside one panel and the
    gutter between two panels are the same white space measured absolutely, which is
    the whole reason the cut fails here. So the crossing gap is compared against the
    gaps that already occur INSIDE this panel's own baseline: a break no wider than
    one the panel already contains is not a boundary, it is another bar gap. The
    panel calibrates its own threshold, and the constant disappears.
    """
    x0, x1, y0, y1 = panel
    ox0, ox1, _oy0, _oy1 = orphan
    by = baseline_row(dark, panel, sx, run)
    row = dark[max(0, by - 1):by + 2].any(axis=0)
    if not row[ox0:ox1].any():
        return False, "밑변 행 %d에 조각 쪽 잉크가 없다" % by
    inside = _row_gaps(row, int(sx), x1)
    internal = max(inside) if inside else 0
    if ox0 >= x1:
        left = max((x for x in range(int(sx), min(len(row), x1)) if row[x]), default=None)
        right = min((x for x in range(ox0, min(len(row), ox1)) if row[x]), default=None)
    else:
        left = max((x for x in range(ox0, min(len(row), ox1)) if row[x]), default=None)
        right = min((x for x in range(int(sx), min(len(row), x1)) if row[x]), default=None)
    if left is None or right is None:
        return False, "밑변 행에서 두 조각을 잇는 잉크를 찾지 못했다"
    cross = max(0, right - left - 1)
    ok = cross <= max(internal, 4)
    return ok, ("건너는 간격 %d px, 패널 내부의 가장 큰 간격 %d px" % (cross, internal))


def same_rows(panel, orphan, run):
    """2. 같은 행 범위를 공유하는가.

    Measured against the panel's rows widened to its own axis, not against the axis
    alone. A plot legitimately overruns its spine - error-bar caps above the top
    tick, tick labels below the baseline - so the drawn axis is too tight a frame to
    judge a piece by, and the first version of this test refused the very bar group
    it was written for. The box may also be short, which is why the reference is the
    UNION of the two rather than either one.
    """
    top = min(panel[2], run[0])
    bottom = max(panel[3], run[1])
    pad = PAD_SHARE * max(1, bottom - top)
    oy0, oy1 = orphan[2], orphan[3]
    ov = min(bottom, oy1) - max(top, oy0)
    share = ov / max(1, min(bottom - top, oy1 - oy0))
    inside = (oy0 >= top - pad) and (oy1 <= bottom + pad)
    return (share >= 0.5 and inside), ("행 겹침 %.2f, 패널 행 %d-%d, 조각 %d-%d"
                                       % (share, top, bottom, oy0, oy1))


def data_without_axis(dark, orphan):
    """3. 한 조각에 축은 없지만 데이터 잉크가 있는가.

    This is what makes it an orphan rather than a panel, and what makes it worth
    recovering rather than ignoring: it carries marks. An empty margin does not.
    """
    if A._has_y_axis(dark, orphan):
        return False, "이 조각은 자기 축을 가지고 있다 - 고아가 아니라 패널이다"
    ox0, ox1, oy0, oy1 = orphan
    sub = dark[oy0:oy1, ox0:ox1]
    share = float(sub.mean()) if sub.size else 0.0
    return share >= A.PLOT_INK_MIN, "축 없음, 잉크 %.3f" % share


def same_coordinates(dark, panel, orphan, run, sx=None, side=None):
    """4. 막대·선이 동일한 축 좌표계에 정렬되는가.

    Two ways a mark can belong to this plot's coordinates: it stands ON the baseline
    (a bar, a box, an error-bar foot), or it lies BETWEEN the axis top and the
    baseline (a line, a scatter). Ink outside that band is drawn against something
    else - another panel's axis, or nothing at all.
    """
    # THE THIRD PLACE THIS ROW WAS WRONG. Criteria 1 and 6 were moved to the row the
    # marks stand on and this one was left at the foot of the axis, where publication
    # 475's figure 1 has no ink: its bars stand on row 835 and the foot is at 967, so
    # "how many of this piece's columns stand on the baseline" answered 0.06 for a
    # piece every bar of which stands on it.
    top, bottom = run
    by = baseline_row(dark, panel, sx if sx is not None else panel[0], run)
    ox0, ox1, oy0, oy1 = orphan
    # THE PIECE'S OWN ROWS, not the whole column of the figure. Taking the full height
    # asked where the ink in these columns starts and ends ANYWHERE on the plate - in
    # publication 475's figure 1 that is the panel two rows up and the tick labels
    # below - so a bar hanging off this panel's zero line was measured against
    # somebody else's ink. `inside` below already restricts itself this way.
    sub = dark[oy0:oy1, ox0:ox1]
    feet, cols = 0, 0
    for i in range(sub.shape[1]):
        col = np.where(sub[:, i])[0] + oy0
        if not len(col):
            continue
        cols += 1
        # EITHER END. "Standing on the baseline" was written as "the column's last
        # inked row is the baseline row", which is true of a bar that goes UP and
        # false of every bar in publication 475's figure 1, where the bars hang DOWN
        # from zero and their last ink is their far end. A mark stands on the
        # baseline when one of its ends is at it.
        #
        # TWO WIDER READINGS WERE TRIED AND MEASURED WORSE, both for the same reason.
        # "The column CROSSES the baseline" makes publication 475's figure 2's y label
        # strip score 0.86 - a column of numerals has ink above and below any row you
        # pick. "The column is INKED AT the baseline" makes the same strip score 0.68,
        # over the 0.60 the term asks for. Neither can tell a numeral from a bar, so
        # neither may be loosened until something can.
        if min(abs(int(col[-1]) - by), abs(int(col[0]) - by)) <= BAR_FOOT:
            feet += 1
    if cols == 0:
        return False, "조각에 잉크가 없다"
    foot_share = feet / cols
    band = dark[max(0, top - 2):bottom + 2, ox0:ox1]
    whole = dark[oy0:oy1, ox0:ox1]
    inside = (float(band.sum()) / float(whole.sum())) if whole.sum() else 0.0
    # THE LABEL-STRIP ROUTE IS OFF BY DEFAULT, AND THE CORPUS IS WHY. Counting a
    # numeral column as "in this plot's coordinates" is true - the numerals are drawn
    # against this axis and nothing else - and it saved publication 116's figure 3,
    # which had lost its only ladder to the cut. But 83 of the 97 left-side adoptions
    # it enabled were on panels that ALREADY read their own numerals (`label_band`
    # walks left from the axis without caring where the box edge is), so those merges
    # bought nothing while making eight boxes wide enough to trip the assignment
    # layer's size guards. Criterion 4 as stated is about marks - bars and lines -
    # and that is what it is left measuring.
    labels = False
    if LABEL_STRIP_EVIDENCE and side == "left" and sx is not None:
        near = ox1 >= int(sx) - A.LABEL_BAND_MAX - 8
        rows = (min(bottom, oy1) - max(top, oy0)) / max(1, bottom - top)
        labels = near and rows >= 0.80
    # THE BAND TERM IS VACUOUS AND LOAD-BEARING AT THE SAME TIME, which is the least
    # comfortable thing measured about this module. `inside` is 1.0 by construction for
    # any piece lying inside the panel's rows, so on its own it accepts a column of y
    # numerals as readily as a bar group - publication 475's figure 2 adopts two label
    # strips on exactly that evidence, at a foot share of 0.00.
    #
    # AND REFUSING THEM MAKES THAT FIGURE WORSE. Restricting the term to the plot side
    # of the spine - there are no marks left of a spine, which is true - shrinks panels
    # C, E and F on 475 figure 2 (C loses its third bar group, x1 403 -> 297) and takes
    # 475 figure 1 from seven boxes to eight. Those adoptions add no ladder; the WIDER
    # BOX they produce is what keeps `collapse_same_axis` and the mode score landing on
    # the right geometry afterwards. The harness is getting those boxes right for the
    # wrong reason, and the repair is not here: a panel's box should contain its own
    # label strip BY CONSTRUCTION, the way `label_band` reads it, rather than by an
    # adoption this criterion then has to justify. Until it does, the term stays as it
    # is and this comment is the warning.
    ok = foot_share >= FOOT_SHARE or inside >= INSIDE_SHARE or labels
    return ok, ("밑변에 선 열 %.2f, 축 범위 안 잉크 %.2f%s"
                % (foot_share, inside, ", 축 라벨 스트립" if labels else ""))


def same_caption(panel, orphan, cap_floor):
    """5. 둘이 같은 캡션에 속하는가.

    The caption is the figure's floor, so a piece on the far side of it belongs to
    the page, not to this plot. Where no caption was read this returns None - unknown
    is not the same as false, and an unknown does not veto.
    """
    if cap_floor is None:
        return None, "이 클립에서 캡션을 읽지 못했다"
    ok = panel[3] <= cap_floor + 2 and orphan[3] <= cap_floor + 2
    return ok, "캡션 행 %d, 패널 하단 %d, 조각 하단 %d" % (cap_floor, panel[3], orphan[3])


def more_regular(dark, panel, orphan, sx, run):
    """6. 합친 뒤 축·눈금·데이터 배치가 더 일관적인가.

    The arbiter, and the only test that looks at the RESULT rather than the join. A
    plot's marks are evenly spaced; a piece that belongs to it extends that rhythm,
    and a piece that does not breaks it.

    Returns None when there are too few marks to speak of regularity, which is common
    and must not be read as a refusal.
    """
    # THE SAME ROW CRITERION 1 USES. Asking `bar_centres` to find bars standing on
    # the foot of the y axis finds none at all on a signed bar chart, and criterion 6
    # then answers "too few marks to speak of regularity" - so the ARBITER was silent
    # on every panel of publication 475's figure 2, which is six of them.
    by = baseline_row(dark, panel, sx, run)
    x0, x1, y0, y1 = panel
    ox0, ox1 = orphan[0], orphan[1]
    import x_reader as X
    merged = (min(x0, ox0), max(x1, ox1), min(y0, orphan[2]), max(y1, orphan[3]))
    try:
        before = [c[1] for c in X.bar_centres(dark, panel, sx, by)]
        after = [c[1] for c in X.bar_centres(dark, merged, sx, by)]
    except Exception:
        return None, "막대 중심을 재지 못했다"
    if len(before) < MIN_MARKS or len(after) < MIN_MARKS:
        return None, "막대·눈금이 %d→%d개뿐이라 규칙성을 잴 수 없다" % (len(before), len(after))
    if len(after) <= len(before):
        return None, "합쳐도 표시 개수가 늘지 않는다 (%d→%d)" % (len(before), len(after))
    cb = _cv([before[i + 1] - before[i] for i in range(len(before) - 1)])
    ca = _cv([after[i + 1] - after[i] for i in range(len(after) - 1)])
    if cb is None or ca is None:
        return None, "간격을 잴 수 없다"
    ok = ca <= cb + CV_SLACK
    return ok, "표시 %d→%d개, 간격 변동 %.3f→%.3f" % (len(before), len(after), cb, ca)


NAMES = ("baseline", "rows", "data_no_axis", "coords", "caption", "regular")


def verdict(dark, panel, orphan, sx, run, cap_floor, side=None):
    """(adopt?, {test: (ok, detail)}) - the six, and what they add up to.

    NECESSARY: the piece must be a piece (`data_no_axis`), must live in the panel's
    rows (`rows`), and must not be on the far side of the caption (`caption`).
    EVIDENCE: at least one of `baseline` and `coords` must positively say the two are
    one plot - proximity alone is never enough.
    ARBITER: `regular` may veto. It never adopts on its own.

    An unknown (None) neither supports nor vetoes.
    """
    t = {}
    t["data_no_axis"] = data_without_axis(dark, orphan)
    t["rows"] = same_rows(panel, orphan, run)
    t["caption"] = same_caption(panel, orphan, cap_floor)
    t["baseline"] = baseline_continues(dark, panel, orphan, sx, run)
    t["coords"] = same_coordinates(dark, panel, orphan, run, sx, side)
    t["regular"] = more_regular(dark, panel, orphan, sx, run)
    need = t["data_no_axis"][0] and t["rows"][0] and (t["caption"][0] is not False)
    evidence = bool(t["baseline"][0]) or bool(t["coords"][0])
    veto = t["regular"][0] is False
    return (need and evidence and not veto), t


def describe(t):
    def mark(v):
        return "O" if v is True else ("X" if v is False else "-")
    return "; ".join("%s %s(%s)" % (mark(t[n][0]), n, t[n][1]) for n in NAMES)
