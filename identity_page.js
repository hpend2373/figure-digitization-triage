/* 사람이 정체 제안을 보고 내리는 판정. 화면은 값을 옮기기만 하고, 무엇이 답이
 * 되는지는 전부 여기 있습니다 - `geometry_page.js`와 같은 나눔입니다.
 *
 * `identity_proposer`는 x 라벨, 계열(범례), y 제목, n을 읽어 제안합니다. 사람이
 * 하는 일은 그림을 보고 "읽은 대로 맞다"고 하거나 고치는 것이고, 리더가 거절한
 * 자리에서만 직접 적습니다. 그리고 리더가 읽을 수 없는 것 - 이 x축이 무슨
 * 요인(TIMEPOINT/GROUP)인지, 계열이 무슨 요인(ARM/SEX)인지 - 는 사람만 말합니다.
 *
 * 이 파일이 지키는 것:
 *   1. 오버레이를 직접 보았다고 누르지 않으면 답이 아닙니다.
 *   2. 이름 없는 확인은 확인이 아닙니다.
 *   3. 확인은 x 위치를 하나 이상, 라벨을 빠짐없이, 서로 다르게 들고 와야 합니다.
 *   4. 확인은 계열을 하나 이상 들고 와야 하고, 색으로 가르는 표는 계열마다
 *      색이, 선 모양으로 가르는 표는 계열마다 선 모양이 있어야 합니다.
 *   5. x 요인과 계열 요인은 사람이 적어야 하고, 둘이 같으면 답이 아닙니다 -
 *      한 요인이 두 축에 있으면 Cell_Key가 두 번 적힙니다.
 *   6. 결과변수 이름이 없으면 답이 아닙니다. n은 비워 둘 수 있고, 비면 계획서가
 *      그 자리를 이름 부릅니다.
 */

var VERDICTS = ['CONFIRMED', 'REJECTED', 'HOLD'];
var HELD = 'HOLD';

//: 계획서가 부르는 표 종류. `batch_manifests.BATCH_MARK_TYPES`와 같아야 합니다.
var MARK_TYPES = ['BAR_COLOR', 'BAR_MONO', 'LINE_COLOR', 'LINE_MONO', 'LINE_MONO_STYLE',
                  'SCATTER', 'BOX_VIOLIN'];
var COLOUR_MARKS = ['BAR_COLOR', 'LINE_COLOR'];
var LINE_STYLES = ['SOLID', 'DASHED', 'DOTTED', 'NONE'];
var MARKER_SHAPES = ['CIRCLE', 'TRIANGLE', 'SQUARE', 'DIAMOND', 'ANY', 'NONE'];
var MARKER_FILLS = ['OPEN', 'FILLED', 'ANY'];
var BAR_FILLS = ['SOLID', 'HATCHED', 'STIPPLED', 'OPEN', 'NONE'];
var BAR_TOPS = ['OUTLINE_CENTER', 'FILL_EDGE', 'MARKER_CENTER', 'NOT_A_BAR'];

function isNumber(v) {
  return v !== '' && v !== null && v !== undefined && isFinite(Number(v));
}
function trim(v) { return String(v === null || v === undefined ? '' : v).trim(); }

/* 리더가 읽은 것과 사람이 적은 것 중 나갈 것. 빈 것은 "읽은 대로"입니다. */
function pick(typed, read) {
  var t = trim(typed);
  return t !== '' ? t : trim(read);
}

/* 'label@px;label@px' -> [{label, px}] */
function parseLabels(text) {
  var out = [];
  String(text || '').split(';').forEach(function (part) {
    var at = part.lastIndexOf('@');
    if (at < 0) return;
    var px = Number(part.slice(at + 1));
    if (!isFinite(px)) return;
    out.push({ label: part.slice(0, at), px: px });
  });
  return out;
}

/* 'name@r,g,b;name@r,g,b' -> [{name, colour:[r,g,b]|null}] */
function parseSeries(text) {
  var out = [];
  String(text || '').split(';').forEach(function (part) {
    if (!part) return;
    var at = part.lastIndexOf('@');
    var name = at < 0 ? part : part.slice(0, at);
    var colour = null;
    if (at >= 0) {
      var bits = part.slice(at + 1).split(',').map(Number);
      if (bits.length === 3 && bits.every(isFinite)) colour = bits;
    }
    out.push({ name: name, colour: colour });
  });
  return out;
}

