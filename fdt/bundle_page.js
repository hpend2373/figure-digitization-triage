/* 남은 결정 묶음 페이지(`bundle_page.py`)에서 무엇이 답이 되는가. 화면은 값을
 * 옮기기만 하고, 답이 되는 규칙은 전부 여기 있습니다 - `decision_page.js`와
 * 같은 나눔입니다.
 *
 * 이 페이지는 두 종류의 답을 받습니다(`approval.py`):
 *
 *   본 답        사람이 "직접 보았다"를 누른 줄. Seen_By_Person=1.
 *   승인된 관찰  사람이 보지 않고, 제안을 그대로 고른 줄. Seen_By_Person=0,
 *                Observed_By = 그 제안을 낸 것(항목마다 페이지가 심어 둠),
 *                Approval_Ref = 이 답 파일과 승인한 사람과 날짜.
 *
 * 이 파일이 지키는 넷:
 *   1. 제안과 다른 답은 "직접 보았다" 없이는 답이 아닙니다. 사람이 보지 않고
 *      고른 다른 답은 누구의 관찰도 아닙니다 - 제안을 낸 것은 그렇게 보지 않았고,
 *      사람은 보지 않았습니다.
 *   2. 승인된 관찰에는 본 것(Observed_By)이 있어야 하고, 그것이 승인한 사람과
 *      같으면 안 됩니다(`approval.OBSERVER_IS_APPROVER`).
 *   3. 이름을 고친 답(EDIT)은 고친 글이 있어야 하고, 사람이 쓴 글이므로 늘 본 답입니다.
 *   4. "제안대로 채우기"는 빈 칸만 채웁니다. 사람이 고른 답을 제안으로 덮으면
 *      그 줄은 사람이 고르지 않은 승인이 됩니다.
 */

var HOLD = 'HOLD';
var EDIT = 'EDIT';

var CSV_COLUMNS = ['Item', 'Section', 'Target_ID', 'Proposal', 'Decision', 'Text', 'Unit',
                   'Seen_By_Person', 'Verified_By', 'Observed_By', 'Approval_Ref',
                   'Decided_On', 'Item_SHA256', 'Image_SHA256', 'Note'];

function clean(v) { return String(v === null || v === undefined ? '' : v).trim(); }

function optionValues(item) {
  var out = [];
  var opts = (item && item.options) || [];
  for (var i = 0; i < opts.length; i++) out.push(String(opts[i][0]));
  return out;
}

/* 고친 이름이 제안과 다른가. 단위만 고쳐도 고친 것입니다. */
function edited(item, state) {
  var t = item.text || {};
  return clean(state.text) !== clean(t.value) || clean(state.unit) !== clean(t.unit);
}

/* 이 항목의 지금 상태가 답이 되는가, 안 되면 왜 안 되는가.
 *
 *   item  = { id, sec, target, options: [[값, 말, 효과]], proposal, observed_by,
 *             text: {value, unit} 또는 null, sha, img_sha }
 *   state = { choice, seen, text, unit, note, on }
 *   ctx   = { who, file }
 *   돌려주는 것 = { ready, why, row, approved }
 */
