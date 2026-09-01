# -*- coding: utf-8 -*-
"""The workbook step, on a workbook small enough to reason about.

WHY A FIXTURE AND NOT THE REAL FILE. The real workbook has already had these
rows applied, so the only path it can exercise is the one that declines. The
paths that matter - appending once, declining to append twice, refusing a
half-applied sheet, and leaving nothing behind when the second sheet fails -
have never been run anywhere. A fixture built here is small, and every part of
it is visible in this file.
"""
import io, json, os, re, shutil, sys, tempfile, zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import xlsx_append_rows as X

N, FAIL = [0], []


def check(name, ok, detail=''):
    N[0] += 1
    print('  %s %s%s' % ('ok  ' if ok else 'FAIL', name,
                         '' if ok else '  <- %s' % detail))
    if not ok:
        FAIL.append(name)


TMP = tempfile.mkdtemp(prefix='fdt-xlsx-')
NS = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'
RNS = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'


def sheet_xml(rows, start=1):
    body = ''
    for k, vals in enumerate(rows):
        cells = ''.join(
            '<x:c r="%s%d" t="str"><x:v>%s</x:v></x:c>'
            % (X.col_name(j), start + k, v)
            for j, v in enumerate(vals) if v != '')
        body += '<x:row r="%d">%s</x:row>' % (start + k, cells)
    return ('<?xml version="1.0" encoding="utf-8"?>'
            '<x:worksheet xmlns:x="%s"><x:sheetData>%s</x:sheetData>'
            '</x:worksheet>' % (NS, body))


def book(sheets, table_on=None):
    """A workbook with one part per named sheet, and optionally a table."""
    path = os.path.join(TMP, 'wb-%d.xlsx' % len(os.listdir(TMP)))
    names = sorted(sheets)
    wb = ('<?xml version="1.0" encoding="utf-8"?><x:workbook xmlns:x="%s">'
          '<x:sheets>%s</x:sheets></x:workbook>'
          % (NS, ''.join('<x:sheet name="%s" sheetId="%d" r:id="r%d" '
                         'xmlns:r="%s" />' % (n, i + 1, i + 1, RNS)
                         for i, n in enumerate(names))))
    rels = ('<?xml version="1.0" encoding="utf-8"?><Relationships '
            'xmlns="http://schemas.openxmlformats.org/package/2006/'
            'relationships">%s</Relationships>'
            % ''.join('<Relationship Target="/xl/worksheets/sheet%d.xml" '
                      'Id="r%d" />' % (i + 1, i + 1)
                      for i, _n in enumerate(names)))
    with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED) as z:
        z.writestr('xl/workbook.xml', wb)
        z.writestr('xl/_rels/workbook.xml.rels', rels)
        for i, n in enumerate(names):
            z.writestr('xl/worksheets/sheet%d.xml' % (i + 1),
                       sheet_xml(sheets[n]))
            if n == table_on:
                # A ROW PAST THE TABLE'S ref IS ON THE SHEET AND OUTSIDE THE
                # TABLE - filters and structured references stop at the old
                # last row, so the rows are there and yet not there. The
                # fixture had no table at all, so the branch that extends the
                # ref never ran anywhere.
                z.writestr('xl/worksheets/_rels/sheet%d.xml.rels' % (i + 1),
                           '<?xml version="1.0" encoding="utf-8"?>'
                           '<Relationships xmlns="http://schemas.'
                           'openxmlformats.org/package/2006/relationships">'
                           '<Relationship Target="/xl/tables/table1.xml" '
                           'Id="t1" /></Relationships>')
                z.writestr('xl/tables/table1.xml',
                           '<?xml version="1.0" encoding="utf-8"?>'
                           '<x:table xmlns:x="%s" id="1" name="t" '
                           'ref="A1:C%d" />' % (NS, len(sheets[n])))
    return path


def parts_of(path):
    with zipfile.ZipFile(path) as z:
        return [(i, z.read(i.filename)) for i in z.infolist()]


def members_dict(path):
    return {i.filename: d for i, d in parts_of(path)}


