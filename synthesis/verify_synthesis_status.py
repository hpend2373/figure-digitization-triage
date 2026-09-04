# -*- coding: utf-8 -*-
"""The synthesis suites are counted the way the main suites are counted.

    python3 verify_synthesis_status.py     # exit 0 = the tree matches its README

WHY THIS EXISTS. The workflow ran these suites and grepped their last line for
`all scenarios passed`. That catches a suite that fails. It does not catch a
suite that VANISHES: drop a file from the CI loop, or add a test nobody
registers, and nothing anywhere changes - no total falls, no marker disagrees,
and the loop keeps printing success for the suites that remain. The main
package solved this once with `scenario-counts.tsv` and a README marker; this
is the same rule for the second pipeline, which otherwise repeats a failure the
first one already paid for.

Three things, and the file-set check is the one the grep could never do:

  every test file here is classified          a new `test_*.py` that is neither
                                              declared CI-runnable nor declared
                                              bundle-dependent fails, so it
                                              cannot be added and forgotten.

  each CI suite prints exactly one count      and a count of zero is a failure,
                                              not a pass; a suite that runs
                                              nothing must not look like a
                                              suite that runs everything.

  the total matches the README                so the number cannot move on its
                                              own, in either direction.
"""
import ast
import builtins
import glob
import io
import os
import re
import subprocess
import tempfile
import sys

HERE = os.path.dirname(os.path.abspath(__file__))

#: Suites that read no files and so can run anywhere, including CI.
CI_SUITES = ("test_route_gate", "test_rowkey", "test_write_cycle",
             "test_xlsx_cycle", "test_status_gate")
#: Suites that need the extraction bundle, which is not redistributable. They
#: are declared, not run: an undeclared file is the failure this catches.
BUNDLE_SUITES = ("test_readiness_gate",)

MARKER = re.compile(
    r"<!--\s*CURRENT_SYNTHESIS_SCENARIO_COUNT:\s*([0-9]+)\s*-->")
#: PER SUITE, NOT ONLY THE TOTAL. The README table carried a count per suite in
#: prose, which nothing checked: scenarios were added to two suites and the
#: three cells still read 18 / 63 / 66 while the checked total said 171. A
#: number no one verifies is a number that drifts, so the per-suite counts are
#: a marker too, and the prose no longer carries any.
SUITE_MARKER = re.compile(
    r"<!--\s*SYNTHESIS_SUITE_COUNT:\s*([A-Za-z0-9_]+)\s+([0-9]+)\s*-->")
COUNT = re.compile(r"^FDT_SCENARIOS_RUN=([0-9]+)$", re.M)


def _modules(where, pattern="*.py"):
    """Files here that `import` could actually reach.

    A stem with a space in it is not an identifier, so no statement anywhere
    can name it. This tree syncs through a service that resolves a collision
    by writing `test_route_gate 2.py` beside the original; none of those are
    in the repository, and the file-set check below counted them as suites
    nobody declared - which made the gate fail on a clean checkout that
    happened to be sitting in a synced folder, and a gate that cannot pass
    locally is a gate nobody runs locally.

    The rule is not "ignore that sync tool", which would be a fact about one
    laptop rather than about the code. It is that an unimportable name cannot
    be a module of this package on any machine.
    """
    return [p for p in sorted(glob.glob(os.path.join(where, pattern)))
            if os.path.splitext(os.path.basename(p))[0].isidentifier()]


def _short_circuits(tree):
    """Truth literals that make the expression around them unfalsifiable."""
    for node in ast.walk(tree):
        if isinstance(node, ast.BoolOp):
            wants = isinstance(node.op, ast.Or)
            for value in node.values:
                if isinstance(value, ast.Constant) and bool(value.value) is wants:
                    yield node.lineno