function hexOf(rgb) {
  if (!rgb) return '';
  return '#' + rgb.map(function (v) {
    var h = Math.max(0, Math.min(255, Math.round(v))).toString(16);
    return h.length < 2 ? '0' + h : h;
  }).join('').toUpperCase();
}

/* 사람이 손대지 않은 자리에 리더의 것을 채운 위치 목록.
 * state.positions = [{label, px}] (사람이 찍거나 고친 것), 비어 있으면 읽은 것. */
function positionsOf(s) {
  var mine = s.positions || [];
  if (mine.length) return mine;
  return parseLabels(s.readLabels);
}

/* 같은 규칙으로 계열. state.series = [{name, colour, line_style, marker, marker_fill, bar_fill}] */
function seriesOf(s) {
  var mine = s.series || [];
  if (mine.length) return mine;
  return parseSeries(s.readSeries).map(function (e) {
    return { name: e.name, colour: e.colour, line_style: '', marker: '', marker_fill: '', bar_fill: '' };
  });
}

/* 이 제안의 지금 상태가 답이 되는가.
 *
 * state = { verdict, who, seen, note, xFactor, positions, seriesFactor, series,
 *           markType, outcome, unit, n, barTop, stem,
 *           readLabels, readSeries, readOutcome, readUnit, readN, markProposed,
 *           kind, frameX0, frameX1, proposal }
 */
