"""The documented status is the measured status, or CI is red.

    python3 verify_documented_status.py --profile {core|full} \
        --rasters {absent|present} COUNTS.tsv README.md run_batch.py

Every commit that adds a scenario moves the suite total, and the number in
`README.md` followed by hand. It was wrong: the tree ran 2282 scenarios while
the file said "2184 scenarios on main after v7.43". A status line nobody can
trust is worse than no status line, because a reader takes it as the state of
the package - and the reader most likely to take it that way is the next person
deciding whether this thing can be pointed at a corpus.

Three things have to agree, for the profile named on the command line:

    the SUM of what the suites reported this run
    <!-- CURRENT_SCENARIO_COUNT_CORE: N -->  or  _FULL, in README.md
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
That difference is the whole of the gap between the two package totals, and the
totals themselves are not repeated here - they are the two markers in
`README.md`, which this file measures. A number that moves every release and is
written down in two places is a number that will disagree with itself.

The first version of this file documented one number and explained the other in
prose, which left a real contradiction: a correct run in a full environment
printed "this is not a defect" and then exited 1. A guard that calls a healthy
tree broken is a guard people learn to run with `|| true`.

So the environment is an ARGUMENT, and each profile has its own marker:

    --profile core   <!-- CURRENT_SCENARIO_COUNT_CORE: N -->   lock file only
    --profile full   <!-- CURRENT_SCENARIO_COUNT_FULL: N -->   + intake backends

## And the publisher figures are the second environment argument

The rasters are not in this repository and cannot be: they are publisher
figures. Four suites SKIP whole sections without them, so the total moves again
- and this time it moves between two runs of the SAME profile, because a fork
has no `FDT_RASTER_SOURCE` secret and this repository's own CI does.

Two markers per profile would be four numbers for one tree. Instead the markers
stay what a FRESH PUBLIC CLONE runs - the state a reader is in - and one more
marker says how much of the suite that reader cannot run:

    <!-- CURRENT_SCENARIO_COUNT_RASTER_ONLY: N -->

    --rasters absent    expected = the profile marker            (a clone, a fork)
    --rasters present   expected = the profile marker + N        (CI with the secret)

The third number is worth printing on its own account: it is the size of the
part of this suite that nobody without the figures can check.

A suite whose WHOLE file is raster-gated reports 0, and "a suite that reports 0
passes" is refused above for a good reason: the usual cause is a suite that fell
out of the loop. The two are told apart by MEASUREMENT, not by a list kept here:
the CI loop looks for `raster_root.ABSENT_TOKEN` in the suite's own output and
appends a third column saying it skipped. So a zero is allowed only from a suite
that said, in that run, which figure it could not see - and a suite that says so
in a run declaring `--rasters present` is a fetch that half-worked, which is
refused too.

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

RASTER_MARKER = re.compile(
    r"<!--\s*CURRENT_SCENARIO_COUNT_RASTER_ONLY:\s*([0-9]+)\s*-->")
#: The same sentence rule as the totals: the marker cannot move on its own.
RASTER_LINE = re.compile(r"([0-9]{1,6})\s+of\s+them\s+need\s+the\s+"
                         r"publisher\s+figures")

RASTERS = ("absent", "present")


#: The third column the CI loop writes for a suite that printed
#: `raster_root.ABSENT_TOKEN`. Spelled here and in the workflow, and
#: `test_reproducibility` asserts the two are the same string.
SKIPPED = "RASTER_SKIPPED"


def read_counts(path):
    """({suite: count}, {suites that skipped for want of a raster})."""
    out, skipped = {}, set()
    with open(path, encoding="utf-8") as fh:
        for number, line in enumerate(fh, 1):
            line = line.rstrip("\n")
            if not line.strip():
                continue
            parts = line.split("\t")
            if len(parts) not in (2, 3) or not parts[1].isdigit():
                raise SystemExit("%s:%d is not SUITE<TAB>COUNT[<TAB>%s]: %r"
                                 % (path, number, SKIPPED, line))
            if len(parts) == 3 and parts[2] not in ("", SKIPPED):
                raise SystemExit("%s:%d has a third column that is neither "
                                 "empty nor %r: %r" % (path, number, SKIPPED, line))
            if parts[0] in out:
                raise SystemExit("%s:%d reports %s twice" % (path, number, parts[0]))
            out[parts[0]] = int(parts[1])
            if len(parts) == 3 and parts[2] == SKIPPED:
                skipped.add(parts[0])
    return out, skipped


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


def problems_with(counts, readme, version, package_dir, profile,
                  rasters="absent", skipped=()):
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
    skipped = set(skipped)
    # A ZERO IS ALLOWED ONLY FROM A SUITE THAT SAID WHY. `test_compile_plan` is
    # raster-gated end to end: every one of its scenarios compiles the shipped
    # plan, and without the five figures there is nothing to compile. It reports
    # 0 and names the file it could not open.
    zero = sorted(s for s, n in counts.items() if n == 0 and s not in skipped)
    if zero:
        out.append("%s reported 0 scenarios and did not say a publisher figure "
                   "was missing. A suite that runs nothing passes; that is what "
                   "this catches" % ", ".join(zero))
    if rasters == "present" and skipped:
        # THE FETCH THAT HALF-WORKED. The clone step succeeded, the root is set,
        # and one file is not under it - so those sections SKIP and the total is
        # short by exactly the amount nobody would notice.
        out.append("%s could not find a publisher figure in a run that declares "
                   "them present. The root is set and something is not under it"
                   % ", ".join(sorted(skipped)))

    raster_hits = RASTER_MARKER.findall(readme)
    if len(raster_hits) != 1:
        out.append("README carries %d CURRENT_SCENARIO_COUNT_RASTER_ONLY "
                   "marker(s); it needs exactly one" % len(raster_hits))
        raster_only = None
    else:
        raster_only = int(raster_hits[0])
        raster_said = RASTER_LINE.findall(readme)
        if len(raster_said) != 1:
            out.append("README carries %d sentence(s) saying how many scenarios "
                       "need the publisher figures; it needs exactly one"
                       % len(raster_said))
        elif int(raster_said[0]) != raster_only:
            out.append("the sentence reads %s scenarios needing the publisher "
                       "figures and the marker says %d"
                       % (raster_said[0], raster_only))

    hits = count_marker(profile).findall(readme)
    # THE MARKER IS WHAT A CLONE RUNS. This run may be a run that can see the
    # figures, and then it runs the marker's scenarios AND the raster-only ones.
    expected = None
    if len(hits) == 1 and raster_only is not None:
        expected = int(hits[0]) + (raster_only if rasters == "present" else 0)
    if len(hits) != 1:
        out.append("README carries %d CURRENT_SCENARIO_COUNT_%s marker(s); it "
                   "needs exactly one" % (len(hits), profile.upper()))
    elif expected is not None and expected != total:
        # WHICH DIRECTION it missed by is the diagnosis, and the wrong one
        # sends the next person to edit the marker.
        out.append("README says CURRENT_SCENARIO_COUNT_%s: %s, the publisher "
                   "figures are %s so %d were expected, and the %s suites "
                   "reported %d. %s"
                   % (profile.upper(), hits[0], rasters, expected, profile,
                      total,
                      "A suite has lost scenarios" if total < expected else
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
        said_total = (int(said_count)
                      + (raster_only if rasters == "present" and raster_only
                         else 0))
        if said_total != total:
            out.append("the %s status sentence reads %s scenarios (%d with "
                       "the publisher figures, which are %s) and the tree is "
                       "%d. Updating the marker and leaving the prose behind "
                       "is the same defect one level down"
                       % (profile, said_count, said_total, rasters, total))
        if isinstance(said, tuple) and said[1] != version:
            out.append("the %s status sentence reads v%s and the runner says %s"
                       % (profile, said[1], version))
    return out


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    profile = "core"
    rasters = "absent"
    while len(argv) > 1 and argv[0] in ("--profile", "--rasters"):
        if argv[0] == "--profile":
            profile, argv = argv[1], argv[2:]
        else:
            rasters, argv = argv[1], argv[2:]
    if profile not in PROFILES or rasters not in RASTERS or len(argv) != 3:
        print("usage: verify_documented_status.py [--profile core|full] "
              "[--rasters absent|present] COUNTS.tsv README.md run_batch.py")
        return 2
    counts_path, readme_path, source_path = argv
    package_dir = os.path.dirname(os.path.abspath(readme_path)) or "."

    counts, skipped = read_counts(counts_path)
    readme = open(readme_path, encoding="utf-8").read()
    version = pipeline_version(source_path)
    total = sum(counts.values())
    problems = problems_with(counts, readme, version, package_dir, profile,
                             rasters=rasters, skipped=skipped)

    if problems:
        print("DOCUMENTED STATUS DOES NOT MATCH THE TREE (profile: %s, "
              "publisher figures: %s)" % (profile, rasters))
        for problem in problems:
            print("  - %s" % problem)
        print()
        print("what README should carry for this profile:")
        print("    <!-- CURRENT_PIPELINE_VERSION: %s -->" % version)
        # THE MARKER IS THE CLONE'S NUMBER. Printing this run's total when this
        # run could see the figures would talk the next person into writing the
        # number a fork cannot reach.
        raster_hits = RASTER_MARKER.findall(readme)
        _only = int(raster_hits[0]) if len(raster_hits) == 1 else 0
        print("    <!-- CURRENT_SCENARIO_COUNT_%s: %d -->"
              % (profile.upper(),
                 total - (_only if rasters == "present" else 0)))
        print()
        print("what each suite reported:")
        for suite in sorted(counts):
            print("    %-30s %5d" % (suite, counts[suite]))
        return 1

    print("documented status matches the tree (%s, publisher figures %s): %d "
          "scenarios across %d suites, pipeline v%s"
          % (profile, rasters, total, len(counts), version))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
