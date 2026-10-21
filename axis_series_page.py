# -*- coding: utf-8 -*-
"""축·눈금과 계열(정체) 제안을 한 카드에 함께 놓는 확인 페이지.

    python3 axis_series_page.py --run RUN --geometry GDIR --identity IDIR \\
        --proposals PROPOSALS.json --out PAGE.html [--date 2026-10-16]

기하 확인(`geometry_page`)과 정체 확인(`identity_page`)을 한 번에 묻습니다. 사람은 패널마다
그림 두 장(축·눈금 오버레이, 계열·이름 오버레이)과 제안 표를 보고 두 부분에 각각
**제안대로 / 고칠 곳 있음 / 보류**를 답하고, **두 그림을 직접 봤다**를 누릅니다. '제안대로'는
미리 골라져 있고 목격은 미리 눌러져 있지 않습니다(`axis_series_page.js`의 머리말).

**판정 논리를 새로 짓지 않습니다.** 페이지는 `geometry_page.js`·`identity_page.js`를 각자의
모듈 범위에 싣고, 카드마다 두 페이지의 `build`가 짓는 것과 같은 META에 제안을 얹은 상태를 그
파일들의 `verdictOf`에 넘깁니다. '제안대로'가 내보내는 관문 줄은 두 페이지에서 같은 값을 손으로
넣었을 때와 같고, `route_axis_series.py`가 그것을 `record_geometry`·`record_identity`의 답
CSV로 나눕니다.

## 제안 파일 (PROPOSALS.json)

리더(`geometry_proposer`·`identity_proposer`)가 읽은 것은 제안 CSV에 있고, 이 파일은 그 위에
누군가(대개 Claude가 그림을 보고) 얹는 몫입니다. 패널마다:

    {"BY": "Claude",                                  # 제안한 쪽 - 카드와 Note에 그 이름으로
     "P": {"<Draft_ID>__p<i>": {
        "geo": {"verdict": "CONFIRMED|SHARED|REJECTED|HOLD",
                "top": "", "bottom": "",              # 맨 위·맨 아래 눈금 값 - 비우면 리더가 읽은 것
                "rows": [],                           # 그 두 값이 붙는 래스터 행 - 비우면 리더가 잰 눈금의 양 끝
                "frame": "",                          # 다시 그린 프레임 'x0,x1,y0,y1'(정수) - 비우면 리더 프레임
                "shared": "", "say": "한 줄 근거"},
        "idn": {"verdict": "CONFIRMED|REJECTED|HOLD",
                "xFactor": "", "positions": [{"label": "", "px": 0}],   # positions 비우면 리더가 읽은 x 라벨
                "seriesFactor": "", "series": [{"name": "", "colour": [r, g, b] | null, "line_style": "",
                                                "marker": "", "marker_fill": "", "bar_fill": "", "cue": ""}],
                "markType": "", "route": "AUTO|MANUAL", "outcome": "", "unit": "", "n": "",
                "barTop": "", "stem": true, "say": "한 줄 근거"},
        "look": "사람이 먼저 볼 것 (없으면 빈칸)"}}}

`frame`을 다시 그린 패널은 이 페이지에 내기 **전에** `propose_run.py reframe`으로 정체 제안을
같은 프레임 위에서 다시 내야 합니다 - 그렇지 않으면 이 빌더가 멈춥니다(`FRAMES_DISAGREE`).
'고칠 곳 있음'으로 돌아온 패널만 다시 물을 때는 그 패널만 든 제안 파일과 `--subset`.
결과 이름·단위가 리더가 읽은 것과 같으면 리더의 것으로 나가고(Value_Sources `READ`), 다르면
제안의 것이 나갑니다. 리더가 읽은 단위가 그림에 없는 것이라 비워야 하면 `unit`을 빈칸으로
두면 됩니다(`unitBlank`).
"""
import argparse
import base64
import csv
import datetime
import io
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from page_bits import CSS, esc                                   # noqa: E402
import geometry_proposer as GP                                   # noqa: E402
import identity_proposer as IP                                   # noqa: E402

