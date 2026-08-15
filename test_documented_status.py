"""What the documentation guard refuses, pinned so it cannot quietly stop.

    python3 test_documented_status.py     # exit 0 = all scenarios pass

`verify_documented_status.py` runs once per CI job, against a tree that agrees
with itself. That proves it does not FALSELY fail; it proves nothing about
whether it still fails when it should. Delete any one of its checks and, as
long as the repository happens to be consistent, CI stays green - which is the
fail-open shape this package refuses everywhere else.

So every refusal is a scenario here, against synthetic fixtures rather than the
real README: a guard tested only against the tree it guards can be satisfied by
editing the tree.

The five that were verified by hand when the guard was written are the first
five below. The rest are the ones hand-verification does not reach.
"""
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import verify_documented_status as V                             # noqa: E402

FAILURES, PASSED = [], [0]


def check(name, ok, detail=""):
    print(("  ok   " if ok else "  FAIL ") + name + ("" if ok else "  <- " + detail))
    if ok:
        PASSED[0] += 1
    else:
        FAILURES.append(name)


ROOT = tempfile.mkdtemp(prefix="fdt_docstatus_")
SUITES = {"test_alpha.py": 100, "test_beta.py": 44}
VERSION = "9.9"


def package(counts=None, readme=None, version=VERSION, suites=None,
            directory=None):
    """A miniature package: some suites, a README, a runner, a counts file."""
    directory = directory or tempfile.mkdtemp(prefix="pkg_", dir=ROOT)
    for name in (suites if suites is not None else SUITES):
        open(os.path.join(directory, name), "w", encoding="utf-8").write("print(1)\n")
    open(os.path.join(directory, "run_batch.py"), "w", encoding="utf-8").write(
        '"""A docstring mentioning PIPELINE_VERSION = "0.1" that must not count."""\n'
        '# PIPELINE_VERSION = "0.2" in a comment must not count either\n'
        'PIPELINE_VERSION = "%s"\n' % version)
    counts = SUITES if counts is None else counts
    with open(os.path.join(directory, "counts.tsv"), "w", encoding="utf-8") as fh:
        for suite, number in counts.items():
            fh.write("%s\t%s\n" % (suite, number))
    total = sum(int(v) for v in counts.values() if str(v).isdigit())
    open(os.path.join(directory, "README.md"), "w", encoding="utf-8").write(
        readme if readme is not None else default_readme(total, total + 38, version))
    return directory


def default_readme(core, full, version=VERSION):
    return ("# pkg\n\n"
            "<!-- CURRENT_PIPELINE_VERSION: %s -->\n"
            "<!-- CURRENT_SCENARIO_COUNT_CORE: %d -->\n"
            "<!-- CURRENT_SCENARIO_COUNT_FULL: %d -->\n\n"
            "%d scenarios on main after v%s under `requirements-lock.txt`, and "
            "%d with the intake backends.\n" % (version, core, full, core,
                                                version, full))


def run(directory, profile="core"):
    return V.main(["--profile", profile,
                   os.path.join(directory, "counts.tsv"),
                   os.path.join(directory, "README.md"),
                   os.path.join(directory, "run_batch.py")])


def refuses(name, **kw):
    """The guard must return non-zero for this package."""
    profile = kw.pop("profile", "core")
    directory = package(**kw)
    check(name, run(directory, profile) == 1)


print("a tree that agrees with itself passes, in both profiles")
# The same README, checked twice against two different counts files - which is
# what the two CI jobs do.
_CORE_TOTAL, _FULL_TOTAL = 144, 182
_README = default_readme(_CORE_TOTAL, _FULL_TOTAL)
_core = package(counts={"test_alpha.py": 100, "test_beta.py": 44}, readme=_README)
_full = package(counts={"test_alpha.py": 138, "test_beta.py": 44}, readme=_README)
check("the core environment against the core marker", run(_core, "core") == 0)
check("the full environment against the full marker", run(_full, "full") == 0)
# THE POINT OF TWO PROFILES. Before they existed a correct run in a full
# environment printed "this is not a defect" and then exited 1, and a guard
# that calls a healthy tree broken is one people learn to run with `|| true`.
check("and the full environment is NOT judged against the core marker",
      run(_full, "core") == 1)
