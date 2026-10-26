/* 축·계열 확인 페이지의 결정들에 대한 시나리오.
 *
 *     node test_axis_series_page.mjs
 *
 * 관문 줄을 짓는 것은 geometry_page.js·identity_page.js의 verdictOf이고, 여기서 보는 것은
 * 카드의 답을 그 함수들에 옮기는 일입니다.
 */
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
const require = createRequire(import.meta.url);
const GEO = require('../fdt/geometry_page.js');
const IDN = require('../fdt/identity_page.js');
const AX = require('../fdt/axis_series_page.js');

let pass = 0; const fails = [];
function test(name, fn) {
  try { fn(); console.log('ok    ' + name); pass++; }
  catch (e) { console.log('FAIL  ' + name + '  <- ' + e.message); fails.push(name); }
}

const gmeta = {
  'D1__p1': { proposal: 'D1__p1', readPairs: '100@50;0@450', topPixel: '50', bottomPixel: '450', siblings: ['D1__p2'],
              sharedCandidate: '', originX: 0, originY: 0, frameTop: '40', frameBottom: '460', noFrame: false,
              region: '0,0,800,500' },
  'D1__p2': { proposal: 'D1__p2', readPairs: '', topPixel: '60', bottomPixel: '440', siblings: ['D1__p1'],
              sharedCandidate: '', originX: 0, originY: 0, frameTop: '40', frameBottom: '460', noFrame: false,
              region: '0,0,800,500' }
};
const imeta = {
  'D1__p1': { proposal: 'D1__p1', readLabels: 'Pre@200;Post@600', readSeries: '', readOutcome: 'Heart rate',
              readUnit: 'bpm', readN: '', markProposed: 'BAR_COLOR', kind: 'BAR', frameX0: '100', frameX1: '700',
              originX: 0, originY: 0 },
  'D1__p2': { proposal: 'D1__p2', readLabels: '', readSeries: '', readOutcome: 'MAP', readUnit: 'A%',
              readN: '', markProposed: 'LINE_MONO', kind: 'LINE', frameX0: '100', frameX1: '700', originX: 0, originY: 0 }
};
function data(over) {
  return Object.assign({
    order: ['D1__p1', 'D1__p2'], gmeta: gmeta, imeta: imeta, date: '2026-10-16', proposer: 'Claude',
    prov: { 'D1__p1': { geo: '프레임 리더 · 눈금 값 리더', idn: 'x 라벨·자리 리더' },
            'D1__p2': { geo: '프레임 리더 · 눈금 값 Claude', idn: "'읽지 않는다' Claude" } },
    proposals: {
      'D1__p1': { geo: { verdict: 'CONFIRMED' },
                  idn: { verdict: 'CONFIRMED', xFactor: 'TIMEPOINT', seriesFactor: 'GROUP', markType: 'BAR_COLOR',
                         series: [{ name: 'ALL', colour: [230, 130, 0], line_style: '', marker: '', marker_fill: '',
                                    bar_fill: 'SOLID', cue: '' }],
                         route: 'AUTO', n: '', barTop: 'FILL_EDGE', stem: true, positions: [], outcome: '', unit: '' } },
      'D1__p2': { geo: { verdict: 'CONFIRMED', top: '120', bottom: '60' },
                  idn: { verdict: 'REJECTED' } }
    }
  }, over || {});
}
function st(over) {
  return Object.assign({ 'D1__p1': { geo: 'ACCEPT', idn: 'ACCEPT', seen: true, note: '' },
                         'D1__p2': { geo: 'ACCEPT', idn: 'ACCEPT', seen: true, note: '' } }, over || {});
}

