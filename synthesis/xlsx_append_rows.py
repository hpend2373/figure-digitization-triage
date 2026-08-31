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
import xml.sax.saxutils as SU

NUM = re.compile(r'^-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?$')


def col_name(i):
    s = ''
    while i >= 0:
        s = chr(ord('A') + i % 26) + s
        i = i // 26 - 1
    return s


def sheet_part(z, name):
    wbx = z.read('xl/workbook.xml').decode('utf-8')
    m = re.search(r'<x:sheet name="%s"[^>]*r:id="([^"]+)"' % re.escape(name), wbx)
    if not m:
        raise SystemExit('sheet not found: %s' % name)
    rels = z.read('xl/_rels/workbook.xml.rels').decode('utf-8')
    t = re.search(r'Target="([^"]+)"[^>]*Id="%s"' % re.escape(m.group(1)), rels) \
        or re.search(r'Id="%s"[^>]*Target="([^"]+)"' % re.escape(m.group(1)), rels)
    return t.group(1).lstrip('/')


def table_part(z, sheet_p):
    """The Excel table object over this sheet, if it has one.

    A row appended past the table's `ref` is on the sheet but outside the
    table, so filters and structured references quietly stop at the old last
    row - the rows would be there and yet not there."""
    rl = re.sub(r'^xl/worksheets/', 'xl/worksheets/_rels/', sheet_p) + '.rels'
    if rl not in z.namelist():
        return None
    m = re.search(r'Target="([^"]*/tables/[^"]+)"', z.read(rl).decode('utf-8'))
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


def append(path, sheet, rows):
    with zipfile.ZipFile(path) as z:
        part = sheet_part(z, sheet)
        tpart = table_part(z, part)
        xml = z.read(part).decode('utf-8')
        members = [(i, z.read(i.filename)) for i in z.infolist()]
    last = max(int(m.group(1)) for m in re.finditer(r'<x:row r="(\d+)"', xml))
    add = build_rows(rows, last + 1, styles_of_last_row(xml))
    i = xml.rindex('</x:sheetData>')
    xml = xml[:i] + add + xml[i:]
    new_last = last + len(rows)

    edited = {part: xml.encode('utf-8')}
    if tpart:
        t = dict(members)
        traw = [d for inf, d in members if inf.filename == tpart][0].decode('utf-8')
        traw2, n = re.subn(r'(ref=")([A-Z]+)1:([A-Z]+)\d+(")',
                           lambda m: m.group(1) + m.group(2) + '1:' + m.group(3)
                           + str(new_last) + m.group(4), traw)
        if not n:
            raise SystemExit('table ref not found in %s' % tpart)
        edited[tpart] = traw2.encode('utf-8')

    tmp = path + '.tmp'
    with zipfile.ZipFile(tmp, 'w', zipfile.ZIP_DEFLATED) as out:
        for info, data in members:
            out.writestr(info, edited.get(info.filename, data))
    shutil.move(tmp, path)
    return last, new_last, tpart


if __name__ == '__main__':
    here = os.path.dirname(os.path.abspath(__file__))
    base = os.path.abspath(os.path.join(here, '..', '..'))
    wbp = os.path.join(base, 'extraction_form_RASi_PCa.xlsx')
    new = json.load(io.open(os.path.join(here, 'logs', 'new_rows.json'),
                            encoding='utf-8'))
    bak = os.path.join(base, 'archive', 'pre_supplement_integration_2026-08-30',
                       'extraction_form_RASi_PCa.xlsx')
    if not os.path.exists(bak):
        shutil.copy2(wbp, bak)
    for sheet, rows in new.items():
        a, b, tp = append(wbp, sheet, rows)
        print('%-24s %d행 -> %d행 (+%d), 표 %s' % (sheet, a, b, len(rows), tp))
