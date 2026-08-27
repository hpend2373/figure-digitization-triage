"""Regression tests for a clean reproducibility environment."""
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

passed("clean-room import without scipy")

# A script that cannot find its input has two honest answers and one dishonest
# one. It can say so and stop, or it can be told the input is genuinely optional
# - but it must not exit 0 SILENTLY, because a suite that never opened a figure
# then reports the same green as one that read every cell correctly.
#
# THE CONTRACT CHANGED WHEN THE RASTERS LEFT THE REPOSITORY. This tree is public
# and the publisher figures are not redistributable, so ABSENT is now the normal
# state and exiting 2 on it would make every run red. What replaces the old
# check is stronger than it was, and it is two halves:
#
#   ABSENT  -> exit 0, and the output must NAME the raster it could not find.
#              A silent skip is still the dishonest answer.
#   WRONG   -> a raster that IS present and does not hash to the one the
#              coordinates were measured on must FAIL. That is the case the old
#              check could not reach at all, and it is the one that returns a
#              plausible number for the wrong picture.
#
# The absence is visible in the SCENARIO COUNTS as well: `test_bar_reader` runs
# 121 with the ID 323 raster and 97 without it, and `verify_documented_status`
# refuses a README that claims either number while the tree runs the other.
import tempfile                                                     # noqa: E402

ABSENT = os.path.join(HERE, "fixtures", "definitely_missing.png")
NOWHERE = os.path.join(tempfile.gettempdir(), "fdt_no_rasters_here")
_env = dict(os.environ)
_env["FDT_RASTER_ROOT"] = NOWHERE
for label, argv, raster in (
        ("forward_test_real_monochrome.py",
         ["forward_test_real_monochrome.py", ABSENT],
         "ID386_Fig2_publisher_898x1662.png"),
        ("forward_test_397_mono_bar.py",
         ["forward_test_397_mono_bar.py", ABSENT], "397_fig3.jpeg"),
        ("pilot_397.py",
         ["pilot_397.py", os.path.join(NOWHERE, "out"), NOWHERE],
         "397_fig1.jpeg")):
    argv = [os.path.join(HERE, argv[0])] + argv[1:]
    missing = subprocess.run([sys.executable] + argv, capture_output=True,
                             text=True, env=_env)
    out = missing.stdout + missing.stderr
    assert missing.returncode == 0, (
        "%s with a missing raster must SKIP (exit 0), got %d\n%s"
        % (label, missing.returncode, out))
    assert "SKIP" in out and raster in out, (
        "%s skipped without naming the raster it could not find\n%s"
        % (label, out))
    passed("a missing raster SKIPS %s, and says which one" % label)

# AND THE HALF THE OLD CHECK COULD NOT REACH.
_decoy = tempfile.mkdtemp(prefix="fdt_decoy_")
with open(os.path.join(_decoy, "397_fig3.jpeg"), "wb") as _fh:
    _fh.write(b"not the figure these coordinates were measured on")
_denv = dict(os.environ)
_denv["FDT_RASTER_ROOT"] = _decoy
_wrongrun = subprocess.run(
    [sys.executable, os.path.join(HERE, "forward_test_397_mono_bar.py")],
    capture_output=True, text=True, env=_denv)
assert _wrongrun.returncode != 0, (
    "a raster that is not the one the coordinates were measured on was "
    "MEASURED instead of refused\n%s%s"
    % (_wrongrun.stdout, _wrongrun.stderr))
passed("a raster whose hash does not match is refused, not measured")


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
    passed("partial attestation BLOCKS the pilot (%s)" % label)

