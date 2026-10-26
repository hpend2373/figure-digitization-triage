# -*- coding: utf-8 -*-
"""쪽을 옮긴 그림 행이 옮기기 전 쪽의 지문을 들고 있으면, 지금 쪽의 지문으로 고칩니다.

    python3 fdt/rehash_moved_pages.py --run RUN            # 무엇을 고칠지만 보여 줌
    python3 fdt/rehash_moved_pages.py --run RUN --write    # 고침

판정 시트에서 사람이 그림을 옆 쪽에 그리면 `sheet/apply_validated.py`가 그 행을 그 쪽으로
옮깁니다: `Page`, `Page_Raster`, 쪽 크기가 바뀌고 `Moved_From_Page`가 원래 쪽을 기억합니다.
2026-10-16 전의 그 코드는 `Page_Raster_SHA256`을 옮기지 않았습니다. 그래서 그렇게 옮긴
행은 새 쪽에 있으면서 옛 쪽 그림의 지문을 들고 있고, 지문을 대 보는 곳마다 그림이
바뀌었다고 말합니다(run2 10_1038_S41467_023_41990_4 D004·D006, 결정 묶음 2026-10-15 E01).
코드는 고쳤고, 이 도구는 이미 그렇게 적힌 행을 고칩니다.

고치는 것은 **증거가 그렇다고 말하는 행만**입니다: `Moved_From_Page`가 있고, 적힌 지문이
지금 쪽 래스터의 지문과 다르며, 옮기기 전 쪽 래스터의 지문과 **같은** 행. 적힌 지문이 둘
중 어느 것과도 다르면 그것은 이 결함이 아닙니다(래스터를 다시 뽑았거나, 다른 파일이거나)
- 손대지 않고 이름을 대며 멈춥니다. 하나라도 멈추면 아무것도 쓰지 않습니다.

`Page_Raster`는 그 run을 만든 세션의 절대 경로일 수 있습니다. 그 경로에 파일이 없으면
경로의 `/pages/` 뒤를 `--pages`(기본 `RUN/pages`) 아래에서 찾습니다.
"""
import argparse
import csv
import hashlib
import io
import os
import re

DRAFT = "figure_intake_draft.csv"
PAGE_NAME = re.compile(r"^page-0*(\d+)\.png$")


def sha256(path):
    return hashlib.sha256(io.open(path, "rb").read()).hexdigest()


def resolve(path, pages):
    """그 파일이 있는 경로, 또는 ''."""
    path = str(path or "").strip()
    if path and os.path.isfile(path):
        return path
    if "/pages/" in path:
        there = os.path.join(pages, *path.split("/pages/", 1)[1].split("/"))
        if os.path.isfile(there):
            return there
    return ""


def sibling(raster, page):
    """같은 문서 폴더의 `page` 쪽 래스터. 이름의 0 채움은 문서마다 다르니 숫자로 읽습니다."""
    folder = os.path.dirname(raster)
    for name in sorted(os.listdir(folder)):
        m = PAGE_NAME.match(name)
        if m and int(m.group(1)) == int(page):
            return os.path.join(folder, name)
    return ""


def plan(rows, pages):
    """([(행 번호, Draft_ID, 옛 지문, 새 지문, 옮기기 전 쪽)], 멈춤 [(Draft_ID, 코드, 사유)], 이미 맞는 수)."""
    fixes, stops, fine = [], [], 0
    for n, r in enumerate(rows):
        was = str(r.get("Moved_From_Page") or "").strip()
        if not was:
            continue
        did = r.get("Draft_ID", "")
        cur = resolve(r.get("Page_Raster"), pages)
        if not cur:
            stops.append((did, "PAGE_RASTER_MISSING", "p.%s의 래스터 %s를 찾을 수 없습니다." % (r.get("Page"), r.get("Page_Raster"))))
            continue
        stored, now = str(r.get("Page_Raster_SHA256") or "").strip(), sha256(cur)
        if stored == now:
            fine += 1
            continue
        prev = sibling(cur, was) if was.isdigit() else ""
        if prev and stored == sha256(prev):
            fixes.append((n, did, stored, now, was))
            continue
        stops.append((did, "HASH_UNEXPLAINED", "적힌 지문 %s가 지금 쪽 p.%s(%s)의 것도, 옮기기 전 쪽 p.%s(%s)의 것도 "
                      "아닙니다. 이 결함이 아닙니다 - 손대지 않습니다."
                      % (stored[:12] or "(빈칸)", r.get("Page"), now[:12], was, sha256(prev)[:12] if prev else "래스터 없음")))
    return fixes, stops, fine


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--run", required=True)
    ap.add_argument("--pages", help="쪽 래스터 폴더 (기본: RUN/pages)")
    ap.add_argument("--write", action="store_true", help="고칩니다. 없으면 무엇을 고칠지만 보여 줍니다.")
    a = ap.parse_args(argv)
    path = os.path.join(a.run, DRAFT)
    with io.open(path, encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        fields, rows = list(reader.fieldnames or []), list(reader)
    fixes, stops, fine = plan(rows, a.pages or os.path.join(a.run, "pages"))
    for _n, did, old, new, was in fixes:
        print("고침 %s: Page_Raster_SHA256 %s -> %s (옮기기 전 p.%s의 지문이었음)" % (did, old[:12], new[:12], was))
    for did, code, why in stops:
        print("멈춤 %s — %s: %s" % (did, code, why))
    print("옮긴 행: 고칠 것 %d · 이미 맞음 %d · 멈춤 %d" % (len(fixes), fine, len(stops)))
    if stops:
        print("멈춘 행이 있어 아무것도 쓰지 않았습니다.")
        return 1
    if not a.write or not fixes:
        return 0
    for n, _did, _old, new, _was in fixes:
        rows[n]["Page_Raster_SHA256"] = new
    tmp = path + ".tmp"
    with io.open(tmp, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
    os.replace(tmp, path)
    print("%s에 %d행을 고쳐 적었습니다." % (path, len(fixes)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
