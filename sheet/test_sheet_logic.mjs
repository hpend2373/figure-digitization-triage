/* Tests for the sheet logic. Each case here is a defect the second audit
 * found, or a property that audit confirmed working and must not regress.
 * Run: node test_sheet_logic.mjs
 */
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
const L = createRequire(import.meta.url)('./sheet_logic.js');

let ran = 0, failed = 0;
function test(name, fn) {
  ran++;
  try { fn(); } catch (e) { failed++; console.log('FAIL  ' + name + '\n      ' + e.message); return; }
  console.log('ok    ' + name);
}

const row = (id, fp, extra) => Object.assign(
  { Draft_ID: id, Source_Document_ID: 'DOC', Source_File: 'f.pdf', Page: '4',
    Figure_Number: 'FIG1', Crop_Quality_Status: 'ACCEPTABLE',
    Row_Fingerprint: fp, Count_Blocked: '0' }, extra || {});

/* ---- W11: values the browser flags but the old export shipped anyway ---- */
test('음수는 저장되지 않는다', () => {
  assert.equal(L.validatePanelCount('-1').ok, false);
});
test('상한을 넘는 값은 저장되지 않는다', () => {
  assert.equal(L.validatePanelCount('41').ok, false);
});
test('소수는 저장되지 않는다', () => {
  assert.equal(L.validatePanelCount('1.5').ok, false);
});
test('공백만 있는 입력은 미검토로 남는다', () => {
  const v = L.validatePanelCount('   ');
  assert.equal(v.ok, true);
  assert.equal(v.value, null);
});
test('0은 유효하다 - 축 영역이 없다는 뜻', () => {
  assert.deepEqual(L.validatePanelCount('0'), { ok: true, value: '0', error: '' });
});
test('상한값 40은 통과한다', () => {
  assert.equal(L.validatePanelCount('40').value, '40');
});

/* ---- 빈칸은 0이 아니다 (W6에서 통과한 성질, 회귀 금지) ---- */
test('미검토 행은 CSV에서 빈칸으로 남고 0이 되지 않는다', () => {
  const rows = [row('A', 'fp-a')];
  const csv = L.buildCsv(rows, {}, 'B1');
  const line = csv.split('\n')[1];
  assert.match(line, /"","NOT_REVIEWED"/);
  assert.doesNotMatch(line, /"0","NOT_REVIEWED"/);
});
test('입력한 0은 0으로 나가고 미검토와 구별된다', () => {
  const rows = [row('A', 'fp-a')];
  const csv = L.buildCsv(rows, { A: '0' }, 'B1');
  assert.match(csv.split('\n')[1], /"0","ENTERED"/);
});

/* ---- 2단계 요구: 행 순서가 바뀌어도 값이 다른 그림에 붙지 않는다 ---- */
test('행 내용이 바뀌면 과거 값은 복원되지 않는다', () => {
  const store = { A: { v: '3', fp: 'OLD' } };
  const out = L.restoreEntries(store, [row('A', 'NEW')]);
  assert.deepEqual(out.applied, {});
  assert.deepEqual(out.rejected, [{ id: 'A', reason: 'ROW_CHANGED' }]);
});
test('행이 사라지면 값은 버려지고 다른 행으로 새지 않는다', () => {
  const store = { GONE: { v: '3', fp: 'fp-x' } };
  const out = L.restoreEntries(store, [row('A', 'fp-a')]);
  assert.deepEqual(out.applied, {});
  assert.equal(out.rejected[0].reason, 'ROW_GONE');
});
test('행 순서가 뒤집혀도 값은 자기 행에 붙는다', () => {
  const rows = [row('A', 'fp-a'), row('B', 'fp-b')];
  const store = { B: { v: '7', fp: 'fp-b' }, A: { v: '2', fp: 'fp-a' } };
  assert.deepEqual(L.restoreEntries(store, rows).applied, { A: '2', B: '7' });
  assert.deepEqual(L.restoreEntries(store, rows.slice().reverse()).applied,
                   { A: '2', B: '7' });
});
test('저장된 값이 망가져 있어도 복원이 죽지 않는다', () => {
  const out = L.restoreEntries({ A: null, B: 'plain', C: 5 },
                               [row('A', 'fp-a')]);
  assert.deepEqual(out.applied, {});
  assert.equal(out.rejected.length, 3);
});
test('저장소가 비어 있어도 복원이 죽지 않는다', () => {
  assert.deepEqual(L.restoreEntries(null, [row('A', 'fp-a')]).applied, {});
  assert.deepEqual(L.restoreEntries({}, []).rejected, []);
});
test('저장된 값이 유효하지 않으면 화면에 올리지 않는다', () => {
  const out = L.restoreEntries({ A: { v: '-3', fp: 'fp-a' } },
                               [row('A', 'fp-a')]);
  assert.deepEqual(out.applied, {});
  assert.equal(out.rejected[0].reason, 'INVALID_VALUE');
});

