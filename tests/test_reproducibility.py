"""The package as a whole: clean-room imports, pinned environment, shipped
schemas, the skill contract, CI coverage, and what may never be tracked.

    python3 tests/test_reproducibility.py
"""
import _paths  # noqa: E402,F401  (puts fdt/ on sys.path)
import builtins
import csv
import json
import importlib.util
import os
import subprocess
import sys


HERE = os.path.dirname(os.path.abspath(__file__))

#: Scenarios PRINTED. This file uses neither `check` nor `expect` - it asserts
#: and prints a PASS line - so it reported no total, and the CI guard that sums
#: the suites had nothing to read from it.
_PASSES = [0]


def passed(message):
    """A scenario that held, counted on its way out."""
    _PASSES[0] += 1
    print("%s: PASS" % message)
real_import = builtins.__import__


def without_scipy(name, globals=None, locals=None, fromlist=(), level=0):
    if name == "scipy" or name.startswith("scipy."):
        raise ModuleNotFoundError("scipy intentionally unavailable in clean-room test")
    return real_import(name, globals, locals, fromlist, level)


builtins.__import__ = without_scipy
try:
    spec = importlib.util.spec_from_file_location(
        "mark_readers_clean", os.path.join(_paths.CODE, "mark_readers.py"))
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

passed("clean-room import without scipy")

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

import run_batch as RB_ENV                                         # noqa: E402

env = RB_ENV.environment_record()
assert env["Python"] and env["Platform"], env
assert set(env["Libraries"]) == {"numpy", "pandas", "PIL", "cv2"}, env
assert all(v and v != "unknown" for v in env["Libraries"].values()), env
passed("the runner can describe its own environment")

LOCK = os.path.join(_paths.ROOT, "requirements-lock.txt")
assert os.path.exists(LOCK), "requirements-lock.txt is not in the package"
locked = dict(re.findall(r"^([A-Za-z0-9_.-]+)==([^\s]+)$",
                         open(LOCK, encoding="utf-8").read(), re.M))
lower = {re.split(r"[><=]", line)[0].strip().lower()
         for line in open(os.path.join(_paths.ROOT, "requirements.txt"), encoding="utf-8")
         if line.strip() and not line.startswith("#")}
assert lower <= {k.lower() for k in locked}, (
    "%s is required but not pinned" % sorted(lower - {k.lower() for k in locked}))
assert "opencv-python==" not in open(LOCK, encoding="utf-8").read(), (
    "opencv-python and opencv-python-headless both provide cv2; pinning both "
    "leaves which one answers an import to resolution order")
passed("every requirement is pinned in the lock file, exactly once")

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
       ("value_review", FIN_T.value_review_columns),
       # The per-cell decisions. Shipped for the same reason the panel one is:
       # somebody looking at the package should be able to see the shape of the
       # answer before they have a run to answer about.
       ("inference_review", FIN_T.inference_review_columns)])

# The flat single-table template belongs to the pre-batch hand-extraction path
# that `kernel.fig_validate_extraction` still serves. It does not follow the
# `*_TEMPLATE.csv` naming, so the glob missed it and nothing could tell whether
# it was current - which is exactly the state `value_review_TEMPLATE.csv` was
# found in. It is generated from `fig_template_columns`, so it is checked here
# by name.
import kernel as K_T                                               # noqa: E402

LEGACY_TEMPLATES = {os.path.join(_paths.TEMPLATES, "figure_extraction_template_v7.csv"):
                    K_T.fig_template_columns}
for _path, _fn in LEGACY_TEMPLATES.items():
    assert os.path.exists(_path), "%s is referenced but not shipped" % _path
    with open(_path, newline="", encoding="utf-8") as fh:
        assert next(csv.reader(fh)) == _fn(), (
            "%s no longer matches fig_template_columns()" % os.path.basename(_path))

shipped = sorted(glob.glob(os.path.join(_paths.TEMPLATES, "*_TEMPLATE.csv")))
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
passed("every shipped template matches its column function (%d)" % len(shipped))

# The skill the package ships is the skill an agent installs. It was an
# addendum - "sections to add", to be pasted into a SKILL.md that lived
# somewhere else - so what got installed depended on somebody doing the pasting
# correctly, and the entrypoint contract was in neither document.
SKILL = os.path.join(_paths.ROOT, "SKILL.md")
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
assert not os.path.exists(os.path.join(_paths.ROOT, "SKILL_ADDENDUM.md")), (
    "both SKILL.md and SKILL_ADDENDUM.md ship; one of them is stale by "
    "construction")
