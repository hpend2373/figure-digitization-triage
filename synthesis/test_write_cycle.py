# -*- coding: utf-8 -*-
"""The four phases of a write, which a rerun alone never reaches.

    python3 test_write_cycle.py      # exit 0 = all scenarios pass

WHY THIS FILE EXISTS. Every defect that reached the extraction tables lived in
the ORDER of a write, not in any one step: ordinals minted before the guard, so
a rerun died on its own previous output; a field added for the guard reaching
the CSV writer, so the first table was written and the second raised; a table
already full beside a table still empty, which the guard called WRITE. None of
them are reachable by running a writer that has already run - a clean no-op
returns before the write branch, and every run after the first one is a no-op.
So each was found by hand, once, and only after it had shipped.

The protocol is one function now (`rowkey.run_writer`), and this drives it
through the four states a real writer passes through:

    nothing written yet   -> writes, and numbers the rows only then
    written already       -> a no-op, and the files do not move
    one table, not both   -> writes nothing, and says which disagrees
    failure part way      -> writes nothing, and leaves no half-written file

Reads and writes only a temporary directory: no bundle, no corpus, no network.
"""
import csv
import io
import json
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rowkey as K                                              # noqa: E402

FAIL, N = [], [0]
TMP = tempfile.mkdtemp(prefix="fdt_cycle_")


def check(name, ok, detail=''):
    print(('  ok   ' if ok else '  FAIL ') + name + ('' if ok else '  <- ' + detail))
    if ok:
        N[0] += 1
    else:
        FAIL.append(name)


COLS = ['row_id', 'effect_row_id', 'rec_id', 'source_sha256', 'source_page_ref',
        'population_subgroup', 'exposure_definition', 'outcome_name',
        'outcome_timepoint', 'analysis_variant', 'effect_measure',
        'effect_point', 'human_confirmed']
KEY = K.EFFECT_KEY
VALUE = ('effect_point',)


def row(n, point='1.0'):
    return {'rec_id': 'R1', 'source_sha256': 'sha', 'source_page_ref': 'T1',
            'population_subgroup': 'all', 'exposure_definition': 'drug %d' % n,
            'outcome_name': 'outcome', 'outcome_timepoint': '',
            'analysis_variant': 'adjusted', 'effect_measure': 'HR',
            'effect_point': point, 'human_confirmed': 'no',
            # THE FIELD THAT BROKE THE FIRST WRITE. Added so both sides can
            # name a parent the same way; not a column of any file.
            'parent_effect_key': ''}


def fresh(name, rows=()):
    path = os.path.join(TMP, name)
    with io.open(path, 'w', encoding='utf-8', newline='') as fh:
        w = csv.DictWriter(fh, fieldnames=COLS)
        w.writeheader()
        w.writerows(K.writable(rows, COLS))
    return path


def read(path):
    with io.open(path, encoding='utf-8-sig') as fh:
        return list(csv.DictReader(fh))


NUMBERED = []


def number(label, existing, intended):
    """Stand-in for the writers' ordinal assignment, and a witness to WHEN."""
    NUMBERED.append(label)
    start = len(existing)
    for i, r in enumerate(intended, start=start + 1):
        r['row_id'] = '%s-%03d' % (label, i)


print("the four phases of a write")

# ---------------------------------------------------------------- phase one
A, B = fresh('a.csv'), fresh('b.csv')
new_a, new_b = [row(1), row(2)], [row(3)]
del NUMBERED[:]
verdict, written = K.run_writer(
    'cycle', [('a', A, COLS, [], new_a, KEY, VALUE),
              ('b', B, COLS, [], new_b, KEY, VALUE)], TMP, assign_ids=number, assignable={'row_id'})
check("nothing written yet, so it writes", verdict == 'WRITE', verdict)
check("and both files receive their rows",
      len(read(A)) == 2 and len(read(B)) == 1,
      "%d / %d" % (len(read(A)), len(read(B))))
check("the rows are numbered, and only once the guard has said to write",
      NUMBERED == ['a', 'b'] and read(A)[0]['row_id'] == 'a-001',
      "%s" % NUMBERED)
check("the field that is not a column did not reach the file",
      'parent_effect_key' not in read(A)[0])

