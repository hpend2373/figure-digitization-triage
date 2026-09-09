/* 사람이 그림을 보고 내리는 처분들. 화면은 값을 옮기기만 하고, 무엇이 답이
 * 되는지는 전부 여기 있습니다 - `errorbar_page.js`와 같은 나눔입니다.
 *
 * 이 파일이 지키는 둘:
 *   1. 그림을 직접 보았다고 누르지 않으면 그 줄은 답이 아닙니다.
 *   2. "일부 패널만"이라고 답하면서 어느 패널인지 적지 않으면 답이 아닙니다.
 *      어느 패널인지 모르는 "일부"는 다음 사람에게 아무 말도 하지 않습니다.
 */

//: 물음마다 받을 수 있는 처분. 물음이 다르면 받을 답도 다릅니다 - "셀 수
//: 없다"에 대해 `DATA`는 답이 아니고, 어긋난 캡션에 대해 `COUNTABLE`은
//: 답이 아닙니다.
var CHOICES = {
  UNCOUNTABLE: ['RECROP', 'NOT_DATA', 'COUNTABLE', 'HOLD'],
  MIXED: ['DATA', 'NOT_DATA', 'PARTIAL', 'HOLD'],
  CROP_DISPUTE: ['RECROP', 'NOT_DATA', 'HOLD']
};

//: 어느 패널인지 적어야만 답이 되는 처분.
var NEEDS_WHICH = ['PARTIAL'];

//: 아직 정하지 않았다는 답. 답이긴 하지만 다음으로 넘어가지 않습니다.
var HELD = 'HOLD';

function needsWhich(choice) {
  return NEEDS_WHICH.indexOf(String(choice || '').trim().toUpperCase()) >= 0;
}

/* 이 그림의 지금 상태가 답이 되는가, 안 되면 왜 안 되는가.
 *
 * `state` = { kind, choice, which, note, seen }
 * 돌려주는 것 = { ready, why, row }
 */
function decisionOf(id, state) {
  var s = state || {};
  var kind = String(s.kind || '').trim().toUpperCase();
  var choice = String(s.choice || '').trim().toUpperCase();
  var which = String(s.which || '').trim();
  var allowed = CHOICES[kind];
  if (!allowed) return { ready: false, why: '무엇을 묻는지 모르는 줄입니다: ' + (kind || '(빈칸)'), row: null };
  if (!choice) return { ready: false, why: '아직 고르지 않았습니다', row: null };
  if (allowed.indexOf(choice) < 0) {
    return { ready: false, why: '이 물음에 쓸 수 없는 답입니다: ' + choice, row: null };
  }
  if (needsWhich(choice) && !which) {
    return { ready: false, why: '어느 패널이 데이터인지 적어 주세요', row: null };
  }
  // THE ONE THING THIS PAGE EXISTS TO ASK. 고르는 것은 판단이고 이것은
  // 목격입니다. 둘을 한 번의 클릭으로 묶으면 고르기만 한 줄이 본 줄이 됩니다.
  if (!s.seen) {
    return { ready: false, why: '이 그림을 직접 보셨다고 눌러 주세요', row: null };
  }
  return { ready: true, why: '', row: {
    Draft_ID: String(s.draft || id),
    Question: kind,
    Decision: choice,
    Which_Panels: needsWhich(choice) ? which : '',
    Seen_By_Person: '1',
    Note: String(s.note || '').trim()
  } };
}

var CSV_COLUMNS = ['Draft_ID', 'Question', 'Decision', 'Which_Panels',
                   'Seen_By_Person', 'Note'];

function csvCell(s) {
  return '"' + String(s === null || s === undefined ? '' : s)
    .replace(/"/g, '""') + '"';
}

/* 답이 된 줄만. `HOLD`도 답이므로 나갑니다 - "아직 정하지 않았다"를 적어 두는
 * 것과 아무 말도 하지 않는 것은 다르고, 다음 사람은 그 차이를 알아야 합니다. */
function buildCsv(ids, states) {
  var lines = [CSV_COLUMNS.join(',')];
  ids = (ids || []).slice().sort();
  for (var i = 0; i < ids.length; i++) {
    var got = decisionOf(ids[i], (states || {})[ids[i]]);
    if (!got.ready) continue;
    var out = [];
    for (var c = 0; c < CSV_COLUMNS.length; c++) {
      out.push(csvCell(got.row[CSV_COLUMNS[c]]));
    }
    lines.push(out.join(','));
  }
  return lines.join('\n');
}

/* 아직 답이 안 된 그림의 수. `HOLD`는 답이므로 남은 일이 아닙니다 - 사람이
 * 보고 "아직 못 정하겠다"고 말한 것도 그 그림에 대해 한 일입니다. */
function remaining(ids, states) {
  var left = 0;
  for (var i = 0; i < ids.length; i++) {
    if (!decisionOf(ids[i], (states || {})[ids[i]]).ready) left++;
  }
  return left;
}

/* 아직 정하지 않겠다고 적어 둔 그림의 수. 화면 위에서 남은 일과 따로 셉니다. */
function held(ids, states) {
  var n = 0;
  for (var i = 0; i < ids.length; i++) {
    var got = decisionOf(ids[i], (states || {})[ids[i]]);
    if (got.ready && got.row.Decision === HELD) n++;
  }
  return n;
}

if (typeof module !== 'undefined' && module.exports) {
  module.exports = { CHOICES: CHOICES, NEEDS_WHICH: NEEDS_WHICH, HELD: HELD,
                     needsWhich: needsWhich, decisionOf: decisionOf,
                     buildCsv: buildCsv, CSV_COLUMNS: CSV_COLUMNS,
                     remaining: remaining, held: held };
}
