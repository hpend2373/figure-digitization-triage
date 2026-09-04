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
 ("M5 크롭 차단 제거", "if (row.Count_Blocked === '1') return 'BLOCKED_BAD_CROP';", ""),
 ("M6 미검토를 0으로", "var count = status === 'ENTERED' ? applied[r.Draft_ID] : '';",
                       "var count = status === 'ENTERED' ? applied[r.Draft_ID] : '0';"),
 ("M7 저장값 재검증 제거", "if (!v.ok) { rejected.push({ id: id, reason: 'INVALID_VALUE' }); continue; }", ""),
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
