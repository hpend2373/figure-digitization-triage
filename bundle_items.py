# -*- coding: utf-8 -*-
"""계획서 점검이 남긴 문제에서, 사람이 정할 물음을 모아 결정 묶음의 SPEC을 씁니다.

    python3 bundle_items.py --census CENSUS/ --run RUN --plans PLANS/ --work WORK/ \
        [--proposals proposals.json] --spec WORK/spec.json

CENSUS는 계획서 점검의 출력입니다(`census_copy.py`의 before/ 또는 after/, 또는 같은 모양의
폴더: man_<논문>/ 매니페스트와 out_<논문>/manifest_problems.csv). 문제 코드마다 물음 하나:

    X  SOURCE_PANEL_UNRESOLVED, SOURCE_PANEL_RUN_LINK_MISSING   그림 하나의 처분 (record_dispositions)
    C  MISSING_TARGET_OUTCOME_LABEL (그려진 패널)              결과 이름, 또는 목표 아님 (R4 - 아직 길 없음)
    F  MISSING_SERIES_DISCRIMINANT (BAR_MONO)                  막대 칠 (record_identity)
    M  MISSING_SERIES_DISCRIMINANT (선·기호)                   기호 모양 (record_identity)
    L  IDENTITY_DOMAIN_FILL_CONFLICT                           한 그림 두 범례 (record_identity, 또는 길)
    K  CALIBRATION_OUTSIDE_PANEL                               눈금 짝 또는 상자 (record_geometry·identity)

잴 수 있는 것은 잽니다(래스터에서): K는 짝 둘레 12 px 안의 눈금 표시(가시 왼쪽·오른쪽 짧은
선, 가로선, 옅은 격자선), F는 x 위치마다 막대 속의 어두운 비율과 판독기의 띠
(`mark_readers._FILL_BANDS`). 잰 것으로 정해지는 물음은 기계 제안이 붙습니다 - K는 짝을 표시
위로(PAIRS) 또는 상자를(BOX), F는 모든 막대가 한 띠면 그 칠, 띠가 섞이면 MANUAL. 그 밖은
그림을 보아야 하는 물음이라, 제안은 PROPOSALS(Claude나 사람이 그림을 보고 쓴 것)에서 옵니다:

    {"proposals": {"<열쇠>": {"proposal": "...", "why": "...", "observed_by": "...",
                             "which": "e,f,g", "text": {"value": "...", "unit": "..."},
                             "extra_options": [[값, 말, 효과], ...]}},
     "extra_items": [{"section": "B", ...bundle_page 항목...}],
     "sections": {"B": "제목"}, "section_order": ["A", "B", "X", ...], "notes": ["..."]}

열쇠는 `X:<Draft_ID>`, `C:<패널>`, `F:<패널>:<계열>`, `M:<패널>:<계열>`, `L:<그림>`, `K:<패널>`
입니다. PROPOSALS가 기계 제안을 덮습니다.

**제안이 없는 물음이 하나라도 있으면 SPEC을 쓰지 않습니다**(WORK/todo.json에 그 물음들과 잰 것,
그림을 적고 종료 코드 2). 결정 묶음은 모든 줄에 제안이 있어야 합니다(`bundle_page`). todo.json이
그림을 보고 제안을 쓸 사람(또는 에이전트)의 작업 목록입니다. 지금 점검에 없는 물음의 제안은
거절합니다(STALE_PROPOSAL) - 다른 점검을 보고 쓴 제안입니다.

이미 처분된 그림의 남은 일(PARTIAL의 그 패널 그리기, RECROP, REDRAW)과 그리지 않은 패널의
결과 이름은 물음이 아니라 사람의 일이라 SPEC의 notes에 적습니다.
"""
import argparse
import collections
import csv
import glob
import io
import json
import math
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import bundle_page as BP                                         # noqa: E402

