/* 남은 결정 묶음 페이지의 결정들에 대한 시나리오.
 *
 *     node test_bundle_page.mjs
 */
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
const L = createRequire(import.meta.url)('./bundle_page.js');

let pass = 0; const fails = [];
function test(name, fn) {
  try { fn(); console.log('ok    ' + name); pass++; }
  catch (e) { console.log('FAIL  ' + name + '  <- ' + e.message); fails.push(name); }
}

const LABEL_EFFECT = { gate: null, needs: 'R4', uses_text: true };
function item(over) {
  return Object.assign({ id: 'B01', sec: 'B', target: 'DOC_D001', proposal: 'NON_TARGET',
                         observed_by: 'Claude (survey)', sha: 'a'.repeat(64), img_sha: 'b'.repeat(64),
                         options: [['DIGITIZE', 'read'], ['NON_TARGET', 'close'], ['HOLD', 'hold']], text: null }, over || {});
}
function label(over) {
  return item(Object.assign({ id: 'C001', sec: 'C', target: 'DOC_D002__p1', proposal: 'LABEL',
                              options: [['LABEL', 'label', LABEL_EFFECT], ['EDIT', 'edit', LABEL_EFFECT],
                                        ['NON_TARGET', 'close'], ['HOLD', 'hold']],
                              text: { value: 'Heart rate', unit: 'bpm' } }, over || {}));
}
const CTX = { who: 'minyeop', file: 'bundle_answers.csv' };

test('제안을 그대로 고른 줄은 보지 않아도 승인된 관찰이 된다', () => {
  const got = L.answerOf(item(), { choice: 'NON_TARGET', on: '2026-10-16' }, CTX);
  assert.equal(got.ready, true);
  assert.equal(got.approved, true);
  assert.equal(got.row.Seen_By_Person, '0');
  assert.equal(got.row.Observed_By, 'Claude (survey)');
  assert.match(got.row.Approval_Ref, /bundle_answers\.csv: minyeop 2026-10-16/);
});

/* REVERT: 제안과 다른 답도 보지 않고 받는다. 그 줄은 아무도 보지 않은 판정이
 * 됩니다 - 제안을 낸 것은 그렇게 보지 않았고, 사람은 보지 않았습니다. */
test('제안과 다른 답은 직접 보았다 없이는 답이 아니다', () => {
  const got = L.answerOf(item(), { choice: 'DIGITIZE' }, CTX);
  assert.equal(got.ready, false);
  assert.match(got.why, /직접 보았다/);
});
test('제안과 다른 답도 직접 보았으면 본 답이다', () => {
  const got = L.answerOf(item(), { choice: 'DIGITIZE', seen: true }, CTX);
  assert.equal(got.ready, true);
  assert.equal(got.approved, false);
  assert.equal(got.row.Seen_By_Person, '1');
  assert.equal(got.row.Observed_By, '');
  assert.equal(got.row.Approval_Ref, '');
});
test('제안대로라도 직접 보았으면 본 답으로 나간다', () => {
  const got = L.answerOf(item(), { choice: 'NON_TARGET', seen: true }, CTX);
  assert.equal(got.row.Seen_By_Person, '1');
  assert.equal(got.approved, false);
});

/* REVERT: 제안을 낸 것이 없는 항목도 승인으로 받는다. Observed_By가 빈 승인은
 * 관문이 APPROVAL_INCOMPLETE로 거절합니다 - 페이지가 먼저 막지 않으면 사람은
 * 답을 보냈다고 생각하고 관문에서 처음 압니다. */
test('제안을 낸 것이 적히지 않은 항목은 승인만으로 답이 되지 않는다', () => {
  const got = L.answerOf(item({ observed_by: '' }), { choice: 'NON_TARGET' }, CTX);
  assert.equal(got.ready, false);
  assert.match(got.why, /Observed_By/);
});
/* REVERT: 본 것과 승인한 사람이 같아도 받는다(approval.OBSERVER_IS_APPROVER). */
test('제안을 낸 것과 승인하는 사람이 같으면 승인이 아니다', () => {
  const got = L.answerOf(item({ observed_by: 'MinYeop' }), { choice: 'NON_TARGET' }, CTX);
  assert.equal(got.ready, false);
  assert.match(got.why, /같습니다/);
});
test('이름이 없으면 답이 아니다', () => {
  assert.equal(L.answerOf(item(), { choice: 'NON_TARGET' }, { who: ' ' }).ready, false);
});
test('항목에 없는 답은 이름을 대며 거절한다', () => {
  const got = L.answerOf(item(), { choice: 'PARTIAL', seen: true }, CTX);
  assert.equal(got.ready, false);
  assert.match(got.why, /PARTIAL/);
});
test('보류는 보지 않아도 답이고, 누가 보았는지를 주장하지 않는다', () => {
  const got = L.answerOf(item(), { choice: 'HOLD' }, CTX);
  assert.equal(got.ready, true);
  assert.equal(got.row.Seen_By_Person, '');
  assert.equal(got.row.Observed_By, '');
});

