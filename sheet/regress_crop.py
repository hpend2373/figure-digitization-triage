# -*- coding: utf-8 -*-
"""Score the crop boxes against where the figures actually are.

    python3 regress_crop.py            # score, and check the harness itself

WHAT CHANGED, AND WHY. The old harness measured ink inside the box it was
scoring - target ink over the caption's own horizontal span, foreign ink over
another caption's. Both numbers came from the box, so a box that missed its
figure altogether still scored, and a box holding white space scored zero
against nothing. It passed 19 of 19 while a person, looking, found five crops
still wrong. Four rounds of algorithm work were measured by it and three of
them were rejected on its numbers - which was luck, not diagnosis.

Now the truth is outside the code, in `crop_truth.py`, read off the rendered
pages one figure at a time. Two numbers per crop, and they cannot both be
gamed by moving the box:

    covered     share of THIS figure the box holds     - too small, it clips
    intrusion   share of ANOTHER figure the box holds  - too big, it merges

And a third thing, which is the point of a harness: it checks ITSELF first.
`crop_truth.VISUAL_VERDICT` records what a person judged of each crop, and if
this file's thresholds disagree with that on any entry, it says so and exits
non-zero BEFORE reporting any score. A harness that cannot reproduce the
verdicts it was built to automate has no business grading anything.
"""
import csv
import io
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import crop_truth as T                                            # noqa: E402
import paths as PATHS                                             # noqa: E402

#: A crop holding less than this of its figure has clipped it. Chosen so the
#: two boxes a person passed clear it and the three they failed do not; the
#: calibration below is what enforces that, rather than this comment.
COVERED_FLOOR = 0.85

#: A crop holding more than this of a DIFFERENT figure has merged them.
INTRUSION_CEILING = 0.15

#: A draft row whose page size was never recorded, or whose key is claimed by
#: two different boxes. Both are measured as nothing and reported as such.
NO_PAGE_SIZE = "NO_PAGE_SIZE"
AMBIGUOUS = "AMBIGUOUS_DRAFT_BOX"
#: The page the draft recorded cannot be trusted: the method is not one of the
#: three that read a real MediaBox, the numbers are not finite and positive, or
#: two rows on the same page disagree about how big it is. Distinct from
#: NO_PAGE_SIZE, which means nobody wrote one down at all - "not recorded" and
#: "recorded wrongly" are different problems and a person fixes them
#: differently.
UNTRUSTED = "PAGE_GEOMETRY_UNTRUSTED"

#: The ways the intake's `page_geometry` can read a real page box. Anything
#: else - UNKNOWN above all - is a size nothing measured.
TRUSTED_METHODS = ("PYPDF_MEDIABOX", "PDFMINER_LAYOUT", "PDFINFO_UNIFORM")


def _finite(v):
    return v == v and v not in (float("inf"), float("-inf"))


