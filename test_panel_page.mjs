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

/* 화면에서 잰 것을 원본 픽셀로 옮기는 산수. 이것이 렌더러의 문자열 안에 있는
 * 동안에는 아무 시나리오도 보지 않았고, 창이 좁을 때 상자가 어긋난 자리에
 * 저장되는 것을 아무도 몰랐습니다. */
const RECT = { left: 0, top: 0, width: 900, height: 450 };
test('캔버스가 제 크기일 때는 그린 자리가 그대로다', () => {
  const p = L.imagePoint(RECT, { w: 900, h: 450 }, { w: 1800, h: 900 }, 450, 225);
  assert.deepEqual(p, { x: 900, y: 450 });
});
/* REVERT: 잰 크기를 쓰지 않고 캔버스의 좌표계 크기로 나눈다. 창이 좁으면 그림은
 * 줄어도 좌표계는 안 줄어서, 그은 자리와 저장되는 자리가 1.25배 어긋납니다.
 * 좌표는 그림 안이라 관문도 못 잡습니다. */
test('창이 좁아 그림이 줄면 줄어든 크기로 잰다', () => {
  const p = L.imagePoint({ left: 0, top: 0, width: 720, height: 360 },
                         { w: 900, h: 450 }, { w: 1800, h: 900 }, 360, 180);
  assert.deepEqual(p, { x: 900, y: 450 });
});
test('캔버스가 어디에 놓였든 그 자리를 뺀다', () => {
  const p = L.imagePoint({ left: 100, top: 50, width: 900, height: 450 },
                         { w: 900, h: 450 }, { w: 1800, h: 900 }, 550, 275);
  assert.deepEqual(p, { x: 900, y: 450 });
});
test('그림 밖을 눌러도 그림 안으로 붙인다', () => {
  const p = L.imagePoint(RECT, { w: 900, h: 450 }, { w: 1800, h: 900 }, -50, 9000);
  assert.deepEqual(p, { x: 0, y: 900 });
});
test('크기를 모르면 자리도 없다', () => {
  assert.equal(L.imagePoint({ left: 0, top: 0, width: 0, height: 0 },
                            { w: 900, h: 450 }, { w: 1800, h: 900 }, 10, 10), null);
  assert.equal(L.imagePoint(RECT, { w: 900, h: 450 }, null, 10, 10), null);
});

test('누른 자리를 품는 가장 작은 상자를 고른다', () => {
  const bs = [{ x0: 0, y0: 0, x1: 100, y1: 100 }, { x0: 10, y0: 10, x1: 40, y1: 40 }];
  assert.equal(L.boxAt(bs, 20, 20), 1);
  assert.equal(L.boxAt(bs, 80, 80), 0);
  assert.equal(L.boxAt(bs, 200, 200), -1);
});

/* REVERT: 겹치는 상자를 말하지 않는다. 한 패널을 두 번 읽거나 이웃의 표시를
 * 함께 읽는데, 계수만 맞으면 아무 데도 안 걸립니다 - 실제로 자동 제안이
 * 이웃 패널을 통째로 품은 상자를 30쌍 냈고 아무도 몰랐습니다. */
test('많이 겹치는 상자 쌍을 이름 대어 말한다', () => {
  const got = L.overlapPairs([{ x0: 0, y0: 0, x1: 100, y1: 100 },
                              { x0: 0, y0: 0, x1: 90, y1: 90 },
                              { x0: 500, y0: 0, x1: 600, y1: 100 }]);
  assert.equal(got.length, 1);
  assert.equal(got[0].a, 1); assert.equal(got[0].b, 2);
  assert.ok(got[0].part > 0.8);
});
/* REVERT: 겹침을 큰 상자 쪽으로만 잰다. 큰 패널 안에 작은 상자가 통째로 들어
 * 있으면 큰 쪽 넓이로는 몇 %밖에 안 되어 조용히 지나갑니다 - 실제로 자동 제안이
 * 낸 완전 포함 4건이 그런 모양이었습니다. */
test('큰 상자가 작은 상자를 통째로 품는 것도 겹침이다', () => {
  const got = L.overlapPairs([{ x0: 0, y0: 0, x1: 1000, y1: 1000 },
                              { x0: 10, y0: 10, x1: 100, y1: 100 }]);
  assert.equal(got.length, 1);
  assert.equal(got[0].part, 1);
});
test('스치는 상자는 겹침이 아니다', () => {
  assert.equal(L.overlapPairs([{ x0: 0, y0: 0, x1: 100, y1: 100 },
                               { x0: 95, y0: 0, x1: 200, y1: 100 }]).length, 0);
});

/* REVERT: 브라우저에 남아 있던 답을 그대로 쓴다. 같은 file:// 자리에서 묶음이
 * 저장소를 함께 쓰기 때문에, 제안을 고쳐 페이지를 다시 만들어도 옛 상자가
 * "제안"으로 되살아나고 옛 "봤다"가 그대로 나갑니다. */
test('제안이나 크롭이 바뀐 답은 이 그림의 답이 아니다', () => {
  assert.equal(L.staleState({ stamp: 'abc/v2/3' }, { stamp: 'abc/v2/3' }), false);
  assert.equal(L.staleState({ stamp: 'abc/v1/3' }, { stamp: 'abc/v2/3' }), true);
  assert.equal(L.staleState({}, { stamp: 'abc/v2/3' }), true);
});

/* REVERT: 답을 크롭에 묶지 않는다. 같은 이름으로 다시 만들어진 크롭은 같은
 * 크기의 다른 그림이고, 관문은 그것을 알 길이 없습니다. */
