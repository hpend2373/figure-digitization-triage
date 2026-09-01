# -*- coding: utf-8 -*-
"""Append rows to a workbook sheet WITHOUT re-serialising the workbook.

WHY NOT openpyxl. Loading and saving this workbook with openpyxl keeps the
formulas and throws away their CACHED RESULTS - and those cached results are
the only thing that lets the sync receipt compare the workbook against the CSVs
at all. Re-saving to add rows would destroy, in the same motion, the property
that was just repaired: 432 formula cells would come back as None to any
data_only=True reader, and all ten sheet/CSV pairs would start reporting
differences again. The formulas also sit in the MIDDLE of these two sheets -
rows 8, 28, 66, 67 and so on - so they are not something an appender can step
around by working at the end unless the existing rows are left untouched.

So this edits the sheet's XML directly. Every existing row, the shared strings,
the styles, and every other part of the zip are copied through byte for byte;
the new rows go after the last one, in the same spelling the workbook already
uses (an x: prefix, t="str" for text and t="n" for numbers), and the sheet's
table range is extended to take them in.
"""
import io, json, os, re, shutil, sys, zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bundle_paths
import rowkey
import xml.sax.saxutils as SU

NUM = re.compile(r'^-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?$')


def col_name(i):
    s = ''
    while i >= 0:
        s = chr(ord('A') + i % 26) + s
        i = i // 26 - 1
    return s


def sheet_part(parts, name):
    wbx = parts['xl/workbook.xml'].decode('utf-8')
    m = re.search(r'<x:sheet name="%s"[^>]*r:id="([^"]+)"' % re.escape(name), wbx)
    if not m:
        raise SystemExit('sheet not found: %s' % name)
    rels = parts['xl/_rels/workbook.xml.rels'].decode('utf-8')
    t = re.search(r'Target="([^"]+)"[^>]*Id="%s"' % re.escape(m.group(1)), rels) \
        or re.search(r'Id="%s"[^>]*Target="([^"]+)"' % re.escape(m.group(1)), rels)
    return t.group(1).lstrip('/')


def table_part(parts, sheet_p):
    """The Excel table object over this sheet, if it has one.

    A row appended past the table's `ref` is on the sheet but outside the
    table, so filters and structured references quietly stop at the old last
    row - the rows would be there and yet not there."""
    rl = re.sub(r'^xl/worksheets/', 'xl/worksheets/_rels/', sheet_p) + '.rels'
    if rl not in parts:
        return None
    m = re.search(r'Target="([^"]*/tables/[^"]+)"', parts[rl].decode('utf-8'))
    return m.group(1).lstrip('/') if m else None


def styles_of_last_row(xml):
    """{column letter: style id} taken from the last row, so appended rows
    look like the rows above them instead of like a foreign paste."""
    rows = list(re.finditer(r'<x:row r="(\d+)"[^>]*>(.*?)</x:row>', xml, re.S))
    if not rows:
        return {}
    out = {}
    for c in re.finditer(r'<x:c r="([A-Z]+)\d+"(?:\s+s="(\d+)")?', rows[-1].group(2)):
        if c.group(2):
            out[c.group(1)] = c.group(2)
    return out


def build_rows(rows, start, styles):
    out = []
    for k, vals in enumerate(rows):
        n = start + k
        cells = []
        for j, v in enumerate(vals):
            v = '' if v is None else str(v)
            if v == '':
                continue
            letter = col_name(j)
            s = ' s="%s"' % styles[letter] if letter in styles else ''
            if NUM.match(v):
                cells.append('<x:c r="%s%d"%s t="n"><x:v>%s</x:v></x:c>'
                             % (letter, n, s, v))
            else:
                cells.append('<x:c r="%s%d"%s t="str"><x:v>%s</x:v></x:c>'
                             % (letter, n, s, SU.escape(v)))
        out.append('<x:row r="%d">%s</x:row>' % (n, ''.join(cells)))
    return ''.join(out)


def col_index(letter):
    n = 0
    for ch in letter:
        n = n * 26 + (ord(ch) - ord('A') + 1)
    return n - 1


def row_values(xml, r, ncols):
    """One row's cell text, or None if the sheet has no such row.

    A cell stored as a SHARED STRING is not read back as its text. Nothing
    this script writes is stored that way - it writes t="str" inline - so a
    shared string in the tail means the rows came from somewhere else, and
    reading them as unknown makes the comparison below refuse rather than
    assume.
    """
    m = re.search(r'<x:row r="%d"[^>]*>(.*?)</x:row>' % r, xml, re.S)
    if not m:
        return None
    vals = [''] * ncols
    for c in re.finditer(r'<x:c r="([A-Z]+)\d+"([^>]*?)(?:/>|>(.*?)</x:c>)',
                         m.group(1), re.S):
        j = col_index(c.group(1))
        if j >= ncols:
            continue
        if 't="s"' in (c.group(2) or ''):
            vals[j] = '\x00SHARED_STRING'
            continue
        v = re.search(r'<x:v>(.*?)</x:v>', c.group(3) or '', re.S)
        vals[j] = SU.unescape(v.group(1)) if v else ''
    return vals