def rows_of(path, sheet, ncols):
    parts = members_dict(path)
    xml = parts[X.sheet_part(parts, sheet)].decode('utf-8')
    last = max(int(m.group(1)) for m in re.finditer(r'<x:row r="(\d+)"', xml))
    return [X.row_values(xml, r, ncols) for r in range(1, last + 1)]


HEAD = [['id', 'v'], ['a', '1'], ['b', '2']]
NEW = [['c', '3'], ['d', '4']]

# --------------------------------------------------------------- the states
P = book({'s1': HEAD})
check("rows that are nowhere on the sheet are ABSENT",
      X.sheet_state(members_dict(P), 's1', NEW)[0] == 'ABSENT',
      X.sheet_state(members_dict(P), 's1', NEW)[0])

P2 = book({'s1': HEAD + NEW})
check("rows that are there, in order, are PRESENT",
      X.sheet_state(members_dict(P2), 's1', NEW)[0] == 'PRESENT')

# THEY WERE THE LAST ROWS ON THE DAY THEY WERE APPLIED, AND THEN THE FIGURE
# WRITER ADDED FOUR MORE. An exact-tail rule reads that as a conflict and
# tells the operator to fix a state that is not broken.
P3 = book({'s1': HEAD + NEW + [['e', '5']]})
check("rows written past are still PRESENT, not a conflict",
      X.sheet_state(members_dict(P3), 's1', NEW)[0] == 'PRESENT',
      X.sheet_state(members_dict(P3), 's1', NEW)[0])

P4 = book({'s1': HEAD + NEW[:1]})
check("half of them is a CONFLICT nobody can append their way out of",
      X.sheet_state(members_dict(P4), 's1', NEW)[0] == 'CONFLICT')

P5 = book({'s1': HEAD[:1] + [NEW[0]] + HEAD[1:] + [NEW[1]]})
check("all of them but broken apart is a CONFLICT too",
      X.sheet_state(members_dict(P5), 's1', NEW)[0] == 'CONFLICT')

# FINDING THE BLOCK IS NOT ENOUGH. The state the old implementation could
# produce - a second run appending the same rows again - CONTAINS the block.
# Stopping at the first match would have called that workbook fine.
check("the block twice over is a CONFLICT",
      X.sheet_state(members_dict(book({'s1': HEAD + NEW + NEW})),
                    's1', NEW)[0] == 'CONFLICT',
      X.sheet_state(members_dict(book({'s1': HEAD + NEW + NEW})),
                    's1', NEW)[0])
check("the block plus a stray copy of one of its rows is a CONFLICT",
      X.sheet_state(members_dict(book({'s1': HEAD + NEW + NEW[:1]})),
                    's1', NEW)[0] == 'CONFLICT')
check("the same rows in two places, neither of them the block, is a CONFLICT",
      X.sheet_state(members_dict(book({'s1': HEAD + NEW[:1] + [['z', '9']]
                                       + NEW})), 's1', NEW)[0] == 'CONFLICT')

# ------------------------------------------------------------- the appending
P6 = book({'s1': HEAD})
_parts = members_dict(P6)
_edited, _a, _b, _tp = X.plan_append(_parts, 's1', NEW)
check("planning changes nothing on disk",
      X.sheet_state(members_dict(P6), 's1', NEW)[0] == 'ABSENT'
      and _edited[X.sheet_part(members_dict(P6), 's1')]
      != members_dict(P6)[X.sheet_part(members_dict(P6), 's1')])
X.write_workbook(P6, parts_of(P6), _edited)
check("the rows are on the sheet after the write",
      X.sheet_state(members_dict(P6), 's1', NEW)[0] == 'PRESENT')
check("and the rows that were there are untouched",
      rows_of(P6, 's1', 2)[:3] == [['id', 'v'], ['a', '1'], ['b', '2']],
      "%s" % rows_of(P6, 's1', 2)[:3])
check("appending reports the row numbers it used",
      (_a, _b) == (3, 5), "%s %s" % (_a, _b))

