# -*- coding: utf-8 -*-
"""Every image an intake wrote must be there, and must decode to its last row.

    python3 verify_intake_images.py <intake directory> [receipt.json]

WHY. A render that is interrupted leaves a PNG with a valid header and a
truncated body. Nothing downstream notices: the file is there, it has a
plausible size, and `Page_Raster_SHA256` hashes the bytes that made it to disk
just as happily as it would hash the whole picture. The first thing to fail is
whatever finally tries to read the last row of pixels - which in this run was a
measurement script, three steps and a day later.

`Image.open` alone does not settle it either; it reads the header and returns.
`load()` is what decodes the image data, so that is what this does.

AND DECODING WHAT IS THERE SAYS NOTHING ABOUT WHAT IS NOT. This walked the
directory and reported every file it found as fine - which is exactly what it
did while one page raster the draft names was still sitting in the part it was
built in, because a merge skipped a document whose directory already existed.
The draft is the list of what should exist; the disk is what does. Both
directions are compared: named and absent, and present and unnamed.

Exit 0 = every image decodes. Non-zero = the list of the ones that do not.
"""
import csv
import io
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from PIL import Image


def unreadable(root):
    """[(relative path, bytes, error)] for every PNG that will not decode."""
    bad = []
    for base, _dirs, files in os.walk(root):
        for f in sorted(files):
            if not f.lower().endswith((".png", ".jpg", ".jpeg")):
                continue
            p = os.path.join(base, f)
            try:
                im = Image.open(p)
                im.load()
            except Exception as exc:
                bad.append((os.path.relpath(p, root), os.path.getsize(p),
                            type(exc).__name__))
    return bad


def expected(root):
    """{relative path: the Draft_ID that names it} from the draft itself."""
    draft = os.path.join(root, "figure_intake_draft.csv")
    if not os.path.exists(draft):
        return None
    out = {}
    with io.open(draft, encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            for col in ("Figure_Crop", "Page_Raster"):
                v = (r.get(col) or "").strip()
                if not v:
                    continue
                rel = os.path.relpath(v, root) if os.path.isabs(v) else v
                out.setdefault(rel, r["Draft_ID"])
    return out


def on_disk(root):
    return {os.path.relpath(os.path.join(b, f), root)
            for b, _d, fs in os.walk(root) for f in fs
            if f.lower().endswith((".png", ".jpg", ".jpeg"))}


def roundtrip_mismatches(root):
    """[(Draft_ID, detail)] for crops the draft's own geometry cannot re-cut."""
    import csv
    import roundtrip
    path = os.path.join(root, "figure_intake_draft.csv")
    if not os.path.exists(path):
        return []
    out = []
    for row in csv.DictReader(io.open(path, encoding="utf-8")):
        status, detail = roundtrip.check(row, root)
        if status in ("MISMATCH", "NO_CUT"):
            out.append((row["Draft_ID"], "%s %s" % (status, detail)))
    return out


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv:
        raise SystemExit(__doc__.strip().splitlines()[2].strip())
    root = argv[0]
    receipt = argv[1] if len(argv) > 1 else ""
    bad = unreadable(root)
    here = on_disk(root)
    want = expected(root)
    absent = sorted((rel, want[rel]) for rel in (want or {}) if rel not in here)
    # An image on disk that the draft does not name is not an error - the
    # parts directories and any earlier run's leftovers live under the same
    # root - so it is counted and named, not refused on.
    unnamed = sorted(here - set(want or {}))
    # THE THIRD QUESTION. Decoding proves the file is whole; the expected list
    # proves it is the file the draft names. Neither proves the picture in it
    # is the region the draft's box describes - a mirrored or stale crop
    # decodes perfectly. `roundtrip` cuts the box again and compares.
    mismatched = roundtrip_mismatches(root)
    problems = (bool(bad) or bool(absent) or want is None
                or bool(mismatched))
    if receipt:
        json.dump({"root": os.path.abspath(root), "images_on_disk": len(here),
                   "named_by_draft": len(want or {}),
                   "unreadable": [list(x) for x in bad],
                   "named_but_absent": [list(x) for x in absent],
                   "on_disk_not_named": len(unnamed),
                   "roundtrip_mismatched": [list(x) for x in mismatched],
                   "verdict": "REFUSED" if problems else "COMPLETE_AND_DECODES"},
                  io.open(receipt, "w", encoding="utf-8"), indent=2,
                  ensure_ascii=False)
    for rel, size, err in bad[:20]:
        print("  깨진 이미지  %-58s %d바이트 %s" % (rel[-58:], size, err))
    for rel, did in absent[:20]:
        print("  초안이 부르는데 없음  %-46s (%s)" % (rel[-46:], did[-24:]))
    if want is None:
        print("figure_intake_draft.csv가 없어 기대 목록을 만들 수 없습니다")
    else:
        print("초안이 부르는 %d개 중 없는 것 %d개 · 디스크의 %d개 중 초안이 "
              "부르지 않는 것 %d개" % (len(want), len(absent), len(here),
                                  len(unnamed)))
    for did, detail in mismatched[:20]:
        print("  상자에서 다시 만들 수 없음  %-40s %s" % (did[-40:], detail))
    print("끝까지 읽히지 않는 것 %d개 · 상자에서 다시 만들 수 없는 것 %d개"
          % (len(bad), len(mismatched)))
    if problems:
        print("판정: REFUSED — 깨진·없는 이미지는 다시 렌더하거나 병합을 마저 "
              "해야 하고, 상자에서 다시 만들 수 없는 크롭은 초안의 기하를 "
              "채우거나 그 행을 계수에서 빼야 합니다")
        return 1
    print("판정: COMPLETE_AND_DECODES")
    return 0


if __name__ == "__main__":
    sys.exit(main())
