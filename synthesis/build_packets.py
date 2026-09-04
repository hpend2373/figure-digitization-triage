# -*- coding: utf-8 -*-
"""Assemble what a human reviewer needs in order to decide, for all 43 studies.

THIS PREPARES DECISIONS; IT DOES NOT MAKE THEM. Dual extraction, consensus,
risk of bias, cohort overlap and pooling permission are the reviewer's, and the
columns for them here are deliberately EMPTY, named exactly as the workbook
names them so an answer can be carried straight back. Nothing in this folder is
written into the extraction workbook or its CSVs.

What it does do is gather, per study, the things that are hard to see when the
evidence is spread over 1,700 rows: which rows carry a discrepancy flag, which
are blocked and why, which values the machine refused to read at all, and what
the source-coverage note says is still outstanding. A reviewer should be able to
open one packet and know what is in front of them.
"""
import collections, csv, io, json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import bundle_paths
BASE = bundle_paths.BASE


def read(name, delim=','):
    with io.open(os.path.join(BASE, name), encoding='utf-8-sig', newline='') as fh:
        return list(csv.DictReader(fh, delimiter=delim))


def write(path, cols, rows):
    with io.open(path, 'w', encoding='utf-8-sig', newline='') as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        for r in rows:
            w.writerow({c: r.get(c, '') for c in cols})


ops = read('extraction_operational_status.csv')
eff = read('effect_extraction_text_long.csv')
cnt = read('extraction_counts_long.csv')
cov = {r['rec_id']: r for r in read('text_table_coverage.csv')}
scr = {r['rec_id']: r for r in read('fulltext_screening.tsv', '\t')}

# values the integration step refused to turn into numbers, kept per record so
# they surface in the packet of the study they belong to rather than in a log
refused = collections.defaultdict(list)
rp = os.path.join(BASE, 'outputs', 'supplement_integration_2026-08-30',
                  'logs', 'integration.json')
if os.path.exists(rp):
    for b in json.load(io.open(rp, encoding='utf-8')).get('refused_values', []):
        refused[b['rec_id']].append(b)
# and the figure values deliberately left unextracted because the figure does
# not print the comparator they would be measured against
cp = os.path.join(BASE, 'outputs', 'supplement_integration_2026-08-30',
                  'logs', 'R1087_coexposure_pending.json')
if os.path.exists(cp):
    d = json.load(io.open(cp, encoding='utf-8'))
    for v in d['printed_values']:
        refused[d['rec_id']].append({
            'rec_id': d['rec_id'], 'field': 'co-exposure aOR',
            'where': '%s, %s' % (d['source_page_ref'], v['exposure_group']),
            'printed': '%s (99%% CI %s, %s)' % (v['aOR'], v['ci99_low'],
                                                v['ci99_high']),
            'reason': d['why_not_extracted']})

by_eff = collections.defaultdict(list)
for r in eff:
    by_eff[r['rec_id']].append(r)
by_cnt = collections.Counter(r['rec_id'] for r in cnt)


def needs_adjudication(r):
    cs = r['calculation_status']
    return (r['discrepancy_flag'] == 'yes'
            or r['source_or_derivation_blocked'] == 'yes'
            or cs.startswith(('BLOCKED', 'RECONSTRUCTED', 'SOURCE_INTERNAL')))


# ---- the register: every row a person has to rule on, one line each
REG_HUMAN = ['reviewer_initials', 'reviewer_decision', 'reviewer_date',
             'reviewer_note']
REG = (['rec_id', 'study_id', 'effect_row_id', 'why', 'calculation_status',
        'effect_measure', 'effect_point', 'effect_ci_low', 'effect_ci_high',
        'exposure_definition', 'outcome_name', 'analysis_variant',
        'source_page_ref', 'source_transcription', 'notes'] + REG_HUMAN)
reg = []
for r in eff:
    if not needs_adjudication(r):
        continue
    why = []
    if r['discrepancy_flag'] == 'yes':
        why.append('discrepancy_flag')
    if r['source_or_derivation_blocked'] == 'yes':
        why.append('source_or_derivation_blocked')
    if r['calculation_status'].startswith(('BLOCKED', 'RECONSTRUCTED',
                                           'SOURCE_INTERNAL')):
        why.append(r['calculation_status'])
    d = dict(r)
    d['why'] = '; '.join(sorted(set(why)))
    reg.append(d)
