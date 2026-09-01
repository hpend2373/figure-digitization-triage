# -*- coding: utf-8 -*-
"""What each writer owes, in one place, for everyone who checks it.

ONE CONTRACT, TWO READERS. This lived inside build_final_manifest, so the
final receipt recomputed the writer's code, its inputs, its source documents,
its tables, its sidecars and their volatile keys - and the workbook step,
which is the thing that actually MUTATES a file, checked a subset it had
written for itself. A source document could change, the writer not be re-run,
and the workbook be modified anyway; the disagreement surfaced later, in the
final receipt, after the mutation.

Declared here rather than read off a receipt. The table set used to be
intersected with whatever the receipt already named, so a receipt that lost an
entry lost the check along with it - the scope of the proof set by the thing
being proved.
"""
import io
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bundle_paths
import rowkey

HERE = os.path.dirname(os.path.abspath(__file__))

#: The tables these writers share, and the files they live in.
TABLE_FILES = {'effects_text_long': 'effect_extraction_text_long.csv',
               'extraction_counts_long': 'extraction_counts_long.csv'}


def _supplement_sources(base):
    """Recomputed the way the writer computes it, so the set is a set."""
    supp = os.path.join(base, 'source_supplements')
    if not os.path.isdir(supp):
        return {}
    return {f: rowkey.file_digest(os.path.join(supp, f))
            for f in sorted(os.listdir(supp))
            if f.startswith(('R0855', 'R0856', 'R1040'))}


def _figure_sources(base):
    spec = bundle_paths.study_inputs()['figure_rows']
    return {v: rowkey.file_digest(os.path.join(base, v))
            for v in sorted({r['source_local_path'] for r in spec})}


CONTRACTS = {
    'integrate_supplements': {
        'file': 'integrate_supplements.py',
        'tables': ('effects_text_long', 'extraction_counts_long'),
        # WHAT MAY BE LEFT OUT OF EACH DIGEST. The receipt names its own
        # volatile keys; without a contract to check them against, widening
        # that list exempted any field from the comparison while every other
        # check still passed.
        'sidecars': {'new_rows.json': (),
                     'integration.json': ('archived_to', 'date', 'dry_run',
                                          'verdict')},
        'sources': _supplement_sources},
    'figure_printed_numbers': {
        'file': 'figure_printed_numbers.py',
        'tables': ('effects_text_long',),
        'sidecars': {'figure_rows.json': (),
                     'R1087_coexposure_pending.json': ()},
        'sources': _figure_sources},
}


#: WHAT EACH SIDECAR HAS TO BE, not just which bytes it is. A hash proves the
#: file is the one the receipt names; it says nothing about the shape of what
#: is inside. The final manifest read `len(integration.json['refused_values'])`
#: and an integer there ended the run in a TypeError before any check could
#: report anything - which is how this was found: I put an integer there
#: myself while testing a mutation.
SIDECAR_SCHEMA = {
    'integration.json': ('object', {'refused_values': 'list',
                                    'new_effect_rows': 'count',
                                    'new_count_rows': 'count'}),
    'R1087_coexposure_pending.json': ('object', {'printed_values': 'list'}),
    'new_rows.json': ('object', {}),
    'figure_rows.json': ('array', {}),
}


def shape_problems(name, payload):
    """Where a sidecar's contents are not the shape everything downstream
    assumes. Reported, never raised: a malformed sidecar is a refusal with a
    name, not a traceback in the middle of a receipt."""
    want = SIDECAR_SCHEMA.get(name)
    if want is None:
        return []
    kind, keys = want
    if kind == 'array' and not isinstance(payload, list):
        return [('SIDECAR_SCHEMA_INVALID',
                 '%s is a %s, not a list of rows'
                 % (name, type(payload).__name__))]
    if kind == 'object' and not isinstance(payload, dict):
        return [('SIDECAR_SCHEMA_INVALID',
                 '%s is a %s, not an object' % (name, type(payload).__name__))]
    out = []
    for key, want_kind in sorted(keys.items()):
        got = payload.get(key)
        if want_kind == 'list' and not isinstance(got, list):
            out.append(('SIDECAR_SCHEMA_INVALID',
                        '%s: %s is %s, not a list'
                        % (name, key, type(got).__name__)))
        if want_kind == 'count' and not (isinstance(got, int)
                                         and not isinstance(got, bool)
                                         and got >= 0):
            out.append(('SIDECAR_SCHEMA_INVALID',
                        '%s: %s is %r, not a count' % (name, key, got)))
    return out


def read_sidecars(name, receipt, logs):
    """The writer's sidecars, read ONCE, judged, and handed back.

    VALIDATED BEFORE USE. The final manifest counted refusals and held
    estimates out of these files and only then asked whether they were the
    files the receipt named - and it opened each one twice, so what it counted
    and what it checked could differ. Callers now get the payloads that passed.
    """
    contract = CONTRACTS[name]
    payloads, out = {}, []
    for fname in sorted(contract['sidecars']):
        path = os.path.join(logs, fname)
        if not os.path.exists(path):
            out.append(('SIDECAR_MISSING',
                        '%s is attested and is not on disk' % fname))
            continue
        try:
            payload = json.load(io.open(path, encoding='utf-8'))
        except ValueError as exc:
            out.append(('SIDECAR_UNREADABLE', '%s: %s' % (fname, exc)))
            continue
        found = rowkey.sidecar_payload_problems(
            receipt, fname, payload, contract['sidecars'])
        found += shape_problems(fname, payload)
        out += found
        if not found:
            payloads[fname] = payload
    return payloads, out


def problems(name, receipt, base, logs, sidecars=True):
    """Everything in this receipt that no longer describes the tree.

    Returns (problems, {sidecar name: the payload that passed}). Callers use
    the returned payloads rather than opening the files again.

    `sidecars=False` for a caller that has already read a sidecar and judged
    the payload it holds - re-reading the file here would check one thing
    while that caller applies another.
    """
    contract = CONTRACTS[name]
    want = {
        'protocol_sha256': rowkey.file_digest(
            os.path.join(os.path.dirname(os.path.abspath(rowkey.__file__)),
                         'rowkey.py')),
        'study_inputs_sha256': rowkey.file_digest(bundle_paths.STUDY_INPUTS),
        'tables': {k: rowkey.file_digest(os.path.join(base, TABLE_FILES[k]))
                   for k in contract['tables']},
        'sources': contract['sources'](base),
    }
    code = os.path.join(HERE, contract['file'])
    if os.path.exists(code):
        want['writer_code_sha256'] = rowkey.file_digest(code)
    found = rowkey.attestation_problems(receipt, want)
    # AND THE SETS THEMSELVES, NOT ONLY THE ENTRIES THEY SHARE.
    # attestation_problems judges what the caller names; a receipt naming
    # something extra, or missing an entry, is a different claim about what
    # this writer did.
    core = (receipt.get('attestation') or {}).get('core') or {}
    caller = (receipt.get('attestation') or {}).get('caller') or {}
    for what, got, declared in (
            ('table', sorted(core.get('tables') or {}),
             sorted(contract['tables'])),
            ('source', sorted(caller.get('sources') or {}),
             sorted(want['sources'])),
            ('sidecar', sorted(receipt.get('sidecars') or {}),
             sorted(contract['sidecars']))):
        if got != declared:
            found.append(('RECEIPT_%s_SET_MISMATCH' % what.upper(),
                          'receipt names %ss %s, the contract declares %s'
                          % (what, got, declared)))
    payloads = {}
    if sidecars:
        payloads, found_side = read_sidecars(name, receipt, logs)
        found += found_side
    return found, payloads