/* ---- W7: 크롭이 잘못된 행은 숫자를 받지 않는다 ---- */
test('크롭 결함 행은 값이 있어도 BLOCKED로 나간다', () => {
  const rows = [row('A', 'fp-a', { Count_Blocked: '1', Page: '9' })];
  const cells = L.buildCsv(rows, { A: '4' }, 'B1').split('\n')[1].split(',');
  const at = k => cells[L.CSV_COLUMNS.indexOf(k)];
  assert.equal(at('Observed_Panel_Count'), '""');
  assert.equal(at('Entry_Status'), '"BLOCKED_BAD_CROP"');
});
test('크롭이 정상인 행은 같은 조건에서 값이 나간다 - 위 검사가 통과만 하는 것이 아님', () => {
  const rows = [row('A', 'fp-a', { Count_Blocked: '0', Page: '9' })];
  const cells = L.buildCsv(rows, { A: '4' }, 'B1').split('\n')[1].split(',');
  assert.equal(cells[L.CSV_COLUMNS.indexOf('Observed_Panel_Count')], '"4"');
});

/* ---- 내보내기가 감사 가능해야 한다 ---- */
test('CSV에 지문과 빌드 ID가 실려 나간다', () => {
  assert.ok(L.CSV_COLUMNS.includes('Row_Fingerprint'));
  assert.ok(L.CSV_COLUMNS.includes('Sheet_Build_ID'));
  assert.ok(L.CSV_COLUMNS.includes('Entry_Status'));
  const csv = L.buildCsv([row('A', 'fp-a')], {}, 'BUILD-9');
  assert.match(csv, /"fp-a"/);
  assert.match(csv, /"BUILD-9"/);
});
test('CSV 행 수는 입력 행 수와 같다', () => {
  const rows = [row('A', 'a'), row('B', 'b'), row('C', 'c')];
  assert.equal(L.buildCsv(rows, {}, 'B').split('\n').length, 4);
});
test('큰따옴표가 든 값이 CSV를 깨지 않는다', () => {
  const rows = [row('A', 'a', { Source_File: 'a "quoted" name.pdf' })];
  assert.match(L.buildCsv(rows, {}, 'B'), /"a ""quoted"" name\.pdf"/);
});

/* ---- where the keyboard goes next, and what is actually left ---- */
const seq = [row('a', 'f1'), row('b', 'f2', { Count_Blocked: '1' }),
             row('c', 'f3'), row('d', 'f4', { Count_Blocked: '1' })];

test('Enter는 다음으로 숫자를 넣을 수 있는 행으로 간다', () => {
  assert.equal(L.nextOpenId(seq, 'a'), 'c');
});
test('막힌 행은 멈춰 서는 자리가 아니다', () => {
  assert.equal(L.nextOpenId(seq, null), 'a');
  assert.equal(L.nextOpenId([seq[1], seq[0]], null), 'a');
});
test('끝에서는 처음으로 돌아가지 않는다 - 센 값을 덮어쓰게 된다', () => {
  assert.equal(L.nextOpenId(seq, 'c'), null);
});
test('사라진 행에서 출발하면 아무 데도 가지 않는다', () => {
  assert.equal(L.nextOpenId(seq, 'zzz'), null);
});
test('남은 수는 입력 가능한 행만 센다', () => {
  assert.deepEqual(L.remaining(seq, {}), { open: 2, left: 2, done: 0 });
  assert.deepEqual(L.remaining(seq, { a: '4' }), { open: 2, left: 1, done: 1 });
});
test('막힌 행에 값이 있어도 진행률을 올리지 않는다', () => {
  assert.deepEqual(L.remaining(seq, { b: '3' }), { open: 2, left: 2, done: 0 });
});
test('빈 문자열은 아직 안 한 것으로 센다', () => {
  assert.deepEqual(L.remaining(seq, { a: '' }), { open: 2, left: 2, done: 0 });
});
test('0은 한 것으로 센다 - 빈칸과 다르다', () => {
  assert.deepEqual(L.remaining(seq, { a: '0' }), { open: 2, left: 1, done: 1 });
});

