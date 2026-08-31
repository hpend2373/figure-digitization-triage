# -*- coding: utf-8 -*-
"""Write the transcribed figure values into the effect table.

NOT DIGITIZATION. Neither of the two queued figures is measured off a plotted
point; both print their numbers as text beside the forest plot, which is why
`figure_extraction_queue.csv` routes them as TRANSCRIBE_PRINTED_NUMBERS. The
pixel-measurement pipeline and its counting gate are a different problem and
are untouched here.

WHERE THE NUMBERS LIVE, AND WHY NOT HERE. The values, the quoted definitions
and the article filenames are publisher-derived, so they sit in
`study_inputs.json`, which is not published. This file is the writer: it adds
the fail-closed posture, refuses to append twice, and leaves every human field
alone. Read `study_inputs.example.json` for the shape.

Each transcription in that file was checked against the rendered source page,
not taken from the routing queue - the queue is a plan, not evidence. Two
things that check surfaced are carried in the data as ordinary fields rather
than as special cases in code: a figure whose column header and axis label
disagree about what its numbers are gets discrepancy_flag=yes, and estimates
whose comparator is not printed anywhere on the page are held out of the effect
table entirely and listed under `figure_pending` instead. An unstated
comparator is not a detail to fill in later; it means the contrast the number
expresses is unknown.

pool_eligible=no, human_confirmed=no, human_gate=HUMAN_DUAL_EXTRACTION_REQUIRED
on every row, as for all machine transcription.
"""
import csv, hashlib, io, json, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import bundle_paths
import rowkey

BASE = bundle_paths.BASE
TODAY = '2026-08-30'
INPUTS = bundle_paths.study_inputs()

GATE = dict(candidate_after_human_confirmation='yes', pool_eligible='no',
            human_gate='HUMAN_DUAL_EXTRACTION_REQUIRED', schema_version='2',
            evidence_capture_type='STRUCTURED_TRANSCRIPTION_NOT_VERBATIM',
            derivation_method='reported',
            calculation_status='REPORTED_AI_TRANSCRIBED',
            effect_model='SEE_SOURCE_ANALYSIS_VARIANT',
            count_scope='DESCRIPTIVE_EXPOSURE_COUNTS_NOT_TIME_VARYING_MODEL_N',
            count_review_status='PARTIAL_REQUIRES_HUMAN_REVIEW',
            source_quote_status='STRUCTURED_TRANSCRIPTION_NOT_VERBATIM',
            human_confirmed='no', ai_correction_date=TODAY,
            extraction_scope_status='FIGURE_PRINTED_NUMBERS_NOT_EXHAUSTIVE',
            source_or_derivation_blocked='no',
            data_source='figure (printed numbers)')


def sha(p):
    h = hashlib.sha256()
    with open(p, 'rb') as f:
        for b in iter(lambda: f.read(65536), b''):
            h.update(b)
    return h.hexdigest()


p = os.path.join(BASE, 'effect_extraction_text_long.csv')
with io.open(p, encoding='utf-8-sig', newline='') as fh:
    rd = csv.DictReader(fh)
    cols, rows = rd.fieldnames, list(rd)

digests = {}
out = []
for spec in INPUTS['figure_rows']:
    src = spec['source_local_path']
    if src not in digests:
        digests[src] = sha(os.path.join(BASE, src))
    d = {c: '' for c in cols}
    d.update(GATE)
    d.update(spec)
    d['source_sha256'] = digests[src]
    out.append(d)

# The held estimates are recorded where a reviewer will see them, with their
# printed values intact, so that "not extracted" never means "not seen".
json.dump(INPUTS['figure_pending'],
          io.open(os.path.join(HERE, 'logs', 'R1087_coexposure_pending.json'),
                  'w', encoding='utf-8'), indent=2, ensure_ascii=False)

def assign_ids(_label, existing, intended):
    seq = {}
    for r in existing:
        m = re.match(r'^(R\d+)-T(\d+)$', r.get('effect_row_id') or '')
        if m:
            seq[m.group(1)] = max(seq.get(m.group(1), 0), int(m.group(2)))
    used = {r['effect_row_id'] for r in existing}
    for d in intended:
        seq[d['rec_id']] = seq.get(d['rec_id'], 0) + 1
        eid = '%s-T%03d' % (d['rec_id'], seq[d['rec_id']])
        assert eid not in used, eid
        used.add(eid)
        d['effect_row_id'] = eid


# ONE PROTOCOL, SHARED WITH THE OTHER WRITER. See `rowkey.run_writer`: the
# order of a write is where the defects were, and a writer that has already
# run never reaches it.
print('재실행 안전성 점검:')
if '--write' in sys.argv:
    verdict, written = rowkey.run_writer(
        'figure_printed_numbers',
        [('effects_text_long', p, cols, rows, out,
          rowkey.EFFECT_KEY, rowkey.EFFECT_VALUE)],
        os.path.join(HERE, 'logs'), assign_ids=assign_ids)
    may = verdict == 'WRITE'
    if may:
        json.dump([[r.get(c, '') for c in cols] for r in out],
                  io.open(os.path.join(HERE, 'logs', 'figure_rows.json'), 'w',
                          encoding='utf-8'), ensure_ascii=False)
else:
    may = rowkey.guard('figure_printed_numbers',
                       [('effects_text_long', rows, out,
                         rowkey.EFFECT_KEY, rowkey.EFFECT_VALUE)],
                       os.path.join(HERE, 'logs'))

print('전사 대상 %d행%s' % (len(out), '' if may else ' (가드가 쓰기를 막았습니다)'))
print('비교군이 없어 보류한 값 %d건' % len(INPUTS['figure_pending']['printed_values']))
