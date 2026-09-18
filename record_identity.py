# -*- coding: utf-8 -*-
"""사람이 정체 제안을 보고 내린 판정을 제안 파일에 적습니다.

    python3 record_identity.py --proposals DIR \\
        --answers DIR/identity_answers.csv --when 2026-09-18

`identity_page.py`가 내는 답 CSV를 받아, 그 답이 실제로 낸 제안에 대한 것인지,
사람이 오버레이를 보았다고 말했는지, 누가 보았는지 말했는지를 보고 나서
적습니다. `record_geometry.py`와 같은 자리에 서 있습니다.

이 관문이 지키는 것은 **계획서가 설 수 있는 정체**입니다: x 위치가 있고 라벨이
서로 다르고, 계열이 있고 표 종류가 계열을 가를 수 있고, 결과변수에 이름이 있는
것. 요인 이름은 사람만 적고, 이 관문은 그 이름이 계획서의 격자 이름으로 쓸 수
있는 모양인지만 봅니다.

적는 파일은 `identity_decisions.csv`이고 제안의 열을 그대로 씁니다 -
`make_plan`이 그 행을 바로 읽습니다.
"""
import argparse
import csv
import io
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import batch_manifests as BM                                     # noqa: E402
import identity_proposer as IP                                   # noqa: E402

PROPOSALS = IP.PROPOSALS
DECISIONS = "identity_decisions.csv"

VERDICTS = ("CONFIRMED", "REJECTED", "HOLD")
HELD = "HOLD"
ANSWER_REQUIRED = ("Proposal_ID", "Human_Verification_Status", "Verified_By", "Seen_By_Person")
TRUE = ("1", "TRUE", "YES", "Y", "T")
FACTOR_NAME = re.compile(r"^[A-Z][A-Z0-9_]*$")
COLOUR_HEX = re.compile(r"^#[0-9A-Fa-f]{6}$")
BAR_TOPS = ("OUTLINE_CENTER", "FILL_EDGE", "MARKER_CENTER", "NOT_A_BAR")
#: 프레임 너비의 이만큼은 밖이어도 x 위치로 봐줍니다.
FRAME_SLACK = 0.10


def is_true(v):
    return str(v or "").strip().upper() in TRUE


def parse_json_list(text, what):
    """(목록, 문제). JSON 배열이 아니면 문제."""
    raw = (text or "").strip()
    if not raw:
        return [], None
    try:
        got = json.loads(raw)
    except ValueError:
        return [], ("%s_NOT_JSON" % what, "%s 칸이 JSON 목록이 아닙니다: %r" % (what, raw[:60]))
    if not isinstance(got, list) or not all(isinstance(e, dict) for e in got):
        return [], ("%s_NOT_JSON" % what, "%s 칸은 객체의 목록이어야 합니다" % what)
    return got, None


def load_proposals(proposals):
    path = os.path.join(proposals, PROPOSALS)
    if not os.path.exists(path):
        raise SystemExit("%s가 없습니다. 답을 붙일 제안이 없습니다." % path)
    return dict((r["Proposal_ID"], r) for r in csv.DictReader(io.open(path, encoding="utf-8-sig")))


def load_recorded(out_path):
    if not os.path.exists(out_path):
        return []
    return list(csv.DictReader(io.open(out_path, encoding="utf-8-sig")))


def positions_problems(positions, proposal):
    out = []
    if not positions:
        return [("X_POSITIONS_MISSING", "확인인데 x 위치가 하나도 없습니다.")]
    seen = set()
    try:
        x0, x1 = float(proposal.get("Panel_X0")), float(proposal.get("Panel_X1"))
        slack = (x1 - x0) * FRAME_SLACK
    except (TypeError, ValueError):
        x0 = x1 = slack = None
    for i, p in enumerate(positions, 1):
        label = str(p.get("label") or "").strip()
        px = p.get("px")
        if not label:
            out.append(("X_LABEL_MISSING", "%d번째 x 위치의 라벨이 비어 있습니다." % i))
        elif label.upper() in seen:
            out.append(("X_LABEL_DUPLICATE", "x 라벨 %r이 둘입니다." % label))
        seen.add(label.upper())
        if not isinstance(px, (int, float)) or px != px:
            out.append(("X_PIXEL_MISSING", "x 위치 %r의 픽셀이 수가 아닙니다." % label))
        elif x0 is not None and (px < x0 - slack or px > x1 + slack):
            out.append(("X_PIXEL_OUTSIDE_FRAME", "x 위치 %r(%g px)이 프레임 %g..%g 밖입니다."
                        % (label, px, x0, x1)))
    return out


