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

console.log('\n' + (ran - failed) + '/' + ran + ' passed');
process.exit(failed ? 1 : 0);
