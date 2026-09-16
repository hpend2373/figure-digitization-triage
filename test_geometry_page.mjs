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

/* 리더가 읽어 낸 제안. 이 페이지의 흔한 줄이고, 사람이 할 일은 보는 것뿐입니다.
 * 눈금은 넷인데 리더는 위의 셋만 읽었습니다 - 이 코퍼스의 실제 모양이고,
 * 값과 픽셀을 따로 다루면 바로 여기서 어긋납니다. */
function state(over) {
  return Object.assign({ verdict: 'CONFIRMED', top: '', bottom: '', note: '',
                         seen: true, who: 'MC', proposal: 'GP001',
                         readPairs: '40@100;30@200;20@300',
                         topPixel: 100, bottomPixel: 400 }, over || {});
}

/* 리더가 거절한 제안. 여기서만 사람이 숫자를 칩니다. */
function unread(over) {
  return state(Object.assign({ readPairs: '' }, over || {}));
}

test('읽힌 제안은 보기만 해도 답이 된다', () => {
  const got = L.verdictOf('GP001', state());
  assert.equal(got.ready, true);
  assert.equal(got.row.Human_Verification_Status, 'CONFIRMED');
  assert.equal(got.row.Y_Tick_Top_Value, '40');
  assert.equal(got.row.Y_Tick_Bottom_Value, '20');
  assert.equal(got.row.Seen_By_Person, '1');
});

/* REVERT: 리더가 읽은 값을 맨 위·맨 아래 눈금 픽셀과 짝지운다. 리더의 사다리가
 * 눈금 전부를 읽었다는 보장이 없습니다 - FIG9에서 6개 중 5개, 5개 중 3개를
 * 읽었고, 그 값을 양 끝 픽셀과 짝지으니 축척이 20%와 50% 어긋났습니다.
 * 잔차는 0.1px이었고 아무 데서도 걸리지 않았습니다. */
test('리더의 값은 리더가 읽은 픽셀과 짝지어 나간다', () => {
  const got = L.verdictOf('GP001', state());
  assert.equal(got.row.Confirmed_Tick_Values, '40@100;20@300');
  assert.equal(got.row.Value_Source, 'READ');
});

/* REVERT: 사람이 친 값도 짝 없이 값만 내보낸다. 어느 눈금의 값인지 다음
 * 단계가 짐작해야 하고, 그 짐작이 두 번째 결함이었습니다. */
test('사람이 친 값은 맨 위·맨 아래 눈금과 짝지어 나간다', () => {
  const got = L.verdictOf('GP002', unread({ top: '250', bottom: '0' }));
  assert.equal(got.ready, true);
  assert.equal(got.row.Confirmed_Tick_Values, '250@100;0@400');
  assert.equal(got.row.Value_Source, 'TYPED');
});
test('값을 붙일 눈금 행이 없으면 답이 아니다', () => {
  const got = L.verdictOf('GP002', unread({ top: '250', bottom: '0',
                                            topPixel: '', bottomPixel: '' }));
  assert.equal(got.ready, false);
  assert.match(got.why, /눈금 행이 없습니다/);
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
  assert.match(blank.why, /맨 위 눈금과 맨 아래 눈금/);
});

/* REVERT: 사람이 친 값보다 리더가 읽은 값을 앞에 둔다. 사람이 리더를 고치러
 * 친 숫자가 무시되고, 화면에는 고쳤다고 보입니다. */
test('사람이 적은 값이 리더가 읽은 값을 이긴다', () => {
  const got = L.verdictOf('GP001', state({ top: '50', bottom: '10' }));
  assert.equal(got.row.Y_Tick_Top_Value, '50');
  assert.equal(got.row.Confirmed_Tick_Values, '50@100;10@400');
  assert.equal(got.row.Value_Source, 'TYPED');
});
test('아무것도 고치지 않았으면 읽은 값 그대로라고 적힌다', () => {
  assert.equal(L.verdictOf('GP001', state()).row.Value_Source, 'READ');
});

