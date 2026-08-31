# -*- coding: utf-8 -*-
"""Rebuild a formula-free workbook sheet from its CSV counterpart.

WHY THIS EXISTS. `operational_status_all_eligible` and `source_corpus_receipt`
are the two newest CSV-backed sheets, and both fell behind their CSVs: the
first still called R0006 and R1087 PENDING_FIGURE_EXTRACTION with zero linked
rows, the second held 74 rows to the CSV's 85 and was missing every
SOURCE_UNAVAILABLE record. The synchronization check that should have caught
this only knew about ten pairs, so it reported "all matched" while two sheets
were stale - the check's own scope was the defect.

Both sheets contain NO formulas, which is what makes wholesale replacement
safe here and unsafe elsewhere: nothing in them has a cached result to lose.
The script refuses to touch a sheet that has any formula, so it cannot be
pointed at `effects_text_long` by mistake.

Styles are carried over per column from the existing header and first data row,
and the sheet's table range is extended, so a rebuilt sheet still looks and
filters like the one it replaced.
"""
import csv, io, os, re, shutil, sys, zipfile
import xml.sax.saxutils as SU

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bundle_paths
BASE = bundle_paths.BASE
WB = os.path.join(BASE, 'extraction_form_RASi_PCa.xlsx')
NUM = re.compile(r'^-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?$')


def col_name(i):
    s = ''
    while i >= 0:
        s = chr(ord('A') + i % 26) + s
        i = i // 26 - 1
    return s


def styles_from(xml, rownum):
    out = {}
    m = re.search(r'<x:row r="%d"[^>]*>(.*?)</x:row>' % rownum, xml, re.S)
    if not m:
        return out
    for c in re.finditer(r'<x:c r="([A-Z]+)\d+"(?:\s+s="(\d+)")?', m.group(1)):
        if c.group(2):
            out[c.group(1)] = c.group(2)
    return out


def rebuild(sheet, csv_name):
    with zipfile.ZipFile(WB) as z:
        wbx = z.read('xl/workbook.xml').decode('utf-8')
        rels = z.read('xl/_rels/workbook.xml.rels').decode('utf-8')
        members = [(i, z.read(i.filename)) for i in z.infolist()]
    raw = dict((i.filename, d) for i, d in members)
    m = re.search(r'<x:sheet name="%s"[^>]*r:id="([^"]+)"' % re.escape(sheet), wbx)
    if not m:
        raise SystemExit('sheet not found: %s' % sheet)
    t = (re.search(r'Target="([^"]+)"[^>]*Id="%s"' % m.group(1), rels)
         or re.search(r'Id="%s"[^>]*Target="([^"]+)"' % m.group(1), rels))
    part = t.group(1).lstrip('/')
    xml = raw[part].decode('utf-8')
    if '<x:f>' in xml:
        raise SystemExit('%s contains formulas; refusing to rebuild' % sheet)

    with io.open(os.path.join(BASE, csv_name), encoding='utf-8-sig',
                 newline='') as fh:
        data = [r for r in csv.reader(fh) if any(c != '' for c in r)]
    hstyle, dstyle = styles_from(xml, 1), styles_from(xml, 2)

    body = []
    for n, row in enumerate(data, start=1):
        st = hstyle if n == 1 else dstyle
        cells = []
        for j, v in enumerate(row):
            if v == '':
                continue
            L = col_name(j)
            s = ' s="%s"' % st[L] if L in st else ''
            if NUM.match(v):
                cells.append('<x:c r="%s%d"%s t="n"><x:v>%s</x:v></x:c>'
                             % (L, n, s, v))
            else:
                cells.append('<x:c r="%s%d"%s t="str"><x:v>%s</x:v></x:c>'
                             % (L, n, s, SU.escape(v)))
        body.append('<x:row r="%d">%s</x:row>' % (n, ''.join(cells)))

    a = xml.index('<x:sheetData>')
    b = xml.index('</x:sheetData>') + len('</x:sheetData>')
    was = len(re.findall(r'<x:row r="\d+"', xml))
    xml = xml[:a] + '<x:sheetData>' + ''.join(body) + '</x:sheetData>' + xml[b:]
    last, ncol = len(data), max(len(r) for r in data)
    xml = re.sub(r'<x:dimension ref="[^"]*" ?/>',
                 '<x:dimension ref="A1:%s%d" />' % (col_name(ncol - 1), last),
                 xml, count=1)

    edited = {part: xml.encode('utf-8')}
    rl = re.sub(r'^xl/worksheets/', 'xl/worksheets/_rels/', part) + '.rels'
    if rl in raw:
        tm = re.search(r'Target="([^"]*/tables/[^"]+)"', raw[rl].decode('utf-8'))
        if tm:
            tp = tm.group(1).lstrip('/')
            tx = raw[tp].decode('utf-8')
            tx2, k = re.subn(r'(ref=")([A-Z]+)1:([A-Z]+)\d+(")',
                             lambda s: s.group(1) + s.group(2) + '1:'
                             + s.group(3) + str(last) + s.group(4), tx)
            if not k:
                raise SystemExit('table ref not found for %s' % sheet)
            edited[tp] = tx2.encode('utf-8')

    tmp = WB + '.tmp'
    with zipfile.ZipFile(tmp, 'w', zipfile.ZIP_DEFLATED) as out:
        for info, d in members:
            out.writestr(info, edited.get(info.filename, d))
    shutil.move(tmp, WB)
    print('%-34s %d행 -> %d행' % (sheet, was, last))


if __name__ == '__main__':
    bak = os.path.join(BASE, 'archive', 'pre_supplement_integration_2026-08-30',
                       'extraction_form_RASi_PCa.pre_sheet_rebuild.xlsx')
    if not os.path.exists(bak):
        shutil.copy2(WB, bak)
    rebuild('operational_status_all_eligible', 'extraction_operational_status.csv')
    rebuild('source_corpus_receipt', 'source_corpus_receipt.csv')
