# -*- coding: utf-8 -*-
"""Drive the built sheet in a real browser and check what comes out.

The second audit's W6 refused to accept "the code looks right": a value can be
typed on one figure and land on another without any line of code looking
wrong. So this types a DIFFERENT value into every enabled input, downloads the
CSV the page itself produces, and checks each value against the row it was
typed on. It also reloads the page to see the values come back to the same
figures, and blocks storage to see the page say so.
"""
import csv
import io
import json
import os
import re
import sys

from playwright.sync_api import sync_playwright

import paths as PATHS

# ONE PART, DRIVEN END TO END. The sheet is several files now; this exercises
# the largest of them, because the properties under test are per page - typing
# into a row, the export's columns, what comes back after a reload - and a
# page is a page. FDT_BROWSER_PART picks another one.
_PARTS = PATHS.parts_for(PATHS.SHEET)
if not _PARTS:
    raise SystemExit("빌드된 시트가 없습니다: %s" % PATHS.SHEET)
_PICK = os.environ.get("FDT_BROWSER_PART")
SHEET = "file://" + (_PICK if _PICK else
                     max(_PARTS, key=lambda f: os.path.getsize(f)))
print("대상 시트: %s (%d개 중)" % (os.path.basename(SHEET), len(_PARTS)))
ran = failed = 0


def check(name, cond, detail=""):
    global ran, failed
    ran += 1
    print(("ok    " if cond else "FAIL  ") + name
          + ("" if cond else "\n      " + str(detail)))
    if not cond:
        failed += 1


def read_csv(text):
    return list(csv.DictReader(io.StringIO(text.lstrip("﻿"))))


