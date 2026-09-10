/* 기하 확인 페이지의 결정들에 대한 시나리오.
 *
 *     node test_geometry_page.mjs
 */
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
const L = createRequire(import.meta.url)('./geometry_page.js');

let pass = 0; const fails = [];
function test(name, fn) {
  try { fn(); console.log('ok    ' + name); pass++; }
  catch (e) { console.log('FAIL  ' + name + '  <- ' + e.message); fails.push(name); }
}

/* 리더가 읽어 낸 제안. 이 페이지의 흔한 줄이고, 사람이 할 일은 보는 것뿐입니다. */
function state(over) {
  return Object.assign({ verdict: 'CONFIRMED', first: '', last: '', note: '',
                         seen: true, who: 'MC', proposal: 'GP001',
                         readFirst: '40', readLast: '10' }, over || {});
}

/* 리더가 거절한 제안. 여기서만 사람이 숫자를 칩니다. */
function unread(over) {
  return state(Object.assign({ readFirst: '', readLast: '' }, over || {}));
}

test('읽힌 제안은 보기만 해도 답이 된다', () => {
  const got = L.verdictOf('GP001', state());
  assert.equal(got.ready, true);
  assert.equal(got.row.Human_Verification_Status, 'CONFIRMED');
  assert.equal(got.row.Y_Tick_First_Value, '40');
  assert.equal(got.row.Y_Tick_Last_Value, '10');
  assert.equal(got.row.Seen_By_Person, '1');
});

/* REVERT: 오버레이를 보았다고 누르지 않아도 답으로 친다. 고르기만 한 줄이
 * "내가 이 그림을 보았다"는 진술로 나갑니다 - 이 페이지가 있는 이유입니다. */
test('오버레이를 봤다고 누르지 않으면 답이 아니다', () => {
  const got = L.verdictOf('GP001', state({ seen: false }));
  assert.equal(got.ready, false);
  assert.match(got.why, /직접 보셨다/);
  assert.equal(got.row, null);
});

/* REVERT: 이름 없이도 확인으로 친다. `proposal_problems`가 그 줄을
 * PROPOSAL_VERDICT_UNATTRIBUTED로 되돌려 보내는데, 그때는 사람이 이미
 * 페이지를 떠난 뒤입니다. */
test('누가 보았는지 없으면 확인이 아니다', () => {
  const got = L.verdictOf('GP001', state({ who: '   ' }));
  assert.equal(got.ready, false);
  assert.match(got.why, /누가 보았는지/);
});

/* REVERT: 리더가 읽지 못한 축도 확인으로 통과시킨다. 값 없는 CONFIRMED는
 * 계산이 되지 않고, 되지 않는 채로 통과하면 다음 사람은 있는 줄 압니다. */
test('리더가 읽지 못했으면 사람이 적어야 답이 된다', () => {
  const blank = L.verdictOf('GP002', unread());
  assert.equal(blank.ready, false);
  assert.match(blank.why, /첫 눈금과 끝 눈금/);
  const typed = L.verdictOf('GP002', unread({ first: '250', last: '0' }));
  assert.equal(typed.ready, true);
  assert.equal(typed.row.Y_Tick_First_Value, '250');
});

/* REVERT: 사람이 친 값보다 리더가 읽은 값을 앞에 둔다. 사람이 리더를 고치러
 * 친 숫자가 무시되고, 화면에는 고쳤다고 보입니다. */
test('사람이 적은 값이 리더가 읽은 값을 이긴다', () => {
  const got = L.verdictOf('GP001', state({ first: '50' }));
  assert.equal(got.row.Y_Tick_First_Value, '50');
  assert.equal(got.row.Y_Tick_Last_Value, '10');
  assert.equal(got.row.Value_Source, 'TYPED');
});
test('아무것도 고치지 않았으면 읽은 값 그대로라고 적힌다', () => {
  assert.equal(L.verdictOf('GP001', state()).row.Value_Source, 'READ');
});

/* REVERT: 숫자가 아닌 것도 눈금 값으로 받는다. 축이 "약 40"이라고 적힌
 * 제안은 계산에 들어가는 순간 0이 되거나 터집니다. */
test('숫자가 아닌 눈금 값은 답이 아니다', () => {
  assert.equal(L.verdictOf('GP002', unread({ first: '약 40', last: '0' })).ready, false);
});
/* REVERT: 첫 눈금과 끝 눈금이 같아도 받는다. 값/픽셀이 0인 축이고, 그 패널의
 * 모든 값이 같은 수로 나옵니다. */
test('첫 눈금과 끝 눈금이 같으면 축이 아니다', () => {
  const got = L.verdictOf('GP002', unread({ first: '10', last: '10.0' }));
  assert.equal(got.ready, false);
  assert.match(got.why, /축이 아닙니다/);
});

/* REVERT: 거절과 보류에도 눈금 값을 묻는다. 틀린 프레임의 눈금 값을 받아
 * 적는 것은 틀린 것을 더 자세히 적는 일이고, 사람을 거기 붙잡아 둡니다. */
test('거절과 보류는 눈금 값을 묻지 않는다', () => {
  const no = L.verdictOf('GP002', unread({ verdict: 'REJECTED' }));
  assert.equal(no.ready, true);
  assert.equal(no.row.Y_Tick_First_Value, '');
  assert.equal(no.row.Value_Source, '');
  assert.equal(L.verdictOf('GP002', unread({ verdict: 'HOLD' })).ready, true);
});

test('아직 고르지 않은 줄은 답이 아니다', () => {
  const got = L.verdictOf('GP001', state({ verdict: '' }));
  assert.equal(got.ready, false);
  assert.match(got.why, /아직 고르지/);
});
test('이 페이지가 받을 수 없는 답은 이름을 대며 거절한다', () => {
  const got = L.verdictOf('GP001', state({ verdict: 'MAYBE' }));
  assert.equal(got.ready, false);
  assert.match(got.why, /MAYBE/);
});

test('제안 이름은 상태가 들고 있는 것을 쓴다', () => {
  assert.equal(L.verdictOf('key', state({ proposal: 'GP007' })).row.Proposal_ID,
               'GP007');
});

test('csv는 답이 된 줄만 싣는다', () => {
  const csv = L.buildCsv(['GP001', 'GP002'],
                         { GP001: state(), GP002: state({ seen: false }) });
  const lines = csv.split('\n');
  assert.equal(lines.length, 2);
  assert.equal(lines[0], L.CSV_COLUMNS.join(','));
  assert.match(lines[1], /GP001/);
});
test('csv는 목록에 있는 이름만 싣는다', () => {
  assert.equal(L.buildCsv(['GP001'], { GP001: state(), GP009: state() })
               .split('\n').length, 2);
});
test('따옴표가 든 메모는 csv를 깨뜨리지 않는다', () => {
  const csv = L.buildCsv(['GP001'], { GP001: state({ note: '축이 "깨져" 있음' }) });
  assert.match(csv, /"축이 ""깨져"" 있음"/);
});

test('남은 일은 답이 안 된 제안을 센다', () => {
  assert.equal(L.remaining(['a', 'b', 'c'],
                           { a: state(), b: state({ seen: false }) }), 2);
});
test('보류는 남은 일이 아니라 따로 센다', () => {
  const st = { a: state({ verdict: 'HOLD' }), b: state() };
  assert.equal(L.remaining(['a', 'b'], st), 0);
  assert.equal(L.held(['a', 'b'], st), 1);
});

console.log('');
console.log(pass + '/' + (pass + fails.length) + ' passed');
if (fails.length) { console.log('FAILED: ' + fails.join(', ')); process.exit(1); }