def draft_rows(draft_dir):
    """{(document, label, page): entry} straight out of the shipped draft.

    READ, NOT RECOMPUTED, AND THAT NOW INCLUDES THE PAGE. An earlier harness
    called `figure_bbox` itself and graded a box the draft may never have held;
    v9.27 fixed that by reading `Figure_BBox`. But it still opened the PDF for
    one more thing - the page size - and worked it out from the text on the
    page, which is not the page: text stops short of the paper, so every
    fraction came out inflated. Opening the PDF at all also meant finding it,
    and it was found by BASENAME, so two documents both called `fulltext.pdf`
    resolved to whichever the staged list mentioned last - one publication's
    box scored against another's page, with a number at the end and no error.

    Now nothing here opens a PDF.

    A KEY CLAIMED TWICE IS NOT A TIE TO BREAK. The same label can appear as a
    caption and again as a cross-reference, two backends can propose different
    boxes, and one line can carry two captions. Taking the first row made the
    answer depend on file order.

    AND THE BOX IS ONLY HALF THE ROW. Two rows can carry the same
    `Figure_BBox` and different page sizes - one read from a MediaBox, one from
    `pdfinfo` on a mixed-size document - and the same points over a different
    denominator is a different fraction. Comparing the boxes alone let file
    order pick the denominator instead. The whole geometry is the signature.

    A PAGE HAS ONE SIZE. Rows that share a document and a page must agree about
    it; where they do not, every figure on that page is held rather than scored
    against a size that is right for at most one of them.
    """
    out, by_page = {}, {}
    with io.open(os.path.join(draft_dir, "figure_intake_draft.csv"),
                 encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            if not row.get("Figure_BBox"):
                continue
            key = (row["Source_Document_ID"], row["Figure_Number"],
                   row["Page"])
            geometry = (row.get("Page_Width_Pt", ""),
                        row.get("Page_Height_Pt", ""),
                        row.get("Page_Geometry_Method", ""))
            entry = {"box": row["Figure_BBox"], "w": geometry[0],
                     "h": geometry[1], "method": geometry[2],
                     "candidates": [row["Figure_BBox"]]}
            by_page.setdefault((key[0], key[2]), set()).add(geometry)
            seen = out.get(key)
            if seen is None:
                out[key] = entry
            elif (seen["box"], seen["w"], seen["h"], seen["method"]) != (
                    entry["box"],) + geometry:
                seen["status"] = AMBIGUOUS
                if entry["box"] not in seen["candidates"]:
                    seen["candidates"].append(entry["box"])
    for key, entry in out.items():
        if len(by_page.get((key[0], key[2]), ())) > 1 and "status" not in entry:
            entry["status"] = UNTRUSTED
            entry["detail"] = "두 행이 같은 쪽에 서로 다른 페이지 크기를 적었습니다"
    return out


def box_for(entry):
    """The draft's box as fractions of the page the DRAFT recorded.

    Returns (box, status). The box is None whenever it cannot be trusted, and
    the status says which kind of untrustworthy it is. Nothing is scored on a
    page whose size was guessed, and nothing is scored on a box that does not
    lie inside its own page - a box wider than the paper is not a crop, it is a
    coordinate system mismatch, and normalising it would produce a number that
    looks like an answer.
    """
    if entry.get("status") in (AMBIGUOUS, UNTRUSTED):
        return None, entry["status"]
    # NOT RECORDED comes before RECORDED BY NOTHING: a blank cell is the more
    # basic fact, and the two send a person to different places - one to the
    # walk that failed to write the size, one to the document whose size no
    # backend could read.
    try:
        w, h = float(entry["w"]), float(entry["h"])
    except (TypeError, ValueError):
        return None, NO_PAGE_SIZE
    if not (_finite(w) and _finite(h)) or w <= 0 or h <= 0:
        return None, NO_PAGE_SIZE
    if entry.get("method") not in TRUSTED_METHODS:
        return None, UNTRUSTED
    try:
        x0, y0, x1, y1 = [float(v) for v in entry["box"].split(",")]
    except ValueError:
        return None, "NO_BOX"
    if not all(_finite(v) for v in (x0, y0, x1, y1)):
        return None, "NO_BOX"
    if not (0 <= x0 < x1 <= w and 0 <= y0 < y1 <= h):
        return None, UNTRUSTED
    return (x0 / w, y0 / h, x1 / w, y1 / h), "OK"


def verdict(cov, intr):
    if cov < COVERED_FLOOR:
        return "WRONG"
    if intr > INTRUSION_CEILING:
        return "WRONG"
    return "OK"


def score(document_of, entries):
    """[(key, covered, intrusion, verdict)] for every figure with a truth box."""
    out = []
    for (pid, label, page) in sorted(T.FIGURE_REGIONS):
        entry = entries.get((document_of(pid), label, page))
        if entry is None:
            out.append(((pid, label, page), 0.0, 0.0, "NO_BOX"))
            continue
        box, status = box_for(entry)
        if box is None:
            out.append(((pid, label, page), 0.0, 0.0, status))
            continue
        truth = T.FIGURE_REGIONS[(pid, label, page)]
        others = [b for (p, l, g), b in T.FIGURE_REGIONS.items()
                  if p == pid and g == page and l != label]
        cov, intr = T.covered(box, truth), T.intrusion(box, others)
        out.append(((pid, label, page), cov, intr, verdict(cov, intr)))
    return out


#: The verdicts that mean "this cannot be scored" rather than a judgement.
REFUSALS = (UNTRUSTED, AMBIGUOUS, NO_PAGE_SIZE)


def calibrate(scored):
    """The harness must agree with the person. Returns the disagreements.

    A REFUSAL IS NOT A DISAGREEMENT, IF SOMEBODY WROTE IT DOWN. Equality was
    the whole rule, so a crop the harness stopped being able to score read the
    same as a crop it got wrong - and the two are opposite. Saying "I cannot
    put a number on this" blocks the row exactly as WRONG does; what it costs
    is coverage, not safety, and the cost is worth seeing rather than failing
    on. It is tolerated only for the keys `crop_truth.NOT_SCORABLE` names, so
    a case the harness newly loses its grip on is still a failure until a
    person looks at it and records why.

    Nothing tolerates the harness being MORE permissive than the person: a
    crop somebody judged WRONG that comes back OK is the defect this file
    exists for, and it is fatal wherever it appears.
    """
    got = {k: v for k, _c, _i, v in scored}
    bad, tolerated = [], []
    for key, want in sorted(T.VISUAL_VERDICT.items()):
        have = got.get(key)
        if have == want:
            continue
        if have is None:
            bad.append((key, want, "not scored"))
        elif have in REFUSALS and key in T.NOT_SCORABLE:
            tolerated.append((key, want, have))
        else:
            bad.append((key, want, have))
    return bad, tolerated


if __name__ == "__main__":
    # NO PDF IS OPENED HERE. The staged-path list is gone with it: it was
    # keyed by basename, and two documents named `fulltext.pdf` resolved to
    # whichever line came last, so one publication's box could be scored
    # against another publication's page and still produce a number.
    rows = json.load(io.open(PATHS.CROSSCHECK, encoding="utf-8"))
    by_pid = {r["pid"]: r for r in rows}
    entries = draft_rows(PATHS.DRAFT)

    def document_of(pid):
        r = by_pid.get(pid)
        return r["doc"] if r else ""

    scored = score(document_of, entries)
    print("%-22s %9s %9s  %s" % ("figure", "covered", "intrusion", "verdict"))
    for key, cov, intr, v in scored:
        print("%-22s %8.2f %9.2f  %s"
              % ("%s/%s/p%s" % key, cov, intr, v))

    print()
    bad, tolerated = calibrate(scored)
    for key, want, have in tolerated:
        print("점수 없음  %s/%s/p%s  사람은 %s, 하네스는 %s — %s"
              % (key[0], key[1], key[2], want, have, T.NOT_SCORABLE[key]))
    if bad:
        print("THE HARNESS DISAGREES WITH THE PERSON - fix the harness first:")
        for key, want, have in bad:
            print("  %s/%s/p%s  person said %s, harness says %s"
                  % (key[0], key[1], key[2], want, have))
        raise SystemExit(1)
    print("harness agrees with every visual verdict on record (%d)"
          % len(T.VISUAL_VERDICT))

    # A SCORE IS NOT A VERDICT. The harness earns its authority from the
    # entries a person judged; on a figure nobody has judged it is measuring,
    # not deciding, and saying otherwise would be the machine manufacturing
    # the very judgement it exists to reproduce. 99 Fig. 4 sits at 0.84
    # against a floor of 0.85 with no verdict on record - a knife edge that
    # belongs to a person, not to a constant.
    judged = [(k, v) for k, _c, _i, v in scored if k in T.VISUAL_VERDICT]
    unjudged = [(k, c, i, v) for k, c, i, v in scored
                if k not in T.VISUAL_VERDICT]
    bad_judged = [k for k, v in judged if v != "OK"]
    print("%d/%d judged figures score OK, matching the person on every one"
          % (len(judged) - len(bad_judged), len(judged)))
    for k in bad_judged:
        print("   confirmed wrong: %s/%s/p%s" % k)
    if unjudged:
        print("%d figures have no verdict on record - measured, not decided:"
              % len(unjudged))
        for k, c, i, v in unjudged:
            print("   %-20s covered %.2f  intrusion %.2f  (harness would say "
                  "%s)" % ("%s/%s/p%s" % k, c, i, v))