passed("SKILL.md is standalone and states the run contract")

# CI must run every suite in the package. A test file nobody runs is a test
# file that will be broken the next time somebody looks. The workflow runs the
# suites by GLOB rather than by a list somebody has to keep, so the check is
# that every glob the suites live under is the one the workflow loops over -
# and that the loop requires the scenario marker from each one.
CI = os.path.join(_paths.ROOT, ".github", "workflows", "suite.yml")
RUNNER = os.path.join(_paths.ROOT, ".github", "run_suites.sh")
assert os.path.exists(CI), "no CI workflow in the package"
assert os.path.exists(RUNNER), "no suite runner beside the workflow"
_workflow = open(CI, encoding="utf-8").read()
assert "run_suites.sh" in _workflow, "the workflow does not call the suite runner"
ci_text = _workflow + open(RUNNER, encoding="utf-8").read()
for _glob in ("tests/test_*.py", "tests/sheet/test_*.py", "tests/test_*.mjs",
              "tests/sheet/test_*.mjs"):
    assert _glob in ci_text, "CI does not loop over %s" % _glob
    assert glob.glob(os.path.join(_paths.ROOT, _glob)), (
        "CI loops over %s and nothing matches it" % _glob)
assert "FDT_SCENARIOS_RUN" in ci_text, (
    "CI does not require the scenario marker, so a suite that ran nothing "
    "would go green")
_suites = (glob.glob(os.path.join(HERE, "test_*.py"))
           + glob.glob(os.path.join(HERE, "sheet", "test_*.py")))
_silent = [os.path.relpath(p, _paths.ROOT) for p in _suites
           if "FDT_SCENARIOS_RUN" not in open(p, encoding="utf-8").read()]
assert not _silent, "these suites print no FDT_SCENARIOS_RUN marker: %s" % _silent
passed("CI runs every test file in the package (%d)" % len(_suites))

# AND NO PUBLISHER FIGURE, PDF OR CORPUS FILE IS TRACKED. This repository is
# public and the figures it is built to read are not redistributable. Rasters
# once were tracked here, one `git add -A` at a time, and had to be purged from
# the history. `.gitignore` is the first fence and `git add -f` walks through it;
# this is the second, and it runs in CI.
#
# THE RULE IS STRUCTURAL rather than a list of names: every tracked picture is a
# synthetic test fixture under `tests/`, drawn by a `make_*` script or described
# by a truth file, and no document format a publisher ships is tracked at all.
_RASTER = (".png", ".jpg", ".jpeg", ".tif", ".tiff", ".gif", ".bmp", ".webp")
_NEVER = (".pdf", ".tar", ".xls", ".xlsx", ".docx")
_CORPUS = ("dig201.csv", "clips201.csv", "captions.csv", "proposals.csv")
_index = subprocess.run(["git", "ls-files"], cwd=_paths.ROOT,
                        capture_output=True, text=True)
if _index.returncode == 0 and _index.stdout.strip():
    _tracked = _index.stdout.splitlines()
    _bad = [t for t in _tracked
            if t.lower().endswith(_NEVER)
            or os.path.basename(t) in _CORPUS or t.startswith("clips/")
            or (t.lower().endswith(_RASTER) and not t.startswith("tests/"))]
    assert not _bad, ("these must never be tracked in a public repository: %s"
                      % _bad)
    passed("no publisher figure, PDF or corpus file is tracked (%d paths checked)"
           % len(_tracked))
else:
    # A TARBALL HAS NO INDEX, so there is nothing to be wrong. Counted anyway,
    # so the scenario count does not depend on how the tree was obtained.
    passed("no publisher figure, PDF or corpus file is tracked (no index here)")

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
                   + glob.glob(os.path.join(HERE, "sheet", "test_*.py"))):
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
passed("no scenario is written so that it cannot fail (%d files)"
      % (len(glob.glob(os.path.join(HERE, "test_*.py")))
         + len(glob.glob(os.path.join(HERE, "sheet", "test_*.py")))))

# One line, one format, for the CI loop that requires a marker from every suite.
print("FDT_SCENARIOS_RUN=%d" % _PASSES[0])
