"""The documented status is the measured status, or CI is red.

    python3 verify_documented_status.py COUNTS.tsv README.md run_batch.py

Every commit that adds a scenario moves the suite total, and the number in
`README.md` followed by hand. It was wrong: the tree ran 2282 scenarios while
the file said "2184 scenarios on main after v7.43". A status line nobody can
trust is worse than no status line, because a reader takes it as the state of
the package - and the reader most likely to take it that way is the next person
deciding whether this thing can be pointed at a corpus.

Three things have to agree:

    the SUM of what the suites reported this run
    <!-- CURRENT_SCENARIO_COUNT: N -->     in README.md
    the sentence a person reads in README.md

and separately:

    run_batch.PIPELINE_VERSION
    <!-- CURRENT_PIPELINE_VERSION: X.Y --> in README.md
    the same sentence

## Why markers, and why only on one line

`INSTALL.md` is a release history. The version numbers and scenario counts in
it are records of what was true at the time, kept deliberately, and a
repository-wide replace would rewrite the history to match today. The markers
give the machine a handle on the CURRENT-status line and nothing else.

## Why the file set is checked

It is the check that matters most, and the one that is easy to leave out.
Without it the honest failure - somebody drops a suite out of the CI loop -
reads as "the total went down, update the marker", and the guard helps you
lower it. A suite that reports zero is refused for the same reason: a suite
that runs nothing passes.

## The count is a property of the tree AND the environment

`test_corpus_intake` SKIPs its PDF-adapter, per-status, renderer and crop
sections when no PDF backend is installed, so the same tree runs 149 of those
scenarios on a workstation with pdfminer and poppler and 111 under
`requirements-lock.txt`. 2282 against 2244 for the whole package.

The documented number is **the locked environment's**, because that is the one
a reader can reproduce: `requirements-lock.txt` is what the shipped results
were produced on. Running this verifier on a box with the optional backends
installed will report MORE than the marker, and that is not a defect in either
- it is why the failure message says so.

## Why the version is read by AST

The same way `test_compile_plan` reads the plan contract. A number in a
docstring or a comment must not be able to satisfy a check about what the code
assigns.
"""
import ast
import glob
import os
import re
import sys

MARKERS = {
    "count": re.compile(r"<!--\s*CURRENT_SCENARIO_COUNT:\s*([0-9]+)\s*-->"),
    "version": re.compile(r"<!--\s*CURRENT_PIPELINE_VERSION:\s*([0-9][0-9.]*)\s*-->"),
}
#: The line a person reads. Both numbers have to be in it, so the marker cannot
#: be updated on its own and leave the prose behind - which is the same defect
#: this file exists to catch, one level down.
STATUS_LINE = re.compile(
    r"([0-9]{3,6})\s+scenarios\s+on\s+main\s+after\s+v([0-9][0-9.]*)")


def read_counts(path):
    """{suite: count} from the TSV the CI loop appended to."""
    out = {}
    with open(path, encoding="utf-8") as fh:
        for number, line in enumerate(fh, 1):
            line = line.rstrip("\n")
            if not line.strip():
                continue
            parts = line.split("\t")
            if len(parts) != 2 or not parts[1].isdigit():
                raise SystemExit("%s:%d is not SUITE<TAB>COUNT: %r"
                                 % (path, number, line))
            if parts[0] in out:
                raise SystemExit("%s:%d reports %s twice" % (path, number, parts[0]))
            out[parts[0]] = int(parts[1])
    return out


def pipeline_version(path):
    """PIPELINE_VERSION as the module assigns it, read without importing."""
    tree = ast.parse(open(path, encoding="utf-8").read(), path)
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id == "PIPELINE_VERSION":
                if not isinstance(node.value, ast.Constant) \
                        or not isinstance(node.value.value, str):
                    raise SystemExit("%s: PIPELINE_VERSION is not a literal "
                                     "string, so nothing here can read it" % path)
                return node.value.value
    raise SystemExit("%s: no PIPELINE_VERSION assignment at module level" % path)