/* REVERT: 리더가 읽은 방향과 사람이 적은 방향이 어긋나도 받는다. "첫/끝"이라고
 * 물었을 때 FIG9 여섯 패널이 전부 뒤집혀 돌아왔고, 문 넷을 다 지났습니다.
 * 뒤집힌 축은 이 코퍼스에 실제로 있어서 뒤집힘 자체는 막을 수 없지만, 기계와
 * 사람이 같은 축을 반대로 읽었다면 둘 중 하나가 틀렸습니다. */
test('리더와 방향이 어긋나면 답이 아니다', () => {
  const got = L.verdictOf('GP001', state({ top: '20', bottom: '40' }));
  assert.equal(got.ready, false);
  assert.match(got.why, /반대입니다/);
});
test('리더가 읽지 못한 축은 방향을 견줄 데가 없다', () => {
  assert.equal(L.verdictOf('GP002', unread({ top: '0', bottom: '250' })).ready, true);
});
test('리더도 뒤집혀 읽었으면 뒤집힌 답이 통과한다', () => {
  const inverted = state({ readPairs: '20@100;30@200;40@300',
                           top: '20', bottom: '40' });
  assert.equal(L.verdictOf('GP001', inverted).ready, true);
});

/* 음수 축. 이 코퍼스에 -10 .. -40, -1 .. -0.3 같은 축이 실제로 있고, 부호를
 * 잃는 순간 그 패널의 모든 값이 뒤집힙니다. 친 값도, 읽은 값도 부호째 나가야
 * 합니다. */
test('사람이 친 음수 눈금 값은 부호째 답이 된다', () => {
  const got = L.verdictOf('GP002', unread({ top: '0', bottom: '-40' }));
  assert.equal(got.ready, true, got.why);
  assert.equal(got.row.Y_Tick_Bottom_Value, '-40');
  assert.equal(got.row.Confirmed_Tick_Values, '0@100;-40@400');
});
test('리더가 읽은 음수 눈금 값도 부호째 답이 된다', () => {
  const got = L.verdictOf('GP001', state({ readPairs: '-10@100;-20@200;-30@300' }));
  assert.equal(got.ready, true, got.why);
  assert.equal(got.row.Y_Tick_Top_Value, '-10');
  assert.equal(got.row.Y_Tick_Bottom_Value, '-30');
  assert.equal(got.row.Confirmed_Tick_Values, '-10@100;-30@300');
});

/* REVERT: 숫자가 아닌 것도 눈금 값으로 받는다. 축이 "약 40"이라고 적힌
 * 제안은 계산에 들어가는 순간 0이 되거나 터집니다. */
test('숫자가 아닌 눈금 값은 답이 아니다', () => {
  assert.equal(L.verdictOf('GP002', unread({ top: '약 40', bottom: '0' })).ready, false);
});
/* REVERT: 맨 위와 맨 아래가 같아도 받는다. 값/픽셀이 0인 축이고, 그 패널의
 * 모든 값이 같은 수로 나옵니다. */
test('맨 위와 맨 아래가 같으면 축이 아니다', () => {
  const got = L.verdictOf('GP002', unread({ top: '10', bottom: '10.0' }));
  assert.equal(got.ready, false);
  assert.match(got.why, /축이 아닙니다/);
});

/* REVERT: 거절과 보류에도 눈금 값을 묻는다. 틀린 프레임의 눈금 값을 받아
 * 적는 것은 틀린 것을 더 자세히 적는 일이고, 사람을 거기 붙잡아 둡니다. */
test('거절과 보류는 눈금 값을 묻지 않는다', () => {
  const no = L.verdictOf('GP002', unread({ verdict: 'REJECTED' }));
  assert.equal(no.ready, true);
  assert.equal(no.row.Y_Tick_Top_Value, '');
  assert.equal(no.row.Confirmed_Tick_Values, '');
  assert.equal(no.row.Value_Source, '');
  assert.equal(L.verdictOf('GP002', unread({ verdict: 'HOLD' })).ready, true);
});

