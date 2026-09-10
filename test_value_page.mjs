/* 값 검토 페이지의 결정들에 대한 시나리오.
 *
 *     node test_value_page.mjs
 */
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
const L = createRequire(import.meta.url)('./value_page.js');

let pass = 0; const fails = [];
function test(name, fn) {
  try { fn(); console.log('ok    ' + name); pass++; }
  catch (e) { console.log('FAIL  ' + name + '  <- ' + e.message); fails.push(name); }
}

const NEED = ['Marks_Checked', 'Axis_Labels_Checked', 'Calibration_Checked'];
function state(over) {
  return Object.assign({
    decision: 'APPROVED', who: 'RV_1', subject: 'abc123', panel: 'P_GP001',
    note: '', required: NEED,
    checks: { Marks_Checked: true, Axis_Labels_Checked: true,
              Calibration_Checked: true }}, over || {});
}

test('다 갖춘 승인은 한 줄이 된다', () => {
  const got = L.reviewOf('P_GP001', state());
  assert.equal(got.ready, true);
  assert.equal(got.row.Decision, 'APPROVED');
  assert.equal(got.row.Marks_Checked, 'TRUE');
  assert.equal(got.row.Review_Subject_SHA256, 'abc123');
});

/* REVERT: 확인 칸을 보지 않고 승인으로 친다. `Decision`은 "동의한다"이고 확인
 * 칸은 "무엇을 보았는가"입니다 - 서로 다른 주장이고, 하나로 묶으면 보지 않은
 * 것에 동의한 줄이 생깁니다. `finalize_batch`가 그 줄을 되돌려 보내는데,
 * 그때는 사람이 이미 페이지를 떠난 뒤입니다. */
test('확인이 남아 있으면 승인이 아니다', () => {
  const got = L.reviewOf('P_GP001', state({ checks: { Marks_Checked: true } }));
  assert.equal(got.ready, false);
  assert.match(got.why, /Axis_Labels_Checked/);
});
test('무엇이 남았는지 이름을 댄다', () => {
  assert.match(L.reviewOf('P_GP001', state({ checks: {} })).why, /Marks_Checked/);
});

/* REVERT: 거절과 보류에도 확인 칸을 요구한다. 잘못 앉은 표시를 자세히
 * 확인해 달라고 사람을 붙잡아 두는 일입니다. */
test('거절과 보류는 확인 칸을 묻지 않는다', () => {
  assert.equal(L.reviewOf('P_GP001',
    state({ decision: 'REJECTED', checks: {} })).ready, true);
  assert.equal(L.reviewOf('P_GP001',
    state({ decision: 'HOLD', checks: {} })).ready, true);
});
test('거절이 확인하지 않은 것을 확인했다고 적지 않는다', () => {
  const got = L.reviewOf('P_GP001', state({ decision: 'REJECTED', checks: {} }));
  assert.equal(got.row.Marks_Checked, 'FALSE');
});

/* REVERT: 이름 없이도 판정으로 친다. `finalize_batch`는 등록된 사람만 승인할
 * 수 있다고 하고, 이름 없는 줄은 그 확인을 받을 수조차 없습니다. */
test('누가 보았는지 없으면 판정이 아니다', () => {
  const got = L.reviewOf('P_GP001', state({ who: '  ' }));
  assert.equal(got.ready, false);
  assert.match(got.why, /누가 보았는지/);
});

/* REVERT: 실행 지문 없이도 답으로 친다. 그러면 이 답이 어느 추출에 대한
 * 것인지 알 수 없고, 다른 실행의 승인이 이 실행에 상속됩니다. */
test('실행 지문이 없으면 답이 아니다', () => {
  const got = L.reviewOf('P_GP001', state({ subject: '' }));
  assert.equal(got.ready, false);
  assert.match(got.why, /지문/);
});

test('아직 고르지 않은 줄은 답이 아니다', () => {
  assert.match(L.reviewOf('P_GP001', state({ decision: '' })).why, /아직 고르지/);
});
test('받을 수 없는 답은 이름을 대며 거절한다', () => {
  assert.match(L.reviewOf('P_GP001', state({ decision: 'MAYBE' })).why, /MAYBE/);
});
test('묻지 않은 확인은 빈 칸으로 나간다', () => {
  assert.equal(L.reviewOf('P_GP001', state()).row.Identity_Checked, '');
});

/* REVERT: 본 날짜를 브라우저 시계에서 가져온다. 이 프로그램이 아는 것이
 * 아니고, 아는 척하면 나중에 그 날짜가 증거가 됩니다. */
test('본 날짜는 부른 쪽이 준다', () => {
  const csv = L.buildCsv(['P_GP001'], { P_GP001: state() }, '2026-09-10');
  assert.match(csv, /2026-09-10/);
});
/* REVERT: 오늘 날짜를 브라우저에서 가져온다. 이 프로그램이 아는 것이 아니고,
 * 아는 척하면 나중에 그 날짜가 "언제 보았는가"의 증거가 됩니다. */
test('부르는 쪽이 날짜를 주지 않으면 날짜도 없다', () => {
  const csv = L.buildCsv(['P_A'], { P_A: state({ panel: 'P_A' }) }, '');
  assert.equal(csv.split('\n')[1].split(',')[10], '""');
});
/* REVERT: 화면의 열쇠를 그대로 Panel_ID로 내보낸다. 화면이 패널 하나를 두 번
 * 싣거나 이름에 무언가를 붙여 두면, 나가는 이름이 실행의 패널 이름이 아닙니다. */
test('패널 이름은 상태가 들고 있는 것을 쓴다', () => {
  assert.equal(L.reviewOf('key', state({ panel: 'P_GP007' })).row.Panel_ID,
               'P_GP007');
});
/* REVERT: 목록이 아니라 상태에 있는 이름을 전부 내보낸다. 브라우저에 남아
 * 있던 지난 실행의 답이 이 실행의 답안지에 섞여 나갑니다. */
test('csv는 목록에 있는 패널만 싣는다', () => {
  assert.equal(L.buildCsv(['P_A'],
    { P_A: state({ panel: 'P_A' }), P_OLD: state({ panel: 'P_OLD' }) }, '')
    .split('\n').length, 2);
});
test('csv는 답이 된 줄만 싣고 번호를 다시 매긴다', () => {
  const csv = L.buildCsv(['P_A', 'P_B'],
    { P_A: state({ panel: 'P_A' }), P_B: state({ decision: '' }) }, '2026-09-10');
  const lines = csv.split('\n');
  assert.equal(lines.length, 2);
  assert.match(lines[1], /"R001"/);
});
test('따옴표가 든 메모는 csv를 깨뜨리지 않는다', () => {
  assert.match(L.buildCsv(['P_A'],
    { P_A: state({ panel: 'P_A', note: '표시가 "옆"에 앉음' }) }, ''),
    /"표시가 ""옆""에 앉음"/);
});
test('남은 일과 보류를 따로 센다', () => {
  const st = { a: state({ decision: 'HOLD', checks: {} }), b: state({ decision: '' }) };
  assert.equal(L.remaining(['a', 'b'], st), 1);
  assert.equal(L.held(['a', 'b'], st), 1);
});

console.log('');
console.log(pass + '/' + (pass + fails.length) + ' passed');
if (fails.length) { console.log('FAILED: ' + fails.join(', ')); process.exit(1); }