def problems_with(counts, readme, version, package_dir):
    """Everything wrong, as sentences. Empty means the documentation is true."""
    out = []
    total = sum(counts.values())

    present = {os.path.basename(p) for p in
               glob.glob(os.path.join(package_dir, "test_*.py"))}
    missing = sorted(present - set(counts))
    extra = sorted(set(counts) - present)
    if missing:
        out.append("%d suite(s) in the package reported no count: %s. A suite "
                   "that drops out of the CI loop lowers the total, and without "
                   "this check the fix looks like editing the marker downwards"
                   % (len(missing), ", ".join(missing)))
    if extra:
        out.append("the counts file names %d file(s) that are not in the "
                   "package: %s" % (len(extra), ", ".join(extra)))
    zero = sorted(s for s, n in counts.items() if n == 0)
    if zero:
        out.append("%s reported 0 scenarios. A suite that runs nothing passes; "
                   "that is what this catches" % ", ".join(zero))

    found = {}
    for name, pattern in MARKERS.items():
        hits = pattern.findall(readme)
        if len(hits) != 1:
            out.append("README carries %d CURRENT_%s marker(s); it needs "
                       "exactly one" % (len(hits), name.upper()))
        else:
            found[name] = hits[0]

    if "count" in found and int(found["count"]) != total:
        # Which direction it missed by is the diagnosis. More than documented
        # is almost always optional backends installed locally; fewer is a
        # suite that lost scenarios.
        why = ("" if total >= int(found["count"]) else
               " - a suite has lost scenarios, or ran in an environment that "
               "SKIPs more than the locked one")
        if total > int(found["count"]):
            why = (" - this environment runs MORE than the locked one. "
                   "test_corpus_intake SKIPs its PDF sections without a "
                   "backend, so a workstation with pdfminer and poppler "
                   "installed is expected to exceed the documented number; "
                   "the marker records what requirements-lock.txt runs")
        out.append("README says CURRENT_SCENARIO_COUNT: %s and the suites "
                   "reported %d%s" % (found["count"], total, why))
    if "version" in found and found["version"] != version:
        out.append("README says CURRENT_PIPELINE_VERSION: %s and the runner "
                   "says %s" % (found["version"], version))

    sentences = STATUS_LINE.findall(readme)
    if len(sentences) != 1:
        out.append("README carries %d current-status sentence(s) matching "
                   "'<N> scenarios on main after v<X>'; it needs exactly one"
                   % len(sentences))
    else:
        said_count, said_version = sentences[0]
        if int(said_count) != total or said_version != version:
            out.append("the status sentence reads %s scenarios / v%s and the "
                       "tree is %d / v%s. Updating the marker and leaving the "
                       "prose behind is the same defect one level down"
                       % (said_count, said_version, total, version))
    return out


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if len(argv) != 3:
        print("usage: verify_documented_status.py COUNTS.tsv README.md run_batch.py")
        return 2
    counts_path, readme_path, source_path = argv
    package_dir = os.path.dirname(os.path.abspath(readme_path)) or "."

    counts = read_counts(counts_path)
    readme = open(readme_path, encoding="utf-8").read()
    version = pipeline_version(source_path)
    total = sum(counts.values())
    problems = problems_with(counts, readme, version, package_dir)

    if problems:
        print("DOCUMENTED STATUS DOES NOT MATCH THE TREE")
        for problem in problems:
            print("  - %s" % problem)
        print()
        print("what README should carry:")
        print("    <!-- CURRENT_PIPELINE_VERSION: %s -->" % version)
        print("    <!-- CURRENT_SCENARIO_COUNT: %d -->" % total)
        print("    ... %d scenarios on main after v%s ..." % (total, version))
        print()
        print("what each suite reported:")
        for suite in sorted(counts):
            print("    %-30s %5d" % (suite, counts[suite]))
        return 1

    print("documented status matches the tree: %d scenarios across %d suites, "
          "pipeline v%s" % (total, len(counts), version))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