# ---------------------------------------------------------------- phase two
before = (read(A), read(B))
del NUMBERED[:]
verdict, written = K.run_writer(
    'cycle', [('a', A, COLS, read(A), [row(1), row(2)], KEY, VALUE),
              ('b', B, COLS, read(B), [row(3)], KEY, VALUE)], TMP,
    assign_ids=number, assignable={'row_id'})
check("written already, so it is a no-op",
      verdict == 'ALREADY_PRESENT_NO_WRITE', verdict)
check("nothing is written on a no-op", written == [])
check("and no ordinal is minted either - an id claims a row that may not exist",
      NUMBERED == [], "%s" % NUMBERED)
check("the files are exactly as they were",
      (read(A), read(B)) == before)

# A CLEAN RERUN STILL HAS TO HAND BACK THE ORDINALS. Nothing stamps the
# caller's rows when no write happens, so anything built from them afterwards -
# the sidecar the workbook step applies - carried blanks where the table has
# ids. The guard has just proven every row is on file; reading its id is not
# minting one.
_rerun = [row(1), row(2)]
_v, _w = K.run_writer(
    'cycle', [('a', A, COLS, read(A), _rerun, KEY, VALUE),
              ('b', B, COLS, read(B), [row(3)], KEY, VALUE)], TMP,
    assign_ids=number, assignable={'row_id'})
check("a clean rerun hands back the ids the rows have on file",
      all(r.get('row_id') for r in _rerun)
      and {r['row_id'] for r in _rerun} == {r['row_id'] for r in read(A)},
      "%s" % [r.get('row_id') for r in _rerun])
check("without minting one or writing anything",
      (_v, _w, NUMBERED) == (K.CLEAN_RERUN, [], []),
      "%s %s %s" % (_v, _w, NUMBERED))
check("still a no-op on the files",
      (read(A), read(B)) == before)
# AN ORDINAL IS A POSITION IN A FILE, NOT SOMETHING A CALLER BRINGS. It is
# left out of the comparison by design, so a row that arrives carrying a
# different one is still the same row - and the file is what says where it is.
_E = fresh('e.csv', [dict(row(5), effect_row_id='e-777')])
_brought = dict(row(5), effect_row_id='caller-made-this')
_v = K.run_writer('brought',
                  [('e', _E, COLS, read(_E), [_brought], KEY, VALUE)], TMP,
                  assignable={'effect_row_id'})[0]
check("a row that arrived with another ordinal is still a clean rerun",
      _v == K.CLEAN_RERUN, _v)
check("and comes back carrying the ordinal the file has",
      _brought['effect_row_id'] == 'e-777', _brought['effect_row_id'])

# -------------------------------------------------------------- phase three
C = fresh('c.csv', [dict(row(1), row_id='c-001')])
D = fresh('d.csv')
verdict, written = K.run_writer(
    'cycle', [('c', C, COLS, read(C), [row(1)], KEY, VALUE),
              ('d', D, COLS, [], [row(9)], KEY, VALUE)], TMP,
    assign_ids=number, assignable={'row_id'})
check("one table done and another empty writes nothing",
      verdict == 'CONFLICT_NO_WRITE', verdict)
check("and the empty one stays empty", read(D) == [])
_rep = json.load(io.open(os.path.join(TMP, 'cycle_idempotency.json'),
                         encoding='utf-8'))
check("the receipt says which table is in which state",
      _rep['table_states'] == {'c': K.IDENTICAL, 'd': K.EMPTY},
      "%s" % _rep['table_states'])

# --------------------------------------------------------------- phase four
# THE FIRST VERSION OF THIS PHASE NEVER REACHED THE WRITE. It passed a list
# whose __iter__ raised, and `guard` iterates the intended rows before any file
# is touched - so the exception came out of the guard, the assertions about
# rollback passed because nothing had been written, and `write_all_or_nothing`
# still had no scenario for the thing it is named after. The two below fail
# INSIDE the write: one while staging, one while replacing.

# (a) staging: the second file's directory does not exist.
E = fresh('e.csv', [dict(row(1), row_id='e-001')])
MISSING = os.path.join(TMP, 'no-such-dir', 'f.csv')
raised = False
try:
    K.run_writer('cycle', [('e', E, COLS, read(E), [row(2)], KEY, VALUE),
                           ('f', MISSING, COLS, [], [row(3)], KEY, VALUE)],
                 TMP, assign_ids=number, assignable={'row_id'})
