# -*- coding: utf-8 -*-
"""Every image an intake wrote must decode, all the way to its last row.

    python3 verify_intake_images.py <intake directory>

WHY. A render that is interrupted leaves a PNG with a valid header and a
truncated body. Nothing downstream notices: the file is there, it has a
plausible size, and `Page_Raster_SHA256` hashes the bytes that made it to disk
just as happily as it would hash the whole picture. The first thing to fail is
whatever finally tries to read the last row of pixels - which in this run was a
measurement script, three steps and a day later.

`Image.open` alone does not settle it either; it reads the header and returns.
`load()` is what decodes the image data, so that is what this does.

Exit 0 = every image decodes. Non-zero = the list of the ones that do not.
"""
import io
import json
import os
import sys

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


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv:
        raise SystemExit(__doc__.strip().splitlines()[2].strip())
    root = argv[0]
    receipt = argv[1] if len(argv) > 1 else ""
    bad = unreadable(root)
    total = sum(1 for b, _d, fs in os.walk(root) for f in fs
                if f.lower().endswith((".png", ".jpg", ".jpeg")))
    if receipt:
        json.dump({"root": os.path.abspath(root), "images": total,
                   "unreadable": [list(x) for x in bad],
                   "verdict": "REFUSED" if bad else "ALL_DECODE"},
                  io.open(receipt, "w", encoding="utf-8"), indent=2,
                  ensure_ascii=False)
    for rel, size, err in bad[:20]:
        print("  깨진 이미지  %-60s %d바이트 %s" % (rel[-60:], size, err))
    print("이미지 %d개 중 끝까지 읽히지 않는 것 %d개" % (total, len(bad)))
    if bad:
        print("판정: REFUSED — 다시 렌더해야 합니다")
        return 1
    print("판정: ALL_DECODE")
    return 0


if __name__ == "__main__":
    sys.exit(main())
