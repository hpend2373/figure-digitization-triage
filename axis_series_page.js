/* 축·눈금과 계열(정체) 제안을 한 카드에 놓는 확인 페이지의 판정 논리.
 *
 * 무엇이 관문 줄이 되는지는 여기 없습니다. 그것은 `geometry_page.js`·`identity_page.js`의
 * `verdictOf`가 정하고, 이 파일은 카드의 답(제안대로 / 고칠 곳 있음 / 보류, 직접 봤다, 이름,
 * 메모)을 두 함수가 받는 상태로 옮긴 뒤 나온 줄을 답 CSV 한 줄에 싣습니다. 그래서 '제안대로'가
 * 내보내는 줄은 기하·정체 확인 페이지에서 같은 값을 손으로 넣었을 때 나오는 줄과 같고,
 * `record_geometry`·`record_identity`가 그대로 받습니다(`route_axis_series.py`가 나눠 줌).
 *
 * 이 파일이 지키는 것:
 *   1. '제안대로'는 미리 골라 둡니다 - 사람이 할 일은 대개 보는 것이고, 고를 것은 다를 때뿐입니다.
 *      이미 고른 답은 덮지 않습니다.
 *   2. '두 그림을 직접 봤다'는 미리 누르지 않습니다. 고르는 것은 판단이고 이것은 본 일이라,
 *      둘을 한 클릭으로 묶으면 그림을 안 연 카드가 본 카드가 됩니다.
 *   3. 이름 없는 답은 답이 아닙니다.
 *   4. '고칠 곳 있음'은 무엇을 고칠지 메모가 있어야 다 된 것으로 셉니다(내보내기는 됩니다 -
 *      메모 없는 고칠 곳도 사람이 한 말입니다).
 *   5. 관문 규칙에 걸리는 제안은 '제안대로'로 답이 되지 않고, 걸린 까닭을 카드에 보입니다.
 *
 * 하나를 덧붙입니다: `identity_page.js`의 단위 칸은 "비우면 리더가 읽은 것"이라 리더가 읽은
 * 단위를 지울 길이 없습니다. 제안이 단위가 없다고 한 패널(`unitBlank`)은 나온 줄의 Unit을 비우고
 * 그 사실을 Note에 적습니다.
 */

var PARTS = ['geo', 'idn'];
var ANSWERS = ['ACCEPT', 'FIX', 'HOLD'];
var CSV_COLUMNS = ['Proposal_ID', 'Part', 'Answer', 'Verified_By', 'Seen_By_Person', 'Note', 'Gate_Row'];
var PART_NAME = { geo: 'GEOMETRY', idn: 'IDENTITY' };

function copyOf(o) { return JSON.parse(JSON.stringify(o)); }
function trimmed(v) { return String(v === null || v === undefined ? '' : v).trim(); }

/* data = { order, gmeta, imeta, proposals, prov, date, proposer }
 *   gmeta/imeta  geometry_page·identity_page가 카드마다 짓는 META와 같은 것
 *   proposals    { id: { geo: {...상태 칸}, idn: {...상태 칸, unitBlank?} } }
 *   prov         { id: { geo: '무엇을 누가 제안했는지', idn: '...' } } */