NEAR, ON, BOX_TOL = 12, 1.5, 5
#: 판독기의 칠 띠(`mark_readers._FILL_BANDS`)와 같아야 합니다 - 시나리오가 둘을 대 봅니다.
FILL_BANDS = {"SOLID": (0.72, 1.01), "HATCHED": (0.12, 0.60), "OPEN": (-0.01, 0.06)}
MACHINE = "bundle_items.py (래스터에서 잰 것)"
SECTION_TITLES = collections.OrderedDict([
    ("X", "그림 처분"), ("C", "결과 이름"), ("F", "흑백 막대의 칠"), ("M", "선의 기호"),
    ("L", "한 그림, 두 범례"), ("K", "눈금 짝이 상자 밖")])
PERSON_WORK = ("PARTIAL", "RECROP", "REDRAW")
MARKERS = [("CIRCLE/FILLED", "● 속 찬 동그라미"), ("CIRCLE/OPEN", "○ 빈 동그라미"), ("CIRCLE/ANY", "동그라미, 속은 상관없음"),
           ("SQUARE/FILLED", "■ 속 찬 네모"), ("SQUARE/OPEN", "□ 빈 네모"), ("TRIANGLE/FILLED", "▲ 속 찬 세모"),
           ("TRIANGLE/OPEN", "△ 빈 세모"), ("DIAMOND/FILLED", "◆ 속 찬 마름모")]


def rd(path):
    return list(csv.DictReader(io.open(path, encoding="utf-8-sig"))) if os.path.exists(path) else []


def key_of(panel_id):
    base, i = panel_id.rsplit("_P", 1)
    return "%s__p%d" % (base, int(i))


def series_key(name):
    return re.sub(r"[^0-9a-z]+", " ", str(name).lower()).strip()


def census_rows(cdir):
    """[{pub, check, where, detail, row}] - 문제와, 그 문제가 가리키는 매니페스트 행."""
    out = []
    files = {"series": "series_manifest.csv", "panels": "panel_manifest.csv", "source_panels": "source_panel_inventory.csv"}
    for mp in sorted(glob.glob(os.path.join(cdir, "out_*", "manifest_problems.csv"))):
        pub = os.path.basename(os.path.dirname(mp))[4:]
        tabs = {}
        for r in rd(mp):
            kind, _, ref = r["where"].partition(":")
            row = None
            if kind in files and ref.isdigit():
                if kind not in tabs:
                    tabs[kind] = rd(os.path.join(cdir, "man_" + pub, files[kind]))
                row = tabs[kind][int(ref) - 2]
            out.append(dict(pub=pub, check=r["check"], where=r["where"], detail=r.get("detail", ""), row=row))
    return out


# ------------------------------------------------------------------------------------------------ measure ----
def _gray(path):
    import numpy as np
    from PIL import Image
    Image.MAX_IMAGE_PIXELS = None
    return np.asarray(Image.open(path).convert("L")).astype(int)


def runs(rows):
    out = []
    for r in rows:
        if out and r - out[-1][-1] <= 1:
            out[-1].append(r)
        else:
            out.append([r])
    return out


def find_spine(gray, x0, y0, y1, hint=None):
    """y축 가시: 상자 왼쪽 끝(또는 기록의 Y_Axis_Spine_X) 40 px 안에서 가장 어두운 긴 세로줄."""
    import numpy as np
    c0 = int(hint) if hint else x0
    xa, xb = max(0, c0 - 40), min(gray.shape[1], c0 + 40)
    return xa + int(np.argmax((gray[y0:y1, xa:xb] < 128).sum(0)))


def tick_marks(gray, sp, x0, ylo, yhi):
    """짝 둘레의 눈금 표시: 가시 왼쪽·오른쪽 짧은 선, 가로선, 옅은 격자선. 창의 90 % 이상을 덮는 줄의 묶음
    (14줄 이하). [(종류, 첫 줄, 끝 줄, 가운데)]"""
    ylo, yhi = max(0, ylo), min(gray.shape[0], yhi)
    out = []
    for kind, xa, xb, thr in (("왼쪽 눈금", sp - 14, sp - 3, 128), ("오른쪽 눈금", sp + 4, sp + 14, 128),
                              ("가로선", x0 + 40, x0 + 400, 128), ("옅은 격자선", x0 + 40, x0 + 400, 235)):
        win = gray[ylo:yhi, max(0, xa):max(0, min(gray.shape[1], xb))]
        if win.size == 0:
            continue
        cov = (win < thr).mean(1)
        for g in runs([ylo + i for i, c in enumerate(cov) if c >= 0.9]):
            if len(g) <= 14:
                out.append((kind, g[0], g[-1], (g[0] + g[-1]) / 2.0))
    return out