# TWO SHEETS, ONE WORKBOOK, ONE REPLACE. The step used to call append() per
# sheet, each one reading and rewriting the file, so a failure on the second
# left the workbook carrying the first.
P7 = book({'s1': HEAD, 's2': HEAD})
_parts = members_dict(P7)
_all = {}
for _s in ('s1', 's2'):
    _e, _x, _y, _t = X.plan_append(_parts, _s, NEW)
    _parts.update(_e)
    _all.update(_e)
check("two sheets planned against one set of parts touch two parts",
      len(_all) == 2, "%s" % sorted(_all))
_before = X.rowkey.file_digest(P7)
try:
    # The SECOND edited part is unwritable, so the failure lands after the
    # first has already gone into the temporary zip.
    X.write_workbook(P7, parts_of(P7),
                     dict(_all, **{sorted(_all)[1]: None}))
    _raised = False
except Exception:
    _raised = True
check("a write that fails part way raises", _raised)
check("and leaves the workbook exactly as it was",
      X.rowkey.file_digest(P7) == _before)
check("with no temporary file left behind",
      not [f for f in os.listdir(TMP) if f.endswith('.tmp')],
      "%s" % [f for f in os.listdir(TMP) if f.endswith('.tmp')])
X.write_workbook(P7, parts_of(P7), _all)
check("and both sheets carry their rows when it succeeds",
      [X.sheet_state(members_dict(P7), s, NEW)[0] for s in ('s1', 's2')]
      == ['PRESENT', 'PRESENT'])

# --------------------------------------------------------- the table's range
PT = book({'s1': HEAD}, table_on='s1')
_before_parts = members_dict(PT)
_edits, _a, _b, _tp = X.plan_append(_before_parts, 's1', NEW)
X.write_workbook(PT, parts_of(PT), _edits)
check("appending extends the table's range to the new last row",
      'ref="A1:C5"' in members_dict(PT)['xl/tables/table1.xml'].decode('utf-8'),
      members_dict(PT)['xl/tables/table1.xml'].decode('utf-8')[-40:])
check("and the append reports which table part it touched",
      _tp == 'xl/tables/table1.xml', "%s" % _tp)
check("every part it did not edit is byte for byte what it was",
      {k: v for k, v in members_dict(PT).items() if k not in _edits}
      == {k: v for k, v in _before_parts.items() if k not in _edits})

# ------------------------------------------------------- reading cells back
P8 = book({'s1': [['x', '']]})
check("an empty cell reads back as empty, not as missing",
      X.row_values(members_dict(P8)[
          X.sheet_part(members_dict(P8), 's1')].decode('utf-8'), 1, 2)
      == ['x', ''])
check("a row that is not there reads as None",
      X.row_values(members_dict(P8)[
          X.sheet_part(members_dict(P8), 's1')].decode('utf-8'), 99, 2)
      is None)
_shared = sheet_xml([['x', 'y']]).replace('t="str"><x:v>y', 't="s"><x:v>3')
check("a shared-string cell is not read as its text",
      X.row_values(_shared, 1, 2)[1] == '\x00SHARED_STRING',
      "%s" % X.row_values(_shared, 1, 2))


# --- the whole step, on a bundle built here ---------------------------------
# EVERY CHECK THAT DECIDES WHETHER THE WORKBOOK IS TOUCHED LIVED IN __main__,
# where nothing could reach it: the precondition set, the verdict, the receipt.
# The helpers above were tested and the decision was not. apply_workbook() is
# that decision, and this exercises it against a bundle small enough to build.
import csv
import rowkey as K

BASE = os.path.join(TMP, 'bundle')
LOGS = os.path.join(BASE, 'logs')
os.makedirs(LOGS)
COLS = ['row_id', 'rec', 'val']
LABELS = sorted(X.TABLES)


def csv_write(path, rows):
    with io.open(path, 'w', encoding='utf-8', newline='') as fh:
        w = csv.DictWriter(fh, fieldnames=COLS)
        w.writeheader()
        w.writerows(K.writable(rows, COLS))


def csv_read(path):
    with io.open(path, encoding='utf-8-sig') as fh:
        return list(csv.DictReader(fh))


def table_path(label):
    return os.path.join(BASE, X.TABLES[label])