test('답은 어느 크롭 위의 좌표인지 들고 나간다', () => {
  const row = L.panelsOf('D0001', state({ crop: 'deadbeef', proposalVersion: 'v2' })).rows[0];
  assert.equal(row.Crop_SHA256, 'deadbeef');
  assert.equal(row.Proposal_Version, 'v2');
  const none = L.panelsOf('D0001', state({ verdict: 'NO_PANELS', boxes: [],
                                           crop: 'deadbeef' })).rows[0];
  assert.equal(none.Crop_SHA256, 'deadbeef');
});

/* 개수: 그 패널에서 읽어야 할 표시가 몇인가. 리더가 찾아낸 수와 대조할 유일한
 * 수이고, 끌기로는 말할 수 없어 숫자 칸으로 받습니다. */
test('개수는 그대로 줄이 된다', () => {
  const rows = L.panelsOf('D0001', state({
    boxes: [box({ count: '3', countSource: 'PROPOSED' }), box({ x0: 500, x1: 900, count: '5' })]
  })).rows;
  assert.equal(rows[0].Mark_Count, '3');
  assert.equal(rows[0].Count_Source, 'PROPOSED');
  assert.equal(rows[1].Count_Source, 'TYPED');
});
/* REVERT: 빈 개수를 막는다. 이 페이지가 묻는 것은 자리와 종류이고, 개수 1019칸을
 * 다 채우게 붙잡아 두면 아무도 끝내지 못합니다. */
test('개수를 아직 말하지 않아도 답이 된다', () => {
  const got = L.panelsOf('D0001', state());
  assert.equal(got.ready, true);
  assert.equal(got.rows[0].Mark_Count, '');
  assert.equal(got.rows[0].Count_Source, '');
});
/* REVERT: 아무 글자나 개수로 받는다. 리더가 찾아낸 수와 대조할 수가 아닙니다. */
test('셀 수 없는 개수는 답이 아니다', () => {
  assert.match(L.panelsOf('D0001', state({ boxes: [box({ count: '세 개' })] })).why, /개수는 1 이상/);
  assert.match(L.panelsOf('D0001', state({ boxes: [box({ count: '0' })] })).why, /개수는 1 이상/);
  assert.match(L.panelsOf('D0001', state({ boxes: [box({ count: '1.5' })] })).why, /개수는 1 이상/);
});
test('개수를 아직 말하지 않은 패널을 센다', () => {
  const st = { a: state({ boxes: [box({ count: '2' }), box({ x0: 500, x1: 900 })] }),
               b: state({ verdict: 'NO_PANELS', boxes: [] }) };
  assert.equal(L.missingCounts(['a', 'b'], st), 1);
});

/* 한 패널에 종류가 둘인 그림 - 막대 위에 선(쌍축). 리더 둘이 같은 자리를 읽어야
 * 하고, 종류 하나로는 말할 수 없습니다. */
test('두 번째 종류와 그 개수가 줄이 된다', () => {
  const row = L.panelsOf('D0001', state({
    boxes: [box({ mark: 'BAR', mark2: 'LINE', count2: '2', mark2Source: 'PROPOSED' })] })).rows[0];
  assert.equal(row.Mark_Type_2, 'LINE');
  assert.equal(row.Mark_Count_2, '2');
  assert.equal(row.Mark2_Source, 'PROPOSED');
});
test('두 번째 종류가 없으면 그 칸들은 비어 나간다', () => {
  const row = L.panelsOf('D0001', state({ boxes: [box({ count2: '9' })] })).rows[0];
  assert.equal(row.Mark_Type_2, ''); assert.equal(row.Mark_Count_2, ''); assert.equal(row.Mark2_Source, '');
});
/* REVERT: 두 번째 종류를 첫 번째와 같게, 또는 "읽을 값 없음"으로 받는다. 같은
 * 종류를 두 번 읽을 일도, 없는 값을 읽을 일도 없습니다. */
test('두 번째 종류는 첫 번째와 달라야 한다', () => {
  assert.match(L.panelsOf('D0001', state({ boxes: [box({ mark2: 'BOX' })] })).why, /같습니다/);
});
test('읽을 값 없음은 두 번째 종류가 아니다', () => {
  assert.match(L.panelsOf('D0001', state({ boxes: [box({ mark2: 'NOT_DATA' })] })).why, /받을 수 없는 두 번째/);
  assert.match(L.panelsOf('D0001', state({ boxes: [box({ mark: 'NOT_DATA', mark2: 'LINE' })] })).why, /받을 수 없는 두 번째/);
  assert.match(L.panelsOf('D0001', state({ boxes: [box({ mark2: 'PIE' })] })).why, /받을 수 없는 두 번째/);
});
test('두 번째 종류의 개수도 셀 수여야 한다', () => {
  assert.match(L.panelsOf('D0001', state({ boxes: [box({ mark2: 'LINE', count2: '0' })] })).why, /두 번째 종류: 개수는/);
});
/* REVERT: 개별 피험자의 점·선이 겹친 것을 적지 않는다. 읽을 값이 아니라 리더가
 * 비켜 가야 할 잉크이고, 상자 리더가 실제로 그 점에 걸린 적이 있습니다. */
test('개별 점·선 겹침은 따로 나간다', () => {
  const rows = L.panelsOf('D0001', state({
    boxes: [box({ overlay: 'INDIVIDUAL', overlaySource: 'PROPOSED' }), box({ x0: 500, x1: 900 })] })).rows;
  assert.equal(rows[0].Overlay, 'INDIVIDUAL'); assert.equal(rows[0].Overlay_Source, 'PROPOSED');
  assert.equal(rows[1].Overlay, ''); assert.equal(rows[1].Overlay_Source, '');
});

console.log('');
console.log(pass + '/' + (pass + fails.length) + ' passed');
if (fails.length) { console.log('FAILED: ' + fails.join(', ')); process.exit(1); }
