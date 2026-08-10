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
demo_dir = os.path.join(tempfile.gettempdir(), "fdt_demo")
assert not os.path.exists(os.path.join(demo_dir, "figure_values_accepted.csv")), (
    "a DEMO_ONLY run left an accepted file")
print("no attestation runs as DEMO_ONLY with zero accepted: PASS")

# --------------------------------------------------------------------------
# the approval gate, end to end
# --------------------------------------------------------------------------
# MACHINE_QC_PASSED means the gate found nothing wrong. It does not mean anybody
# looked at where the marks landed - and a reader that puts a plausible number
# on the wrong bar produces exactly the output the gate has nothing to say
# about. `run_batch` used to write `figure_values_accepted.csv` itself, so the
# two claims were the same file.
FIN = os.path.join(HERE, "finalize_batch.py")


def sh(*argv):
    return subprocess.run([sys.executable] + list(argv), capture_output=True,
                          text=True)


att_dir = os.path.join(tempfile.gettempdir(), "fdt_attested")
assert not os.path.exists(os.path.join(att_dir, "figure_values_accepted.csv")), (
    "run_batch wrote an accepted file; only finalize_batch may")
assert os.path.exists(os.path.join(att_dir, "figure_values_machine_qc.csv"))
assert os.path.exists(os.path.join(att_dir, "review_queue.csv"))
print("run_batch stops at machine QC and writes a review queue: PASS")

empty = sh(FIN, att_dir)
assert empty.returncode == 1 and "NOTHING_APPROVED" in empty.stdout, empty.stdout
assert not os.path.exists(os.path.join(att_dir, "figure_values_accepted.csv"))
print("an unreviewed run finalizes to nothing: PASS")


# --------------------------------------------------------------------------
# the environment a value depended on
# --------------------------------------------------------------------------
# The run recorded its own code hash and nothing about what that code ran on.
# Contour finding, raster decoding and least-squares fitting all live in
# libraries this package pins only by lower bound, and a bar top found at row
# 312 by one OpenCV and row 313 by the next is a different number in the
# accepted file.
import glob                                                        # noqa: E402
import re                                                          # noqa: E402

sys.path.insert(0, HERE)
import run_batch as RB_ENV                                         # noqa: E402

env = RB_ENV.environment_record()
assert env["Python"] and env["Platform"], env
assert set(env["Libraries"]) == {"numpy", "pandas", "PIL", "cv2"}, env
assert all(v and v != "unknown" for v in env["Libraries"].values()), env
print("the runner can describe its own environment: PASS")

stamp = json.load(open(os.path.join(att_dir, "run_stamp.json")))
assert stamp.get("Environment", {}).get("Python"), stamp
assert stamp["Environment"]["Libraries"]["numpy"] == env["Libraries"]["numpy"], stamp
print("and every run stamp carries it: PASS")

LOCK = os.path.join(HERE, "requirements-lock.txt")
assert os.path.exists(LOCK), "requirements-lock.txt is not in the package"
locked = dict(re.findall(r"^([A-Za-z0-9_.-]+)==([^\s]+)$",
                         open(LOCK, encoding="utf-8").read(), re.M))
lower = {re.split(r"[><=]", line)[0].strip().lower()
         for line in open(os.path.join(HERE, "requirements.txt"), encoding="utf-8")
         if line.strip() and not line.startswith("#")}
assert lower <= {k.lower() for k in locked}, (
    "%s is required but not pinned" % sorted(lower - {k.lower() for k in locked}))
assert "opencv-python==" not in open(LOCK, encoding="utf-8").read(), (
    "opencv-python and opencv-python-headless both provide cv2; pinning both "
    "leaves which one answers an import to resolution order")
print("every requirement is pinned in the lock file, exactly once: PASS")

# --------------------------------------------------------------------------
# the templates the package ships
# --------------------------------------------------------------------------
# A template is a promise about a schema, and `value_review_TEMPLATE.csv` still
# offered `Panel_Fingerprint` - a column that has not existed since 7.16.
# Anybody starting from it got REVIEW_SCHEMA_INCOMPLETE: safe, but the shipped
# artifact contradicted the running code, and 1275 scenarios passed anyway
# because nothing tested a static file. The check below is over EVERY template
# on disk, and an unmapped one is a failure - so a new template cannot be added
# without a column function behind it.
import batch_manifests as BM_T                                     # noqa: E402
import grid_engine as GE_T                                         # noqa: E402
import finalize_batch as FIN_T                                     # noqa: E402