# THE PILOT NEEDS ITS FIVE PUBLISHER RASTERS to reach an attestation at all, and
# this repository does not carry them. The BLOCK scenarios above do not - a
# partial attestation is refused before any figure is opened, which is the order
# this round had to fix - so only the sections that actually RUN the pilot are
# conditional. CI supplies the rasters through FDT_RASTER_ROOT and runs them.
import raster_root as _RR                                        # noqa: E402
_pilot_rasters = all(_RR.check("397_fig%d.jpeg" % n)[0] for n in range(1, 6))
if not _pilot_rasters:
    print(_RR.skip_note("397_fig1.jpeg"))
    print("  the pilot's ATTESTED / DEMO_ONLY / approval-gate scenarios need it")

if _pilot_rasters:
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
  passed("a full attestation runs as ATTESTED with the given dates")

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
  passed("no attestation runs as DEMO_ONLY with zero accepted")

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


# AND THIS SECTION READS WHAT THAT RUN WROTE, so it is gated by the same
# condition. It was not, and CI found it: the directory is a fixed path under
# /tmp, so a machine that had ever run the pilot WITH the figures kept one - and
# these two scenarios then passed against an output no run in that session had
# produced. On a clean runner the same code asserts a directory that does not
# exist. A scenario that reads a fixed temporary path can pass for a reason that
# has nothing to do with the tree it is testing.
att_dir = os.path.join(tempfile.gettempdir(), "fdt_attested")
if _pilot_rasters:
  assert not os.path.exists(os.path.join(att_dir, "figure_values_accepted.csv")), (
      "run_batch wrote an accepted file; only finalize_batch may")
  assert os.path.exists(os.path.join(att_dir, "figure_values_machine_qc.csv"))
  assert os.path.exists(os.path.join(att_dir, "review_queue.csv"))
  passed("run_batch stops at machine QC and writes a review queue")

  empty = sh(FIN, att_dir)
  assert empty.returncode == 1 and "NOTHING_APPROVED" in empty.stdout, empty.stdout
  assert not os.path.exists(os.path.join(att_dir, "figure_values_accepted.csv"))
  passed("an unreviewed run finalizes to nothing")


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
passed("the runner can describe its own environment")

# THE STAMP IS THE PILOT'S, so this one is gated too. The property - a run
# records what it ran on - is not about publisher figures, but the only run
# stamp this file has is the one the pilot wrote.
if _pilot_rasters:
  stamp = json.load(open(os.path.join(att_dir, "run_stamp.json")))
  assert stamp.get("Environment", {}).get("Python"), stamp
  assert stamp["Environment"]["Libraries"]["numpy"] == env["Libraries"]["numpy"], stamp
  passed("and every run stamp carries it")

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
passed("every shipped template matches its column function (%d)" % len(shipped))

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
passed("SKILL.md is standalone and states the run contract")

# CI must run every suite in the package. A test file nobody runs is a test
# file that will be broken the next time somebody looks.
CI = os.path.join(HERE, ".github", "workflows", "suite.yml")
assert os.path.exists(CI), "no CI workflow in the package"
ci_text = open(CI, encoding="utf-8").read()
suites = {os.path.basename(p)[:-3] for p in glob.glob(os.path.join(HERE, "test_*.py"))}
unrun = sorted(s for s in suites if s not in ci_text)
assert not unrun, "CI does not run: %s" % unrun
passed("CI runs every test file in the package (%d)" % len(suites))

# And every forward test, which the pattern above does not match. A forward test
# is the only thing in the package that opens a publisher figure, so one that
# nobody runs is exactly the one whose absence is least visible - the suites
# stay green either way. The ones whose raster is not redistributable SKIP in
# CI, which is a different outcome from not being there.
forwards = {os.path.basename(p)[:-3]
            for p in glob.glob(os.path.join(HERE, "forward_test_*.py"))}
unrun = sorted(s for s in forwards if s not in ci_text)
assert not unrun, "CI does not run the forward tests: %s" % unrun
passed("CI runs every forward test in the package (%d)" % len(forwards))

# And every worked example. These are the only things in the package that run
# the whole ladder on a real publication, so one that nobody runs is the one
# whose rot is least visible - a pilot that stopped finalizing would leave
# every suite green.
pilots = {os.path.basename(p)[:-3]
          for p in glob.glob(os.path.join(HERE, "pilot_*.py"))}