LOGIC = "axis_series_page.js"
#: 오버레이를 싣는 크기(긴 변). 눈금 숫자가 읽히고, 96패널이 20 MB 안에 드는 만큼.
MAXDIM = 1000
FRAME_KEYS = ("Panel_X0", "Panel_X1", "Panel_Y0", "Panel_Y1")


def rows(path):
    with io.open(path, encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def data_url(path, maxdim=MAXDIM, colours=96):
    """(data URL, 원래 (w, h)). 색을 줄인 PNG - 오버레이는 선과 글자라 96색이면 됩니다."""
    from PIL import Image
    im = Image.open(path).convert("RGB")
    w, h = im.size
    s = min(1.0, float(maxdim) / max(w, h))
    if s < 1:
        im = im.resize((int(round(w * s)), int(round(h * s))), Image.LANCZOS)
    buf = io.BytesIO()
    im.quantize(colors=colours, method=Image.MEDIANCUT, dither=Image.NONE).save(buf, "PNG", optimize=True)
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode(), (w, h)


def crop_url(path):
    from PIL import Image
    im = Image.open(path).convert("RGB")
    im.thumbnail((1300, 1300))
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=78)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


def short(fid):
    return fid if len(fid) < 46 else fid[:20] + "…" + fid[-22:]


def order_of(ids):
    return sorted(ids, key=lambda p: (p.split("__p")[0], int(p.split("__p")[1])))


def metas(G, I, order):
    """(gmeta, imeta) - geometry_page.build·identity_page.build가 카드마다 짓는 것과 같은 META."""
    by_raster = {}
    for p in order:
        by_raster.setdefault(G[p]["Raster"], []).append(p)
    gmeta, imeta = {}, {}
    for p in order:
        g, i = G[p], I[p]
        marks = [m for m in (g.get("Y_Tick_Pixels") or "").split(";") if m]
        gmeta[p] = {"proposal": p, "readPairs": (g.get("Y_Tick_Read_Values") or "").strip(),
                    "topPixel": marks[0] if marks else "", "bottomPixel": marks[-1] if marks else "",
                    "siblings": [s for s in by_raster[g["Raster"]] if s != p],
                    "sharedCandidate": (g.get("Y_Axis_Shared_Candidate") or "").strip(),
                    "originX": GP.overlay_origin(g)[0], "originY": GP.overlay_origin(g)[1],
                    "frameTop": (g.get("Panel_Y0") or "").strip(), "frameBottom": (g.get("Panel_Y1") or "").strip(),
                    "noFrame": False, "region": (g.get("Region") or "").strip()}
        imeta[p] = {"proposal": p, "readLabels": (i.get("X_Labels_Read") or "").strip(),
                    "readSeries": (i.get("Series_Read") or "").strip(),
                    "readOutcome": (i.get("Outcome_Read") or "").strip(), "readUnit": (i.get("Unit_Read") or "").strip(),
                    "readN": (i.get("N_Read") or "").strip(), "markProposed": (i.get("Mark_Type_Proposed") or "").strip(),
                    "kind": (i.get("Panel_Kind") or "").strip().upper(),
                    "frameX0": (i.get("Panel_X0") or "").strip(), "frameX1": (i.get("Panel_X1") or "").strip(),
                    "originX": IP.overlay_origin(i)[0], "originY": IP.overlay_origin(i)[1]}
    return gmeta, imeta