# and the values that never became rows, so they are not invisible
for rid, items in refused.items():
    for b in items:
        reg.append({'rec_id': rid, 'study_id': '', 'effect_row_id': '',
                    'why': 'REFUSED_AT_EXTRACTION',
                    'calculation_status': 'NOT_EXTRACTED',
                    'source_page_ref': b['where'],
                    'source_transcription': 'printed as: %s' % b['printed'],
                    'notes': b['reason']})
write(os.path.join(HERE, 'discrepancy_register.csv'), REG, reg)

# ---- risk of bias: one blank worksheet row per study, workbook column names
ROB = (['rec_id', 'study_id', 'year', 'study_design', 'analysis_stream',
        'local_source_path'] +
       ['rob_tool', 'nos_selection_stars', 'nos_comparability_stars',
        'nos_outcome_stars', 'nos_total_stars', 'robins_d1_confounding',
        'robins_d2_selection', 'robins_d3_classification',
        'robins_d4_deviations', 'robins_d5_missing', 'robins_d6_measurement',
        'robins_d7_reporting', 'rob_overall', 'rob_justification_verbatim',
        'immortal_time_bias_risk', 'detection_bias_psa_screening',
        'assessor_initials', 'assessment_date'])
write(os.path.join(HERE, 'rob_worksheet.csv'), ROB, ops)

# ---- dual extraction: what the second extractor is being asked to confirm
DUAL = (['rec_id', 'study_id', 'analysis_stream', 'operational_status',
         'effect_rows_to_confirm', 'rows_requiring_adjudication',
         'count_rows', 'source_blocks_reviewed', 'outstanding_work'] +
        ['extractor1_initials', 'extractor2_initials',
         'extraction_date_initial', 'extraction_date_consensus',
         'extraction_consensus_status', 'discrepancy_note', 'human_confirmed',
         'pool_eligible'])
dual = []
for o in ops:
    rid = o['rec_id']
    rows = by_eff.get(rid, [])
    dual.append(dict(o,
                     effect_rows_to_confirm=len(rows),
                     rows_requiring_adjudication=sum(1 for r in rows
                                                     if needs_adjudication(r)),
                     count_rows=by_cnt.get(rid, 0),
                     source_blocks_reviewed=cov.get(rid, {}).get(
                         'source_blocks_reviewed', ''),
                     extractor1_initials='', extractor2_initials='',
                     extraction_date_initial='', extraction_date_consensus='',
                     extraction_consensus_status='', discrepancy_note='',
                     human_confirmed='', pool_eligible=''))
write(os.path.join(HERE, 'dual_extraction_worklist.csv'), DUAL, dual)

# ---- index
IDX = ['rec_id', 'study_id', 'year', 'analysis_stream', 'operational_status',
       'effect_rows', 'rows_requiring_adjudication', 'count_rows',
       'refused_values', 'packet', 'title']
idx = []
for o in ops:
    rid = o['rec_id']
    rows = by_eff.get(rid, [])
    idx.append(dict(o, effect_rows=len(rows),
                    rows_requiring_adjudication=sum(1 for r in rows
                                                    if needs_adjudication(r)),
                    count_rows=by_cnt.get(rid, 0),
                    refused_values=len(refused.get(rid, [])),
                    packet='packets/%s.md' % rid))
write(os.path.join(HERE, 'INDEX.csv'), IDX, idx)

# ---- one readable packet per study
MEASURE_ORDER = ('HR', 'OR', 'RR', 'incidence_rate', 'median', 'mean')


def esc(s):
    return (s or '').replace('|', '\\|').replace('\n', ' ')


