# -*- coding: utf-8 -*-
"""Every path this bundle uses, in one place and overridable.

The third audit could not re-run any of it: `/tmp/intake*`, `/home/claude` and
`/mnt/user-data/uploads` were written into a dozen files, so the tar described
a result nobody else could reproduce. Nothing below is a default anybody has to
accept - each is an environment variable away from being somewhere else.
"""
import os

HERE = os.path.dirname(os.path.abspath(__file__))


#: What each variable falls back to when the environment says nothing. Kept
#: because a check on the effective value is a check on whoever ran it: with
#: FDT_PATH_REWRITE set, the suite asked whether THIS run had a machine path,
#: not whether the repository ships one as its default. The default is the
#: thing that travels.
DEFAULTS = {}


def _p(name, default):
    DEFAULTS[name] = default
    return os.environ.get(name, default)


#: WHERE ONE RUN LIVES. The paths below were one machine's absolute paths -
#: `/tmp/intake6/draft`, `/tmp/intake`, `/mnt/user-data/uploads/...` - which is
#: the defect this module was written for, still sitting in the defaults it
#: hands out. A run is a directory: the draft CSVs, `pages/`, `crops/` and the
#: sheet all sit in it, which is what `corpus_intake.py --out` produces and
#: what `build_sheet2.py` writes back into. Point FDT_RUN at one and the rest
#: follow; override any single one when a tree is arranged differently.
RUN = _p("FDT_RUN", os.path.join(os.path.dirname(HERE), "intake-run"))


def require(name, what):
    """A path that must exist, or a message naming the variable to set."""
    value = globals()[name]
    if value and os.path.exists(value):
        return value
    raise SystemExit(
        "%s이(가) 없습니다: %r\n"
        "FDT_%s로 지정하거나, FDT_RUN을 인테이크 산출 디렉터리로 두십시오 "
        "(지금 FDT_RUN=%r)." % (what, value, name, RUN))


#: The intake output the sheet is built from.
DRAFT = _p("FDT_DRAFT", RUN)
#: The human-authored worklist, as CSV.
WORKLIST = _p("FDT_WORKLIST", os.path.join(RUN, "worklist.csv"))
#: The second audit's findings, which the sheet reads to block rows.
AUDIT = _p("FDT_AUDIT", os.path.join(RUN, "audit"))
#: The row-by-row record of a visual pass over the countable rows, bound to
#: crop digests. `sheet/census.py` says what it is for; the short version is
#: that ACCEPTABLE is a measurement of the crop and this is a look at what is
#: inside it. It travels with the run because the sheet's blocking rule reads
#: it: a run without it is a run whose blocks silently disappeared.
CENSUS = _p("FDT_CENSUS", os.path.join(RUN, "crop_visual_census.csv"))
#: Build without a census on purpose (a fixture, a corpus nobody has looked
#: at yet). Anything but "1" and a missing census stops the build, because a
#: safety rule that vanishes when its file is missing is not a safety rule.
CENSUS_OPTIONAL = _p("FDT_CENSUS_OPTIONAL", "") == "1"

#: What three independent proposers said about every row's figure region and
#: whether they agree - `validate_regions.py` writes it. The sheet's blocking
#: rule reads the Agreement column: a row nobody's second method confirms is
#: REVIEW_REQUIRED. Missing means the build stops, unless FDT_REGIONS_OPTIONAL=1
#: says out loud that nobody has run the proposers on this corpus yet.
REGIONS = _p("FDT_REGIONS", os.path.join(RUN, "validated_regions.csv"))
REGIONS_OPTIONAL = _p("FDT_REGIONS_OPTIONAL", "") == "1"

#: Where the built sheet goes, and what the tests read.
SHEET = _p("FDT_SHEET",
           os.path.join(RUN, "panel_count_contact_sheet.html"))
#: How large one sheet may get before the next document starts a new file.
#: The crops now ride at the resolution they were cut at, and one file of 604
#: of them is not a file a browser opens. Documents are never split across
#: sheets - a person works a document at a time.
SHEET_BUDGET = int(_p("FDT_SHEET_BUDGET", str(18 * 1024 * 1024)))


def pid_of_document(worklist_rows, ledger_rows):
    """{Source_Document_ID: pid}, from the two files that already say it.

    The crop harness took this from a JSON map that no code in this repository
    writes. The worklist names each publication's file, the ledger records the
    path the intake read, and `rewrite` bridges the two - which is exactly what
    the sheet builder does to put a pid on a card.
    """
    import urllib.parse
    by_path = {}
    for w in worklist_rows:
        href = w.get("href") or ""
        if href.startswith("file://"):
            href = href[len("file://"):]
        by_path[rewrite(urllib.parse.unquote(href))] = w.get("pid", "")
    out = {}
    for row in ledger_rows:
        pid = by_path.get(row.get("Input_Path", ""))
        if pid:
            out[row["Source_Document_ID"]] = pid
    return out


def part_path(sheet, i):
    stem, ext = os.path.splitext(sheet)
    return "%s_%02d%s" % (stem, i, ext)


def parts_for(sheet):
    """Every built sheet file, in order. One file, or the parts beside it.

    The tests and the merge both need this, and each having its own idea of
    where the parts are is how a check ends up reading a different set of
    files than the one the person filled in.
    """
    out, i = [], 1
    while os.path.exists(part_path(sheet, i)):
        out.append(part_path(sheet, i))
        i += 1
    if out:
        return out
    return [sheet] if os.path.exists(sheet) else []


#: The repository, for the modules the crop tools import.
REPO = _p("FDT_REPO", os.path.dirname(HERE))
#: Page rasters, for the crop regression.
PAGES = _p("FDT_PAGES", os.path.join(DRAFT, "pages"))
#: Source documents, listed one absolute path per line.
STAGED = _p("FDT_STAGED", os.path.join(RUN, "staged_paths.txt"))
#: How a worklist href is turned into the path the intake recorded. The
#: builder had one machine's home directory written into it - the worklist was
#: authored on a laptop and the intake ran in a container - so it matched
#: nothing anywhere else and died on a bare `assert`. Pairs are `from=to`,
#: separated by commas; empty means the href is used as it stands.
#: Empty by default. It used to default to one person's home directory, which
#: is data about a laptop, not a default - and a default nobody can be right
#: about silently matches nothing. `build_sheet2.py` names the unmatched pids
#: and says to set this.
PATH_REWRITE = _p("FDT_PATH_REWRITE", "")


def rewrite(path):
    for pair in PATH_REWRITE.split(","):
        if "=" in pair:
            src, dst = pair.split("=", 1)
            if src and path.startswith(src):
                return dst + path[len(src):]
    return path


#: The worklist-to-document map the crop harness reads to find a pid's PDF.
#: An OPTIONAL pid -> document map. Optional because nothing in this
#: repository ever produced one: `regress_crop.py` required it, and the file
#: was made by hand, once, on one machine - so the harness that grades the
#: crops could not be run by anyone else at all. It is derived from the
#: worklist and the ledger now (see `pid_of_document`), and this stays only as
#: an override for a tree where that derivation does not hold.
CROSSCHECK = _p("FDT_CROSSCHECK", "")
