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
import csv, io, json, os

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


def attestation_problems(receipt, expected):
    """What in this receipt no longer describes the tree. [] means it holds.

    A RECEIPT THAT RECORDS ONLY ITS VERDICT IS A STRING. The verdict was the
    only thing anyone read, so deleting the attestation, or changing the code,
    the inputs or the files it was reached from, left an old
    ALREADY_PRESENT_NO_WRITE reading as proof of a rerun that never happened.
    Recording it and checking it are two different pieces of work, and only the
    first was done.

    `expected` carries whatever the caller can recompute now:
    protocol_sha256, writer_code_sha256, study_inputs_sha256, sources
    ({name: sha}), tables ({label: file_sha256}). A key absent from `expected`
    is not checked; a key present and different is named.
    """
    att = (receipt or {}).get('attestation')
    if not att:
        return [('RECEIPT_ATTESTATION_MISSING', 'no attestation recorded')]
    core, caller = att.get('core', {}), att.get('caller', {})
    out = []
    # THE SCHEME COMES FIRST BECAUSE IT EXPLAINS THE REST. Row digests written
    # under a different serialisation are not comparable, so saying so once
    # beats naming every table as stale for a reason that is not theirs.
    scheme = core.get('rows_digest_scheme')
    if scheme != ROWS_DIGEST_SCHEME:
        out.append(('RECEIPT_DIGEST_SCHEME_STALE',
                    'row digests recorded under %s, this is %s'
                    % (scheme or '(absent)', ROWS_DIGEST_SCHEME)))
    for key, code, where in (
            ('protocol_sha256', 'RECEIPT_PROTOCOL_STALE', core),
            ('writer_code_sha256', 'RECEIPT_WRITER_CODE_STALE', caller),
            ('study_inputs_sha256', 'RECEIPT_STUDY_INPUTS_STALE', caller)):
        want = expected.get(key)
        if want is None:
            continue
        got = where.get(key)
        if got != want:
            out.append((code, '%s recorded %s, tree has %s'
                        % (key, (got or '(absent)')[:12], want[:12])))
    for name, want in (expected.get('sources') or {}).items():
        got = (caller.get('sources') or {}).get(name)
        if got != want:
            out.append(('RECEIPT_SOURCE_STALE',
                        '%s recorded %s, tree has %s'
                        % (name, (got or '(absent)')[:12], want[:12])))
    for label, want in (expected.get('tables') or {}).items():
        got = (core.get('tables') or {}).get(label, {}).get('file_sha256')
        if got != want:
            out.append(('RECEIPT_TABLE_STALE',
                        '%s recorded %s, tree has %s'
                        % (label, (got or '(absent)')[:12], want[:12])))
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
        # A DESTINATION THAT DID NOT EXIST HAS NO BACKUP TO RESTORE, and
        # leaving it is not "as it was": the first file being new was the case
        # the rollback silently skipped, so a failure on the second commit left
        # a file behind that had never been there.
        for path in replaced:
            if path in backups and os.path.exists(backups[path]):
                os.replace(backups[path], path)
            elif path not in backups and os.path.exists(path):
                os.remove(path)
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


def file_digest(path):
    """sha256 of a file, or '' when it is not there yet."""
    import hashlib
    if not os.path.exists(path):
        return ''
    h = hashlib.sha256()
    with open(path, 'rb') as fh:
        for chunk in iter(lambda: fh.read(65536), b''):
            h.update(chunk)
    return h.hexdigest()


#: Bumped when the serialisation below changes. An attestation carries it, so
#: a receipt written under one scheme cannot be silently compared with a digest
#: computed under another - the mismatch is a mismatch, and says so.
ROWS_DIGEST_SCHEME = "fdt-rows-digest-2"


def _cell(v):
    """A value as the file will carry it.

    csv.DictWriter writes str(v) and writes None as the empty field, and
    everything read back is text. A digest that distinguishes 1 from "1", or
    None from "", disagrees with the file it is supposed to stand for: a rerun
    that parsed a column slightly differently would read as a changed table
    while the bytes on disk are identical.
    """
    return '' if v is None else str(v)