except (OSError, IOError):
    raised = True
check("a staging failure on the second file raises", raised)
check("and the first file still holds only its original row",
      len(read(E)) == 1, "%d" % len(read(E)))
check("no half-written file is left beside either",
      not [f for f in os.listdir(TMP) if f.endswith('.writing')],
      "%s" % [f for f in os.listdir(TMP) if f.endswith('.writing')])

# (b) commit: every file stages, and the SECOND replace fails. This is the one
# that used to leave the first table new and the second old.
G = fresh('g.csv', [dict(row(1), row_id='g-001')])
H = fresh('h.csv', [dict(row(2), row_id='h-001')])
before_g, before_h = read(G), read(H)
JOURNAL = os.path.join(TMP, 'journal.json')
moves = []


def flaky_replace(src, dst):
    moves.append(dst)
    if len(moves) == 2:
        raise OSError('injected failure on the second replace')
    os.replace(src, dst)


raised = False
try:
    K.run_writer('cycle', [('g', G, COLS, read(G), [row(3)], KEY, VALUE),
                           ('h', H, COLS, read(H), [row(4)], KEY, VALUE)],
                 TMP, assign_ids=number, assignable={'row_id'}, journal_path=JOURNAL,
                 replace=flaky_replace)
except OSError:
    raised = True
check("a failure on the SECOND replace raises", raised)
check("the first file is put back, not left one commit ahead",
      read(G) == before_g, "%s" % read(G))
check("and the second is untouched", read(H) == before_h)
check("no temporary or backup file survives",
      not [f for f in os.listdir(TMP)
           if f.endswith(('.writing', '.previous'))],
      "%s" % [f for f in os.listdir(TMP)
              if f.endswith(('.writing', '.previous'))])
check("the journal says the transaction was rolled back",
      json.load(io.open(JOURNAL, encoding='utf-8'))['state']
      == 'ABORTED_ROLLED_BACK')

# (c) a clean commit records itself, so an interrupted run is visible
K.run_writer('cycle', [('g', G, COLS, read(G), [row(5)], KEY, VALUE)],
             TMP, assign_ids=number, assignable={'row_id'}, journal_path=JOURNAL)
_j = json.load(io.open(JOURNAL, encoding='utf-8'))
check("a clean commit leaves a COMMITTED journal", _j['state'] == 'COMMITTED')
check("with a hash of what it wrote", bool(list(_j['sha256'].values())[0]))
check("and the row really is there now", len(read(G)) == 2)

# ------------------------------------------- the checks before any of that
# A PARENT REFERENCE IS RESOLVED AND CHECKED BEFORE A ROW IS NUMBERED OR
# WRITTEN. The supplement writer used to call annotate_parents itself and
# discard what it returned, so a dangling or duplicated parent arrived at the
# guard as an ordinary unmatched key.
PARENT = fresh('parent.csv', [dict(row(1), row_id='p-001', effect_row_id='x-1'),
                              dict(row(2), row_id='p-002', effect_row_id='x-1')])
CHILD = fresh('child.csv')
verdict, written = K.run_writer(
    'cycle', [('child', CHILD, COLS, [], [dict(row(3), effect_row_id='x-1')],
               K.COUNT_KEY, K.COUNT_VALUE),
              ('parent', PARENT, COLS, read(PARENT), [], KEY, VALUE)],
    TMP, relations=[('child', 'parent')], assign_ids=number,
    assignable={'row_id'})
check("an ordinal used by two parents stops the transaction before it starts",
      verdict == 'PREFLIGHT_CONFLICT_NO_WRITE', verdict)
check("and nothing is written", written == [] and read(CHILD) == [])
_pre = json.load(io.open(os.path.join(TMP, 'cycle_idempotency.json'),
                         encoding='utf-8'))
check("the receipt names what the preflight found",
      any(x[0] == 'DUPLICATE_EFFECT_ROW_ID' for x in _pre['preflight_problems']),
      "%s" % _pre['preflight_problems'][:2])