unrun = sorted(s for s in pilots if s not in ci_text)
assert not unrun, "CI does not run the worked examples: %s" % unrun
passed("CI runs every worked example in the package (%d)" % len(pilots))

# THE TWO STRINGS THE CI LOOP AND THE GUARD HAVE TO AGREE ON. A suite whose
# whole file is raster-gated reports 0, and a 0 is refused unless that run says
# the suite named a missing figure. The saying is a token printed by
# `raster_root.skip_note` and grepped by the workflow; the recording is a column
# value the workflow writes and `verify_documented_status` reads. Neither can be
# checked by running the guard - both live in a YAML file - so they are checked
# by comparing the literals with the constants they are copies of. Change either
# constant without the workflow and every raster-gated zero becomes a red CI run
# whose message is about a suite falling out of the loop.
import raster_root as _RRT                                          # noqa: E402
import verify_documented_status as _VDS                             # noqa: E402
assert _RRT.ABSENT_TOKEN in ci_text, (
    "the workflow does not look for raster_root.ABSENT_TOKEN (%s), so a suite "
    "that skips its whole file reports a bare 0" % _RRT.ABSENT_TOKEN)
assert _VDS.SKIPPED in ci_text, (
    "the workflow does not write %s, which is the column "
    "verify_documented_status reads" % _VDS.SKIPPED)
passed("the workflow, the skip note and the guard spell the same two tokens")

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
passed("no scenario is written so that it cannot fail (%d files)"
      % len(glob.glob(os.path.join(HERE, "test_*.py"))))

# --------------------------------------------------------------------------
# the worked example's cells are the cells the figure prints
# --------------------------------------------------------------------------
# v8.7. `id323_figure_values.csv` shipped `323|FIG2|DAP` as B-1, DI7, DI14, DI19,
# R1 with R5 absent. The figure prints six categories and DI19's mean is zero, so
# it draws an error bar and NO BAR - and `read_bar_panel`, given no declared
# slots, numbered what it found by sequence and filed the last two bars one
# timepoint early. `build_id323.py` now reads the printed categories and passes
# them, which moves exactly those two cells and nothing else.
#
# Pinned on the SHIPPED FILE, because that is what the defect was: reverting the
# wiring leaves every suite green - `build_id323.py` exits 0 either way - and the
# only durable evidence is which cells the artifact carries.
_v323 = list(csv.DictReader(open(os.path.join(HERE, "id323_figure_values.csv"),
                                 encoding="utf-8")))
_dap = [r["Cell_Key"] for r in _v323 if r["Unit_ID"] == "323|FIG2|DAP"]
assert _dap, "the worked example no longer carries 323|FIG2|DAP"
assert _dap == ["TIMEPOINT=B-1", "TIMEPOINT=DI7", "TIMEPOINT=DI14",
                "TIMEPOINT=R1", "TIMEPOINT=R5"], (
    "323|FIG2|DAP's hole belongs at DI19, whose bar is a mean of zero; got %s"
    % _dap)
passed("the worked example's zero-mean category is the one left absent")

# --------------------------------------------------------------------------
# one place says what the package runs today
# --------------------------------------------------------------------------
# `verify_documented_status.py` makes README's total agree with the measurement.
# Nothing made the REST of the package agree with README, so two files went on
# saying 2244/2282 for eleven releases while the tree ran 2900/2938 - stale in
# exactly the way the guard exists to prevent, one directory away from it.
#
# So: a shipped file may not state a package-wide scenario count unless it is
# the current one or it dates itself. README.md is the current-status line and
# is measured every CI run; INSTALL.md is a release history and its numbers are
# records on purpose; the suites are exempt because their paragraphs are full of
# fixture numbers, ORCIDs and dates, and a suite that drifts is caught by
# running it. Everything else either quotes today's number or cites the version
# its number belonged to.
import re                                                          # noqa: E402

