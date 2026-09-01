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

  /* THE PICTURE, AT THE SIZE IT WAS CUT. The grid's thumbnail is 300px wide;
   * the crop it came from is not, and until now those pixels were not in the
   * page at all. Clicking the thumbnail - or pressing z on a row - opens the
   * large copy. Nothing here suggests a count; it only lets one be seen. */
  var lb = document.getElementById('lb');
  var lbimg = document.getElementById('lbimg');
  var lbcap = document.getElementById('lbcap');

  function openZoom(fig) {
    var t = fig && fig.querySelector('img.thumb[data-zoom]');
    if (!t) return;
    lbimg.src = t.getAttribute('data-zoom');
    var cap = fig.querySelector('.cap');
    lbcap.textContent = cap ? cap.textContent.slice(0, 160) : '';
    lb.classList.add('on');
  }

  function closeZoom() { lb.classList.remove('on'); lbimg.removeAttribute('src'); }

  lb.addEventListener('click', function (e) {
    if (e.target === lb || e.target.id === 'lbclose') closeZoom();
  });
  document.getElementById('lbclose').addEventListener('click', closeZoom);
  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape' && lb.classList.contains('on')) closeZoom();
  });
  document.addEventListener('click', function (e) {
    var t = e.target;
    if (t && t.tagName === 'IMG' && t.classList.contains('thumb')) {
      openZoom(t.closest('.fig'));
    }
  });

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
    var r = remaining(ROWS, applied);
    cnt.textContent = r.done + ' / ' + r.open + ' 입력됨 · 남은 ' + r.left +
      '행 · 계수 불가 ' + (ROWS.length - r.open) + '행 · 전체 ' +
      ROWS.length + '행';
  }

  var byInput = {};

  /* ENTER GOES TO THE NEXT ROW THAT CAN TAKE A NUMBER. 415 of these means 415
   * reaches for the mouse otherwise, and a hand that leaves the keyboard
   * between every figure is a hand that starts skipping. Where "next" is
   * lives in sheet_logic.js, under test. */
  function focusRow(id) {
    var el = byInput[id];
    if (!el) return;
    el.focus();
    var fig = el.closest('.fig');
    fig.scrollIntoView({ block: 'center' });
    document.querySelectorAll('.fig.here').forEach(function (f) {
      f.classList.remove('here');
    });
    fig.classList.add('here');
  }

  function msgFor(id) {
    return document.querySelector('[data-msg="' + CSS.escape(id) + '"]');
  }

  inputs.forEach(function (i) {
    var id = i.dataset.id;
    byInput[id] = i;
    if (!i.disabled) {
      i.addEventListener('keydown', function (e) {
        if (e.key === 'Enter') {
          e.preventDefault();
          var nxt = nextOpenId(ROWS, id);
          if (nxt) focusRow(nxt);
          else i.blur();
        } else if (e.key === 'z' || e.key === 'Z') {
          /* The picture is a keystroke away, so looking closer costs nothing.
           * A count made without looking closer is the thing to avoid. */
          e.preventDefault();
          openZoom(i.closest('.fig'));
        }
      });
      i.addEventListener('focus', function () {
        document.querySelectorAll('.fig.here').forEach(function (f) {
          f.classList.remove('here');
        });
        i.closest('.fig').classList.add('here');
      });
    }
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