check("nor the core environment against the full one",
      run(_core, "full") == 1)

print()
print("the five that were checked by hand when the guard was written")
refuses("a marker one too high",
        readme=default_readme(145, 182))
refuses("the prose left behind when the marker moved",
        readme=default_readme(144, 182).replace("144 scenarios", "999 scenarios"))
refuses("the version bumped in the code and not in the documentation",
        version="9.9", readme=default_readme(144, 182, "9.8"))
refuses("a suite dropped out of the counts file",
        counts={"test_alpha.py": 100})
refuses("a suite in the counts file that the package does not contain",
        counts=dict(SUITES, test_ghost=1))

print()
print("and the ones hand-verification does not reach")
refuses("a suite that reported zero scenarios",
        counts={"test_alpha.py": 144, "test_beta.py": 0})
refuses("a count marker that is missing",
        readme=default_readme(144, 182).replace(
            "<!-- CURRENT_SCENARIO_COUNT_CORE: 144 -->\n", ""))
refuses("a count marker that appears twice",
        readme=default_readme(144, 182).replace(
            "<!-- CURRENT_SCENARIO_COUNT_CORE: 144 -->",
            "<!-- CURRENT_SCENARIO_COUNT_CORE: 144 -->\n"
            "<!-- CURRENT_SCENARIO_COUNT_CORE: 144 -->"))
refuses("a version marker that is missing",
        readme=default_readme(144, 182).replace(
            "<!-- CURRENT_PIPELINE_VERSION: 9.9 -->\n", ""))
refuses("a status sentence that is missing",
        readme="# pkg\n\n<!-- CURRENT_PIPELINE_VERSION: 9.9 -->\n"
               "<!-- CURRENT_SCENARIO_COUNT_CORE: 144 -->\n"
               "<!-- CURRENT_SCENARIO_COUNT_FULL: 182 -->\n")
refuses("two status sentences, so nobody can say which is the status",
        readme=default_readme(144, 182)
        + "\n144 scenarios on main after v9.9 under `requirements-lock.txt`.\n")
refuses("a status sentence naming a version the runner does not",
        readme=default_readme(144, 182).replace("after v9.9", "after v9.8"))

print()
print("the counts file has to be a counts file")
for _name, _line in (("a row with no count", "test_alpha.py\n"),
                     ("a count that is not a number", "test_alpha.py\tabc\n"),
                     ("a suite reported twice",
                      "test_alpha.py\t100\ntest_alpha.py\t44\n")):
    _dir = tempfile.mkdtemp(prefix="tsv_", dir=ROOT)
    package(directory=_dir)
    open(os.path.join(_dir, "counts.tsv"), "w", encoding="utf-8").write(_line)
    try:
        _rc = run(_dir)
        _ok = _rc != 0
    except SystemExit:
        _ok = True                      # read_counts refuses by raising
    check(_name + " is refused", _ok)

print()
print("the version is what the code ASSIGNS, not what it mentions")
# REVERT: read PIPELINE_VERSION with a regex. The fixture's docstring and
# comment both carry a different version on purpose; a regex over the file
# picks one of them and the check passes against a number nobody assigned.
_v = package()
check("a version in a docstring or a comment does not satisfy the check",
      V.pipeline_version(os.path.join(_v, "run_batch.py")) == VERSION,
      V.pipeline_version(os.path.join(_v, "run_batch.py")))
_nonliteral = tempfile.mkdtemp(prefix="nonlit_", dir=ROOT)
package(directory=_nonliteral)
open(os.path.join(_nonliteral, "run_batch.py"), "w", encoding="utf-8").write(
    'import os\nPIPELINE_VERSION = os.environ.get("V", "9.9")\n')
