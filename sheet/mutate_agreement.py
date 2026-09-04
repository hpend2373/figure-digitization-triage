# -*- coding: utf-8 -*-
"""영역 합의 규칙과 다시 자르기의 가드를 하나씩 되돌리고, 어떤 시나리오가 죽는지 본다.

    python3 mutate_agreement.py
"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import mutate_guard                                       # noqa: E402
SUITE = ["python3", os.path.join(HERE, "test_sheet_build.py")]

MUT = [
    ("M1 차단 규칙이 합의를 안 봄", "block_rules.py",
     "    if agreement is not None and agreement not in AGREEMENT_COUNTABLE:",
     "    if False:"),
    ("M2 모르는 값을 통과시킴", "block_rules.py",
     '''        return AGREEMENT_UNCOUNTABLE.get(
            agreement, "그림 영역 검증 결과를 해석할 수 없어 막았습니다 (%r)."
            % (agreement,))''',
     '''        if agreement in AGREEMENT_UNCOUNTABLE:
            return AGREEMENT_UNCOUNTABLE[agreement]
        return ""'''),
    ("M3 빌더가 합의를 안 넘김", "build_sheet2.py",
     '''                             agreement=(None if AGREEMENT is None else
                                        AGREEMENT.get(d["Draft_ID"], "PENDING")),''',
     "                             agreement=None,"),
    ("M15 빌더가 중복 사실을 규칙에 안 넘김", "build_sheet2.py",
     '                             duplicate=DUPLICATE.get(d["Draft_ID"]))',
     "                             duplicate=None)"),
    ("M16 빌더가 중복을 계산하지 않음", "build_sheet2.py",
     "DUPLICATE = BR.duplicate_map(DRAFT, blocked_ids=_BLOCKED_IDS)", "DUPLICATE = {}"),
    # ------------------------------------------ 중복: 두 출처, 막힌 행 제외, 칸으로 적기
    ("M17 빌더가 막힌 행도 중복 겨루기에 넣음", "build_sheet2.py",
     "DUPLICATE = BR.duplicate_map(DRAFT, blocked_ids=_BLOCKED_IDS)",
     "DUPLICATE = BR.duplicate_map(DRAFT, blocked_ids=())"),
    ("M18 빌더가 apply가 적어 둔 중복을 읽지 않음", "build_sheet2.py",
     "    DUPLICATE.setdefault(_i, _v)", "    pass"),
    ("M19 빌더가 픽셀 충돌에 중복을 안 넘김", "build_sheet2.py",
     "SHARED_CROP = BR.shared_crop_map(CROP_SHA, duplicate=DUPLICATE)",
     "SHARED_CROP = BR.shared_crop_map(CROP_SHA)"),
    ("M20 사유 표가 이긴 행을 적지 않음", "build_sheet2.py",
     '            "Duplicate_Of": (DUPLICATE.get(_d["Draft_ID"]) or ("",))[0] if _br else "",',
     '            "Duplicate_Of": "",'),
    ("M21 요약이 중복을 막음에 섞어 셈", "build_sheet2.py",
     "         _DUP_BLOCKED,", "         0,"),
    # ------------------------------------------- 번호: 빌더가 규칙에게 한 번만 묻는가
    ("M22 사유 표가 번호 필요를 안 적음", "build_sheet2.py",
     '            "Number_Would_Open": "1" if BR.REPAIR_NUMBER in _fix else "0",',
     '            "Number_Would_Open": "0",'),
    ("M23 상자 필요를 번호 답으로 적음", "build_sheet2.py",
     '            "Box_Would_Open": "1" if BR.REPAIR_BOX in _fix else "0",',
     '            "Box_Would_Open": "1" if BR.REPAIR_NUMBER in _fix else "0",'),
    ("M25 \uc0ac\uc720 \ud45c\uac00 '\ub204\uac00 \uc138\uace0 \uc788\ub098'\ub97c \uc548 \uc801\uc74c", "build_sheet2.py",
     '            "Mentions_Held": ";".join(', '            "Mentions_Held": "" and ";".join('),
    ("M26 \ubb38\uc11c\ubcc4\ub85c \uc548 \ub098\ub204\uace0 \uc804\uccb4\uc5d0\uc11c \ucc3e\uc74c", "build_sheet2.py",
     '                    _d, BYDOC_ROWS.get(_d["Source_Document_ID"], ()), BLOCK))',
     '                    _d, DRAFT, BLOCK))'),
    # `if _br else ()`를 지우는 변이는 여기 없습니다. `repairs_that_open`은
    # 막히지 않은 행에 대해 어차피 ()를 돌려주므로 (빈 후보를 먼저 시험합니다)
    # 출력이 한 글자도 달라지지 않습니다 - 죽일 수 없는 변이는 가드가 관측되지
    # 않는다는 뜻이 아니라 그 변이가 아무것도 바꾸지 않는다는 뜻입니다. 그 절은
    # 644행 중 568행에 대한 계산을 건너뛰는 속도 가드로 남깁니다.
    ("M4 검증표 없어도 진행", "build_sheet2.py",
     "elif PATHS.REGIONS_OPTIONAL:\n    AGREEMENT = None",
     "elif True:\n    AGREEMENT = None"),
    ("M5 빌드 ID에서 검증표 제외", "build_sheet2.py",
     "              PATHS.CENSUS, PATHS.REGIONS]", "              PATHS.CENSUS]"),
    ("M6 다시 자르기가 DISAGREE도 자름", "apply_validated.py",
     '        if reg.get("Agreement") != RECUT_FROM:', "        if False:"),
    ("M7 다시 자르기가 THIN도 자름", "apply_validated.py",
     '        if str(d.get("Crop_Quality_Status") or "").strip() != "ACCEPTABLE":',
     "        if False:"),
    ("M8 크롭 파일을 안 바꿈", "apply_validated.py",
     '        image.save(os.path.join(run, d["Figure_Crop"]))', "        pass"),
    # 두 자리에 같은 줄이 있습니다 - 사람이 고른 상자로 자르는 쪽과 기계가
    # 검증 상자로 자르는 쪽. 들여쓰기만 다르므로 짧은 앵커는 앞의 것(사람 쪽)을
    # 집었고, 이 러너의 시나리오는 사람 경로를 돌지 않아 변이가 살아남았습니다.
    # 앞 줄까지 포함해 기계 경로를 정확히 집습니다. 사람 경로의 같은 가드는
    # `mutate_review.py`가 `test_review_sheet.py`로 지킵니다.
    ("M9 옛 상자를 안 남김 (기계가 다시 자르는 쪽)", "apply_validated.py",
     '        image.save(os.path.join(run, d["Figure_Crop"]))\n'
     '        d["Proposal_Figure_BBox"] = d.get("Proposal_Figure_BBox") or old_box',
     '        image.save(os.path.join(run, d["Figure_Crop"]))'),
    ("M10 검증표를 AGREE_3으로 안 바꿈", "apply_validated.py",
     '        reg["Agreement"] = "AGREE_3"', "        pass"),
    ("M11 Human_Choice 검증 제거", "apply_validated.py",
     "        if choice not in HUMAN_CHOICES:", "        if False:"),
    ("M12 사람의 BLOCKED 무시", "apply_validated.py",
     '            if choice == "BLOCKED":', "            if False:"),
    ("M13 Agent_Choice를 사람 선택처럼 적용", "apply_validated.py",
     '        choice = str(reg.get("Human_Choice") or "").strip().upper()\n        if choice:',
     '        choice = str(reg.get("Human_Choice") or reg.get("Agent_Choice") or "").strip().upper()\n        if choice:'),
    ("M14 HUMAN_BLOCKED를 통과시킴", "block_rules.py",
     'AGREEMENT_COUNTABLE = ("AGREE_3", "HUMAN_VALIDATED")',
     'AGREEMENT_COUNTABLE = ("AGREE_3", "HUMAN_VALIDATED", "HUMAN_BLOCKED")'),
]


def run():
    r = subprocess.run(SUITE, capture_output=True, text=True, cwd=HERE)
    fails = [l.split("FAIL", 1)[1].strip() for l in r.stdout.splitlines()
             if l.strip().startswith("FAIL")]
    return r.returncode, fails


mutate_guard.restore_any(HERE)

bad = 0
for name, filename, old, new in mutate_guard.slice_of(MUT):
    path = os.path.join(HERE, filename)
    base = open(path, encoding="utf-8").read()
    if old not in base:
        print("PATCH_FAILED %s" % name)
        bad += 1
        continue
    with mutate_guard.mutation(path, base.replace(old, new, 1)):
        code, fails = run()
    killed = code != 0
    print("%-9s %-30s %s" % ("KILLED" if killed else "SURVIVED", name,
                             ("| " + "; ".join(f[:60] for f in fails[:2])) if killed
                             else "<-- 이 가드를 지키는 시나리오가 없다"))
    if not killed:
        bad += 1

code, _ = run()
print("\n복원 후: %s" % ("통과" if code == 0 else "실패 - 복원되지 않았습니다"))
sys.exit(1 if bad or code else 0)