def rows_digest(rows, fields):
    """sha256 of the rows a writer intends, under the fields that matter.

    CANONICAL, NOT repr(). repr's output is a property of the running
    interpreter - container reprs, str/unicode prefixes, float formatting -
    and this digest goes into a receipt that a later run, on a later
    interpreter, is expected to reproduce. `sorted(r.items())` also fixed only
    the key order inside one row while leaving the rest to repr.

    The stream is the scheme name, the field list as a JSON array, then one
    JSON object per row with sorted keys. No length framing: a JSON array and
    a JSON object cannot be confused for one another or split differently, so
    the concatenation has exactly one reading. Row order is part of the digest
    on purpose - it is part of the file.
    """
    import hashlib
    h = hashlib.sha256()

    def feed(obj):
        h.update(json.dumps(obj, ensure_ascii=False, sort_keys=True,
                            separators=(',', ':')).encode('utf-8'))

    h.update(ROWS_DIGEST_SCHEME.encode('utf-8'))
    feed(list(fields))
    for r in rows:
        feed({k: _cell(v) for k, v in r.items() if not k.startswith('_')})
    return h.hexdigest()


def _refuse(receipt_dir, name, verdict, key, labels):
    """Record a refusal that happened before any table was touched."""
    os.makedirs(receipt_dir, exist_ok=True)
    json.dump({'verdict': verdict, key: labels},
              io.open(os.path.join(receipt_dir, '%s_idempotency.json' % name),
                      'w', encoding='utf-8'), indent=2)
    print('  판정: %s (%s)' % (verdict, ', '.join(labels)))
    return verdict, []


def load_csv_snapshot(path):
    """A table's columns, rows and digest, from ONE read of its bytes.

    THE DIGEST HAS TO BE OF WHAT WAS PARSED. The stale-snapshot check compares
    what the caller read against what is on disk inside the lock - but it was
    handed a digest computed at the call site, long after the rows had been
    read and usually after minutes of parsing source documents. Another writer
    committing in that gap left the caller holding OLD rows and a NEW digest,
    which is the one pair the check reads as fresh. It would then replace the
    whole table from rows that never saw the other writer's work, and the
    guard would have signed it off.

    Reading the bytes once and digesting those bytes closes the gap without
    holding the lock across the parsing.
    """
    import hashlib
    if not os.path.exists(path):
        return None, [], ''
    with open(path, 'rb') as fh:
        raw = fh.read()
    rd = csv.DictReader(io.StringIO(raw.decode('utf-8-sig')))
    return rd.fieldnames, list(rd), hashlib.sha256(raw).hexdigest()


def persisted_digest(rows, fields):
    """The digest of these rows AS THE FILE CARRIES THEM.

    `intended_rows_sha256` is taken over the rows as the writer holds them,
    transients and all, and before the ordinals are minted. It cannot be
    recomputed by anything downstream that has only the file. This one is
    taken over `writable(rows, fields)` - the exact dicts the CSV writer
    serialises - so a consumer holding the rows and the file's columns can
    arrive at the same number and prove it is looking at the same rows.
    """
    return rows_digest(writable(rows, fields), fields)


def json_digest(payload):
    """sha256 of a JSON payload, canonically.

    The object in memory and the file it was written to have to give the same
    number, or indentation would read as a changed sidecar. Same scheme tag
    and same serialisation as rows_digest, for the same reason.
    """
    import hashlib
    return hashlib.sha256(
        (ROWS_DIGEST_SCHEME + json.dumps(payload, ensure_ascii=False,
                                         sort_keys=True,
                                         separators=(',', ':')))
        .encode('utf-8')).hexdigest()


def _without(payload, volatile):
    """A payload minus the keys a writer declared it cannot re-derive."""
    if not volatile or not isinstance(payload, dict):
        return payload
    return {k: v for k, v in payload.items() if k not in set(volatile)}


def sidecar_problems(receipt, files, volatile=None):
    """Sidecars on disk that are not the ones this receipt's run produced.

    A SIDECAR IS OUTSIDE THE TRANSACTION. The tables commit together or not at
    all, but the JSON files beside them - the rows handed to the workbook
    step, the held estimates handed to a reviewer - are written by a plain
    dump after it, or in one case before it. Nothing tied them to the run that
    was supposed to have produced them, so a file left by an earlier run, or
    one written while the guard was refusing to write at all, read as this
    run's output to everything downstream.

    The writer records each payload's digest in its receipt, via
    `attest_sidecars`, after writing the files. Here the file on disk is
    parsed and digested the same way and compared, so a sidecar that does not
    belong to this receipt is named rather than believed.

    `files` is {name recorded in the attestation: path on disk}. `volatile`
    is {name: keys the CALLER allows to be left out of the digest}; anything
    the receipt declares beyond that is a mismatch, not a permission. The
    receipt used to name its own volatile keys and be believed, so adding
    `refused_values` to that list and then changing it passed every check -
    the scope of the proof set, again, by the thing being proved.
    """
    allowed = volatile or {}
    out = []
    for name, path in sorted(files.items()):
        if not os.path.exists(path):
            out.append(('SIDECAR_MISSING',
                        '%s is attested and is not on disk' % name))
            continue
        try:
            payload = json.load(io.open(path, encoding='utf-8'))
        except ValueError as exc:
            out.append(('SIDECAR_UNREADABLE', '%s: %s' % (name, exc)))
            continue
        out += sidecar_payload_problems(receipt, name, payload, volatile)
    return out