def numbered(label, existing, intended):
    for i, r in enumerate(intended, start=len(existing) + 1):
        r['row_id'] = '%s-%03d' % (label[:3], i)


NEW_ROWS = {LABELS[0]: [{'rec': 'R9', 'val': '1'}],
            LABELS[1]: [{'rec': 'R8', 'val': '2'}, {'rec': 'R7', 'val': '3'}]}
for _l in LABELS:
    csv_write(table_path(_l), [{'row_id': 'old-1', 'rec': 'R1', 'val': '0'}])


def run_writer(intended):
    def sidecars(_v, _w):
        return {'new_rows.json':
                {l: [[r.get(c, '') for c in COLS] for r in intended[l]]
                 for l in LABELS}}
    tables = []
    for l in LABELS:
        _c, rows, dig = K.load_csv_snapshot(table_path(l))
        tables.append((l, table_path(l), COLS, rows, intended[l],
                       ('rec',), ('val',)))
    return K.run_writer('integrate_supplements', tables, LOGS,
                        assign_ids=numbered, assignable={'row_id'},
                        sidecars=sidecars,
                        read_digests={l: K.load_csv_snapshot(table_path(l))[2]
                                      for l in LABELS})[0]


_v1 = run_writer({l: [dict(r) for r in NEW_ROWS[l]] for l in LABELS})
check("the writer writes the tables first", _v1 == 'WRITE', _v1)
_v2 = run_writer({l: [dict(r) for r in NEW_ROWS[l]] for l in LABELS})
check("and a second run proves the rerun is a no-op",
      _v2 == K.CLEAN_RERUN, _v2)

WB = book({LABELS[0]: [COLS, ['old-1', 'R1', '0']],
           LABELS[1]: [COLS, ['old-1', 'R1', '0']]})


def apply():
    return X.apply_workbook(BASE, LOGS, WB)


_r = apply()
check("a bound sidecar over an unapplied workbook applies",
      _r['verdict'] == 'APPLY', "%s" % _r.get('problems') or _r['verdict'])
check("the workbook changed, and the receipt says from what to what",
      _r['workbook_sha256_before'] != _r['workbook_sha256_after']
      and _r['workbook_sha256_after'] == K.file_digest(WB))
check("both sheets carry their rows",
      [X.sheet_state(members_dict(WB), l,
                     [[r['row_id'], r['rec'], r['val']]
                      for r in csv_read(table_path(l))[1:]])[0]
       for l in LABELS] == ['PRESENT', 'PRESENT'])

_before = K.file_digest(WB)
_r = apply()
check("running it again declines instead of appending twice",
      _r['verdict'] == 'ALREADY_APPLIED_NO_WRITE', _r['verdict'])
check("and the workbook is byte for byte what it was",
      K.file_digest(WB) == _before)


def refuses(name, codes_wanted, wreck, repair):
    """Break one thing, run the step, put it back."""
    keep = K.file_digest(WB)
    wreck()
    out = apply()
    got = [c for c, _d in out.get('problems') or []]
    check(name, out['verdict'] == 'REFUSED_NO_WRITE'
          and any(c in got for c in codes_wanted), "%s" % got)
    check("  and the workbook is untouched", K.file_digest(WB) == keep)
    repair()


_rec_path = os.path.join(LOGS, 'integrate_supplements_idempotency.json')
# KEPT AS BYTES. Read as text and written back, a file written with \r\n
# comes back with \n - the restore itself becomes the next test's tampering,
# and every check after the first one fails for a reason that is not there.
_rec_keep = io.open(_rec_path, 'rb').read()
_side_path = os.path.join(LOGS, 'new_rows.json')
_side_keep = io.open(_side_path, 'rb').read()
_csv_keep = io.open(table_path(LABELS[0]), 'rb').read()


def restore(path, raw):
    return lambda: io.open(path, 'wb').write(raw)


def rewrite(path, obj):
    return lambda: json.dump(obj, io.open(path, 'w', encoding='utf-8'),
                             indent=2, ensure_ascii=False)


