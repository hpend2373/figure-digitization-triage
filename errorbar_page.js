/* 오차 정의 판정 페이지의 결정들. 화면은 값을 옮기기만 하고, 무엇이 답이 되는지는
 * 전부 여기 있습니다 - `sheet/sheet_logic.js`와 같은 나눔입니다.
 *
 * 이 파일이 지키는 하나: 사람이 원문을 보았다고 누르지 않으면 그 줄은 답이 되지
 * 않습니다. `record_errorbar`가 `NOT_VERIFIED_BY_PERSON`으로 막는 것과 같은 말을
 * 여기서도 합니다 - 관문에서만 막으면 사람은 채워 놓고 거부당하고, 왜 거부됐는지
 * 는 터미널에만 남습니다.
 */

//: 계획서가 받는 분산 종류. `kernel.FIG_DISPERSION_TYPES`와 같아야 하고,
//: `test_errorbar_review_page.py`가 둘이 같은지 봅니다.
var TYPES = ['SD', 'SE', 'SEM', 'CI95', 'IQR', 'RANGE', 'NO_ERRORBAR'];
//: 종류 대신 적을 수 있는 처분. 못 찾았다는 것도 사람의 답입니다.
var DISPOSITIONS = ['DROP', 'NOT_DATA', 'HOLD'];

//: 인용문을 요구하지 않는 답들. `NO_ERRORBAR`는 그림을 본 사람의 말이지 문장이
//: 아니고, 처분 셋은 "논문이 말하지 않는다"는 답이라 댈 문장이 없습니다.
//: 나머지에 빈 인용문을 허용하면 관문이 `NO_ERRORBAR_SOURCE`로 되돌려보냅니다.
var QUOTE_FREE = ['NO_ERRORBAR'].concat(DISPOSITIONS);

function needsQuote(code) {
  var c = String(code || '').trim().toUpperCase();
  if (!c) return false;
  return QUOTE_FREE.indexOf(c) < 0;
}

/* 한 문서의 지금 상태가 답이 되는가, 안 되면 왜 안 되는가.
 *
 * `state` = { code, quote, page, verified, note }
 * 돌려주는 것 = { ready, why, row }  - `row`는 답 CSV 한 줄이거나 null.
 */
function answerOf(doc, state) {
  var s = state || {};
  var code = String(s.code || '').trim().toUpperCase();
  var quote = String(s.quote || '').trim();
  var page = String(s.page || '').trim();
  if (!code) return { ready: false, why: '아직 고르지 않았습니다', row: null };
  if (TYPES.indexOf(code) < 0 && DISPOSITIONS.indexOf(code) < 0) {
    return { ready: false, why: '쓸 수 없는 종류입니다: ' + code, row: null };
  }
  if (needsQuote(code) && !quote) {
    return { ready: false, why: '논문이 그렇게 말한 문장을 골라 주세요', row: null };
  }
  // THE ONE THING THIS PAGE EXISTS TO ASK. 종류를 고르는 것은 판단이고, 이것은
  // 목격입니다. 둘을 한 번의 클릭으로 묶으면 고르기만 한 줄이 본 줄이 됩니다.
  if (!s.verified) {
    return { ready: false, why: 'PDF에서 이 문장을 직접 보셨다고 눌러 주세요',
             row: null };
  }
  // `doc`는 화면이 상태를 담아 두는 열쇠일 뿐입니다. 한 논문을 그림마다 따로
  // 물을 때 그 열쇠는 "논문::그림"이 되므로, 답으로 나가는 이름은 상태가 들고
  // 있는 것을 씁니다 - 열쇠를 그대로 내보내면 존재하지 않는 문서 이름이
  // 관문으로 갑니다.
  return { ready: true, why: '', row: {
    Source_Document_ID: String(s.doc || doc),
    Figure_Number: String(s.figure || ''),
    Dispersion_Type: code,
    Errorbar_Definition_Source: needsQuote(code) ? quote : '',
    Found_On_Page: needsQuote(code) ? page : '',
    Verified_In_Source: '1',
    Note: String(s.note || '').trim()
  } };
}

//: `Figure_Number`는 관문이 요구하는 열이 아니고 무시됩니다. 그림마다 답한
//: 경우에 그 답이 어느 그림 것인지 파일만 보고 알 수 있게 싣습니다 - 논문
//: 단위로 답한 줄에서는 빈칸입니다.
var CSV_COLUMNS = ['Source_Document_ID', 'Figure_Number', 'Dispersion_Type',
                   'Errorbar_Definition_Source', 'Found_On_Page',
                   'Verified_In_Source', 'Note'];

function csvCell(s) {
  return '"' + String(s === null || s === undefined ? '' : s)
    .replace(/"/g, '""') + '"';
}

/* 답이 된 줄만 내보냅니다. 반쯤 채운 줄을 함께 내보내면 관문이 그 줄을 거부하고,
 * 거부 목록이 길어지면 사람은 그 목록을 읽지 않게 됩니다.
 *
 * `docs`가 첫 인자인 것은 실수 하나 때문입니다. 화면은 상태를 문서 이름으로
 * 저장하는데, 이름을 잘못 읽으면 인용문 같은 것이 이름 자리에 들어앉습니다.
 * `states`의 열쇠를 그대로 믿으면 그 잘못된 이름이 `Source_Document_ID`가 되어
 * 관문까지 갑니다 - 관문은 그런 문서가 없다고 할 뿐, 그 이름이 어디서 왔는지는
 * 아무도 모릅니다. 이 페이지가 아는 문서만 줄이 됩니다. */
function buildCsv(docs, states) {
  var lines = [CSV_COLUMNS.join(',')];
  docs = (docs || []).slice().sort();
  for (var i = 0; i < docs.length; i++) {
    var got = answerOf(docs[i], (states || {})[docs[i]]);
    if (!got.ready) continue;
    var out = [];
    for (var c = 0; c < CSV_COLUMNS.length; c++) {
      out.push(csvCell(got.row[CSV_COLUMNS[c]]));
    }
    lines.push(out.join(','));
  }
  return lines.join('\n');
}

/* 아직 사람이 손대지 않은 문서의 수. 화면 위에 남은 일이 몇인지 적기 위한 것이고,
 * "고르기만 하고 확인은 안 누른" 문서도 남은 일로 셉니다 - 그 줄은 나가지 않으니까요. */
function remaining(docs, states) {
  var left = 0;
  for (var i = 0; i < docs.length; i++) {
    if (!answerOf(docs[i], (states || {})[docs[i]]).ready) left++;
  }
  return left;
}

if (typeof module !== 'undefined' && module.exports) {
  module.exports = { TYPES: TYPES, DISPOSITIONS: DISPOSITIONS,
                     QUOTE_FREE: QUOTE_FREE, needsQuote: needsQuote,
                     answerOf: answerOf, buildCsv: buildCsv,
                     CSV_COLUMNS: CSV_COLUMNS, remaining: remaining };
}
