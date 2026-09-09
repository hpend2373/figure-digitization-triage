# -*- coding: utf-8 -*-
"""아직 사람이 해야 할 일을, 그림과 함께 한 장에.

    python3 worklist_page.py --run RUN --plans RUN/plans_YYYY-MM-DD \
                             --out RUN/worklist.html

계획서는 그림마다 `Needs`를 적습니다. 그 목록은 CSV 안에 있고, CSV 안에서는
"패널 기하 302"가 숫자 하나입니다 - 어느 그림인지, 그 그림이 어떻게 생겼는지,
왜 그 일이 남았는지는 보이지 않습니다.

이 페이지는 **답을 받지 않습니다.** 무엇이 남았는지 보여 주고, 각 일이 어느
도구로 가는지 적을 뿐입니다. 답을 받는 자리는 따로 있고(오차 정의는
`errorbar_review_page`, 계수는 계수 시트), 한 화면에서 두 가지를 하면 어느
쪽도 자기 규율을 지키지 못합니다.
"""
import argparse
import collections
import csv
import io
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from page_bits import CSS, THUMB_SMALL, esc, thumb                # noqa: E402

FIGURES = "plan_figures.csv"
COUNTS = "observed_panel_counts.csv"

#: 할 일마다, 그 일을 실제로 하는 자리. 페이지가 "무엇이 남았다"까지만 말하고
#: 어디서 하는지를 말하지 않으면, 목록을 본 사람은 다시 물어야 합니다.
WHERE = {
    "패널 기하 (읽을 자리·눈금·표 종류)":
        "계획서의 패널마다 읽을 자리와 눈금을 씁니다 (WebPlotDigitizer 프로젝트).",
    "오차 정의":
        "errorbar_review_page.py가 내는 판정 페이지에서 답합니다.",
    "셀 수 없다고 하신 그림 — 처분 결정":
        "이 그림을 버릴지(NOT_DATA), 다시 자를지, 그대로 둘지 정합니다.",
    "캡션이 스스로 어긋난 그림 — 어느 패널이 데이터인지 확인":
        "캡션에 not-data 낱말과 오차 정의가 같이 있습니다. 그림을 보고 "
        "어느 패널이 값을 담고 있는지 정합니다.",
    "대상 그림이 아니라고 하신 크롭 — 처분 결정 또는 재크롭":
        "이의를 적어 두신 크롭입니다.",
}


def _rows(path):
    if not os.path.exists(path):
        return []
    with io.open(path, encoding="utf-8-sig") as fh:
        return list(csv.DictReader(fh))


def needs_of(row):
    """이 그림에 남은 일들. 계획서가 적어 준 그대로."""
    return [n.strip() for n in (row.get("Needs") or "").split(" · ") if n.strip()]


