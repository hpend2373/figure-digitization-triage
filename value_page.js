/* 사람이 읽힌 값을 보고 내리는 판정. 화면은 값을 옮기기만 하고, 무엇이 답이
 * 되는지는 전부 여기 있습니다 - `geometry_page.js`와 같은 나눔입니다.
 *
 * `run_batch`는 `figure_values_machine_qc.csv`에서 멈춥니다. 그 파일은 기계가
 * 아무 잘못도 못 찾았다는 뜻이지, 표시가 어디에 앉았는지 누가 보았다는 뜻이
 * 아닙니다. 그 차이가 `finalize_batch`가 있는 까닭이고, 이 페이지는 그 문 앞에
 * 서서 사람의 답을 받습니다.
 *
 * 이 파일이 지키는 넷:
 *   1. 승인은 확인 칸이 전부 채워져야 승인입니다. `Decision`은 "동의한다"이고
 *      확인 칸은 "무엇을 보았는가"입니다 - 서로 다른 주장이고, 하나로 묶으면
 *      보지 않은 것에 동의한 줄이 생깁니다.
 *   2. 누가 보았는지 없는 판정은 판정이 아닙니다.
 *   3. 이 실행의 지문을 들고 있지 않은 줄은 어느 추출에 대한 답인지 모릅니다.
 *   4. `HOLD`는 답이지만 승인이 아닙니다.
 */

var DECISIONS = ['APPROVED', 'REJECTED', 'HOLD'];

//: 승인이 데리고 와야 하는 확인들. 어떤 실행 모드가 무엇을 묻는지는
//: `run_batch.REVIEW_CONFIRMATIONS`가 정하고, 페이지가 그것을 심어 줍니다 -
//: 여기 못 박아 두면 모드가 늘 때 화면과 관문이 서로 다른 것을 묻습니다.
var HELD = 'HOLD';
var APPROVED = 'APPROVED';

function requiredOf(state) {
  var r = (state || {}).required;
  return Object.prototype.toString.call(r) === '[object Array]' ? r : [];
}

function missingChecks(state) {
  var s = state || {}, need = requiredOf(s), out = [];
  for (var i = 0; i < need.length; i++) {
    if (!(s.checks || {})[need[i]]) out.push(need[i]);
  }
  return out;
}

/* 이 패널의 지금 상태가 답이 되는가, 안 되면 왜 안 되는가.
 *
 * `state` = { decision, checks, note, who, panel, subject, required }
 * 돌려주는 것 = { ready, why, row }
 */
function reviewOf(id, state) {
  var s = state || {};
  var decision = String(s.decision || '').trim().toUpperCase();
  var who = String(s.who || '').trim();
  var subject = String(s.subject || '').trim();
  if (!decision) return { ready: false, why: '아직 고르지 않았습니다', row: null };
  if (DECISIONS.indexOf(decision) < 0) {
    return { ready: false, why: '이 페이지가 받을 수 없는 답입니다: ' + decision, row: null };
  }
  if (!who) {
    return { ready: false, why: '누가 보았는지 적어 주세요 (등록된 검토자 ID)', row: null };
  }
  // 이 답이 어느 추출에 대한 것인가. 지문이 없으면 `finalize_batch`가 그것을
  // 다른 실행의 답과 구별하지 못합니다.
  if (!subject) {
    return { ready: false, why: '이 패널의 실행 지문이 없습니다 — 이 실행의 대기열에서 온 줄이 아닙니다', row: null };
  }
  // 승인은 확인 칸을 데리고 와야 합니다. 거절과 보류는 묻지 않습니다 - 잘못
  // 앉은 표시를 자세히 확인해 달라고 붙잡아 두는 일이기 때문입니다.
  var missing = decision === APPROVED ? missingChecks(s) : [];
  if (missing.length) {
    return { ready: false,
             why: '승인하려면 확인해야 하는 것이 남았습니다: ' + missing.join(', '),
             row: null };
  }
  var checks = {};
  var need = requiredOf(s);
  for (var i = 0; i < need.length; i++) {
    checks[need[i]] = (s.checks || {})[need[i]] ? 'TRUE' : 'FALSE';
  }
  return { ready: true, why: '', row: {
    Panel_ID: String(s.panel || id),
    Review_Subject_SHA256: subject,
    Reviewer_ID: who,
    Decision: decision,
    Marks_Checked: checks.Marks_Checked || '',
    Axis_Labels_Checked: checks.Axis_Labels_Checked || '',
    Calibration_Checked: checks.Calibration_Checked || '',
    Identity_Checked: checks.Identity_Checked || '',
    Inference_Checked: checks.Inference_Checked || '',
    Note: String(s.note || '').trim()
  } };
}

var CSV_COLUMNS = ['Review_ID', 'Panel_ID', 'Review_Subject_SHA256',
                   'Reviewer_ID', 'Decision', 'Marks_Checked',
                   'Axis_Labels_Checked', 'Calibration_Checked',
                   'Identity_Checked', 'Inference_Checked', 'Reviewed_At',
                   'Note'];

function csvCell(s) {
  return '"' + String(s === null || s === undefined ? '' : s)
    .replace(/"/g, '""') + '"';
}

/* 답이 된 줄만. `HOLD`도 나갑니다 - "아직 못 정하겠다"를 적어 두는 것과 아무
 * 말도 하지 않는 것은 다르고, `finalize_batch`에서 둘 다 승인이 아닙니다. */
function buildCsv(ids, states, when) {
  var lines = [CSV_COLUMNS.join(',')], n = 0;
  ids = (ids || []).slice().sort();
  for (var i = 0; i < ids.length; i++) {
    var got = reviewOf(ids[i], (states || {})[ids[i]]);
    if (!got.ready) continue;
    n += 1;
    // 본 날짜는 페이지를 만든 쪽이 줍니다. 브라우저의 시계가 아니라 -
    // 이 프로그램이 아는 것이 아니고, 아는 척하면 나중에 그 날짜가 증거가
    // 됩니다.
    got.row.Review_ID = 'R' + ('00' + n).slice(-3);
    got.row.Reviewed_At = String(when || '');
    var out = [];
    for (var c = 0; c < CSV_COLUMNS.length; c++) {
      out.push(csvCell(got.row[CSV_COLUMNS[c]]));
    }
    lines.push(out.join(','));
  }
  return lines.join('\n');
}

function remaining(ids, states) {
  var left = 0;
  for (var i = 0; i < ids.length; i++) {
    if (!reviewOf(ids[i], (states || {})[ids[i]]).ready) left++;
  }
  return left;
}

function held(ids, states) {
  var n = 0;
  for (var i = 0; i < ids.length; i++) {
    var got = reviewOf(ids[i], (states || {})[ids[i]]);
    if (got.ready && got.row.Decision === HELD) n++;
  }
  return n;
}

if (typeof module !== 'undefined' && module.exports) {
  module.exports = { DECISIONS: DECISIONS, HELD: HELD, APPROVED: APPROVED,
                     requiredOf: requiredOf, missingChecks: missingChecks,
                     reviewOf: reviewOf, buildCsv: buildCsv,
                     CSV_COLUMNS: CSV_COLUMNS, remaining: remaining, held: held };
}