TEMPLATE_COLUMNS = dict(
    [(name, fn) for name, fn in BM_T.BATCH_TEMPLATES]
    + [("figure_manifest", GE_T.fig_figure_columns),
       ("grid_definitions", GE_T.fig_grid_columns),
       ("unit_manifest", GE_T.fig_unit_columns),
       ("figure_values", GE_T.fig_values_columns),
       ("value_review", FIN_T.value_review_columns)])

# The flat single-table template belongs to the pre-batch hand-extraction path
# that `kernel.fig_validate_extraction` still serves. It does not follow the
# `*_TEMPLATE.csv` naming, so the glob missed it and nothing could tell whether
# it was current - which is exactly the state `value_review_TEMPLATE.csv` was
# found in. It is generated from `fig_template_columns`, so it is checked here
# by name.
import kernel as K_T                                               # noqa: E402

LEGACY_TEMPLATES = {os.path.join(HERE, "figure_extraction_template_v7.csv"):
                    K_T.fig_template_columns}
for _path, _fn in LEGACY_TEMPLATES.items():
    assert os.path.exists(_path), "%s is referenced but not shipped" % _path
    with open(_path, newline="", encoding="utf-8") as fh:
        assert next(csv.reader(fh)) == _fn(), (
            "%s no longer matches fig_template_columns()" % os.path.basename(_path))

shipped = sorted(glob.glob(os.path.join(HERE, "*_TEMPLATE.csv")))
unmapped = [os.path.basename(p) for p in shipped
            if os.path.basename(p)[:-len("_TEMPLATE.csv")] not in TEMPLATE_COLUMNS]
assert not unmapped, (
    "%s ships with no column function behind it, so nothing can tell whether "
    "it is current" % unmapped)
drifted = []
for path in shipped:
    name = os.path.basename(path)[:-len("_TEMPLATE.csv")]
    with open(path, newline="", encoding="utf-8") as fh:
        header = next(csv.reader(fh))
    want = TEMPLATE_COLUMNS[name]()
    if header != want:
        drifted.append("%s: %s" % (
            os.path.basename(path),
            {"missing": [c for c in want if c not in header],
             "stale": [c for c in header if c not in want]}))
assert not drifted, "shipped templates disagree with the code: %s" % drifted
assert len(shipped) == len(TEMPLATE_COLUMNS), (
    "%d column functions but %d templates on disk"
    % (len(TEMPLATE_COLUMNS), len(shipped)))
print("every shipped template matches its column function (%d): PASS" % len(shipped))

# The skill the package ships is the skill an agent installs. It was an
# addendum - "sections to add", to be pasted into a SKILL.md that lived
# somewhere else - so what got installed depended on somebody doing the pasting
# correctly, and the entrypoint contract was in neither document.
SKILL = os.path.join(HERE, "SKILL.md")
assert os.path.exists(SKILL), "SKILL.md is not in the package"
skill_text = open(SKILL, encoding="utf-8").read()
assert skill_text.startswith("---\nname: "), (
    "SKILL.md has no front matter, so nothing can discover it")
for required in ("compile_plan.py", "run_batch.py", "finalize_batch.py",
                 "figure_values_accepted.csv", "finalize_stamp.json",
                 "value_review.csv", "review_queue.csv"):
    assert required in skill_text, (
        "SKILL.md never mentions %s, so it does not describe the run" % required)
# The contract has to name the states a run can end in, or an agent cannot tell
# a refusal from a result.
for status in ("MANIFEST_REJECTED", "INPUT_LOAD_FAILED", "DEMO_OUTPUT_REFUSED",
               "INTERNAL_ERROR", "RUN_ARTIFACT_MODIFIED", "NOTHING_APPROVED",
               "FINALIZED"):
    assert status in skill_text, "SKILL.md does not say what %s means" % status
# The run steps were corrected to branch on Review_Mode; the protocol body
# further down still said every passing panel gets an overlay, which is the
# contract the code stopped holding when WPD_ONLY appeared.
assert "WPD_ONLY" in skill_text and "Review_Mode" in skill_text, (
    "SKILL.md does not tell a reviewer what to open when there is no overlay")
for stale in ("Each passing panel also gets `review/",
              "open review/<Panel_ID>_overlay.png for every row"):
    assert stale not in skill_text, (
        "SKILL.md still says %r, which contradicts Review_Mode=WPD_ONLY" % stale)
