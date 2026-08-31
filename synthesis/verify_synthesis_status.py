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
import glob
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))

#: Suites that read no files and so can run anywhere, including CI.
CI_SUITES = ("test_route_gate", "test_rowkey", "test_write_cycle")
#: Suites that need the extraction bundle, which is not redistributable. They
#: are declared, not run: an undeclared file is the failure this catches.
BUNDLE_SUITES = ("test_readiness_gate",)

MARKER = re.compile(
    r"<!--\s*CURRENT_SYNTHESIS_SCENARIO_COUNT:\s*([0-9]+)\s*-->")
COUNT = re.compile(r"^FDT_SCENARIOS_RUN=([0-9]+)$", re.M)


def main():
    problems, total = [], 0

    found = sorted(os.path.splitext(os.path.basename(p))[0]
                   for p in glob.glob(os.path.join(HERE, "test_*.py")))
    declared = sorted(CI_SUITES + BUNDLE_SUITES)
    if found != declared:
        problems.append(
            "the test files here are %s and the declared suites are %s; a "
            "suite that is neither run in CI nor declared bundle-dependent is "
            "a suite nobody counts" % (found, declared))

    for name in CI_SUITES:
        path = os.path.join(HERE, name + ".py")
        if not os.path.exists(path):
            problems.append("%s is declared CI-runnable and is not here" % name)
            continue
        run = subprocess.run([sys.executable, path], cwd=HERE,
                             capture_output=True, text=True)
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
        total += int(counts[0])
        print("    %-22s %4d" % (name + ".py", int(counts[0])))

    readme = open(os.path.join(HERE, "README.md"), encoding="utf-8").read()
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
        print("    <!-- CURRENT_SYNTHESIS_SCENARIO_COUNT: %d -->" % total)
        raise SystemExit(1)
    print("synthesis status matches the tree: %d scenarios across %d suites, "
          "%d more declared bundle-dependent"
          % (total, len(CI_SUITES), len(BUNDLE_SUITES)))


if __name__ == "__main__":
    main()
