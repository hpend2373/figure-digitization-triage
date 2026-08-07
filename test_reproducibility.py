"""Regression tests for a clean reproducibility environment."""
import builtins
import importlib.util
import os
import subprocess
import sys


HERE = os.path.dirname(os.path.abspath(__file__))
real_import = builtins.__import__


def without_scipy(name, globals=None, locals=None, fromlist=(), level=0):
    if name == "scipy" or name.startswith("scipy."):
        raise ModuleNotFoundError("scipy intentionally unavailable in clean-room test")
    return real_import(name, globals, locals, fromlist, level)


builtins.__import__ = without_scipy
try:
    spec = importlib.util.spec_from_file_location(
        "mark_readers_clean", os.path.join(HERE, "mark_readers.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
finally:
    builtins.__import__ = real_import

points = [dict(x_value=x, y_value=y) for x, y in
          ((1, 2), (2, 3), (3, 5), (4, 4), (5, 8), (6, 9))]
for kind in ("PEARSON_R", "SPEARMAN_RHO", "KENDALL_TAU", "R_SQUARED", "SLOPE"):
    result = module.summarize_association(points, kind)
    assert result["Association_Type"] == kind
    assert result["N_Pairs"] == 6
    assert result["Association_Value"] == result["Association_Value"]

print("clean-room import without scipy: PASS")

missing = subprocess.run(
    [sys.executable, os.path.join(HERE, "forward_test_real_monochrome.py"),
     os.path.join(HERE, "fixtures", "definitely_missing.png")],
    capture_output=True, text=True,
)
assert missing.returncode == 2, (
    "a missing forward-test fixture must be BLOCKED (exit 2), got %d\n%s%s"
    % (missing.returncode, missing.stdout, missing.stderr))
print("missing forward fixture exits 2: PASS")