test('제안한 이름을 고른 줄은 그 이름과 단위를 들고 간다', () => {
  const got = L.answerOf(label(), { choice: 'LABEL' }, CTX);
  assert.equal(got.ready, true);
  assert.equal(got.row.Text, 'Heart rate');
  assert.equal(got.row.Unit, 'bpm');
});
test('효과가 여럿인 답도 그중 하나가 이름을 쓰면 이름을 들고 간다', () => {
  const it = label({ options: [['LABEL', 'label', [{ gate: 'identity', proposal_id: 'p' , set: { a: 1 } }, LABEL_EFFECT]],
                               ['HOLD', 'hold']] });
  assert.equal(L.answerOf(it, { choice: 'LABEL' }, CTX).row.Text, 'Heart rate');
  const no = label({ options: [['LABEL', 'label', [{ gate: 'identity', proposal_id: 'p', set: { a: 1 } }]], ['HOLD', 'hold']] });
  assert.equal(L.answerOf(no, { choice: 'LABEL' }, CTX).row.Text, '');
});
test('이름을 들고 가지 않는 답은 이름 칸이 비어 있다', () => {
  const got = L.answerOf(label({ proposal: 'NON_TARGET' }), { choice: 'NON_TARGET' }, CTX);
  assert.equal(got.row.Text, '');
});
/* REVERT: 고친 이름도 승인으로 받는다. 사람이 쓴 글을 "Claude가 보았다"로
 * 적게 됩니다. */
test('이름을 고친 답은 늘 직접 보았다가 있어야 한다', () => {
  const got = L.answerOf(label({ proposal: 'EDIT' }), { choice: 'EDIT', text: 'HR', unit: 'bpm' }, CTX);
  assert.equal(got.ready, false);
  assert.match(got.why, /직접 보았다/);
  const ok = L.answerOf(label(), { choice: 'EDIT', text: 'HR', unit: 'bpm', seen: true }, CTX);
  assert.equal(ok.ready, true);
  assert.equal(ok.row.Text, 'HR');
});
test('고친 이름이 비었거나 제안과 같으면 답이 아니다', () => {
  assert.match(L.answerOf(label(), { choice: 'EDIT', text: ' ', seen: true }, CTX).why, /적어/);
  assert.match(L.answerOf(label(), { choice: 'EDIT', text: 'Heart rate', unit: 'bpm', seen: true }, CTX).why, /같습니다/);
  assert.equal(L.answerOf(label(), { choice: 'EDIT', text: 'Heart rate', unit: 'min⁻¹', seen: true }, CTX).ready, true);
});

/* REVERT: 채우기가 사람이 고른 답까지 제안으로 덮는다. 사람이 다르게 고른
 * 줄이 사람이 고르지 않은 승인이 됩니다. */
test('제안대로 채우기는 빈 칸만 채운다', () => {
  const items = [item({ id: 'B01' }), item({ id: 'B02' }), item({ id: 'B03', proposal: '' })];
  const st = { B01: { choice: 'DIGITIZE', seen: true } };
  const n = L.fillEmpty(items, st, null, '2026-10-16');
  assert.equal(n, 1);
  assert.equal(st.B01.choice, 'DIGITIZE');
  assert.equal(st.B02.choice, 'NON_TARGET');
  assert.equal(st.B02.on, '2026-10-16');
  assert.equal((st.B03 || {}).choice, undefined);
});
test('묶음 채우기는 고른 묶음만 채운다', () => {
  const items = [item({ id: 'B01', sec: 'B' }), item({ id: 'A01', sec: 'A' })];
  const st = {};
  L.fillEmpty(items, st, (x) => x.sec === 'A');
  assert.equal((st.B01 || {}).choice, undefined);
  assert.equal(st.A01.choice, 'NON_TARGET');
});

/* REVERT: CSV에서 항목·그림 지문을 뺀다. 답이 어느 항목의 어느 그림을 보고
 * 한 것인지 관문 쪽(bundle_route)이 확인할 길이 없어집니다. */
test('CSV는 답이 된 줄만, 항목과 그림의 지문을 싣고 나간다', () => {
  const items = [item({ id: 'B01' }), item({ id: 'B02' })];
  const csv = L.buildCsv(items, { B01: { choice: 'NON_TARGET', note: 'a, "b"' } }, CTX).trim().split('\n');
  assert.equal(csv.length, 2);
  assert.deepEqual(csv[0].split(','), L.CSV_COLUMNS);
  assert.match(csv[1], /^B01,B,DOC_D001,NON_TARGET,NON_TARGET,/);
  assert.ok(csv[1].includes('a'.repeat(64)) && csv[1].includes('b'.repeat(64)));
  assert.ok(csv[1].endsWith('"a, ""b"""'));
});
test('셈은 승인·본 답·보류를 나눠 센다', () => {
  const items = [item({ id: 'B01' }), item({ id: 'B02' }), item({ id: 'B03' }), item({ id: 'B04' })];
  const t = L.tally(items, { B01: { choice: 'NON_TARGET' }, B02: { choice: 'DIGITIZE', seen: true },
                             B03: { choice: 'HOLD' } }, CTX);
  assert.deepEqual(t, { ready: 3, approved: 1, seen: 1, held: 1, total: 4 });
});

console.log('\n' + pass + ' scenarios passed' + (fails.length ? ', ' + fails.length + ' FAILED' : ''));
if (fails.length) process.exit(1);
