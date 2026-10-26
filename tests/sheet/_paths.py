"""Where the count-sheet code is, seen from tests/sheet/.

Imported first by every sheet suite: it puts `fdt/sheet/` and `fdt/` on
`sys.path` and names the folders a suite may need to read.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TESTS = os.path.dirname(HERE)
ROOT = os.path.dirname(TESTS)
CODE = os.path.join(ROOT, "fdt")
SHEET = os.path.join(CODE, "sheet")
TEMPLATES = os.path.join(ROOT, "templates")
for _p in (CODE, SHEET, HERE):
    if _p in sys.path:
        sys.path.remove(_p)
    sys.path.insert(0, _p)