/* ---- 봤지만 셀 수 없음: 빈칸이 감당하던 두 번째 뜻 ---- */
test('이유 없는 "셀 수 없음"은 받지 않는다', () => {
  assert.equal(L.validateUncountable('').ok, false);
  assert.equal(L.validateUncountable('   ').ok, false);
});
test('이유가 있으면 받고, 200자에서 자른다', () => {
  assert.equal(L.validateUncountable(' 인셋이 축인지 모르겠음 ').value,
               '인셋이 축인지 모르겠음');
  assert.equal(L.validateUncountable('가'.repeat(400)).value.length, 200);
});
test('셀 수 없음은 안 본 것과 다른 상태다', () => {
  assert.equal(L.entryStatus(row('a', 'f'), {}, {}), 'NOT_REVIEWED');
  assert.equal(L.entryStatus(row('a', 'f'), {}, { a: '이유' }),
               'SEEN_UNCOUNTABLE');
});
test('숫자가 있으면 숫자가 이긴다', () => {
  assert.equal(L.entryStatus(row('a', 'f'), { a: '3' }, { a: '이유' }),
               'ENTERED');
});
test('막힌 행은 무엇을 붙여도 막힌 행이다', () => {
  assert.equal(L.entryStatus(row('a', 'f', { Count_Blocked: '1' }), {},
                             { a: '이유' }), 'BLOCKED_BAD_CROP');
});
test('CSV가 이유를 함께 내보낸다', () => {
  const line = L.buildCsv([row('a', 'f')], {}, 'B', { a: '스캔이 거침' })
    .split('\n')[1].split(',');
  assert.equal(line[L.CSV_COLUMNS.indexOf('Entry_Status')],
               '"SEEN_UNCOUNTABLE"');
  assert.equal(line[L.CSV_COLUMNS.indexOf('Uncountable_Reason')],
               '"스캔이 거침"');
  assert.equal(line[L.CSV_COLUMNS.indexOf('Observed_Panel_Count')], '""');
});
test('숫자를 넣은 행에는 이유를 내보내지 않는다', () => {
  const line = L.buildCsv([row('a', 'f')], { a: '2' }, 'B', { a: '옛 이유' })
    .split('\n')[1].split(',');
  assert.equal(line[L.CSV_COLUMNS.indexOf('Uncountable_Reason')], '""');
});
test('셀 수 없음으로 정리된 행은 남은 일이 아니다', () => {
  const rs = [row('a', 'f1'), row('b', 'f2')];
  assert.deepEqual(L.remaining(rs, {}, { a: '이유' }),
                   { open: 2, left: 1, done: 1 });
});

/* ---- 2026-09-06 감사: 시트가 그 행에 대해 틀렸다고 말할 자리 ---- */
test('이유 없는 이의는 저장되지 않는다', () => {
  assert.equal(L.validateObjection('').ok, false);
  assert.equal(L.validateObjection('   ').ok, false);
});
test('이유 없는 이의 거절문이 무엇을 적으라는지 말한다', () => {
  assert.ok(L.validateObjection('').error.includes('한 줄'));
});
test('이의 이유도 200자에서 끊긴다', () => {
  assert.equal(L.validateObjection('가'.repeat(500)).value.length, 200);
});
test('열린 행의 이의는 CROP_DISPUTED다', () => {
  assert.equal(L.entryStatus(row('a', 'f'), {}, {}, { a: '본문 문단' }),
               'CROP_DISPUTED');
});
// REVERT: put the objection after ENTERED. 엉뚱한 그림에서 읽은 수가 그대로
// 나갑니다 - 그 수를 지우려고 만든 칸인데.
test('숫자를 넣은 뒤의 이의는 숫자를 이긴다', () => {
  assert.equal(L.entryStatus(row('a', 'f'), { a: '3' }, {}, { a: '머리글' }),
               'CROP_DISPUTED');
});
test('그 행의 숫자는 CSV에 나가지 않는다', () => {
  const line = L.buildCsv([row('a', 'f')], { a: '3' }, 'B', {}, { a: '머리글' })
    .split('\n')[1].split(',');
  assert.equal(line[L.CSV_COLUMNS.indexOf('Observed_Panel_Count')], '""');
  assert.equal(line[L.CSV_COLUMNS.indexOf('Objection_Reason')], '"머리글"');
});
test('막힌 행의 이의는 BLOCK_DISPUTED이고 막힘은 그대로다', () => {
  const b = row('a', 'f', { Count_Blocked: '1' });
  assert.equal(L.entryStatus(b, {}, {}, { a: '그림이 멀쩡히 보임' }),
               'BLOCK_DISPUTED');
  assert.equal(L.entryStatus(b, {}, {}, {}), 'BLOCKED_BAD_CROP');
});
/* REVERT: 확인한 행을 BLOCKED_BAD_CROP으로 내보낸다. 그러면 사람이 눈으로 보고
 * "이 차단 맞다"고 한 행과 아무도 보지 않아 막혀 있는 행이 파일에서 같은 줄이
 * 되고, 다음 사람이 같은 카드를 다시 봅니다. 오늘 그 일이 실제로 났습니다 -
 * 확인할 자리가 없어서 이의 칸에 "잘잡았어."라고 적힌 행이 이의로 기록됐습니다. */