/* 축을 나눠 쓰는 패널. 이 코퍼스는 한 줄의 패널에 y축을 맨 왼쪽 하나만 찍고
 * 나머지엔 눈금도 라벨도 없습니다. 그 패널은 읽을 것도 칠 것도 없고, 사람이
 * 할 수 있는 말은 "p7의 축을 쓴다"뿐입니다. 값은 관문이 옮겨 적습니다. */
function shared(over) {
  return unread(Object.assign({ verdict: 'SHARED', proposal: 'GP002',
                                sharedWith: 'GP001', siblings: ['GP001', 'GP003'] },
                              over || {}));
}
test('다른 패널의 축을 쓴다는 답은 값 없이 답이 된다', () => {
  const got = L.verdictOf('GP002', shared());
  assert.equal(got.ready, true, got.why);
  assert.equal(got.row.Human_Verification_Status, 'SHARED');
  assert.equal(got.row.Y_Axis_Shared_With, 'GP001');
  assert.equal(got.row.Y_Tick_Top_Value, '');
  assert.equal(got.row.Confirmed_Tick_Values, '');
  assert.equal(got.row.Value_Source, 'SHARED');
});
/* REVERT: 어느 패널인지 없어도 받는다. 관문이 옮겨 올 짝이 없습니다. */
test('어느 패널의 축인지 없으면 답이 아니다', () => {
  const got = L.verdictOf('GP002', shared({ sharedWith: '' }));
  assert.equal(got.ready, false);
  assert.match(got.why, /어느 패널/);
});
/* REVERT: 자기 자신을 받는다. 옮겨 올 곳이 자기라서 영원히 값이 없습니다. */
test('자기 자신의 축은 공유가 아니다', () => {
  assert.equal(L.verdictOf('GP002', shared({ sharedWith: 'GP002',
                                             siblings: ['GP001', 'GP002', 'GP003'] })).ready, false);
  // 형제 목록이 없어도(예: 저장된 상태를 되읽을 때) 자기 자신은 막힙니다.
  assert.equal(L.verdictOf('GP002', shared({ sharedWith: 'GP002', siblings: [] })).ready, false);
});
/* REVERT: 다른 그림의 패널도 받는다. 픽셀 행은 래스터의 것이라 옮겨 올 수
 * 없고, 옮기면 엉뚱한 행에 값이 붙습니다. */
test('같은 그림의 패널만 축을 나눠 쓴다', () => {
  const got = L.verdictOf('GP002', shared({ sharedWith: 'GP009' }));
  assert.equal(got.ready, false);
  assert.match(got.why, /같은 그림/);
});
/* REVERT: 공유하면서 값도 적어 온 것을 받는다. 어느 쪽이 답인지 모릅니다. */
test('축을 빌리면서 값도 적으면 답이 아니다', () => {
  const got = L.verdictOf('GP002', shared({ top: '40' }));
  assert.equal(got.ready, false);
  assert.match(got.why, /값을 지우거나/);
});
test('축을 빌린 줄은 CSV에 어느 패널인지와 함께 나간다', () => {
  const csv = L.buildCsv(['GP002'], { GP002: shared() });
  const lines = csv.split('\n');
  assert.ok(L.CSV_COLUMNS.indexOf('Y_Axis_Shared_With') >= 0);
  assert.ok(lines[1].indexOf('"SHARED"') >= 0 && lines[1].indexOf('"GP001"') >= 0, lines[1]);
});
/* 값을 확인한 줄은 공유 칸이 비어 나갑니다 - 하나이거나 다른 하나입니다. */
test('값을 확인한 줄에는 공유 칸이 비어 있다', () => {
  assert.equal(L.verdictOf('GP001', state({ sharedWith: 'GP003' })).row.Y_Axis_Shared_With, '');
});

/* 사람이 그림에 찍은 눈금. 리더가 눈금을 못 잰 패널 - 프레임은 맞는데
 * 눈금이 안 잡히거나 아예 없는 것 - 은 값을 붙일 행이 없어서 막혔습니다.
 * 975장 중 108장. 사람이 맨 위·맨 아래 눈금을 그림에 찍으면 그 행에 값이
 * 붙습니다. */
