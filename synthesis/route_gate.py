# -*- coding: utf-8 -*-
"""Does a row of extracted evidence agree with the route its record was given?

THE DEFECT THIS EXISTS FOR WAS REAL AND SHIPPED. Three effect rows for a
Mendelian randomization record were written with
`synthesis_readiness=QUANTITATIVE_CANDIDATE` - the value for a record that CAN
enter the standard drug-exposure pool - while screening, the operational status
table and the source-corpus receipt all said `MR_SEPARATE`. Every QC check
passed, because every check looked at one artifact at a time. The row was never
poolable in fact, since pooling permission is a separate human field, but the
long table disagreed with every other artifact about what KIND of evidence it
held, and nothing said so.

So this compares artifacts rather than fields. Screening decides the route;
each effect row of that record has to carry the same route.

READS NO FILES. The caller supplies rows as plain dictionaries, which is what
lets the scenarios beside it put the defect back and require it to be caught.
A gate with no scenario that can fail is decoration.
"""

#: The screening columns that fix a record's route, and the effect-row columns
#: that must repeat it.
PAIRS = (('synthesis_readiness', 'synthesis_readiness', 'effect_readiness_mismatch'),
         ('audit_v2_stream', 'analysis_stream', 'effect_stream_mismatch'))


#: Screening itself disagrees about this record's route, so no route of its is
#: authoritative and none of its rows can be judged against one.
AMBIGUOUS = "screening_route_ambiguous"


def route_index(screening_rows, id_field='rec_id'):
    """{rec_id: route} for the records screening ruled on, once.

    A RECORD RULED ON TWICE, DIFFERENTLY, HAS NO RULING. This built a plain
    dictionary, so a second row for the same record simply overwrote the first
    and the LAST line of the file decided what every effect row of that record
    had to say. Reorder the file and the requirement changes - which is the
    same file-order authority this gate exists to catch one table over.

    Rows that agree collapse; rows that disagree mark the record ambiguous, and
    `findings` then reports that rather than measuring anything against a route
    that screening does not actually assert.
    """
    out = {}
    for s in screening_rows:
        rid = str(s.get(id_field) or '')
        if not rid:
            continue
        route = {c: str(s.get(c) or '') for c, _e, _code in PAIRS}
        seen = out.get(rid)
        if seen is None:
            out[rid] = dict(route, _status='OK')
        elif any(seen.get(c) != route[c] for c in route):
            out[rid] = dict(seen, _status=AMBIGUOUS,
                            _other={c: route[c] for c in route})
    return out


def findings(effect_rows, routes, id_field='rec_id'):
    """[(effect_row_id, code, detail)] - one per disagreement.

    Silent in two cases that are NOT disagreements, and both matter:

      a record screening has not ruled on. Inventing a verdict for a record
      with no route would make the gate louder than the evidence.

      an empty cell on either side. A blank is missing information; treating
      it as a contradiction would flood the report with rows that simply have
      not been filled in yet, and a gate nobody can read is a gate nobody acts
      on.
    """
    out = []
    for r in effect_rows:
        want = routes.get(str(r.get(id_field) or ''))
        if not want:
            continue
        if want.get('_status') == AMBIGUOUS:
            out.append((r.get('effect_row_id'), AMBIGUOUS,
                        'Screening rules on %s twice with different routes; '
                        'neither is authoritative.' % r.get(id_field)))
            continue
        for scol, ecol, code in PAIRS:
            a, b = str(want.get(scol) or ''), str(r.get(ecol) or '')
            if a and b and a != b:
                out.append((r.get('effect_row_id'), code,
                            'Row says %s=%s; screening says %s for %s.'
                            % (ecol, b, a, r.get(id_field))))
    return out
