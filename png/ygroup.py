# -*- coding: utf-8 -*-
"""The y scale groups a run proposed, drawn on the figure they were proposed on."""
import csv, os, sys
from PIL import Image, ImageDraw, ImageFont
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import capt

# AMBER, NOT GREEN. Green read as "this shared scale has been verified", and
# nothing here has been checked against a masked-label corpus. Green is reserved
# for a transfer that has passed one.
PROV = (176, 108, 12)
DEP = (150, 130, 90)
NONE = (168, 52, 43)
AMB = (120, 90, 160)
PROPOSED = (176, 108, 12)
MONO = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf"
F = ImageFont.truetype(MONO, 16)


def B(s):
    return [int(v) for v in s.split(",")]


def load(trace, pid, fig):
    rows = list(csv.DictReader(open(trace)))
    sp = [r for r in rows if r["kind"] == "SELECTED_PASS"
          and r["pid"] == pid and r["fig"] == fig][0]
    mode, ink, png = sp["mode"], sp["ink"], sp["png"]

    def keep(kind):
        return [r for r in rows if r["kind"] == kind and r["pid"] == pid
                and r["fig"] == fig and r["mode"] == mode and r["ink"] == ink]
    return png, keep("Y_SCALE_GROUP"), keep("Y_SCALE_MEMBER"), keep("SELECTED")


def chip(d, xy, text, col, limit, pad=4, font=F):
    x, y = xy
    w = int(font.getlength(text))
    if x + w + 2 * pad > limit:
        x = max(2, limit - w - 2 * pad - 2)
    d.rectangle([x, y, x + w + 2 * pad, y + font.size + 2 * pad - 2], fill=(255, 255, 255))
    d.rectangle([x, y, x + w + 2 * pad, y + font.size + 2 * pad - 2], outline=col, width=2)
    d.text((x + pad, y + pad - 2), text, fill=col, font=font)


def render(trace, pid, fig, out):
    png, groups, members, sel = load(trace, pid, fig)
    boxes = {r["panel"]: B(r["box"]) for r in sel}
    im = Image.open(os.path.join(ROOT, "clips", png)).convert("RGB")
    d = ImageDraw.Draw(im)
    for g in groups:
        col = {"ROW_BAND_ONE_PROVIDER": PROV,
               "ROW_BAND_NO_PROVIDER": NONE,
               "ROW_BAND_NO_ELIGIBLE_PROVIDER": NONE}.get(g["status"], AMB)
        mem = [m for m in members if m["group_id"] == g["group_id"]]
        xs = [boxes[m["panel"]] for m in mem if m["panel"] in boxes]
        if not xs:
            continue
        bx = [min(b[0] for b in xs), max(b[1] for b in xs),
              min(b[2] for b in xs), max(b[3] for b in xs)]
        d.rectangle([bx[0] - 8, bx[2] - 8, bx[1] + 7, bx[3] + 7], outline=col, width=4)
        chip(d, (bx[0] - 6, bx[2] - 34),
             "%s  %s  transfer %s%s"
             % (g["group_id"], g["status"].replace("ROW_BAND_", ""),
                g["transfer"],
                "  CHAINED" if g["linkage"] == "CHAINED" else ""),
             col, im.width)
        for m in mem:
            if m["panel"] not in boxes:
                continue
            b = boxes[m["panel"]]
            prov = m["is_provider"] == "True"
            one = g["status"] == "ROW_BAND_ONE_PROVIDER"
            c2 = PROV if prov else (DEP if one else NONE)
            note = ("PROVIDER" if prov else
                    ("candidate <- %s  UNVALIDATED" % g["provider_panel"] if one
                     else "no eligible provider"))
            d.rectangle([b[0], b[2], b[1] - 1, b[3] - 1], outline=c2, width=2)
            chip(d, (b[0] + 4, b[3] - 28), "%s %s" % (m["panel"], note), c2,
                 im.width)
    lines = ["%-4s %-7s %-10s %-11s %-6s %-6s %-5s %-5s %s"
             % ("", "group", "role", "eligibility", "d_base", "sym", "p_un",
                "line", "ticks (lengths)")]
    for g in groups:
        for m in [x for x in members if x["group_id"] == g["group_id"]]:
            tk = ";".join("%s(%s)" % (a, b) for a, b in
                          zip((m["ticks"] or "").split(";"),
                              (m.get("tick_lengths") or "").split(";"))
                          if a)
            lines.append("%-4s %-7s %-10s %-11s %-6s %-6s %-5s %-5s %s"
                         % (m["panel"], g["group_id"],
                            "provider" if m["is_provider"] == "True" else
                            ("candidate" if g["status"] == "ROW_BAND_ONE_PROVIDER"
                             else "unresolved"),
                            m.get("eligibility") or "-",
                            m.get("d_baseline") or "-",
                            m.get("symmetric_max") or "-",
                            m.get("provider_unmatched") or "-",
                            (m.get("line_residual_px") or "-")[:5],
                            (tk or "-")[:40]))
    lines.append("")
    for g in groups:
        if g["status"] != "ROW_BAND_ONE_PROVIDER":
            lines.append("%-3s %-30s  %s" % (
                g["group_id"], g["status"].replace("ROW_BAND_", ""),
                "; ".join(m["ineligible_why"] for m in members
                          if m["group_id"] == g["group_id"]
                          and m["own_ladder"] == "True") or "no member read a ladder"))
    prov = sum(1 for m in members if m["is_provider"] == "True")
    cand = {g["group_id"] for g in groups
            if g["status"] == "ROW_BAND_ONE_PROVIDER"}
    serve = [m for m in members if m["group_id"] in cand
             and m["is_provider"] != "True" and m["own_ladder"] != "True"]
    unres = [m for m in members if m["group_id"] in
             {g["group_id"] for g in groups
              if g["status"] in ("ROW_BAND_NO_PROVIDER",
                                 "ROW_BAND_NO_ELIGIBLE_PROVIDER")}]
    # WHAT IS TRUE NOW, AND WHAT IS ONLY PROPOSED, on separate lines. The first
    # version added providers to candidates and called the sum "currently
    # calibratable panels", which claimed twelve calibrated panels on a figure
    # where four are calibrated and nothing has been transferred.
    lines += ["",
              "actually calibrated panels (local ladder)   %d" % prov,
              "shadow transfer candidates (UNVALIDATED)    %d" % len(serve),
              "conditionally calibratable after review     %d" % (prov + len(serve)),
              "unresolved panels                           %d" % len(unres),
              "bands with no eligible provider             %d"
              % sum(1 for g in groups
                    if g["status"] in ("ROW_BAND_NO_PROVIDER",
                                       "ROW_BAND_NO_ELIGIBLE_PROVIDER")),
              "ladder_pass_count                           %d"
              % sum(1 for r in sel if r["calibration"] == "LOCAL_LADDER"),
              "",
              "어떤 transfer 도 검증되지 않았다. amber 는 제안이고 승인이 아니다."]
    im = capt.below(im, "%s %s: y 스케일의 소유자는 패널이 아니라 행 그룹" % (pid, fig),
                    lines,
                    keys=[(PROV, "provider (local ladder)", False),
                          (DEP, "transfer candidate, UNVALIDATED", False),
                          (NONE, "no eligible provider", False),
                          (AMB, "two or more providers", False)])
    im.save(out)
    return out


if __name__ == "__main__":
    print(render("trY.csv", "177", "Fig. 2", "png/F1_yscale_177fig2.png"))
    print(render("trY.csv", "475", "Fig. 1", "png/F2_yscale_475fig1.png"))