def states(proposal, imeta, by):
    """제안 한 패널 -> (기하 상태 칸, 정체 상태 칸, 기하 출처, 정체 출처).

    상태 칸은 geometry_page.js·identity_page.js의 verdictOf가 받는 이름 그대로입니다. 출처는
    무엇을 누가 냈는지 - 리더와 제안한 쪽을 가르고, 관문 줄의 Note에 그대로 남습니다."""
    cg, ci = proposal["geo"], proposal["idn"]
    gs, gsrc = {"verdict": cg["verdict"]}, []
    if cg.get("frame"):
        gs.update(frame=cg["frame"], pickedTopPixel=cg["rows"][0], pickedBottomPixel=cg["rows"][1],
                  top=cg["top"], bottom=cg["bottom"])
        gsrc += ["프레임 %s(다시 그림)" % by, "눈금 값·행 %s" % by]
    elif cg.get("rows"):
        gs.update(pickedTopPixel=cg["rows"][0], pickedBottomPixel=cg["rows"][1], top=cg["top"], bottom=cg["bottom"])
        gsrc += ["프레임 리더", "눈금 값·행 %s" % by]
    elif str(cg.get("top", "")) != "":
        gs.update(top=cg["top"], bottom=cg["bottom"])
        gsrc += ["프레임 리더", "눈금 값 %s(행은 리더가 잰 것)" % by]
    else:
        gsrc += ["프레임 리더", "눈금 값 리더"]
    if cg.get("shared"):
        gs["sharedWith"] = cg["shared"]
    ist, isrc = {"verdict": ci["verdict"]}, []
    if ci["verdict"] == "CONFIRMED":
        ist.update(xFactor=ci["xFactor"], seriesFactor=ci["seriesFactor"], markType=ci["markType"],
                   series=ci["series"], route=ci.get("route", "AUTO"), n=ci.get("n", ""),
                   barTop=ci.get("barTop", ""), stem=bool(ci.get("stem")), positions=ci.get("positions") or [])
        same_out = ci["outcome"] == imeta["readOutcome"]
        same_unit = ci["unit"] == imeta["readUnit"]
        ist["outcome"] = "" if same_out else ci["outcome"]
        ist["unit"] = "" if same_unit else ci["unit"]
        if not same_unit and ci["unit"] == "":
            ist["unitBlank"] = True
        isrc += ["x 라벨·자리 %s" % (by if ci.get("positions") else "리더"), "x 요인·계열·표 종류 %s" % by,
                 "결과 이름 %s · 단위 %s" % ("리더" if same_out else by, "리더" if same_unit else by)]
    else:
        isrc.append("'%s' %s" % ({"REJECTED": "읽지 않는다", "HOLD": "보류"}.get(ci["verdict"], ci["verdict"]), by))
    return gs, ist, " · ".join(gsrc), " · ".join(isrc)


def check_inputs(G, I, P, subset=False):
    """빌더가 멈출 까닭 [(pid, 코드, 사유)]. 하나라도 있으면 페이지를 짓지 않습니다.

    `subset`이면 제안 파일에 있는 패널만 봅니다 - '고칠 곳 있음'으로 돌아온 패널만 다시 물을 때."""
    stops = []
    for pid in sorted(set(P) if subset else set(G) | set(I) | set(P)):
        if pid not in P:
            stops.append((pid, "NO_PROPOSAL", "리더 제안은 있는데 얹을 제안이 없습니다"))
        elif pid not in G or pid not in I:
            stops.append((pid, "NO_READER_PROPOSAL", "기하 또는 정체 제안 CSV에 없습니다"))
        else:
            fr = P[pid]["geo"].get("frame") or ""
            want = [str(int(float(v))) for v in fr.split(",")] if fr else [str(int(float(G[pid][k]))) for k in FRAME_KEYS]
            have = [str(int(float(I[pid][k]))) for k in FRAME_KEYS]
            if want != have:
                stops.append((pid, "FRAMES_DISAGREE",
                              "기하 %s, 정체 %s - 다시 그린 프레임이면 propose_run.py reframe을 먼저"
                              % (",".join(want), ",".join(have))))
    return stops


