# -*- coding: utf-8 -*-
"""Root entry point for sheet/test_sheet_build.py, so CI runs it with the others.

    python3 test_sheet_build.py     # exit 0 = all scenarios pass

The suite itself lives beside the code it tests. This is here because the CI
loop runs `python <name>.py` from the repository root, and a suite that only
exists one directory down is a suite nobody runs.
"""
import os
import runpy
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "sheet"))
runpy.run_path(os.path.join(HERE, "sheet", "test_sheet_build.py"), run_name="__main__")