function verdictOf(id, state) {
  var s = state || {};
  var verdict = trim(s.verdict).toUpperCase();
  var who = trim(s.who);
  if (!verdict) return { ready: false, why: '아직 고르지 않았습니다', row: null };
  if (VERDICTS.indexOf(verdict) < 0) {
    return { ready: false, why: '이 페이지가 받을 수 없는 답입니다: ' + verdict, row: null };
  }
  if (!s.seen) return { ready: false, why: '이 오버레이를 직접 보셨다고 눌러 주세요', row: null };
  if (!who) return { ready: false, why: '누가 보았는지 적어 주세요 (이름 또는 이니셜)', row: null };

  var row = {
    Proposal_ID: String(s.proposal || id),
    Human_Verification_Status: verdict,
    X_Factor: '', X_Labels: '', Series_Factor: '', Series: '', Mark_Type: '',
    Outcome_Name: '', Unit: '', N_Outcome: '', Bar_Top_Definition: '',
    Errorbar_Stem_Confirmed: '',
    Verified_By: who, Seen_By_Person: '1', Value_Sources: '', Note: trim(s.note)
  };
  if (verdict !== 'CONFIRMED') return { ready: true, why: '', row: row };

  var sources = [];
  // ---- x ------------------------------------------------------------
  var xFactor = trim(s.xFactor).toUpperCase();
  if (!xFactor) return { ready: false, why: 'x축이 무슨 요인인지 적어 주세요 (예: TIMEPOINT, GROUP)', row: null };
  if (!/^[A-Z][A-Z0-9_]*$/.test(xFactor)) {
    return { ready: false, why: '요인 이름은 대문자·숫자·밑줄만: ' + xFactor, row: null };
  }
  var positions = positionsOf(s);
  if (!positions.length) {
    return { ready: false, why: '읽힌 x 라벨이 없습니다 — 그림에서 x 위치를 찍고 라벨을 적어 주세요', row: null };
  }
  var seen = {};
  for (var i = 0; i < positions.length; i++) {
    var lab = trim(positions[i].label);
    if (!lab) return { ready: false, why: (i + 1) + '번째 x 위치의 라벨이 비어 있습니다', row: null };
    if (seen[lab.toUpperCase()]) return { ready: false, why: '같은 x 라벨이 둘입니다: ' + lab, row: null };
    seen[lab.toUpperCase()] = true;
    if (!isNumber(positions[i].px)) return { ready: false, why: 'x 위치의 픽셀이 수가 아닙니다', row: null };
    if (isNumber(s.frameX0) && isNumber(s.frameX1)) {
      var w = Number(s.frameX1) - Number(s.frameX0);
      if (positions[i].px < Number(s.frameX0) - 0.1 * w || positions[i].px > Number(s.frameX1) + 0.1 * w) {
        return { ready: false, why: 'x 위치 ' + lab + '이 프레임 밖입니다', row: null };
      }
    }
  }
  sources.push('x:' + ((s.positions || []).length ? 'TYPED' : 'READ'));
  // ---- series ---------------------------------------------------------
  var seriesFactor = trim(s.seriesFactor).toUpperCase();
  var markType = trim(s.markType || s.markProposed).toUpperCase();
  if (MARK_TYPES.indexOf(markType) < 0) {
    return { ready: false, why: '표 종류를 골라 주세요 (' + MARK_TYPES.join(', ') + ')', row: null };
  }
  var series = seriesOf(s);
  if (!series.length) {
    return { ready: false, why: '계열이 없습니다 — 범례의 계열을 적어 주세요 (하나뿐이면 하나)', row: null };
  }
  if (series.length > 1 && !seriesFactor) {
    return { ready: false, why: '계열이 둘 이상이면 계열이 무슨 요인인지 적어 주세요 (예: ARM, SEX)', row: null };
  }
  if (seriesFactor && !/^[A-Z][A-Z0-9_]*$/.test(seriesFactor)) {
    return { ready: false, why: '요인 이름은 대문자·숫자·밑줄만: ' + seriesFactor, row: null };
  }
  if (seriesFactor && seriesFactor === xFactor) {
    return { ready: false, why: 'x 요인과 계열 요인이 같습니다 — 한 요인이 두 축에 있을 수 없습니다', row: null };
  }
  var names = {};
  for (var k = 0; k < series.length; k++) {
    var nm = trim(series[k].name);
    if (!nm && series.length > 1) return { ready: false, why: (k + 1) + '번째 계열의 이름이 비어 있습니다', row: null };
    if (nm && names[nm.toUpperCase()]) return { ready: false, why: '같은 계열 이름이 둘입니다: ' + nm, row: null };
    names[nm.toUpperCase()] = true;
    if (COLOUR_MARKS.indexOf(markType) >= 0 && !series[k].colour) {
      return { ready: false, why: markType + '은 색으로 계열을 가릅니다 — ' + (nm || (k + 1) + '번째') + ' 계열의 색이 없습니다', row: null };
    }
    if (markType === 'LINE_MONO_STYLE' && LINE_STYLES.indexOf(trim(series[k].line_style).toUpperCase()) < 0) {
      return { ready: false, why: 'LINE_MONO_STYLE은 선 모양으로 계열을 가릅니다 — ' + (nm || (k + 1) + '번째') + ' 계열의 선 모양을 골라 주세요', row: null };
    }
    if (markType === 'LINE_MONO' && series.length > 1 && (!series[k].marker || series[k].marker === 'NONE')) {
      return { ready: false, why: 'LINE_MONO는 마커 모양으로 계열을 가릅니다 — ' + (nm || (k + 1) + '번째') + ' 계열의 마커를 골라 주세요', row: null };
    }
    if (markType === 'BAR_MONO' && series.length > 1 && (!series[k].bar_fill || series[k].bar_fill === 'NONE')) {
      return { ready: false, why: 'BAR_MONO는 채움 무늬로 계열을 가릅니다 — ' + (nm || (k + 1) + '번째') + ' 계열의 무늬를 골라 주세요', row: null };
    }
  }
  if (series.length > 1) {
    var keys = series.map(function (e) {
      return COLOUR_MARKS.indexOf(markType) >= 0 ? hexOf(e.colour)
        : [e.line_style, e.marker, e.marker_fill, e.bar_fill].map(function (v) { return trim(v).toUpperCase(); }).join('|');
    });
    for (var a = 0; a < keys.length; a++) {
      for (var b = a + 1; b < keys.length; b++) {
        if (keys[a] === keys[b] && keys[a] !== '') {
          return { ready: false, why: '두 계열을 가를 것이 없습니다 (' + series[a].name + ', ' + series[b].name + ')', row: null };
        }
      }
    }
  }
  sources.push('series:' + ((s.series || []).length ? 'TYPED' : 'READ'));
  // ---- unit -----------------------------------------------------------
  var outcome = pick(s.outcome, s.readOutcome);
  if (!outcome) return { ready: false, why: '결과변수 이름을 적어 주세요 (y축 제목)', row: null };
  var unit = pick(s.unit, s.readUnit);
  var n = pick(s.n, s.readN);
  if (n !== '' && !(isNumber(n) && Number(n) > 0 && Number(n) === Math.floor(Number(n)))) {
    return { ready: false, why: 'n은 양의 정수여야 합니다: ' + n, row: null };
  }
  sources.push('outcome:' + (trim(s.outcome) ? 'TYPED' : 'READ'));
  sources.push('n:' + (trim(s.n) ? 'TYPED' : (n ? 'READ' : 'NONE')));
  var barTop = '';
  if (markType.indexOf('BAR') === 0) {
    barTop = trim(s.barTop).toUpperCase();
    if (BAR_TOPS.indexOf(barTop) < 0) {
      return { ready: false, why: '막대의 값을 어디서 읽는지 골라 주세요 (' + BAR_TOPS.join(', ') + ')', row: null };
    }
  }
  var stem = '';
  if (markType !== 'SCATTER' && markType !== 'BOX_VIOLIN') {
    stem = s.stem ? 'TRUE' : 'FALSE';
  }
  row.X_Factor = xFactor;
  row.X_Labels = JSON.stringify(positions.map(function (p) { return { label: trim(p.label), px: Number(p.px) }; }));
  row.Series_Factor = seriesFactor;
  row.Series = JSON.stringify(series.map(function (e) {
    return { name: trim(e.name), colour: e.colour ? hexOf(e.colour) : '',
             line_style: trim(e.line_style).toUpperCase(), marker: trim(e.marker).toUpperCase(),
             marker_fill: trim(e.marker_fill).toUpperCase(), bar_fill: trim(e.bar_fill).toUpperCase() };
  }));
  row.Mark_Type = markType;
  row.Outcome_Name = outcome;
  row.Unit = unit;
  row.N_Outcome = n;
  row.Bar_Top_Definition = barTop;
  row.Errorbar_Stem_Confirmed = stem;
  row.Value_Sources = sources.join(';');
  return { ready: true, why: '', row: row };
}