def build(run, geometry, identity, proposals_path, date, log=print, subset=False):
    with io.open(proposals_path, encoding="utf-8") as fh:
        data = json.load(fh)
    P, by = data["P"], data.get("BY") or "제안"
    G = {r["Proposal_ID"]: r for r in rows(os.path.join(geometry, "geometry_proposal.csv"))}
    I = {r["Proposal_ID"]: r for r in rows(os.path.join(identity, IP.PROPOSALS))}
    stops = check_inputs(G, I, P, subset)
    if stops:
        raise SystemExit("\n".join("멈춤 %s — %s: %s" % s for s in stops) + "\n페이지를 짓지 않았습니다.")
    drafts = {r["Draft_ID"]: r for r in rows(os.path.join(run, "figure_intake_draft.csv"))}
    order = order_of(P)
    gmeta, imeta = metas(G, I, order)
    gstate, istate, prov = {}, {}, {}
    for p in order:
        gs, ist, pg, pi = states(P[p], imeta[p], by)
        gstate[p], istate[p], prov[p] = gs, ist, {"geo": pg, "idn": pi}

    W = []
    w = W.append
    w("<!doctype html><html lang='ko'><head><meta charset='utf-8'>"
      "<meta name='viewport' content='width=device-width,initial-scale=1'>")
    w("<title>축·계열 확인 — 패널 %d개 (%s)</title>" % (len(order), esc(date)))
    w(CSS)
    w(STYLE)
    w("</head><body><header><h1>축·계열 확인 — 패널 %d개 <span class='count' id='left'></span></h1>" % len(order))
    w("<p style='margin:4px 0 0'>보신 분 <input id='who' size='12' placeholder='이름'> &nbsp; "
      "<button id='next'>다음 확인할 카드 ↓</button> &nbsp; "
      "<button id='dl'>CSV 내려받기</button> <span class='count' id='msg'></span></p></header><main>")
    w("<div class='doc'><p class='note' style='margin-top:0'>축·눈금(리더)과 계열(정체) 제안입니다. 리더가 못 읽거나 "
      "틀린 자리는 <b>%s가 그림을 보고 채운 제안</b>이고, 아무것도 확인되지 않았습니다.</p>" % esc(by))
    w("<p class='note'>왼쪽 그림은 <b>축·눈금</b>: 빨강=리더 프레임, 자홍=리더가 읽은 눈금 숫자, "
      "<span style='color:#1e64c8'>파랑 점선=%s가 다시 그린 프레임과 값을 붙인 눈금 행</span>. 오른쪽 그림은 "
      "<b>계열·이름</b>: 빨강=그 카드의 프레임, 파랑=x 라벨 자리, 자홍=리더가 읽은 y축 제목.</p>" % esc(by))
    w("<p class='note'><b>모든 카드에 '제안대로'가 미리 골라져 있습니다.</b> 그림을 보고 맞으면 <b>두 그림을 직접 봤다</b>만 "
      "누르시면 됩니다(이 칸은 미리 누르지 않았습니다 — 본 일은 보신 분만 적을 수 있습니다). 다르면 그 부분을 "
      "<b>고칠 곳 있음</b>으로 바꾸고 메모에 무엇을, 또는 <b>보류</b>. '제안대로'가 내보내는 줄은 기하·정체 확인 페이지의 "
      "논리가 그대로 짓습니다.</p>")
    looks = [p for p in order if P[p].get("look")]
    w("<p class='note'><b>먼저 보세요 (%d):</b> %s</p></div>" % (len(looks), " · ".join(
        "<a href='#c-%s'>%s p%s</a>" % (esc(p), esc(short(p.split('__p')[0])), p.split('__p')[1]) for p in looks)))
    cur = None
    for p in order:
        fid, idx = p.split("__p")
        if fid != cur:
            cur = fid
            d = drafts.get(fid, {})
            crop = os.path.join(run, d.get("Figure_Crop") or "")
            w("<section class='fig'><h2>%s <span class='sub'>· %s · 패널 %d개</span></h2>"
              % (esc(fid), esc(d.get("Source_File") or ""), sum(1 for q in order if q.startswith(fid + "__p"))))
            w("<p class='note'>%s</p>" % esc((d.get("Caption_Text") or "").strip()[:400]))
            if d.get("Figure_Crop") and os.path.isfile(crop):
                w("<details><summary>그림 전체 보기</summary><img src='%s' alt=''></details>" % crop_url(crop))
            w("</section>")
        w(card(p, G[p], I[p], P[p], gmeta[p], imeta[p], prov[p], geometry, identity, by))
    w("</main><script>")
    payload = {"order": order, "gmeta": gmeta, "imeta": imeta, "prov": prov, "date": date, "proposer": by,
               "proposals": {p: {"geo": gstate[p], "idn": istate[p]} for p in order}}
    w("var DATA = %s;" % json.dumps(payload, ensure_ascii=False))
    for name, fn in (("GEO", "geometry_page.js"), ("IDN", "identity_page.js"), ("AX", LOGIC)):
        with io.open(os.path.join(HERE, fn), encoding="utf-8") as fh:
            w("var %s = (function () { var module = { exports: {} };\n%s\n; return module.exports; })();" % (name, fh.read()))
    w(PAGE_JS)
    w("</script></body></html>")
    html = "\n".join(W)
    info = {"panels": len(order), "figures": len({p.split("__p")[0] for p in order}), "looks": len(looks)}
    log("패널 %(panels)d · 그림 %(figures)d · 먼저 보세요 %(looks)d" % info)
    return html, info


