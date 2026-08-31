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