function answerOf(item, state, ctx) {
  var s = state || {}, c = ctx || {};
  var choice = clean(s.choice).toUpperCase();
  var who = clean(c.who);
  if (!item || !item.id) return { ready: false, why: '무엇을 묻는지 모르는 줄입니다', row: null };
  if (!choice) return { ready: false, why: '아직 고르지 않았습니다', row: null };
  if (optionValues(item).indexOf(choice) < 0) {
    return { ready: false, why: '이 항목에 없는 답입니다: ' + choice, row: null };
  }
  if (!who) return { ready: false, why: '맨 위에 이름을 적어 주세요', row: null };
  var text = '', unit = '';
  if (choice === EDIT) {
    if (!item.text) return { ready: false, why: '고칠 이름이 없는 항목입니다', row: null };
    text = clean(s.text); unit = clean(s.unit);
    if (!text) return { ready: false, why: '고친 이름을 적어 주세요', row: null };
    if (!edited(item, s)) return { ready: false, why: '이름이 제안과 같습니다 — 제안대로를 고르세요', row: null };
  } else if (item.text && choice !== HOLD && optionHasText(item, choice)) {
    text = clean(item.text.value); unit = clean(item.text.unit);
  }
  var seen = !!s.seen, approved = false, observed = '', ref = '', sp = '';
  if (choice === HOLD) {
    // 보류는 답이지만 아무것도 적지 않습니다. 누가 보았는지를 주장하지 않습니다.
    sp = '';
  } else if (seen) {
    sp = '1';
  } else {
    // THE LINE THIS PAGE EXISTS FOR. 보지 않고 고른 답은 제안 그대로일 때만
    // 승인이 됩니다. 이름을 고친 답은 사람이 쓴 글이라 늘 본 답이어야 합니다.
    if (choice === EDIT || choice !== clean(item.proposal).toUpperCase()) {
      return { ready: false, why: '제안과 다르게 고르셨으면 “직접 보았다”를 눌러 주세요', row: null };
    }
    observed = clean(item.observed_by);
    if (!observed) return { ready: false, why: '제안을 낸 것(Observed_By)이 없는 항목이라 승인만으로는 답이 되지 않습니다', row: null };
    if (observed.toLowerCase() === who.toLowerCase()) {
      return { ready: false, why: '제안을 낸 것과 승인하는 사람이 같습니다 — 직접 보셨다면 “직접 보았다”를 누르세요', row: null };
    }
    sp = '0'; approved = true;
    ref = clean(c.file) + ': ' + who + ' ' + clean(s.on) + ' 결정 묶음 페이지에서 제안대로 승인';
  }
  return { ready: true, why: '', approved: approved, row: {
    Item: item.id, Section: clean(item.sec), Target_ID: clean(item.target), Proposal: clean(item.proposal),
    Decision: choice, Text: text, Unit: unit, Seen_By_Person: sp, Verified_By: who,
    Observed_By: observed, Approval_Ref: ref, Decided_On: clean(s.on),
    Item_SHA256: clean(item.sha), Image_SHA256: clean(item.img_sha), Note: clean(s.note)
  } };
}

/* 이 답이 이름 칸을 들고 가는가 - 효과가 이름을 쓰는 답(LABEL 같은)만. */
function optionHasText(item, choice) {
  var opts = item.options || [];
  for (var i = 0; i < opts.length; i++) {
    if (String(opts[i][0]) !== choice) continue;
    var e = opts[i][2];
    if (Object.prototype.toString.call(e) === '[object Array]') {
      for (var k = 0; k < e.length; k++) if (e[k] && e[k].uses_text) return true;
      return false;
    }
    return !!(e && e.uses_text);
  }
  return false;
}

/* 빈 칸만 제안으로. 채운 수를 돌려줍니다. `pred`가 고르는 항목만 봅니다. */
function fillEmpty(items, states, pred, today) {
  var n = 0;
  for (var i = 0; i < items.length; i++) {
    var it = items[i];
    if (pred && !pred(it)) continue;
    if (!it.proposal) continue;
    var s = states[it.id] || (states[it.id] = {});
    if (clean(s.choice)) continue;
    s.choice = it.proposal; s.on = today || s.on || ''; n++;
  }
  return n;
}

function csvCell(v) {
  var s = String(v === null || v === undefined ? '' : v);
  return /[",\n\r]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s;
}

/* 답이 된 줄만, 항목 순서대로. */
function buildCsv(items, states, ctx) {
  var lines = [CSV_COLUMNS.join(',')];
  for (var i = 0; i < items.length; i++) {
    var got = answerOf(items[i], (states || {})[items[i].id], ctx);
    if (!got.ready) continue;
    var out = [];
    for (var c = 0; c < CSV_COLUMNS.length; c++) out.push(csvCell(got.row[CSV_COLUMNS[c]]));
    lines.push(out.join(','));
  }
  return lines.join('\n') + '\n';
}

/* 화면 위의 셈: 답이 된 것, 그중 승인, 본 답, 보류. */
function tally(items, states, ctx) {
  var t = { ready: 0, approved: 0, seen: 0, held: 0, total: items.length };
  for (var i = 0; i < items.length; i++) {
    var got = answerOf(items[i], (states || {})[items[i].id], ctx);
    if (!got.ready) continue;
    t.ready++;
    if (got.row.Decision === HOLD) t.held++;
    else if (got.approved) t.approved++;
    else t.seen++;
  }
  return t;
}

if (typeof module !== 'undefined' && module.exports) {
  module.exports = { HOLD: HOLD, EDIT: EDIT, CSV_COLUMNS: CSV_COLUMNS, answerOf: answerOf,
                     fillEmpty: fillEmpty, buildCsv: buildCsv, tally: tally, edited: edited };
}
