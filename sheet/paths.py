# -*- coding: utf-8 -*-
"""Every path this bundle uses, in one place and overridable.

The third audit could not re-run any of it: `/tmp/intake*`, `/home/claude` and
`/mnt/user-data/uploads` were written into a dozen files, so the tar described
a result nobody else could reproduce. Nothing below is a default anybody has to
accept - each is an environment variable away from being somewhere else.
"""
import os

HERE = os.path.dirname(os.path.abspath(__file__))


def _p(name, default):
    return os.environ.get(name, default)


#: The intake output the sheet is built from.
DRAFT = _p("FDT_DRAFT", "/tmp/intake6/draft")
#: The human-authored worklist, as CSV.
WORKLIST = _p("FDT_WORKLIST", "/tmp/wl/worklist.csv")
#: The second audit's findings, which the sheet reads to block rows.
AUDIT = _p("FDT_AUDIT",
           "/mnt/user-data/uploads/Downloads/include_fulltext_bundle/outputs/"
           "2026-08-28-contact-sheet-audit")
#: Where the built sheet goes, and what the tests read.
SHEET = _p("FDT_SHEET", "/tmp/intake/panel_count_contact_sheet.html")
#: How large one sheet may get before the next document starts a new file.
#: The crops now ride at the resolution they were cut at, and one file of 604
#: of them is not a file a browser opens. Documents are never split across
#: sheets - a person works a document at a time.
SHEET_BUDGET = int(_p("FDT_SHEET_BUDGET", str(18 * 1024 * 1024)))


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
REPO = _p("FDT_REPO", "/home/claude/geo/verify")
#: Page rasters, for the crop regression.
PAGES = _p("FDT_PAGES", os.path.join(DRAFT, "pages"))
#: Source documents, listed one absolute path per line.
STAGED = _p("FDT_STAGED", "/tmp/wl/staged_paths.txt")
#: How a worklist href is turned into the path the intake recorded. The
#: builder had one machine's home directory written into it - the worklist was
#: authored on a laptop and the intake ran in a container - so it matched
#: nothing anywhere else and died on a bare `assert`. Pairs are `from=to`,
#: separated by commas; empty means the href is used as it stands.
PATH_REWRITE = _p("FDT_PATH_REWRITE",
                  "/Users/minyeop/=/mnt/user-data/uploads/")


def rewrite(path):
    for pair in PATH_REWRITE.split(","):
        if "=" in pair:
            src, dst = pair.split("=", 1)
            if src and path.startswith(src):
                return dst + path[len(src):]
    return path


#: The worklist-to-document map the crop harness reads to find a pid's PDF.
CROSSCHECK = _p("FDT_CROSSCHECK", "/tmp/intake/crosscheck.json")
