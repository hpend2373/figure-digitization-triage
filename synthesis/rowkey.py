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


#: Fields this module adds so both sides can be compared, which no file has a
#: column for. Anything ELSE a row carries that its file does not is schema
#: drift, not a transient.
ALLOWED_TRANSIENT_FIELDS = ('parent_effect_key',)


class SchemaError(Exception):
    """A row carries a field its file has no column for."""


def writable(rows, fieldnames):
    """Rows restricted to the file's own columns - and no silent losses.

    THE FIRST VERSION DROPPED WHATEVER DID NOT FIT, which fixed the crash it
    was written for and opened a quieter one: add a provenance column to a
    writer, forget the CSV schema, and the field disappears between the guard
    and the disk. The first run looks like a success, the evidence is not on
    disk, and the disagreement surfaces on some later rerun as a conflict
    nobody can explain. Known transients are dropped; anything else raises
    before a single file is touched. A leading underscore is this package's
    mark for a field that never leaves memory.
    """
    allowed = set(fieldnames) | set(ALLOWED_TRANSIENT_FIELDS)
    for r in rows:
        extra = sorted(f for f in set(r) - allowed if not f.startswith('_'))
        if extra:
            raise SchemaError(
                'row carries %s, which its file has no column for; add the '
                'column or declare the field transient' % ', '.join(extra))
    return [{c: r.get(c, '') for c in fieldnames} for r in rows]


def write_all_or_nothing(specs, replace=None, journal_path=None):
    """Write several files, or leave every one of them as it was.

    THE FIRST VERSION WAS NOT WHAT ITS NAME SAID. It staged every file and then
    moved them into place one after another, with the failure handling on the
    STAGING loop only - so a failure on the second move left the first file
    replaced and the second one old: exactly the mixed state this module exists
    to prevent, produced by the function named after preventing it.

    Now the previous contents are copied aside first, each move is `os.replace`,
    and a failure part way through puts back every file already replaced. A
    journal records the transaction, so an interrupted run is visible afterwards
    rather than silent.

    What this still does not promise, named rather than implied: a process
    killed between two replaces cannot restore anything, and the recovery can
    itself fail. A generation directory with one pointer swap would make the
    commit a single act; this is robust to exceptions, not to `kill -9`.
    """
    import csv as _csv
    import hashlib
    import shutil
    replace = replace or os.replace
    staged, opened, backups, replaced = [], [], {}, []
    try:
        for path, fieldnames, rows in specs:
            tmp = path + '.writing'
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

    for _tmp, path in staged:
        if os.path.exists(path):
            backups[path] = path + '.previous'
            shutil.copy2(path, backups[path])
    if journal_path:
        json.dump({'state': 'COMMITTING', 'files': [p for _t, p in staged]},
                  io.open(journal_path, 'w', encoding='utf-8'), indent=2)
    try:
        for tmp, path in staged:
            replace(tmp, path)
            replaced.append(path)
    except Exception:
        for path in replaced:
            if path in backups and os.path.exists(backups[path]):
                os.replace(backups[path], path)
        for tmp, _p in staged:
            if os.path.exists(tmp):
                os.remove(tmp)
        for backup in backups.values():
            if os.path.exists(backup):
                os.remove(backup)
        if journal_path:
            json.dump({'state': 'ABORTED_ROLLED_BACK'},
                      io.open(journal_path, 'w', encoding='utf-8'), indent=2)
        raise
    for backup in backups.values():
        if os.path.exists(backup):
            os.remove(backup)
    if journal_path:
        digests = {}
        for _t, path in staged:
            h = hashlib.sha256()
            with open(path, 'rb') as fh:
                for chunk in iter(lambda: fh.read(65536), b''):
                    h.update(chunk)
            digests[path] = h.hexdigest()
        json.dump({'state': 'COMMITTED', 'files': [p for _t, p in staged],
                   'sha256': digests},
                  io.open(journal_path, 'w', encoding='utf-8'), indent=2)
    return [p for _t, p in staged]


#: Fields `assign_ids` may set. Everything else the guard has already ruled on.
ASSIGNABLE_FIELDS = set(ORDINAL_FIELDS) | {'parent_effect_key'}


def _snapshot(rows, assignable):
    return [tuple(sorted((k, v) for k, v in r.items()
                         if k not in assignable and not k.startswith('_')))
            for r in rows]


