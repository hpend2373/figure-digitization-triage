# -*- coding: utf-8 -*-
"""The workbook step, on a workbook small enough to reason about.

WHY A FIXTURE AND NOT THE REAL FILE. The real workbook has already had these
rows applied, so the only path it can exercise is the one that declines. The
paths that matter - appending once, declining to append twice, refusing a
half-applied sheet, and leaving nothing behind when the second sheet fails -
have never been run anywhere. A fixture built here is small, and every part of
it is visible in this file.
"""
import io, os, re, shutil, sys, tempfile, zipfile

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


def book(sheets):
    """A workbook with one part per named sheet. No styles, no tables."""
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

shutil.rmtree(TMP, ignore_errors=True)
print()
print('FDT_SCENARIOS_RUN=%d' % N[0])
print('%d scenarios run' % N[0])
if FAIL:
    print('%d FAILED: %s' % (len(FAIL), FAIL))
    raise SystemExit(1)
print('all scenarios passed')
