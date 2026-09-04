# -*- coding: utf-8 -*-
"""계수를 막는 규칙의 가드를 하나씩 되돌리고, 어떤 시나리오가 죽는지 본다.

    python3 mutate_blocks.py

`block_rules.py`는 이 저장소에서 가장 위험한 파일입니다 - 사람이 어떤 그림에
숫자를 적어도 되는지 정하니까요. 여기서 살아남는 변이는 "이 가드를 지키는
시나리오가 없다"는 뜻이고, 그러면 가드를 고치거나 지워야 합니다.
"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import mutate_guard                                       # noqa: E402
ROOT = os.path.dirname(HERE)
SUITE = ["python3", os.path.join(ROOT, "test_sheet_blocks.py")]

MUT = [
    ("M1 판정을 아예 안 봄", "block_rules.py",
     "        if not human_cut(row):\n            return table[key]", "        pass"),
    ("M2 기계가 다시 자른 것도 만료로 침", "block_rules.py",
     '    src = str(row.get("Crop_Source") or "").strip().upper()\n'
     '    return src[len(HUMAN_CUT):] if src.startswith(HUMAN_CUT) else ""',
     '    src = str(row.get("Crop_Source") or "").strip().upper()\n'
     '    return src or ""'),
    ("M3 사람이 정한 크롭인지 안 보고 늘 만료", "block_rules.py",
     "        if not human_cut(row):", "        if False:"),
    ("M4 어디에 있든 HUMAN_CHOICE면 만료", "block_rules.py",
     '    return src[len(HUMAN_CUT):] if src.startswith(HUMAN_CUT) else ""',
     '    return src[len(HUMAN_CUT):] if HUMAN_CUT in src else ""'),
    ("M5 만료를 카드에 알리지 않음", "block_rules.py",
     '    return table.get(key, "") or _defect_reason(defect)',
     '    return ""'),
    ("M6 판정이 없는 행도 만료됐다고 함", "block_rules.py",
     '    return table.get(key, "") or _defect_reason(defect)',
     '    return table.get(key, "만료된 판정")'),
    ("M7 만료가 아직 막힌 행까지 보고함", "block_rules.py",
     '    if not human_cut(row):\n        return ""\n    table = STILL_WRONG',
     '    if False:\n        return ""\n    table = STILL_WRONG'),
    ("M8 상자를 그리면 그림 번호도 읽힌 것으로", "block_rules.py",
     '    if not str(row.get("Figure_Number", "")).strip():',
     '    if not str(row.get("Figure_Number", "")).strip() and not human_cut(row):'),
    ("M9 상자를 그리면 크롭 상태도 통과", "block_rules.py",
     "    if key in table:", "    if human_cut(row):\n        return \"\"\n    if key in table:"),
    ("M11 2차 감사 FAIL은 만료되지 않음", "block_rules.py",
     "    _fail = _defect_reason(defect)\n    if _fail and not human_cut(row):",
     "    _fail = _defect_reason(defect)\n    if _fail:"),
    ("M12 2차 감사 FAIL이 늘 만료됨", "block_rules.py",
     "    if _fail and not human_cut(row):", "    if False:"),
    ("M13 만료 보고가 감사 판정을 빠뜨림", "block_rules.py",
     '    return table.get(key, "") or _defect_reason(defect)',
     '    return table.get(key, "")'),
    ("M14 경고도 막는 판정으로 침", "block_rules.py",
     '    if not defect or str(defect.get("classification", "")).strip() != "FAIL":\n        return ""',
     '    if not defect:\n        return ""'),
    # ----------------------------------- 상자를 그리면 풀리는가 (판정 페이지가 하는 약속)
    ("M15 상자로는 못 푸는 행도 풀린다고 함", "block_rules.py",
     '            trial.update(Crop_Source=HUMAN_CUT + "DRAWN",\n'
     '                         Crop_Quality_Status="ACCEPTABLE")',
     '            trial.update(Crop_Source=HUMAN_CUT + "DRAWN",\n'
     '                         Crop_Quality_Status="ACCEPTABLE",\n'
     '                         Figure_Number="FIGX", Confidence="1.00")'),

    ("M16 다시 재는 것을 셈에 넣지 않음", "block_rules.py",
     "                 Crop_Quality_Status=\"ACCEPTABLE\")", "                 )"),
    ("M17 공유 크롭이 풀리는 것으로 안 침", "block_rules.py",
     '            ctx.update(shared_with=(), roundtrip="MATCH",',
     '            ctx.update(roundtrip="MATCH",'),

    ("M18 사람이 정한 크롭이라는 것을 빠뜨림", "block_rules.py",
     '            trial.update(Crop_Source=HUMAN_CUT + "DRAWN",',
     '            trial.update(Crop_Source="",'),

    ("M19 물어보면서 행을 고침", "block_rules.py",
     '            trial.update(Crop_Source=HUMAN_CUT + "DRAWN",\n'
     '                         Crop_Quality_Status="ACCEPTABLE")',
     '            row["Crop_Quality_Status"] = "ACCEPTABLE"\n'
     '            trial.update(Crop_Source=HUMAN_CUT + "DRAWN")'),

    # ------------------------------------------- 한 그림을 두 행이 세는 것
    ("M29 중복을 안 봄", "block_rules.py",
     "    if duplicate:\n        if len(duplicate) > 2", "    if False:\n        if len(duplicate) > 2"),
    ("M30 겹치지 않아도 중복으로 침", "block_rules.py",
     "                if any(_iou(box, other_box) >= DUPLICATE_IOU for _o, other_box in c):",
     "                if True:"),
    ("M31 겹침 문턱을 0으로", "block_rules.py",
     "DUPLICATE_IOU = 0.30", "DUPLICATE_IOU = 0.0"),
    ("M32 쪽이 달라도 중복으로 침", "block_rules.py",
     '        key = (r.get("Source_Document_ID"), fig, str(r.get("Page") or "").strip())',
     '        key = (r.get("Source_Document_ID"), fig)'),
    ("M33 그림 번호가 달라도 중복", "block_rules.py",
     '        key = (r.get("Source_Document_ID"), fig, str(r.get("Page") or "").strip())',
     '        key = (r.get("Source_Document_ID"), str(r.get("Page") or "").strip())'),
    ("M34 문서가 달라도 중복", "block_rules.py",
     '        key = (r.get("Source_Document_ID"), fig, str(r.get("Page") or "").strip())',
     '        key = (fig, str(r.get("Page") or "").strip())'),
    ("M35 번호 없는 행도 짝지음", "block_rules.py",
     "        if not box or not fig:\n            continue", "        if not box:\n            continue"),
    ("M36 근거 순서를 뒤집음", "block_rules.py",
     "            ranked = sorted(c, key=lambda rb: (-claim_rank(rb[0]), rb[0][\"Draft_ID\"]))",
     "            ranked = sorted(c, key=lambda rb: (claim_rank(rb[0]), rb[0][\"Draft_ID\"]))"),
    ("M37 근거를 안 보고 이름순으로만", "block_rules.py",
     "            ranked = sorted(c, key=lambda rb: (-claim_rank(rb[0]), rb[0][\"Draft_ID\"]))",
     "            ranked = sorted(c, key=lambda rb: rb[0][\"Draft_ID\"])"),
    ("M38 옮겨 그린 것을 제자리 그림과 같이 침", "block_rules.py",
     '    return (CLAIM_DRAWN_ELSEWHERE if str(row.get("Moved_From_Page") or "").strip()\n            else CLAIM_DRAWN)',
     "    return CLAIM_DRAWN"),
    ("M39 사람이 고른 것과 탐지기가 놓은 것을 같이 침", "block_rules.py",
     "    if not src.startswith(HUMAN_CUT):\n        return CLAIM_DETECTED",
     "    if True:\n        return CLAIM_DETECTED"),
    ("M40 중복도 상자로 풀린다고 함", "block_rules.py",
     '            ctx.update(shared_with=(), roundtrip="MATCH",\n'
     '                       agreement="HUMAN_VALIDATED", crop_sha="")',
     '            ctx.update(shared_with=(), roundtrip="MATCH",\n'
     '                       agreement="HUMAN_VALIDATED", crop_sha="",\n'
     '                       duplicate=None)'),

    ("M41 이유가 이긴 행을 안 말함", "block_rules.py",
     '                % (duplicate[0], duplicate[1], duplicate[0], duplicate[0]))',
     '                % ("어떤", duplicate[1], "어떤", "어떤"))'),

    # ----------------------------------------- 본문 참조 문장이 캡션으로 잡힌 행
    ("M20 유령 판정 안 함", "block_rules.py",
     "    ghost = phantom_reason(row, codes, twin)\n    if ghost:\n        return ghost",
     "    ghost = \"\"\n    if ghost:\n        return ghost"),
    ("M21 옆 쪽 행 없이도 유령으로 침", "block_rules.py",
     "    if not (twin and body_reference(row.get(\"Caption_Text\"))):",
     "    if not body_reference(row.get(\"Caption_Text\")):\n        return \"\"\n    twin = twin or (\"?\", 0)\n    if False:"),
    ("M22 탐지기 코드를 안 봄 (문장형 진짜 캡션이 죽음)", "block_rules.py",
     "    if len(codes) != 2 or any(c != NO_CANDIDATE for c in codes):\n        return \"\"",
     "    if False:\n        return \"\""),
    ("M23 한쪽 탐지기만 후보 없어도 유령", "block_rules.py",
     "    if len(codes) != 2 or any(c != NO_CANDIDATE for c in codes):",
     "    if len(codes) != 2 or all(c != NO_CANDIDATE for c in codes):"),
    ("M24 캡션 문장을 안 봄", "block_rules.py",
     "    if not (twin and body_reference(row.get(\"Caption_Text\"))):",
     "    if not twin:"),
    ("M25 이유에 진짜 행을 안 적음", "block_rules.py",
     '            "크기의 영역이 없고, 같은 그림이 p.%s의 %s 행으로 이미 있습니다. 이 행을 "\n'
     '            "세면 그 그림을 두 번 세는 것입니다." % (other_page, other))',
     '            "크기의 영역이 없습니다.")'),
    ("M26 멀리 있는 같은 번호도 이웃으로", "block_rules.py",
     "                if other != did and abs(other_page - page) == 1:",
     "                if other != did:"),
    ("M27 다른 문서까지 이웃으로", "block_rules.py",
     '        key = (r.get("Source_Document_ID"), r.get("Figure_Number"))',
     '        key = (r.get("Figure_Number"),)'),
    ("M28 유령 판정을 크롭 판정 뒤로", "block_rules.py",
     "    ghost = phantom_reason(row, codes, twin)\n    if ghost:\n        return ghost\n    if key in table:",
     "    if key in table:\n        ghost = phantom_reason(row, codes, twin)\n        if ghost and not human_cut(row):\n            return ghost\n    if key in table:"),
    ("M10 공유 크롭도 만료로 뚫림", "block_rules.py",
     "    if shared_with:", "    if shared_with and not human_cut(row):"),
    # ------------------- \ubcf8\ubb38 \ubb38\uc7a5 \ud310\uc815\uacfc "\uadf8 \uadf8\ub9bc\uc744 \ub204\uac00 \uc138\uace0 \uc788\ub098"
    ("M58 \ubcf5\uc218\ud615\uc744 \ubabb \ubd04", "block_rules.py",
     'm = BODY_MULTI.match(text) or BODY_REFERENCE.match(text)',
     'm = BODY_REFERENCE.match(text)'),
    ("M59 body_reference\uac00 \ubcf5\uc218\ud615\uc744 \ubabb \ubd04", "block_rules.py",
     'return bool(BODY_MULTI.match(text) or BODY_REFERENCE.match(text))',
     'return bool(BODY_REFERENCE.match(text))'),
    ("M60 OCR l/I\ub97c \uc22b\uc790\ub85c \uc548 \ubd04", "block_rules.py",
     '_FIGNUM = r"(?:\\d{1,2}|[lI])"', '_FIGNUM = r"(?:\\d{1,2})"'),
    ("M61 ', and'\ub97c \ubaa8\ub974\uba74 \ub9c8\uc9c0\ub9c9 \uadf8\ub9bc\uc744 \uc783\ub294\ub2e4", "block_rules.py",
     r'_SEP = r"(?:\s*,\s*and\s+|\s*,\s*|\s*&\s*|\s+and\s+)"',
     r'_SEP = r"(?:\s*,\s*|\s*&\s*|\s+and\s+)"'),
    ("M62 l/I\ub97c 1\ub85c \uc548 \uc77d\uc74c", "block_rules.py",
     '1 if token in ("l", "I") else int(token)',
     'int(token) if token.isdigit() else 99'),
    ("M63 \ub9c9\ud78c \ud589\ub3c4 \uc138\uace0 \uc788\ub2e4\uace0 \ud568", "block_rules.py",
     '                    and str(blocked_of.get(other["Draft_ID"], "")).strip()\n'
     '                    != BLOCKED_MARK):',
     '                    ):'),
    ("M64 \ub9c9\ud798 \ud45c\uc2dc\ub97c \ucc38\uac70\uc9d3\uc73c\ub85c \uc77d\uc74c", "block_rules.py",
     '                    and str(blocked_of.get(other["Draft_ID"], "")).strip()\n'
     '                    != BLOCKED_MARK):',
     '                    and not blocked_of.get(other["Draft_ID"])):'),
    ("M65 \uc790\uae30 \uc790\uc2e0\ub3c4 \uc138\uace0 \uc788\ub2e4\uace0 \ud568", "block_rules.py",
     '            if other.get("Draft_ID") == row.get("Draft_ID"):\n                continue\n',
     ''),
    # M66은 없습니다. "이 사실은 행을 막지 않는다"는 가드는 구조적입니다 -
    # `blocked_reason`이 `mentions_held`를 부르지 않습니다. 변이는 있는 줄을
    # 뒤집을 뿐 없는 호출을 만들지 못하므로 어떤 변이도 그것을 표현할 수
    # 없고, 죽지 않는 변이는 가드가 관측되지 않는다는 뜻이 아니라 그 변이가
    # 아무것도 바꾸지 않는다는 뜻입니다. 시나리오가 그 계약을 적어 둡니다.

    # -------------------------------- 번호: 사람이 채우면 풀리는가, 같은 문 두 번
    ("M52 상자만 물어보고 번호는 안 물어봄", "block_rules.py",
     "    for wanted in ((), (REPAIR_BOX,), (REPAIR_NUMBER,),\n"
     "                   (REPAIR_BOX, REPAIR_NUMBER)):",
     "    for wanted in ((), (REPAIR_BOX,)):"),
    ("M53 둘 다 필요한 경우를 안 봄", "block_rules.py",
     "                   (REPAIR_BOX, REPAIR_NUMBER)):",
     "                   ):"),
    ("M54 번호 시늉만 하고 사람이 적었다고 안 함", "block_rules.py",
     '            trial["Number_Source"] = NUMBER_BY_HUMAN\n', ""),
    ("M55 사람이 적어도 신뢰도 0이 그대로 막음", "block_rules.py",
     "        if not (numbered_by_hand(row)\n"
     "                and reason.startswith(UNREADABLE_NUMBER_REASON)):",
     "        if True:"),
    ("M56 어떤 사유의 신뢰도 0이든 번호로 뚫림", "block_rules.py",
     "        if not (numbered_by_hand(row)\n"
     "                and reason.startswith(UNREADABLE_NUMBER_REASON)):",
     "        if not numbered_by_hand(row):"),
    ("M57 기계가 넣은 번호도 사람 것으로 침", "block_rules.py",
     '    return (str(row.get("Number_Source") or "").strip().upper()\n'
     "            == NUMBER_BY_HUMAN)",
     "    return True"),
    # ------------------------------ 중복: 막힌 행은 끼지 않고, 사람이 찾은 중복은 적힌다
    ("M47 사람이 막은 행도 중복 겨루기에 낌", "block_rules.py",
     '        if r.get("Draft_ID") in blocked_ids:\n            continue\n',
     ''),
    ("M48 적어 둔 중복을 읽지 않음", "block_rules.py",
     '        twin = str(r.get("Duplicate_Of") or "").strip()\n        if twin:',
     '        twin = str(r.get("Duplicate_Of") or "").strip()\n        if False:'),
    ("M49 사람이 찾은 중복을 기계 중복처럼 말함", "block_rules.py",
     "        if len(duplicate) > 2 and duplicate[2] == CONFIRMED_BY_BOX:",
     "        if False:"),
    ("M50 중복으로 설명되는 쌍도 픽셀 충돌로 봄", "block_rules.py",
     "                others = sorted(x for x in ids if x != one and not same_figure(one, x))",
     "                others = sorted(x for x in ids if x != one)"),
    ("M51 한쪽 방향의 중복만 설명으로 침", "block_rules.py",
     "        return ((duplicate.get(a) or (None,))[0] == b\n"
     "                or (duplicate.get(b) or (None,))[0] == a)",
     "        return (duplicate.get(a) or (None,))[0] == b"),
]


def run():
    r = subprocess.run(SUITE, capture_output=True, text=True, cwd=ROOT)
    fails = [l.split("FAIL", 1)[1].strip() for l in r.stdout.splitlines()
             if l.strip().startswith("FAIL")]
    return r.returncode, fails


mutate_guard.restore_any(HERE)

bad = 0
for name, filename, old, new in MUT:
    path = os.path.join(HERE, filename)
    base = open(path, encoding="utf-8").read()
    if old not in base:
        print("PATCH_FAILED %s" % name)
        bad += 1
        continue
    with mutate_guard.mutation(path, base.replace(old, new, 1)):
        code, fails = run()
    killed = code != 0
    print("%-9s %-34s %s" % ("KILLED" if killed else "SURVIVED", name,
                             ("| " + "; ".join(f[:52] for f in fails[:2])) if killed
                             else "<-- 이 가드를 지키는 시나리오가 없다"))
    if not killed:
        bad += 1

code, _ = run()
print("\n복원 후: %s" % ("통과" if code == 0 else "실패 - 복원되지 않았습니다"))
sys.exit(1 if bad or code else 0)
