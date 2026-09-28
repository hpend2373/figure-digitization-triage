/* 정체 확인 페이지의 결정들에 대한 시나리오.
 *
 *     node test_identity_page.mjs
 */
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
const L = createRequire(import.meta.url)('./identity_page.js');

let pass = 0; const fails = [];
function test(name, fn) {
  try { fn(); console.log('ok    ' + name); pass++; }
  catch (e) { console.log('FAIL  ' + name + '  <- ' + e.message); fails.push(name); }
}

/* 리더가 다 읽어 낸 색 막대 패널. 사람이 할 일은 요인 이름과 막대 정의뿐입니다. */
function state(over) {
  return Object.assign({ verdict: 'CONFIRMED', who: 'MC', seen: true, note: '', proposal: 'GP001',
                         xFactor: 'TIMEPOINT', positions: [], seriesFactor: 'ARM', series: [],
                         markType: '', outcome: '', unit: '', n: '', barTop: 'OUTLINE_CENTER', stem: true,
                         readLabels: 'Pre@175;D1@325;D3@475;R0@625',
                         readSeries: 'Fluid@220,40,40;Control@40,80,220',
                         readOutcome: 'Heart rate', readUnit: 'bpm', readN: '8', markProposed: 'BAR_COLOR',
                         kind: 'BAR', frameX0: 100, frameX1: 700 }, over || {});
}

test('다 읽힌 패널은 요인 이름만 적으면 답이 된다', () => {
  const got = L.verdictOf('GP001', state());
  assert.equal(got.ready, true, got.why);
  assert.equal(got.row.X_Factor, 'TIMEPOINT');
  assert.deepEqual(JSON.parse(got.row.X_Labels).map(p => p.label), ['Pre', 'D1', 'D3', 'R0']);
  assert.deepEqual(JSON.parse(got.row.Series).map(s => [s.name, s.colour]), [['Fluid', '#DC2828'], ['Control', '#2850DC']]);
  assert.equal(got.row.Mark_Type, 'BAR_COLOR');
  assert.equal(got.row.Outcome_Name, 'Heart rate');
  assert.equal(got.row.Unit, 'bpm');
  assert.equal(got.row.N_Outcome, '8');
  assert.equal(got.row.Value_Sources, 'x:READ;series:READ;outcome:READ;n:READ');
});
test('보지 않았거나 이름이 없으면 답이 아니다', () => {
  assert.equal(L.verdictOf('GP001', state({ seen: false })).ready, false);
  assert.equal(L.verdictOf('GP001', state({ who: '' })).ready, false);
  assert.equal(L.verdictOf('GP001', state({ verdict: '' })).ready, false);
  assert.equal(L.verdictOf('GP001', state({ verdict: 'MAYBE' })).ready, false);
});
test('거절과 보류는 값 없이 답이다', () => {
  const got = L.verdictOf('GP001', state({ verdict: 'REJECTED', xFactor: '' }));
  assert.equal(got.ready, true);
  assert.equal(got.row.X_Labels, '');
  assert.equal(L.verdictOf('GP001', state({ verdict: 'HOLD' })).ready, true);
  assert.equal(L.held(['a'], { a: state({ verdict: 'HOLD' }) }), 1);
});
/* REVERT: x 요인 없이 확인이 된다. 격자가 설 이름이 없습니다. */
test('x 요인은 사람이 적어야 한다', () => {
  const got = L.verdictOf('GP001', state({ xFactor: '' }));
  assert.equal(got.ready, false);
  assert.match(got.why, /요인/);
  assert.equal(L.verdictOf('GP001', state({ xFactor: 'time point' })).ready, false);
});
/* REVERT: 하나뿐인 계열은 요인 없이 받는다. 수준 없는 계열은 Cell_Key가 되지 못하고
 * 배치층이 MISSING_SERIES_IDENTITY로 거절합니다 - 파일럿 Beckers는 계열 하나에도
 * POSTURE=SUPINE을 적었습니다. */
