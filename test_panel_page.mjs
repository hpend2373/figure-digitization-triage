/* 패널 페이지의 결정들에 대한 시나리오.
 *
 *     node test_panel_page.mjs
 */
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
const L = createRequire(import.meta.url)('./panel_page.js');

let pass = 0; const fails = [];
function test(name, fn) {
  try { fn(); console.log('ok    ' + name); pass++; }
  catch (e) { console.log('FAIL  ' + name + '  <- ' + e.message); fails.push(name); }
}

function box(over) {
  return Object.assign({ x0: 10, y0: 10, x1: 400, y1: 300, mark: 'BOX', source: 'DRAWN' }, over || {});
}
function state(over) {
  return Object.assign({
    verdict: 'PANELS', seen: true, who: 'RV_1', draft: 'D0001', note: '',
    size: { w: 1000, h: 800 }, declared: 2,
    boxes: [box({ source: 'PROPOSED' }), box({ x0: 500, x1: 900, mark: 'BAR' })] }, over || {});
}

test('상자마다 한 줄이 된다', () => {
  const got = L.panelsOf('D0001', state());
  assert.equal(got.ready, true);
  assert.equal(got.rows.length, 2);
  assert.deepEqual([got.rows[0].Panel_Index, got.rows[1].Panel_Index], [1, 2]);
  assert.equal(got.rows[1].Mark_Type, 'BAR');
  assert.equal(got.rows[1].X1, 900);
});

/* REVERT: 종류를 안 고른 패널도 넘긴다. 그 패널은 리더가 없는 패널이고, 넘기면
 * 계획서가 그것을 읽을 수 있는 패널로 셉니다. */
test('종류를 고르지 않은 패널이 있으면 답이 아니다', () => {
  const got = L.panelsOf('D0001', state({ boxes: [box(), box({ x0: 500, x1: 900, mark: '' })] }));
  assert.equal(got.ready, false);
  assert.match(got.why, /2번 패널.*골라 주세요/);
});
test('받을 수 없는 종류는 이름을 대며 거절한다', () => {
  assert.match(L.panelsOf('D0001', state({ boxes: [box({ mark: 'PIE' })] })).why, /PIE/);
});

/* REVERT: 상자가 그림 밖으로 나가도 받는다. 600 DPI로 옮길 때 그 상자는
 * 아무 데도 떨어지지 않고, 리더는 흰 종이를 읽습니다. */
test('그림 밖으로 나간 상자는 답이 아니다', () => {
  const got = L.panelsOf('D0001', state({ boxes: [box({ x1: 1200 })] }));
  assert.equal(got.ready, false);
  assert.match(got.why, /그림 밖/);
});
/* REVERT: 넓이 없는 상자도 패널로 센다. 아무것도 못 읽는데 패널 수에 들어갑니다. */
test('넓이 없는 상자는 답이 아니다', () => {
  assert.match(L.panelsOf('D0001', state({ boxes: [box({ x1: 12 })] })).why, /넓이/);
});
test('그림의 크기를 모르면 상자를 놓을 수 없다', () => {
  assert.match(L.panelsOf('D0001', state({ size: null })).why, /크기/);
});
test('좌표가 수가 아니면 답이 아니다', () => {
  assert.match(L.panelsOf('D0001', state({ boxes: [box({ x0: 'a' })] })).why, /수가 아닙/);
});

/* REVERT: 패널이 있다면서 상자 없는 답을 받는다. 패널 0개인 그림이
 * NO_PANELS가 아니라 PANELS로 나가고, 다음 단계는 그 그림에서 아무것도 못 찾습니다. */
test('패널이 있다면서 상자가 없으면 답이 아니다', () => {
  assert.match(L.panelsOf('D0001', state({ boxes: [] })).why, /상자가 없습/);
});

/* REVERT: 직접 보았다는 표시 없이도 답으로 친다. 자동 제안을 그대로 넘긴 것과
 * 사람이 본 것이 구별되지 않습니다. */
test('직접 보았다고 누르지 않으면 답이 아니다', () => {
  assert.match(L.panelsOf('D0001', state({ seen: false })).why, /직접 보셨다고/);
});
test('누가 보았는지 없으면 답이 아니다', () => {
  assert.match(L.panelsOf('D0001', state({ who: '  ' })).why, /누가 보았는지/);
});
test('아직 고르지 않은 그림은 답이 아니다', () => {
  assert.match(L.panelsOf('D0001', state({ verdict: '' })).why, /아직 고르지/);
});
test('받을 수 없는 판정은 이름을 대며 거절한다', () => {
  assert.match(L.panelsOf('D0001', state({ verdict: 'MAYBE' })).why, /MAYBE/);
});

/* REVERT: 제안을 그대로 받은 것과 사람이 그은 것을 같은 것으로 적는다. 자동
 * 분할이 얼마나 맞았는지 아무도 셀 수 없습니다. */