def vacuous_scenarios():
    """Scenarios whose condition cannot fail, in this directory's suites.

    THE MAIN PACKAGE HAS HAD THIS CHECK FOR A WHILE and it scans only the root
    `test_*.py`. These suites sit one directory down, so an `... or True`
    written here was invisible to it - and one was, in the very commit whose
    message says a scenario that cannot fail is not a scenario. A rule that
    only covers the files someone remembered is not the rule.

    Parsed, not grepped: a line search misses `condition or\n True`,
    `condition or (True)` and `x or 1`. Only the CONDITION of a scenario is
    examined, because `x or "fallback"` in a detail string is the ordinary
    idiom for a default and says nothing about whether the scenario can fail.
    """
    out = []
    for path in _modules(HERE, 'test_*.py'):
        tree = ast.parse(io.open(path, encoding='utf-8').read(), path)
        for node in ast.walk(tree):
            tested = []
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                    and node.func.id == 'check' and len(node.args) >= 2):
                tested = [node.args[1]]
            elif isinstance(node, ast.Assert):
                tested = [node.test]
            for expression in tested:
                # A BARE CONSTANT IS THE SAME DEFECT WITHOUT THE `or`.
                # `check("...", True)` is not a BoolOp and slipped through the
                # first version of this scan - written, of course, in the
                # commit that added the scan.
                if isinstance(expression, ast.Constant):
                    out.append('%s:%d' % (os.path.basename(path),
                                          expression.lineno))
                for line in _short_circuits(expression):
                    out.append('%s:%d' % (os.path.basename(path), line))
    return out


#: Names that exist without any binding in the file. Kept beside the module so
#: a scenario can name it, and so this list is one place, not two.
_ALWAYS_BOUND = frozenset(dir(builtins)) | frozenset((
    "__file__", "__name__", "__doc__", "__spec__", "__package__",
    "__loader__", "__builtins__"))


def _binds(tree):
    """Every name this module binds, in ANY scope.

    DELIBERATELY OVER-APPROXIMATE. A name bound inside one function counts as
    bound for the whole file, which means real scope errors pass. That is the
    trade this check makes on purpose: the question it answers is only "was
    this name ever obtained at all", which is exactly the shape of a missing
    import, and answering only that keeps the false-positive count at zero. A
    checker people learn to skim past is not a checker.
    """
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add((alias.asname or alias.name).split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                names.add(alias.asname or alias.name)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef,
                               ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, ast.Name) and isinstance(node.ctx,
                                                       (ast.Store, ast.Del)):
            names.add(node.id)
        elif isinstance(node, ast.arg):
            names.add(node.arg)
        elif isinstance(node, ast.ExceptHandler) and node.name:
            names.add(node.name)
        elif isinstance(node, (ast.Global, ast.Nonlocal)):
            names.update(node.names)
    return names


def unbound_names(where=HERE):
    """Names read but never bound, across EVERY module here - not only tests.

    WHAT THIS CAUGHT. `build_packets.py` called `sys.path.insert` on its
    nineteenth line and never imported `sys`; `widen_and_recompute.py` did the
    same on its twenty-ninth. Both are grammatically perfect, so `py_compile`
    accepts them and the NameError waits for import time. Neither is a
    `test_*.py`, so every check in this file looked straight past them, and
    neither runs in CI - the packet builder had been dead for as long as
    anybody had not run it by hand.

    So this one scans `*.py`, not `test_*.py`. The scenario-count checks above
    can only see the suites; the defect that motivated them - a thing silently
    not running - lives just as comfortably in the scripts the suites do not
    import. A gate that only inspects the files someone remembered to register
    reproduces the failure it was built to stop.

    A file that cannot be read or parsed is REPORTED, not skipped: on this
    tree a cloud-evicted file raises OSError on open, and a scan that treats
    "could not look" as "nothing wrong" is the same silence in a new place.
    """
    out = []
    for path in _modules(where):
        name = os.path.basename(path)
        try:
            tree = ast.parse(io.open(path, encoding="utf-8").read(), path)
        except SyntaxError as exc:
            out.append("%s:%s does not parse (%s)" % (name, exc.lineno, exc.msg))
            continue
        except (OSError, UnicodeDecodeError) as exc:
            out.append("%s could not be read (%s)" % (name, exc))
            continue
        have, seen = _binds(tree) | _ALWAYS_BOUND, set()
        for node in ast.walk(tree):
            if (isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load)
                    and node.id not in have and node.id not in seen):
                seen.add(node.id)
                out.append("%s:%d uses %s and never binds it"
                           % (name, node.lineno, node.id))
    return out


