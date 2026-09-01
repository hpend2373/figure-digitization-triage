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
import collections, csv, io, json, os, re, shutil, sys, zipfile

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
    PRESENT    all of them are there, in order, as ONE block, and no copy of
               any of them anywhere else
    CONFLICT   anything in between - some there and some not, the block twice,
               the block plus a stray copy of one of its rows, or two halves
               in two places

    NOT "are they the last rows". They were the last rows on the day they were
    appended and then the figure writer added four more; an exact-tail rule
    calls that applied-and-then-written-past state a conflict, which is a
    refusal the operator cannot act on.

    But "the block is somewhere" is not enough either. The very state the old
    implementation could produce - a second run appending the same rows again -
    contains the block, so finding it and stopping there would have called
    the duplicate-applied workbook fine. Every intended row is counted, and
    the count has to match the block exactly.
    """
    xml = parts[sheet_part(parts, sheet)].decode('utf-8')
    ncols = max(len(r) for r in rows) if rows else 0
    last = max(int(m.group(1)) for m in re.finditer(r'<x:row r="(\d+)"', xml))
    seq = [row_values(xml, r, ncols) for r in range(1, last + 1)]
    seq = [tuple(v) for v in seq if v is not None]
    want = [tuple(as_text(r)) for r in rows]
    n = len(want)
    if not n:
        return 'CONFLICT', last
    wanted = collections.Counter(want)
    found = collections.Counter(t for t in seq if t in wanted)
    blocks = [i for i in range(len(seq) - n + 1) if seq[i:i + n] == want]
    if len(blocks) == 1 and found == wanted:
        return 'PRESENT', last
    if not found:
        return 'ABSENT', last
    return 'CONFLICT', last


def sheet_columns(parts, sheet):
    """The column names this sheet declares, in order, or None.

    An Excel table's `tableColumn` names first, because that is what
    structured references resolve against; the header row when the sheet has
    no table. Either way it is the order the workbook believes in, and
    `plan_append` writes the sidecar's values from column A rightwards - so
    if the two orders disagree, every value lands under the wrong heading and
    the rows look perfectly well formed.
    """
    part = sheet_part(parts, sheet)
    tpart = table_part(parts, part)
    if tpart and tpart in parts:
        cols = [SU.unescape(m.group(1)) for m in re.finditer(
            r'<(?:\w+:)?tableColumn[^>]*\bname="([^"]*)"',
            parts[tpart].decode('utf-8'))]
        if cols:
            return cols
    head = row_values(parts[part].decode('utf-8'), 1, 4096)
    if head is None:
        return None
    while head and head[-1] == '':
        head.pop()
    return head or None


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
#: they live in. Declared here rather than read off the receipt or off the
#: sidecar: a receipt that lost an entry, or a sidecar that arrived with one
#: sheet missing, would otherwise lose the check along with it.
TABLES = {'effects_text_long': 'effect_extraction_text_long.csv',
          'extraction_counts_long': 'extraction_counts_long.csv'}
WORKBOOK = 'extraction_form_RASi_PCa.xlsx'
WRITER = 'integrate_supplements'


def load_table(base, label):
    return rowkey.load_csv_snapshot(os.path.join(base, TABLES[label]))


def preconditions(base, logs):
    """Everything that has to hold before the workbook may be touched.

    THE ROWS, THE RECEIPT AND THE TABLES ARE ONE CLAIM OR THEY ARE NOTHING.
    new_rows.json is written by another script in another run. Checking that
    it was attested, and separately that the CSV hash matches the receipt,
    leaves the two facts unrelated: a producer recording a correct file hash
    beside a sidecar full of different rows satisfied both. So the rows in the
    sidecar are rebuilt against the CURRENT columns, digested the way the
    writer digested what it persisted, and looked up in the CSV itself.
    """
    receipt = rowkey.read_receipt(logs, WRITER)
    # READ ONCE, AND CHECK THE OBJECT THAT WILL BE APPLIED. Verifying the file
    # and then opening it again to use it verifies one thing and applies
    # another if anything touches it in between - the same gap that was closed
    # for the CSVs by digesting the bytes that were parsed. The CLI holds the
    # bundle lock, but a hand edit or a process that does not take the lock is
    # not bound by it, and the fix costs one variable.
    path = os.path.join(logs, 'new_rows.json')
    new = None
    if not os.path.exists(path):
        problems = [('SIDECAR_MISSING', 'new_rows.json is not on disk')]
    else:
        try:
            new = json.load(io.open(path, encoding='utf-8'))
            problems = rowkey.sidecar_payload_problems(
                receipt, 'new_rows.json', new)
        except ValueError as exc:
            problems = [('SIDECAR_UNREADABLE', 'new_rows.json: %s' % exc)]
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
    # ONLY A CLEAN RERUN. The attestation is written before the tables are
    # replaced, so a first WRITE's receipt records the PRE-write file hashes
    # and can never match the CSVs it just produced. Allowing WRITE here was a
    # branch that could not be taken; the order is writer, then the writer
    # again to prove the rerun is clean, then this.
    if receipt.get('verdict') != rowkey.CLEAN_RERUN:
        problems.append(('WRITER_VERDICT_NOT_A_CLEAN_RERUN',
                         '%s last reported %s; run it again and let it prove '
                         'the rerun is a no-op first'
                         % (WRITER, receipt.get('verdict'))))
    if problems:
        return receipt, None, problems

    if not isinstance(new, dict) or sorted(new) != sorted(TABLES):
        problems.append(('SIDECAR_SHEET_SET_MISMATCH',
                         'new_rows.json carries %s, this step needs %s'
                         % (sorted(new) if isinstance(new, dict) else type(new),
                            sorted(TABLES))))
        return receipt, None, problems

    persisted = receipt.get('persisted') or {}
    for label in sorted(TABLES):
        rows, said = new[label], persisted.get(label) or {}
        fields, on_file, _d = load_table(base, label)
        if not isinstance(rows, list) or not rows or not all(
                isinstance(r, list) for r in rows):
            problems.append(('SIDECAR_BLOCK_MALFORMED',
                             '%s is not a non-empty list of rows' % label))
            continue
        if list(said.get('fields') or ()) != list(fields or ()):
            problems.append(('SIDECAR_FIELDS_MISMATCH',
                             '%s: the receipt was written against %d columns '
                             'and the file has %d'
                             % (label, len(said.get('fields') or ()),
                                len(fields or ()))))
            continue
        widths = sorted({len(r) for r in rows})
        if widths != [len(fields)]:
            problems.append(('SIDECAR_ROW_WIDTH_MISMATCH',
                             '%s: rows are %s wide, the file has %d columns'
                             % (label, widths, len(fields))))
            continue
        if len(rows) != said.get('rows'):
            problems.append(('SIDECAR_ROW_COUNT_MISMATCH',
                             '%s: sidecar has %d rows, the receipt persisted '
                             '%s' % (label, len(rows), said.get('rows'))))
            continue
        as_dicts = [dict(zip(fields, r)) for r in rows]
        got = rowkey.persisted_digest(as_dicts, fields)
        if got != said.get('rows_sha256'):
            problems.append(('SIDECAR_NOT_THE_PERSISTED_ROWS',
                             '%s: the receipt persisted %s and the sidecar '
                             'digests %s'
                             % (label, (said.get('rows_sha256')
                                        or '(absent)')[:12], got[:12])))
            # NOT `continue`. The next check asks a different question - are
            # these rows in the file at all - and it is the only one that can
            # answer it. Stopping here left it with no case of its own, and a
            # check nothing can make fail is not a check.

        # AND THE ROWS ARE IN THE FILE, ONCE EACH, AS OFTEN AS THE SIDECAR
        # CLAIMS THEM. Counted on both sides: the sidecar's own rows used to
        # go through a set, which threw away how many times it asked for each
        # one. A sidecar claiming the same row twice, with a receipt written
        # to match, then compared a one-element set against a file that had
        # it once and passed - and the workbook would have taken the row
        # twice.
        have = collections.Counter(
            tuple((r.get(c) or '') for c in fields) for r in on_file)
        side = collections.Counter(
            tuple((r.get(c) or '') for c in fields) for r in as_dicts)
        twice = sorted(t for t, n in side.items() if n != 1)
        if twice:
            # Every persisted row carries an ordinal, so two identical rows in
            # one block is not a thing this pipeline can legitimately produce.
            problems.append(('SIDECAR_DUPLICATE_ROW',
                             '%s: %d of its rows appear more than once in the '
                             'sidecar itself' % (label, len(twice))))
        wrong = [t for t, n in side.items() if have[t] != n]
        if wrong:
            problems.append(('SIDECAR_ROWS_NOT_ONCE_IN_TABLE',
                             '%s: %d of its rows are in the file %s'
                             % (label, len(wrong),
                                'a different number of times'
                                if any(have[t] for t in wrong)
                                else 'not at all')))
    return receipt, new, problems


def apply_workbook(base, logs, workbook_path):
    """Read, decide, and either apply the rows or leave the workbook alone.

    Separated from __main__ so the decision can be exercised. Everything the
    audit named as untested lived in that block: the precondition set, the
    verdict, the receipt it writes. Returns the receipt it wrote.
    """
    receipt, new, problems = preconditions(base, logs)
    if problems:
        for code, detail in problems:
            print('  %-32s %s' % (code, detail))
        return _receipt(logs, {'verdict': 'REFUSED_NO_WRITE',
                               'problems': [list(x) for x in problems],
                               'workbook_sha256_before':
                                   rowkey.file_digest(workbook_path),
                               'workbook_sha256_after':
                                   rowkey.file_digest(workbook_path)})

    with zipfile.ZipFile(workbook_path) as z:
        members = [(i, z.read(i.filename)) for i in z.infolist()]
    parts = {i.filename: d for i, d in members}

    # WHAT THE WORKBOOK ALREADY CARRIES, BEFORE DECIDING TO ADD ANYTHING. An
    # attested sidecar says the rows are the right rows. It does not say they
    # have not been applied - and this script used to append whatever it was
    # handed, so a second run put every row in twice.
    # AND THE WORKBOOK'S COLUMNS ARE THE FILE'S COLUMNS. The rows are written
    # from column A rightwards in the CSV's order; a workbook whose headings
    # are in a different order takes them all under the wrong ones, and the
    # sheet still looks well formed. The final manifest would find it later -
    # after the workbook had been changed, which is exactly what a
    # fail-closed mutation step is supposed to prevent.
    schema = []
    for sheet in sorted(new):
        declared = sheet_columns(parts, sheet)
        fields = list(load_table(base, sheet)[0] or ())
        if declared != fields:
            schema.append(('WORKBOOK_SCHEMA_MISMATCH',
                           '%s: the sheet declares %s and the file has %s'
                           % (sheet, declared, fields)))
    if schema:
        for code, detail in schema:
            print('  %-32s %s' % (code, detail))
        return _receipt(logs, {'verdict': 'REFUSED_NO_WRITE',
                               'problems': [list(x) for x in schema],
                               'workbook_sha256_before':
                                   rowkey.file_digest(workbook_path),
                               'workbook_sha256_after':
                                   rowkey.file_digest(workbook_path)})

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
        # Half applied, applied twice, or applied and then copied. Neither
        # adding the rows nor leaving them is right, and this step is not the
        # place to guess which.
        verdict = 'CONFLICT_NO_WRITE'

    before = rowkey.file_digest(workbook_path)
    applied = {}
    if verdict == 'APPLY':
        bak = os.path.join(base, 'archive',
                           'pre_supplement_integration_2026-08-30', WORKBOOK)
        if not os.path.exists(bak):
            os.makedirs(os.path.dirname(bak), exist_ok=True)
            shutil.copy2(workbook_path, bak)
        edited = {}
        for sheet, rows in sorted(new.items()):
            part_edits, a, b, tp = plan_append(parts, sheet, rows)
            # Planned against the parts as the previous sheet left them, so
            # both sheets and both table refs go in together.
            parts.update(part_edits)
            edited.update(part_edits)
            applied[sheet] = {'from_row': a, 'to_row': b, 'rows': len(rows),
                              'table_part': tp}
            print('  %-24s %d행 -> %d행 (+%d), 표 %s'
                  % (sheet, a, b, len(rows), tp))
        write_workbook(workbook_path, members, edited)

    return _receipt(logs, {
        'verdict': verdict,
        'sheet_states': states,
        'applied': applied,
        'workbook_sha256_before': before,
        'workbook_sha256_after': rowkey.file_digest(workbook_path),
        'new_rows_sha256': (receipt.get('sidecars') or {}).get('new_rows.json'),
        'persisted': receipt.get('persisted'),
        'writer_receipt_verdict': receipt.get('verdict')})


def _receipt(logs, body):
    os.makedirs(logs, exist_ok=True)
    json.dump(body, io.open(os.path.join(logs,
                                         'xlsx_append_rows_receipt.json'),
                            'w', encoding='utf-8'),
              indent=2, ensure_ascii=False)
    print('  판정: %s' % body['verdict'])
    return body


if __name__ == '__main__':
    # ONE HOME FOR THE BUNDLE, THE SAME ONE THE WRITERS USE. This script found
    # the workbook and the receipts by walking up from its own directory, so
    # the shipped copy read a different tree than FDT_BUNDLE named: it could
    # check one run's receipt and append to another run's workbook.
    with rowkey.write_lock(bundle_paths.write_lock()):
        out = apply_workbook(bundle_paths.BASE, bundle_paths.receipt_dir(),
                             os.path.join(bundle_paths.BASE, WORKBOOK))
    if out['verdict'] in ('CONFLICT_NO_WRITE', 'REFUSED_NO_WRITE'):
        raise SystemExit(1)
