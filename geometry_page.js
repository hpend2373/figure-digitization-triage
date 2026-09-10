/* 사람이 기하 제안을 보고 내리는 판정. 화면은 값을 옮기기만 하고, 무엇이 답이
 * 되는지는 전부 여기 있습니다 - `errorbar_page.js`·`decision_page.js`와 같은
 * 나눔입니다.
 *
 * `geometry_proposer`는 프레임과 눈금 픽셀을 재고, 축이 무어라고 적혀 있는지도
 * 읽습니다. 읽은 것은 `Y_Tick_Read_*`에 있고 사람의 칸에는 없습니다. 이 페이지가
 * 하는 일은 그 둘을 잇는 것입니다: 사람이 그림을 보고 "읽은 대로 맞다"고 하면
 * 읽은 값이 사람의 칸으로 건너가고, 아니면 사람이 직접 적습니다.
 *
 * 묻는 것은 **맨 위 눈금**과 **맨 아래 눈금**입니다. "첫/끝"이라고 물었을 때
 * FIG9 여섯 패널이 전부 뒤집혀 돌아왔습니다 - 축은 아래에서 시작하니 아래부터
 * 적는 것이 자연스럽고, 계산은 위부터 짝지었습니다. 물음이 위치를 말하면
 * 애매한 데가 없습니다.
 *
 * 이 파일이 지키는 다섯:
 *   1. 오버레이를 직접 보았다고 누르지 않으면 그 줄은 답이 아닙니다.
 *   2. 확인은 이름을 대야 확인입니다. 누가 보았는지 없는 확인은 확인이 아닙니다.
 *   3. `CONFIRMED`인데 눈금 값이 없으면 답이 아닙니다 - 값 없는 기하는 계산이
 *      되지 않고, 되지 않는 채로 통과하면 다음 사람은 그것이 있는 줄 압니다.
 *   4. 맨 위 눈금과 맨 아래 눈금이 같으면 축이 아닙니다.
 *   5. 리더가 읽은 방향과 사람이 적은 방향이 반대이면 답이 아닙니다. 뒤집힌
 *      축은 이 코퍼스에 실제로 있어서 뒤집힘 자체는 막을 수 없지만, 기계와
 *      사람이 같은 축을 반대로 읽었다면 둘 중 하나가 틀렸습니다.
 */

//: 사람이 이 제안에 대해 할 수 있는 말. `HOLD`는 "아직 못 정하겠다"이고,
//: 답이긴 하지만 다음으로 넘어가지 않습니다.
var VERDICTS = ['CONFIRMED', 'REJECTED', 'HOLD'];

//: 눈금 값이 있어야만 답이 되는 판정. 거절과 보류는 값을 묻지 않습니다 -
//: 틀린 프레임의 눈금 값을 받아 적는 것은 틀린 것을 더 자세히 적는 일입니다.
var NEEDS_VALUES = ['CONFIRMED'];

var HELD = 'HOLD';

function needsValues(verdict) {
  return NEEDS_VALUES.indexOf(String(verdict || '').trim().toUpperCase()) >= 0;
}

/* 사람이 칸을 비워 두었으면 리더가 읽은 값. 비워 둔 것은 "읽은 대로"라는 뜻이고,
 * 적어 넣은 것은 "리더가 틀렸고 이것이 맞다"는 뜻입니다.
 *
 * 리더가 읽지 못한 제안에는 넘겨줄 것이 없어서 빈 채로 옵니다 - 그러면 3번
 * 문에 걸리고, 그것이 이 페이지에서 사람이 실제로 타이핑해야 하는 유일한
 * 자리입니다. */
function valueOf(typed, read) {
  var t = String(typed === null || typed === undefined ? '' : typed).trim();
  return t !== '' ? t : String(read === null || read === undefined ? '' : read).trim();
}

function isNumber(v) {
  return v !== '' && isFinite(Number(v));
}

/* 'v@px;v@px' -> [[v,px],...]. 리더가 읽은 짝도, 사람이 확인한 짝도 같은 모양
 * 입니다 - 계산이 쓰는 것은 값이 아니라 값과 그 값이 붙은 픽셀 행입니다. */
function parsePairs(text) {
  var out = [];
  var parts = String(text === null || text === undefined ? '' : text).split(';');
  for (var i = 0; i < parts.length; i++) {
    if (parts[i].indexOf('@') < 0) continue;
    var bits = parts[i].split('@');
    var v = Number(bits[0]), px = Number(bits[1]);
    if (isFinite(v) && isFinite(px)) out.push([v, px]);
  }
  return out;
}