def main():
    problems, total, measured = [], 0, {}

    for where in vacuous_scenarios():
        problems.append('%s is a scenario whose condition cannot fail' % where)

    problems.extend(unbound_names())

    found = sorted(os.path.splitext(os.path.basename(p))[0]
                   for p in _modules(HERE, "test_*.py"))
    declared = sorted(CI_SUITES + BUNDLE_SUITES)
    if found != declared:
        problems.append(
            "the test files here are %s and the declared suites are %s; a "
            "suite that is neither run in CI nor declared bundle-dependent is "
            "a suite nobody counts" % (found, declared))

    pycache_prefix = tempfile.mkdtemp(prefix="fdt-pyc-")
    for name in CI_SUITES:
        path = os.path.join(HERE, name + ".py")
        if not os.path.exists(path):
            problems.append("%s is declared CI-runnable and is not here" % name)
            continue
        # A SUITE MUST BE RUN FROM ITS SOURCE, NOT FROM A CACHE. The tree
        # lives on a mount whose mtime does not always move when a file's
        # contents do, and Python trusts mtime and size to decide whether a
        # __pycache__ entry is current. A stale entry there made a suite
        # report failures its source does not have - and would just as
        # readily hide failures its source does have. Compiling into a
        # throwaway prefix means what runs is what is on disk.
        env = dict(os.environ)
        env["PYTHONPYCACHEPREFIX"] = pycache_prefix
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        run = subprocess.run([sys.executable, path], cwd=HERE,
                             capture_output=True, text=True, env=env)
        if run.returncode != 0:
            problems.append("%s exited %d" % (name, run.returncode))
            continue
        counts = COUNT.findall(run.stdout or "")
        if len(counts) != 1:
            problems.append("%s printed %d FDT_SCENARIOS_RUN lines; it must "
                            "print exactly one" % (name, len(counts)))
            continue
        if int(counts[0]) == 0:
            problems.append("%s ran 0 scenarios; a suite that runs nothing "
                            "must not read as a suite that passed" % name)
            continue
        if "all scenarios passed" not in (run.stdout or ""):
            problems.append("%s did not print its verdict" % name)
            continue
        measured[name] = int(counts[0])
        total += int(counts[0])
        print("    %-22s %4d" % (name + ".py", int(counts[0])))

    readme = open(os.path.join(HERE, "README.md"), encoding="utf-8").read()
    per_suite = dict((n, int(c)) for n, c in SUITE_MARKER.findall(readme))
    if per_suite != measured:
        problems.append(
            "synthesis/README.md's per-suite markers are %s and the suites "
            "reported %s"
            % (sorted(per_suite.items()), sorted(measured.items())))
    said = MARKER.findall(readme)
    if len(said) != 1:
        problems.append("synthesis/README.md carries %d "
                        "CURRENT_SYNTHESIS_SCENARIO_COUNT marker(s); it needs "
                        "exactly one" % len(said))
    elif int(said[0]) != total:
        problems.append("synthesis/README.md says %s scenarios and the suites "
                        "reported %d" % (said[0], total))

    if problems:
        print("SYNTHESIS STATUS DOES NOT MATCH THE TREE")
        for p in problems:
            print("  - %s" % p)
        print()
        print("what synthesis/README.md should carry:")
        for name in CI_SUITES:
            if name in measured:
                print("    <!-- SYNTHESIS_SUITE_COUNT: %s %d -->"
                      % (name, measured[name]))
        print("    <!-- CURRENT_SYNTHESIS_SCENARIO_COUNT: %d -->" % total)
        raise SystemExit(1)
    print("synthesis status matches the tree: %d scenarios across %d suites, "
          "%d more declared bundle-dependent"
          % (total, len(CI_SUITES), len(BUNDLE_SUITES)))


if __name__ == "__main__":
    main()
