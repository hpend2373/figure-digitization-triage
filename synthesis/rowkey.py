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
#: WHAT MUST ALSO AGREE IS DERIVED, NOT LISTED. A hand-written list of eight
#: fields left out `derivation_method` - and that is the field whose wrong
#: value, on 52 rows, counted baseline medians and IQRs as reported effect
#: estimates in this very pipeline. The guard would have called the wrong row
#: and the corrected row identical and reported the rerun as a clean no-op,
#: leaving the misclassification in place. A list of what matters will always
#: be missing whatever nobody thought of; what a writer controls is everything
#: it emits except the parts that belong to someone or something else.
#:
#: Kept as constants for callers that want the old narrow comparison, but
#: `guard` derives the payload by subtraction.
EFFECT_VALUE = ('effect_point', 'effect_ci_low', 'effect_ci_high', 'ci_level',
                'n_exposed', 'events_exposed', 'synthesis_readiness',
                'analysis_stream', 'derivation_method')

#: An ordinal is a position, not a value: it changes when rows are renumbered
#: and says nothing about whether the row is the same fact.
ORDINAL_FIELDS = ('effect_row_id', 'count_id', 'draft_id', 'descriptive_id')
#: A timestamp of the run, not of the evidence.
NONDETERMINISTIC_FIELDS = ('ai_correction_date',)
#: A PERSON'S, AND SO NOT THE WRITER'S TO REPRODUCE. A reviewer confirming a
#: row must not turn the next rerun into a conflict.
HUMAN_OWNED_FIELDS = (
    'human_confirmed', 'verified_by', 'verified_at', 'pool_eligible',
    'candidate_after_human_confirmation', 'human_gate',
    'extraction_consensus_status', 'extractor1_initials',
    'extractor2_initials', 'extraction_date_initial',
    'extraction_date_consensus', 'discrepancy_note', 'reviewer_initials')

#: A count is not free-standing: it is a number read beside one estimate, so
#: the estimate it was read beside is part of what it is. Without a parent the
#: same cohort N recorded beside twelve dose strata read as one number written
#: twelve times; without `population_scope` the same count under four age bands
#: did the same.
#:
#: THE PARENT IS NAMED SEMANTICALLY, NOT BY ITS ORDINAL. `effect_row_id` is a
#: position, which is why it is absent from EFFECT_KEY - and a writer cannot
#: know it before the rows are numbered, so a guard keyed on it compares a
#: blank against a filled cell and reports a table it wrote itself as empty.
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
    by_id, twice = {}, set()
    for e in effect_rows:
        rid = (e.get('effect_row_id') or '').strip()
        if not rid:
            continue
        if rid in by_id:
            # THE SAME LAST-WRITE-WINS THIS FILE JUST REMOVED ELSEWHERE. An
            # ordinal reused by two estimates cannot resolve to one parent, and
            # picking the later row would make a count's identity depend on
            # file order.
            twice.add(rid)
        by_id[rid] = str(key_of(e, EFFECT_KEY))
    problems = []
    for c in count_rows:
        rid = (c.get('effect_row_id') or '').strip()
        stated = c.get('parent_effect_key')
        if rid and rid in twice:
            problems.append(('DUPLICATE_EFFECT_ROW_ID', rid))
            c['parent_effect_key'] = '?%s' % rid
            continue
        resolved = by_id.get(rid) if rid else ''
        if rid and resolved is None:
            # NAMED A PARENT THAT IS NOT THERE. Silently blanking it made the
            # count look parentless, which is a different and lesser problem.
            problems.append(('UNKNOWN_PARENT_EFFECT_ROW_ID', rid))
            c['parent_effect_key'] = '?%s' % rid
            continue
        if stated and resolved and stated != resolved:
            problems.append(('PARENT_EFFECT_KEY_MISMATCH', rid))
            c['parent_effect_key'] = '?%s' % rid
            continue
        if not stated:
            c['parent_effect_key'] = resolved or ''
    return problems