/* 값이 픽셀 행을 따라 커지는가 작아지는가. +1이면 아래로 갈수록 커지고(뒤집힌
 * 축), -1이면 위로 갈수록 커집니다(보통). 0이면 기울기를 알 수 없습니다. */
function slopeSign(pairs) {
  if (!pairs || pairs.length < 2) return 0;
  var a = pairs[0], b = pairs[pairs.length - 1];
  if (a[1] === b[1] || a[0] === b[0]) return 0;
  return (b[0] - a[0]) / (b[1] - a[1]) > 0 ? 1 : -1;
}

/* 이 축이 어느 쪽으로 커지는지, 사람이 읽을 말로.
 *
 * 리더가 읽지 못한 축에서는 방향을 견줄 데가 없습니다 - 사람이 적은 것이
 * 유일한 진술이고, 그것이 뒤집혀도 막을 근거가 없습니다. 그래서 막는 대신
 * **되읽어 줍니다**: 자기가 방금 무슨 축을 만들었는지 글자로 보면, 위아래를
 * 바꿔 적은 것은 눈에 걸립니다.
 */
function directionWord(pairs) {
  var sign = slopeSign(pairs);
  if (!sign) return '';
  return sign < 0 ? '위로 갈수록 커지는 축' : '아래로 갈수록 커지는 축';
}

/* 이 제안의 지금 상태가 답이 되는가, 안 되면 왜 안 되는가.
 *
 * `state` = { verdict, top, bottom, note, seen, who,
 *             readPairs, topPixel, bottomPixel }
 *   readPairs   리더가 읽은 '값@픽셀' 문자열. 비어 있으면 리더가 거절한 축.
 *   topPixel    맨 위 눈금의 픽셀 행. 사람이 값을 적으면 그 값이 붙는 자리.
 *   bottomPixel 맨 아래 눈금의 픽셀 행.
 *
 * 돌려주는 것 = { ready, why, row }
 */
function verdictOf(id, state) {
  var s = state || {};
  var verdict = String(s.verdict || '').trim().toUpperCase();
  var who = String(s.who || '').trim();
  if (!verdict) return { ready: false, why: '아직 고르지 않았습니다', row: null };
  if (VERDICTS.indexOf(verdict) < 0) {
    return { ready: false, why: '이 페이지가 받을 수 없는 답입니다: ' + verdict, row: null };
  }
  // 목격. 고르는 것은 판단이고 이것은 본 일입니다. 둘을 한 클릭으로 묶으면
  // 그림을 안 열고 고른 줄이 본 줄이 됩니다.
  if (!s.seen) {
    return { ready: false, why: '이 오버레이를 직접 보셨다고 눌러 주세요', row: null };
  }
  // 이름. `geometry_proposer.proposal_problems`가 지키는 것과 같은 문이고,
  // 여기서 먼저 막는 것은 사람이 그 자리에서 고칠 수 있기 때문입니다.
  if (!who) {
    return { ready: false, why: '누가 보았는지 적어 주세요 (이름 또는 이니셜)', row: null };
  }
  var read = parsePairs(s.readPairs);
  var top = '', bottom = '', pairs = [], source = '';
  if (needsValues(verdict)) {
    var typedTop = String(s.top === null || s.top === undefined ? '' : s.top).trim();
    var typedBottom = String(s.bottom === null || s.bottom === undefined ? '' : s.bottom).trim();
    var typed = typedTop !== '' || typedBottom !== '';
    if (!typed && read.length >= 2) {
      // 리더가 읽은 그대로. 짝은 리더의 것을 씁니다 - 리더가 맨 위·맨 아래
      // 눈금을 읽었다는 보장이 없고, 그 값을 맨 위·맨 아래 픽셀과 짝지으면
      // 축척이 조용히 어긋납니다.
      pairs = [read[0], read[read.length - 1]];
      top = String(pairs[0][0]);
      bottom = String(pairs[1][0]);
      source = 'READ';
    } else {
      if (!isNumber(typedTop) || !isNumber(typedBottom)) {
        return { ready: false,
                 why: '맨 위 눈금과 맨 아래 눈금이 무엇인지 적어 주세요 - 리더가 읽지 못했습니다',
                 row: null };
      }
      if (!isNumber(s.topPixel) || !isNumber(s.bottomPixel)
          || Number(s.topPixel) === Number(s.bottomPixel)) {
        return { ready: false, why: '이 제안에는 값을 붙일 눈금 행이 없습니다', row: null };
      }
      top = typedTop;
      bottom = typedBottom;
      pairs = [[Number(top), Number(s.topPixel)],
               [Number(bottom), Number(s.bottomPixel)]];
      source = 'TYPED';
    }
    if (Number(top) === Number(bottom)) {
      return { ready: false, why: '맨 위 눈금과 맨 아래 눈금이 같으면 축이 아닙니다', row: null };
    }
    // 방향. 기계와 사람이 같은 축을 반대로 읽었으면 둘 중 하나가 틀렸고,
    // 어느 쪽이든 그대로 적으면 그 패널의 모든 값이 뒤집힙니다. 뒤집힌 축은
    // 이 코퍼스에 실제로 있으니 뒤집힘 자체는 막지 않습니다 - 막는 것은
    // **어긋남**입니다.
    var mine = slopeSign(pairs), theirs = slopeSign(read);
    if (mine && theirs && mine !== theirs) {
      return { ready: false, why: theirs < 0
        ? '리더는 위로 갈수록 값이 커진다고 읽었는데, 적으신 값은 반대입니다 — 맨 위와 맨 아래가 바뀌지 않았는지 보아 주세요'
        : '리더는 아래로 갈수록 값이 커진다고 읽었는데, 적으신 값은 반대입니다 — 맨 위와 맨 아래가 바뀌지 않았는지 보아 주세요',
        row: null };
    }
  }
  return { ready: true, why: '', row: {
    Proposal_ID: String(s.proposal || id),
    Human_Verification_Status: verdict,
    Y_Tick_Top_Value: top,
    Y_Tick_Bottom_Value: bottom,
    // 계산이 실제로 쓰는 것. 값만 넘기면 어느 눈금의 값인지 다음 단계가
    // 짐작해야 하고, 그 짐작이 두 번째 결함이었습니다.
    Confirmed_Tick_Values: pairs.map(function (p) {
      return p[0] + '@' + p[1];
    }).join(';'),
    Verified_By: who,
    Seen_By_Person: '1',
    // 사람이 직접 친 값인가, 리더가 읽은 값을 그대로 둔 것인가. 둘 다 사람이
    // 보고 통과시킨 값이지만 같은 일은 아니고, 리더가 얼마나 맞았는지는 이
    // 칸으로만 셀 수 있습니다.
    Value_Source: source,
    Note: String(s.note || '').trim()
  } };
}

