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
#: The repository, for the modules the crop tools import.
REPO = _p("FDT_REPO", "/home/claude/geo/verify")
#: Page rasters, for the crop regression.
PAGES = _p("FDT_PAGES", os.path.join(DRAFT, "pages"))
#: Source documents, listed one absolute path per line.
STAGED = _p("FDT_STAGED", "/tmp/wl/staged_paths.txt")
#: The worklist-to-document map the crop harness reads to find a pid's PDF.
CROSSCHECK = _p("FDT_CROSSCHECK", "/tmp/intake/crosscheck.json")
