# -*- coding: utf-8 -*-
"""Drag a box on the decision page in a real browser and see what comes out.

    python3 test_draw_browser.py <review_choose_NN.html>

WHY A BROWSER. `test_review_sheet.py` reads the built HTML as text: it can see
that the code says `f[0] * pw`, not that a drag lands where the person pointed.
The thing this page adds is a hand: a person drags across a figure and expects
the crop to be that figure. Between the pointer and `Human_Box` sit the image's
displayed size, the page's scroll, the card's own point dimensions and a
per-cent-of-parent overlay - none of which any text check can exercise.

So this drags a KNOWN fraction of the displayed page and checks the exported
box against the same fraction of the page's real size in points. A conversion
that used screen pixels, or the natural raster size, or forgot the scroll,
lands somewhere else and fails here.
"""
import csv
import io
import os
import re
import sys
import tempfile

from playwright.sync_api import sync_playwright

N, FAIL = [0], []


def check(name, ok, detail=""):
    N[0] += 1
    print("  %s %s%s" % ("ok  " if ok else "FAIL", name,
                         "" if ok else "  <- %s" % (detail,)))
    if not ok:
        FAIL.append(name)


#: Where the drag starts and ends, as a fraction of the displayed page.
FX0, FY0, FX1, FY1 = 0.25, 0.30, 0.75, 0.62
#: How far the exported box may sit from that, in points. A point is about a
#: third of a millimetre on paper; the rounding in the page's own arithmetic
#: costs well under one.
TOL_PT = 2.0


def drag(page, handle, x0, y0, x1, y1, steps=8):
    """Drag across the element, re-measuring first - the page reflows."""
    handle.scroll_into_view_if_needed()
    page.wait_for_timeout(80)
    b = handle.bounding_box()
    page.mouse.move(b["x"] + b["width"] * x0, b["y"] + b["height"] * y0)
    page.mouse.down()
    page.mouse.move(b["x"] + b["width"] * x1, b["y"] + b["height"] * y1, steps=steps)
    page.mouse.up()
    page.wait_for_timeout(150)
    return b


def cells(line):
    out, cur, quoted = [], "", False
    i = 0
    while i < len(line):
        ch = line[i]
        if quoted:
            if ch == '"' and i + 1 < len(line) and line[i + 1] == '"':
                cur += '"'
                i += 1
            elif ch == '"':
                quoted = False
            else:
                cur += ch
        elif ch == '"':
            quoted = True
        elif ch == ",":
            out.append(cur)
            cur = ""
        else:
            cur += ch
        i += 1
    out.append(cur)
    return out