var CSV_COLUMNS = ['Proposal_ID', 'Human_Verification_Status',
                   'Y_Tick_Top_Value', 'Y_Tick_Bottom_Value',
                   'Confirmed_Tick_Values',
                   'Verified_By', 'Seen_By_Person', 'Value_Source', 'Note'];

function csvCell(s) {
  return '"' + String(s === null || s === undefined ? '' : s)
    .replace(/"/g, '""') + '"';
}

/* 답이 된 줄만. `HOLD`도 답이므로 나갑니다 - "아직 못 정하겠다"를 적어 두는
 * 것과 아무 말도 하지 않는 것은 다르고, 다음 사람은 그 차이를 알아야 합니다. */
function buildCsv(ids, states) {
  var lines = [CSV_COLUMNS.join(',')];
  ids = (ids || []).slice().sort();
  for (var i = 0; i < ids.length; i++) {
    var got = verdictOf(ids[i], (states || {})[ids[i]]);
    if (!got.ready) continue;
    var out = [];
    for (var c = 0; c < CSV_COLUMNS.length; c++) {
      out.push(csvCell(got.row[CSV_COLUMNS[c]]));
    }
    lines.push(out.join(','));
  }
  return lines.join('\n');
}

/* 아직 답이 안 된 제안의 수. `HOLD`는 답이므로 남은 일이 아닙니다. */
function remaining(ids, states) {
  var left = 0;
  for (var i = 0; i < ids.length; i++) {
    if (!verdictOf(ids[i], (states || {})[ids[i]]).ready) left++;
  }
  return left;
}

/* 아직 정하지 않겠다고 적어 둔 제안의 수. 남은 일과 따로 셉니다. */
function held(ids, states) {
  var n = 0;
  for (var i = 0; i < ids.length; i++) {
    var got = verdictOf(ids[i], (states || {})[ids[i]]);
    if (got.ready && got.row.Human_Verification_Status === HELD) n++;
  }
  return n;
}

if (typeof module !== 'undefined' && module.exports) {
  module.exports = { VERDICTS: VERDICTS, NEEDS_VALUES: NEEDS_VALUES, HELD: HELD,
                     needsValues: needsValues, valueOf: valueOf,
                     parsePairs: parsePairs, slopeSign: slopeSign,
                     directionWord: directionWord,
                     verdictOf: verdictOf, buildCsv: buildCsv,
                     CSV_COLUMNS: CSV_COLUMNS, remaining: remaining, held: held };
}