with sync_playwright() as pw:
    br = pw.chromium.launch()

    # ---------------------------------------------------------------- normal
    ctx = br.new_context(accept_downloads=True)
    pg = ctx.new_page()
    errors = []
    pg.on("pageerror", lambda e: errors.append(str(e)))
    pg.goto(SHEET)

    enabled = pg.eval_on_selector_all(
        "input[data-id]:not([disabled])", "els => els.map(e => e.dataset.id)")
    disabled = pg.eval_on_selector_all(
        "input[data-id][disabled]", "els => els.map(e => e.dataset.id)")
    # derived from the shipped page, so a redrawn draft does not need this
    # file edited - what is checked is that the two halves account for every
    # row and that neither half is empty
    total = pg.eval_on_selector_all("input[data-id]", "els => els.length")
    check("입력칸이 모든 행에 하나씩 있다 (%d)" % total,
          len(enabled) + len(disabled) == total and total > 0,
          "%d + %d vs %d" % (len(enabled), len(disabled), total))
    check("입력 가능한 행과 차단된 행이 모두 존재한다",
          len(enabled) > 0 and len(disabled) > 0,
          "%d / %d" % (len(enabled), len(disabled)))
    check("처음 열었을 때 모든 칸이 비어 있다",
          pg.eval_on_selector_all("input[data-id]",
                                  "els => els.every(e => e.value === '')"))
    check("페이지가 오류 없이 뜬다", not errors, errors[:2])

    # EVERY ENABLED INPUT GETS A VALUE ITS NEIGHBOURS DO NOT, so a swap cannot
    # hide behind two equal numbers. It was hashed from the id, which collides:
    # on the smallest part, four rows drew two values and the check that keeps
    # this from being vacuous failed for a reason that was not the page's.
    # Positional, so the values are distinct up to the 41 a panel count allows.
    want = {i: str(n % 41) for n, i in enumerate(enabled)}
    pg.evaluate(
        """m => { for (const [id, v] of Object.entries(m)) {
             const el = document.querySelector(
               'input[data-id="' + CSS.escape(id) + '"]');
             el.value = v;
             el.dispatchEvent(new Event('input', {bubbles: true}));
           } }""", want)

    with pg.expect_download() as dl:
        pg.click("#dl")
    path = dl.value.path()
    rows = read_csv(io.open(path, encoding="utf-8").read())

    check("CSV 행 수 = 화면의 행 수 (%d)" % total, len(rows) == total, len(rows))
    by = {r["Draft_ID"]: r for r in rows}
    wrong = [(i, want[i], by[i]["Observed_Panel_Count"])
             for i in enabled if by[i]["Observed_Panel_Count"] != want[i]]
    # The count is this part's, not the corpus's: it said 604 on every one of
    # the four files, each of which holds a few hundred rows.
    check("입력한 %d개 값이 전부 자기 행에 실려 나온다 (뒤바뀜 0)" % len(enabled),
          not wrong, wrong[:5])
    check("이 파트의 행 수만큼(최대 41) 서로 다른 값을 넣었다 — 검사가 "
          "무의미하지 않음",
          len(set(want.values())) == min(len(enabled), 41),
          "%d / %d" % (len(set(want.values())), len(enabled)))
    check("차단 행은 값 없이 BLOCKED_BAD_CROP로 나간다",
          all(by[i]["Observed_Panel_Count"] == ""
              and by[i]["Entry_Status"] == "BLOCKED_BAD_CROP"
              for i in disabled))
    check("모든 행에 지문과 빌드 ID가 실려 있다",
          all(re.fullmatch(r"[0-9a-f]{12}", r["Row_Fingerprint"])
              and r["Sheet_Build_ID"].startswith("sheet-") for r in rows))

    # ---- 값이 자기 행에 붙는가: 배열 첫 행이 아닌 칸을 골라서 -------------
    # A value binding to ROWS[0] instead of its own row is the defect here, so
    # the row has to be one that is NOT ROWS[0] - otherwise the check passes
    # for a page that has the bug. It used to take the first enabled input on
    # screen, which stopped being a different row once each file began
    # carrying only the rows it shows.
    first_arr = pg.evaluate("ROWS[0].Draft_ID")
    not_first = [i for i in enabled if i != first_arr]
    check("배열 첫 행이 아닌 입력칸이 있다 (이 검사가 의미를 가짐)",
          bool(not_first), "enabled=%d" % len(enabled))
    first_dom = not_first[0]
    check("입력한 값이 배열 첫 행이 아니라 자기 행에 붙는다",
          by[first_dom]["Observed_Panel_Count"] == want[first_dom]
          and by[first_arr]["Observed_Panel_Count"]
          != want.get(first_dom, "\0"))

    # ---- 빈칸은 0이 되지 않는다 -------------------------------------------
    # PICKED FROM WHAT THIS FILE HAS. The indices were 7 and 11, which is
    # fine for a part with hundreds of rows and an IndexError on the last
    # part, which has 22. Two distinct rows are all these checks need.
    check("이 파트에 서로 다른 입력칸이 둘 이상 있다", len(enabled) >= 2,
          len(enabled))
    one = enabled[min(7, len(enabled) - 1)]
    pg.evaluate("""id => { const el = document.querySelector(
          'input[data-id="' + CSS.escape(id) + '"]');
          el.value = ''; el.dispatchEvent(new Event('input', {bubbles:true})); }""",
                one)
    with pg.expect_download() as dl2:
        pg.click("#dl")
    rows2 = read_csv(io.open(dl2.value.path(), encoding="utf-8").read())
    r2 = {r["Draft_ID"]: r for r in rows2}[one]
    check("비운 칸은 빈칸·NOT_REVIEWED로 나가고 0이 되지 않는다",
          r2["Observed_Panel_Count"] == "" and r2["Entry_Status"] == "NOT_REVIEWED",
          r2)

    # ---- 유효하지 않은 값은 저장도 내보내기도 되지 않는다 ------------------
    two = enabled[min(11, len(enabled) - 2)]
    for bad in ("-1", "41", "1.5"):
        pg.evaluate("""a => { const el = document.querySelector(
              'input[data-id="' + CSS.escape(a[0]) + '"]');
              el.value = a[1]; el.dispatchEvent(new Event('input',{bubbles:true})); }""",
                    [two, bad])
        shown = pg.eval_on_selector('[data-msg="%s"]' % two, "e => e.textContent")
        check("잘못된 값 %-4s 은 화면에 사유가 뜬다" % bad, bool(shown.strip()), shown)
    # A number input reports a half-typed number as badInput with an empty
    # value: the field LOOKS blank while whatever was there is gone. Plain
    # letters are swallowed by the field and never arrive, so the reachable
    # case is "1e", "3-", "+" - and it has to be typed, not assigned.
    sel = 'input[data-id="%s"]' % two
    for partial in ("1e", "3-", "+"):
        pg.eval_on_selector(sel, "e => { e.value = ''; }")
        pg.locator(sel).press_sequentially(partial, delay=15)
        check("반쯤 입력된 숫자 %-3s 는 빈칸처럼 보여도 사유가 뜬다" % partial,
              bool(pg.eval_on_selector('[data-msg="%s"]' % two,
                                       "e => e.textContent").strip()))
        check("  그 행이 오류로 표시된다",
              pg.eval_on_selector(
                  sel, "e => e.closest('.fig').classList.contains('err')"))

    with pg.expect_download() as dl3:
        pg.click("#dl")
    rows3 = read_csv(io.open(dl3.value.path(), encoding="utf-8").read())
    r3 = {r["Draft_ID"]: r for r in rows3}[two]
    check("잘못된 값은 CSV로 나가지 않는다",
          r3["Observed_Panel_Count"] == "", r3)

    # ---- 다시 열면 값이 같은 그림으로 돌아온다 -----------------------------
    pg.reload()
    back = pg.eval_on_selector_all(
        "input[data-id]:not([disabled])",
        "els => Object.fromEntries(els.filter(e => e.value !== '')"
        ".map(e => [e.dataset.id, e.value]))")
    expect = {k: v for k, v in want.items() if k not in (one, two)}
    check("새로 고쳐도 값이 원래 그림으로 돌아온다",
          back == expect,
          {k: (expect.get(k), back.get(k)) for k in set(expect) ^ set(back)})
    ctx.close()

    # ---- 행이 바뀌면 과거 값은 되살아나지 않는다 ---------------------------
    ctx2 = br.new_context(accept_downloads=True)
    pg2 = ctx2.new_page()
    pg2.goto(SHEET)
    pg2.evaluate(
        """m => { for (const [id, v] of Object.entries(m)) {
             const el = document.querySelector(
               'input[data-id="' + CSS.escape(id) + '"]');
             el.value = v;
             el.dispatchEvent(new Event('input', {bubbles: true}));
           } }""", want)
    check("지문을 흔들기 전에는 값이 실제로 저장되어 있다",
          pg2.evaluate("""() => {
              const k = Object.keys(localStorage).find(x =>
                  x.indexOf('fdt_panel_counts::') === 0);
              return k ? Object.keys(JSON.parse(localStorage.getItem(k))).length : 0;
          }""") == len(enabled))
    pg2.evaluate("""() => {
        const k = Object.keys(localStorage).find(x =>
            x.indexOf('fdt_panel_counts::') === 0);
        const s = JSON.parse(localStorage.getItem(k) || '{}');
        for (const id of Object.keys(s)) s[id].fp = 'deadbeefdead';
        localStorage.setItem(k, JSON.stringify(s)); }""")
    pg2.reload()
    left = pg2.eval_on_selector_all(
        "input[data-id]", "els => els.filter(e => e.value !== '').length")
    check("지문이 어긋난 값은 하나도 화면에 오르지 않는다", left == 0, left)
    check("그 사실을 사용자에게 알린다",
          "되살리지 않았습니다" in pg2.eval_on_selector("#storagewarn",
                                                 "e => e.textContent"))
    ctx2.close()

    # ---- 저장소가 막히면 조용히 잃지 않는다 --------------------------------
    ctx3 = br.new_context()
    pg3 = ctx3.new_page()
    pg3.add_init_script("""Object.defineProperty(window, 'localStorage', {
        get() { throw new DOMException('denied', 'SecurityError'); } });""")
    err3 = []
    pg3.on("pageerror", lambda e: err3.append(str(e)))
    pg3.goto(SHEET)
    vis = pg3.eval_on_selector("#storagewarn",
                               "e => getComputedStyle(e).display !== 'none'")
    check("저장소가 막히면 경고가 눈에 보인다", vis)
    check("저장소가 막혀도 페이지는 죽지 않는다",
          not err3 and pg3.eval_on_selector_all(
              "input[data-id]", "e => e.length") == total, err3[:2])
    ctx3.close()
    br.close()

print("\n%d/%d passed" % (ran - failed, ran))
sys.exit(1 if failed else 0)
