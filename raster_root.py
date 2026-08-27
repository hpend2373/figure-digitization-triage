#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Where a publisher raster is, when the repository does not carry it.

    FDT_RASTER_ROOT=/path/to/rasters python3 <anything that needs one>

THE REPOSITORY IS PUBLIC AND THESE FIGURES ARE NOT REDISTRIBUTABLE. They were
tracked in it, and the README said "private research repository" while GitHub
said `visibility: public` - a contradiction between a claim in a file and a
setting on a server, which no check in this package was looking at. The rasters
are gone from the tree and from its history; what stays is this table, which
pins each one by SHA-256.

`forward_test_127_mono_bar.py` had the pattern already, for exactly this reason,
and this module is that pattern made shared rather than copied:

    ABSENT   -> SKIP, exit 0, loudly. A run that cannot see the figure has
                nothing to say about it, and saying nothing is not a failure.
    PRESENT  -> the SHA-256 must match. A raster that is not the one the
                coordinates were measured on is worse than no raster: it
                returns a plausible number for the wrong picture.

The hashes below were taken from the files as they stood in the last commit that
carried them, so a reader who has the originals can check that what they have is
what this package measured.

A ROOT MIRRORS THE LAYOUT, subdirectories included: the keys below are paths,
not names, and `fixtures/id323_fig1.jpeg` is looked for at
`$FDT_RASTER_ROOT/fixtures/id323_fig1.jpeg`. A flat directory of loose files was
accepted here for one commit and it half-worked: `check` found them, and then
`make_plan_323` - which joins the plan's own relative path onto the root -
opened nothing. A root that satisfies some callers and not others is worse than
one that is plainly missing, so a file under the wrong path now reads as absent
and SKIPs.
"""
import hashlib
import os

HERE = os.path.dirname(os.path.abspath(__file__))
ENV = "FDT_RASTER_ROOT"

#: repo-relative name -> sha256 of the bytes this package measured.
RASTERS = {
    "323_p5_fig2.jpeg":
        "53debc3ceea8c15aecbc6fc7cba9eda02f0ba17a8f392d47e02043c077b3e27a",
    "397_fig1.jpeg":
        "196fee64bd3b6c8401707291a88fea64e0032f2ffa97e8dd138057e8ff30e1a1",
    "397_fig2.jpeg":
        "2a377dd7ef381c27f40fcff8c9a6d8016a68b972ef7d1ecb81951ec7ef90ada5",
    "397_fig3.jpeg":
        "6650fba60385108799214be820580cd92a81cc874dfdb0760ad9e6630b7f1ff9",
    "397_fig4.jpeg":
        "44103d3658f4142e5754abc6a3c510c529eb0772bbf6acd92604e7816f1d58d2",
    "397_fig5.jpeg":
        "d00ff8144590c0dc8f2d6166c84723c04c1be0a764750dd9b97092922782d86e",
    "ID386_Fig2_publisher_898x1662.png":
        "908314d516fce70b724cba8e05d469cdee8a6df52572a6c7dfac4dadbe4ecd08",
    "fixtures/id323_fig1.jpeg":
        "51584f993ca605b257896733b467bfb8b0a61f2000a6ecc04c4d9bca37e11756",
    "id323_fig1.tar":
        "5eab5e206a0e9c4bbd978b1b6808267a6c15ad338542c3829ace4afb4bb4aea7",
    "id323_fig2.tar":
        "252b4da65b43c6d6813aa12af6ecee04bfc2a9d73e6196a1992b8ec72e3c1785",
}


def roots(extra=""):
    """Where to look, nearest first: an explicit root, the environment, HERE.

    HERE stays on the list so a developer who drops the originals back beside
    the code is not told they are missing - the hash still has to match, which
    is the check that matters.
    """
    out = []
    for r in (extra, os.environ.get(ENV, ""), HERE):
        if r and r not in out:
            out.append(r)
    return out


def find(name, extra=""):
    """The path to `name` under the first root that has it, or ""."""
    for root in roots(extra):
        p = os.path.join(root, name)
        if os.path.exists(p):
            return p
    return ""


def sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def check(name, extra=""):
    """(path, note) - path is "" when the raster is absent.

    Raises when a raster IS present and is not the one the coordinates were
    measured on. Absent and wrong are different answers and only one of them is
    an error.
    """
    path = find(name, extra)
    if not path:
        return "", skip_note(name)
    want = RASTERS.get(name, "").strip().lower()
    if not want:
        return path, "no hash is pinned for %s" % name
    got = sha(path)
    if got != want:
        raise ValueError(
            "%s hashes %s..., this package measured %s.... A raster that is "
            "not the one the coordinates were taken on returns a plausible "
            "number for the wrong picture." % (path, got[:16], want[:16]))
    return path, "raster %s... verified" % got[:16]


#: A TOKEN, not prose. A suite that skips its whole file reports 0 scenarios,
#: and "a suite that reports 0 passes" is exactly what `verify_documented_status`
#: refuses - correctly, because the usual cause is a suite that fell out of the
#: loop. The CI loop tells the two apart by looking for this string in the
#: suite's output, so it has to be something no sentence would produce by
#: accident, and it has to live here rather than being spelled twice.
ABSENT_TOKEN = "FDT_RASTER_ABSENT"


def skip_note(name):
    return ("SKIP [%s]: %s is not on this machine. It is a publisher figure "
            "and is not redistributable, so this repository does not carry it. "
            "Re-run with %s pointing at the directory that holds it; the "
            "SHA-256 is pinned in raster_root.py so the wrong file cannot be "
            "substituted." % (ABSENT_TOKEN, name, ENV))