test('확인 표가 아닌 값은 되살아나지 않는다', () => {
  assert.equal(L.validateConfirm(L.CONFIRM_MARK).ok, true);
  assert.equal(L.validateConfirm('아무거나').ok, false);
  assert.equal(L.validateConfirm('').ok, false);
});
test('손댄 저장값은 확인으로 복원되지 않는다', () => {
  const rows = [row('a', 'f', { Count_Blocked: '1' })];
  const got = L.restoreWith({ a: { v: '예', fp: 'f' } }, rows,
                            L.validateConfirm);
  assert.equal(Object.keys(got.applied).length, 0);
  assert.equal(L.entryStatus(rows[0], {}, {}, {}, got.applied),
               'BLOCKED_BAD_CROP');
});
test('막힌 행을 사람이 확인하면 BLOCK_CONFIRMED다', () => {
  const b = row('a', 'f', { Count_Blocked: '1' });
  assert.equal(L.entryStatus(b, {}, {}, {}, { a: true }), 'BLOCK_CONFIRMED');
  assert.equal(L.entryStatus(b, {}, {}, {}, {}), 'BLOCKED_BAD_CROP');
});
test('확인은 이유를 요구하지 않는다', () => {
  const line = L.buildCsv([row('a', 'f', { Count_Blocked: '1' })], {}, 'B', {},
                          {}, { a: true }).split('\n')[1].split(',');
  assert.equal(line[L.CSV_COLUMNS.indexOf('Entry_Status')], '"BLOCK_CONFIRMED"');
  assert.equal(line[L.CSV_COLUMNS.indexOf('Objection_Reason')], '""');
  assert.equal(line[L.CSV_COLUMNS.indexOf('Observed_Panel_Count')], '""');
});
test('이의와 확인이 함께 켜지면 글이 있는 이의가 이긴다', () => {
  const b = row('a', 'f', { Count_Blocked: '1' });
  assert.equal(L.entryStatus(b, {}, {}, { a: '그림이 멀쩡히 보임' }, { a: true }),
               'BLOCK_DISPUTED');
});
test('막히지 않은 행은 확인이 켜져 있어도 확인이 아니다', () => {
  const open = row('a', 'f');
  assert.equal(L.entryStatus(open, { a: '2' }, {}, {}, { a: true }), 'ENTERED');
  assert.equal(L.entryStatus(open, {}, {}, {}, { a: true }), 'NOT_REVIEWED');
});

