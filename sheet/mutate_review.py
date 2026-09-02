# -*- coding: utf-8 -*-
"""판정 페이지의 가드를 하나씩 되돌리고, 어떤 시나리오가 죽는지 본다.

    python3 mutate_review.py
"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SUITE = ["python3", os.path.join(HERE, "test_review_sheet.py")]

MUT = [
    ("M1 에이전트 제안을 미리 눌러 둠", "review_sheet.py",
     "\"style='--c:%s'>%s <kbd>%s</kbd></button>\"",
     "\"style='--c:%s' aria-pressed='true'>%s <kbd>%s</kbd></button>\""),
    ("M2 에이전트 제안을 펼쳐 둠", "review_sheet.py",
     "<div class='agent' hidden>", "<div class='agent'>"),
    ("M3 지문에서 상자를 뺌", "review_sheet.py",
     '''    raw = "|".join([queue_row["Draft_ID"], queue_row.get("Crop_SHA256", ""),
                    queue_row.get("Proposal_Figure_BBox", ""),
                    queue_row.get("PDF_BBox", ""), queue_row.get("Raster_BBox", "")])''',
     '''    raw = "|".join([queue_row["Draft_ID"], queue_row.get("Crop_SHA256", "")])'''),
    ("M4 지문에서 크롭을 뺌", "review_sheet.py",
     'queue_row.get("Crop_SHA256", ""),\n                    queue_row.get("Proposal_Figure_BBox", ""),',
     'queue_row.get("Proposal_Figure_BBox", ""),'),
    ("M5 인테이크와 다른 공식으로 자름", "review_sheet.py",
     "    got = roundtrip.cut(Image.open(raster), dict(row, Figure_BBox=box_text))",
     "    _p = roundtrip.PAD\n    roundtrip.PAD = 0\n"
     "    got = roundtrip.cut(Image.open(raster), dict(row, Figure_BBox=box_text))\n"
     "    roundtrip.PAD = _p"),
    ("M6 페이지에 상자를 안 그림", "review_sheet.py",
     "        draw.rectangle([box[0] * sx, box[1] * sy, box[2] * sx, box[3] * sy],",
     "        continue\n        draw.rectangle([box[0] * sx, box[1] * sy, box[2] * sx, box[3] * sy],"),
    ("M7 지문 대조 제거", "review_sheet.py",
     "if (!store[id] || store[id].fp !== card.dataset.fp)", "if (false)"),
    ("M8 모르는 선택 값 허용", "review_sheet.py",
     "else if (VALID.indexOf(store[id].choice) < 0) { delete store[id]; dropped++; }", ""),
    ("M9 저장소 쓰기 탐지 제거", "review_sheet.py",
     "  window.localStorage.setItem(probe, '1');", ""),
    ("M10 고르지 않은 행도 값을 내보냄", "review_sheet.py",
     "q['Human_Choice'] = kept ? kept.choice : '';",
     "q['Human_Choice'] = kept ? kept.choice : q['Agent_Choice'];"),
    ("M11 merge가 크롭 digest를 안 봄", "review_packet.py",
     '    if queue_row.get("Crop_SHA256") and queue_row["Crop_SHA256"] != crop_sha:',
     "    if False:"),
    ("M12 merge가 고른 상자를 안 봄", "review_packet.py",
     "    if was != now:", "    if False:"),
    ("M13 고르지 않은 상자까지 대조", "review_packet.py",
     "    column = CHOICE_BOX.get(choice)",
     "    for _c in CHOICE_BOX.values():\n"
     "        if queue_row.get(_c, '') != (region_row or {}).get(_c, ''):\n"
     "            return '어느 상자든 바뀜'\n"
     "    column = CHOICE_BOX.get(choice)"),
    ("M14 BLOCKED도 상자를 지목한 것으로", "review_packet.py",
     "    if column is None:                     # BLOCKED names no box\n        return \"\"",
     "    if column is None:\n        column = 'PDF_BBox'"),
    ("M15 merge가 stale을 안 부름", "review_packet.py",
     "        why = stale(q, reg, now)", "        why = ''"),
]


def run():
    r = subprocess.run(SUITE, capture_output=True, text=True, cwd=HERE)
    fails = [l.split("FAIL", 1)[1].strip() for l in r.stdout.splitlines()
             if l.strip().startswith("FAIL")]
    return r.returncode, fails


bad = 0
for name, filename, old, new in MUT:
    path = os.path.join(HERE, filename)
    base = open(path, encoding="utf-8").read()
    if old not in base:
        print("PATCH_FAILED %s" % name)
        bad += 1
        continue
    try:
        open(path, "w", encoding="utf-8").write(base.replace(old, new, 1))
        code, fails = run()
    finally:
        open(path, "w", encoding="utf-8").write(base)
    killed = code != 0
    print("%-9s %-30s %s" % ("KILLED" if killed else "SURVIVED", name,
                             ("| " + "; ".join(f[:56] for f in fails[:2])) if killed
                             else "<-- 이 가드를 지키는 시나리오가 없다"))
    if not killed:
        bad += 1

code, _ = run()
print("\n복원 후: %s" % ("통과" if code == 0 else "실패 - 복원되지 않았습니다"))
sys.exit(1 if bad or code else 0)