var CSV_COLUMNS = ['Proposal_ID', 'Human_Verification_Status', 'X_Factor', 'X_Labels',
                   'Series_Factor', 'Series', 'Mark_Type', 'Outcome_Name', 'Unit', 'N_Outcome',
                   'Bar_Top_Definition', 'Errorbar_Stem_Confirmed',
                   'Verified_By', 'Seen_By_Person', 'Value_Sources', 'Note'];

function csvCell(s) {
  return '"' + String(s === null || s === undefined ? '' : s).replace(/"/g, '""') + '"';
}

function buildCsv(ids, states) {
  var lines = [CSV_COLUMNS.join(',')];
  ids = (ids || []).slice().sort();
  for (var i = 0; i < ids.length; i++) {
    var got = verdictOf(ids[i], (states || {})[ids[i]]);
    if (!got.ready) continue;
    lines.push(CSV_COLUMNS.map(function (c) { return csvCell(got.row[c]); }).join(','));
  }
  return lines.join('\n');
}

function remaining(ids, states) {
  var left = 0;
  for (var i = 0; i < ids.length; i++) {
    if (!verdictOf(ids[i], (states || {})[ids[i]]).ready) left++;
  }
  return left;
}

function held(ids, states) {
  var n = 0;
  for (var i = 0; i < ids.length; i++) {
    var got = verdictOf(ids[i], (states || {})[ids[i]]);
    if (got.ready && got.row.Human_Verification_Status === HELD) n++;
  }
  return n;
}

if (typeof module !== 'undefined' && module.exports) {
  module.exports = { VERDICTS: VERDICTS, HELD: HELD, MARK_TYPES: MARK_TYPES, COLOUR_MARKS: COLOUR_MARKS,
                     LINE_STYLES: LINE_STYLES, MARKER_SHAPES: MARKER_SHAPES, MARKER_FILLS: MARKER_FILLS,
                     BAR_FILLS: BAR_FILLS, BAR_TOPS: BAR_TOPS,
                     parseLabels: parseLabels, parseSeries: parseSeries, hexOf: hexOf,
                     positionsOf: positionsOf, seriesOf: seriesOf, pick: pick,
                     verdictOf: verdictOf, buildCsv: buildCsv, CSV_COLUMNS: CSV_COLUMNS,
                     remaining: remaining, held: held };
}