test('막힌 행의 이의도 이유와 함께 나간다', () => {
  const line = L.buildCsv([row('a', 'f', { Count_Blocked: '1' })], {}, 'B', {},
                          { a: '중복이 아님' }).split('\n')[1].split(',');
  assert.equal(line[L.CSV_COLUMNS.indexOf('Entry_Status')], '"BLOCK_DISPUTED"');
  assert.equal(line[L.CSV_COLUMNS.indexOf('Objection_Reason')], '"중복이 아님"');
  assert.equal(line[L.CSV_COLUMNS.indexOf('Observed_Panel_Count')], '""');
});
test('이의가 없는 행의 이의 칸은 빈칸이다', () => {
  const line = L.buildCsv([row('a', 'f')], { a: '2' }, 'B', {}, {})
    .split('\n')[1].split(',');
  assert.equal(line[L.CSV_COLUMNS.indexOf('Objection_Reason')], '""');
});
test('이의와 셀 수 없음은 서로 다른 칸으로 나간다', () => {
  const line = L.buildCsv([row('a', 'f')], {}, 'B', { a: '거침' }, { a: '머리글' })
    .split('\n')[1].split(',');
  assert.equal(line[L.CSV_COLUMNS.indexOf('Entry_Status')], '"CROP_DISPUTED"');
  assert.equal(line[L.CSV_COLUMNS.indexOf('Uncountable_Reason')], '""');
  assert.equal(line[L.CSV_COLUMNS.indexOf('Objection_Reason')], '"머리글"');
});
test('이의로 정리된 행은 남은 일이 아니다', () => {
  const rs = [row('a', 'f1'), row('b', 'f2')];
  assert.deepEqual(L.remaining(rs, {}, {}, { a: '본문' }),
                   { open: 2, left: 1, done: 1 });
});
test('막힌 행의 이의는 남은 일 셈을 건드리지 않는다', () => {
  const rs = [row('a', 'f1', { Count_Blocked: '1' }), row('b', 'f2')];
  assert.deepEqual(L.remaining(rs, {}, {}, { a: '차단이 틀림' }),
                   { open: 1, left: 1, done: 0 });
});
test('그림이 바뀐 행의 이의는 되살아나지 않는다', () => {
  const out = L.restoreWith({ a: { v: '본문', fp: '옛지문' } },
                            [row('a', '새지문')], L.validateObjection);
  assert.deepEqual(out.applied, {});
  assert.equal(out.rejected[0].reason, 'ROW_CHANGED');
});

/* ---- 체크 칸이 자기를 누른 사람과 싸우지 않는다 ---- */
// REVERT: derive the box from the stored reason alone. 누르는 순간 체크가
// 풀리고 이유 칸이 사라져, "한 줄 적어 주세요"라는 말만 남고 적을 자리가
// 없어집니다 - 사람이 화면에서 본 그대로입니다.
test('방금 눌렀고 이유가 아직 없으면 켜진 채로 이유 칸이 보인다', () => {
  assert.deepEqual(L.boxState(undefined, true),
                   { checked: true, reasonVisible: true, settled: false });
});
test('저장된 이유가 있으면 켜져 있고 이유 칸이 보인다', () => {
  assert.deepEqual(L.boxState('본문 문단', false),
                   { checked: true, reasonVisible: true, settled: true });
});
test('누르지도 않고 저장된 것도 없으면 꺼져 있고 이유 칸은 숨는다', () => {
  assert.deepEqual(L.boxState('', false),
                   { checked: false, reasonVisible: false, settled: false });
});
test('이유 없이 눌러만 둔 것은 정리된 답이 아니다', () => {
  assert.equal(L.boxState('', true).settled, false);
  assert.equal(L.boxState('적었음', true).settled, true);
});

/* ---- 내려받은 CSV를 다른 빌드로 다시 들여온다 ---- */
const _line = (id, fp, count, status, why, obj) =>
  ['"' + id + '"', '"D"', '"f.pdf"', '"3"', '"FIG1"', '"ACCEPTABLE"',
   '"' + fp + '"', '"' + count + '"', '"' + status + '"', '"' + (why || '') + '"',
   '"' + (obj || '') + '"', '"old-build"'].join(',');
const _csv = (...lines) => L.CSV_COLUMNS.join(',') + '\n' + lines.join('\n') + '\n';
const _rows = [row('a', 'f1'), row('b', 'f2'),
               row('c', 'f3', { Count_Blocked: '1' })];