test('제안을 받은 상자와 그은 상자를 구별해 적는다', () => {
  const rows = L.panelsOf('D0001', state()).rows;
  assert.equal(rows[0].Region_Source, 'PROPOSED');
  assert.equal(rows[1].Region_Source, 'DRAWN');
});
/* REVERT: 제안된 종류와 사람이 고른 종류를 같은 것으로 적는다. 기계가 낸
 * 종류가 얼마나 맞았는지 아무도 셀 수 없습니다. */
test('제안된 종류와 고른 종류를 구별해 적는다', () => {
  const rows = L.panelsOf('D0001', state({ boxes: [box({ markSource: 'PROPOSED' }), box({ x0: 500, x1: 900 })] })).rows;
  assert.equal(rows[0].Mark_Source, 'PROPOSED');
  assert.equal(rows[1].Mark_Source, 'TYPED');
  assert.match(L.buildCsv(['D0001'], { D0001: state() }).split('\n')[0], /Mark_Source/);
});
test('출처를 모르는 상자는 그은 것으로 적는다', () => {
  assert.equal(L.panelsOf('D0001', state({ boxes: [box({ source: 'x' })] })).rows[0].Region_Source, 'DRAWN');
});
test('전에 센 수와 그은 수를 함께 적는다', () => {
  const r = L.panelsOf('D0001', state()).rows[0];
  assert.equal(r.Declared_Count, '2');
  assert.equal(r.Drawn_Count, '2');
});

/* REVERT: NO_PANELS를 상자 없다고 거절한다. "이 그림엔 읽을 패널이 없다"는
 * 답이고, 그것을 못 내면 22개 그림이 영영 대기열에 남습니다. */
test('패널이 없다는 답은 상자 없이 한 줄이다', () => {
  const got = L.panelsOf('D0001', state({ verdict: 'NO_PANELS', boxes: [] }));
  assert.equal(got.ready, true);
  assert.equal(got.rows.length, 1);
  assert.equal(got.rows[0].Panel_Index, 0);
  assert.equal(got.rows[0].Verdict, 'NO_PANELS');
  assert.equal(got.rows[0].Mark_Type, '');
});
test('보류도 상자 없이 한 줄이고 넘어가지 않는다', () => {
  const got = L.panelsOf('D0001', state({ verdict: 'HOLD' }));
  assert.equal(got.ready, true);
  assert.equal(got.rows[0].Verdict, 'HOLD');
  assert.equal(L.held(['a'], { a: state({ verdict: 'HOLD' }) }), 1);
});

/* REVERT: 화면의 열쇠를 Draft_ID로 내보낸다. 화면이 열쇠에 무언가를 붙여 두면
 * 나가는 이름이 초안의 이름이 아닙니다. */
test('Draft_ID는 상태가 들고 있는 것을 쓴다', () => {
  assert.equal(L.panelsOf('key', state({ draft: 'D0007' })).rows[0].Draft_ID, 'D0007');
});
test('좌표는 정수로 나간다', () => {
  assert.equal(L.panelsOf('D0001', state({ boxes: [box({ x0: 10.6 })] })).rows[0].X0, 11);
});

/* REVERT: 목록이 아니라 상태에 있는 이름을 전부 내보낸다. 브라우저에 남아 있던
 * 다른 묶음의 답이 이 묶음의 답안지에 섞여 나갑니다. */
test('csv는 목록에 있는 그림만 싣는다', () => {
  const csv = L.buildCsv(['D_A'], { D_A: state({ draft: 'D_A' }), D_OLD: state({ draft: 'D_OLD' }) });
  assert.equal(csv.split('\n').length, 3);
  assert.doesNotMatch(csv, /D_OLD/);
});
test('csv는 답이 된 그림만 싣는다', () => {
  const csv = L.buildCsv(['D_A', 'D_B'], { D_A: state({ draft: 'D_A' }), D_B: state({ verdict: '' }) });
  assert.equal(csv.split('\n').length, 3);
  assert.equal(csv.split('\n')[0].split(',')[0], 'Draft_ID');
});
test('따옴표가 든 메모는 csv를 깨뜨리지 않는다', () => {
  assert.match(L.buildCsv(['D_A'], { D_A: state({ draft: 'D_A', note: '축이 "둘"' }) }),
               /"축이 ""둘"""/);
});
test('남은 일과 보류를 따로 센다', () => {
  const st = { a: state({ verdict: 'HOLD' }), b: state({ verdict: '' }), c: state() };
  assert.equal(L.remaining(['a', 'b', 'c'], st), 1);
  assert.equal(L.held(['a', 'b', 'c'], st), 1);
});

console.log('');
console.log(pass + '/' + (pass + fails.length) + ' passed');
if (fails.length) { console.log('FAILED: ' + fails.join(', ')); process.exit(1); }
