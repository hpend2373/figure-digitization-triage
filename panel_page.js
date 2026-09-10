/* 사람이 그림 위에 패널을 긋고 그 패널에 무엇이 그려졌는지 말하는 판정. 화면은
 * 값을 옮기기만 하고, 무엇이 답이 되는지는 전부 여기 있습니다 - `geometry_page.js`
 * 와 같은 나눔입니다.
 *
 * 계획서에 남은 일의 대부분이 이것입니다: 패널 1019개마다 **어디**인지와
 * **무엇**인지. 어디인지는 자동 분할이 사람 계수와 맞는 그림(절반)에서 제안이
 * 있고, 나머지는 사람이 긋습니다. 무엇인지는 아무 데도 없고 전부 사람입니다 -
 * 그것이 리더를 고르고, 이 논문이 "막대는 SEM, 상자는 사분위"라고 말할 때
 * 분산의 뜻까지 정합니다.
 *
 * 이 파일이 지키는 넷:
 *   1. 그림을 직접 보았다고 누르지 않으면 답이 아닙니다.
 *   2. 누가 보았는지 없는 답은 답이 아닙니다.
 *   3. 패널마다 무엇이 그려졌는지 말해야 합니다. 상자만 긋고 종류를 안 고른
 *      패널은 리더가 없는 패널이고, 그것을 넘기면 계획서가 그 패널을 읽을
 *      수 있는 것으로 셉니다.
 *   4. 상자는 그림 안에 있어야 하고 넓이가 있어야 합니다. 그림 밖의 상자는
 *      600 DPI로 옮길 때 아무 데도 안 떨어지고, 넓이 0인 상자는 아무것도 못
 *      읽는데 패널로 셉니다.
 *
 * 자리와 종류는 대개 기계가 먼저 제안합니다. 사람이 그것을 그대로 받았는지
 * 고쳤는지는 `Region_Source`·`Mark_Source`로 따로 나갑니다 - 그 둘이 없으면
 * 제안이 얼마나 맞았는지 아무도 셀 수 없고, 사람이 본 것과 기계가 낸 것이
 * 같은 줄에 앉습니다.
 *
 * 화면의 기하도 여기 있습니다. 끌어서 그은 자리를 원본 픽셀로 옮기는 산수가
 * 렌더러의 문자열 안에 있었고, 그래서 아무 시나리오도 그것을 보지 않았습니다 -
 * 창이 좁으면 그림은 줄고 캔버스는 안 줄어 상자가 1.25배 어긋난 자리에 앉는데,
 * 좌표는 그림 안이라 관문도 못 잡았습니다. 재는 것은 화면이 하고, 잰 것으로
 * 무엇을 하는지는 여기서 정합니다.
 */

//: 패널에 그려질 수 있는 것. 리더 이름이 아니라 사람이 보는 이름입니다 -
//: 막대가 색인지 단색인지는 기계가 잉크를 재서 정하고, 사람이 정하는 것은
//: 막대냐 선이냐입니다. `NOT_DATA`는 그 패널이 축은 있지만 읽을 값이 없다는
//: 답이고, 답입니다.
var MARKS = ['BAR', 'LINE', 'BOX', 'SCATTER', 'NOT_DATA'];

//: 그림 전체에 대한 판정. `NO_PANELS`는 "이 그림에 읽을 패널이 없다" - 사람이
//: 전에 센 수가 틀렸다는 말이고, 그것도 답입니다. `HOLD`는 답이지만 넘어가지
//: 않습니다.
var VERDICTS = ['PANELS', 'NO_PANELS', 'HOLD'];
var HELD = 'HOLD';

function num(v) { var n = Number(v); return isFinite(n) ? n : null; }

/* 화면에서 잰 것을 원본 픽셀로. `rect`는 캔버스가 **실제로 차지한** 크기이고
 * `backing`은 캔버스가 그리는 좌표계의 크기입니다. 둘은 같지 않습니다: 창이
 * 좁거나 브라우저를 확대하면 그림과 캔버스는 CSS로 줄어들지만 그리는 좌표계는
 * 그대로입니다. 잰 크기를 쓰지 않으면 그은 자리와 저장되는 자리가 어긋납니다. */
function imagePoint(rect, backing, size, clientX, clientY) {
  var rw = num((rect || {}).width), rh = num((rect || {}).height);
  var bw = num((backing || {}).w), bh = num((backing || {}).h);
  var sw = num((size || {}).w), sh = num((size || {}).h);
  if (!rw || !rh || !bw || !bh || !sw || !sh) return null;
  var x = (num(clientX) - num((rect || {}).left || 0)) * (sw / rw);
  var y = (num(clientY) - num((rect || {}).top || 0)) * (sh / rh);
  return { x: Math.max(0, Math.min(sw, x)), y: Math.max(0, Math.min(sh, y)) };
}