function noticks(over) {
  return unread(Object.assign({ topPixel: '', bottomPixel: '',
                                frameTop: 100, frameBottom: 500 }, over || {}));
}
test('눈금 행이 없는 제안은 찍어 달라고 말한다', () => {
  const got = L.verdictOf('GP002', noticks({ top: '40', bottom: '0' }));
  assert.equal(got.ready, false);
  assert.match(got.why, /찍어 주세요/);
});
test('찍은 두 줄에 친 값이 붙는다', () => {
  const got = L.verdictOf('GP002', noticks({ top: '40', bottom: '0',
                                             pickedTopPixel: 120, pickedBottomPixel: 480 }));
  assert.equal(got.ready, true, got.why);
  assert.equal(got.row.Confirmed_Tick_Values, '40@120;0@480');
  assert.equal(got.row.Value_Source, 'TYPED_PICKED');
});
/* REVERT: 잰 눈금이 있으면 찍은 줄을 무시한다. 잰 눈금이 틀린 자리에
 * 있어서(프레임 선을 눈금으로 잰 것) 사람이 다시 찍은 것인데 잰 것에
 * 붙습니다. */
test('찍은 줄은 잰 눈금보다 앞선다', () => {
  const got = L.verdictOf('GP002', unread({ top: '40', bottom: '0', frameTop: 100, frameBottom: 500,
                                            pickedTopPixel: 130, pickedBottomPixel: 470 }));
  assert.equal(got.row.Confirmed_Tick_Values, '40@130;0@470');
});
test('한 줄만 찍었으면 잰 눈금에 붙는다', () => {
  const got = L.verdictOf('GP002', unread({ top: '40', bottom: '0', pickedTopPixel: 130 }));
  assert.equal(got.ready, true, got.why);
  assert.equal(got.row.Confirmed_Tick_Values, '40@100;0@400');
  assert.equal(got.row.Value_Source, 'TYPED');
});
/* REVERT: 같은 행에 두 번 찍은 것을 받는다. 축척이 0으로 나뉩니다. */
test('찍은 두 줄이 같은 행이면 답이 아니다', () => {
  const got = L.verdictOf('GP002', noticks({ top: '40', bottom: '0',
                                             pickedTopPixel: 300, pickedBottomPixel: 300 }));
  assert.equal(got.ready, false);
  assert.match(got.why, /같은 행/);
});
/* REVERT: 프레임 밖에 찍은 줄을 받는다. 프레임이 제목 상자에 잡힌 패널에서
 * 사람이 진짜 축을 찍으면, 틀린 프레임에 맞는 눈금이 붙어 "맞다"로 나갑니다.
 * 프레임이 틀린 것의 답은 "틀렸다"입니다. */
test('프레임 밖에 찍은 줄은 답이 아니다', () => {
  const got = L.verdictOf('GP002', noticks({ top: '40', bottom: '0',
                                             pickedTopPixel: 20, pickedBottomPixel: 480 }));
  assert.equal(got.ready, false);
  assert.match(got.why, /프레임 밖/);
});
test('프레임 선 바로 위아래는 프레임 안이다', () => {
  assert.equal(L.rowsInsideFrame(95, 505, 100, 500), true);
  assert.equal(L.rowsInsideFrame(40, 505, 100, 500), false);
  // 프레임을 모르는 상태(옛 저장)는 묻지 않습니다
  assert.equal(L.rowsInsideFrame(40, 505, '', ''), true);
});

/* REVERT: 만들어진 축이 어느 쪽으로 커지는지 되읽어 주지 않는다. 리더가 읽지
 * 못한 축에서는 방향을 견줄 데가 없어서 막을 근거도 없고, 그러면 남는 방법은
 * 사람이 자기가 방금 무엇을 말했는지 보는 것뿐입니다. */
test('만들어진 축의 방향을 사람이 읽을 말로 되읽어 준다', () => {
  assert.equal(L.directionWord(L.parsePairs('40@100;20@300')), '위로 갈수록 커지는 축');
  assert.equal(L.directionWord(L.parsePairs('20@100;40@300')), '아래로 갈수록 커지는 축');
  assert.equal(L.directionWord(L.parsePairs('')), '');
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
