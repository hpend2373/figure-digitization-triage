"""Regression tests for a clean reproducibility environment."""
import builtins
import csv
import json
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


# --------------------------------------------------------------------------
# the pilot's attestation, which is set from outside the file
# --------------------------------------------------------------------------
# Half an attestation reads as a whole one. With only FDT_REVIEWER_NAME set the
# pilot ran a real person's name against a fictional ORCID; with only
# FDT_REVIEWER_ORCID it ran a fictional name against a real ORCID and flipped
# its own Note to "opened all five publisher rasters". With neither, a fictional
# person was recorded HUMAN_CONFIRMED under Status=RAN - harmless only because
# ID397's dispersion is unresolved and nothing is accepted.
PILOT = os.path.join(HERE, "pilot_397.py")
FULL = {"FDT_REVIEWER_NAME": "김민엽",
        "FDT_REVIEWER_ORCID": "0000-0002-1694-233X",
        "FDT_INSPECTION_DATE": "2026-08-06",
        "FDT_REGISTRATION_DATE": "2026-08-01"}


def run_pilot(env_overrides, out_name):
    env = {k: v for k, v in os.environ.items() if k not in FULL}
    env.update(env_overrides)
    env["FDT_RUN_DATE"] = "2026-08-07"
    return subprocess.run(
        [sys.executable, PILOT, os.path.join(tempfile.gettempdir(), out_name)],
        capture_output=True, text=True, env=env)


for label, partial in (
        ("name only", {"FDT_REVIEWER_NAME": FULL["FDT_REVIEWER_NAME"]}),
        ("ORCID only", {"FDT_REVIEWER_ORCID": FULL["FDT_REVIEWER_ORCID"]}),
        ("name and ORCID but no dates",
         {k: FULL[k] for k in ("FDT_REVIEWER_NAME", "FDT_REVIEWER_ORCID")}),
        ("dates only",
         {k: FULL[k] for k in ("FDT_INSPECTION_DATE", "FDT_REGISTRATION_DATE")})):
    r = run_pilot(partial, "fdt_partial")
    assert r.returncode == 2, (
        "a partial attestation (%s) must be BLOCKED (exit 2), got %d\n%s%s"
        % (label, r.returncode, r.stdout, r.stderr))
    assert "partial attestation" in r.stderr, r.stderr
    print("partial attestation BLOCKS the pilot (%s): PASS" % label)

full = run_pilot(FULL, "fdt_attested")
assert full.returncode == 0, "a full attestation must run\n%s%s" % (full.stdout, full.stderr)
assert "[ATTESTED]" in full.stdout, full.stdout
attested = json.load(open(os.path.join(tempfile.gettempdir(), "fdt_attested",
                                       "run_stamp.json")))
assert attested["Run_Mode"] == "ATTESTED", attested
registry = list(csv.DictReader(open(os.path.join(
    tempfile.gettempdir(), "fdt_attested", "manifests",
    "reviewer_registry.csv"), encoding="utf-8")))
assert registry[0]["Reviewer_Name"] == FULL["FDT_REVIEWER_NAME"], registry
assert registry[0]["Reviewer_Contact"] == FULL["FDT_REVIEWER_ORCID"], registry
# The dates were hardcoded to 2026-08-07, which is a false record on every run
# after the day it was written.
assert registry[0]["Registration_Date"] == FULL["FDT_REGISTRATION_DATE"], registry
figures = list(csv.DictReader(open(os.path.join(
    tempfile.gettempdir(), "fdt_attested", "manifests",
    "source_figure_manifest.csv"), encoding="utf-8")))
assert {r["Inspection_Date"] for r in figures} == {FULL["FDT_INSPECTION_DATE"]}, figures
print("a full attestation runs as ATTESTED with the given dates: PASS")

demo = run_pilot({}, "fdt_demo")
assert demo.returncode == 0, "%s%s" % (demo.stdout, demo.stderr)
assert "[DEMO_ONLY]" in demo.stdout, demo.stdout
demo_stamp = json.load(open(os.path.join(tempfile.gettempdir(), "fdt_demo",
                                         "run_stamp.json")))
assert demo_stamp["Run_Mode"] == "DEMO_ONLY", demo_stamp
assert demo_stamp["Values_Accepted"] == 0, demo_stamp
demo_accepted = os.path.join(tempfile.gettempdir(), "fdt_demo",
                             "figure_values_accepted.csv")
assert not os.path.getsize(demo_accepted) or sum(
    1 for _ in open(demo_accepted, encoding="utf-8")) <= 1, (
    "a DEMO_ONLY run wrote poolable rows")
print("no attestation runs as DEMO_ONLY with zero accepted: PASS")
