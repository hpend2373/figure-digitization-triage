# -*- coding: utf-8 -*-
"""Scenarios for the cross-artifact route gate.

    python3 test_route_gate.py      # exit 0 = all scenarios pass

Reads no files: the rows are written here, so the defect the gate exists for
can be put back and required to be caught. Revert the comparison in
`route_gate.findings` and the scenarios below that name a mismatch die.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import route_gate as G                                          # noqa: E402

FAIL, N = [], [0]


def check(name, ok, detail=''):
    print(('  ok   ' if ok else '  FAIL ') + name + ('' if ok else '  <- ' + detail))
    if ok:
        N[0] += 1
    else:
        FAIL.append(name)


SCREEN = [{'rec_id': 'MR1', 'synthesis_readiness': 'MR_SEPARATE',
           'audit_v2_stream': 'S4_mendelian_randomization_separate'},
          {'rec_id': 'OBS1', 'synthesis_readiness': 'QUANTITATIVE_CANDIDATE',
           'audit_v2_stream': 'S1_incidence'},
          {'rec_id': 'BLANK1', 'synthesis_readiness': '', 'audit_v2_stream': ''}]
ROUTES = G.route_index(SCREEN)


def row(rid, ready, stream, eid='E1'):
    return {'rec_id': rid, 'effect_row_id': eid,
            'synthesis_readiness': ready, 'analysis_stream': stream}


print('cross-artifact route gate')

check('경로가 일치하는 행은 조용하다',
      G.findings([row('MR1', 'MR_SEPARATE', 'S4_mendelian_randomization_separate')],
                 ROUTES) == [])

# THE DEFECT, PUT BACK.
hit = G.findings([row('MR1', 'QUANTITATIVE_CANDIDATE',
                      'S4_mendelian_randomization_separate')], ROUTES)
check('MR 기록에 QUANTITATIVE_CANDIDATE를 넣으면 걸린다', len(hit) == 1, '%s' % hit)
check('사유가 readiness 불일치로 나온다',
      hit and hit[0][1] == 'effect_readiness_mismatch', '%s' % hit)
check('메시지가 양쪽 값을 모두 말한다',
      hit and 'QUANTITATIVE_CANDIDATE' in hit[0][2] and 'MR_SEPARATE' in hit[0][2],
      '%s' % (hit[0][2] if hit else ''))

check('stream 쪽도 장식이 아니다',
      [f[1] for f in G.findings([row('MR1', 'MR_SEPARATE', 'S1_incidence')], ROUTES)]
      == ['effect_stream_mismatch'])
check('둘 다 어긋나면 둘 다 보고한다',
      len(G.findings([row('MR1', 'QUANTITATIVE_CANDIDATE', 'S1_incidence')],
                     ROUTES)) == 2)

check('스크리닝이 판정하지 않은 기록은 건드리지 않는다',
      G.findings([row('UNKNOWN', 'MR_SEPARATE', 'S1_incidence')], ROUTES) == [])
check('행의 빈 칸은 모순이 아니라 미기입이다',
      G.findings([row('MR1', '', '')], ROUTES) == [])
check('스크리닝의 빈 칸도 마찬가지다',
      G.findings([row('BLANK1', 'MR_SEPARATE', 'S1_incidence')], ROUTES) == [])

check('한 기록의 모든 행이 각각 걸린다',
      len(G.findings([row('MR1', 'QUANTITATIVE_CANDIDATE',
                          'S4_mendelian_randomization_separate', 'E%d' % i)
                      for i in range(3)], ROUTES)) == 3)
check('걸린 행은 effect_row_id로 지목된다',
      sorted(f[0] for f in G.findings(
          [row('MR1', 'QUANTITATIVE_CANDIDATE',
               'S4_mendelian_randomization_separate', 'E%d' % i)
           for i in range(3)], ROUTES)) == ['E0', 'E1', 'E2'])
check('올바른 기록은 같은 배치 안에서도 조용하다',
      len(G.findings([row('MR1', 'QUANTITATIVE_CANDIDATE',
                          'S4_mendelian_randomization_separate'),
                      row('OBS1', 'QUANTITATIVE_CANDIDATE', 'S1_incidence', 'E2')],
                     ROUTES)) == 1)

print()
print('FDT_SCENARIOS_RUN=%d' % N[0])
print('%d scenarios run' % N[0])
if FAIL:
    print('%d FAILED: %s' % (len(FAIL), FAIL))
    raise SystemExit(1)
print('all scenarios passed')