def series_problems(series, mark):
    out = []
    if not series:
        return [("SERIES_MISSING", "확인인데 계열이 하나도 없습니다.")]
    names, keys = set(), []
    for i, e in enumerate(series, 1):
        name = str(e.get("name") or "").strip()
        if not name and len(series) > 1:
            out.append(("SERIES_NAME_MISSING", "%d번째 계열의 이름이 비어 있습니다." % i))
        elif name and name.upper() in names:
            out.append(("SERIES_NAME_DUPLICATE", "계열 이름 %r이 둘입니다." % name))
        names.add(name.upper())
        colour = str(e.get("colour") or "").strip()
        if colour and not COLOUR_HEX.match(colour):
            out.append(("SERIES_COLOUR_BAD", "계열 %r의 색 %r은 #RRGGBB가 아닙니다." % (name, colour)))
        if mark in BM.COLOUR_MARK_TYPES and not colour:
            out.append(("SERIES_COLOUR_MISSING", "%s은 색으로 계열을 가르는데 계열 %r에 색이 없습니다."
                        % (mark, name or i)))
        style = str(e.get("line_style") or "").strip().upper()
        marker = str(e.get("marker") or "").strip().upper()
        mfill = str(e.get("marker_fill") or "").strip().upper()
        bfill = str(e.get("bar_fill") or "").strip().upper()
        for value, vocab, what in ((style, BM.LINE_STYLES, "line_style"),
                                   (marker, BM.MARKER_SHAPES, "marker"),
                                   (mfill, BM.MARKER_FILLS, "marker_fill"),
                                   (bfill, BM.BAR_FILL_PATTERNS, "bar_fill")):
            if value and value not in vocab:
                out.append(("SERIES_STYLE_UNKNOWN", "계열 %r의 %s=%r은 %s 중 하나가 아닙니다."
                            % (name, what, value, "/".join(vocab))))
        if mark == "LINE_MONO_STYLE" and style in ("", "NONE"):
            out.append(("SERIES_DISCRIMINANT_MISSING",
                        "LINE_MONO_STYLE은 선 모양으로 계열을 가르는데 계열 %r에 선 모양이 없습니다." % (name or i)))
        if mark == "LINE_MONO" and len(series) > 1 and marker in ("", "NONE"):
            out.append(("SERIES_DISCRIMINANT_MISSING",
                        "LINE_MONO는 마커 모양으로 계열을 가르는데 계열 %r에 마커가 없습니다." % (name or i)))
        if mark == "BAR_MONO" and len(series) > 1 and bfill in ("", "NONE"):
            out.append(("SERIES_DISCRIMINANT_MISSING",
                        "BAR_MONO는 채움 무늬로 계열을 가르는데 계열 %r에 무늬가 없습니다." % (name or i)))
        keys.append(colour.upper() if mark in BM.COLOUR_MARK_TYPES else (style, marker, mfill, bfill))
    if len(series) > 1 and len(set(keys)) != len(keys):
        out.append(("SERIES_NOT_SEPARABLE", "두 계열을 가를 것이 없습니다 (같은 색이거나 같은 모양)."))
    return out