def sidecar_payload_problems(receipt, name, payload, volatile=None):
    """The same judgement, on a payload the caller already holds.

    READ ONCE, CHECK AND USE THE SAME OBJECT. A consumer that verified the
    file and then opened it again to apply it verified one thing and applied
    another if anything touched the file in between - the same gap that was
    closed for the CSVs by digesting the bytes that were parsed. `files` above
    is for readers that only want the verdict; anything that goes on to ACT on
    a sidecar passes the object it will act on.
    """
    allowed = volatile or {}
    recorded = (receipt or {}).get('sidecars') or {}
    out = []
    record = recorded.get(name)
    if record is None:
        return [('SIDECAR_NOT_ATTESTED',
                 '%s is expected and the receipt does not name it' % name)]
    if not isinstance(record, dict):
        record = {'sha256': record, 'volatile': []}
    declared = tuple(sorted(record.get('volatile') or ()))
    permitted = tuple(sorted(allowed.get(name) or ()))
    if declared != permitted:
        return [('SIDECAR_VOLATILE_SET_MISMATCH',
                 '%s leaves out %s, the contract allows %s'
                 % (name, list(declared), list(permitted)))]
    # Digested under what the CONTRACT allows, not what the receipt claims -
    # they are equal by the check above, and this says which is the authority.
    got = json_digest(_without(payload, permitted))
    if got != record.get('sha256'):
        out.append(('SIDECAR_STALE', '%s recorded %s, this payload is %s'
                    % (name, (record.get('sha256') or '(absent)')[:12],
                       got[:12])))
    return out


def attest_sidecars(receipt_dir, name, payloads, volatile=None):
    """Record in this writer's receipt what the sidecars it wrote contain.

    AFTER THE FILES, NOT BEFORE. Part of what a sidecar carries - an ordinal
    minted during the write - does not exist until the write has happened, so
    there is nothing to attest beforehand. If the process dies between the
    file and this amendment, the sidecar is unattested, and an unattested
    sidecar is reported as a problem rather than accepted: the gap fails
    closed.
    """
    # MERGED, NOT REPLACED. A rerun rewrites only the sidecars it has content
    # for; an ordinal minted by the run that actually wrote the tables is not
    # in this run's hands. Replacing the map would drop the entry for a file
    # that is still there and still correct, and an unattested file reads as a
    # problem.
    # SOME OF A SIDECAR IS THE RUN, NOT THE WORK. integration.json records the
    # date, the verdict and where the previous tables were archived - the run's
    # own identity, which a later run cannot re-derive and must not overwrite.
    # A writer may declare those keys volatile; they are then left out of the
    # digest and NAMED IN THE RECEIPT, so what is bound and what is not is
    # readable rather than assumed. Everything else is bound as before.
    vol = volatile or {}
    keep = _read_receipt(receipt_dir, name).get('sidecars') or {}
    keep.update({k: {'sha256': json_digest(_without(v, vol.get(k))),
                     'volatile': sorted(vol.get(k) or ())}
                 for k, v in payloads.items()})
    _amend_receipt(receipt_dir, name, {'sidecars': keep})


class Locked(Exception):
    """Another writer holds the lock."""


#: The same exclusive lock the writers take, for anything else that has to be
#: alone with the bundle - the workbook step above all, which mutates a file
#: the CSVs are compared against.
def write_lock(path):
    return _Lock(path)


