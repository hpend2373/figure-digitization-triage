/* Panel-count sheet: the logic that can get a number onto the wrong figure.
 *
 * Kept as pure functions with no DOM and no storage, so it can be run under
 * node against the same rows the page ships. Every defect the second audit
 * found lives in here, so this is the file the tests point at.
 *
 * Two rules this file exists to enforce:
 *   a blank is not a zero, and
 *   a value only ever returns to the row it was typed on.
 */

/* A panel count is a whole number of axes regions. Anything else is refused
 * here rather than at the browser's min/max, which does not stop a typed or
 * pasted value from reaching the export. */
var PANEL_MAX = 40;

function validatePanelCount(raw) {
  var s = String(raw === null || raw === undefined ? '' : raw).trim();
  if (s === '') return { ok: true, value: null, error: '' };
  if (!/^[0-9]+$/.test(s)) {
    return { ok: false, value: null,
             error: '0 이상 ' + PANEL_MAX + ' 이하의 정수만 입력합니다' };
  }
  var n = parseInt(s, 10);
  if (n > PANEL_MAX) {
    return { ok: false, value: null,
             error: PANEL_MAX + '개를 넘습니다. 맞다면 메모로 알려 주세요' };
  }
  return { ok: true, value: String(n), error: '' };
}

/* A stored entry carries the fingerprint of the row it was typed on. When the
 * draft is rebuilt - new caption regex, Extended Data split out, a book's
 * chapters renumbered - a row keeping its Draft_ID is not proof it is the same
 * figure, so the value is held back rather than silently reattached. */
function restoreEntries(store, rows) {
  return restoreWith(store, rows, validatePanelCount);
}

/* The same guard, for anything else typed against a row. A reason someone
 * wrote about a figure that has since been recut is exactly as wrong as a
 * count typed on it, and was one `validatePanelCount` away from being kept
 * when the count beside it was thrown out. */
function restoreWith(store, rows, validate) {
  var byId = {}, i;
  for (i = 0; i < rows.length; i++) byId[rows[i].Draft_ID] = rows[i];
  var applied = {}, rejected = [];
  var keys = Object.keys(store || {});
  for (i = 0; i < keys.length; i++) {
    var id = keys[i], e = store[id], row = byId[id];
    if (!e || typeof e !== 'object') {
      rejected.push({ id: id, reason: 'MALFORMED' });
      continue;
    }
    if (!row) { rejected.push({ id: id, reason: 'ROW_GONE' }); continue; }
    if (e.fp !== row.Row_Fingerprint) {
      rejected.push({ id: id, reason: 'ROW_CHANGED' });
      continue;
    }
    var v = validate(e.v);
    if (!v.ok) { rejected.push({ id: id, reason: 'INVALID_VALUE' }); continue; }
    if (v.value !== null && v.value !== '') applied[id] = v.value;
  }
  return { applied: applied, rejected: rejected };
}

/* BLOCKED rows are the ones the audit showed a person cannot count from - the
 * crop holds a neighbouring figure, or clips the target, or is the wrong
 * region entirely. They export as BLOCKED_BAD_CROP with an empty count, never
 * as 0. */
/* A BLANK MEANT "NOT LOOKED AT YET", AND THERE WAS NOWHERE ELSE TO PUT
 * "LOOKED, CANNOT TELL". So a figure a person studied and could not resolve -
 * an inset that may or may not be its own axes, a panel running off the crop,
 * a scan too coarse at any zoom - went back into the pile as unread, to be
 * done again by someone who would reach the same place. Or worse: the only
 * way to make the row stop asking was to type a number.
 *
 * The reason is required, because "cannot tell" without one is indistinguish-
 * able from not having tried, which is the state it exists to separate. */
