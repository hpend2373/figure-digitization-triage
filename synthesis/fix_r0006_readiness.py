# -*- coding: utf-8 -*-
"""R0006's effect rows must carry the readiness its route already locked.

`fulltext_screening.tsv`, `extraction_operational_status.csv` and
`source_corpus_receipt.csv` all classify R0006 as MR_SEPARATE - a Mendelian
randomization record kept out of the standard drug-exposure pool. Its three
figure-transcribed effect rows were written with QUANTITATIVE_CANDIDATE, which
is the value for a record that CAN join that pool. R0904, the only other MR
record, uses MR_SEPARATE on all twelve of its rows; this restores the same.

The row was never poolable in fact - pool_eligible=no on all 1,728 rows - so
nothing was at risk of being pooled. What was wrong is that the long table
disagreed with every other artifact about what kind of evidence this is, and
nothing in QC noticed. A gate for exactly that disagreement is added
separately.
"""
import csv, io, os, re, shutil, sys, zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bundle_paths
BASE = bundle_paths.BASE
WB = os.path.join(BASE, 'extraction_form_RASi_PCa.xlsx')
WANT = 'MR_SEPARATE'

p = os.path.join(BASE, 'effect_extraction_text_long.csv')
with io.open(p, encoding='utf-8-sig', newline='') as fh:
    rd = csv.DictReader(fh)
    cols, rows = rd.fieldnames, list(rd)
col = cols.index('synthesis_readiness')
letter = chr(ord('A') + col) if col < 26 else None
assert letter == 'G', (col, letter)

hit = [i + 2 for i, r in enumerate(rows)
       if r['rec_id'] == 'R0006' and r['synthesis_readiness'] != WANT]
for i in hit:
    rows[i - 2]['synthesis_readiness'] = WANT
if hit:
    with io.open(p, 'w', encoding='utf-8', newline='') as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)
print('CSV에서 고친 행: %s' % hit)

with zipfile.ZipFile(WB) as z:
    wbx = z.read('xl/workbook.xml').decode('utf-8')
    rels = z.read('xl/_rels/workbook.xml.rels').decode('utf-8')
    members = [(i, z.read(i.filename)) for i in z.infolist()]
raw = dict((i.filename, d) for i, d in members)
m = re.search(r'<x:sheet name="effects_text_long"[^>]*r:id="([^"]+)"', wbx)
t = (re.search(r'Target="([^"]+)"[^>]*Id="%s"' % m.group(1), rels)
     or re.search(r'Id="%s"[^>]*Target="([^"]+)"' % m.group(1), rels))
part = t.group(1).lstrip('/')
x = raw[part].decode('utf-8')
n = 0
for i in hit:
    cell = '<x:c r="G%d" t="str"><x:v>%s</x:v></x:c>' % (i, WANT)
    if re.search(r'<x:c r="G%d"' % i, x):
        x, k = re.subn(r'<x:c r="G%d"[^>]*>.*?</x:c>' % i, cell, x, count=1,
                       flags=re.S)
    else:
        x, k = re.subn(r'(<x:c r="F%d"[^>]*>.*?</x:c>)' % i, r'\1' + cell, x,
                       count=1, flags=re.S)
    n += k
print('워크북에서 고친 셀: %d' % n)
if n:
    shutil.copy2(WB, os.path.join(BASE, 'archive',
                                  'pre_supplement_integration_2026-08-30',
                                  'extraction_form_RASi_PCa.pre_readiness.xlsx'))
    tmp = WB + '.tmp'
    with zipfile.ZipFile(tmp, 'w', zipfile.ZIP_DEFLATED) as out:
        for info, data in members:
            out.writestr(info, x.encode('utf-8') if info.filename == part else data)
    shutil.move(tmp, WB)