def run_writer(name, tables, receipt_dir, assign_ids=None, archive=None,
               journal_path=None, replace=None, relations=(),
               assignable=None, dry_run=False):
    """The whole write protocol, in one place, so both writers share one.

    ONE FUNCTION BECAUSE TWO COPIES DRIFT. Each writer had its own sequence -
    annotate, guard, number, serialise - and the parts CI could see were the
    pieces, not the order they were called in. Every defect that reached the
    tables lived in that order: ids minted before the guard so a rerun died on
    its own previous output, a field added for the guard reaching the CSV
    writer, one table written before another failed. None of them are visible
    in a function that is only ever run as a no-op.

    `tables` is [(label, path, fieldnames, existing, intended, key, value)].
    `assign_ids(label, existing, intended)` fills whatever ordinals the file
    uses, and is called ONLY after the guard has said to write - an ordinal
    minted earlier is a claim on a row that may never be written.

    Returns (verdict, written_paths).
    """
    # THE PARENT REFERENCE IS RESOLVED FIRST, AND THE ORDER MATTERS. A count
    # names its parent by ordinal on file and by semantic key before it is
    # written; both sides have to become the same thing BEFORE any key is
    # computed from them, or rows differing only by an unresolved parent
    # collapse and read as duplicates that are not there. The supplement writer
    # used to do this itself and discard what it found, so a duplicated or
    # dangling parent arrived at the guard as an ordinary unmatched key.
    by_label = {label: (existing, intended)
                for label, _p, _f, existing, intended, _k, _v in tables}
    problems = []
    for child, parent in relations:
        c_existing, c_intended = by_label[child]
        p_existing, p_intended = by_label[parent]
        problems += annotate_parents(c_existing, p_existing + p_intended)
        problems += annotate_parents(c_intended, p_existing + p_intended)
    if problems:
        os.makedirs(receipt_dir, exist_ok=True)
        json.dump({'verdict': 'PREFLIGHT_CONFLICT_NO_WRITE',
                   'preflight_problems': [list(x) for x in problems]},
                  io.open(os.path.join(receipt_dir, '%s_idempotency.json' % name),
                          'w', encoding='utf-8'), indent=2, ensure_ascii=False)
        for code, detail in problems[:5]:
            print('  전처리 거부  %-30s %s' % (code, detail))
        print('  판정: PREFLIGHT_CONFLICT_NO_WRITE')
        return 'PREFLIGHT_CONFLICT_NO_WRITE', []

    verdict_tables = [(label, existing, intended, kf, vf)
                      for label, _p, _f, existing, intended, kf, vf in tables]
    may = guard(name, verdict_tables, receipt_dir)
    if not may:
        return _last_verdict(receipt_dir, name), []
    # ONE PATH, INCLUDING THE ONE THAT DOES NOT WRITE. A dry run used to call
    # `guard` directly and skip this function, so every check that lives here -
    # the parent resolution above all - never ran on the path a person actually
    # invokes while watching the output. Against the real tables that reported
    # 44 counts as missing: an artefact of parents nobody had resolved.
    if dry_run:
        return 'WRITE_WOULD_PROCEED', []
    if archive:
        os.makedirs(archive, exist_ok=True)
        for label, path, _f, _e, _i, _k, _v in tables:
            if os.path.exists(path):
                with io.open(path, encoding='utf-8-sig') as fh:
                    io.open(os.path.join(archive, os.path.basename(path)), 'w',
                            encoding='utf-8').write(fh.read())
    if assign_ids:
        # A CALLBACK MAY SET AN ORDINAL AND NOTHING ELSE. It runs after the
        # guard, so anything else it changes is a change to a row already
        # judged - written without ever being compared against what is on file.
        allowed = set(assignable or ASSIGNABLE_FIELDS)
        before = {label: _snapshot(intended, allowed)
                  for label, _p, _f, _e, intended, _k, _v in tables}
        for label, _p, _f, existing, intended, _k, _v in tables:
            assign_ids(label, existing, intended)
        for label, _p, _f, _e, intended, _k, _v in tables:
            if _snapshot(intended, allowed) != before[label]:
                raise SchemaError(
                    'assign_ids changed a field of %s that the guard had '
                    'already judged; only %s may be assigned'
                    % (label, ', '.join(sorted(allowed))))
    written = write_all_or_nothing(
        [(path, fieldnames, existing + intended)
         for _l, path, fieldnames, existing, intended, _k, _v in tables],
        replace=replace, journal_path=journal_path)
    return 'WRITE', written


def _last_verdict(receipt_dir, name):
    path = os.path.join(receipt_dir, '%s_idempotency.json' % name)
    try:
        return json.load(io.open(path, encoding='utf-8'))['verdict']
    except Exception:
        return 'UNKNOWN'


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