/* AND THE PERSON MAY DISAGREE WITH THE SHEET ITSELF.
 *
 * Two ways this sheet can be wrong about a row, and until now neither had
 * anywhere to go. A row open for input can be showing the wrong picture -
 * a paragraph of body text, a header, half of the figure next door - and the
 * only moves available were to type a number for it (counting panels in a
 * page header) or to leave it blank, which reads as "nobody has looked".
 * A blocked row can be blocked wrongly - the 2026-09-06 audit of run2's 75
 * blocked rows found 15 whose figure is perfectly visible, held back as
 * duplicates - and there was no way to say so from the sheet at all.
 *
 * So one objection, recorded against either kind of row, with the reason
 * required for the same cause the "cannot tell" reason is: an objection
 * nobody explained cannot be told from a mis-click, and a mis-click that
 * looks like an objection is worse than no button.
 *
 * IT IS AN OBJECTION AND NOT A VERDICT. On a blocked row it changes nothing
 * about the block - the row stays blocked, exports blocked-and-disputed, and
 * a person decides later. On an open row it does take the number away, and
 * that direction is deliberate: a count read off the wrong picture is a wrong
 * value, and a wrong value is worse than a missing one.
 */
function entryStatus(row, applied, uncountable, objection) {
  var disputed = (objection || {})[row.Draft_ID];
  if (row.Count_Blocked === '1')
    return disputed ? 'BLOCK_DISPUTED' : 'BLOCKED_BAD_CROP';
  // Ahead of ENTERED on purpose. If a number was typed before the person saw
  // what the crop was, the objection is the later and better-informed answer,
  // and `buildCsv` only writes a count for ENTERED - so the number cannot
  // ride out under a status that disowns it.
  if (disputed) return 'CROP_DISPUTED';
  if (Object.prototype.hasOwnProperty.call(applied, row.Draft_ID))
    return 'ENTERED';
  if ((uncountable || {})[row.Draft_ID]) return 'SEEN_UNCOUNTABLE';
  return 'NOT_REVIEWED';
}

//: The two statuses an objection produces. Read by the merge, not by this
//: file's own export - see `buildCsv`.
var DISPUTED_STATUSES = ['CROP_DISPUTED', 'BLOCK_DISPUTED'];

function validateObjection(raw) {
  var s = String(raw === null || raw === undefined ? '' : raw).trim();
  if (s === '') {
    return { ok: false, value: '',
             error: '무엇이 이상한지 한 줄 적어 주세요 — 이유 없는 이의는 ' +
                    '잘못 누른 것과 구별되지 않습니다' };
  }
  return { ok: true, value: s.slice(0, 200), error: '' };
}

function validateUncountable(raw) {
  var s = String(raw === null || raw === undefined ? '' : raw).trim();
  if (s === '') {
    return { ok: false, value: '',
             error: '왜 셀 수 없는지 한 줄 적어 주세요 — 이유 없는 ' +
                    '"셀 수 없음"은 안 본 것과 구별되지 않습니다' };
  }
  return { ok: true, value: s.slice(0, 200), error: '' };
}

/* 체크 칸이 지금 어떤 모양이어야 하는가.
 *
 * THE BOX FOUGHT THE PERSON WHO TICKED IT. 다시 그리는 함수가 저장된 이유만
 * 보고 `box.checked = !!stored`를 했습니다. 사람이 칸을 누른 직후에는 이유가
 * 아직 없으므로 저장된 것도 없고, 그래서 방금 누른 체크가 그 자리에서 풀리고
 * 이유를 적을 칸도 같이 숨었습니다. 화면에 남는 것은 "한 줄 적어 주세요"라는
 * 말뿐이고, 적을 자리는 없습니다 - 요구만 하고 받을 데를 치우는 것은 묻는
 * 것이 아닙니다.
 *
 * 두 가지가 따로입니다. `checked`/`reasonVisible`은 사람이 지금 무엇을 하고
 * 있는가이고, `settled`는 이 행이 답을 가졌는가입니다. 카드 색과 저장은
 * `settled`만 따르므로, 이유 없는 체크는 여전히 아무것도 저장하지 않습니다.
 *
 * 이 결정이 `sheet_page.js`에 있었기 때문에 아무 시나리오도 보지 못했습니다 -
 * 그 파일은 값을 옮기기만 해야 하고, 무엇을 보일지는 값을 옮기는 일이
 * 아닙니다. */
function boxState(stored, ticked) {
  var on = !!stored;
  var open = on || !!ticked;
  return { checked: open, reasonVisible: open, settled: on };
}