test('세어 둔 값이 다른 빌드로 들어온다', () => {
  const g = L.adoptCsv(_csv(_line('a', 'f1', '4', 'ENTERED')), _rows);
  assert.equal(g.ok, true);
  assert.deepEqual(g.counts, { a: '4' });
  assert.equal(g.taken, 1);
});
// REVERT: adopt without the fingerprint check. 초안이 바뀐 뒤의 옛 CSV가 지금은
// 다른 그림인 행에 값을 얹습니다 - 빌드를 나눈 이유가 바로 그것입니다.
test('그림이 바뀐 행의 값은 들어오지 않는다', () => {
  const g = L.adoptCsv(_csv(_line('a', '옛지문', '4', 'ENTERED')), _rows);
  assert.deepEqual(g.counts, {});
  assert.equal(g.rejected[0].reason, 'ROW_CHANGED');
});
test('이 시트에 없는 행은 들어오지 않는다', () => {
  const g = L.adoptCsv(_csv(_line('z', 'fz', '4', 'ENTERED')), _rows);
  assert.equal(g.rejected[0].reason, 'ROW_GONE');
});
test('저장할 수 없는 값은 들어오지 않는다', () => {
  const g = L.adoptCsv(_csv(_line('a', 'f1', '99', 'ENTERED')), _rows);
  assert.deepEqual(g.counts, {});
  assert.equal(g.rejected[0].reason, 'INVALID_VALUE');
});
test('셀 수 없음과 이의도 각자의 칸으로 들어온다', () => {
  const g = L.adoptCsv(_csv(_line('a', 'f1', '', 'SEEN_UNCOUNTABLE', '스캔이 거침'),
                            _line('b', 'f2', '', 'CROP_DISPUTED', '', '본문 문단'),
                            _line('c', 'f3', '', 'BLOCK_DISPUTED', '', '멀쩡히 보임')),
                       _rows);
  assert.deepEqual(g.uncountable, { a: '스캔이 거침' });
  assert.deepEqual(g.objection, { b: '본문 문단', c: '멀쩡히 보임' });
});
test('이유 없는 이의는 들여올 때도 거절된다', () => {
  const g = L.adoptCsv(_csv(_line('a', 'f1', '', 'CROP_DISPUTED')), _rows);
  assert.deepEqual(g.objection, {});
  assert.equal(g.rejected[0].reason, 'INVALID_VALUE');
});
// REVERT: count these as rejections. 사람이 고칠 것이 있는 줄 알고 CSV를
// 들여다보는데, 거기에는 아무 답도 없습니다.
test('막힌 행과 미검토 행은 들여올 것도 거절할 것도 없다', () => {
  const g = L.adoptCsv(_csv(_line('c', 'f3', '', 'BLOCKED_BAD_CROP'),
                            _line('a', 'f1', '', 'NOT_REVIEWED')), _rows);
  assert.equal(g.taken, 0);
  assert.deepEqual(g.rejected, []);
});
// REVERT: adopt the value anyway. 옛 빌드에서 셀 수 있던 행이 지금은 범위
// 밖인데 값이 얹히고, 막은 판정이 조용히 뒤집힙니다.
test('지금 막혀 있는 행에는 값을 들여오지 않는다', () => {
  const g = L.adoptCsv(_csv(_line('c', 'f3', '4', 'ENTERED')), _rows);
  assert.deepEqual(g.counts, {});
  assert.equal(g.rejected[0].reason, 'ROW_BLOCKED_NOW');
});
test('  셀 수 없음도 마찬가지다', () => {
  const g = L.adoptCsv(_csv(_line('c', 'f3', '', 'SEEN_UNCOUNTABLE', '거침')), _rows);
  assert.deepEqual(g.uncountable, {});
  assert.equal(g.rejected[0].reason, 'ROW_BLOCKED_NOW');
});
test('  그러나 막힌 행의 이의는 그 행의 답이므로 들어온다', () => {
  const g = L.adoptCsv(_csv(_line('c', 'f3', '', 'BLOCK_DISPUTED', '', '멀쩡히 보임')), _rows);
  assert.deepEqual(g.objection, { c: '멀쩡히 보임' });
  assert.deepEqual(g.rejected, []);
});
test('시트가 내려준 파일이 아니면 무엇이 없는지 말한다', () => {
  const g = L.adoptCsv('a,b\n1,2\n', _rows);
  assert.equal(g.ok, false);
  assert.ok(g.missing.indexOf('Row_Fingerprint') >= 0);
  assert.equal(g.taken, 0);
});
test('쉼표와 따옴표가 든 이유도 그대로 들어온다', () => {
  const why = '표본, 그리고 ""원그래프""';
  const g = L.adoptCsv(_csv(_line('a', 'f1', '', 'SEEN_UNCOUNTABLE', why)), _rows);
  assert.deepEqual(g.uncountable, { a: '표본, 그리고 "원그래프"' });
});
test('BOM이 붙은 파일도 읽는다', () => {
  const g = L.adoptCsv('\ufeff' + _csv(_line('a', 'f1', '4', 'ENTERED')), _rows);
  assert.deepEqual(g.counts, { a: '4' });
});

console.log('\n' + (ran - failed) + '/' + ran + ' passed');
process.exit(failed ? 1 : 0);
