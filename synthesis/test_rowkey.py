# -*- coding: utf-8 -*-
"""Scenarios for the append guard.

    python3 test_rowkey.py      # exit 0 = all scenarios pass

WHY THIS IS THE MOST SAFETY-CRITICAL PIECE HERE. Both writers used to mint an
id one past the current maximum and append. A second run did not recognise its
own previous output, so it would have appended all 120 rows again and doubled
every estimate in a table meant for meta-analysis. Nothing would have failed;
the file would simply have been wrong.

The scenarios below are about the three outcomes, and the third is the point:
a table that is PARTLY written is a question for a person, not something to
finish by guessing. Revert the conflict branch and scenarios about half-written
and disagreeing tables die.

Writes only into a temporary directory.
"""
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rowkey as K                                              # noqa: E402

FAIL, N = [], [0]
TMP = tempfile.mkdtemp(prefix='fdt_rowkey_')


def check(name, ok, detail=''):
    print(('  ok   ' if ok else '  FAIL ') + name + ('' if ok else '  <- ' + detail))
    if ok:
        N[0] += 1
    else:
        FAIL.append(name)


def eff(rid, sha, ref, expo, out, variant, meas, point, low='', high=''):
    return {'rec_id': rid, 'source_sha256': sha, 'source_page_ref': ref,
            'exposure_definition': expo, 'outcome_name': out,
            'analysis_variant': variant, 'effect_measure': meas,
            'effect_point': point, 'effect_ci_low': low, 'effect_ci_high': high,
            'ci_level': '95', 'n_exposed': '', 'events_exposed': '',
            'synthesis_readiness': 'QUANTITATIVE_CANDIDATE',
            'analysis_stream': 'S1_incidence', 'effect_row_id': 'IGNORED'}


A = eff('R1', 'sha1', 'Table 2', 'drug A', 'outcome X', 'adjusted', 'HR', '1.10',
        '0.90', '1.30')
B = eff('R1', 'sha1', 'Table 2', 'drug B', 'outcome X', 'adjusted', 'HR', '0.80',
        '0.60', '1.05')

print('the append guard')

# ---- identity does not include the ordinal
moved = dict(A, effect_row_id='R1-T999')
check('effect_row_id는 정체성이 아니다 - 순번이 바뀌어도 같은 행이다',
      K.key_of(A, K.EFFECT_KEY) == K.key_of(moved, K.EFFECT_KEY))
check('노출이 다르면 다른 행이다',
      K.key_of(A, K.EFFECT_KEY) != K.key_of(B, K.EFFECT_KEY))
check('같은 값이라도 원본 파일이 다르면 다른 행이다',
      K.key_of(A, K.EFFECT_KEY) != K.key_of(dict(A, source_sha256='sha2'),
                                            K.EFFECT_KEY))

# ---- the three outcomes
miss, same, conf = K.compare([], [A, B], K.EFFECT_KEY, K.EFFECT_VALUE)
check('빈 표에는 둘 다 없음으로 나온다', (len(miss), len(same), len(conf)) == (2, 0, 0))

miss, same, conf = K.compare([A, B], [A, B], K.EFFECT_KEY, K.EFFECT_VALUE)
check('이미 다 있으면 전부 동일로 나온다', (len(miss), len(same), len(conf)) == (0, 2, 0))

miss, same, conf = K.compare([A], [A, B], K.EFFECT_KEY, K.EFFECT_VALUE)
check('일부만 있으면 없음과 동일이 함께 나온다',
      (len(miss), len(same), len(conf)) == (1, 1, 0))

drifted = dict(A, effect_point='1.99')
miss, same, conf = K.compare([drifted], [A], K.EFFECT_KEY, K.EFFECT_VALUE)
check('키는 같은데 값이 다르면 충돌이다',
      (len(miss), len(same), len(conf)) == (0, 0, 1))
check('충돌은 파일에 있는 값과 쓰려던 값을 둘 다 들고 온다',
      conf and conf[0][0]['effect_point'] == '1.10'
      and conf[0][1]['effect_point'] == '1.99')

# ---- the verdicts the writers act on
check('아무것도 없으면 쓴다',
      K.guard('t_write', [('effects', [], [A, B], K.EFFECT_KEY, K.EFFECT_VALUE)],
              TMP) is True)
check('전부 같으면 쓰지 않는다 - 재실행은 무해한 no-op이다',
      K.guard('t_same', [('effects', [A, B], [A, B], K.EFFECT_KEY,
                          K.EFFECT_VALUE)], TMP) is False)
check('반만 쓰인 표에는 쓰지 않는다 - 사람에게 물을 일이다',
      K.guard('t_half', [('effects', [A], [A, B], K.EFFECT_KEY,
                          K.EFFECT_VALUE)], TMP) is False)
check('값이 어긋나면 쓰지 않는다',
      K.guard('t_conf', [('effects', [drifted], [A], K.EFFECT_KEY,
                          K.EFFECT_VALUE)], TMP) is False)
check('여러 표 중 하나만 충돌해도 전체를 막는다',
      K.guard('t_multi', [('a', [], [B], K.EFFECT_KEY, K.EFFECT_VALUE),
                          ('b', [drifted], [A], K.EFFECT_KEY, K.EFFECT_VALUE)],
              TMP) is False)

# ---- the receipt exists and names the verdict
import json                                                     # noqa: E402
rep = json.load(open(os.path.join(TMP, 't_conf_idempotency.json'),
                     encoding='utf-8'))
check('충돌 영수증이 판정을 적는다', rep['verdict'] == 'CONFLICT_NO_WRITE')
check('충돌 영수증이 어긋난 행의 예를 담는다',
      len(rep['effects']['conflict_examples']) == 1)
check('무해한 재실행 영수증은 다른 판정을 적는다',
      json.load(open(os.path.join(TMP, 't_same_idempotency.json'),
                     encoding='utf-8'))['verdict'] == 'ALREADY_PRESENT_NO_WRITE')

# ---- counts use their own identity
C = {'rec_id': 'R1', 'source_sha256': 'sha1', 'source_page_ref': 'Table 2',
     'quantity': 'deaths', 'group_role': 'users', 'value': '12',
     'unit': 'events', 'count_basis': 'raw'}
check('카운트는 수량과 그룹으로 구분된다',
      K.key_of(C, K.COUNT_KEY) != K.key_of(dict(C, quantity='participants'),
                                           K.COUNT_KEY))
check('같은 카운트를 다시 쓰려 하면 동일로 잡힌다',
      len(K.compare([C], [C], K.COUNT_KEY, K.COUNT_VALUE)[1]) == 1)

shutil.rmtree(TMP, ignore_errors=True)
print()
print('FDT_SCENARIOS_RUN=%d' % N[0])
print('%d scenarios run' % N[0])
if FAIL:
    print('%d FAILED: %s' % (len(FAIL), FAIL))
    raise SystemExit(1)
print('all scenarios passed')