function csvCell(s) {
  return '"' + String(s === null || s === undefined ? '' : s)
    .replace(/"/g, '""') + '"';
}

var CSV_COLUMNS = ['Draft_ID', 'Source_Document_ID', 'Source_File', 'Page',
                   'Figure_Number', 'Crop_Quality_Status', 'Row_Fingerprint',
                   'Observed_Panel_Count', 'Entry_Status', 'Uncountable_Reason',
                   'Objection_Reason', 'Sheet_Build_ID'];

function buildCsv(rows, applied, buildId, uncountable, objection) {
  var lines = [CSV_COLUMNS.join(',')];
  for (var i = 0; i < rows.length; i++) {
    var r = rows[i];
    var status = entryStatus(r, applied, uncountable, objection);
    var count = status === 'ENTERED' ? applied[r.Draft_ID] : '';
    var out = [];
    for (var c = 0; c < CSV_COLUMNS.length; c++) {
      var k = CSV_COLUMNS[c];
      if (k === 'Observed_Panel_Count') out.push(csvCell(count));
      else if (k === 'Entry_Status') out.push(csvCell(status));
      else if (k === 'Uncountable_Reason') {
        out.push(csvCell(status === 'SEEN_UNCOUNTABLE'
                         ? (uncountable || {})[r.Draft_ID] : ''));
      }
      // No status guard here, and none is possible: `entryStatus` returns a
      // disputed status for exactly the rows this map has a reason for, so a
      // check that the status is disputed can never change the answer. One
      // was written and no mutation could kill it - decoration, removed.
      else if (k === 'Objection_Reason')
        out.push(csvCell((objection || {})[r.Draft_ID]));
      else if (k === 'Sheet_Build_ID') out.push(csvCell(buildId));
      else out.push(csvCell(r[k]));
    }
    lines.push(out.join(','));
  }
  return lines.join('\n');
}

/* WHERE TO GO NEXT. 415 countable rows means 415 reaches for the mouse, and a
 * hand leaving the keyboard between every figure is a hand that starts
 * skipping. Enter moves to the next row that can take a number - the blocked
 * ones are not stops, because nothing can be typed there. It stops at the end
 * rather than wrapping: coming back around to a row already counted is how a
 * value gets typed over one that was right. */
function nextOpenId(rows, currentId) {
  var seen = currentId === null || currentId === undefined;
  for (var i = 0; i < rows.length; i++) {
    if (!seen) { if (rows[i].Draft_ID === currentId) seen = true; continue; }
    if (rows[i].Count_Blocked !== '1') return rows[i].Draft_ID;
  }
  return null;
}

/* What is left to do, counted the way the person experiences it: rows that
 * can take a number and do not have one. A blocked row is not "remaining" -
 * it can never be done - and counting it as such told the old sheet's
 * progress line that 649 rows were outstanding when 415 were. */
function remaining(rows, applied, uncountable, objection) {
  var left = 0, open = 0;
  for (var i = 0; i < rows.length; i++) {
    if (rows[i].Count_Blocked === '1') continue;
    open++;
    var id = rows[i].Draft_ID;
    var v = (applied || {})[id];
    // A row settled as "looked, cannot tell" is settled. It is not waiting
    // for anyone, and leaving it in the outstanding count is what would send
    // a person back to it to reach the same place again. A row objected to is
    // settled the same way: the person has looked and answered, and the
    // answer is that this row is not a figure to count.
    if ((v === undefined || v === null || v === '')
        && !(uncountable || {})[id] && !(objection || {})[id]) left++;
  }
  return { open: open, left: left, done: open - left };
}

if (typeof module !== 'undefined' && module.exports) {
  module.exports = { PANEL_MAX: PANEL_MAX, validatePanelCount: validatePanelCount,
                     restoreEntries: restoreEntries,
                     restoreWith: restoreWith, entryStatus: entryStatus,
                     buildCsv: buildCsv, CSV_COLUMNS: CSV_COLUMNS,
                     nextOpenId: nextOpenId, remaining: remaining,
                     validateUncountable: validateUncountable,
                     validateObjection: validateObjection,
                     boxState: boxState,
                     DISPUTED_STATUSES: DISPUTED_STATUSES };
}