def measure_calibration(gray, card):
    """짝마다 가장 가까운 표시, 옮긴 짝, 상자. 지금 짝이 표시 위(1.5 px 안)면 그대로."""
    x0, x1, y0, y1 = [int(float(card[c])) for c in ("Panel_X0", "Panel_X1", "Panel_Y0", "Panel_Y1")]
    sp = find_spine(gray, x0, y0, y1, (card.get("Y_Axis_Spine_X") or "").strip() or None)
    pairs = [(float(v), float(p)) for v, p in (x.split("@") for x in card["Confirmed_Tick_Values"].split(";"))]
    new, inside = [], True
    for v, p in pairs:
        marks = [m for m in tick_marks(gray, sp, x0, int(p) - NEAR - 2, int(p) + NEAR + 3) if abs(m[3] - p) <= NEAR]
        best = min(marks, key=lambda m: (abs(m[3] - p), m[0] == "옅은 격자선")) if marks else None
        q, how = p, "가까운 표시 없음"
        if best is not None:
            if abs(best[3] - p) <= ON:
                how = "이미 %s 위" % best[0]
            else:
                q, how = best[3], "%s %d–%d행 가운데" % (best[0], best[1], best[2])
        if not (y0 - BOX_TOL <= q <= y1 + BOX_TOL):
            inside = False
        new.append(dict(value=v, now=p, proposed=q, how=how))
    olds = [p for _v, p in pairs]
    return dict(spine=sp, frame=[x0, x1, y0, y1], pairs=new, all_inside=inside,
                proposed_ticks=";".join("%g@%g" % (n["value"], n["proposed"]) for n in new),
                box=[x0, x1, min(y0, int(math.floor(min(olds))) - 1), max(y1, int(math.ceil(max(olds))) + 1)])


def band(d):
    if d is None:
        return ""
    for k, (lo, hi) in FILL_BANDS.items():
        if lo <= d < hi:
            return k
    return "AMBIGUOUS"


def bar_interior(gray, xc, y0, y1):
    """x에서 막대 속: 13 px 기둥에서 종이가 아니고(중앙값 < 245) 고른(표준편차 < 12) 줄의 가장 긴 묶음(20줄 이상).
    빗금·빈 막대는 그런 묶음이 없어 None. (회색, 128 아래 비율)"""
    import numpy as np
    col = gray[y0:y1, max(0, xc - 6):xc + 7]
    if col.size == 0:
        return None, None
    med, sd = np.median(col, 1), col.std(1)
    ok = [i for i in range(len(med)) if med[i] < 245 and sd[i] < 12]
    best = max(runs(ok), key=len) if ok else []
    if len(best) < 20:
        return None, None
    sub = col[best[0]:best[-1] + 1]
    return int(np.median(sub)), round(float((sub < 128).mean()), 3)