DANGLING = fresh('dangling.csv')
ONE = fresh('one.csv', [dict(row(1), row_id='p-001', effect_row_id='x-9')])
verdict, _w = K.run_writer(
    'cycle', [('child', DANGLING, COLS, [],
               [dict(row(3), effect_row_id='nowhere')],
               K.COUNT_KEY, K.COUNT_VALUE),
              ('parent', ONE, COLS, read(ONE), [], KEY, VALUE)],
    TMP, relations=[('child', 'parent')], assign_ids=number,
    assignable={'row_id'})
check("a parent that is not in the table stops it too",
      verdict == 'PREFLIGHT_CONFLICT_NO_WRITE'
      and any(x[0] == 'UNKNOWN_PARENT_EFFECT_ROW_ID' for x in
              json.load(io.open(os.path.join(TMP, 'cycle_idempotency.json'),
                                encoding='utf-8'))['preflight_problems']),
      verdict)
check("a sound parent reference passes the preflight and writes",
      K.run_writer('cycle',
                   [('child', fresh('ok.csv'), COLS, [],
                     [dict(row(3), effect_row_id='x-9')],
                     K.COUNT_KEY, K.COUNT_VALUE),
                    ('parent', ONE, COLS, read(ONE), [], KEY, VALUE)],
                   TMP, relations=[('child', 'parent')], assign_ids=number,
                   assignable={'row_id'})[0] == 'WRITE')

# A CALLBACK MAY SET AN ORDINAL AND NOTHING ELSE.
MEDDLED = fresh('meddled.csv')


def meddling(_label, _existing, intended):
    intended[0]['row_id'] = 'm-001'
    intended[0]['effect_point'] = '999'


raised = False
try:
    K.run_writer('cycle', [('m', MEDDLED, COLS, [], [row(1)], KEY, VALUE)], TMP,
                 assign_ids=meddling, assignable={'row_id'})
except K.SchemaError:
    raised = True
check("a callback that changes a judged field is refused", raised)
check("and its file is not written", read(MEDDLED) == [])

# A FIELD THE FILE HAS NO COLUMN FOR IS DRIFT, NOT A TRANSIENT.
DRIFT = fresh('drift.csv')
raised = False
try:
    K.run_writer('cycle', [('d', DRIFT, COLS, [],
                            [dict(row(1), new_provenance_field='x')],
                            KEY, VALUE)], TMP, assign_ids=number,
                 assignable={'row_id'})
except K.SchemaError:
    raised = True
check("an undeclared extra field stops the write", raised)
check("before its file is touched", read(DRIFT) == [])
check("while a declared transient passes through",
      K.writable([dict(row(1), parent_effect_key='k')], COLS)[0].get('row_id')
      is not None)

# ------------------------------------------- the path that does not write
# ONE PATH, INCLUDING THE ONE THAT DOES NOT WRITE. A dry run used to call
# `guard` directly and skip `run_writer` entirely, so every check that lives
# there - the parent resolution above all - never ran on the path a person
# actually invokes while watching the output. Against the real tables it
# reported 44 counts as missing: an artefact of parents nobody had resolved,
# not a fact about the data.
DRY_P = fresh('dry_parent.csv', [dict(row(1), row_id='d-001',
                                      effect_row_id='e-1')])
DRY_C = fresh('dry_child.csv')
DRY_CHILD_ROW = dict(row(2), effect_row_id='e-1')
verdict, written = K.run_writer(
    'dry', [('child', DRY_C, COLS, [], [DRY_CHILD_ROW],
             K.COUNT_KEY, K.COUNT_VALUE),
            ('parent', DRY_P, COLS, read(DRY_P), [], KEY, VALUE)],
    TMP, relations=[('child', 'parent')], dry_run=True)
check("a dry run reports what a write would do", verdict == 'WRITE_WOULD_PROCEED',
      verdict)
check("and writes nothing", written == [] and read(DRY_C) == [])
# THE ASSERTION THAT USED TO END IN `or True`, WHICH MADE IT PASS ON ANY CODE
# AT ALL - written into the very commit whose message says a scenario that
# cannot fail is not a scenario. It also watched the wrong table: the parent
# is what a child resolves AGAINST, so the resolved key belongs on the child.
check("the child's parent really was resolved on the way through",
      DRY_CHILD_ROW.get('parent_effect_key')
      == str(K.key_of(read(DRY_P)[0], K.EFFECT_KEY)),
      "%r" % DRY_CHILD_ROW.get('parent_effect_key'))