def as_text(row):
    return ['' if v is None else str(v) for v in row]


def sheet_state(parts, sheet, rows):
    """Whether this sheet already carries these rows. Three answers, not two.

    ABSENT     none of them are anywhere on the sheet
    PRESENT    all of them are there, in order, as one contiguous block
    CONFLICT   some are there and some are not, or they are there but broken
               up - a state nobody can append their way out of

    NOT "are they the last rows". They were the last rows on the day they were
    appended, and then the figure writer added four more; an exact-tail rule
    calls that applied-and-then-written-past state a conflict, which is a
    refusal the operator cannot act on. What matters is whether this block is
    on the sheet, not whether anything came after it.

    "Absent" used to be assumed rather than established - the script appended
    whatever it was handed, so a second run put every row in twice.
    """
    xml = parts[sheet_part(parts, sheet)].decode('utf-8')
    ncols = max(len(r) for r in rows) if rows else 0
    last = max(int(m.group(1)) for m in re.finditer(r'<x:row r="(\d+)"', xml))
    seq = [row_values(xml, r, ncols) for r in range(1, last + 1)]
    seq = [tuple(v) for v in seq if v is not None]
    want = [tuple(as_text(r)) for r in rows]
    n = len(want)
    if n and any(seq[i:i + n] == want for i in range(len(seq) - n + 1)):
        return 'PRESENT', last
    if set(want) & set(seq):
        return 'CONFLICT', last
    return 'ABSENT', last


def plan_append(parts, sheet, rows):
    """The parts an append would change. Nothing is written here.

    Both sheets are planned against ONE set of parts and written once, so a
    failure on the second sheet cannot leave the workbook carrying the first.
    """
    part = sheet_part(parts, sheet)
    tpart = table_part(parts, part)
    xml = parts[part].decode('utf-8')
    last = max(int(m.group(1)) for m in re.finditer(r'<x:row r="(\d+)"', xml))
    add = build_rows(rows, last + 1, styles_of_last_row(xml))
    i = xml.rindex('</x:sheetData>')
    edited = {part: (xml[:i] + add + xml[i:]).encode('utf-8')}
    new_last = last + len(rows)
    if tpart:
        traw = parts[tpart].decode('utf-8')
        traw2, n = re.subn(r'(ref=")([A-Z]+)1:([A-Z]+)\d+(")',
                           lambda m: m.group(1) + m.group(2) + '1:' + m.group(3)
                           + str(new_last) + m.group(4), traw)
        if not n:
            raise SystemExit('table ref not found in %s' % tpart)
        edited[tpart] = traw2.encode('utf-8')
    return edited, last, new_last, tpart


def write_workbook(path, members, edited):
    """The whole workbook, once, through a temporary file.

    Every part not in `edited` is copied byte for byte - that is what keeps
    the 432 cached formula values alive - and the file the readers see is
    swapped in a single replace, so it is either the old workbook or the new
    one and never a zip being built.
    """
    tmp = path + '.tmp'
    try:
        with zipfile.ZipFile(tmp, 'w', zipfile.ZIP_DEFLATED) as out:
            for info, data in members:
                out.writestr(info, edited.get(info.filename, data))
    except Exception:
        # A HALF-BUILT ZIP IS NOT A WORKBOOK, AND IT SITS NEXT TO THE REAL
        # ONE. The replace below never runs, so the workbook itself is intact
        # either way; what is left behind is a file the next run cannot tell
        # from a write in progress. Removing it is best-effort: the bundle can
        # live on a mount that refuses deletes, and failing to clean up must
        # not replace the error that actually happened.
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise
    os.replace(tmp, path)


#: The tables whose rows this step carries into the workbook, and the files
#: they live in. Declared here rather than read off the receipt: a receipt
#: that lost an entry would otherwise lose the check with it.
TABLES = {'effects_text_long': 'effect_extraction_text_long.csv',
          'extraction_counts_long': 'extraction_counts_long.csv'}
WORKBOOK = 'extraction_form_RASi_PCa.xlsx'
WRITER = 'integrate_supplements'