_readme = open(os.path.join(HERE, "README.md"), encoding="utf-8").read()
_current = set(re.findall(r"<!-- CURRENT_SCENARIO_COUNT_\w+: (\d+) -->", _readme))
# THREE: the two profile totals a clone runs, and the raster-only count that
# separates a fork from CI. They are exempt from the sweep below because they
# are the current status and are measured every run; a fourth marker appearing
# here means a number was added that nothing measures.
assert len(_current) == 3, "README should carry three count markers: %s" % _current
_FOUR = re.compile(r"(?<![.\d])(\d{4})(?![.\d])")
_VERSION = re.compile(r"\bv\d+\.\d+\b")
_stale = []
for path in sorted(glob.glob(os.path.join(HERE, "*.py"))
                   + glob.glob(os.path.join(HERE, "*.md"))
                   + glob.glob(os.path.join(HERE, "*.txt"))
                   + glob.glob(os.path.join(HERE, ".github/workflows/*.yml"))):
    name = os.path.basename(path)
    if name in ("README.md", "INSTALL.md") or name.startswith(
            ("test_", "forward_test_")):
        continue
    # PARAGRAPHS, not lines. "the tree ran 2282 scenarios while the file said
    # 2184 after v7.43" is one dated sentence written over two lines, and a
    # line-by-line check would call its second half undated.
    for para in re.split(r"\n\s*\n", open(path, encoding="utf-8").read()):
        if not re.search(r"scenario", para, re.I) or _VERSION.search(para):
            continue
        for found in _FOUR.finditer(para):
            if found.group(1) not in _current:
                _stale.append("%s: %s" % (name, found.group(1)))
assert not _stale, ("a package total outside README.md that is neither current "
                    "nor dated: %s" % ", ".join(_stale))
passed("only README.md says what the package runs today")

# And the guard's own usage has to be the guard's own contract. Its docstring
# opened with a command line that predated `--profile` and named a marker
# (`CURRENT_SCENARIO_COUNT`) the code has not looked for since the split, so the
# one file whose job is documentation drift was carrying two years of it.
import verify_documented_status as V_DOC                           # noqa: E402

_usage = V_DOC.__doc__ or ""
# THE INVOCATION LINE, not the docstring. `--profile` is explained further down
# either way, so `"--profile" in doc` is true whatever the command line at the
# top says - a guard that cannot fail, which the first draft of this check was.
_call = _usage.split("python3 verify_documented_status.py", 1)
assert len(_call) == 2, "the docstring shows no invocation"
assert "--profile" in _call[1][:120], (
    "the invocation the docstring shows does not pass --profile: %r"
    % _call[1][:120].strip())
# AND THE SECOND ENVIRONMENT ARGUMENT, for the same reason the first is here.
# `--rasters` decides which of two totals this run is judged against, so an
# invocation line that omits it teaches the reader the wrong command.
assert "--rasters" in _call[1][:120], (
    "the invocation the docstring shows does not pass --rasters: %r"
    % _call[1][:120].strip())
_named = set(re.findall(r"CURRENT_SCENARIO_COUNT_?\w*", _usage))
# The markers the code actually reads, read OFF the code: the per-profile ones
# it builds by name and the raster-only one it holds as a pattern.
_real = {"CURRENT_SCENARIO_COUNT_%s" % p.upper() for p in V_DOC.PROFILES}
_real |= set(re.findall(r"CURRENT_SCENARIO_COUNT_?\w*",
                        V_DOC.RASTER_MARKER.pattern))
_ghosts = sorted(n for n in _named if n not in _real)
assert not _ghosts, ("the docstring names markers the code does not read: %s"
                     % ", ".join(_ghosts))
assert _named, "the docstring names no marker at all"
passed("the documentation guard's usage is the contract it enforces")

# One line, one format, for the CI guard that checks the documented
# scenario count against the measured one.
print("FDT_SCENARIOS_RUN=%d" % _PASSES[0])