def payload_fields(rows, key_fields):
    """Everything the writer controls: what it emits, minus what is not its own.

        every field the intended rows carry
      - the natural key            (already compared, and compared as identity)
      - ordinals                   (a position, not a value)
      - non-deterministic fields   (the run's clock, not the evidence's)
      - human-owned fields         (a reviewer's confirmation must not turn the
                                    next rerun into a conflict)
      - transient fields (_leading underscore)

    Derived rather than listed, because a list of what matters is always
    missing whatever nobody thought of - which is how `derivation_method`, the
    field that decides whether a row is an effect estimate or a descriptor,
    stayed outside the comparison.
    """
    out, seen = [], set()
    skip = (set(key_fields) | set(ORDINAL_FIELDS) | set(NONDETERMINISTIC_FIELDS)
            | set(HUMAN_OWNED_FIELDS))
    for r in rows:
        for f in r:
            if f in seen or f in skip or f.startswith('_'):
                continue
            seen.add(f)
            out.append(f)
    return tuple(out)


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


#: The only verdict that means a rerun would change nothing.
CLEAN_RERUN = 'ALREADY_PRESENT_NO_WRITE'


def receipt_verdicts(receipt_dir, expected):
    """{writer: verdict} for every writer that was DECLARED, present or not.

    A MISSING RECEIPT IS NOT A SILENCE. Reading whichever receipts happen to be
    on disk meant deleting one deleted the check with it: the final manifest
    went on reporting a consistent state while saying nothing at all about that
    writer's rerun. Every declared writer gets an entry, and a writer with no
    receipt gets RECEIPT_MISSING, which is not CLEAN_RERUN and so cannot pass.
    """
    out = {}
    for name in expected:
        path = os.path.join(receipt_dir, '%s_idempotency.json' % name)
        if not os.path.exists(path):
            out[name] = 'RECEIPT_MISSING'
            continue
        try:
            out[name] = json.load(io.open(path, encoding='utf-8'))['verdict']
        except (ValueError, KeyError):
            out[name] = 'RECEIPT_UNREADABLE'
    return out


def unclean_reruns(verdicts):
    """The writers whose rerun is not proven harmless. Empty means all are."""
    return sorted(n for n, v in verdicts.items() if v != CLEAN_RERUN)


def writable(rows, fieldnames):
    """Rows restricted to the file's own columns, in the file's own order.

    THE GUARD DOES NOT SEE THE WRITE. `parent_effect_key` is a field this
    module ADDS so that both sides can name a parent the same way; it is not a
    column of the CSV. Handing such a row straight to `csv.DictWriter` raises
    `ValueError: dict contains fields not in fieldnames` - and the writer that
    hit it had already written its first table, so the failure landed exactly
    where nothing was watching: between two outputs, in the write branch a
    clean no-op never enters.

    Anything the file does not have a column for is dropped here; anything the
    file has and the row does not becomes empty.
    """
    return [{c: r.get(c, '') for c in fieldnames} for r in rows]


def write_all_or_nothing(specs):
    """Write several CSVs, or leave every one of them as it was.

    `specs` is [(path, fieldnames, rows)]. Each file is written beside itself
    and moved into place only after all of them have been written, so a failure
    partway through - a schema mismatch, a full disk, an interrupt - leaves the
    whole set at the previous state rather than one table ahead of another.
    That in-between state is the one the guard cannot describe: it is neither
    "has not happened" nor "has happened".
    """
    import csv as _csv
    import shutil as _shutil
    staged, opened = [], []
    try:
        for path, fieldnames, rows in specs:
            tmp = path + '.writing'
            # Recorded BEFORE the write, not after: the file that fails is the
            # one whose half-written temp would otherwise be left behind, and
            # it is never the one already in `staged`.
            opened.append(tmp)
            with io.open(tmp, 'w', encoding='utf-8', newline='') as fh:
                w = _csv.DictWriter(fh, fieldnames=list(fieldnames))
                w.writeheader()
                w.writerows(writable(rows, fieldnames))
            staged.append((tmp, path))
    except Exception:
        for tmp in opened:
            if os.path.exists(tmp):
                os.remove(tmp)
        raise
    for tmp, path in staged:
        _shutil.move(tmp, path)
    return [p for _t, p in staged]


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
        # The caller's value list is a floor, not the contract: whatever the
        # writer emits beyond it is still the writer's to reproduce.
        vf = tuple(vf) + tuple(f for f in payload_fields(intended, kf)
                               if f not in vf)
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