/* 누른 자리를 품는 가장 작은 상자의 번호. 없으면 -1. */
function boxAt(boxes, x, y) {
  var best = -1, area = Infinity;
  for (var i = 0; i < (boxes || []).length; i++) {
    var b = boxes[i] || {};
    if (x < b.x0 || x > b.x1 || y < b.y0 || y > b.y1) continue;
    var a = (b.x1 - b.x0) * (b.y1 - b.y0);
    if (a < area) { area = a; best = i; }
  }
  return best;
}

/* 서로 많이 겹치는 상자 쌍. 사람에게 보여 주는 말이 됩니다 - 겹친 상자는 한
 * 패널을 두 번 읽거나 이웃의 표시를 함께 읽습니다. 인셋처럼 정말 겹치는 그림도
 * 있어서 답을 막지는 않고, 보이게만 합니다. */
var OVERLAP_MAX = 0.20;

function overlapPairs(boxes) {
  var out = [];
  boxes = boxes || [];
  for (var i = 0; i < boxes.length; i++) {
    for (var j = i + 1; j < boxes.length; j++) {
      var f = Math.max(coverOf(boxes[i], boxes[j]), coverOf(boxes[j], boxes[i]));
      if (f > OVERLAP_MAX) out.push({ a: i + 1, b: j + 1, part: f });
    }
  }
  return out;
}

function coverOf(a, b) {
  a = a || {}; b = b || {};
  var ix = Math.max(0, Math.min(a.x1, b.x1) - Math.max(a.x0, b.x0));
  var iy = Math.max(0, Math.min(a.y1, b.y1) - Math.max(a.y0, b.y0));
  var area = (a.x1 - a.x0) * (a.y1 - a.y0);
  return area > 0 ? (ix * iy) / area : 0;
}

/* 브라우저에 남아 있던 답이 지금 이 그림의 답인가. 같은 file:// 자리에서는
 * 묶음이 저장소를 함께 쓰고, 제안을 고쳐 페이지를 다시 만들어도 옛 상자가
 * "제안"으로 되살아납니다 - 크롭이나 제안이 바뀌었으면 그 답은 다른 그림에
 * 대한 답입니다. */
function staleState(state, meta) {
  var was = String((state || {}).stamp || '');
  var now = String((meta || {}).stamp || '');
  return was !== now;
}

/* 상자 하나가 이 그림 위에 놓일 수 있는가. 돌려주는 것은 잘못이 없으면 ''. */
function boxProblem(box, size) {
  var x0 = num(box.x0), y0 = num(box.y0), x1 = num(box.x1), y1 = num(box.y1);
  if (x0 === null || y0 === null || x1 === null || y1 === null) return '좌표가 수가 아닙니다';
  if (x1 - x0 < 4 || y1 - y0 < 4) return '넓이가 없습니다';
  var w = num((size || {}).w), h = num((size || {}).h);
  if (w === null || h === null) return '그림의 크기를 모릅니다';
  if (x0 < 0 || y0 < 0 || x1 > w || y1 > h) return '그림 밖으로 나갑니다';
  return '';
}

/* 이 그림의 지금 상태가 답이 되는가, 안 되면 왜 안 되는가.
 *
 * `state` = { verdict, boxes: [{x0,y0,x1,y1,mark,source}], seen, who, note,
 *             draft, size: {w,h}, declared }
 * 돌려주는 것 = { ready, why, rows: [한 패널 한 줄] }
 */