for o in ops:
    rid = o['rec_id']
    rows = by_eff.get(rid, [])
    adj = [r for r in rows if needs_adjudication(r)]
    s = scr.get(rid, {})
    c = cov.get(rid, {})
    L = ['# %s - %s (%s)' % (rid, o.get('study_id') or '(study_id 미기재)',
                             o.get('year', '')), '',
         o.get('title', ''), '']
    L += ['| | |', '|---|---|',
          '| screening | %s (r1 %s / r2 %s, concordant %s) |'
          % (s.get('ft_decision', ''), s.get('r1_decision', ''),
             s.get('r2_decision', ''), s.get('concordant', '')),
          '| stream | %s |' % o.get('analysis_stream', ''),
          '| operational status | %s |' % o.get('operational_status', ''),
          '| source | %s |' % (o.get('local_source_path') or '(없음)'),
          '| effect rows | %d (adjudication 필요 %d) |' % (len(rows), len(adj)),
          '| count rows | %d |' % by_cnt.get(rid, 0), '']
    if s.get('adjudication_note'):
        L += ['> 스크리닝 판정 근거: %s' % esc(s['adjudication_note']), '']
    if c.get('source_blocks_reviewed'):
        L += ['## 검토된 원본 블록', '', c['source_blocks_reviewed'], '',
              '## 추출 처분', '', c.get('extraction_disposition', ''), '']
    if o.get('outstanding_work'):
        L += ['## 남은 작업 (기계 판정)', '', o['outstanding_work'], '']

    if rows:
        byq = collections.Counter(r['effect_measure'] for r in rows)
        L += ['## 추출된 추정치', '',
              ', '.join('%s %d' % (k, v) for k, v in byq.most_common()), '']
    if adj:
        L += ['## 사람이 판정해야 하는 행 (%d)' % len(adj), '',
              '| effect_row_id | 사유 | 측도 | 값 | 노출 | 결과 | 출처 |',
              '|---|---|---|---|---|---|---|']
        for r in adj[:60]:
            why = []
            if r['discrepancy_flag'] == 'yes':
                why.append('discrepancy')
            if r['source_or_derivation_blocked'] == 'yes':
                why.append('blocked')
            val = r['effect_point']
            if r['effect_ci_low']:
                val += ' (%s-%s)' % (r['effect_ci_low'], r['effect_ci_high'])
            L.append('| %s | %s | %s | %s | %s | %s | %s |'
                     % (r['effect_row_id'],
                        esc('; '.join(why) or r['calculation_status']),
                        r['effect_measure'], esc(val),
                        esc(r['exposure_definition'])[:60],
                        esc(r['outcome_name'])[:40],
                        esc(r['source_page_ref'])[:40]))
        if len(adj) > 60:
            L.append('| ... | 나머지 %d행은 discrepancy_register.csv 참조 | | | | | |'
                     % (len(adj) - 60))
        L.append('')
    if refused.get(rid):
        L += ['## 기계가 읽기를 거부한 값 (%d)' % len(refused[rid]), '',
              '추정하지 않고 비워 둔 항목입니다. 원본을 보고 사람이 채워야 합니다.', '',
              '| 위치 | 인쇄된 모양 | 거부 사유 |', '|---|---|---|']
        for b in refused[rid]:
            L.append('| %s | `%s` | %s |'
                     % (esc(b['where']), esc(b['printed']), esc(b['reason'])))
        L.append('')
    L += ['## 이 패킷이 요청하는 판정', '',
          '아래는 전부 비어 있으며 사람만 채웁니다. 에이전트는 값을 넣지 않았습니다.', '',
          '- [ ] 2차 추출 (`extractor2_initials`, `extraction_date_initial`)',
          '- [ ] 합의 (`extraction_consensus_status`, `extraction_date_consensus`, `discrepancy_note`)',
          '- [ ] 비뚤림 위험 (`rob_tool` 및 NOS/ROBINS-I 항목, `rob_overall`, `rob_justification_verbatim`)',
          '- [ ] 코호트 중복 (`overlap_flag_reviewer1`, `overlap_flag_reviewer2`)',
          '- [ ] 사람 확인 (`human_confirmed`)',
          '- [ ] 풀링 허용 (`pool_eligible`)', '',
          '---', '', '작성: 2026-08-30 · 근거 파일: `effect_extraction_text_long.csv`, '
          '`extraction_operational_status.csv`, `text_table_coverage.csv`, '
          '`fulltext_screening.tsv`']
    io.open(os.path.join(HERE, 'packets', '%s.md' % rid), 'w',
            encoding='utf-8').write('\n'.join(L) + '\n')

print('패킷 %d개, adjudication 행 %d개, 거부값 %d건'
      % (len(ops), len(reg) - sum(len(v) for v in refused.values()),
         sum(len(v) for v in refused.values())))
