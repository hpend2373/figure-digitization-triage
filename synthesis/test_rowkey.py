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
import io
import json
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


def eff(rid, sha, ref, expo, out, variant, meas, point, low='', high='',
        subgroup='whole cohort', timepoint=''):
    return {'rec_id': rid, 'source_sha256': sha, 'source_page_ref': ref,
            'population_subgroup': subgroup, 'outcome_timepoint': timepoint,
            'exposure_definition': expo, 'outcome_name': out,
            'analysis_variant': variant, 'effect_measure': meas,
            'effect_point': point, 'effect_ci_low': low, 'effect_ci_high': high,
            'ci_level': '95', 'n_exposed': '', 'events_exposed': '',
            'derivation_method': 'reported',
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

# THE KEY MUST SEE WHAT MAKES TWO ROWS TWO ROWS. Both of these were found by
# the duplicate check against the real table: 93 keys claimed twice, none of
# them actually a duplicate - race-stratified rows and survival percentages at
# different timepoints, which the key could not tell apart and so called one
# row. A key that cannot separate them lets a rerun overwrite one with another.
check("a different population subgroup is a different row",
      K.key_of(A, K.EFFECT_KEY)
      != K.key_of(dict(A, population_subgroup='Black participants'),
                  K.EFFECT_KEY))
check("a different outcome timepoint is a different row",
      K.key_of(A, K.EFFECT_KEY)
      != K.key_of(dict(A, outcome_timepoint='24 months'), K.EFFECT_KEY))
# THE PARENT IS NAMED SEMANTICALLY. A count on file points at its parent by
# ordinal; a count about to be written cannot, because the ordinals do not
# exist yet. `annotate_parents` puts both on the same footing - without it the
# guard compared a blank against a filled cell and reported a table the writer
# had already written as empty.
_p1 = eff('R1', 'sha1', 'Table 2', 'drug A', 'outcome X', 'adjusted', 'HR',
          '1.10')
_p1['effect_row_id'] = 'R1-T001'
_p2 = eff('R1', 'sha1', 'Table 2', 'drug B', 'outcome X', 'adjusted', 'HR',
          '0.80')
_p2['effect_row_id'] = 'R1-T002'
_c1 = {'rec_id': 'R1', 'effect_row_id': 'R1-T001', 'quantity': 'n',
       'group_role': 'all', 'population_scope': 'x'}
_c2 = {'rec_id': 'R1', 'effect_row_id': 'R1-T002', 'quantity': 'n',
       'group_role': 'all', 'population_scope': 'x'}
K.annotate_parents([_c1, _c2], [_p1, _p2])
check("a count read beside a different estimate is a different count",
      K.key_of(_c1, K.COUNT_KEY) != K.key_of(_c2, K.COUNT_KEY))
check("and the parent is named by its key, not by its ordinal",
      "R1-T001" not in str(K.key_of(_c1, K.COUNT_KEY))
      and "drug A" in str(K.key_of(_c1, K.COUNT_KEY)))
_kept = [dict(_c1, parent_effect_key=str(K.key_of(_p1, K.EFFECT_KEY)))]
check("a parent named by key already, and matching, is left alone",
      K.annotate_parents(_kept, [_p1]) == []
      and _kept[0]["parent_effect_key"] == str(K.key_of(_p1, K.EFFECT_KEY)))
_orphan = [{'rec_id': 'R1'}]
check("a count with no parent at all still gets a comparable value",
      K.annotate_parents(_orphan, [_p1]) == []
      and _orphan[0]["parent_effect_key"] == "")

# ---- A PARENT REFERENCE IS CHECKED, NOT TRUSTED
# The same last-write-wins this file removed from the route index lived on
# here: two estimates sharing an ordinal resolved to whichever came last.
_dupe_parent = [dict(_p1), dict(_p2, effect_row_id='R1-T001')]
_c = [dict(_c1)]
check("an ordinal used by two estimates is reported, not resolved",
      [code for code, _ in K.annotate_parents(_c, _dupe_parent)]
      == ['DUPLICATE_EFFECT_ROW_ID'])
check("and such a count gets a parent that matches nothing",
      _c[0]['parent_effect_key'].startswith('?'))
_missing = [dict(_c1, effect_row_id='R1-T404')]
check("a parent that is not in the table is reported, not blanked",
      [code for code, _ in K.annotate_parents(_missing, [_p1])]
      == ['UNKNOWN_PARENT_EFFECT_ROW_ID'])
_mismatch = [dict(_c1, parent_effect_key='SOMETHING ELSE')]
check("a stated parent key that contradicts its ordinal is reported",
      [code for code, _ in K.annotate_parents(_mismatch, [_p1, _p2])]
      == ['PARENT_EFFECT_KEY_MISMATCH'])
check("a real table resolves with no problems at all",
      K.annotate_parents([dict(_c1), dict(_c2)], [_p1, _p2]) == [])
check("and the same count under a different stratum likewise",
      K.key_of({'rec_id': 'R1', 'effect_row_id': 'T', 'quantity': 'n',
                'group_role': 'all', 'population_scope': 'age 57-60'},
               K.COUNT_KEY)
      != K.key_of({'rec_id': 'R1', 'effect_row_id': 'T', 'quantity': 'n',
                   'group_role': 'all', 'population_scope': 'age 61-65'},
                  K.COUNT_KEY))

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

# ---- WHAT THE WRITER MUST REPRODUCE IS DERIVED, NOT LISTED
# The listed eight left out `derivation_method`, and that is the field whose
# wrong value on 52 rows counted baseline medians as reported effect estimates
# here. The guard would have called the wrong row and the corrected row
# identical and reported a clean no-op.
_desc = dict(A, derivation_method='reported')
_desc_fixed = dict(A, derivation_method='reported descriptive statistic')


def verdict_of(name, tables):
    """The receipt's verdict, not just whether the guard said no.

    `guard` returns False for BOTH a conflict and a clean no-op, so asserting
    `is False` cannot tell the two apart - a scenario written that way passes
    whether the code works or not, which is how the first version of these
    checks survived a mutation that reverted the whole payload rule.
    """
    K.guard(name, tables, TMP)
    return json.load(open(os.path.join(TMP, "%s_idempotency.json" % name),
                          encoding="utf-8"))["verdict"]


check("a row that differs only in derivation_method is a conflict",
      verdict_of("t_deriv", [("a", [_desc], [_desc_fixed], K.EFFECT_KEY,
                              K.EFFECT_VALUE)]) == "CONFLICT_NO_WRITE")
check("and so is one that differs in a field nobody thought to list",
      verdict_of("t_notes", [("a", [dict(A, notes='')],
                              [dict(A, notes='changed')], K.EFFECT_KEY,
                              K.EFFECT_VALUE)]) == "CONFLICT_NO_WRITE")
check("the payload is everything emitted, minus key, ordinal, clock and person",
      set(K.payload_fields([dict(A, notes='x', human_confirmed='no',
                                 ai_correction_date='2026-08-30',
                                 _transient='t')], K.EFFECT_KEY))
      == {'effect_point', 'effect_ci_low', 'effect_ci_high', 'ci_level',
          'n_exposed', 'events_exposed', 'synthesis_readiness',
          'analysis_stream', 'derivation_method', 'notes'},
      "%s" % sorted(K.payload_fields([dict(A, notes='x', human_confirmed='no',
                                           ai_correction_date='2026-08-30',
                                           _transient='t')], K.EFFECT_KEY)))

# AND WHAT IS NOT THE WRITER'S STAYS OUT. A reviewer confirming a row, or a
# renumbering, or the clock, must not turn the next rerun into a conflict - a
# guard that cried wolf on a human confirmation would be turned off.
for _label, _field, _value in (("a reviewer's confirmation", 'human_confirmed', 'yes'),
                               ("a pooling permission", 'pool_eligible', 'yes'),
                               ("a renumbering", 'effect_row_id', 'R1-T999'),
                               ("the run's clock", 'ai_correction_date', '2099-01-01')):
    check("%s leaves the rerun a clean no-op" % _label,
          verdict_of("t_ok_%s" % _field,
                     [("a", [dict(A, **{_field: _value})], [A],
                       K.EFFECT_KEY, K.EFFECT_VALUE)])
          == "ALREADY_PRESENT_NO_WRITE", _field)

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

# ---- THE VERDICT IS OVER ALL THE TABLES AT ONCE
# One output finished and another untouched came back WRITE, and appending then
# wrote the finished table a second time. A run either has not happened or has
# happened; anything between is a question.
check("one table done and another empty is a conflict, not a write",
      K.guard("t_mixed", [("effects", [A], [A], K.EFFECT_KEY, K.EFFECT_VALUE),
                          ("counts", [], [B], K.EFFECT_KEY, K.EFFECT_VALUE)],
              TMP) is False)
check("and the receipt names each table's state",
      json.load(open(os.path.join(TMP, "t_mixed_idempotency.json"),
                     encoding="utf-8"))["table_states"]
      == {"effects": K.IDENTICAL, "counts": K.EMPTY})
check("empty beside partial is a conflict too",
      K.guard("t_ep", [("a", [], [A], K.EFFECT_KEY, K.EFFECT_VALUE),
                       ("b", [A], [A, B], K.EFFECT_KEY, K.EFFECT_VALUE)],
              TMP) is False)
check("identical beside conflict is a conflict",
      K.guard("t_ic", [("a", [A], [A], K.EFFECT_KEY, K.EFFECT_VALUE),
                       ("b", [drifted], [A], K.EFFECT_KEY, K.EFFECT_VALUE)],
              TMP) is False)
check("all empty is still a write",
      K.guard("t_ee", [("a", [], [A], K.EFFECT_KEY, K.EFFECT_VALUE),
                       ("b", [], [B], K.EFFECT_KEY, K.EFFECT_VALUE)],
              TMP) is True)
check("all identical is still a clean no-op",
      K.guard("t_ii", [("a", [A], [A], K.EFFECT_KEY, K.EFFECT_VALUE),
                       ("b", [B], [B], K.EFFECT_KEY, K.EFFECT_VALUE)],
              TMP) is False)
check("and that no-op says so rather than reporting a conflict",
      json.load(open(os.path.join(TMP, "t_ii_idempotency.json"),
                     encoding="utf-8"))["verdict"] == "ALREADY_PRESENT_NO_WRITE")

# ---- A KEY THAT APPEARS TWICE IS AN ERROR WHEREVER IT SITS
# In a table of effect estimates headed for meta-analysis the same estimate
# twice is double weight, not a harmless repeat. Collapsing it hides the
# second; choosing one hides whichever was not chosen.
check("the same natural key twice is found",
      K.duplicates([A, dict(A, effect_row_id="OTHER")], K.EFFECT_KEY)
      == [K.key_of(A, K.EFFECT_KEY)])
check("distinct rows are not duplicates",
      K.duplicates([A, B], K.EFFECT_KEY) == [])
check("a duplicate already on file blocks the write",
      K.guard("t_dupe_file",
              [("a", [A, dict(A, effect_point="1.99")], [A],
                K.EFFECT_KEY, K.EFFECT_VALUE)], TMP) is False)
check("even when one of the two on file matches exactly",
      json.load(open(os.path.join(TMP, "t_dupe_file_idempotency.json"),
                     encoding="utf-8"))["a"]["duplicate_keys_on_file"] != [])
check("a writer that would emit the same row twice blocks itself",
      K.guard("t_dupe_new", [("a", [], [A, dict(A, effect_row_id="X")],
                              K.EFFECT_KEY, K.EFFECT_VALUE)], TMP) is False)
check("and the receipt says which side the duplicate is on",
      json.load(open(os.path.join(TMP, "t_dupe_new_idempotency.json"),
                     encoding="utf-8"))["a"]["duplicate_keys_intended"] != [])

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

# ---- A MISSING RECEIPT IS NOT A SILENCE
# Reading whichever receipts happen to be on disk meant deleting one deleted
# the check with it, and the final manifest went on reporting a consistent
# state while saying nothing about that writer at all.
_R = os.path.join(TMP, 'receipts')
os.makedirs(_R, exist_ok=True)
json.dump({'verdict': K.CLEAN_RERUN},
          io.open(os.path.join(_R, 'present_idempotency.json'), 'w',
                  encoding='utf-8'))
json.dump({'verdict': 'CONFLICT_NO_WRITE'},
          io.open(os.path.join(_R, 'conflicted_idempotency.json'), 'w',
                  encoding='utf-8'))
io.open(os.path.join(_R, 'broken_idempotency.json'), 'w',
        encoding='utf-8').write('not json at all')
_v = K.receipt_verdicts(_R, ('present', 'conflicted', 'broken', 'absent'))
check("a writer with no receipt is reported, not skipped",
      _v['absent'] == 'RECEIPT_MISSING', '%s' % _v)
check("a receipt that cannot be read is not a pass either",
      _v['broken'] == 'RECEIPT_UNREADABLE')
check("a declared writer always gets an entry",
      sorted(_v) == ['absent', 'broken', 'conflicted', 'present'])
check("only the clean rerun counts as proven",
      K.unclean_reruns(_v) == ['absent', 'broken', 'conflicted'])
check("and a full set of clean receipts leaves nothing outstanding",
      K.unclean_reruns(K.receipt_verdicts(_R, ('present',))) == [])

# ---- THE WRITE ITSELF, WHICH THE GUARD NEVER SEES
# `parent_effect_key` is added by this module so both sides can name a parent
# the same way. It is not a column of the CSV, and a row still carrying it
# raises ValueError inside csv.DictWriter - in the write branch, which a clean
# no-op never enters, after the first table has already been written.
import csv as _csv                                              # noqa: E402

_COLS = ['rec_id', 'quantity', 'value']
_row = {'rec_id': 'R1', 'quantity': 'n', 'value': '3',
        'parent_effect_key': "('R1', ...)", '_transient': 'x'}
check("a row is cut down to the file's own columns before it is written",
      K.writable([_row], _COLS) == [{'rec_id': 'R1', 'quantity': 'n',
                                     'value': '3'}])
check("and a column the row lacks becomes empty, not missing",
      K.writable([{'rec_id': 'R1'}], _COLS)
      == [{'rec_id': 'R1', 'quantity': '', 'value': ''}])
_probe = os.path.join(TMP, 'probe.csv')
with io.open(_probe, 'w', encoding='utf-8', newline='') as _fh:
    _w = _csv.DictWriter(_fh, fieldnames=_COLS)
    _w.writeheader()
    _w.writerows(K.writable([_row], _COLS))
check("so DictWriter accepts it, which it does not without this",
      os.path.getsize(_probe) > 0)
_raised = False
try:
    with io.open(os.path.join(TMP, 'raw.csv'), 'w', encoding='utf-8',
                 newline='') as _fh:
        _w = _csv.DictWriter(_fh, fieldnames=_COLS)
        _w.writerow(_row)
except ValueError:
    _raised = True
check("the unfiltered row really does raise, or this scenario proves nothing",
      _raised)

# ALL OR NOTHING. A failure partway through leaves one table ahead of another,
# and that in-between state is the one the guard cannot describe: neither "has
# not happened" nor "has happened".
_a = os.path.join(TMP, 'a.csv')
_b = os.path.join(TMP, 'b.csv')
for _p in (_a, _b):
    with io.open(_p, 'w', encoding='utf-8') as _fh:
        _fh.write('rec_id,quantity,value\nOLD,,\n')
K.write_all_or_nothing([(_a, _COLS, [_row]), (_b, _COLS, [_row])])
check("both files are written when both can be",
      all('OLD' not in io.open(p, encoding='utf-8').read() for p in (_a, _b)))
for _p in (_a, _b):
    with io.open(_p, 'w', encoding='utf-8') as _fh:
        _fh.write('rec_id,quantity,value\nOLD,,\n')


class _Boom(list):
    def __iter__(self):
        raise RuntimeError('failure partway through')


_failed = False
try:
    K.write_all_or_nothing([(_a, _COLS, [_row]), (_b, _COLS, _Boom())])
except RuntimeError:
    _failed = True
check("a failure on the second file raises", _failed)
check("and leaves the FIRST file as it was",
      'OLD' in io.open(_a, encoding='utf-8').read())
check("leaving no half-written file behind either",
      not [f for f in os.listdir(TMP) if f.endswith('.writing')],
      "%s" % [f for f in os.listdir(TMP) if f.endswith('.writing')])

shutil.rmtree(TMP, ignore_errors=True)
print()
print('FDT_SCENARIOS_RUN=%d' % N[0])
print('%d scenarios run' % N[0])
if FAIL:
    print('%d FAILED: %s' % (len(FAIL), FAIL))
    raise SystemExit(1)
print('all scenarios passed')