test('계열 요인은 하나뿐이어도 있어야 하고, x 요인과 달라야 한다', () => {
  assert.equal(L.verdictOf('GP001', state({ seriesFactor: '' })).ready, false);
  const same = L.verdictOf('GP001', state({ seriesFactor: 'TIMEPOINT' }));
  assert.equal(same.ready, false);
  assert.match(same.why, /두 축/);
  const one = L.verdictOf('GP001', state({ seriesFactor: '', readSeries: 'Fluid@220,40,40' }));
  assert.equal(one.ready, false);
  assert.match(one.why, /어느 군/);
  const named = L.verdictOf('GP001', state({ seriesFactor: 'GROUP', readSeries: 'Fluid@220,40,40' }));
  assert.equal(named.ready, true, named.why);
  assert.equal(named.row.Series_Factor, 'GROUP');
});
test('읽힌 x 라벨이 없으면 찍어야 한다', () => {
  const got = L.verdictOf('GP001', state({ readLabels: '' }));
  assert.equal(got.ready, false);
  assert.match(got.why, /찍고/);
  const typed = L.verdictOf('GP001', state({ readLabels: '', positions: [{ label: 'Pre', px: 175 }, { label: 'Post', px: 500 }] }));
  assert.equal(typed.ready, true, typed.why);
  assert.equal(typed.row.Value_Sources.split(';')[0], 'x:TYPED');
});
/* REVERT: 빈 라벨이나 같은 라벨을 받는다. 같은 수준이 두 자리에 있으면 셀이 겹칩니다. */
test('라벨은 빠짐없이 서로 달라야 한다', () => {
  assert.match(L.verdictOf('GP001', state({ positions: [{ label: 'Pre', px: 175 }, { label: '', px: 300 }] })).why, /비어/);
  assert.match(L.verdictOf('GP001', state({ positions: [{ label: 'Pre', px: 175 }, { label: 'pre', px: 300 }] })).why, /같은 x 라벨/);
});
test('x 위치는 프레임 안이어야 한다', () => {
  const got = L.verdictOf('GP001', state({ positions: [{ label: 'Pre', px: 175 }, { label: 'Far', px: 900 }] }));
  assert.equal(got.ready, false);
  assert.match(got.why, /프레임 밖/);
});
test('표 종류는 어휘 안이어야 한다', () => {
  assert.equal(L.verdictOf('GP001', state({ markType: 'BAR_RAINBOW' })).ready, false);
  assert.equal(L.verdictOf('GP001', state({ markProposed: '', markType: '' })).ready, false);
});
/* REVERT: 색으로 가르는 표에 색 없는 계열을 받는다. 리더는 그 계열의 마스크를 만들 수 없습니다. */
test('색으로 가르는 표는 계열마다 색이 있어야 한다', () => {
  const got = L.verdictOf('GP001', state({ series: [{ name: 'Fluid', colour: [220, 40, 40] }, { name: 'Control', colour: null }] }));
  assert.equal(got.ready, false);
  assert.match(got.why, /색/);
});
test('선 모양으로 가르는 표는 계열마다 선 모양이 있어야 한다', () => {
  const s = state({ kind: 'LINE', markType: 'LINE_MONO_STYLE', readSeries: '',
                    series: [{ name: 'Fluid', colour: null, line_style: 'SOLID' }, { name: 'Control', colour: null, line_style: '' }] });
  assert.match(L.verdictOf('GP001', s).why, /선 모양/);
  s.series[1].line_style = 'DASHED';
  assert.equal(L.verdictOf('GP001', s).ready, true, L.verdictOf('GP001', s).why);
});
test('두 계열을 가를 것이 없으면 답이 아니다', () => {
  const s = state({ kind: 'LINE', markType: 'LINE_MONO_STYLE', readSeries: '',
                    series: [{ name: 'A', colour: null, line_style: 'SOLID' }, { name: 'B', colour: null, line_style: 'SOLID' }] });
  assert.match(L.verdictOf('GP001', s).why, /가를 것이 없습니다/);
  const c = state({ series: [{ name: 'A', colour: [220, 40, 40] }, { name: 'B', colour: [220, 40, 40] }] });
  assert.match(L.verdictOf('GP001', c).why, /가를 것이 없습니다/);
});
test('계열 이름은 서로 달라야 하고, 하나뿐이어도 있어야 한다', () => {
  assert.match(L.verdictOf('GP001', state({ series: [{ name: 'A', colour: [1, 2, 3] }, { name: 'a', colour: [4, 5, 6] }] })).why, /같은 계열 이름/);
  const one = L.verdictOf('GP001', state({ seriesFactor: 'GROUP', readSeries: '@220,40,40' }));
  assert.equal(one.ready, false);
  assert.match(one.why, /이름\(수준\)이 비어/);
  const named = L.verdictOf('GP001', state({ seriesFactor: 'GROUP', series: [{ name: 'ALL', colour: [220, 40, 40] }] }));
  assert.equal(named.ready, true, named.why);
  assert.equal(JSON.parse(named.row.Series)[0].name, 'ALL');
});
/* REVERT: 결과변수 없이 확인이 된다. 값이 무엇의 값인지 없는 단위입니다. */
test('결과변수 이름이 없으면 답이 아니다', () => {
  const got = L.verdictOf('GP001', state({ readOutcome: '' }));
  assert.equal(got.ready, false);
  assert.match(got.why, /결과변수/);
  const typed = L.verdictOf('GP001', state({ readOutcome: '', outcome: 'Heart rate' }));
  assert.equal(typed.ready, true);
  assert.equal(typed.row.Value_Sources.split(';')[2], 'outcome:TYPED');
});
test('n은 비워도 되고, 적으면 양의 정수여야 한다', () => {
  const none = L.verdictOf('GP001', state({ readN: '' }));
  assert.equal(none.ready, true);
  assert.equal(none.row.N_Outcome, '');
  assert.equal(L.verdictOf('GP001', state({ n: '8.5' })).ready, false);
  assert.equal(L.verdictOf('GP001', state({ n: '-3' })).ready, false);
  assert.equal(L.verdictOf('GP001', state({ n: '12' })).row.N_Outcome, '12');
});
test('막대 표는 값을 어디서 읽는지 골라야 한다', () => {
  const got = L.verdictOf('GP001', state({ barTop: '' }));
  assert.equal(got.ready, false);
  assert.match(got.why, /막대/);
  const box = L.verdictOf('GP001', state({ kind: 'BOX', markProposed: 'BOX_VIOLIN', barTop: '', seriesFactor: 'GROUP', readSeries: 'ALL@220,40,40' }));
  assert.equal(box.ready, true, box.why);
  assert.equal(box.row.Bar_Top_Definition, '');
  assert.equal(box.row.Errorbar_Stem_Confirmed, '');
});
test('오차막대 줄기 확인은 연속형 표에만 나간다', () => {
  assert.equal(L.verdictOf('GP001', state({ stem: false })).row.Errorbar_Stem_Confirmed, 'FALSE');
  assert.equal(L.verdictOf('GP001', state({ stem: true })).row.Errorbar_Stem_Confirmed, 'TRUE');
  assert.equal(L.verdictOf('GP001', state({ kind: 'SCATTER', markProposed: 'SCATTER', barTop: '', seriesFactor: 'GROUP', readSeries: 'ALL@1,2,3' })).row.Errorbar_Stem_Confirmed, '');
});
/* 주황 원·주황 삼각형·파랑 원 (S41467 FIG5 b): 색도 마커도 혼자서는 못 가릅니다. */
function colourMarker(over) {
  return state(Object.assign({ kind: 'LINE', markType: 'LINE_COLOR', barTop: '', seriesFactor: 'TIMEPOINT_DAY', xFactor: 'CLOCK_TIME',
    series: [{ name: 'B3', colour: [228, 134, 10], marker: 'CIRCLE', marker_fill: 'FILLED' },
             { name: 'B1', colour: [228, 134, 10], marker: 'TRIANGLE', marker_fill: 'FILLED' },
             { name: 'D1', colour: [0, 84, 147], marker: 'CIRCLE', marker_fill: 'FILLED' }] }, over || {}));
}
/* REVERT: 사람이 읽는 경로에도 판독기의 구분 규칙을 건다. 색+마커 패널은 영영 답이 되지 않습니다. */
test('색+마커 조합은 판독기 경로로는 답이 아니고, 사람이 읽는 경로로는 답이다', () => {
  assert.match(L.verdictOf('GP001', colourMarker()).why, /가를 것이 없습니다/);
  const got = L.verdictOf('GP001', colourMarker({ route: 'MANUAL' }));
  assert.equal(got.ready, true, got.why);
  assert.equal(got.row.Read_Route, 'MANUAL');
  assert.deepEqual(JSON.parse(got.row.Series).map(e => [e.name, e.colour, e.marker]),
                   [['B3', '#E4860A', 'CIRCLE'], ['B1', '#E4860A', 'TRIANGLE'], ['D1', '#005493', 'CIRCLE']]);
  assert.equal(L.verdictOf('GP001', state()).row.Read_Route, 'AUTO');
  assert.equal(L.routeOf({}), 'AUTO');
});
/* REVERT: 사람이 읽는 경로에서도 색으로 가르는 표의 색을 요구한다. 흰 막대 계열에는 색이 없습니다. */
test('사람이 읽는 경로는 색 없는 계열도 받는다', () => {
  const s = state({ route: 'MANUAL', series: [{ name: 'Fluid', colour: [220, 40, 40], bar_fill: 'HATCHED' }, { name: 'Control', colour: null, bar_fill: 'OPEN' }] });
  assert.equal(L.verdictOf('GP001', s).ready, true, L.verdictOf('GP001', s).why);
});
/* REVERT: 판독기가 모르는 모양을 판독기 경로에서 받는다. 계획서가 판독기에 모르는 모양을 찾으라고 합니다. */
test('판독기가 모르는 모양은 사람이 읽는 경로에서만 답이다', () => {
  const s = state({ kind: 'LINE', markType: 'LINE_MONO', barTop: '', readSeries: '',
                    series: [{ name: 'SUP', colour: null, marker: 'CROSS' }, { name: 'STAND', colour: null, marker: 'ASTERISK' }] });
  const auto = L.verdictOf('GP001', s);
  assert.equal(auto.ready, false);
  assert.match(auto.why, /사람이 읽는다/);
  s.route = 'MANUAL';
  assert.equal(L.verdictOf('GP001', s).ready, true, L.verdictOf('GP001', s).why);
});
/* REVERT: 색으로 가르는 표에서도 ▼를 판독기 경로에서 막는다. 판독기는 색으로 찾고 모양을 보지 않습니다. */
test('색으로 가르는 표에서는 ▼도 판독기 경로에서 답이다', () => {
  const s = state({ kind: 'LINE', markType: 'LINE_COLOR', barTop: '', readSeries: '',
                    series: [{ name: 'Cocktail', colour: [218, 96, 0], marker: 'CIRCLE' }, { name: 'Control', colour: [129, 129, 129], marker: 'TRIANGLE_DOWN' }] });
  const got = L.verdictOf('GP001', s);
  assert.equal(got.ready, true, got.why);
  assert.equal(got.row.Read_Route, 'AUTO');
  assert.equal(JSON.parse(got.row.Series)[1].marker, 'TRIANGLE_DOWN');
  s.markType = 'LINE_MONO';
  s.series[1].marker = 'CROSS';
  assert.equal(L.verdictOf('GP001', s).ready, false);
});
/* REVERT: 마커 표에서 ▼를 막는다 / ▲와 ▼를 다른 모양으로 친다. 판독기의 삼각형은 방향을 보지 않습니다. */
test('마커 표의 ▼는 ▲가 없을 때만 판독기 경로에서 답이다', () => {
  const s = state({ kind: 'LINE', markType: 'LINE_MONO', barTop: '', readSeries: '',
                    series: [{ name: 'Control', colour: null, marker: 'CIRCLE', marker_fill: 'OPEN' }, { name: 'NFL', colour: null, marker: 'TRIANGLE_DOWN', marker_fill: 'FILLED' }] });
  assert.equal(L.verdictOf('GP001', s).ready, true, L.verdictOf('GP001', s).why);
  s.series[0] = { name: 'Up', colour: null, marker: 'TRIANGLE', marker_fill: 'FILLED' };
  assert.equal(L.verdictOf('GP001', s).ready, false);
});
/* REVERT: 사람이 읽는 경로에서 단서를 계열 구분에 넣지 않는다 / 구분을 묻지 않는다. */
test('똑같이 그려진 계열은 서로 다른 구분 단서가 있어야 답이다', () => {
  const same = { colour: [233, 137, 10], marker: 'CIRCLE', marker_fill: 'OPEN', line_style: 'DOTTED' };
  const s = state({ kind: 'LINE', markType: 'LINE_COLOR', barTop: '', route: 'MANUAL',
                    series: [Object.assign({ name: 'D3' }, same), Object.assign({ name: 'B2' }, same)] });
  assert.match(L.verdictOf('GP001', s).why, /구분 단서/);
  s.series[0].cue = '곡선'; s.series[1].cue = ' 곡선 ';
  assert.equal(L.verdictOf('GP001', s).ready, false);
  s.series[0].cue = '위쪽 곡선, 끝에 D3'; s.series[1].cue = '아래쪽 곡선, 끝에 B2';
  const got = L.verdictOf('GP001', s);
  assert.equal(got.ready, true, got.why);
  assert.deepEqual(JSON.parse(got.row.Series).map(e => e.cue), ['위쪽 곡선, 끝에 D3', '아래쪽 곡선, 끝에 B2']);
  assert.equal('cue' in JSON.parse(L.verdictOf('GP001', state()).row.Series)[0], false);
});
test('경로는 csv로 나간다', () => {
  assert.ok(L.CSV_COLUMNS.indexOf('Read_Route') >= 0);
  const csv = L.buildCsv(['a'], { a: colourMarker({ route: 'MANUAL' }) });
  const head = csv.split('\n')[0].split(','), line = csv.split('\n')[1];
  assert.equal(head.indexOf('Read_Route') >= 0, true);
  assert.match(line, /"MANUAL"/);
});
test('사람이 고친 것과 읽은 것을 가른다', () => {
  assert.equal(L.pick('', 'read'), 'read');
  assert.equal(L.pick(' typed ', 'read'), 'typed');
  assert.equal(L.hexOf([255, 0, 16]), '#FF0010');
  assert.deepEqual(L.parseLabels('D1 evening@100;D3@200'), [{ label: 'D1 evening', px: 100 }, { label: 'D3', px: 200 }]);
  assert.deepEqual(L.parseSeries('Fluid@220,40,40;Plain'), [{ name: 'Fluid', colour: [220, 40, 40] }, { name: 'Plain', colour: null }]);
});
test('csv는 답이 된 줄만, 정렬해서', () => {
  const csv = L.buildCsv(['b', 'a'], { a: state(), b: state({ seen: false }) });
  const lines = csv.split('\n');
  assert.equal(lines.length, 2);
  assert.equal(lines[0], L.CSV_COLUMNS.join(','));
  assert.match(lines[1], /^"GP001","CONFIRMED","TIMEPOINT"/);
  assert.equal(L.remaining(['a', 'b'], { a: state(), b: state({ seen: false }) }), 1);
});

console.log('');
console.log(pass + '/' + (pass + fails.length) + ' passed');
if (fails.length) { console.log('FAILED: ' + fails.join(', ')); process.exit(1); }
