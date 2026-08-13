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

## The count is a property of the tree AND the environment, so there are two

`test_corpus_intake` SKIPs its PDF-adapter, per-status, renderer and crop
sections when no PDF backend is installed: 111 scenarios without, 149 with.
2244 against 2282 for the package.

The first version of this file documented one number and explained the other in
prose, which left a real contradiction: a correct run in a full environment
printed "this is not a defect" and then exited 1. A guard that calls a healthy
tree broken is a guard people learn to run with `|| true`.

So the environment is an ARGUMENT, and each profile has its own marker:

    --profile core   <!-- CURRENT_SCENARIO_COUNT_CORE: N -->   lock file only
    --profile full   <!-- CURRENT_SCENARIO_COUNT_FULL: N -->   + intake backends

CI runs both, in two jobs that install what their profile names rather than
inheriting it. `core` REMOVES poppler-utils and the two Python backends before
it starts: a count that depends on what the runner image happens to ship is not
a property of this repository, and `ubuntu-latest` adding poppler would
otherwise turn main red with no commit behind it.

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

PROFILES = ("core", "full")

VERSION_MARKER = re.compile(
    r"<!--\s*CURRENT_PIPELINE_VERSION:\s*([0-9][0-9.]*)\s*-->")


def count_marker(profile):
    return re.compile(r"<!--\s*CURRENT_SCENARIO_COUNT_%s:\s*([0-9]+)\s*-->"
                      % profile.upper())


#: The line a person reads, one per profile. Both numbers have to be in it, so
#: a marker cannot be updated on its own and leave the prose behind - which is
#: the same defect this file exists to catch, one level down.
STATUS_LINE = {
    "core": re.compile(r"([0-9]{3,6})\s+scenarios\s+on\s+main\s+after\s+"
                       r"v([0-9][0-9.]*)\s+under\s+`requirements-lock\.txt`"),
    "full": re.compile(r"([0-9]{3,6})\s+with\s+the\s+intake\s+backends"),
}


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


def problems_with(counts, readme, version, package_dir, profile):
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

    hits = count_marker(profile).findall(readme)
    if len(hits) != 1:
        out.append("README carries %d CURRENT_SCENARIO_COUNT_%s marker(s); it "
                   "needs exactly one" % (len(hits), profile.upper()))
    elif int(hits[0]) != total:
        # WHICH DIRECTION it missed by is the diagnosis, and the wrong one
        # sends the next person to edit the marker.
        out.append("README says CURRENT_SCENARIO_COUNT_%s: %s and the %s suites "
                   "reported %d. %s"
                   % (profile.upper(), hits[0], profile, total,
                      "A suite has lost scenarios" if total < int(hits[0]) else
                      "A suite has gained scenarios, or this environment runs "
                      "more than the %s profile installs" % profile))

    versions = VERSION_MARKER.findall(readme)
    if len(versions) != 1:
        out.append("README carries %d CURRENT_PIPELINE_VERSION marker(s); it "
                   "needs exactly one" % len(versions))
    elif versions[0] != version:
        out.append("README says CURRENT_PIPELINE_VERSION: %s and the runner "
                   "says %s" % (versions[0], version))

    sentences = STATUS_LINE[profile].findall(readme)
    if len(sentences) != 1:
        out.append("README carries %d %s status sentence(s); it needs exactly "
                   "one" % (len(sentences), profile))
    else:
        said = sentences[0]
        said_count = said[0] if isinstance(said, tuple) else said
        if int(said_count) != total:
            out.append("the %s status sentence reads %s scenarios and the tree "
                       "is %d. Updating the marker and leaving the prose behind "
                       "is the same defect one level down"
                       % (profile, said_count, total))
        if isinstance(said, tuple) and said[1] != version:
            out.append("the %s status sentence reads v%s and the runner says %s"
                       % (profile, said[1], version))
    return out


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    profile = "core"
    if argv[:1] == ["--profile"] and len(argv) > 1:
        profile, argv = argv[1], argv[2:]
    if profile not in PROFILES or len(argv) != 3:
        print("usage: verify_documented_status.py [--profile core|full] "
              "COUNTS.tsv README.md run_batch.py")
        return 2
    counts_path, readme_path, source_path = argv
    package_dir = os.path.dirname(os.path.abspath(readme_path)) or "."

    counts = read_counts(counts_path)
    readme = open(readme_path, encoding="utf-8").read()
    version = pipeline_version(source_path)
    total = sum(counts.values())
    problems = problems_with(counts, readme, version, package_dir, profile)

    if problems:
        print("DOCUMENTED STATUS DOES NOT MATCH THE TREE (profile: %s)" % profile)
        for problem in problems:
            print("  - %s" % problem)
        print()
        print("what README should carry for this profile:")
        print("    <!-- CURRENT_PIPELINE_VERSION: %s -->" % version)
        print("    <!-- CURRENT_SCENARIO_COUNT_%s: %d -->" % (profile.upper(), total))
        print()
        print("what each suite reported:")
        for suite in sorted(counts):
            print("    %-30s %5d" % (suite, counts[suite]))
        return 1

    print("documented status matches the tree (%s): %d scenarios across %d "
          "suites, pipeline v%s" % (profile, total, len(counts), version))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