# Every review mode the runner can put in the queue, named in the table a
# reviewer reads. The table ends with "anything else -> do not approve", so a
# mode the skill has not heard of tells a reviewer to refuse a panel the run
# produced correctly - which is what BAR_MONO panels got when the geometry mode
# shipped without touching this file.
import run_batch as _rb                                            # noqa: E402
_unnamed = sorted(m for m in _rb.REVIEW_MODES if m not in skill_text)
assert not _unnamed, (
    "SKILL.md does not tell a reviewer what to open for %s" % ", ".join(_unnamed))
_unasked = sorted({c for cols in _rb.REVIEW_CONFIRMATIONS.values() for c in cols}
                  - set(skill_text.split()))
_unasked = [c for c in _unasked if c not in skill_text]
assert not _unasked, (
    "SKILL.md never mentions the confirmation column(s) %s, so a reviewer "
    "fills in a decision the finalizer then refuses" % ", ".join(_unasked))

assert "sections to add" not in skill_text, (
    "SKILL.md is still written as an addendum to some other document")
assert not os.path.exists(os.path.join(HERE, "SKILL_ADDENDUM.md")), (
    "both SKILL.md and SKILL_ADDENDUM.md ship; one of them is stale by "
    "construction")
print("SKILL.md is standalone and states the run contract: PASS")

# CI must run every suite in the package. A test file nobody runs is a test
# file that will be broken the next time somebody looks.
CI = os.path.join(HERE, ".github", "workflows", "suite.yml")
assert os.path.exists(CI), "no CI workflow in the package"
ci_text = open(CI, encoding="utf-8").read()
suites = {os.path.basename(p)[:-3] for p in glob.glob(os.path.join(HERE, "test_*.py"))}
unrun = sorted(s for s in suites if s not in ci_text)
assert not unrun, "CI does not run: %s" % unrun
print("CI runs every test file in the package (%d): PASS" % len(suites))

# And every forward test, which the pattern above does not match. A forward test
# is the only thing in the package that opens a publisher figure, so one that
# nobody runs is exactly the one whose absence is least visible - the suites
# stay green either way. The ones whose raster is not redistributable SKIP in
# CI, which is a different outcome from not being there.
forwards = {os.path.basename(p)[:-3]
            for p in glob.glob(os.path.join(HERE, "forward_test_*.py"))}
unrun = sorted(s for s in forwards if s not in ci_text)
assert not unrun, "CI does not run the forward tests: %s" % unrun
print("CI runs every forward test in the package (%d): PASS" % len(forwards))

# No scenario may be written so that it cannot fail. Two were: a caption check
# ending `... or True`, which passed whatever the picture contained, and an
# `all(... or True ...)` inside a figure-isolation check. Both looked like
# assertions in the output - "ok" beside a sentence - and asserted nothing.
#
# A short-circuiting truth literal inside a scenario is always that mistake:
# there is no reason to write `X or True` except to make X stop mattering.
# Grepped rather than reasoned about, because the property is textual.
# Parsed, not grepped. A line-by-line search misses `condition or\n True`,
# `condition or (True)` and `x or 1`, and a contract that only holds when the
# mistake is written on one line is not the contract.
import ast                                                          # noqa: E402

def _short_circuits(tree):
    """Truth literals that make the expression around them unfalsifiable."""
    for node in ast.walk(tree):
        if isinstance(node, ast.BoolOp):
            wants = isinstance(node.op, ast.Or)
            for value in node.values:
                if isinstance(value, ast.Constant) and bool(value.value) is wants:
                    yield node.lineno


vacuous = []
for path in sorted(glob.glob(os.path.join(HERE, "test_*.py"))
                   + glob.glob(os.path.join(HERE, "forward_test_*.py"))):
    tree = ast.parse(open(path, encoding="utf-8").read(), path)
    for node in ast.walk(tree):
        # The CONDITION of a scenario, and nothing else. `x or "fallback"` in
        # the detail string, or `r.get("error") or "READING"` in ordinary code,
        # is the normal Python idiom for a default and says nothing about
        # whether a scenario can fail; flagging it would make this check
        # something people route around.
        tested = []
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                and node.func.id == "check" and len(node.args) >= 2):
            tested = [node.args[1]]
        elif isinstance(node, ast.Assert):
            tested = [node.test]
        for expression in tested:
            for line in _short_circuits(expression):
                vacuous.append("%s:%d" % (os.path.basename(path), line))
assert not vacuous, ("a scenario that cannot fail is not a scenario: %s"
                     % ", ".join(vacuous))
print("no scenario is written so that it cannot fail (%d files): PASS"
      % len(glob.glob(os.path.join(HERE, "test_*.py"))))
