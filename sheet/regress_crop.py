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
sys.path.insert(0, PATHS.REPO)
import corpus_intake as CI                                        # noqa: E402

#: A crop holding less than this of its figure has clipped it. Chosen so the
#: two boxes a person passed clear it and the three they failed do not; the
#: calibration below is what enforces that, rather than this comment.
COVERED_FLOOR = 0.85

#: A crop holding more than this of a DIFFERENT figure has merged them.
INTRUSION_CEILING = 0.15

_blocks = {}


def blocks_for(path):
    if path not in _blocks:
        _blocks[path] = CI.text_blocks(path)
    return _blocks[path]


def page_size(path, page):
    bl = [b for b in blocks_for(path) if b[0] == page]
    if not bl:
        return None
    return (max(b[3] for b in bl), max(b[4] for b in bl))


def box_for(path, page, label):
    """The pipeline's box for one figure, as fractions of the page."""
    size = page_size(path, page)
    if not size:
        return None
    for c in CI.caption_candidates(blocks_for(path)):
        if c["page"] != page or not c.get("readable", True):
            continue
        if "FIG" + c["number"].upper() != label:
            continue
        b = CI.figure_bbox(c, blocks_for(path))
        if not b:
            return None
        return (b[0] / size[0], b[1] / size[1],
                b[2] / size[0], b[3] / size[1])
    return None


def verdict(cov, intr):
    if cov < COVERED_FLOOR:
        return "WRONG"
    if intr > INTRUSION_CEILING:
        return "WRONG"
    return "OK"


def score(source_of):
    """[(key, covered, intrusion, verdict)] for every figure with a truth box."""
    out = []
    for (pid, label, page) in sorted(T.FIGURE_REGIONS):
        path = source_of(pid)
        if not path:
            continue
        truth = T.FIGURE_REGIONS[(pid, label, page)]
        others = [b for (p, l, g), b in T.FIGURE_REGIONS.items()
                  if p == pid and g == page and l != label]
        box = box_for(path, int(page), label)
        if box is None:
            out.append(((pid, label, page), 0.0, 0.0, "NO_BOX"))
            continue
        out.append(((pid, label, page), T.covered(box, truth),
                    T.intrusion(box, others), verdict(T.covered(box, truth),
                                                     T.intrusion(box, others))))
    return out


def calibrate(scored):
    """The harness must agree with the person. Returns the disagreements."""
    got = {k: v for k, _c, _i, v in scored}
    bad = []
    for key, want in sorted(T.VISUAL_VERDICT.items()):
        have = got.get(key)
        if have is None:
            bad.append((key, want, "not scored"))
        elif have != want:
            bad.append((key, want, have))
    return bad


if __name__ == "__main__":
    rows = json.load(io.open(PATHS.CROSSCHECK, encoding="utf-8"))
    by_pid = {r["pid"]: r for r in rows}
    src = {l.strip().rsplit("/", 1)[-1]: l.strip()
           for l in io.open(PATHS.STAGED, encoding="utf-8") if l.strip()}

    def source_of(pid):
        r = by_pid.get(pid)
        return src.get(r["file"]) if r else None

    scored = score(source_of)
    print("%-22s %9s %9s  %s" % ("figure", "covered", "intrusion", "verdict"))
    for key, cov, intr, v in scored:
        print("%-22s %8.2f %9.2f  %s"
              % ("%s/%s/p%s" % key, cov, intr, v))

    print()
    bad = calibrate(scored)
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