def main(path):
    errors = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport={"width": 1200, "height": 1800})
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.on("console", lambda m: errors.append(m.text)
                if m.type == "error" else None)
        page.goto("file://" + os.path.abspath(path))
        page.wait_for_selector(".card")

        cards = page.query_selector_all(".card")
        check("카드가 있다", len(cards) > 0, len(cards))
        first = cards[0]
        did = first.get_attribute("data-id")
        pw_pt = float(first.get_attribute("data-pw"))
        ph_pt = float(first.get_attribute("data-ph"))
        check("카드가 페이지 크기를 pt로 들고 있다", pw_pt > 0 and ph_pt > 0,
              (pw_pt, ph_pt))
        check("그리기 버튼은 처음에 잠겨 있다",
              first.query_selector(".pick[data-choice='DRAWN']")
              .get_property("disabled").json_value())
        check("그린 상자 자리는 처음에 감춰져 있다",
              first.query_selector(".mine").get_property("hidden").json_value())

        # ------------------------------------------------------------- 끈다
        drag(page, first.query_selector("img.page"), FX0, FY0, FX1, FY1)
        check("끌면 페이지 위에 보라 상자가 남는다",
              not first.query_selector(".drawn").get_property("hidden").json_value())
        check("끌면 그리기 버튼이 열린다",
              not first.query_selector(".pick[data-choice='DRAWN']")
              .get_property("disabled").json_value())
        check("끌면 그 행이 DRAWN으로 골라진다",
              first.query_selector(".pick[data-choice='DRAWN']")
              .get_attribute("aria-pressed") == "true")
        check("다른 버튼은 눌리지 않는다",
              all(b.get_attribute("aria-pressed") != "true" for b in
                  first.query_selector_all(".pick:not([data-choice='DRAWN'])")))
        check("미리보기가 나타난다",
              not first.query_selector(".mine").get_property("hidden").json_value())
        size = first.query_selector(".mine canvas").evaluate(
            "c => [c.width, c.height]")
        check("미리보기 캔버스에 크기가 있다", size[0] > 10 and size[1] > 10, size)
        # 빈 캔버스는 어떤 상자를 그려도 통과합니다 - 잉크가 있어야 그림입니다.
        ink = first.query_selector(".mine canvas").evaluate(
            "c => { const d = c.getContext('2d')"
            ".getImageData(0,0,c.width,c.height).data; let n = 0;"
            " for (let i=0;i<d.length;i+=4) if (d[i] < 200) n++; return n; }")
        check("미리보기가 빈 그림이 아니다 (잉크가 있다)", ink > 50, ink)

        # ------------------------- 끌린 자리와 저장된 상자가 같은 곳을 가리키는가
        build = page.evaluate(
            "() => (document.body.innerText.match(/빌드 (review-[0-9a-f]+)/) || [])[1]")
        boxes = page.evaluate("k => JSON.parse(localStorage.getItem(k) || '{}')",
                              "fdt-review-box-" + str(build))
        got = boxes.get(did)
        check("상자가 저장됐다", bool(got), list(boxes))
        if got:
            p = [float(v) for v in got["box"].split(",")]
            want = [FX0 * pw_pt, FY0 * ph_pt, FX1 * pw_pt, FY1 * ph_pt]
            check("저장된 상자가 끌린 자리와 pt로 맞는다 (%.0fpt 이내)" % TOL_PT,
                  all(abs(a - b) < TOL_PT for a, b in zip(p, want)),
                  {"got": p, "want": [round(v, 1) for v in want]})
            check("상자가 페이지 안에 있다",
                  p[0] >= 0 and p[1] >= 0 and p[2] <= pw_pt + 0.1
                  and p[3] <= ph_pt + 0.1, p)

        # ------------------------------------------ 클릭은 상자가 되지 않는다
        second = cards[1] if len(cards) > 1 else None
        if second:
            img2 = second.query_selector("img.page")
            img2.scroll_into_view_if_needed()
            page.wait_for_timeout(80)
            b2 = img2.bounding_box()
            page.mouse.click(b2["x"] + b2["width"] * 0.5,
                             b2["y"] + b2["height"] * 0.5)
            page.wait_for_timeout(100)
            check("그냥 클릭하면 상자가 생기지 않는다",
                  second.query_selector(".pick[data-choice='DRAWN']")
                  .get_property("disabled").json_value())

        # ------------------------------------------------------------ 지우기
        first.query_selector(".mine .erase").click()
        page.wait_for_timeout(120)
        check("지우면 미리보기가 사라진다",
              first.query_selector(".mine").get_property("hidden").json_value())
        check("지우면 그리기 버튼이 다시 잠긴다",
              first.query_selector(".pick[data-choice='DRAWN']")
              .get_property("disabled").json_value())
        check("지우면 그 행의 판정도 풀린다",
              first.query_selector(".pick[data-choice='DRAWN']")
              .get_attribute("aria-pressed") == "false")

        # 고쳐 그리는 것은 무르는 것이 아니다
        drag(page, first.query_selector("img.page"), FX0, FY0, FX1, FY1)
        drag(page, first.query_selector("img.page"), FX0 + 0.05, FY0, FX1, FY1)
        check("같은 행에 다시 그려도 판정이 남아 있다",
              first.query_selector(".pick[data-choice='DRAWN']")
              .get_attribute("aria-pressed") == "true")

        if second:
            second.query_selector(".pick[data-choice='BLOCKED']").click()
            page.wait_for_timeout(80)

        # -------------------------------------- 옆 쪽으로 옮겨 그리기 (있으면)
        # 그림이 캡션의 옆 쪽에 있는 행에는 쪽 버튼이 있습니다. 옆 쪽에 그린
        # 상자는 그 쪽의 점(pt)이고, 그 쪽 번호와 함께 나가야 합니다.
        # 앞의 두 카드는 이미 다른 시나리오가 쓰고 있으므로 그 뒤에서 고른다
        nav_card = next((c for c in cards[2:] if c.query_selector(".goto")), None)
        nav_id = None
        if nav_card:
            nav_id = nav_card.get_attribute("data-id")
            cap_page = nav_card.get_attribute("data-page")
            other_btn = next(b for b in nav_card.query_selector_all(".goto")
                             if b.get_attribute("data-page") != cap_page)
            other_page = other_btn.get_attribute("data-page")
            other_btn.click()
            page.wait_for_timeout(120)
            check("쪽 버튼을 누르면 카드가 그 쪽을 보여 준다",
                  nav_card.get_attribute("data-page") == other_page,
                  nav_card.get_attribute("data-page"))
            # 속성이 아니라 그림으로 봅니다: `hidden`이 참인데도 CSS가 이겨서
            # 두 쪽이 겹쳐 보인 적이 있습니다 - 이 검사는 그때 통과했습니다.
            shown = [im.get_attribute("data-page") for im in
                     nav_card.query_selector_all("img.page") if im.is_visible()]
            check("실제로 보이는 페이지 그림은 그 쪽 하나뿐이다", shown == [other_page], shown)
            boxes_px = [im.bounding_box() for im in
                        nav_card.query_selector_all("img.page") if im.is_visible()]
            check("보이는 그림이 하나이므로 겹쳐 쌓이지 않는다",
                  len(boxes_px) == 1 and boxes_px[0]["height"] > 100)
            check("옆 쪽에서는 제안 상자 테두리가 숨는다",
                  all(b.get_property("hidden").json_value()
                      for b in nav_card.query_selector_all(".pbox")))
            opw = float(nav_card.get_attribute("data-pw"))
            oph = float(nav_card.get_attribute("data-ph"))
            img_o = next(im for im in nav_card.query_selector_all("img.page")
                         if not im.get_property("hidden").json_value())
            drag(page, img_o, 0.20, 0.25, 0.70, 0.60)
            build2 = page.evaluate(
                "() => (document.body.innerText.match(/빌드 (review-[0-9a-f]+)/) || [])[1]")
            bx = page.evaluate("k => JSON.parse(localStorage.getItem(k) || '{}')",
                               "fdt-review-box-" + str(build2)).get(nav_id)
            check("옆 쪽에 그린 상자는 그 쪽 번호를 들고 있다",
                  bx and str(bx.get("page")) == other_page, bx)
            if bx:
                p = [float(v) for v in bx["box"].split(",")]
                want = [0.20 * opw, 0.25 * oph, 0.70 * opw, 0.60 * oph]
                check("그 상자는 옆 쪽의 점(pt)이다 (%.0fpt 이내)" % TOL_PT,
                      all(abs(a - b) < TOL_PT for a, b in zip(p, want)),
                      {"got": p, "want": [round(v, 1) for v in want]})
            check("옆 쪽에 그리면 DRAWN으로 골라진다",
                  nav_card.query_selector(".pick[data-choice='DRAWN']")
                  .get_attribute("aria-pressed") == "true")
            # 캡션 쪽으로 돌아가면 상자는 안 보이고(그 쪽 것이 아니다), 다시
            # 옆 쪽으로 가면 돌아온다.
            next(b for b in nav_card.query_selector_all(".goto")
                 if b.get_attribute("data-page") == cap_page).click()
            page.wait_for_timeout(100)
            check("캡션 쪽으로 돌아가면 옆 쪽의 상자는 보이지 않는다",
                  nav_card.query_selector(".drawn").get_property("hidden").json_value())
            check("하지만 판정은 남아 있다",
                  nav_card.query_selector(".pick[data-choice='DRAWN']")
                  .get_attribute("aria-pressed") == "true")
            other_btn.click()
            page.wait_for_timeout(100)
            check("옆 쪽으로 가면 상자가 돌아온다",
                  not nav_card.query_selector(".drawn").get_property("hidden").json_value())
            # 다시 열어도 그 쪽에서 시작한다
            page.reload()
            page.wait_for_selector(".card")
            nav_card = page.query_selector(".card[data-id='%s']" % nav_id)
            check("다시 열면 상자를 그린 쪽에서 시작한다",
                  nav_card.get_attribute("data-page") == other_page,
                  nav_card.get_attribute("data-page"))
            check("다시 열어도 상자와 판정이 있다",
                  not nav_card.query_selector(".drawn").get_property("hidden").json_value()
                  and nav_card.query_selector(".pick[data-choice='DRAWN']")
                  .get_attribute("aria-pressed") == "true")
            cards = page.query_selector_all(".card")
            first = cards[0]

        # ----------------------------------------------- 페이지가 내는 CSV
        with page.expect_download() as got_dl:
            page.click("#save")
        out = os.path.join(tempfile.mkdtemp(prefix="fdt-draw-"), "export.csv")
        got_dl.value.save_as(out)
        text = io.open(out, encoding="utf-8-sig").read().strip().splitlines()
        cols = cells(text[0])
        rows = [dict(zip(cols, cells(l))) for l in text[1:]]
        check("CSV에 Human_Box 칸이 있다", "Human_Box" in cols, cols)
        check("CSV가 카드 수만큼 나온다", len(rows) == len(cards), len(rows))
        r0 = [r for r in rows if r.get("Draft_ID") == did]
        check("그린 행이 DRAWN으로 나간다",
              r0 and r0[0]["Human_Choice"] == "DRAWN",
              r0[0].get("Human_Choice") if r0 else "없음")
        check("그린 행이 상자를 들고 나간다",
              r0 and re.match(r"^[\d.]+,[\d.]+,[\d.]+,[\d.]+$", r0[0]["Human_Box"]),
              r0[0].get("Human_Box") if r0 else "없음")
        blocked = [r for r in rows if r.get("Human_Choice") == "BLOCKED"]
        if second:
            check("막은 행은 상자 없이 나간다",
                  blocked and blocked[0]["Human_Box"] == "",
                  blocked[0].get("Human_Box") if blocked else "없음")
        check("고르지 않은 행은 둘 다 비어 있다",
              all(r["Human_Box"] == "" for r in rows if not r["Human_Choice"]))
        if nav_id:
            rn = [r for r in rows if r.get("Draft_ID") == nav_id]
            check("옆 쪽에 그린 행은 그 쪽 번호와 함께 나간다",
                  rn and rn[0]["Human_Choice"] == "DRAWN"
                  and rn[0]["Human_Page"] == other_page
                  and re.match(r"^[\d.]+,[\d.]+,[\d.]+,[\d.]+$", rn[0]["Human_Box"]),
                  {k: rn[0].get(k) for k in ("Human_Choice", "Human_Page", "Human_Box")}
                  if rn else "없음")
        check("캡션 쪽에 그린 행은 쪽 번호 없이 나간다",
              r0 and r0[0].get("Human_Page", "") == "", r0[0].get("Human_Page") if r0 else "")
        # ------------------------------- 번호 칸: 있으면 CSV에 닿는가
        # 이 칸이 생기기 전, 번호를 적을 자리가 없는 채로 "번호를 적어 주십시오"
        # 라고만 하는 카드가 8행 있었습니다. 사람은 메모 칸에 적었고, 제안자를
        # 골랐고, 둘 다 Figure_Number에 닿지 못했습니다.
        nums = page.query_selector_all("input[data-number]")
        if nums:
            num = nums[0]
            ncard = num.evaluate_handle("e => e.closest('.card')").as_element()
            nid = ncard.get_attribute("data-id")
            check("번호 칸이 있는 카드는 그 사실을 표시한다",
                  "needs-number" in (ncard.get_attribute("class") or ""),
                  ncard.get_attribute("class"))
            num.fill("Figure 4b")
            page.wait_for_timeout(120)
            check("적은 번호가 브라우저 저장소에 남는다",
                  page.evaluate("k => (JSON.parse(localStorage.getItem(k)||'{}'))",
                                "fdt-review-num-" + str(build)).get(nid) == "Figure 4b",
                  page.evaluate("k => localStorage.getItem(k)",
                                "fdt-review-num-" + str(build)))
            check("번호를 적으면 그 카드의 표시가 풀린다",
                  "needs-number" not in (ncard.get_attribute("class") or ""),
                  ncard.get_attribute("class"))
            page.reload()
            page.wait_for_selector(".card")
            check("새로고침해도 적은 번호가 칸에 남아 있다",
                  page.query_selector("input[data-number]").input_value() == "Figure 4b",
                  page.query_selector("input[data-number]").input_value())
            with page.expect_download() as dl2:
                page.click("#save")
            p2 = os.path.join(tempfile.mkdtemp(), "num.csv")
            dl2.value.save_as(p2)
            lines2 = io.open(p2, encoding="utf-8-sig").read().strip().splitlines()
            cols2 = cells(lines2[0])
            rows2 = [dict(zip(cols2, cells(l))) for l in lines2[1:]]
            check("CSV에 Human_Figure_Number 칸이 있다",
                  "Human_Figure_Number" in cols2, cols2)
            rn2 = [r for r in rows2 if r["Draft_ID"] == nid]
            check("적은 번호가 그 행으로 나간다",
                  rn2 and rn2[0]["Human_Figure_Number"] == "Figure 4b",
                  rn2[0].get("Human_Figure_Number") if rn2 else "없음")
            check("번호를 적지 않은 행은 빈 채로 나간다",
                  all(r["Human_Figure_Number"] == "" for r in rows2
                      if r["Draft_ID"] != nid))
        check("자바스크립트 오류가 없다", not errors, errors[:3])
        browser.close()

    print()
    print("FDT_SCENARIOS_RUN=%d" % N[0])
    print("%d scenarios run" % N[0])
    if FAIL:
        print("%d FAILED: %s" % (len(FAIL), FAIL))
        return 1
    print("all scenarios passed")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