_dryv, _ = K.run_writer(
    'dry', [('child', DRY_C, COLS, [], [dict(row(2), effect_row_id='missing')],
             K.COUNT_KEY, K.COUNT_VALUE),
            ('parent', DRY_P, COLS, read(DRY_P), [], KEY, VALUE)],
    TMP, relations=[('child', 'parent')], dry_run=True)
check("so a dry run still refuses a broken parent reference",
      _dryv == 'PREFLIGHT_CONFLICT_NO_WRITE', _dryv)

# --------------------------------------- what the verdict is a verdict about
# A RECEIPT THAT RECORDS ONLY ITS VERDICT SAYS NOTHING ABOUT WHAT IT JUDGED.
# Change the code, the inputs, or the files, and an old
# ALREADY_PRESENT_NO_WRITE still reads as proof of a rerun that never happened.
AT = fresh('attest.csv')
K.run_writer('att', [('a', AT, COLS, [], [row(1)], KEY, VALUE)], TMP,
             assign_ids=number, assignable={'row_id'}, dry_run=True,
             attest={'study_inputs_sha256': 'abc'})
_r = json.load(io.open(os.path.join(TMP, 'att_idempotency.json'),
                       encoding='utf-8')).get('attestation', {})
_a = _r.get('core', {})
_c = _r.get('caller', {})
check("the receipt records which protocol reached the verdict",
      len(_a.get('protocol_sha256', '')) == 64)
check("and the hash of each file it judged against",
      'file_sha256' in _a.get('tables', {}).get('a', {}))
check("and a hash of the rows it intended to write",
      len(_a.get('tables', {}).get('a', {}).get('intended_rows_sha256', '')) == 64)
check("and whatever the caller attests to as well",
      _c.get('study_inputs_sha256') == 'abc')
check("a changed file gives a different hash, or the binding is decorative",
      K.file_digest(AT) != K.file_digest(fresh('attest2.csv', [row(1)])))
check("and changed rows give a different rows hash",
      K.rows_digest([row(1)], COLS) != K.rows_digest([row(2)], COLS))

# RECORDING IT AND CHECKING IT ARE TWO DIFFERENT PIECES OF WORK. Only the
# first was done: the verdict string was all anyone read, so deleting the
# attestation or changing what it was reached from left an old clean verdict
# reading as proof of a rerun that never happened.
_receipt = json.load(io.open(os.path.join(TMP, 'att_idempotency.json'),
                             encoding='utf-8'))
_now = {'protocol_sha256': _a.get('protocol_sha256'),
        'tables': {'a': _a.get('tables', {}).get('a', {}).get('file_sha256')},
        'study_inputs_sha256': 'abc'}
check("a receipt that still describes the tree has no problems",
      K.attestation_problems(_receipt, _now) == [],
      "%s" % K.attestation_problems(_receipt, _now))
check("a receipt with no attestation at all is a problem",
      [c for c, _d in K.attestation_problems({'verdict': 'x'}, _now)]
      == ['RECEIPT_ATTESTATION_MISSING'])
for _key, _code in (('protocol_sha256', 'RECEIPT_PROTOCOL_STALE'),
                    ('study_inputs_sha256', 'RECEIPT_STUDY_INPUTS_STALE')):
    check("a changed %s is named" % _key,
          _code in [c for c, _d in
                    K.attestation_problems(_receipt, dict(_now, **{_key: 'z' * 64}))])
check("a changed table file is named",
      'RECEIPT_TABLE_STALE' in
      [c for c, _d in K.attestation_problems(
          _receipt, dict(_now, tables={'a': 'z' * 64}))])
check("a changed source artifact is named",
      'RECEIPT_SOURCE_STALE' in
      [c for c, _d in K.attestation_problems(
          _receipt, dict(_now, sources={'supp.docx': 'z' * 64}))])
check("what the caller does not know about is not judged",
      K.attestation_problems(_receipt, {}) == [])

# THE SCHEME IS PART OF WHAT A DIGEST MEANS. rows_digest changed from repr()
# to canonical JSON; a receipt written before that carries numbers computed a
# different way, and comparing them would name every table stale for a reason
# that is not the tables'.
_old_scheme = json.loads(json.dumps(_receipt))
_old_scheme['attestation']['core'].pop('rows_digest_scheme', None)
check("a receipt whose row digests are in an older serialisation says so",
      'RECEIPT_DIGEST_SCHEME_STALE'
      in [c for c, _d in K.attestation_problems(_old_scheme, _now)])
