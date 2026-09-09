/* 판정 페이지의 결정들에 대한 시나리오.
 *
 *     node test_errorbar_page.mjs
 */
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
const L = createRequire(import.meta.url)('./errorbar_page.js');

let pass = 0; const fails = [];
function test(name, fn) {
  try { fn(); console.log('ok    ' + name); pass++; }
  catch (e) { console.log('FAIL  ' + name + '  <- ' + e.message); fails.push(name); }
}

const QUOTE = 'Values are means ± SE.';
function state(over) {
  return Object.assign({ code: 'SE', quote: QUOTE, page: '6',
                         verified: true, note: '' }, over || {});
}

test('다 갖춘 답은 한 줄이 된다', () => {
  const got = L.answerOf('D', state());
  assert.equal(got.ready, true);
  assert.equal(got.row.Dispersion_Type, 'SE');
  assert.equal(got.row.Errorbar_Definition_Source, QUOTE);
  assert.equal(got.row.Verified_In_Source, '1');
});

/* REVERT: 확인 없이도 답으로 친다. 고르기만 한 줄이 "내가 원문에서 보았다"는
 * 진술로 나가고, 관문은 그 진술을 믿습니다 - 이 페이지가 있는 이유가 사라집니다. */
test('사람이 확인을 누르지 않으면 답이 아니다', () => {
  const got = L.answerOf('D', state({ verified: false }));
  assert.equal(got.ready, false);
  assert.match(got.why, /직접 보셨다/);
  assert.equal(got.row, null);
});
test('확인만 누르고 종류를 안 고르면 답이 아니다', () => {
  assert.equal(L.answerOf('D', state({ code: '' })).ready, false);
});
test('종류를 골랐어도 인용문이 없으면 답이 아니다', () => {
  const got = L.answerOf('D', state({ quote: '' }));
  assert.equal(got.ready, false);
  assert.match(got.why, /문장/);
});
test('NO_ERRORBAR는 인용문을 요구하지 않는다', () => {
  const got = L.answerOf('D', state({ code: 'NO_ERRORBAR', quote: '', page: '' }));
  assert.equal(got.ready, true);
  assert.equal(got.row.Errorbar_Definition_Source, '');
});
test('처분 셋도 인용문을 요구하지 않는다', () => {
  for (const c of L.DISPOSITIONS) {
    assert.equal(L.answerOf('D', state({ code: c, quote: '', page: '' })).ready,
                 true, c);
  }
});
test('그래도 확인은 처분에도 필요하다', () => {
  assert.equal(L.answerOf('D', state({ code: 'HOLD', quote: '', page: '',
                                       verified: false })).ready, false);
});
test('모르는 종류는 이름을 대며 거절한다', () => {
  const got = L.answerOf('D', state({ code: 'STDEV' }));
  assert.equal(got.ready, false);
  assert.match(got.why, /STDEV/);
});
test('인용문을 받지 않는 답에는 인용문도 쪽도 싣지 않는다', () => {
  const got = L.answerOf('D', state({ code: 'DROP', quote: QUOTE, page: '6' }));
  assert.equal(got.row.Errorbar_Definition_Source, '');
  assert.equal(got.row.Found_On_Page, '');
});
test('CSV는 답이 된 줄만 싣는다', () => {
  const csv = L.buildCsv(['A', 'B', 'C'],
                         { A: state(), B: state({ verified: false }),
                           C: state({ code: '' }) }).split('\n');
  assert.equal(csv.length, 2);
  assert.match(csv[1], /^"A"/);
});
test('CSV 열은 관문이 요구하는 이름을 들고 있다', () => {
  for (const c of ['Source_Document_ID', 'Dispersion_Type',
                   'Errorbar_Definition_Source', 'Verified_In_Source']) {
    assert.ok(L.CSV_COLUMNS.indexOf(c) >= 0, c);
  }
});
test('따옴표가 든 문장도 그대로 나간다', () => {
  const q = 'Standard "deviations" are shown.';
  const csv = L.buildCsv(['A'], { A: state({ code: 'SD', quote: q }) }).split('\n')[1];
  assert.ok(csv.indexOf('""deviations""') >= 0, csv);
});
test('남은 일은 답이 안 된 문서를 센다', () => {
  assert.equal(L.remaining(['A', 'B', 'C'],
                           { A: state(), B: state({ verified: false }) }), 2);
});

/* REVERT: `Object.keys(states)`를 문서 목록으로 쓴다. 화면이 이름을 한 번 잘못
 * 읽으면 - 실제로 라디오의 `data-quote`를 문서 이름으로 읽은 적이 있습니다 -
 * 인용문이 `Source_Document_ID`가 되어 답 CSV로 나갑니다. 관문은 그런 문서가
 * 없다고만 하고, 그 이름이 어디서 왔는지는 화면에도 파일에도 남지 않습니다. */
test('이 페이지가 모르는 이름은 줄이 되지 않는다', () => {
  const csv = L.buildCsv(['A'],
                         { A: state(), '오차 막대는 SD입니다': state() })
    .split('\n');
  assert.equal(csv.length, 2);
  assert.match(csv[1], /^"A"/);
});

/* REVERT: 열쇠를 그대로 `Source_Document_ID`로 내보낸다. 한 논문을 그림마다
 * 따로 물으면 열쇠가 "논문::그림"이 되고, 그 열쇠가 문서 이름 자리로 나가
 * 관문에서 "그런 문서가 없다"가 됩니다. */
test('그림마다 물을 때도 나가는 이름은 논문 이름이다', () => {
  const got = L.answerOf('D::FIG3', state({ doc: 'D', figure: 'FIG3' }));
  assert.equal(got.row.Source_Document_ID, 'D');
  assert.equal(got.row.Figure_Number, 'FIG3');
});
test('논문 단위로 답한 줄의 그림 칸은 비어 있다', () => {
  assert.equal(L.answerOf('D', state()).row.Figure_Number, '');
});

console.log('');
console.log(pass + '/' + (pass + fails.length) + ' passed');
if (fails.length) { console.log('FAILED: ' + fails.join(', ')); process.exit(1); }
