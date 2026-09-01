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


def problems(name, receipt, base, logs, sidecars=True):
    """Everything in this receipt that no longer describes the tree.

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
    if sidecars:
        found += rowkey.sidecar_problems(
            receipt, {f: os.path.join(logs, f) for f in contract['sidecars']},
            contract['sidecars'])
    return found