check("and says it even when the caller can recompute nothing",
      'RECEIPT_DIGEST_SCHEME_STALE'
      in [c for c, _d in K.attestation_problems(_old_scheme, {})])
check("the scheme this run writes is the one it checks for",
      'RECEIPT_DIGEST_SCHEME_STALE'
      not in [c for c, _d in K.attestation_problems(_receipt, _now)])

# --- the files written beside the tables -------------------------------------
# THE TABLES COMMIT TOGETHER; THE SIDECARS DO NOT. new_rows.json is what the
# workbook step applies, and one of them is written before the guard has even
# spoken. A file left by an earlier run reads as this one's output unless
# something ties it to the run.

_side = os.path.join(TMP, 'side')
os.makedirs(_side, exist_ok=True)
_payload = {'rows': [['a', '1'], ['b', '2']], 'cols': ['k', 'v']}
_sp = os.path.join(_side, 'new_rows.json')
json.dump(_payload, io.open(_sp, 'w', encoding='utf-8'), ensure_ascii=False)
K.attest_sidecars(_side, 'sc', {'new_rows.json': _payload})
_att = json.load(io.open(os.path.join(_side, 'sc_idempotency.json'),
                         encoding='utf-8'))
check("the receipt records what the sidecar it wrote contains",
      _att['sidecars']['new_rows.json'] == K.json_digest(_payload))
check("a sidecar that is the payload the receipt attested passes",
      K.sidecar_problems(_att, {'new_rows.json': _sp}) == [],
      "%s" % K.sidecar_problems(_att, {'new_rows.json': _sp}))
json.dump(_payload, io.open(_sp, 'w', encoding='utf-8'), indent=2)
check("indentation is not a change, because the payload is what is compared",
      K.sidecar_problems(_att, {'new_rows.json': _sp}) == [])
json.dump({'rows': [['a', '9']], 'cols': ['k', 'v']},
          io.open(_sp, 'w', encoding='utf-8'))
check("a sidecar left by another run is named, not believed",
      [c for c, _d in K.sidecar_problems(_att, {'new_rows.json': _sp})]
      == ['SIDECAR_STALE'])
io.open(_sp, 'w', encoding='utf-8').write('{not json')
check("a sidecar that will not parse is a problem, not an exception",
      [c for c, _d in K.sidecar_problems(_att, {'new_rows.json': _sp})]
      == ['SIDECAR_UNREADABLE'])
check("an attested sidecar that is not there is named",
      [c for c, _d in K.sidecar_problems(
          _att, {'new_rows.json': os.path.join(_side, 'gone.json')})]
      == ['SIDECAR_MISSING'])
check("a sidecar the receipt never named is not silently accepted",
      [c for c, _d in K.sidecar_problems({'verdict': 'WRITE'},
                                         {'new_rows.json': _sp})]
      == ['SIDECAR_NOT_ATTESTED'])
check("a receipt that records none of them names every one",
      len(K.sidecar_problems({}, {'a.json': _sp, 'b.json': _sp})) == 2)

# --------------------------------------------------- one writer at a time
# Two processes reading the same tables both see them empty and are both told
# to WRITE; the second then appends what the first has already written. The
# guard cannot see that - each is telling the truth about the moment it looked.
LOCK = os.path.join(TMP, 'writer.lock')
L = fresh('locked.csv')
held = K._Lock(LOCK)
held.__enter__()
raised = False
try:
    K.run_writer('locked', [('a', L, COLS, [], [row(1)], KEY, VALUE)], TMP,
                 assign_ids=number, assignable={'row_id'}, lock_path=LOCK)
except K.Locked:
    raised = True
check("a second writer is refused while the lock is held", raised)
check("and it wrote nothing", read(L) == [])
held.__exit__()
# RELEASED BY CLOSING, NOT BY DELETING. The file stays; what matters is that
# the next writer can take it - which an O_EXCL lock could not do on a
# filesystem that refuses deletes.
_retaken = False
_again = K._Lock(LOCK)
try:
    _again.__enter__()
    _retaken = True
finally:
    _again.__exit__()