function panelsOf(id, state) {
  var s = state || {};
  var verdict = String(s.verdict || '').trim().toUpperCase();
  var who = String(s.who || '').trim();
  var boxes = Object.prototype.toString.call(s.boxes) === '[object Array]' ? s.boxes : [];
  if (!verdict) return { ready: false, why: '아직 고르지 않았습니다', rows: [] };
  if (VERDICTS.indexOf(verdict) < 0) {
    return { ready: false, why: '이 페이지가 받을 수 없는 답입니다: ' + verdict, rows: [] };
  }
  if (!s.seen) return { ready: false, why: '이 그림을 직접 보셨다고 눌러 주세요', rows: [] };
  if (!who) return { ready: false, why: '누가 보았는지 적어 주세요', rows: [] };
  var rows = [];
  if (verdict === 'PANELS') {
    if (!boxes.length) {
      return { ready: false, why: '패널이 있다고 하셨는데 그은 상자가 없습니다', rows: [] };
    }
    for (var i = 0; i < boxes.length; i++) {
      var b = boxes[i] || {};
      var bad = boxProblem(b, s.size);
      if (bad) return { ready: false, why: (i + 1) + '번 상자: ' + bad, rows: [] };
      var mark = String(b.mark || '').trim().toUpperCase();
      if (!mark) return { ready: false, why: (i + 1) + '번 패널에 무엇이 그려졌는지 골라 주세요', rows: [] };
      if (MARKS.indexOf(mark) < 0) {
        return { ready: false, why: (i + 1) + '번 패널: 받을 수 없는 종류 ' + mark, rows: [] };
      }
      rows.push({
        Draft_ID: String(s.draft || id),
        Panel_Index: i + 1,
        X0: Math.round(num(b.x0)), Y0: Math.round(num(b.y0)),
        X1: Math.round(num(b.x1)), Y1: Math.round(num(b.y1)),
        Mark_Type: mark,
        // 사람이 그은 것과 기계가 제안한 것을 그대로 받은 것은 같은 상자가
        // 아닙니다. 둘을 가르는 칸이 없으면 자동 분할이 얼마나 맞았는지
        // 아무도 셀 수 없습니다.
        Region_Source: b.source === 'PROPOSED' ? 'PROPOSED' : 'DRAWN',
        Mark_Source: b.markSource === 'PROPOSED' ? 'PROPOSED' : 'TYPED',
        // 이 좌표가 **어느 크롭 위의** 좌표인지. 크롭이 다시 만들어지면 같은
        // 이름의 다른 그림이고, 관문이 그것을 알아야 합니다.
        Crop_SHA256: String(s.crop || ''),
        Proposal_Version: String(s.proposalVersion || ''),
        Declared_Count: num(s.declared) === null ? '' : String(num(s.declared)),
        Drawn_Count: String(boxes.length),
        Verdict: verdict,
        Seen_By_Person: '1', Verified_By: who,
        Note: String(s.note || '').trim()
      });
    }
  } else {
    // NO_PANELS와 HOLD는 그림 한 줄입니다. 상자 없이.
    rows.push({
      Draft_ID: String(s.draft || id), Panel_Index: 0,
      X0: '', Y0: '', X1: '', Y1: '', Mark_Type: '', Region_Source: '', Mark_Source: '',
      Crop_SHA256: String(s.crop || ''), Proposal_Version: String(s.proposalVersion || ''),
      Declared_Count: num(s.declared) === null ? '' : String(num(s.declared)),
      Drawn_Count: '0', Verdict: verdict,
      Seen_By_Person: '1', Verified_By: who,
      Note: String(s.note || '').trim()
    });
  }
  return { ready: true, why: '', rows: rows };
}

var CSV_COLUMNS = ['Draft_ID', 'Panel_Index', 'X0', 'Y0', 'X1', 'Y1', 'Mark_Type',
                   'Region_Source', 'Mark_Source', 'Crop_SHA256', 'Proposal_Version',
                   'Declared_Count', 'Drawn_Count', 'Verdict',
                   'Seen_By_Person', 'Verified_By', 'Note'];

function csvCell(s) {
  return '"' + String(s === null || s === undefined ? '' : s).replace(/"/g, '""') + '"';
}

function buildCsv(ids, states) {
  var lines = [CSV_COLUMNS.join(',')];
  ids = (ids || []).slice().sort();
  for (var i = 0; i < ids.length; i++) {
    var got = panelsOf(ids[i], (states || {})[ids[i]]);
    if (!got.ready) continue;
    for (var r = 0; r < got.rows.length; r++) {
      var out = [];
      for (var c = 0; c < CSV_COLUMNS.length; c++) out.push(csvCell(got.rows[r][CSV_COLUMNS[c]]));
      lines.push(out.join(','));
    }
  }
  return lines.join('\n');
}

function remaining(ids, states) {
  var left = 0;
  for (var i = 0; i < ids.length; i++) if (!panelsOf(ids[i], (states || {})[ids[i]]).ready) left++;
  return left;
}

function held(ids, states) {
  var n = 0;
  for (var i = 0; i < ids.length; i++) {
    var got = panelsOf(ids[i], (states || {})[ids[i]]);
    if (got.ready && got.rows[0].Verdict === HELD) n++;
  }
  return n;
}

if (typeof module !== 'undefined' && module.exports) {
  module.exports = { MARKS: MARKS, VERDICTS: VERDICTS, HELD: HELD,
                     boxProblem: boxProblem, panelsOf: panelsOf, buildCsv: buildCsv,
                     CSV_COLUMNS: CSV_COLUMNS, remaining: remaining, held: held,
                     imagePoint: imagePoint, boxAt: boxAt, overlapPairs: overlapPairs,
                     coverOf: coverOf, staleState: staleState,
                     OVERLAP_MAX: OVERLAP_MAX };
}
