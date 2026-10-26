"""Where the code, the templates and the repository root are, seen from tests/.

Imported first by every suite, so `python3 tests/test_x.py` works from any
directory: it puts `fdt/` (the pipeline) on `sys.path` and names the folders a
suite may need to read.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
CODE = os.path.join(ROOT, "fdt")
SHEET = os.path.join(CODE, "sheet")
TEMPLATES = os.path.join(ROOT, "templates")
for _p in (CODE, HERE):
    if _p not in sys.path:
        sys.path.insert(0, _p)