check("the lock can be taken again once it is released", _retaken)
check("and the writer runs once it is free",
      K.run_writer('locked', [('a', L, COLS, [], [row(1)], KEY, VALUE)], TMP,
                   assign_ids=number, assignable={'row_id'},
                   lock_path=LOCK)[0] == 'WRITE')
check("and a writer runs to completion while holding it",
      read(L) != [])

# ------------------------------- rollback when the first file was brand new
# A DESTINATION THAT DID NOT EXIST HAS NO BACKUP TO RESTORE. The rollback
# restored what it had copied aside and silently skipped the rest, so a first
# file created by the first replace stayed behind when the second failed. Both
# production tables already exist, which is why nothing had noticed.
NEWDEST = os.path.join(TMP, 'brand_new.csv')
OLDDEST = fresh('already_there.csv', [dict(row(1), row_id='o-001')])
before_old = read(OLDDEST)
moves2 = []


def fail_second(src, dst):
    moves2.append(dst)
    if len(moves2) == 2:
        raise OSError('injected failure on the second replace')
    os.replace(src, dst)


raised = False
try:
    K.run_writer('newdest',
                 [('new', NEWDEST, COLS, [], [row(2)], KEY, VALUE),
                  ('old', OLDDEST, COLS, read(OLDDEST), [row(3)], KEY, VALUE)],
                 TMP, assign_ids=number, assignable={'row_id'},
                 replace=fail_second)
except OSError:
    raised = True
check("a failure on the second replace raises, with the first file new", raised)
check("and the file that did not exist does not exist again",
      not os.path.exists(NEWDEST), "%s" % os.path.exists(NEWDEST))
check("while the one that did is unchanged", read(OLDDEST) == before_old)
check("and nothing is left staged", 
      not [f for f in os.listdir(TMP) if f.endswith(('.writing', '.previous'))])

# ------------------------------------ the rows already on file are not the
# callback's either, and it is handed them.
EXIST = fresh('existing.csv', [dict(row(1), row_id='x-001')])


def edits_existing(_label, existing, intended):
    intended[0]['row_id'] = 'x-002'
    existing[0]['effect_point'] = '999'


raised = False
try:
    K.run_writer('edits', [('a', EXIST, COLS, read(EXIST), [row(2)],
                            KEY, VALUE)], TMP, assign_ids=edits_existing,
                 assignable={'row_id'})
except K.SchemaError:
    raised = True
check("a callback that edits a row already on file is refused", raised)
check("and that file still holds one row, unedited",
      len(read(EXIST)) == 1 and read(EXIST)[0]['effect_point'] == '1.0',
      '%s' % read(EXIST))

# --------------------------------- the snapshot was taken outside the lock
# A caller reads the tables, builds its rows, and only then asks to write.
# Another writer can finish in between, and this one would replace the whole
# table from a picture taken before that - dropping rows it never saw. The lock
# does not close it, because the read happened before the lock was taken.
SNAP = fresh('snap.csv', [dict(row(1), row_id='s-001')])
_read_at = K.file_digest(SNAP)
_snapshot_rows = read(SNAP)
# somebody else writes in the meantime
fresh('snap.csv', [dict(row(1), row_id='s-001'), dict(row(2), row_id='s-002')])
verdict, written = K.run_writer(
    'snap', [('a', SNAP, COLS, _snapshot_rows, [row(3)], KEY, VALUE)], TMP,
    assign_ids=number, assignable={'row_id'}, read_digests={'a': _read_at})
check("a snapshot older than the file is refused",
      verdict == 'STALE_EXISTING_SNAPSHOT', verdict)
check("and the other writer's row is still there",
      len(read(SNAP)) == 2, "%d" % len(read(SNAP)))
check("a snapshot that still matches is allowed through",
      K.run_writer('snap2',
                   [('a', SNAP, COLS, read(SNAP), [row(3)], KEY, VALUE)], TMP,
                   assign_ids=number, assignable={'row_id'},
                   read_digests={'a': K.file_digest(SNAP)})[0] == 'WRITE')