def check_answer(answer, proposed):
    problems = []
    pid = (answer.get("Proposal_ID") or "").strip()
    verdict = (answer.get("Human_Verification_Status") or "").strip().upper()
    who = (answer.get("Verified_By") or "").strip()
    if not is_true(answer.get("Seen_By_Person")):
        problems.append(("NOT_SEEN_BY_PERSON", "확인 페이지에서 \"이 오버레이를 직접 봤다\"를 "
                                               "표시하지 않았습니다. 표시가 없는 답은 적지 않습니다."))
    if not who:
        problems.append(("UNATTRIBUTED", "누가 보았는지 적혀 있지 않습니다. 이름 없는 확인은 확인이 아닙니다."))
    if verdict not in VERDICTS:
        problems.append(("BAD_VERDICT", "%r은 이 관문이 받는 답이 아닙니다. 받는 것: %s"
                         % (verdict or "(빈칸)", ", ".join(VERDICTS))))
        return problems
    if pid not in proposed:
        problems.append(("NOT_PROPOSED", "%r은 이 폴더가 낸 제안이 아닙니다." % (pid or "(빈칸)")))
        return problems
    if verdict == HELD:
        problems.append(("HELD", "아직 정하지 않은 답입니다. 적지 않고 목록에 남겨 둡니다."))
        return problems
    if verdict != "CONFIRMED":
        return problems
    proposal = proposed[pid]
    x_factor = (answer.get("X_Factor") or "").strip().upper()
    s_factor = (answer.get("Series_Factor") or "").strip().upper()
    if not x_factor:
        problems.append(("X_FACTOR_MISSING", "x축이 무슨 요인인지 적혀 있지 않습니다. 사람만 적을 수 있습니다."))
    elif not FACTOR_NAME.match(x_factor):
        problems.append(("FACTOR_NAME_BAD", "요인 이름 %r은 대문자·숫자·밑줄이어야 합니다." % x_factor))
    if s_factor and not FACTOR_NAME.match(s_factor):
        problems.append(("FACTOR_NAME_BAD", "요인 이름 %r은 대문자·숫자·밑줄이어야 합니다." % s_factor))
    if s_factor and s_factor == x_factor:
        problems.append(("FACTOR_ON_BOTH_AXES", "x 요인과 계열 요인이 둘 다 %s입니다. 한 요인이 두 축에 "
                                                "있으면 Cell_Key가 두 번 적힙니다." % x_factor))
    positions, bad = parse_json_list(answer.get("X_Labels"), "X_Labels")
    if bad:
        problems.append(bad)
    else:
        problems.extend(positions_problems(positions, proposal))
    mark = (answer.get("Mark_Type") or "").strip().upper()
    kind = (proposal.get("Panel_Kind") or "").strip().upper()
    allowed = IP.MARK_TYPES_FOR.get(kind, ()) + (("LINE_MONO_STYLE",) if kind == "LINE" else ())
    if mark not in BM.BATCH_MARK_TYPES:
        problems.append(("MARK_TYPE_BAD", "표 종류 %r은 %s 중 하나가 아닙니다."
                         % (mark or "(빈칸)", "/".join(BM.BATCH_MARK_TYPES))))
    elif allowed and mark not in allowed:
        problems.append(("MARK_TYPE_NOT_FOR_KIND", "이 패널은 %s로 세어졌는데 표 종류가 %s입니다. "
                                                   "그 종류에 맞는 것: %s" % (kind, mark, "/".join(allowed))))
    series, bad = parse_json_list(answer.get("Series"), "Series")
    if bad:
        problems.append(bad)
    else:
        problems.extend(series_problems(series, mark))
        if len(series) > 1 and not s_factor:
            problems.append(("SERIES_FACTOR_MISSING", "계열이 %d개인데 계열이 무슨 요인인지 적혀 있지 않습니다."
                             % len(series)))
    if not (answer.get("Outcome_Name") or "").strip():
        problems.append(("OUTCOME_MISSING", "결과변수 이름이 없습니다."))
    n = (answer.get("N_Outcome") or "").strip()
    if n and not (n.isdigit() and int(n) > 0):
        problems.append(("N_BAD", "n=%r은 양의 정수가 아닙니다." % n))
    bar_top = (answer.get("Bar_Top_Definition") or "").strip().upper()
    if mark.startswith("BAR") and bar_top not in BAR_TOPS:
        problems.append(("BAR_TOP_MISSING", "막대 표인데 값을 어디서 읽는지(%s)가 없습니다." % "/".join(BAR_TOPS)))
    if bar_top and bar_top not in BAR_TOPS:
        problems.append(("BAR_TOP_BAD", "Bar_Top_Definition=%r" % bar_top))
    stem = (answer.get("Errorbar_Stem_Confirmed") or "").strip().upper()
    if stem and stem not in ("TRUE", "FALSE"):
        problems.append(("STEM_BAD", "Errorbar_Stem_Confirmed=%r은 TRUE/FALSE가 아닙니다." % stem))
    return problems