def edited_receipt(fn):
    def go():
        d = json.loads(_rec_keep)
        fn(d)
        json.dump(d, io.open(_rec_path, 'w', encoding='utf-8'), indent=2)
    return go


refuses("a table changed since the receipt is refused",
        ['RECEIPT_TABLE_STALE'],
        lambda: io.open(table_path(LABELS[0]), 'a',
                        encoding='utf-8').write('x-9,R6,9\n'),
        restore(table_path(LABELS[0]), _csv_keep))

refuses("a receipt that names only one table is refused",
        ['RECEIPT_TABLE_SET_MISMATCH'],
        edited_receipt(lambda d: d['attestation']['core']['tables']
                       .pop(LABELS[1])),
        restore(_rec_path, _rec_keep))

refuses("a receipt whose writer verdict is not a clean rerun is refused",
        ['WRITER_VERDICT_NOT_A_CLEAN_RERUN'],
        edited_receipt(lambda d: d.update({'verdict': 'WRITE'})),
        restore(_rec_path, _rec_keep))

# A MALFORMED PRODUCER, NOT A CORRUPTED FILE. These write the sidecar AND
# attest it, which is what a broken writer would do - the digest check alone
# cannot see them.
_one_sheet = {LABELS[0]: json.loads(_side_keep)[LABELS[0]]}
refuses("a sidecar missing a sheet is refused",
        ['SIDECAR_SHEET_SET_MISMATCH'],
        lambda: (rewrite(_side_path, _one_sheet)(),
                 K.attest_sidecars(LOGS, 'integrate_supplements',
                                   {'new_rows.json': _one_sheet})),
        lambda: (restore(_side_path, _side_keep)(),
                 restore(_rec_path, _rec_keep)()))

_absent = json.loads(_side_keep)
_absent[LABELS[0]] = [['zzz-1', 'R0', '999']]
refuses("a sidecar naming rows that are not in the table is refused",
        ['SIDECAR_ROWS_NOT_ONCE_IN_TABLE'],
        lambda: (rewrite(_side_path, _absent)(),
                 K.attest_sidecars(LOGS, 'integrate_supplements',
                                   {'new_rows.json': _absent})),
        lambda: (restore(_side_path, _side_keep)(),
                 restore(_rec_path, _rec_keep)()))

# THE ROWS ARE REAL, THE COUNT IS RIGHT, AND THEY ARE STILL NOT THIS RUN'S.
# `old-1` was in the table before this writer touched it. It is on file
# exactly once and the block is the right size, so every check except the
# digest is satisfied: only "are these the rows the writer persisted" says no.
_wrong = json.loads(_side_keep)
_wrong[LABELS[0]] = [['old-1', 'R1', '0']]
refuses("a sidecar holding real rows the writer never persisted is refused",
        ['SIDECAR_NOT_THE_PERSISTED_ROWS'],
        lambda: (rewrite(_side_path, _wrong)(),
                 K.attest_sidecars(LOGS, 'integrate_supplements',
                                   {'new_rows.json': _wrong})),
        lambda: (restore(_side_path, _side_keep)(),
                 restore(_rec_path, _rec_keep)()))

_short = json.loads(_side_keep)
_short[LABELS[0]] = [r[:2] for r in _short[LABELS[0]]]
refuses("a sidecar row narrower than the file is refused",
        ['SIDECAR_ROW_WIDTH_MISMATCH'],
        lambda: (rewrite(_side_path, _short)(),
                 K.attest_sidecars(LOGS, 'integrate_supplements',
                                   {'new_rows.json': _short})),
        lambda: (restore(_side_path, _side_keep)(),
                 restore(_rec_path, _rec_keep)()))

check("and after all of that it still declines cleanly",
      apply()['verdict'] == 'ALREADY_APPLIED_NO_WRITE')

shutil.rmtree(TMP, ignore_errors=True)
print()
print('FDT_SCENARIOS_RUN=%d' % N[0])
print('%d scenarios run' % N[0])
if FAIL:
    print('%d FAILED: %s' % (len(FAIL), FAIL))
    raise SystemExit(1)
print('all scenarios passed')
