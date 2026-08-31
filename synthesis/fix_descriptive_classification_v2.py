# -*- coding: utf-8 -*-
"""Put 52 baseline descriptors back in the descriptive column, and repair one
stale formula range - touching no cached value that is not a COUNTIF result.

WHAT WENT WRONG. The supplement integration wrote every new row with
derivation_method='reported'. Right for a hazard ratio, wrong for a median, an
IQR bound, a mean or an SD - and derivation_method is what the workbook's
tallies key on (reported_rows counts AM="reported", descriptive_rows counts
AM="reported descriptive statistic"). So 52 baseline descriptors were counted
as reported EFFECT ESTIMATES; R0855 read 44 reported where 8 is right.

WHAT WENT WRONG IN THE FIRST ATTEMPT AT THIS FIX, and why this file is v2. Its
recompute() summed the COUNTIF calls it found in a formula and returned that
sum - so a formula containing NO COUNTIF, such as ='effects_text_long'!AA8 or
=COUNTA(...), got back the empty sum, zero. It wrote 0 over 160 live cached
values in the `extraction` sheet before the report printed. The workbook was
restored from the backup taken at the top of that run. The lesson is in the
guard below: a formula is recomputed ONLY if it is a pure sum of COUNTIF calls
over the effects table, and anything else is returned untouched rather than
evaluated to a default.

ALSO FIXED: text_extraction_summary!B26 still counts over rows 2:1609 - the
workbook's last row before the 2026-08-30 append - so it silently ignores every
row added that day. Its ranges are extended like its neighbours' already were.
"""
import csv, io, os, re, shutil, zipfile
import xml.sax.saxutils as SU

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import bundle_paths
BASE = bundle_paths.BASE
WB = os.path.join(BASE, 'extraction_form_RASi_PCa.xlsx')
DESC = 'reported descriptive statistic'
DESC_MEASURES = {'median', 'IQR_low', 'IQR_high', 'mean', 'SD'}


def col_index(name):
    n = 0
    for ch in name:
        n = n * 26 + (ord(ch) - 64)
    return n - 1


p = os.path.join(BASE, 'effect_extraction_text_long.csv')
with io.open(p, encoding='utf-8-sig', newline='') as fh:
    rd = csv.DictReader(fh)
    cols, rows = rd.fieldnames, list(rd)
assert cols[col_index('AM')] == 'derivation_method'

# the CSV was already corrected; these are the workbook rows that must follow
targets = [i + 2 for i, r in enumerate(rows)
           if r['ai_correction_date'] == '2026-08-30'
           and r['effect_measure'] in DESC_MEASURES]
still = [i + 2 for i, r in enumerate(rows)
         if r['ai_correction_date'] == '2026-08-30'
         and r['effect_measure'] in DESC_MEASURES
         and r['derivation_method'] != DESC]
if still:
    for i in still:
        rows[i - 2]['derivation_method'] = DESC
    with io.open(p, 'w', encoding='utf-8', newline='') as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)
print('서술 분류 대상 %d행 (CSV에서 이번에 고친 행 %d)' % (len(targets), len(still)))


def countifs(terms):
    n = 0
    for r in rows:
        for letter, crit in terms:
            v = r[cols[col_index(letter)]]
            if crit == '<>':
                ok = v != ''
            elif crit.startswith('<>'):
                ok = v != crit[2:]
            else:
                ok = v == crit
            if not ok:
                break
        else:
            n += 1
    return n


RANGE = r"'effects_text_long'!\$([A-Z]+)\$\d+:\$[A-Z]+\$(\d+)"
PAIR = re.compile(RANGE + r'\s*,\s*(?:"([^"]*)"|\$?([A-Z]+)\$?(\d+))')


def spans(f):
    out = []
    for m in re.finditer(r'COUNTIFS?\(', f):
        i, depth = m.end(), 1
        while i < len(f) and depth:
            depth += (f[i] == '(') - (f[i] == ')')
            i += 1
        out.append((m.start(), i))
    return out


def recompute(f, resolve):
    """A number ONLY for a formula that is a pure sum of COUNTIFs over the
    effects table. Anything else - a direct reference, COUNTA, ROUND, an
    argument shape this does not fully understand - returns None and the cell
    is left exactly as found. The first version of this fix returned an empty
    sum, 0, for such formulas and overwrote 160 live cached values with zero."""
    sp = spans(f)
    if not sp:
        return None
    rest = f
    for a, b in reversed(sp):
        rest = rest[:a] + rest[b:]
    if re.sub(r'[\s+=]', '', rest):
        return None
    total = 0
    for a, b in sp:
        inner = f[a:b][f[a:b].index('(') + 1:-1]
        terms, consumed = [], 0
        for m in PAIR.finditer(inner):
            lit, rc, rr = m.group(3), m.group(4), m.group(5)
            crit = lit if lit is not None else resolve(rc, int(rr))
            if crit is None:
                return None
            terms.append((m.group(1), str(crit)))
            consumed = m.end()
        # every argument must have been consumed by a pair we understood
        if not terms or inner[consumed:].strip():
            return None
        total += countifs(terms)
    return total


