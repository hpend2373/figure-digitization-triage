# -*- coding: utf-8 -*-
"""A stable identity for an extracted row, and the guard that uses it.

WHY. Both writers minted an ID one past the current maximum and appended.
Nothing in that is idempotent: a second `--write` would not recognise its own
previous output and would append all 120 rows again, silently doubling every
estimate in a table meant for meta-analysis. `Draft_ID`-style ordinals cannot
be identity - they are a position, and position moves.

Identity here is what the row IS: which record, which exact source file, which
locator inside it, and which estimate. None of that changes when rows are
reordered, and all of it changes when the row is genuinely a different fact.

THREE OUTCOMES, and the middle one is the point:

  nothing present   -> write, normally
  all present and identical -> a no-op; say so and exit 0
  partly present, or present with different values -> WRITE NOTHING and emit a
      conflict receipt naming the rows that disagree

The third case is where a naive "skip what exists" would quietly half-write a
table. A partial or conflicting state is a question for a person, not something
to resolve by guessing which side is right.
"""
import io, json, os

#: The fields that make an effect row the fact it is. `effect_row_id` is
#: deliberately absent: it is an ordinal, and an ordinal is a position.
EFFECT_KEY = ('rec_id', 'source_sha256', 'source_page_ref',
              'exposure_definition', 'outcome_name', 'analysis_variant',
              'effect_measure')
#: What must also agree before an existing row counts as the same row.
EFFECT_VALUE = ('effect_point', 'effect_ci_low', 'effect_ci_high', 'ci_level',
                'n_exposed', 'events_exposed', 'synthesis_readiness',
                'analysis_stream')

COUNT_KEY = ('rec_id', 'source_sha256', 'source_page_ref', 'quantity',
             'group_role')
COUNT_VALUE = ('value', 'unit', 'count_basis')


def key_of(row, fields):
    return tuple((row.get(f) or '').strip() for f in fields)


def compare(existing, intended, kfields, vfields):
    """(missing, identical, conflicting) for one table."""
    index = {}
    for r in existing:
        index.setdefault(key_of(r, kfields), []).append(r)
    missing, identical, conflict = [], [], []
    for r in intended:
        k = key_of(r, kfields)
        found = index.get(k)
        if not found:
            missing.append(r)
            continue
        same = [g for g in found
                if key_of(g, vfields) == key_of(r, vfields)]
        if same:
            identical.append(r)
        else:
            conflict.append((r, found[0]))
    return missing, identical, conflict


def guard(name, tables, receipt_dir):
    """Decide whether a writer may run. Returns True to write.

    `tables` is [(label, existing_rows, intended_rows, key_fields, value_fields)].
    """
    report, may_write, all_present = {}, True, True
    for label, existing, intended, kf, vf in tables:
        miss, same, conf = compare(existing, intended, kf, vf)
        report[label] = {'intended': len(intended), 'missing': len(miss),
                         'already_identical': len(same), 'conflicting': len(conf),
                         'conflict_examples': [
                             {'key': list(key_of(a, kf)),
                              'intended': {f: a.get(f) for f in vf},
                              'on_file': {f: b.get(f) for f in vf}}
                             for a, b in conf[:5]]}
        if conf:
            may_write = False
        if miss:
            all_present = False
        if same and miss:
            may_write = False          # a half-written table is a question
    verdict = ('CONFLICT_NO_WRITE' if not may_write
               else 'ALREADY_PRESENT_NO_WRITE' if all_present else 'WRITE')
    report['verdict'] = verdict
    os.makedirs(receipt_dir, exist_ok=True)
    json.dump(report, io.open(os.path.join(receipt_dir, '%s_idempotency.json'
                                           % name), 'w', encoding='utf-8'),
              indent=2, ensure_ascii=False)
    for label, d in report.items():
        if label == 'verdict':
            continue
        print('  %-24s 예정 %d / 이미동일 %d / 없음 %d / 충돌 %d'
              % (label, d['intended'], d['already_identical'], d['missing'],
                 d['conflicting']))
    print('  판정: %s' % verdict)
    return verdict == 'WRITE'
