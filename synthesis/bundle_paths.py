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
STUDY_INPUTS = os.environ.get('FDT_STUDY_INPUTS') or os.path.join(
    HERE, 'study_inputs.json')


def study_inputs():
    if not os.path.exists(STUDY_INPUTS):
        raise SystemExit(
            'missing %s\n'
            'This file holds values and quoted text taken from the source\n'
            'publications, which are not redistributable and so are not in\n'
            'the repository. See study_inputs.example.json for its shape, or\n'
            'set FDT_STUDY_INPUTS to point at your own copy.' % STUDY_INPUTS)
    return json.load(io.open(STUDY_INPUTS, encoding='utf-8'))
