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
test('계열이 둘 이상이면 계열 요인이 있어야 하고, x 요인과 달라야 한다', () => {
  assert.equal(L.verdictOf('GP001', state({ seriesFactor: '' })).ready, false);
  const same = L.verdictOf('GP001', state({ seriesFactor: 'TIMEPOINT' }));
  assert.equal(same.ready, false);
  assert.match(same.why, /두 축/);
  const one = L.verdictOf('GP001', state({ seriesFactor: '', readSeries: 'Fluid@220,40,40' }));
  assert.equal(one.ready, true, one.why);
  assert.equal(one.row.Series_Factor, '');
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
test('계열 이름은 서로 달라야 하고, 하나뿐이면 비어도 된다', () => {
  assert.match(L.verdictOf('GP001', state({ series: [{ name: 'A', colour: [1, 2, 3] }, { name: 'a', colour: [4, 5, 6] }] })).why, /같은 계열 이름/);
  const one = L.verdictOf('GP001', state({ seriesFactor: '', readSeries: '@220,40,40' }));
  assert.equal(one.ready, true, one.why);
  assert.equal(JSON.parse(one.row.Series)[0].name, '');
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
  const box = L.verdictOf('GP001', state({ kind: 'BOX', markProposed: 'BOX_VIOLIN', barTop: '', seriesFactor: '', readSeries: '@220,40,40' }));
  assert.equal(box.ready, true, box.why);
  assert.equal(box.row.Bar_Top_Definition, '');
  assert.equal(box.row.Errorbar_Stem_Confirmed, '');
});
test('오차막대 줄기 확인은 연속형 표에만 나간다', () => {
  assert.equal(L.verdictOf('GP001', state({ stem: false })).row.Errorbar_Stem_Confirmed, 'FALSE');
  assert.equal(L.verdictOf('GP001', state({ stem: true })).row.Errorbar_Stem_Confirmed, 'TRUE');
  assert.equal(L.verdictOf('GP001', state({ kind: 'SCATTER', markProposed: 'SCATTER', barTop: '', seriesFactor: '', readSeries: '@1,2,3' })).row.Errorbar_Stem_Confirmed, '');
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
