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
#:
#: HOW THIS KEY GOT LONGER. It first held only the record, the source, the
#: locator, the exposure, the outcome, the variant and the measure - and the
#: duplicate check added beside it immediately found 93 keys claimed twice in
#: a table nobody thought had duplicates. They were not duplicates. They were
#: race-stratified rows differing only in `population_subgroup`, and
#: survival percentages differing only in `outcome_timepoint`: two facts the
#: key could not see, so it called them one fact. A key that cannot tell two
#: rows apart will let a rerun overwrite one with the other. Both fields are
#: in it now, and the same table reports zero.
EFFECT_KEY = ('rec_id', 'source_sha256', 'source_page_ref',
              'population_subgroup', 'exposure_definition', 'outcome_name',
              'outcome_timepoint', 'analysis_variant', 'effect_measure')
#: What must also agree before an existing row counts as the same row.
EFFECT_VALUE = ('effect_point', 'effect_ci_low', 'effect_ci_high', 'ci_level',
                'n_exposed', 'events_exposed', 'synthesis_readiness',
                'analysis_stream')

#: A count is not free-standing: it is a number read beside one estimate, so
#: the estimate it was read beside is part of what it is. Without a parent the
#: same cohort N recorded beside twelve dose strata read as one number written
#: twelve times; without `population_scope` the same count under four age bands
#: did the same.
#:
#: THE PARENT IS NAMED SEMANTICALLY, NOT BY ITS ORDINAL. `effect_row_id` is a
#: position, which is exactly why it is absent from EFFECT_KEY - and a writer
#: cannot know it before the rows are numbered, so a guard keyed on it compares
#: a blank against a filled cell and reports a table it wrote itself as empty.
#: `annotate_parents` fills `parent_effect_key` from whichever the row has.
COUNT_KEY = ('rec_id', 'source_sha256', 'source_page_ref',
             'parent_effect_key', 'quantity', 'group_role', 'population_scope')
COUNT_VALUE = ('value', 'unit', 'count_basis')


def annotate_parents(count_rows, effect_rows):
    """Give every count row its parent's SEMANTIC key, in place.

    A count on file names its parent by ordinal (`effect_row_id`); a count a
    writer is about to emit cannot, because the ordinals do not exist yet, and
    it names the parent by the key instead. This puts both on the same footing
    so they can be compared at all. Rows with neither get an empty parent,
    which is still a value the key can compare.
    """
    by_id = {}
    for e in effect_rows:
        rid = (e.get('effect_row_id') or '').strip()
        if rid:
            by_id[rid] = str(key_of(e, EFFECT_KEY))
    for c in count_rows:
        if c.get('parent_effect_key'):
            continue
        c['parent_effect_key'] = by_id.get(
            (c.get('effect_row_id') or '').strip(), '')
    return count_rows


def key_of(row, fields):
    return tuple((row.get(f) or '').strip() for f in fields)


#: One table's whole state, not a count of rows.
EMPTY, IDENTICAL, PARTIAL, CONFLICT = "EMPTY", "IDENTICAL", "PARTIAL", "CONFLICT"


def duplicates(rows, kfields):
    """Natural keys that appear more than once. Not a tie to break either.

    Two rows with the same identity are an error wherever they sit. In the
    table this guards - effect estimates headed for meta-analysis - the same
    estimate twice is not a harmless repeat: it is double weight. Collapsing
    them quietly would hide the second one, and picking one of them would hide
    whichever it did not pick, so both cases are refused.
    """
    seen, twice = set(), []
    for r in rows:
        k = key_of(r, kfields)
        if k in seen and k not in twice:
            twice.append(k)
        seen.add(k)
    return twice


def compare(existing, intended, kfields, vfields):
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


def state_of(missing, identical, conflict, dup_existing, dup_intended):
    if conflict or dup_existing or dup_intended:
        return CONFLICT
    if missing and identical:
        return PARTIAL
    if identical:
        return IDENTICAL
    return EMPTY


def guard(name, tables, receipt_dir):
    """Decide whether a writer may run. Returns True to write.

    `tables` is [(label, existing_rows, intended_rows, key_fields, value_fields)].

    THE VERDICT IS OVER ALL THE TABLES AT ONCE, and that is the correction this
    function needed. It used to refuse only a conflict, or a single table that
    was half written - so a writer whose effect table was already complete and
    whose count table was still empty came back WRITE, and appending the
    intended rows would have written the effect table a second time. One output
    finished and another untouched is not a state to continue from; it is a
    state to ask about. A run either has not happened, or has happened, and
    anything in between is a question for a person.

        every table EMPTY      -> write
        every table IDENTICAL  -> a no-op; say so
        anything else          -> write nothing, and say what disagrees
    """
    report, states = {}, []
    for label, existing, intended, kf, vf in tables:
        miss, same, conf = compare(existing, intended, kf, vf)
        dup_e = duplicates(existing, kf)
        dup_i = duplicates(intended, kf)
        state = state_of(miss, same, conf, dup_e, dup_i)
        states.append(state)
        report[label] = {
            'state': state, 'intended': len(intended), 'missing': len(miss),
            'already_identical': len(same), 'conflicting': len(conf),
            'duplicate_keys_on_file': [list(k) for k in dup_e],
            'duplicate_keys_intended': [list(k) for k in dup_i],
            'conflict_examples': [
                {'key': list(key_of(a, kf)),
                 'intended': {f: a.get(f) for f in vf},
                 'on_file': {f: b.get(f) for f in vf}}
                for a, b in conf[:5]]}
    if states and all(s == EMPTY for s in states):
        verdict = 'WRITE'
    elif states and all(s == IDENTICAL for s in states):
        verdict = 'ALREADY_PRESENT_NO_WRITE'
    else:
        verdict = 'CONFLICT_NO_WRITE'
    report['verdict'] = verdict
    report['table_states'] = {k: v['state'] for k, v in report.items()
                              if isinstance(v, dict) and 'state' in v}
    os.makedirs(receipt_dir, exist_ok=True)
    json.dump(report, io.open(os.path.join(receipt_dir, '%s_idempotency.json'
                                           % name), 'w', encoding='utf-8'),
              indent=2, ensure_ascii=False)
    for label, d in report.items():
        if not isinstance(d, dict) or 'state' not in d:
            continue
        print('  %-24s %-9s 예정 %d / 이미동일 %d / 없음 %d / 충돌 %d'
              % (label, d['state'], d['intended'], d['already_identical'],
                 d['missing'], d['conflicting']))
        if d['duplicate_keys_on_file'] or d['duplicate_keys_intended']:
            print('      중복 자연키 - 파일 %d, 쓰려던 것 %d'
                  % (len(d['duplicate_keys_on_file']),
                     len(d['duplicate_keys_intended'])))
    print('  판정: %s' % verdict)
    return verdict == 'WRITE'