function makeCheck(GEO, IDN, data) {
  function noteText(id, part, memo, extra) {
    var n = '[축·계열 확인 페이지 ' + data.date + '] 제안: ' + data.prov[id][part] +
            " — 보신 분이 두 그림을 보고 '제안대로'";
    if (extra) n += ' (' + extra + ')';
    return memo ? n + ' | 메모: ' + memo : n;
  }
  function geoState(id, name, seen, memo) {
    var o = copyOf(data.gmeta[id]), c = data.proposals[id].geo;
    for (var k in c) o[k] = c[k];
    o.who = name; o.seen = seen; o.note = noteText(id, 'geo', memo);
    return o;
  }
  function idnState(id, name, seen, memo) {
    var o = copyOf(data.imeta[id]), c = copyOf(data.proposals[id].idn);
    for (var k in c) if (k !== 'unitBlank') o[k] = c[k];
    o.who = name; o.seen = seen;
    o.note = noteText(id, 'idn', memo,
                      c.unitBlank ? '리더가 읽은 단위 "' + data.imeta[id].readUnit + '"는 그림에 없어 비움' : '');
    return o;
  }
  /* '제안대로'일 때 관문에 갈 두 줄 - { geo: {ready, why, row}, idn: {...} } */
  function gate(id, name, seen, memo) {
    var g = GEO.verdictOf(id, geoState(id, name, seen, memo));
    var i = IDN.verdictOf(id, idnState(id, name, seen, memo));
    if (i.ready && i.row && data.proposals[id].idn.unitBlank) i.row.Unit = '';
    return { geo: g, idn: i };
  }
  /* 이름과 목격을 넣어도 관문 규칙에 걸리는 제안들 - { 'id|part': 까닭 } */
  function broken() {
    var out = {};
    data.order.forEach(function (id) {
      var t = gate(id, '검사', true, '');
      PARTS.forEach(function (p) { if (!t[p].ready) out[id + '|' + p] = t[p].why; });
    });
    return out;
  }
  function blank() { return { geo: '', idn: '', seen: false, note: '' }; }
  /* 빈 답에만 '제안대로'. 이미 고른 답(고칠 곳·보류 포함)은 그대로. 목격은 건드리지 않습니다. */
  function withDefaults(st) {
    var out = st || {};
    data.order.forEach(function (id) {
      if (!out[id]) out[id] = blank();
      PARTS.forEach(function (p) { if (!out[id][p]) out[id][p] = 'ACCEPT'; });
    });
    return out;
  }
  /* 한 카드의 한 부분. { done, text, bad, fix, row } */
  function partState(st, who, id, p, brk) {
    var s = (st || {})[id] || blank(), a = s[p], name = trimmed(who);
    if (ANSWERS.indexOf(a) < 0) return { done: false, text: '아직 고르지 않았습니다', bad: false };
    if (a === 'ACCEPT' && brk && brk[id + '|' + p]) {
      return { done: false, text: '제안이 관문 규칙에 걸립니다: ' + brk[id + '|' + p], bad: true };
    }
    if (!s.seen) {
      return { done: false, bad: false,
               text: (a === 'ACCEPT' ? '제안대로(미리 고름) — ' : '') + "그림을 보고 '두 그림을 직접 봤다'를 눌러 주세요" };
    }
    if (!name) return { done: false, text: '보신 분 이름을 위에 적어 주세요', bad: true };
    if (a === 'ACCEPT') {
      var t = gate(id, name, true, trimmed(s.note))[p];
      if (!t.ready) return { done: false, text: t.why, bad: true };
      return { done: true, text: '제안대로 — 관문 줄 준비됨', bad: false, row: t.row };
    }
    if (a === 'FIX') {
      var memo = trimmed(s.note);
      return { done: true, fix: true, bad: !memo,
               text: memo ? '고칠 곳 있음 — 메모대로 고쳐 다시 묻습니다' : '고칠 곳 있음 — 무엇을 고칠지 메모에 적어 주세요' };
    }
    return { done: true, text: '보류', bad: false };
  }
  function csvCell(v) { return '"' + String(v === null || v === undefined ? '' : v).replace(/"/g, '""') + '"'; }
  /* 답이 된 부분만 한 줄씩. 관문 줄은 '제안대로'에만 붙습니다. */
  function answerCsv(st, who, brk) {
    var lines = [CSV_COLUMNS.join(',')], n = 0;
    data.order.forEach(function (id) {
      PARTS.forEach(function (p) {
        var r = partState(st, who, id, p, brk);
        if (!r.done) return;
        lines.push([id, PART_NAME[p], st[id][p], trimmed(who), '1', trimmed(st[id].note),
                    r.row ? JSON.stringify(r.row) : ''].map(csvCell).join(','));
        n++;
      });
    });
    return { csv: lines.join('\n'), n: n };
  }
  function tally(st, who, brk) {
    var left = 0, fix = 0, accepted = 0;
    data.order.forEach(function (id) {
      PARTS.forEach(function (p) {
        var r = partState(st, who, id, p, brk);
        if (!r.done) left++; else if (r.fix) fix++; else if (r.row) accepted++;
      });
    });
    return { left: left, fix: fix, accepted: accepted, total: data.order.length * PARTS.length };
  }
  /* 다음에 볼 카드 - 두 부분 중 하나라도 답이 안 된 첫 카드, 없으면 '' */
  function nextOpen(st, who, brk) {
    for (var k = 0; k < data.order.length; k++) {
      var id = data.order[k];
      if (!PARTS.every(function (p) { return partState(st, who, id, p, brk).done; })) return id;
    }
    return '';
  }
  return { noteText: noteText, geoState: geoState, idnState: idnState, gate: gate, broken: broken,
           withDefaults: withDefaults, partState: partState, answerCsv: answerCsv, tally: tally,
           nextOpen: nextOpen };
}

if (typeof module !== 'undefined' && module.exports) {
  module.exports = { PARTS: PARTS, ANSWERS: ANSWERS, CSV_COLUMNS: CSV_COLUMNS, PART_NAME: PART_NAME,
                     makeCheck: makeCheck };
}