# ------------------------------------------------------------- the workbook
import openpyxl
_vals = openpyxl.load_workbook(WB, data_only=True)

with zipfile.ZipFile(WB) as z:
    wbx = z.read('xl/workbook.xml').decode('utf-8')
    rels = z.read('xl/_rels/workbook.xml.rels').decode('utf-8')
    members = [(i, z.read(i.filename)) for i in z.infolist()]
raw = dict((i.filename, d) for i, d in members)


def part_of(name):
    m = re.search(r'<x:sheet name="%s"[^>]*r:id="([^"]+)"' % re.escape(name), wbx)
    t = (re.search(r'Target="([^"]+)"[^>]*Id="%s"' % m.group(1), rels)
         or re.search(r'Id="%s"[^>]*Target="([^"]+)"' % m.group(1), rels))
    return t.group(1).lstrip('/')


bak = os.path.join(BASE, 'archive', 'pre_supplement_integration_2026-08-30',
                   'extraction_form_RASi_PCa.pre_classification_fix.xlsx')
if not os.path.exists(bak):
    shutil.copy2(WB, bak)

edited = {}

ep = part_of('effects_text_long')
x = raw[ep].decode('utf-8')
n = 0
for r in targets:
    x, k = re.subn(r'(<x:c r="AM%d"[^>]*><x:v>)reported(</x:v></x:c>)' % r,
                   r'\1' + DESC + r'\2', x, count=1)
    n += k
print('워크북 AM 셀 갱신: %d개 / 대상 %d개' % (n, len(targets)))
assert n == len(targets), (n, len(targets))
edited[ep] = x.encode('utf-8')

STALE = re.compile(r"('effects_text_long'!\$[A-Z]+\$2:\$[A-Z]+\$)1609")
CELL = re.compile(r'<x:c r="([A-Z]+)(\d+)"([^>]*)><x:f>(.*?)</x:f><x:v>([^<]*)</x:v></x:c>')
report, skipped = [], []
for sheet in ('text_extraction_status', 'text_extraction_summary', 'extraction',
              'stream_routing', 'audit_summary_final', 'text_remaining_work'):
    sp = part_of(sheet)
    sx = (edited.get(sp) or raw[sp]).decode('utf-8')
    ws = _vals[sheet]
    stats = [0, 0, 0, 0]

    def fix(m):
        c, rn, attrs, f, cached = m.groups()
        if 'effects_text_long' not in f:
            return m.group(0)
        f2, widened = STALE.subn(lambda s: s.group(1) + '1725', f)
        stats[3] += bool(widened)
        got = recompute(SU.unescape(f2), lambda cc, rr: ws['%s%d' % (cc, rr)].value)
        if got is None:
            stats[2] += 1
            skipped.append((sheet, c + rn))
            return ('<x:c r="%s%s"%s><x:f>%s</x:f><x:v>%s</x:v></x:c>'
                    % (c, rn, attrs, f2, cached)) if widened else m.group(0)
        stats[0] += 1
        if str(got) != cached:
            stats[1] += 1
            report.append((sheet, c + rn, cached, str(got)))
        return ('<x:c r="%s%s"%s><x:f>%s</x:f><x:v>%s</x:v></x:c>'
                % (c, rn, attrs, f2, got))

    sx2 = CELL.sub(fix, sx)
    if sx2 != sx:
        edited[sp] = sx2.encode('utf-8')
    if any(stats):
        print('  %-26s 재계산 %3d, 값변경 %2d, 건드리지않음 %3d, 범위확장 %d'
              % (sheet, stats[0], stats[1], stats[2], stats[3]))

tmp = WB + '.tmp'
with zipfile.ZipFile(tmp, 'w', zipfile.ZIP_DEFLATED) as out:
    for info, data in members:
        out.writestr(info, edited.get(info.filename, data))
shutil.move(tmp, WB)

print()
print('바뀐 캐시값 %d개:' % len(report))
for s, ref, a, b in report:
    print('   %-26s %-5s %s -> %s' % (s, ref, a, b))
