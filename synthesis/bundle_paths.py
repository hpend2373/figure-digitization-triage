# -*- coding: utf-8 -*-
"""Where the bundle is, and where the non-public inputs are.

The extraction bundle is not redistributable, so nothing here may assume it
sits at a fixed path relative to this file. `FDT_BUNDLE` names it; the default
is the layout these scripts were written in (two directories up from the
`outputs/<run>/` folder they live in), which keeps them working in place.
"""
import io, json, os

HERE = os.path.dirname(os.path.abspath(__file__))
BASE = os.environ.get('FDT_BUNDLE') or os.path.abspath(
    os.path.join(HERE, '..', '..'))

#: Publisher-derived values and quoted text. Deliberately absent from the
#: published tree; `study_inputs.example.json` shows the shape.
#: ONE HOME, like the receipts. This resolved beside whichever copy of this
#: module was imported, so the writers found the file and the final manifest -
#: importing its own copy from another directory - found nothing and reported
#: every receipt as stale against an empty hash.
STUDY_INPUTS = os.environ.get('FDT_STUDY_INPUTS') or os.path.join(
    BASE, 'outputs', 'supplement_integration_2026-08-30', 'study_inputs.json')


def study_inputs():
    if not os.path.exists(STUDY_INPUTS):
        raise SystemExit(
            'missing %s\n'
            'This file holds values and quoted text taken from the source\n'
            'publications, which are not redistributable and so are not in\n'
            'the repository. See study_inputs.example.json for its shape, or\n'
            'set FDT_STUDY_INPUTS to point at your own copy.' % STUDY_INPUTS)
    return json.load(io.open(STUDY_INPUTS, encoding='utf-8'))


#: WHERE THE RECEIPTS LIVE, for the writers AND for whatever reads them.
#: The writers wrote beside their own file and the final manifest read under
#: the bundle, and `FDT_BUNDLE` moves only the second - so running the shipped
#: writers and then the manifest could have the manifest reading a receipt from
#: a different run in a different tree and calling it proof of this one.
RECEIPTS = os.environ.get('FDT_SYNTHESIS_RECEIPTS') or os.path.join(
    BASE, 'outputs', 'supplement_integration_2026-08-30', 'logs')


def receipt_dir():
    """The one receipt directory, created if it is not there.

    Git does not carry an empty directory, so a fresh clone had no `logs/` and
    the figure writer failed on its first write - before the guard it was
    supposed to reach.
    """
    os.makedirs(RECEIPTS, exist_ok=True)
    return RECEIPTS


def write_lock():
    """ONE lock for every writer that touches these tables.

    A lock per writer serialises a writer against itself and leaves two
    different writers free to interleave on the same file - which is the case
    that loses rows, because each replaces the whole table from the snapshot it
    read.
    """
    return os.path.join(BASE, '.synthesis-write.lock')
