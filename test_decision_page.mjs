/* 처분 판정 페이지의 결정들에 대한 시나리오.
 *
 *     node test_decision_page.mjs
 */
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
const L = createRequire(import.meta.url)('./decision_page.js');

let pass = 0; const fails = [];
function test(name, fn) {
  try { fn(); console.log('ok    ' + name); pass++; }
  catch (e) { console.log('FAIL  ' + name + '  <- ' + e.message); fails.push(name); }
}

function state(over) {
  return Object.assign({ kind: 'UNCOUNTABLE', choice: 'RECROP', which: '',
                         note: '', seen: true, draft: 'd1' }, over || {});
}

test('다 갖춘 답은 한 줄이 된다', () => {
  const got = L.decisionOf('d1', state());
  assert.equal(got.ready, true);
  assert.equal(got.row.Decision, 'RECROP');
  assert.equal(got.row.Seen_By_Person, '1');
});

/* REVERT: 그림을 보았다고 누르지 않아도 답으로 친다. 고르기만 한 줄이 "내가
 * 이 그림을 보았다"는 진술로 나갑니다 - 이 페이지가 있는 이유가 사라집니다. */
test('그림을 봤다고 누르지 않으면 답이 아니다', () => {
  const got = L.decisionOf('d1', state({ seen: false }));
  assert.equal(got.ready, false);
  assert.match(got.why, /직접 보셨다/);
  assert.equal(got.row, null);
});

/* REVERT: 물음마다 받을 답을 가르지 않는다. "셀 수 없다"에 DATA가, 어긋난
 * 캡션에 COUNTABLE이 답으로 들어가고, 그것을 읽는 쪽은 무엇을 물었는지
 * 모르는 채 처분만 받습니다. */
test('물음에 없는 답은 이름을 대며 거절한다', () => {
  const got = L.decisionOf('d1', state({ kind: 'UNCOUNTABLE', choice: 'DATA' }));
  assert.equal(got.ready, false);
  assert.match(got.why, /DATA/);
});
test('물음마다 받는 답이 다르다', () => {
  assert.equal(L.decisionOf('d1', state({ kind: 'MIXED', choice: 'DATA' })).ready, true);
  assert.equal(L.decisionOf('d1', state({ kind: 'CROP_DISPUTE', choice: 'COUNTABLE' })).ready, false);
});
test('무엇을 묻는지 모르는 줄은 답이 되지 않는다', () => {
  const got = L.decisionOf('d1', state({ kind: '' }));
  assert.equal(got.ready, false);
  assert.match(got.why, /모르는/);
});
/* REVERT: 빈칸을 "쓸 수 없는 답"으로 흘려보낸다. 어휘 검사가 어차피 막지만,
 * 아직 고르지 않은 사람에게 "이 물음에 쓸 수 없는 답입니다: "라고 말하게
 * 됩니다 - 자기가 무엇을 잘못했는지 알 수 없는 말입니다. 이 가드가 지키는
 * 것은 답의 모양이 아니라 사람에게 하는 말입니다. */
test('고르지 않으면 아직 고르지 않았다고 말한다', () => {
  const got = L.decisionOf('d1', state({ choice: '' }));
  assert.equal(got.ready, false);
  assert.match(got.why, /아직 고르지 않았습니다/);
});

/* REVERT: 어느 패널인지 묻지 않는다. "일부 패널만 데이터"라는 답에서 어느
 * 패널인지 빠지면, 다음 사람은 그 그림 앞에서 처음부터 다시 봅니다. */
test('일부 패널만이라면 어느 패널인지 적어야 한다', () => {
  const got = L.decisionOf('d1', state({ kind: 'MIXED', choice: 'PARTIAL' }));
  assert.equal(got.ready, false);
  assert.match(got.why, /어느 패널/);
  const ok = L.decisionOf('d1', state({ kind: 'MIXED', choice: 'PARTIAL', which: 'a, c' }));
  assert.equal(ok.ready, true);
  assert.equal(ok.row.Which_Panels, 'a, c');
});
test('패널을 묻지 않는 답에는 패널 칸을 싣지 않는다', () => {
  const got = L.decisionOf('d1', state({ kind: 'MIXED', choice: 'DATA', which: 'a' }));
  assert.equal(got.row.Which_Panels, '');
});

test('아직 못 정하겠다도 답이다', () => {
  const got = L.decisionOf('d1', state({ choice: 'HOLD' }));
  assert.equal(got.ready, true);
  assert.equal(got.row.Decision, 'HOLD');
});
test('그래도 봤다는 표시는 HOLD에도 필요하다', () => {
  assert.equal(L.decisionOf('d1', state({ choice: 'HOLD', seen: false })).ready, false);
});

/* REVERT: 열쇠를 그대로 `Draft_ID`로 내보낸다. 화면이 상태를 담는 열쇠와
 * 파이프라인이 아는 이름이 같으리라는 보장이 없습니다. */
test('나가는 이름은 상태가 들고 있는 Draft_ID다', () => {
  assert.equal(L.decisionOf('KEY', state({ draft: 'd9' })).row.Draft_ID, 'd9');
});

test('CSV는 답이 된 줄만 싣는다', () => {
  const csv = L.buildCsv(['a', 'b'],
                         { a: state({ draft: 'a' }),
                           b: state({ draft: 'b', seen: false }) }).split('\n');
  assert.equal(csv.length, 2);
  assert.match(csv[1], /^"a"/);
});
/* REVERT: `Object.keys(states)`를 목록으로 쓴다. 화면이 이름을 한 번 잘못
 * 읽으면 그 이름이 그대로 `Draft_ID`가 되어 나갑니다. */
test('이 페이지가 모르는 이름은 줄이 되지 않는다', () => {
  const csv = L.buildCsv(['a'], { a: state({ draft: 'a' }),
                                  '어디서 온 이름': state({ draft: 'x' }) }).split('\n');
  assert.equal(csv.length, 2);
});
test('따옴표가 든 메모도 그대로 나간다', () => {
  const csv = L.buildCsv(['a'], { a: state({ draft: 'a', note: '패널 "b"만' }) });
  assert.ok(csv.indexOf('""b""') >= 0, csv);
});

test('남은 일은 답이 안 된 그림을 센다', () => {
  assert.equal(L.remaining(['a', 'b', 'c'],
                           { a: state(), b: state({ seen: false }) }), 2);
});
test('보류는 남은 일이 아니라 따로 센다', () => {
  const st = { a: state({ choice: 'HOLD' }), b: state() };
  assert.equal(L.remaining(['a', 'b'], st), 0);
  assert.equal(L.held(['a', 'b'], st), 1);
});

console.log('');
console.log(pass + '/' + (pass + fails.length) + ' passed');
if (fails.length) { console.log('FAILED: ' + fails.join(', ')); process.exit(1); }
