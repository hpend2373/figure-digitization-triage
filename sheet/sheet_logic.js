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
    var v = validatePanelCount(e.v);
    if (!v.ok) { rejected.push({ id: id, reason: 'INVALID_VALUE' }); continue; }
    if (v.value !== null) applied[id] = v.value;
  }
  return { applied: applied, rejected: rejected };
}

/* BLOCKED rows are the ones the audit showed a person cannot count from - the
 * crop holds a neighbouring figure, or clips the target, or is the wrong
 * region entirely. They export as BLOCKED_BAD_CROP with an empty count, never
 * as 0. */
function entryStatus(row, applied) {
  if (row.Count_Blocked === '1') return 'BLOCKED_BAD_CROP';
  if (Object.prototype.hasOwnProperty.call(applied, row.Draft_ID))
    return 'ENTERED';
  return 'NOT_REVIEWED';
}

function csvCell(s) {
  return '"' + String(s === null || s === undefined ? '' : s)
    .replace(/"/g, '""') + '"';
}

var CSV_COLUMNS = ['Draft_ID', 'Source_Document_ID', 'Source_File', 'Page',
                   'Figure_Number', 'Crop_Quality_Status', 'Row_Fingerprint',
                   'Observed_Panel_Count', 'Entry_Status', 'Sheet_Build_ID'];

function buildCsv(rows, applied, buildId) {
  var lines = [CSV_COLUMNS.join(',')];
  for (var i = 0; i < rows.length; i++) {
    var r = rows[i];
    var status = entryStatus(r, applied);
    var count = status === 'ENTERED' ? applied[r.Draft_ID] : '';
    var out = [];
    for (var c = 0; c < CSV_COLUMNS.length; c++) {
      var k = CSV_COLUMNS[c];
      if (k === 'Observed_Panel_Count') out.push(csvCell(count));
      else if (k === 'Entry_Status') out.push(csvCell(status));
      else if (k === 'Sheet_Build_ID') out.push(csvCell(buildId));
      else out.push(csvCell(r[k]));
    }
    lines.push(out.join(','));
  }
  return lines.join('\n');
}

if (typeof module !== 'undefined' && module.exports) {
  module.exports = { PANEL_MAX: PANEL_MAX, validatePanelCount: validatePanelCount,
                     restoreEntries: restoreEntries, entryStatus: entryStatus,
                     buildCsv: buildCsv, CSV_COLUMNS: CSV_COLUMNS };
}
