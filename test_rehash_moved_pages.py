# -*- coding: utf-8 -*-
"""Scenarios for rehash_moved_pages.py (a moved figure row still carrying the old page's fingerprint).

    python3 test_rehash_moved_pages.py

Each scenario is a way the repair could write a fingerprint the evidence does not support: a row that was
never moved, a fingerprint that belongs to neither page, a page that is not there, or a half-written draft.
"""
import csv
import hashlib
import io
import os
import shutil
import sys
import tempfile

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import rehash_moved_pages as R                                   # noqa: E402

FAILURES, PASSED = [], [0]


def check(name, ok, detail=""):
    print(("  ok   " if ok else "  FAIL ") + name + ("" if ok else "  <- %s" % (detail,)))
    if ok:
        PASSED[0] += 1
    else:
        FAILURES.append(name)


ROOT = tempfile.mkdtemp(prefix="fdt_rehash_")
FIELDS = ["Draft_ID", "Page", "Page_Raster", "Page_Raster_SHA256", "Moved_From_Page", "Note"]


def sha(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


def build(rows_for):
    run = os.path.join(ROOT, "run")
    if os.path.exists(run):
        shutil.rmtree(run)
    doc = os.path.join(run, "pages", "DOC")
    os.makedirs(doc)
    for i, shade in ((7, 40), (8, 120), (9, 200), (10, 250)):
        Image.new("L", (60, 80), shade).save(os.path.join(doc, "page-%02d.png" % i))
    p = dict((i, os.path.join(doc, "page-%02d.png" % i)) for i in (7, 8, 9, 10))
    rows = rows_for(p)
    with io.open(os.path.join(run, R.DRAFT), "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS)
        w.writeheader()
        for r in rows:
            w.writerow(dict((c, r.get(c, "")) for c in FIELDS))
    return run, p


def draft(run):
    return dict((r["Draft_ID"], r) for r in csv.DictReader(io.open(os.path.join(run, R.DRAFT), encoding="utf-8")))


def standard(p):
    old = "/sessions/old-session/mnt/Downloads/run/pages/DOC/page-10.png"
    return [
        {"Draft_ID": "D_MOVED_STALE", "Page": "8", "Page_Raster": p[8], "Page_Raster_SHA256": sha(p[9]), "Moved_From_Page": "9",
         "Note": "사람의 메모"},
        {"Draft_ID": "D_MOVED_FINE", "Page": "9", "Page_Raster": p[9], "Page_Raster_SHA256": sha(p[9]), "Moved_From_Page": "10"},
        {"Draft_ID": "D_NOT_MOVED", "Page": "7", "Page_Raster": p[7], "Page_Raster_SHA256": sha(p[9])},
        {"Draft_ID": "D_OLD_PATH", "Page": "10", "Page_Raster": old, "Page_Raster_SHA256": sha(p[9]), "Moved_From_Page": "9"},
    ]


RUN, P = build(standard)
before = open(os.path.join(RUN, R.DRAFT), "rb").read()
check("a dry run changes nothing", R.main(["--run", RUN]) == 0 and open(os.path.join(RUN, R.DRAFT), "rb").read() == before)
fixes, stops, fine = R.plan(list(draft(RUN).values()), os.path.join(RUN, "pages"))
check("the plan names the moved rows carrying the page they left, and nothing else",
      sorted(f[1] for f in fixes) == ["D_MOVED_STALE", "D_OLD_PATH"] and not stops and fine == 1, (fixes, stops, fine))
check("--write fixes them", R.main(["--run", RUN, "--write"]) == 0)
d = draft(RUN)
check("the moved row now carries its own page's fingerprint", d["D_MOVED_STALE"]["Page_Raster_SHA256"] == sha(P[8]))
# REVERT: read only the path as written. A run made in another session names a path that is not there any more.
check("a path from the session that made the run is found under the run's pages",
      d["D_OLD_PATH"]["Page_Raster_SHA256"] == sha(P[10]))
# REVERT: rehash every row. A row that was never moved is not this defect, whatever its fingerprint says.
check("a row that was never moved is not touched, even with a wrong fingerprint", d["D_NOT_MOVED"]["Page_Raster_SHA256"] == sha(P[9]))
check("a moved row already right is not touched", d["D_MOVED_FINE"]["Page_Raster_SHA256"] == sha(P[9]))
check("only the fingerprint changes - not the path, not the person's note",
      d["D_MOVED_STALE"]["Page_Raster"] == P[8] and d["D_MOVED_STALE"]["Note"] == "사람의 메모"
      and d["D_OLD_PATH"]["Page_Raster"].startswith("/sessions/old-session/"))
after = open(os.path.join(RUN, R.DRAFT), "rb").read().splitlines()
check("the other lines of the draft are byte for byte what they were",
      [l for l in after if b"D_MOVED_STALE" not in l and b"D_OLD_PATH" not in l]
      == [l for l in before.splitlines() if b"D_MOVED_STALE" not in l and b"D_OLD_PATH" not in l])
check("a second run finds nothing to fix", R.main(["--run", RUN, "--write"]) == 0 and draft(RUN) == d)

# REVERT: fix any mismatch on a moved row. A fingerprint from a re-rendered page would be overwritten without a word.
RUN, P = build(lambda p: standard(p) + [{"Draft_ID": "D_STRANGE", "Page": "8", "Page_Raster": p[8], "Page_Raster_SHA256": "ab" * 32,
                                         "Moved_From_Page": "9"}])
before = open(os.path.join(RUN, R.DRAFT), "rb").read()
check("a fingerprint that belongs to neither page stops the run, and nothing is written",
      R.main(["--run", RUN, "--write"]) == 1 and open(os.path.join(RUN, R.DRAFT), "rb").read() == before)
check("... by name", [s[:2] for s in R.plan(list(draft(RUN).values()), os.path.join(RUN, "pages"))[1]] == [("D_STRANGE", "HASH_UNEXPLAINED")])
RUN, P = build(lambda p: standard(p) + [{"Draft_ID": "D_GONE", "Page": "8", "Page_Raster": "/nowhere/page-08.png",
                                         "Page_Raster_SHA256": sha(p[9]), "Moved_From_Page": "9"}])
before = open(os.path.join(RUN, R.DRAFT), "rb").read()
check("a page that cannot be found stops the run, and nothing is written",
      R.main(["--run", RUN, "--write"]) == 1 and open(os.path.join(RUN, R.DRAFT), "rb").read() == before
      and [s[:2] for s in R.plan(list(draft(RUN).values()), os.path.join(RUN, "pages"))[1]] == [("D_GONE", "PAGE_RASTER_MISSING")])
RUN, P = build(lambda p: [{"Draft_ID": "D_NO_PREV", "Page": "8", "Page_Raster": p[8], "Page_Raster_SHA256": sha(p[9]),
                           "Moved_From_Page": "3"}])
check("a moved-from page whose raster is not there cannot explain the fingerprint",
      [s[:2] for s in R.plan(list(draft(RUN).values()), os.path.join(RUN, "pages"))[1]] == [("D_NO_PREV", "HASH_UNEXPLAINED")])
check("page names are read as numbers (page-8.png and page-008.png are page 8)",
      R.sibling(P[9], 8) == P[8] and R.sibling(P[9], "08") == P[8])
check("--pages points at another pages folder", R.resolve("/x/pages/DOC/page-07.png", os.path.join(ROOT, "run", "pages")) == P[7]
      and R.resolve("/x/pages/DOC/page-07.png", os.path.join(ROOT, "elsewhere")) == "")

shutil.rmtree(ROOT, ignore_errors=True)
print()
print("%d scenarios run" % (PASSED[0] + len(FAILURES)))
print("FDT_SCENARIOS_RUN=%d" % PASSED[0])
if FAILURES:
    print("FAILED: %s" % FAILURES)
    raise SystemExit(1)
print("all scenarios passed")