def series_text(ci):
    out = []
    for s in ci.get("series") or []:
        col = s.get("colour")
        bits = [b for b in (("#%02X%02X%02X" % tuple(col)) if col else "", s.get("marker", ""), s.get("marker_fill", ""),
                            s.get("line_style", ""), s.get("bar_fill", "")) if b]
        sw = ("<i class='sw' style='background:#%02X%02X%02X'></i>" % tuple(col)) if col else ""
        out.append("%s<b>%s</b>%s%s" % (sw, esc(s.get("name")), (" <span class='sub'>(%s)</span>" % esc(" ".join(bits))) if bits else "",
                                        (" <span class='cue'>— %s</span>" % esc(s["cue"])) if s.get("cue") else ""))
    return "<br>".join(out)


def card(p, g, i, prop, gm, im, prov, geometry, identity, by):
    cg, ci = prop["geo"], prop["idn"]
    fid, idx = p.split("__p")
    out = []
    w = out.append
    w("<div class='doc' id='c-%s' data-id='%s'>" % (esc(p), esc(p)))
    w("<h3 style='margin:0 0 6px;font-size:15px'>p%s <span class='sub'>%s · %s</span></h3>"
      % (esc(idx), esc((g.get("Note") or "").split(" ", 2)[-1]), esc(short(fid))))
    w("<div class='pics'>")
    gu, (gw, gh) = data_url(os.path.join(geometry, p + ".png"))
    ox, oy = gm["originX"], gm["originY"]
    ov = []
    if cg.get("frame"):
        x0, x1, y0, y1 = [float(t) for t in cg["frame"].split(",")]
        ov.append("<div class='ov ovf' style='left:%.3f%%;top:%.3f%%;width:%.3f%%;height:%.3f%%'></div>"
                  % ((x0 - ox) / gw * 100, (y0 - oy) / gh * 100, (x1 - x0) / gw * 100, (y1 - y0) / gh * 100))
    marked = cg.get("rows") or ([gm["topPixel"], gm["bottomPixel"]] if str(cg.get("top", "")) != "" else [])
    for rr, val in zip(marked, (cg.get("top"), cg.get("bottom"))):
        if str(rr) != "":
            ov.append("<div class='ov ovr' style='left:0;right:0;top:%.3f%%'><span>%s</span></div>"
                      % ((float(rr) - oy) / gh * 100, esc(val)))
    w("<div class='pic'><div class='cap'>축·눈금</div><div style='position:relative'><img src='%s' alt=''>%s</div></div>"
      % (gu, "".join(ov)))
    iu, (iw, ih) = data_url(os.path.join(identity, p + ".png"))
    ox, oy = im["originX"], im["originY"]
    ov = []
    if ci["verdict"] == "CONFIRMED":
        for pos in ci.get("positions") or []:
            ov.append("<div class='ov ovx' style='left:%.3f%%;top:%.3f%%;height:4%%'><span>%s</span></div>"
                      % ((float(pos["px"]) - ox) / iw * 100, (float(i["Panel_Y1"]) - oy) / ih * 100 - 4, esc(pos["label"])))
    w("<div class='pic'><div class='cap'>계열·이름</div><div style='position:relative'><img src='%s' alt=''>%s</div></div>"
      % (iu, "".join(ov)))
    w("</div><table class='pr'>")
    if str(cg.get("top", "")) != "":
        vals = "맨 위 <b>%s</b> · 맨 아래 <b>%s</b>" % (esc(cg["top"]), esc(cg["bottom"]))
    else:
        vals = "리더가 읽은 눈금: %s" % esc(", ".join(x.split("@")[0] for x in (g.get("Y_Tick_Read_Values") or "").split(";") if x))
    frame_txt = ("%s가 다시 그린 프레임 <code>%s</code>" % (esc(by), esc(cg["frame"]))) if cg.get("frame") else \
        "리더 프레임 <code>%s</code>" % esc(",".join(g.get(k, "") for k in FRAME_KEYS))
    if cg["verdict"] == "SHARED":
        vals = "다른 패널의 축을 씀: <b>%s</b>" % esc(cg.get("shared"))
    w("<tr><th>축·눈금</th><td>%s<br>%s<div class='say'>%s</div><div class='src'>제안: %s</div></td></tr>"
      % (vals, frame_txt, esc(cg.get("say")), esc(prov["geo"])))
    if ci["verdict"] == "CONFIRMED":
        xs = ci.get("positions") or [{"label": t, "px": px} for t, px in IP.labels_of(i.get("X_Labels_Read"))]
        w("<tr><th>x</th><td><b>%s</b>: %s</td></tr>" % (esc(ci["xFactor"]), " · ".join(esc(x["label"]) for x in xs)))
        w("<tr><th>계열</th><td><b>%s</b> · %s · 판독 %s<br>%s</td></tr>"
          % (esc(ci["seriesFactor"]), esc(ci["markType"]),
             "<b>사람(MANUAL)</b>" if ci.get("route") == "MANUAL" else "판독기(AUTO)", series_text(ci)))
        extra = []
        if ci["markType"].startswith("BAR"):
            extra.append("막대 값: %s" % {"OUTLINE_CENTER": "윤곽선 중심", "FILL_EDGE": "채움 가장자리",
                                          "MARKER_CENTER": "마커 중심", "FILL_ONLY": "테두리 없음(채움 끝)"}.get(ci.get("barTop"), ci.get("barTop")))
        if ci["markType"] not in ("SCATTER", "BOX_VIOLIN"):
            extra.append("오차막대 줄기가 마크에 붙음: %s" % ("예" if ci.get("stem") else "아니오"))
        if ci.get("n"):
            extra.append("n %s" % esc(ci["n"]))
        w("<tr><th>결과변수</th><td><b>%s</b>%s%s</td></tr>"
          % (esc(ci["outcome"]), (" [%s]" % esc(ci["unit"])) if ci["unit"] else " [단위 없음]",
             ("<br><span class='sub'>%s</span>" % " · ".join(extra)) if extra else ""))
        w("<tr><th></th><td><div class='say'>%s</div><div class='src'>제안: %s</div></td></tr>" % (esc(ci.get("say")), esc(prov["idn"])))
    else:
        w("<tr><th>계열·이름</th><td class='rej'><b>%s</b><div class='say'>%s</div><div class='src'>제안: %s</div></td></tr>"
          % ("이 패널은 읽지 않는다(수작업 판독)" if ci["verdict"] == "REJECTED" else "아직 못 정하겠다",
             esc(ci.get("say")), esc(prov["idn"])))
    w("</table>")
    if prop.get("look"):
        w("<div class='look'><b>먼저 보세요:</b> %s</div>" % esc(prop["look"]))
    for part, title in (("geo", "축·눈금"), ("idn", "계열·이름")):
        w("<div class='part'><h4>%s</h4>" % title)
        for val, lab in (("ACCEPT", "제안대로"), ("FIX", "고칠 곳 있음"), ("HOLD", "보류")):
            w("<label><input type='radio' name='%s-%s' data-part='%s' data-id='%s' value='%s'%s> %s</label>"
              % (part, esc(p), part, esc(p), val, " checked" if val == "ACCEPT" else "", lab))
        w("</div>")
    w("<div class='row2'><label class='verify'><input type='checkbox' data-seen='%s'> <b>두 그림을 직접 봤다</b></label> &nbsp; "
      "메모 <input type='text' data-note='%s' size='40' placeholder='고칠 곳이 있으면 무엇을'> &nbsp; "
      "<button class='both' data-both='%s'>둘 다 제안대로로 되돌리기</button></div>" % (esc(p), esc(p), esc(p)))
    w("<div class='state' data-state='%s'></div></div>" % esc(p))
    return "\n".join(out)


