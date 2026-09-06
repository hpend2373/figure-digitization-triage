import os, subprocess, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import mutate_guard                                       # noqa: E402
SRC = os.path.join(HERE, 'sheet_logic.js')
base = open(SRC, encoding='utf-8').read()
MUT = [
 ("M1 정수 검사 제거", "if (!/^[0-9]+$/.test(s)) {", "if (false) {"),
 ("M2 상한 검사 제거", "if (n > PANEL_MAX) {", "if (false) {"),
 ("M3 지문 대조 제거", "if (e.fp !== row.Row_Fingerprint) {", "if (false) {"),
 ("M4 행 존재 검사 제거", "if (!row) { rejected.push({ id: id, reason: 'ROW_GONE' }); continue; }",
                          "if (!row) { row = rows[0]; }"),
 ("M5 크롭 차단 제거",
  "  if (row.Count_Blocked === '1')\n    return disputed ? 'BLOCK_DISPUTED' : 'BLOCKED_BAD_CROP';",
  ""),
 ("M6 미검토를 0으로", "var count = status === 'ENTERED' ? applied[r.Draft_ID] : '';",
                       "var count = status === 'ENTERED' ? applied[r.Draft_ID] : '0';"),
 ("M7 저장값 재검증 제거", "if (!v.ok) { rejected.push({ id: id, reason: 'INVALID_VALUE' }); continue; }", ""),
 ("M8 이유 없는 이의 허용",
  "  if (s === '') {\n    return { ok: false, value: '',\n             error: '무엇이 이상한지 한 줄 적어 주세요",
  "  if (false) {\n    return { ok: false, value: '',\n             error: '무엇이 이상한지 한 줄 적어 주세요"),
 ("M9 이의보다 숫자가 이김", "  if (disputed) return 'CROP_DISPUTED';",
  "  if (false) return 'CROP_DISPUTED';"),
 ("M10 막힌 행의 이의를 버림",
  "return disputed ? 'BLOCK_DISPUTED' : 'BLOCKED_BAD_CROP';",
  "return 'BLOCKED_BAD_CROP';"),
 ("M11 체크 칸을 저장된 것만 보고 다시 그림",
  "  var open = on || !!ticked;", "  var open = on;"),
 ("M12 이의 붙은 행이 남은 일로 셈해짐",
  "        && !(uncountable || {})[id] && !(objection || {})[id]) left++;",
  "        && !(uncountable || {})[id]) left++;"),
]
mutate_guard.restore_any(HERE)

bad = 0
for name, old, new in MUT:
    if old not in base:
        print('PATCH_FAILED %s' % name); bad += 1; continue
    with mutate_guard.mutation(SRC, base.replace(old, new, 1)):
        r = subprocess.run(['node', 'test_sheet_logic.mjs'],
                           capture_output=True, text=True, cwd=HERE)
    killed = r.returncode != 0
    fails = [l.split('FAIL  ')[1] for l in r.stdout.splitlines() if l.startswith('FAIL')]
    print('%-10s %-22s %s' % ('KILLED' if killed else 'SURVIVED', name,
                              ('| ' + '; '.join(fails[:3])) if killed else '<-- 이 가드는 시나리오가 없다'))
    if not killed: bad += 1
r = subprocess.run(['node', 'test_sheet_logic.mjs'], capture_output=True,
                   text=True, cwd=HERE)
print('\n복원 후:', r.stdout.strip().splitlines()[-1])
sys.exit(1 if bad else 0)