# ------------------------------------------------------------------------------------------------ pictures ----
def box_picture(raster, boxes, labels, out_png, pad=60):
    from PIL import Image, ImageDraw
    Image.MAX_IMAGE_PIXELS = None
    im = Image.open(raster).convert("RGB")
    x0 = max(0, min(b[0] for b in boxes) - pad); x1 = min(im.width, max(b[1] for b in boxes) + pad)
    y0 = max(0, min(b[2] for b in boxes) - pad); y1 = min(im.height, max(b[3] for b in boxes) + pad)
    im = im.crop((x0, y0, x1, y1)); d = ImageDraw.Draw(im)
    w = max(3, im.width // 300)
    for b, lab in zip(boxes, labels):
        d.rectangle((b[0] - x0, b[2] - y0, b[1] - x0, b[3] - y0), outline=(214, 40, 40), width=w)
        d.text((b[0] - x0 + 6, b[2] - y0 + 4), lab, fill=(214, 40, 40))
    im.save(out_png)
    return out_png


def tick_picture(raster, m, out_png):
    """짝마다 3배 확대: 빨강 지금 짝, 초록 옮긴 짝, 파랑 상자 위·아래 끝."""
    from PIL import Image, ImageDraw
    Image.MAX_IMAGE_PIXELS = None
    im = Image.open(raster).convert("RGB")
    x0, x1, y0, y1 = m["frame"]; sp = m["spine"]
    tiles = []
    for p in m["pairs"]:
        lo, hi = int(min(p["now"], p["proposed"])) - 40, int(max(p["now"], p["proposed"])) + 41
        bx = (max(0, sp - 170), max(0, lo), min(im.width, sp + 110), min(im.height, hi))
        t = im.crop(bx).resize(((bx[2] - bx[0]) * 3, (bx[3] - bx[1]) * 3), Image.NEAREST)
        d = ImageDraw.Draw(t); W = t.width
        Y = lambda y: (y - bx[1]) * 3 + 1
        for yy in (y0, y1):
            if bx[1] <= yy <= bx[3]:
                d.line([(0, Y(yy)), (W * 0.3, Y(yy))], fill=(40, 90, 220), width=3)
        d.line([(W * 0.62, Y(p["now"])), (W, Y(p["now"]))], fill=(214, 40, 40), width=3)
        if p["proposed"] != p["now"]:
            d.line([(W * 0.62, Y(p["proposed"])), (W, Y(p["proposed"]))], fill=(30, 150, 60), width=3)
        tiles.append(t)
    S = Image.new("RGB", (sum(t.width for t in tiles) + 12 * (len(tiles) - 1), max(t.height for t in tiles)), "white")
    x = 0
    for t in tiles:
        S.paste(t, (x, 0)); x += t.width + 12
    S.save(out_png)
    return out_png


# ------------------------------------------------------------------------------------------------ questions ----
def frame(card):
    return [int(float(card[c])) for c in ("Panel_X0", "Panel_X1", "Panel_Y0", "Panel_Y1")]


def disp(draft, value, which=""):
    return {"gate": "dispositions", "row": {"Draft_ID": draft, "Disposition": value, "Which_Panels": which}}


def questions(cdir, run, plans, work, file_root=None, identity_dir=None, geometry_dir=None, log=print):
    """({열쇠: 물음}, 사람의 일 [글]). 물음 = {section, question, now, facts, options, images, table,
    machine: {proposal, why} 또는 None, text_needed, group}."""
    file_root = file_root or run
    I = dict((r["Proposal_ID"], r) for r in rd(os.path.join(run, identity_dir or os.path.join("seg", "identity600"), "identity_decisions.csv")))
    G = dict((r["Proposal_ID"], r) for r in rd(os.path.join(run, geometry_dir or os.path.join("seg", "geometry600"), "geometry_decisions.csv")))
    drafts = dict((r["Draft_ID"], r) for r in rd(os.path.join(run, "figure_intake_draft.csv")))
    PF = dict((r["Draft_ID"], r) for r in rd(os.path.join(plans, "plan_figures.csv")))
    FS = dict((r["Draft_ID"], r) for r in rd(os.path.join(run, "figure_dispositions.csv")))
    os.makedirs(work, exist_ok=True)
    pics = os.path.join(work, "pictures")
    os.makedirs(pics, exist_ok=True)
    Q, tasks = collections.OrderedDict(), []
    rows = census_rows(cdir)
    cache = {}

    def gray(raster):
        if raster not in cache:
            cache.clear(); cache[raster] = _gray(os.path.join(file_root, raster))
        return cache[raster]

    # X - figures
    figs = collections.OrderedDict()
    undrawn = 0
    for r in rows:
        if r["check"] == "SOURCE_PANEL_UNRESOLVED" and r["row"]:
            figs.setdefault(r["row"]["Source_Figure_ID"], []).append(r["check"])
        elif r["check"] == "SOURCE_PANEL_RUN_LINK_MISSING":
            figs.setdefault(r["where"].split(":", 1)[1].rsplit("_P", 1)[0], []).append(r["check"])
    for d, checks in figs.items():
        if d in FS and FS[d].get("Disposition") in PERSON_WORK:
            tasks.append("%s %s: %s로 처분됨 — 남은 일은 사람의 일(%s)" % (d, PF.get(d, {}).get("Figure_Number", ""), FS[d]["Disposition"],
                                                                 PF.get(d, {}).get("Needs", "")))
            continue
        f = drafts.get(d, {})
        crop = os.path.join(file_root, f.get("Figure_Crop") or "")
        Q["X:" + d] = dict(section="X", question="%s %s %s쪽" % (f.get("Source_Document_ID", ""), f.get("Figure_Number", ""), f.get("Page", "")),
                           now="%s · 캡션 경로 %s · %s" % (PF.get(d, {}).get("Disposition", "?"), PF.get(d, {}).get("Route", "?"),
                                                           ", ".join("%s %d" % kv for kv in collections.Counter(checks).items())),
                           target=d, images=[{"path": crop, "caption": "크롭"}] if os.path.isfile(crop) else [],
                           options=[["DIGITIZE", "읽을 그림 (DIGITIZE)", disp(d, "DIGITIZE")],
                                    ["NON_TARGET", "목표 결과 아님 (NON_TARGET)", disp(d, "NON_TARGET")],
                                    ["NOT_DATA", "데이터 아님 (NOT_DATA)", disp(d, "NOT_DATA")]],
                           partial=d, machine=None)
    # C - outcome labels of drawn panels
    for r in rows:
        if r["check"] != "MISSING_TARGET_OUTCOME_LABEL" or not r["row"]:
            continue
        k = key_of(r["row"]["Source_Panel_ID"])
        g = G.get(k)
        if not g or not (g.get("Verified_By") or "").strip():
            undrawn += 1
            continue
        png = box_picture(os.path.join(file_root, g["Raster"]), [frame(g)], ["p%s" % k.rsplit("__p", 1)[1]],
                          os.path.join(pics, "C_%s.png" % k))
        Q["C:" + k] = dict(section="C", question="%s 결과 이름" % k, target=k, group="C:" + k.rsplit("__p", 1)[0],
                           now="결과 이름 없음 · %s" % r["row"].get("Panel_Disposition", ""), images=[{"path": png, "caption": "600 dpi"}],
                           options=[["LABEL", "제안한 이름으로 적음", {"gate": None, "needs": "R4: 패널 결과 이름 기록", "uses_text": True}],
                                    ["EDIT", "이름을 고쳐 적음", {"gate": None, "needs": "R4: 패널 결과 이름 기록", "uses_text": True}],
                                    ["NON_TARGET", "목표 결과 아님 — 이 패널 닫음", {"gate": None, "needs": "R4: 패널 목표 여부 기록"}]],
                           text_needed=True, machine=None)
    if undrawn:
        tasks.append("결과 이름이 없는 그리지 않은 패널 %d개 — 패널을 그리고 정체를 확인하면 이름이 생깁니다." % undrawn)
    # F, M - series without a discriminant
    for r in rows:
        if r["check"] != "MISSING_SERIES_DISCRIMINANT" or not r["row"]:
            continue
        k, sid = key_of(r["row"]["Panel_ID"]), r["row"]["Series_ID"]
        card = I.get(k)
        if not card:
            continue
        ser = json.loads(card.get("Series") or "[]")
        hit = [s for s in ser if series_key(s.get("name")) == series_key(sid)]
        name = hit[0]["name"] if len(hit) == 1 else sid
        manual = ["MANUAL", "사람이 읽음 (MANUAL)", {"gate": "identity", "proposal_id": k, "set": {"Read_Route": "MANUAL"}}]
        png = box_picture(os.path.join(file_root, card["Raster"]), [frame(card)], ["p%s" % k.rsplit("__p", 1)[1]],
                          os.path.join(pics, "S_%s_%s.png" % (k, series_key(sid).replace(" ", "_"))))
        if "fill pattern" in r["detail"] or card.get("Mark_Type") == "BAR_MONO":
            gr = gray(card["Raster"]); x0, x1, y0, y1 = frame(card)
            bars = []
            for lab in json.loads(card.get("X_Labels") or "[]"):
                grey, dark = bar_interior(gr, int(round(float(lab["px"]))), y0, y1)
                bars.append((lab["label"], grey, dark, band(dark)))
            bands = set(b[3] for b in bars)
            machine = None
            if bars and "" not in bands and "AMBIGUOUS" not in bands:
                machine = ({"proposal": bands.pop(), "why": "x 위치마다 잰 막대 속이 모두 한 띠"} if len(bands) == 1 else
                           {"proposal": "MANUAL", "why": "막대 속이 x 위치마다 다른 띠(%s) — 한 계열에 칠 하나를 적을 수 없음" % ", ".join(sorted(bands))})
            Q["F:%s:%s" % (k, sid)] = dict(
                section="F", question="%s 계열 %s의 칠" % (k, name), target=k, group="F:" + k.rsplit("__p", 1)[0],
                now="%s · Bar_Fill_Pattern 비어 있음" % card.get("Mark_Type", ""), images=[{"path": png, "caption": "600 dpi"}],
                table=[["x 위치"] + [b[0] for b in bars], ["속 회색"] + [("—" if b[1] is None else b[1]) for b in bars],
                       ["어두운 비율"] + [("—" if b[2] is None else b[2]) for b in bars], ["판독기 띠"] + [b[3] or "속 칠 없음" for b in bars]],
                options=[[v, v, {"gate": "identity", "proposal_id": k, "series": [{"name": name, "set": {"bar_fill": v}}]}]
                         for v in ("SOLID", "HATCHED", "OPEN")] + [manual], machine=machine)
        else:
            opts = [[v, lab, {"gate": "identity", "proposal_id": k,
                              "series": [{"name": name, "set": {"marker": v.split("/")[0], "marker_fill": v.split("/")[1]}}]}]
                    for v, lab in MARKERS]
            if len(ser) == 1:
                opts.append(["ANY/ANY", "모양 상관없음 (계열 하나)", {"gate": "identity", "proposal_id": k,
                                                                 "series": [{"name": name, "set": {"marker": "ANY", "marker_fill": "ANY"}}]}])
            Q["M:%s:%s" % (k, sid)] = dict(section="M", question="%s 계열 %s의 기호" % (k, name), target=k, group="M:" + k.rsplit("__p", 1)[0],
                                           now="%s · Marker_Shape 비어 있음" % card.get("Mark_Type", ""),
                                           images=[{"path": png, "caption": "600 dpi"}], options=opts + [manual], machine=None)
    # L - one figure, two legends
    doms = collections.OrderedDict()
    for r in rows:
        if r["check"] == "IDENTITY_DOMAIN_FILL_CONFLICT":
            doms.setdefault(r["where"].split(":", 1)[1].rsplit("_P", 1)[0], []).append(r["detail"])
    for d, details in doms.items():
        pks = sorted((k for k in I if k.startswith(d + "__p")), key=lambda k: int(k.rsplit("__p", 1)[1]))
        if not pks:
            continue
        png = box_picture(os.path.join(file_root, I[pks[0]]["Raster"]), [frame(I[k]) for k in pks],
                          ["p%s" % k.rsplit("__p", 1)[1] for k in pks], os.path.join(pics, "L_%s.png" % d))
        Q["L:" + d] = dict(section="L", question="%s 범례" % d, target=d, now="한 범례 영역 안에서 같은 칠이 다른 뜻 — 문제 %d건" % len(details),
                           images=[{"path": png, "caption": "600 dpi, 상자 = 패널"}],
                           table=[["패널", "계열 요인", "계열 = 칠"]] + [["p%s" % k.rsplit("__p", 1)[1], I[k].get("Series_Factor", ""),
                                                                    ", ".join("%s=%s" % (s.get("name"), s.get("bar_fill", ""))
                                                                              for s in json.loads(I[k].get("Series") or "[]"))] for k in pks],
                           options=[["MANUAL", "이 그림의 패널 모두 사람이 읽음 (MANUAL)",
                                     [{"gate": "identity", "proposal_id": k, "set": {"Read_Route": "MANUAL"}} for k in pks]]], machine=None)
    # K - calibration outside the box
    for r in rows:
        if r["check"] != "CALIBRATION_OUTSIDE_PANEL" or not r["row"]:
            continue
        k = key_of(r["row"]["Panel_ID"])
        g = G.get(k)
        if not g or not (g.get("Confirmed_Tick_Values") or "").strip():
            continue
        m = measure_calibration(gray(g["Raster"]), g)
        png = tick_picture(os.path.join(file_root, g["Raster"]), m, os.path.join(pics, "K_%s.png" % k))
        pairs_set = {"Confirmed_Tick_Values": m["proposed_ticks"]}
        x0, x1, ny0, ny1 = m["box"]
        box_effect = [{"gate": "geometry", "proposal_id": k, "set": {"Panel_Y0": str(ny0), "Panel_Y1": str(ny1)}}]
        if k in I:
            box_effect.append({"gate": "identity", "proposal_id": k, "set": {"Panel_Y0": str(ny0), "Panel_Y1": str(ny1)}})
        moved = m["proposed_ticks"] != g["Confirmed_Tick_Values"]
        machine = ({"proposal": "PAIRS", "why": "짝을 바로 옆 눈금 표시로: " + "; ".join("%g: %s" % (p["value"], p["how"]) for p in m["pairs"])}
                   if moved and m["all_inside"] else
                   {"proposal": "BOX", "why": "가까운 눈금 표시로 옮겨도 짝이 상자 밖 — 상자를 짝까지 넓힘 (정체 카드의 상자도 같이)"})
        Q["K:" + k] = dict(section="K", question="%s 눈금 짝" % k, target=k, now="%s · 상자 y %d–%d" % (g["Confirmed_Tick_Values"], m["frame"][2], m["frame"][3]),
                           facts=r["detail"], images=[{"path": png, "caption": "3배 확대. 빨강 지금 짝, 초록 옮긴 짝, 파랑 상자 끝"}],
                           options=([["PAIRS", "짝을 눈금 표시 위로: %s (상자 그대로)" % m["proposed_ticks"],
                                      {"gate": "geometry", "proposal_id": k, "set": pairs_set}]] if moved else [])
                           + [["BOX", "상자를 넓힘: y %d–%d → %d–%d (정체 카드도)" % (m["frame"][2], m["frame"][3], ny0, ny1), box_effect]],
                           machine=machine)
    log("물음 %d (%s) · 사람의 일 %d" % (len(Q), ", ".join("%s %d" % kv for kv in collections.Counter(q["section"] for q in Q.values()).items()), len(tasks)))
    return Q, tasks


def merge(Q, tasks, P):
    """(spec 또는 None, todo, 문제). 모든 물음에 제안이 있어야 spec이 나옵니다."""
    props = (P or {}).get("proposals") or {}
    problems = [("STALE_PROPOSAL", "%s는 이 점검에 없는 물음의 제안입니다." % k) for k in props if k not in Q]
    sections = collections.OrderedDict()
    todo = []
    for k, q in Q.items():
        p = props.get(k) or {}
        if not p.get("proposal") and q.get("machine"):
            p = dict(q["machine"], observed_by=MACHINE, **{kk: vv for kk, vv in p.items() if kk not in ("proposal", "why", "observed_by")})
        opts = [list(o) for o in q["options"]] + [list(o) for o in p.get("extra_options") or []]
        if p.get("proposal") == "PARTIAL" and q.get("partial"):
            if not (p.get("which") or "").strip():
                problems.append(("PARTIAL_WITHOUT_PANELS", "%s: PARTIAL 제안에 어느 패널인지(which)가 없습니다." % k))
            opts.insert(1, ["PARTIAL", "일부 패널만 읽음: %s (PARTIAL)" % p.get("which", ""), disp(q["partial"], "PARTIAL", p.get("which", ""))])
        opts.append(["HOLD", "보류"])
        item = dict(id="", target=q["target"], question=q["question"], now=q["now"], options=opts,
                    proposal=p.get("proposal", ""), why=p.get("why", ""), observed_by=p.get("observed_by", ""),
                    images=q.get("images") or [], key=k)
        for f in ("facts", "table", "group"):
            if q.get(f):
                item[f] = q[f]
        if q.get("text_needed"):
            item["text"] = p.get("text") or {"value": "", "unit": ""}
            if p.get("proposal") in ("LABEL", "EDIT") and not (item["text"].get("value") or "").strip():
                problems.append(("LABEL_WITHOUT_TEXT", "%s: 이름을 제안하면서 이름이 없습니다." % k))
        if not item["proposal"]:
            todo.append(dict(key=k, section=q["section"], question=q["question"], now=q["now"], options=[o[:2] for o in opts],
                             images=[i["path"] for i in item["images"]], table=q.get("table"), facts=q.get("facts", "")))
        sections.setdefault(q["section"], []).append(item)
    for e in (P or {}).get("extra_items") or []:
        sections.setdefault(e.get("section") or "Z", []).append(dict((kk, vv) for kk, vv in e.items() if kk != "section"))
    if todo or problems:
        return None, todo, problems
    order = list((P or {}).get("section_order") or []) + [s for s in SECTION_TITLES if s not in ((P or {}).get("section_order") or [])]
    order += [s for s in sections if s not in order]
    titles = dict(SECTION_TITLES, **((P or {}).get("sections") or {}))
    spec = {"schema": BP.SCHEMA, "title": (P or {}).get("title") or "남은 결정 묶음",
            "answers_file": (P or {}).get("answers_file") or "bundle_answers.csv",
            "notes": list((P or {}).get("notes") or []) + tasks, "sections": []}
    for s in order:
        if s not in sections:
            continue
        items = sections[s]
        width = 3 if len(items) > 99 else 2
        for n, it in enumerate(items, 1):
            if not it.get("id"):
                it["id"] = "%s%0*d" % (s, width, n)
        spec["sections"].append({"id": s, "title": titles.get(s, s), "items": items})
    return spec, [], problems


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--census", required=True)
    ap.add_argument("--run", required=True)
    ap.add_argument("--plans", required=True)
    ap.add_argument("--work", required=True, help="그림과 todo.json을 둘 곳 (로컬)")
    ap.add_argument("--spec", required=True)
    ap.add_argument("--proposals")
    ap.add_argument("--file-root")
    ap.add_argument("--identity-dir")
    ap.add_argument("--geometry-dir")
    a = ap.parse_args(argv)
    P = json.load(io.open(a.proposals, encoding="utf-8")) if a.proposals else {}
    Q, tasks = questions(a.census, a.run, a.plans, a.work, a.file_root, a.identity_dir, a.geometry_dir)
    spec, todo, problems = merge(Q, tasks, P)
    if spec is not None:
        problems += BP.check_spec(spec, os.path.dirname(os.path.abspath(a.spec)))
    if problems:
        for c, m in problems:
            print("거절 %s: %s" % (c, m))
        return 1
    if todo:
        path = os.path.join(a.work, "todo.json")
        json.dump(todo, io.open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print("제안이 없는 물음 %d개 - SPEC을 쓰지 않았습니다. 작업 목록: %s" % (len(todo), path))
        return 2
    json.dump(spec, io.open(a.spec, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("SPEC: %s (항목 %d)" % (a.spec, sum(len(s["items"]) for s in spec["sections"])))
    return 0


if __name__ == "__main__":
    sys.exit(main())