STYLE = """<style>
.fig{margin:30px 0 8px;padding-top:10px;border-top:3px solid #c9c9c2}
.fig h2{font-size:16px;margin:0}
.fig details{margin:6px 0}
.fig details img{max-width:100%;border:1px solid #ddd}
.pics{display:flex;gap:10px;flex-wrap:wrap}
.pic{position:relative;flex:1 1 360px;max-width:560px}
.pic img{width:100%;display:block;border:1px solid #ddd}
.pic .cap{font-size:12px;color:#5a5a56;margin:2px 0}
.ov{position:absolute;pointer-events:none}
.ovf{border:2px dashed #1e64c8}
.ovr{border-top:2px dashed #1e64c8;height:0}
.ovr span,.ovx span{position:absolute;font-size:11px;color:#fff;background:#1e64c8;padding:0 3px;white-space:nowrap}
.ovr span{right:0;top:-15px}
.ovx{border-left:2px solid #1e64c8;width:0}
.ovx span{left:-2px;bottom:-16px}
table.pr{border-collapse:collapse;width:100%;margin:10px 0;font-size:13.5px}
table.pr th{text-align:left;vertical-align:top;width:7.5em;color:#5a5a56;font-weight:normal;padding:4px 6px}
table.pr td{padding:4px 6px;border-top:1px solid #eee;vertical-align:top}
.part{margin:8px 0;padding:8px 10px;border-radius:6px;background:#fafaf8;border:1px solid #e6e6e0}
.part h4{margin:0 0 4px;font-size:14px}
.part label{margin-right:14px;font-size:13.5px;white-space:nowrap}
.say{font-size:13px;color:#3c3c38;margin:4px 0}
.src{font-size:12px;color:#7a7a74}
.look{background:#fff8dc;border-left:3px solid #c9a000;padding:6px 10px;font-size:13px;margin:6px 0}
.rej{color:#8a3b12}
.sw{display:inline-block;width:11px;height:11px;border:1px solid #888;margin-right:4px;vertical-align:-1px}
.cue{color:#5a5a56;font-size:12.5px}
.state{font-size:12.5px;margin-top:6px}
.bad{color:#b3261e}
.okk{color:#2e7d32}
.row2{margin-top:8px}
.both{font-size:12.5px}
.doc{scroll-margin-top:90px}
.doc.done{border-color:#6b8f6b;background:#f6faf6}
.doc.fix{border-color:#c9a000;background:#fffdf3}
.verify{display:inline-block;padding:6px 12px;border:2px solid #6b8f6b;border-radius:6px;background:#f2f8f2;font-size:14.5px;cursor:pointer}
.verify input{transform:scale(1.3);margin-right:6px}
#next{font-weight:bold}
</style>"""

