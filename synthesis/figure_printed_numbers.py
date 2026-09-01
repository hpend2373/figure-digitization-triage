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
# COLUMNS, ROWS AND DIGEST FROM ONE READ. The digest was taken at the
# run_writer call below, after the figure specs had been parsed and every
# source page hashed; a writer committing in that gap would have handed this
# run old rows with a current digest, which is what the stale-snapshot check
# reads as fresh.
cols, rows, read_digest = rowkey.load_csv_snapshot(p)

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

RECEIPTS = bundle_paths.receipt_dir()

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
write = '--write' in sys.argv
verdict, written = rowkey.run_writer(
    'figure_printed_numbers',
    [('effects_text_long', p, cols, rows, out,
      rowkey.EFFECT_KEY, rowkey.EFFECT_VALUE)],
    RECEIPTS,
    assign_ids=assign_ids if write else None,
    assignable={'effect_row_id'},
    journal_path=os.path.join(RECEIPTS, 'figure_printed_numbers_journal.json'),
    lock_path=bundle_paths.write_lock(),
    read_digests={'effects_text_long': read_digest},
    attest={'writer_code_sha256': rowkey.file_digest(os.path.abspath(__file__)),
            'study_inputs_sha256': rowkey.file_digest(bundle_paths.STUDY_INPUTS),
            'sources': {os.path.basename(v): rowkey.file_digest(
                os.path.join(BASE, v)) for v in digests}},
    dry_run=not write)
may = verdict == 'WRITE'
# THE SIDECARS BELONG TO THE VERDICT. The held estimates used to be dumped
# before the guard had spoken, so a run the guard refused still left a file
# that read as its output. Both are written only on a verdict that says the
# tables are what this run means them to be, and both are then recorded in
# the receipt - see `rowkey.attest_sidecars`.
if may or verdict == rowkey.CLEAN_RERUN:
    # The ordinals are in `out` either way: minted here on a write, read back
    # off the file on a clean rerun. So this run can say what the sidecars
    # must contain whether or not it is the run that wrote them.
    _side = {'figure_rows.json': [[r.get(c, '') for c in cols] for r in out],
             # The held estimates are recorded where a reviewer will see them,
             # with their printed values intact, so that "not extracted" never
             # means "not seen".
             'R1087_coexposure_pending.json': INPUTS['figure_pending']}
    if may:
        json.dump(_side['figure_rows.json'],
                  io.open(os.path.join(RECEIPTS, 'figure_rows.json'), 'w',
                          encoding='utf-8'), ensure_ascii=False)
    json.dump(INPUTS['figure_pending'],
              io.open(os.path.join(RECEIPTS, 'R1087_coexposure_pending.json'),
                      'w', encoding='utf-8'), indent=2, ensure_ascii=False)
    rowkey.attest_sidecars(RECEIPTS, 'figure_printed_numbers', _side)

print('전사 대상 %d행%s' % (len(out), '' if may else ' (가드가 쓰기를 막았습니다)'))
print('비교군이 없어 보류한 값 %d건' % len(INPUTS['figure_pending']['printed_values']))