test('제안대로는 기하·정체 페이지의 verdictOf가 짓는 줄을 낸다', () => {
  const C = AX.makeCheck(GEO, IDN, data());
  const g = C.partState(st(), 'MY', 'D1__p1', 'geo', C.broken());
  const i = C.partState(st(), 'MY', 'D1__p1', 'idn', C.broken());
  assert.equal(g.done, true, g.text); assert.equal(i.done, true, i.text);
  assert.equal(g.row.Confirmed_Tick_Values, '100@50;0@450');
  assert.equal(g.row.Value_Source, 'READ');
  assert.equal(i.row.X_Factor, 'TIMEPOINT');
  assert.deepEqual(JSON.parse(i.row.X_Labels).map(p => p.label), ['Pre', 'Post']);
  assert.equal(i.row.Outcome_Name, 'Heart rate');
  assert.equal(i.row.Verified_By, 'MY');
});
test('제안이 적은 눈금 값은 리더가 잰 눈금 행에 붙는다', () => {
  const C = AX.makeCheck(GEO, IDN, data());
  const g = C.partState(st(), 'MY', 'D1__p2', 'geo', C.broken());
  assert.equal(g.row.Confirmed_Tick_Values, '120@60;60@440');
  assert.equal(g.row.Value_Source, 'TYPED');
});
test("'읽지 않는다' 제안은 REJECTED 줄이 된다", () => {
  const C = AX.makeCheck(GEO, IDN, data());
  const i = C.partState(st(), 'MY', 'D1__p2', 'idn', C.broken());
  assert.equal(i.row.Human_Verification_Status, 'REJECTED');
});
test('Note에 무엇을 누가 제안했는지와 메모가 남는다', () => {
  const C = AX.makeCheck(GEO, IDN, data());
  const i = C.partState(st({ 'D1__p1': { geo: 'ACCEPT', idn: 'ACCEPT', seen: true, note: '확인함' } }), 'MY', 'D1__p1', 'idn', C.broken());
  assert.match(i.row.Note, /^\[축·계열 확인 페이지 2026-10-16\] 제안: x 라벨·자리 리더/);
  assert.match(i.row.Note, /\| 메모: 확인함$/);
});
test('보지 않았거나 이름이 없으면 답이 아니다', () => {
  const C = AX.makeCheck(GEO, IDN, data());
  const b = C.broken();
  assert.equal(C.partState(st({ 'D1__p1': { geo: 'ACCEPT', idn: 'ACCEPT', seen: false, note: '' } }), 'MY', 'D1__p1', 'geo', b).done, false);
  const noName = C.partState(st(), '  ', 'D1__p1', 'geo', b);
  assert.equal(noName.done, false); assert.match(noName.text, /보신 분 이름/);
});
test("빈 답에만 '제안대로'를 채우고, 고른 답과 목격은 건드리지 않는다", () => {
  const C = AX.makeCheck(GEO, IDN, data());
  const s = C.withDefaults({ 'D1__p1': { geo: 'FIX', idn: '', seen: false, note: 'x' } });
  assert.equal(s['D1__p1'].geo, 'FIX');
  assert.equal(s['D1__p1'].idn, 'ACCEPT');
  assert.equal(s['D1__p2'].geo, 'ACCEPT');
  assert.equal(s['D1__p1'].seen, false);
  assert.equal(s['D1__p2'].seen, false);
});
test('고칠 곳은 메모가 없으면 표시하지만 답으로는 나간다', () => {
  const C = AX.makeCheck(GEO, IDN, data());
  const r = C.partState(st({ 'D1__p1': { geo: 'FIX', idn: 'ACCEPT', seen: true, note: '' } }), 'MY', 'D1__p1', 'geo', C.broken());
  assert.equal(r.done, true); assert.equal(r.fix, true); assert.equal(r.bad, true); assert.equal(r.row, undefined);
});
test('리더가 읽은 단위를 비우는 제안은 줄의 Unit을 비우고 Note에 적는다', () => {
  const d = data();
  d.proposals['D1__p2'].idn = Object.assign({}, d.proposals['D1__p1'].idn,
    { outcome: 'MAP', unitBlank: true, positions: [{ label: 'A', px: 200 }, { label: 'B', px: 600 }] });
  const C = AX.makeCheck(GEO, IDN, d);
  const i = C.partState(st(), 'MY', 'D1__p2', 'idn', C.broken());
  assert.equal(i.done, true, i.text);
  assert.equal(i.row.Unit, '');
  assert.match(i.row.Note, /리더가 읽은 단위 "A%"는 그림에 없어 비움/);
  const kept = C.partState(st(), 'MY', 'D1__p1', 'idn', C.broken());
  assert.equal(kept.row.Unit, 'bpm');
});
test('관문 규칙에 걸리는 제안은 제안대로로 답이 되지 않고 까닭을 보인다', () => {
  const d = data();
  d.proposals['D1__p1'].idn = Object.assign({}, d.proposals['D1__p1'].idn, { xFactor: '' });
  const C = AX.makeCheck(GEO, IDN, d);
  const b = C.broken();
  assert.ok(b['D1__p1|idn']);
  const r = C.partState(st(), 'MY', 'D1__p1', 'idn', b);
  assert.equal(r.done, false); assert.equal(r.bad, true); assert.match(r.text, /^제안이 관문 규칙에 걸립니다/);
  assert.equal(C.partState(st({ 'D1__p1': { geo: 'ACCEPT', idn: 'HOLD', seen: true, note: '' } }), 'MY', 'D1__p1', 'idn', b).done, true);
});
test('답 CSV는 답이 된 부분만, 관문 줄은 제안대로에만', () => {
  const C = AX.makeCheck(GEO, IDN, data());
  const s = st({ 'D1__p2': { geo: 'HOLD', idn: 'ACCEPT', seen: false, note: '' } });
  const out = C.answerCsv(s, 'MY', C.broken());
  const lines = out.csv.split('\n');
  assert.equal(lines[0], AX.CSV_COLUMNS.join(','));
  assert.equal(out.n, 2);
  assert.match(lines[1], /^"D1__p1","GEOMETRY","ACCEPT","MY","1","","\{/);
  assert.match(lines[2], /^"D1__p1","IDENTITY","ACCEPT"/);
});
test('남은 답과 다음 카드', () => {
  const C = AX.makeCheck(GEO, IDN, data());
  const s = st({ 'D1__p1': { geo: 'ACCEPT', idn: 'ACCEPT', seen: true, note: '' },
                 'D1__p2': { geo: 'ACCEPT', idn: 'ACCEPT', seen: false, note: '' } });
  const t = C.tally(s, 'MY', C.broken());
  assert.deepEqual([t.left, t.accepted, t.total], [2, 2, 4]);
  assert.equal(C.nextOpen(s, 'MY', C.broken()), 'D1__p2');
  s['D1__p2'].seen = true;
  assert.equal(C.nextOpen(s, 'MY', C.broken()), '');
});

// --- 들어온 답 다시 대 보기 (recheck) ---
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
const RC = await import('../fdt/axis_series_recheck.mjs');
function answered(over) {
  const C = AX.makeCheck(GEO, IDN, data());
  return RC.parseCsv(C.answerCsv(st(over), 'MY', C.broken()).csv);
}
test('페이지가 낸 답은 다시 지은 줄과 모두 같다', () => {
  const r = AX.recheck(GEO, IDN, data(), answered());
  assert.deepEqual([r.rows, r.same, r.differ.length, r.unknown.length, r.unanswered.length], [4, 4, 0, 0, 0]);
  assert.deepEqual(r.names, ['MY']);
});
test('메모가 있는 답도 같은 줄로 다시 짓는다', () => {
  const rows = answered({ 'D1__p1': { geo: 'ACCEPT', idn: 'ACCEPT', seen: true, note: '눈금 확인함' } });
  assert.match(rows[0].Gate_Row, /메모: 눈금 확인함/);
  const r = AX.recheck(GEO, IDN, data(), rows);
  assert.equal(r.differ.length, 0, JSON.stringify(r.differ));
});
test('관문 줄의 칸 하나가 다르면 다른 줄로 잡는다', () => {
  const rows = answered();
  const g = JSON.parse(rows[0].Gate_Row); g.Confirmed_Tick_Values = '100@51;0@450'; rows[0].Gate_Row = JSON.stringify(g);
  const r = AX.recheck(GEO, IDN, data(), rows);
  assert.equal(r.same, 3); assert.equal(r.differ.length, 1);
  assert.match(r.differ[0][2], /다시 지은 줄과 다릅니다/);
});
test('다른 제안으로 지은 페이지의 답은 맞지 않는다', () => {
  const d = data(); d.proposals['D1__p2'].geo = { verdict: 'CONFIRMED', top: '130', bottom: '60' };
  const r = AX.recheck(GEO, IDN, d, answered());
  assert.equal(r.differ.length, 1); assert.equal(r.differ[0][0], 'D1__p2');
});
test('보류·고칠 곳 줄에 관문 줄이 붙어 있으면 잡는다', () => {
  const rows = answered({ 'D1__p2': { geo: 'HOLD', idn: 'ACCEPT', seen: true, note: '' } });
  const hold = rows.find(x => x.Proposal_ID === 'D1__p2' && x.Part === 'GEOMETRY');
  assert.equal(hold.Gate_Row, '');
  assert.equal(AX.recheck(GEO, IDN, data(), rows).differ.length, 0);
  hold.Gate_Row = rows[0].Gate_Row;
  const r = AX.recheck(GEO, IDN, data(), rows);
  assert.equal(r.differ.length, 1); assert.match(r.differ[0][2], /답이 아닌 줄에 관문 줄/);
});
test('보지 않은 제안대로 줄은 답이 아니다', () => {
  const rows = answered(); rows[0].Seen_By_Person = '0'; rows[1].Seen_By_Person = '0';
  const r = AX.recheck(GEO, IDN, data(), rows);
  assert.equal(r.differ.length, 2); assert.match(r.differ[0][2], /답이 아닌 줄에 관문 줄/);
});
test('페이지에 없는 패널, 답하지 않은 패널, 읽지 못하는 관문 줄', () => {
  const rows = answered();
  rows.push(Object.assign({}, rows[0], { Proposal_ID: 'D9__p1' }));
  rows[1].Gate_Row = '{not json';
  const r = AX.recheck(GEO, IDN, data(), rows.filter(x => x.Proposal_ID !== 'D1__p2'));
  assert.deepEqual(r.unknown, ['D9__p1']); assert.deepEqual(r.unanswered, ['D1__p2']);
  assert.match(r.differ[0][2], /읽지 못합니다/);
});
test('명령: 페이지에서 제안을 꺼내 대 보고, 다르면 종료 코드 1', () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'fdt_recheck_'));
  const page = path.join(dir, 'p.html'), ans = path.join(dir, 'a.csv');
  fs.writeFileSync(page, '<html><script>var DATA = ' + JSON.stringify(data()) + ';\nvar GEO = 1;</script></html>');
  const C = AX.makeCheck(GEO, IDN, data());
  const csv = C.answerCsv(st(), 'MY', C.broken()).csv;
  fs.writeFileSync(ans, '﻿' + csv.replace(/\n/g, '\r\n'));
  const run = () => spawnSync(process.execPath, [new URL('../fdt/axis_series_recheck.mjs', import.meta.url).pathname, page, ans], { encoding: 'utf8' });
  let p = run();
  assert.equal(p.status, 0, p.stdout + p.stderr);
  assert.equal(JSON.parse(p.stdout.split('\n')[0]).same, 4);
  fs.writeFileSync(ans, csv.replace('100@50', '100@52'));
  p = run();
  assert.equal(p.status, 1); assert.match(p.stdout, /DIFFER D1__p1 \| GEOMETRY/);
  fs.writeFileSync(page, '<html></html>');
  assert.notEqual(run().status, 0);
  fs.rmSync(dir, { recursive: true, force: true });
});

console.log('');
console.log(pass + '/' + (pass + fails.length) + ' passed');
if (fails.length) { console.log('FAILED: ' + fails.join(', ')); process.exit(1); }