def build(run, plans, log=print):
    """(html, 그림 수, 일 수)."""
    figs = _rows(os.path.join(plans, FIGURES))
    counted = dict((r["Draft_ID"], r) for r in _rows(os.path.join(run, COUNTS)))
    live = [r for r in figs if needs_of(r)]
    if not live:
        raise SystemExit("%s에 남은 일이 없습니다." % os.path.join(plans, FIGURES))

    order, by_need = [], collections.OrderedDict()
    for r in live:
        for n in needs_of(r):
            if n not in by_need:
                by_need[n] = []
                order.append(n)
            by_need[n].append(r)
    order.sort(key=lambda n: -len(by_need[n]))

    out = []
    w = out.append
    w("<!doctype html><html lang='ko'><head><meta charset='utf-8'>")
    w("<meta name='viewport' content='width=device-width,initial-scale=1'>")
    w("<title>남은 일 — 그림 %d개</title>" % len(live))
    w(CSS)
    w("""<style>
/* `.grid{display:grid}`가 `[hidden]{display:none}`과 명시도가 같아서, 뒤에
   오는 쪽이 이깁니다 - 탭을 눌러도 숨겨지지 않았습니다. 브라우저로 돌려
   보고서야 알았습니다. */
[hidden]{display:none!important}
.tabs{display:flex;flex-wrap:wrap;gap:8px;margin:10px 0 0}
.tab{font:13px inherit;padding:6px 12px;border:1px solid #c9c9c2;border-radius:16px;
background:#fff;cursor:pointer}
.tab.on{background:#1a1a1a;color:#fff;border-color:#1a1a1a}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:14px}
.card{background:#fff;border:1px solid #ddddd8;border-radius:8px;padding:10px}
.card img{display:block;width:100%;height:auto;border-radius:4px;background:#f4f4f2}
.card .who{font:12px ui-monospace,Menlo,monospace;color:#55554f;margin:7px 0 2px;
word-break:break-all}
.card .what{font-size:13px;font-weight:600}
.card .meta{font-size:12px;color:#55554f;margin-top:4px}
.card .said{font-size:12px;color:#8a5a12;margin-top:4px}
.why{color:#5a5a56;font-size:13px;margin:2px 0 14px;max-width:80ch}
</style>""")
    w("<header><h1>남은 일 <span class='count'>그림 %d · 패널 %d · 논문 %d</span></h1>"
      % (len(live),
         sum(int(r.get("Observed_Panel_Count") or 0) for r in live),
         len(set(r["Publication_ID"] for r in live))))
    w("<p class='note'>계획서가 그림마다 적어 둔 <b>남은 일</b>입니다. 이 "
      "페이지는 <b>답을 받지 않습니다</b> — 무엇이 남았는지 보여 주고, 각 일을 "
      "어디서 하는지 적을 뿐입니다.</p>")
    w("<div class='tabs'><button class='tab on' data-need=''>전체 %d</button>"
      % sum(len(v) for v in by_need.values()))
    for n in order:
        w("<button class='tab' data-need='%s'>%s %d</button>"
          % (esc(n), esc(n.split(" — ")[0].split(" (")[0]), len(by_need[n])))
    w("</div></header><main>")

    for n in order:
        w("<h3 class='sec' data-sec='%s'>%s <span class='count'>%d</span></h3>"
          % (esc(n), esc(n), len(by_need[n])))
        w("<p class='why' data-sec='%s'>%s</p>" % (esc(n), esc(WHERE.get(n, ""))))
        w("<div class='grid' data-sec='%s'>" % esc(n))
        for r in sorted(by_need[n], key=lambda x: (x["Publication_ID"],
                                                   len(x["Figure_Number"]),
                                                   x["Figure_Number"])):
            w(card(run, r, counted.get(r["Draft_ID"], {})))
        w("</div>")

    w("</main><script>%s</script></body></html>" % TABS_JS)
    log("그림 %d개 · 일 %d개 · 논문 %d편"
        % (len(live), sum(len(v) for v in by_need.values()),
           len(set(r["Publication_ID"] for r in live))))
    return "\n".join(out), len(live), sum(len(v) for v in by_need.values())


def card(run, row, count):
    out = []
    w = out.append
    w("<div class='card'>")
    src = thumb(os.path.join(run, (row.get("Image") or "")), THUMB_SMALL)
    if src:
        w("<img src='%s' loading='lazy' alt='%s'>" % (src, esc(row["Figure_Number"])))
    else:
        w("<div class='nofig'>크롭 없음</div>")
    w("<div class='what'>%s · p.%s · 패널 %s</div>"
      % (esc(row["Figure_Number"]), esc(row["Page"]),
         esc(row.get("Observed_Panel_Count") or "?")))
    w("<div class='who'>%s</div>" % esc(row["Publication_ID"]))
    bits = []
    if (row.get("Statistic_Type") or "").strip():
        bits.append(row["Statistic_Type"])
    if (row.get("Dispersion_Type") or "").strip():
        bits.append("%s (%s)" % (row["Dispersion_Type"],
                                 row.get("Errorbar_Source_Kind") or "?"))
    if (row.get("Disposition") or "").strip():
        bits.append(row["Disposition"])
    w("<div class='meta'>%s</div>" % esc(" · ".join(bits)))
    # 사람이 계수 시트에 적어 둔 말. 이 페이지가 그것을 되풀이하지 않으면,
    # 왜 이 그림이 여기 있는지는 다시 시트를 열어야 알 수 있습니다.
    said = (count.get("Uncountable_Reason") or "").strip() \
        or (count.get("Objection_Reason") or "").strip()
    if said:
        w("<div class='said'>적어 두신 말: %s</div>" % esc(said[:200]))
    w("</div>")
    return "\n".join(out)


TABS_JS = r"""
(function () {
  var tabs = Array.prototype.slice.call(document.querySelectorAll('.tab'));
  function show(need) {
    Array.prototype.slice.call(document.querySelectorAll('[data-sec]'))
      .forEach(function (el) {
        el.hidden = !!need && el.getAttribute('data-sec') !== need;
      });
    tabs.forEach(function (t) {
      t.classList.toggle('on', t.getAttribute('data-need') === need);
    });
  }
  tabs.forEach(function (t) {
    t.addEventListener('click', function () { show(t.getAttribute('data-need')); });
  });
  show('');
})();
"""


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run", required=True)
    ap.add_argument("--plans", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    html, _n, _w = build(os.path.expanduser(a.run), os.path.expanduser(a.plans))
    with io.open(os.path.expanduser(a.out), "w", encoding="utf-8") as fh:
        fh.write(html)
    print("페이지: %s (%.1f MB)"
          % (a.out, os.path.getsize(os.path.expanduser(a.out)) / 1e6))
    return 0


if __name__ == "__main__":
    sys.exit(main())
