<script>
/* The page's wiring. All decisions live in sheet_logic.js under test; this
 * file only moves values between the DOM, the store, and a download.
 *
 * The storage key carries the build id, so a sheet built from a different
 * draft never inherits values typed against the old one - and inside a build,
 * each entry still carries its row's fingerprint. */
(function () {
  var KEY = 'fdt_panel_counts::' + BUILD_ID;
  var store = {};
  var storageOk = true;
  var warn = document.getElementById('storagewarn');

  function showStorageWarning(text) {
    storageOk = false;
    warn.style.display = 'block';
    warn.innerHTML = '<b>입력이 이 브라우저에 저장되지 않습니다.</b> ' + text +
      ' 창을 닫거나 새로 고치면 입력이 사라집니다. ' +
      '작업을 마치기 전에 <b>CSV 내려받기</b>를 눌러 파일로 받아 두십시오.';
  }

  /* Probe rather than assume: a blocked or full store throws on write, not on
   * read, and the old sheet swallowed that in an empty catch. */
  try {
    var probe = KEY + '::probe';
    localStorage.setItem(probe, '1');
    localStorage.removeItem(probe);
  } catch (e) {
    showStorageWarning('브라우저가 저장소를 막고 있습니다 (' + e.name + ').');
  }

  if (storageOk) {
    try {
      var raw = localStorage.getItem(KEY);
      var parsed = raw ? JSON.parse(raw) : {};
      store = (parsed && typeof parsed === 'object' && !Array.isArray(parsed))
        ? parsed : {};
    } catch (e) { store = {}; }
  }

  var restored = restoreEntries(store, ROWS);
  var applied = restored.applied;
  if (restored.rejected.length) {
    var byReason = {};
    restored.rejected.forEach(function (r) {
      byReason[r.reason] = (byReason[r.reason] || 0) + 1;
    });
    var parts = Object.keys(byReason).map(function (k) {
      return ({ ROW_CHANGED: '그림 내용이 바뀜', ROW_GONE: '행이 사라짐',
                INVALID_VALUE: '값이 유효하지 않음',
                MALFORMED: '저장 형식이 깨짐' }[k] || k) + ' ' +
             byReason[k] + '건';
    });
    warn.style.display = 'block';
    warn.innerHTML = '<b>이전 입력 ' + restored.rejected.length +
      '건을 되살리지 않았습니다</b> (' + parts.join(', ') + ').' +
      ' 같은 자리에 다른 그림이 오면 값이 엉뚱한 그림에 붙기 때문에, ' +
      '되살리는 대신 버렸습니다. 해당 그림은 다시 세어 주십시오.';
  }

  var inputs = [].slice.call(document.querySelectorAll('input[data-id]'));
  var cnt = document.getElementById('cnt');
  var countable = ROWS.filter(function (r) { return r.Count_Blocked !== '1'; });

  function persist() {
    if (!storageOk) return;
    try { localStorage.setItem(KEY, JSON.stringify(store)); }
    catch (e) { showStorageWarning('저장 중 오류가 났습니다 (' + e.name + ').'); }
  }

  function tally() {
    var n = Object.keys(applied).length;
    cnt.textContent = n + ' / ' + countable.length + ' 입력됨 · 계수 불가 ' +
      (ROWS.length - countable.length) + '행 · 전체 ' + ROWS.length + '행';
  }

  function msgFor(id) {
    return document.querySelector('[data-msg="' + CSS.escape(id) + '"]');
  }

  inputs.forEach(function (i) {
    var id = i.dataset.id;
    if (applied[id] !== undefined) {
      i.value = applied[id];
      i.closest('.fig').classList.add('done');
    }
    if (i.disabled) return;
    i.addEventListener('input', function () {
      var fig = i.closest('.fig'), msg = msgFor(id);
      /* A number input hands back '' for letters, so a typed 'abc' would look
       * like "not reviewed yet" and quietly drop whatever was there. The
       * browser still knows the entry was not a number. */
      if (i.validity && i.validity.badInput) {
        fig.classList.add('err');
        fig.classList.remove('done');
        msg.textContent = '숫자가 아닙니다. 0 이상 40 이하의 정수만 입력합니다';
        delete applied[id];
        delete store[id];
        persist();
        tally();
        return;
      }
      var v = validatePanelCount(i.value);
      if (!v.ok) {
        fig.classList.add('err');
        fig.classList.remove('done');
        msg.textContent = v.error;
        delete applied[id];
        delete store[id];
        persist();
        tally();
        return;
      }
      fig.classList.remove('err');
      msg.textContent = '';
      if (v.value === null) {
        delete applied[id];
        delete store[id];
        fig.classList.remove('done');
      } else {
        applied[id] = v.value;
        store[id] = { v: v.value, fp: i.closest('.fig').dataset.fp };
        fig.classList.add('done');
      }
      persist();
      tally();
    });
  });

  document.getElementById('clr').addEventListener('click', function () {
    if (!confirm('입력한 패널 수를 모두 지웁니다. 되돌릴 수 없습니다.')) return;
    store = {};
    Object.keys(applied).forEach(function (k) { delete applied[k]; });
    if (storageOk) { try { localStorage.removeItem(KEY); } catch (e) {} }
    inputs.forEach(function (i) {
      i.value = '';
      i.closest('.fig').classList.remove('done', 'err');
      var m = msgFor(i.dataset.id); if (m) m.textContent = '';
    });
    tally();
  });

  document.getElementById('dl').addEventListener('click', function () {
    var csv = buildCsv(ROWS, applied, BUILD_ID);
    var b = new Blob(['﻿' + csv], { type: 'text/csv;charset=utf-8' });
    var a = document.createElement('a');
    a.href = URL.createObjectURL(b);
    a.download = 'observed_panel_counts_' + BUILD_ID + '.csv';
    document.body.appendChild(a); a.click(); a.remove();
  });

  tally();
})();
</script>