# THE ORDER BOTH WRITERS ACTUALLY USED. Rows were read first, the source
# documents were parsed for minutes, and only at the run_writer call was the
# digest taken. A writer committing in that window hands this run OLD rows and
# a CURRENT digest - the one pair a digest comparison cannot see through.
SNAPB = fresh('snapb.csv', [dict(row(1), row_id='b-001')])
_late_rows = read(SNAPB)                       # 1. rows
fresh('snapb.csv', [dict(row(1), row_id='b-001'),      # 2. somebody commits
                    dict(row(2), row_id='b-002')])
_late_digest = K.file_digest(SNAPB)            # 3. digest, at the call
check("old rows with a current digest are refused, not written",
      K.run_writer('late',
                   [('a', SNAPB, COLS, _late_rows, [row(3)], KEY, VALUE)], TMP,
                   assign_ids=number, assignable={'row_id'},
                   read_digests={'a': _late_digest})[0]
      == 'SNAPSHOT_ROWS_DISAGREE')
check("and the other writer's rows are still there",
      len(read(SNAPB)) == 2, "%d" % len(read(SNAPB)))

# The loader exists so a caller cannot build that pair in the first place.
SNAPC = fresh('snapc.csv', [dict(row(1), row_id='c-001')])
_cols_c, _rows_c, _dig_c = K.load_csv_snapshot(SNAPC)
check("the loader digests the bytes it parsed",
      _dig_c == K.file_digest(SNAPC))
# NOT A SECOND READ OF THE PATH. Two reads are two moments, and the whole
# point of the loader is that the rows and the digest come from one. Nothing
# can change the file between them inside a single-threaded test, so the
# distinction is asserted directly: the loader must not go back to the file.
_orig_digest = K.file_digest


def _no_second_read(_path):
    raise AssertionError('load_csv_snapshot read the path a second time')


K.file_digest = _no_second_read
try:
    _again = K.load_csv_snapshot(SNAPC)[2]
    _one_read = _again == _dig_c
except AssertionError:
    _one_read = False
finally:
    K.file_digest = _orig_digest
check("and does not go back to the file for it", _one_read)
check("and parses what csv.DictReader parses",
      [dict(r) for r in _rows_c] == [dict(r) for r in read(SNAPC)]
      and _cols_c == COLS)
fresh('snapc.csv', [dict(row(1), row_id='c-001'), dict(row(2), row_id='c-002')])
check("a loaded snapshot that the file has moved past is refused",
      K.run_writer('loaded',
                   [('a', SNAPC, COLS, _rows_c, [row(3)], KEY, VALUE)], TMP,
                   assign_ids=number, assignable={'row_id'},
                   read_digests={'a': _dig_c})[0]
      == 'STALE_EXISTING_SNAPSHOT')
check("a loaded snapshot of a file nobody has touched goes through",
      K.run_writer('loaded2',
                   [('a', SNAPC, COLS) + tuple(K.load_csv_snapshot(SNAPC)[1:2])
                    + ([row(3)], KEY, VALUE)], TMP,
                   assign_ids=number, assignable={'row_id'},
                   read_digests={'a': K.load_csv_snapshot(SNAPC)[2]})[0]
      == 'WRITE')
check("a file that is not there loads as empty rather than raising",
      K.load_csv_snapshot(os.path.join(TMP, 'nope.csv')) == (None, [], ''))

check("and a caller that records no digest is not judged on one",
      K.run_writer('snap3',
                   [('a', fresh('snap3.csv'), COLS, [], [row(4)], KEY, VALUE)],
                   TMP, assign_ids=number, assignable={'row_id'})[0] == 'WRITE')

# ------------------------------------------------- and the archive, if asked
G = fresh('g.csv', [dict(row(1), row_id='g-001')])
ARCH = os.path.join(TMP, 'archive')
K.run_writer('cycle', [('g', G, COLS, read(G), [row(2)], KEY, VALUE)], TMP,
             assign_ids=number, assignable={'row_id'}, archive=ARCH)
check("the previous file is archived before it is replaced",
      os.path.exists(os.path.join(ARCH, 'g.csv'))
      and len(read(os.path.join(ARCH, 'g.csv'))) == 1)
check("and the new file has both rows", len(read(G)) == 2)

shutil.rmtree(TMP, ignore_errors=True)
print()
print("FDT_SCENARIOS_RUN=%d" % N[0])
print("%d scenarios run" % N[0])
if FAIL:
    print("%d FAILED: %s" % (len(FAIL), FAIL))
    raise SystemExit(1)
print("all scenarios passed")
