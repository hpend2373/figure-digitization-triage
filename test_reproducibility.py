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

# A script that cannot find its input has two honest answers and one dishonest
# one. It can say so and stop, or it can be told the input is genuinely optional
# - but it must not exit 0, because a suite that never opened a figure then
# reports the same green as one that read every cell correctly. Only
# `forward_test_real_monochrome.py` got this right; the other two shipped a
# SKIP, and the pilot's SKIP sat below the code that hashes the rasters, so it
# could not even reach the exit it was wrong about.
import tempfile                                                     # noqa: E402

ABSENT = os.path.join(HERE, "fixtures", "definitely_missing.png")
NOWHERE = os.path.join(tempfile.gettempdir(), "fdt_no_rasters_here")
for label, argv in (
        ("forward_test_real_monochrome.py",
         ["forward_test_real_monochrome.py", ABSENT]),
        ("forward_test_397_mono_bar.py",
         ["forward_test_397_mono_bar.py", ABSENT]),
        ("pilot_397.py",
         ["pilot_397.py", os.path.join(NOWHERE, "out"), NOWHERE])):
    argv = [os.path.join(HERE, argv[0])] + argv[1:]
    missing = subprocess.run([sys.executable] + argv, capture_output=True, text=True)
    assert missing.returncode == 2, (
        "%s with a missing raster must be BLOCKED (exit 2), got %d\n%s%s"
        % (label, missing.returncode, missing.stdout, missing.stderr))
    assert "BLOCKED" in (missing.stdout + missing.stderr), (
        "%s exited 2 without saying which raster is missing\n%s%s"
        % (label, missing.stdout, missing.stderr))
    print("missing raster BLOCKS %s: PASS" % label)