class _Lock(object):
    """Exclusive for the whole transaction, guard to final replace.

    Two processes reading the same tables both see them empty and are both told
    to WRITE; the second then appends what the first has already written. The
    guard cannot see that, because each is telling the truth about the moment
    it looked.

    HELD WITH `flock`, NOT BY THE FILE'S EXISTENCE. An O_EXCL lock file has to
    be DELETED to be released, and the filesystem this runs against refuses
    deletes - so the first writer to take one could never give it back, and
    every later run failed with "another writer holds it" pointing at a process
    that had finished. `flock` is released when the descriptor closes, whatever
    the filesystem permits, and a leftover lock file holds nothing.
    """

    def __init__(self, path):
        self.path = path
        self.fd = None

    def __enter__(self):
        if not self.path:
            return self
        import fcntl
        self.fd = os.open(self.path, os.O_CREAT | os.O_RDWR, 0o600)
        try:
            fcntl.flock(self.fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            os.close(self.fd)
            self.fd = None
            raise Locked('another writer holds %s' % self.path)
        os.ftruncate(self.fd, 0)
        os.write(self.fd, ('%d\n' % os.getpid()).encode('ascii'))
        return self

    def __exit__(self, *exc):
        if self.fd is not None:
            import fcntl
            try:
                fcntl.flock(self.fd, fcntl.LOCK_UN)
            finally:
                os.close(self.fd)
                self.fd = None
        return False


def run_writer(name, tables, receipt_dir, assign_ids=None, archive=None,
               journal_path=None, replace=None, relations=(),
               assignable=None, dry_run=False, lock_path=None,
               attest=None, read_digests=None, sidecars=None):
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
    with _Lock(lock_path):
        # THE SNAPSHOT WAS TAKEN OUTSIDE THE LOCK. A caller reads the tables,
        # builds its rows, and only then asks to write; another writer can
        # finish in between, and this one would replace the whole table from a
        # picture taken before that - dropping rows it never saw. The lock
        # alone does not close it, because the read happened before the lock.
        # What the caller read is compared with what is there now, inside it.
        stale = [label for label, path, _f, _e, _i, _k, _v in tables
                 if (read_digests or {}).get(label) is not None
                 and (read_digests or {})[label] != file_digest(path)]
        if stale:
            return _refuse(receipt_dir, name, 'STALE_EXISTING_SNAPSHOT',
                           'stale_tables', stale)
        # AND THE ROWS HAVE TO BE THE ROWS THAT DIGEST DESCRIBES. Matching
        # digests only prove the file has not moved since the digest was
        # taken - not that the caller's rows came from it. A caller that read
        # its rows early and took the digest late (which is what both writers
        # did: rows first, then minutes of document parsing, then the digest
        # at the call) holds old rows and a current digest, and that is the
        # one pair this check used to read as fresh. The whole table would
        # then be replaced from rows that never saw the other writer's work.
        # Inside the lock the file IS what the digest says, so its rows are
        # what `existing` has to be.
        disagree = []
        for label, path, _f, existing, _i, _k, _v in tables:
            if (read_digests or {}).get(label) is None:
                continue
            on_file_cols, on_file, _d = load_csv_snapshot(path)
            cols = on_file_cols or ()
            if len(on_file) != len(existing) or not all(
                    all((a.get(c) or '') == (b.get(c) or '') for c in cols)
                    for a, b in zip(on_file, existing)):
                disagree.append(label)
        if disagree:
            return _refuse(receipt_dir, name, 'SNAPSHOT_ROWS_DISAGREE',
                           'disagreeing_tables', disagree)
        verdict, written = _run_writer(name, tables, receipt_dir, assign_ids,
                                       archive, journal_path, replace,
                                       relations, assignable, dry_run, attest)
        # THE FILES BESIDE THE TABLES ARE PART OF THE TRANSACTION. They used to
        # be written after run_writer returned - which is after the lock was
        # released - so two runs could interleave into a state neither of them
        # produced: one commits its tables, the other commits its own, and the
        # first then writes ITS sidecar and merges ITS digest into the other's
        # receipt. Built and recorded here, they cannot outlive the lock that
        # the tables were written under.
        #
        # `sidecars(verdict, written)` returns {filename: payload}. It is
        # called after the ordinals exist - minted on a write, read back off
        # the files on a clean rerun - and the payloads are written only when
        # this run is the one that wrote the tables.
        # WHAT THE ROWS BECAME, RECORDED AFTER THEY BECAME IT. The
        # attestation above is written before the ordinals exist, so nothing
        # in it describes the rows that are actually in the file. A consumer -
        # the workbook step - could check that the sidecar was attested and
        # that the CSV hash matched, and still not know the sidecar held THESE
        # rows: a producer recording a correct file hash beside a sidecar full
        # of different rows passed both checks.
        if verdict in ('WRITE', CLEAN_RERUN):
            _amend_receipt(receipt_dir, name, {'persisted': {
                label: {'rows_sha256': persisted_digest(intended, fields),
                        'rows': len(intended),
                        'fields': list(fields)}
                for label, _p, fields, _e, intended, _k, _v in tables}})
        if sidecars is not None and verdict in ('WRITE', CLEAN_RERUN):
            payloads = sidecars(verdict, written)
            volatile = getattr(sidecars, 'volatile', None)
            if verdict == 'WRITE':
                for fname, payload in sorted(payloads.items()):
                    json.dump(payload,
                              io.open(os.path.join(receipt_dir, fname), 'w',
                                      encoding='utf-8'),
                              indent=2, ensure_ascii=False)
            attest_sidecars(receipt_dir, name, payloads, volatile)
        return verdict, written


def _run_writer(name, tables, receipt_dir, assign_ids, archive, journal_path,
                replace, relations, assignable, dry_run, attest):
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
    # WHAT THE VERDICT IS A VERDICT ABOUT. A receipt that records only its
    # verdict says nothing about which code, which inputs and which files it
    # was reached from - so an old ALREADY_PRESENT_NO_WRITE reads as proof of
    # a rerun that has not happened. These are what would have to be the same
    # for the verdict to still hold.
    attestation = {
        'generated': __import__('datetime').datetime.now().isoformat(
            timespec='seconds'),
        'protocol_sha256': file_digest(os.path.abspath(__file__)),
        # WHICH SERIALISATION THE ROW DIGESTS BELOW ARE IN. Without it a
        # receipt written under an older scheme compares as a changed table,
        # and the reader has no way to tell that apart from rows that really
        # moved.
        'rows_digest_scheme': ROWS_DIGEST_SCHEME,
        'tables': {label: {'file_sha256': file_digest(path),
                           'intended_rows_sha256': rows_digest(intended, fields),
                           'intended_rows': len(intended),
                           'existing_rows': len(existing)}
                   for label, path, fields, existing, intended, _k, _v in tables},
    }
    # THE CALLER'S CLAIMS SIT BESIDE THE CORE ONES, NOT OVER THEM. A caller
    # that happened to pass `protocol_sha256` or `tables` would otherwise
    # overwrite what this function measured with what it asserts.
    attestation = {'core': attestation, 'caller': dict(attest or {})}
    _amend_receipt(receipt_dir, name, {'attestation': attestation})
    if not may:
        verdict = _last_verdict(receipt_dir, name)
        # THE CALLER'S ROWS SHOULD CARRY THE IDS THEY HAVE ON FILE. On a write
        # `assign_ids` stamps them; on a clean rerun nothing does, so a caller
        # that builds anything from those rows afterwards - a sidecar handed
        # to the workbook step, a receipt - writes blanks where the table has
        # ordinals, and the two disagree for a reason that is not a defect in
        # either. The guard has just proven every intended row is already on
        # file under its natural key, so the ordinal is there to be read.
        # Reading it is not minting one.
        if verdict == CLEAN_RERUN and assignable:
            for _l, _p, _f, existing, intended, kf, _v in tables:
                index = {}
                for r in existing:
                    index.setdefault(key_of(r, kf), r)
                for r in intended:
                    match = index.get(key_of(r, kf))
                    for f in assignable:
                        # Unconditionally: an ordinal is a position in a
                        # file, and it is left out of the comparison for that
                        # reason. Whatever a caller brought under that name is
                        # not a competing claim, so there is nothing to
                        # arbitrate - the file says where the row is.
                        if match and f in match:
                            r[f] = match[f]
        return verdict, []
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
        # THE ROWS ALREADY ON FILE ARE NOT THE CALLBACK'S EITHER, and it is
        # handed them. Nothing in them may move - they were not judged as
        # something to write, they are what is already there, and they go back
        # out with the new rows.
        before_existing = {label: _snapshot(existing, set())
                           for label, _p, _f, existing, _i, _k, _v in tables}
        for label, _p, _f, existing, intended, _k, _v in tables:
            assign_ids(label, existing, intended)
        for label, _p, _f, existing, _i, _k, _v in tables:
            if _snapshot(existing, set()) != before_existing[label]:
                raise SchemaError(
                    'assign_ids changed a row already on file in %s; the rows '
                    'it is given to read are not its to edit' % label)
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


def read_receipt(receipt_dir, name):
    """A writer's receipt as a dict, {} if it is not there or not readable."""
    return _read_receipt(receipt_dir, name)


def _read_receipt(receipt_dir, name):
    try:
        return json.load(io.open(os.path.join(
            receipt_dir, '%s_idempotency.json' % name), encoding='utf-8'))
    except Exception:
        return {}


def _amend_receipt(receipt_dir, name, extra):
    path = os.path.join(receipt_dir, '%s_idempotency.json' % name)
    d = _read_receipt(receipt_dir, name)
    d.update(extra)
    os.makedirs(receipt_dir, exist_ok=True)
    json.dump(d, io.open(path, 'w', encoding='utf-8'), indent=2,
              ensure_ascii=False)


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