#: 화면. 값을 옮기기만 하고, 무엇이 답이 되는지는 AX(axis_series_page.js)와 그 밑의 GEO·IDN에 있습니다.
PAGE_JS = r"""
(function () {
  var CHECK = AX.makeCheck(GEO, IDN, DATA);
  var KEY = 'fdt_axis_series_' + DATA.date + '_' + DATA.order.length;
  var st = {}, who = '';
  try { var saved = JSON.parse(localStorage.getItem(KEY) || '{}') || {}; st = saved.st || {}; who = saved.who || ''; }
  catch (e) { st = {}; }
  st = CHECK.withDefaults(st);
  var BROKEN = CHECK.broken();
  function save() { try { localStorage.setItem(KEY, JSON.stringify({ st: st, who: who })); } catch (e) {} }
  function q(s) { return document.querySelector(s); }
  function all(s) { return Array.prototype.slice.call(document.querySelectorAll(s)); }
  function sel(id) { return String(id).replace(/["\\]/g, '\\$&'); }
  function render(id) {
    var parts = AX.PARTS.map(function (p) { return CHECK.partState(st, who, id, p, BROKEN); });
    q('[data-state="' + sel(id) + '"]').innerHTML = ['축·눈금', '계열·이름'].map(function (t, k) {
      return '<div class="' + (parts[k].bad ? 'bad' : (parts[k].row ? 'okk' : '')) + '">' + t + ': ' + parts[k].text + '</div>';
    }).join('');
    var card = q('.doc[data-id="' + sel(id) + '"]');
    card.classList.toggle('done', parts[0].done && parts[1].done && !parts[0].fix && !parts[1].fix);
    card.classList.toggle('fix', !!(parts[0].fix || parts[1].fix));
  }
  function counts() {
    var t = CHECK.tally(st, who, BROKEN);
    q('#left').textContent = '— 남은 답 ' + t.left + ' / ' + t.total + ' (제안대로 ' + t.accepted + ', 고칠 곳 ' + t.fix + ')';
  }
  function renderAll() { DATA.order.forEach(render); counts(); }
  q('#who').value = who;
  q('#who').addEventListener('input', function (e) { who = e.target.value; save(); renderAll(); });
  all('input[type=radio][data-part]').forEach(function (r) {
    var id = r.getAttribute('data-id'), p = r.getAttribute('data-part');
    r.checked = st[id][p] === r.value;
    r.addEventListener('change', function () { st[id][p] = r.value; save(); render(id); counts(); });
  });
  all('[data-both]').forEach(function (b) {
    var id = b.getAttribute('data-both');
    b.addEventListener('click', function () {
      AX.PARTS.forEach(function (p) {
        st[id][p] = 'ACCEPT';
        var r = q('input[name="' + p + '-' + sel(id) + '"][value="ACCEPT"]'); if (r) r.checked = true;
      });
      save(); render(id); counts();
    });
  });
  all('[data-seen]').forEach(function (c) {
    var id = c.getAttribute('data-seen');
    c.checked = !!st[id].seen;
    c.addEventListener('change', function () { st[id].seen = c.checked; save(); render(id); counts(); });
  });
  all('[data-note]').forEach(function (t) {
    var id = t.getAttribute('data-note');
    t.value = st[id].note || '';
    t.addEventListener('input', function () { st[id].note = t.value; save(); render(id); counts(); });
  });
  q('#dl').addEventListener('click', function () {
    var out = CHECK.answerCsv(st, who, BROKEN);
    var blob = new Blob(['\ufeff' + out.csv], { type: 'text/csv;charset=utf-8' });
    var link = document.createElement('a');
    link.href = URL.createObjectURL(blob);
    link.download = 'axis_series_answers_' + DATA.date + '.csv';
    document.body.appendChild(link); link.click(); document.body.removeChild(link);
    q('#msg').textContent = '답 ' + out.n + '줄을 내려받았습니다';
  });
  q('#next').addEventListener('click', function () {
    var id = CHECK.nextOpen(st, who, BROKEN);
    if (id) q('.doc[data-id="' + sel(id) + '"]').scrollIntoView({ behavior: 'smooth', block: 'start' });
    else q('#msg').textContent = '모든 카드에 답했습니다';
  });
  save();
  window.__axisSeries = { check: CHECK, broken: BROKEN, state: function () { return st; } };
  renderAll();
})();
"""


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--run", required=True)
    ap.add_argument("--geometry", required=True, help="geometry_proposal.csv와 오버레이가 있는 폴더")
    ap.add_argument("--identity", required=True, help="identity_proposal.csv와 오버레이가 있는 폴더")
    ap.add_argument("--proposals", required=True, help="리더 위에 얹는 제안 JSON (머리말)")
    ap.add_argument("--out", required=True)
    ap.add_argument("--date", default=datetime.date.today().isoformat(), help="페이지와 답 파일 이름의 날짜")
    ap.add_argument("--subset", action="store_true",
                    help="제안 파일에 있는 패널만 (고칠 곳으로 돌아온 패널을 다시 물을 때)")
    a = ap.parse_args(argv)
    html, _info = build(a.run, a.geometry, a.identity, a.proposals, a.date, subset=a.subset)
    with io.open(a.out, "w", encoding="utf-8") as fh:
        fh.write(html)
    print("페이지: %s (%.1f MB)" % (a.out, len(html.encode("utf-8")) / 1e6))
    return 0


if __name__ == "__main__":
    sys.exit(main())