def record(proposals, answers, when, out_path=None, replace=False, log=print, answers_path=None):
    missing = [c for c in ANSWER_REQUIRED if c not in (answers[0] if answers else {})]
    if answers and missing:
        raise SystemExit("답 CSV에 %s 열이 없습니다. 확인 페이지가 내려준 파일이 맞습니까?"
                         % ", ".join(missing))
    proposed = load_proposals(proposals)
    out_path = out_path or os.path.join(proposals, DECISIONS)
    if answers_path and os.path.exists(answers_path) and os.path.exists(out_path) \
            and os.path.samefile(answers_path, out_path):
        raise SystemExit("답 파일과 적는 파일이 같습니다 (%s). 페이지가 내려준 파일은 "
                         "identity_answers.csv이고, 이 관문이 적는 파일은 %s입니다." % (out_path, DECISIONS))
    existing = load_recorded(out_path)
    settled = set(r["Proposal_ID"] for r in existing)
    written, turned_away = [], []
    for answer in answers:
        pid = (answer.get("Proposal_ID") or "").strip()
        problems = check_answer(answer, proposed)
        if problems:
            turned_away.append((pid or "(빈칸)", problems))
            continue
        if pid in settled and not replace:
            turned_away.append((pid, [("ALREADY_RECORDED", "이 제안은 이미 판정되어 있습니다. 바꾸려면 --replace를 주십시오.")]))
            continue
        row = dict(proposed[pid])
        row.update({
            "Human_Verification_Status": (answer.get("Human_Verification_Status") or "").strip().upper(),
            "Verified_By": (answer.get("Verified_By") or "").strip(),
            "Verified_At": when,
            "X_Factor": (answer.get("X_Factor") or "").strip().upper(),
            "X_Labels": (answer.get("X_Labels") or "").strip(),
            "Series_Factor": (answer.get("Series_Factor") or "").strip().upper(),
            "Series": (answer.get("Series") or "").strip(),
            "Mark_Type": (answer.get("Mark_Type") or "").strip().upper(),
            "Outcome_Name": (answer.get("Outcome_Name") or "").strip(),
            "Unit": (answer.get("Unit") or "").strip(),
            "N_Outcome": (answer.get("N_Outcome") or "").strip(),
            "Bar_Top_Definition": (answer.get("Bar_Top_Definition") or "").strip().upper(),
            "Errorbar_Stem_Confirmed": (answer.get("Errorbar_Stem_Confirmed") or "").strip().upper(),
            "Note": (answer.get("Note") or "").strip(),
        })
        written.append(row)
    keep = [r for r in existing if r["Proposal_ID"] not in set(w["Proposal_ID"] for w in written)]
    rows = sorted(keep + written, key=lambda x: x["Proposal_ID"])
    IP.write_proposals(out_path, rows)
    log("적음 %d · 거절 %d · 이미 있던 것 %d" % (len(written), len(turned_away), len(keep)))
    for name, problems in turned_away:
        for code, why in problems:
            log("  거절 %s — %s: %s" % (name, code, why))
    return written, turned_away, out_path


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--proposals", required=True)
    ap.add_argument("--answers", required=True)
    ap.add_argument("--out")
    ap.add_argument("--when", required=True, help="사람이 오버레이를 본 날짜. 오늘로 채우지 않습니다.")
    ap.add_argument("--replace", action="store_true")
    a = ap.parse_args(argv)
    answers = list(csv.DictReader(io.open(a.answers, encoding="utf-8-sig")))
    _w, refused, path = record(os.path.expanduser(a.proposals), answers, a.when, out_path=a.out,
                               replace=a.replace, answers_path=os.path.expanduser(a.answers))
    print(path)
    return 1 if refused else 0


if __name__ == "__main__":
    raise SystemExit(main())
