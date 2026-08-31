# -*- coding: utf-8 -*-
"""Scenarios for the cross-artifact route gate in qc_extraction.check_long.

    python3 test_readiness_gate.py      # exit 0 = all scenarios pass

A gate with no scenario that can fail is decoration. The defect this gate
exists for was real and shipped: three R0006 effect rows carried
synthesis_readiness=QUANTITATIVE_CANDIDATE while screening, the operational
status table and the corpus receipt all said MR_SEPARATE, and every existing
QC check passed because each looked at one artifact at a time.

So the scenarios below do not merely assert that today's data is clean - they
reintroduce the defect and require the gate to catch it, and they check the
gate stays quiet where it should. Revert the gate and scenarios 2, 3 and 5 die.
"""
import os, sys
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bundle_paths
BASE = bundle_paths.BASE
sys.path.insert(0, BASE)
import qc_extraction as QC

FAIL, N = [], [0]


def check(name, ok, detail=''):
    print(('  ok   ' if ok else '  FAIL ') + name + ('' if ok else '  <- ' + detail))
    if ok:
        N[0] += 1
    else:
        FAIL.append(name)


eff = pd.read_csv(os.path.join(BASE, 'effect_extraction_text_long.csv'),
                  dtype=object, encoding='utf-8-sig').fillna('')
scr = pd.read_csv(os.path.join(BASE, 'fulltext_screening.tsv'), sep='\t',
                  dtype=object, encoding='utf-8-sig').fillna('')


def gate_hits(effects, code):
    f = QC.check_long(effects, screening=scr)
    return [] if not len(f) else list(f[f.check == code].rec_id)


print('cross-artifact route gate')

# 1. the shipped table agrees with screening everywhere
check('현재 표에는 readiness 불일치가 없다',
      gate_hits(eff, 'effect_readiness_mismatch') == [],
      '%s' % gate_hits(eff, 'effect_readiness_mismatch')[:5])
check('현재 표에는 stream 불일치도 없다',
      gate_hits(eff, 'effect_stream_mismatch') == [])

# 2. THE DEFECT ITSELF, put back
bad = eff.copy()
mask = bad.rec_id == 'R0006'
bad.loc[mask, 'synthesis_readiness'] = 'QUANTITATIVE_CANDIDATE'
hits = gate_hits(bad, 'effect_readiness_mismatch')
check('R0006을 QUANTITATIVE_CANDIDATE로 되돌리면 3행이 걸린다',
      len(hits) == 3, '%d개 걸림' % len(hits))
check('걸린 것이 R0006의 행이다',
      set(hits) == set(bad.loc[mask, 'effect_row_id']), '%s' % hits)

# 3. the same defect on the other MR record
bad2 = eff.copy()
m2 = bad2.rec_id == 'R0904'
bad2.loc[m2, 'synthesis_readiness'] = 'QUANTITATIVE_CANDIDATE'
check('R0904에 같은 결함을 넣으면 12행이 걸린다',
      len(gate_hits(bad2, 'effect_readiness_mismatch')) == 12,
      '%d' % len(gate_hits(bad2, 'effect_readiness_mismatch')))

# 4. a record screening says nothing about is not invented into a finding
orphan = eff.head(3).copy()
orphan['rec_id'] = 'R9999'
check('스크리닝에 없는 기록은 판정하지 않는다',
      gate_hits(orphan, 'effect_readiness_mismatch') == []
      and gate_hits(orphan, 'effect_stream_mismatch') == [])

# 5. the stream half of the gate is not decoration either
bad3 = eff.copy()
bad3.loc[bad3.rec_id == 'R0006', 'analysis_stream'] = 'S1_incidence'
check('MR 기록의 stream을 S1로 바꾸면 걸린다',
      len(gate_hits(bad3, 'effect_stream_mismatch')) == 3,
      '%d' % len(gate_hits(bad3, 'effect_stream_mismatch')))

# 6. an empty cell is missing information, not a contradiction
blank = eff.copy()
blank.loc[blank.rec_id == 'R0006', 'synthesis_readiness'] = ''
check('빈 칸은 불일치로 세지 않는다',
      gate_hits(blank, 'effect_readiness_mismatch') == [])

print()
print('%d scenarios run' % N[0])
if FAIL:
    print('%d FAILED: %s' % (len(FAIL), FAIL))
    raise SystemExit(1)
print('all scenarios passed')