try:
    V.pipeline_version(os.path.join(_nonliteral, "run_batch.py"))
    _ok = False
except SystemExit:
    _ok = True
check("a version computed at runtime is refused rather than guessed", _ok)
_absent = tempfile.mkdtemp(prefix="absent_", dir=ROOT)
package(directory=_absent)
open(os.path.join(_absent, "run_batch.py"), "w", encoding="utf-8").write("X = 1\n")
try:
    V.pipeline_version(os.path.join(_absent, "run_batch.py"))
    _ok = False
except SystemExit:
    _ok = True
check("and a file with no PIPELINE_VERSION at all is refused", _ok)

print()
print("the profile is a declaration, not a default that hides a mistake")
check("an unknown profile is refused rather than treated as core",
      run(_core, "workstation") == 2)
check("and the two profiles are the two CI jobs",
      V.PROFILES == ("core", "full"), "%r" % (V.PROFILES,))

print()
print("the runbook names commands and flags this package actually has")
# PILOT.md is the procedure a person follows, and a procedure that names a flag
# nothing accepts is worse than none: the reviewer runs it, gets an error, and
# improvises - which is the one thing the file exists to prevent. Every command
# line in it is parsed against the real parsers.
import re as _re                                                   # noqa: E402
import finalize_batch as _FIN                                      # noqa: E402
import review_preflight as _PF                                     # noqa: E402
import run_batch as _RB                                            # noqa: E402

_PILOT = os.path.join(HERE, "PILOT.md")
check("the runbook is in the package", os.path.exists(_PILOT))
_lines = [l.strip() for l in open(_PILOT, encoding="utf-8").read().splitlines()
          if l.strip().startswith("python3 ")]
_lines += [l.strip() for l in open(_PILOT, encoding="utf-8").read().splitlines()
           if _re.match(r"^\s+\d+\s+python3 ", l)]
_lines = [_re.sub(r"^\d+\s+", "", l) for l in _lines]
check("  and it gives a command for every step of the review",
      len(_lines) >= 5, "%s" % _lines)
_MODULES = {"run_batch.py": _RB, "review_preflight.py": _PF,
            "finalize_batch.py": _FIN}
_unknown = []
for _line in _lines:
    _parts = _line.split()
    _module = _MODULES.get(_parts[1])
    if _module is None:
        _unknown.append(_parts[1])
        continue
    _flags = {p for p in _parts[2:] if p.startswith("--")}
    _src = open(os.path.join(HERE, _parts[1]), encoding="utf-8").read()
    for _flag in _flags:
        if 'add_argument("%s"' % _flag not in _src:
            _unknown.append("%s %s" % (_parts[1], _flag))
check("  and every flag it names is one that module accepts",
      not _unknown, "%s" % _unknown)
# AND THE FILES IT TELLS A REVIEWER TO OPEN are the ones the run writes.
_named = set(_re.findall(r'`?(OUT/[A-Za-z0-9_./<>-]+)`?', open(_PILOT).read()))
_writes = set(_RB.CANONICAL_DIRS) | set(_RB.CANONICAL_OUTPUTS) | {
    "value_review.csv", "inference_review.csv", "figure_values_accepted.csv"}
_missing = [n for n in _named
            if n.split("/")[1].split("<")[0].rstrip("_")
            not in {w.split("/")[0].rstrip("/") for w in _writes}
            and n.split("/")[1] not in _writes]
check("  and every file it tells a reviewer to open is one the run writes",
      not _missing, "%s / writes %s" % (sorted(_missing), sorted(_writes)))

shutil.rmtree(ROOT, ignore_errors=True)
print()
# One line, one format, for the CI guard that checks the documented
# scenario count against the measured one.
print("FDT_SCENARIOS_RUN=%d" % (PASSED[0] + len(FAILURES)))
print("%d scenarios run" % (PASSED[0] + len(FAILURES)))
if FAILURES:
    print("%d FAILED: %s" % (len(FAILURES), FAILURES))
    raise SystemExit(1)
print("all scenarios passed")