def preconditions(base, logs):
    """Everything that has to hold before the workbook may be touched.

    THE ROWS AND THE TABLES THEY CAME FROM ARE ONE CLAIM. new_rows.json is
    written by another script in another run; this one used to take it on
    faith, so a file left by an earlier run would have been appended while the
    CSVs said something else. The receipt binds the rows to the tables they
    were derived from, and those tables are hashed here and now.
    """
    receipt = rowkey.read_receipt(logs, WRITER)
    problems = rowkey.sidecar_problems(
        receipt, {'new_rows.json': os.path.join(logs, 'new_rows.json')})
    problems += rowkey.attestation_problems(receipt, {
        'protocol_sha256': rowkey.file_digest(
            os.path.join(os.path.dirname(os.path.abspath(rowkey.__file__)),
                         'rowkey.py')),
        'tables': {k: rowkey.file_digest(os.path.join(base, v))
                   for k, v in TABLES.items()}})
    named = sorted((receipt.get('attestation') or {})
                   .get('core', {}).get('tables') or {})
    if named != sorted(TABLES):
        problems.append(('RECEIPT_TABLE_SET_MISMATCH',
                         'receipt names tables %s, this step needs %s'
                         % (named, sorted(TABLES))))
    if receipt.get('verdict') not in ('WRITE', rowkey.CLEAN_RERUN):
        problems.append(('WRITER_VERDICT_NOT_CLEAN',
                         '%s last reported %s' % (WRITER,
                                                  receipt.get('verdict'))))
    return receipt, problems


if __name__ == '__main__':
    # ONE HOME FOR THE BUNDLE, THE SAME ONE THE WRITERS USE. This script found
    # the workbook and the receipts by walking up from its own directory, so
    # the shipped copy read a different tree than FDT_BUNDLE named: it could
    # check one run's receipt and append to another run's workbook.
    base = bundle_paths.BASE
    logs = bundle_paths.receipt_dir()
    wbp = os.path.join(base, WORKBOOK)

    with rowkey.write_lock(bundle_paths.write_lock()):
        receipt, problems = preconditions(base, logs)
        if problems:
            for code, detail in problems:
                print('  %-28s %s' % (code, detail))
            raise SystemExit(
                'the rows handed to this step are not bound to the tables on '
                'disk; the workbook is untouched.')
        new = json.load(io.open(os.path.join(logs, 'new_rows.json'),
                                encoding='utf-8'))

        with zipfile.ZipFile(wbp) as z:
            members = [(i, z.read(i.filename)) for i in z.infolist()]
        parts = {i.filename: d for i, d in members}

        # WHAT THE WORKBOOK ALREADY CARRIES, BEFORE DECIDING TO ADD ANYTHING.
        # An attested sidecar says the rows are the right rows. It does not
        # say they have not been applied - and this script used to append
        # whatever it was handed, so a second run put every row in twice.
        states = {sheet: sheet_state(parts, sheet, rows)[0]
                  for sheet, rows in sorted(new.items())}
        for sheet, state in sorted(states.items()):
            print('  %-24s %s' % (sheet, state))
        distinct = set(states.values())
        if distinct == {'PRESENT'}:
            verdict = 'ALREADY_APPLIED_NO_WRITE'
        elif distinct == {'ABSENT'}:
            verdict = 'APPLY'
        else:
            # Half applied, or applied and then written past. Neither adding
            # the rows nor leaving them is right, and this step is not the
            # place to guess which.
            verdict = 'CONFLICT_NO_WRITE'

        before = rowkey.file_digest(wbp)
        applied = {}
        if verdict == 'APPLY':
            bak = os.path.join(base, 'archive',
                               'pre_supplement_integration_2026-08-30',
                               WORKBOOK)
            if not os.path.exists(bak):
                os.makedirs(os.path.dirname(bak), exist_ok=True)
                shutil.copy2(wbp, bak)
            edited = {}
            for sheet, rows in sorted(new.items()):
                part_edits, a, b, tp = plan_append(parts, sheet, rows)
                # Planned against the parts as the previous sheet left them,
                # so both sheets and both table refs go in together.
                parts.update(part_edits)
                edited.update(part_edits)
                applied[sheet] = {'from_row': a, 'to_row': b,
                                  'rows': len(rows), 'table_part': tp}
                print('  %-24s %d행 -> %d행 (+%d), 표 %s'
                      % (sheet, a, b, len(rows), tp))
            write_workbook(wbp, members, edited)

        json.dump({'verdict': verdict,
                   'sheet_states': states,
                   'applied': applied,
                   'workbook_sha256_before': before,
                   'workbook_sha256_after': rowkey.file_digest(wbp),
                   'new_rows_sha256': (receipt.get('sidecars') or {})
                                      .get('new_rows.json'),
                   'writer_receipt_verdict': receipt.get('verdict')},
                  io.open(os.path.join(logs, 'xlsx_append_rows_receipt.json'),
                          'w', encoding='utf-8'), indent=2, ensure_ascii=False)
        print('  판정: %s' % verdict)
        if verdict == 'CONFLICT_NO_WRITE':
            raise SystemExit(1)
