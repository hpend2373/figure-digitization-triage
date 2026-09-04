# -*- coding: utf-8 -*-
"""판정 페이지의 가드를 하나씩 되돌리고, 어떤 시나리오가 죽는지 본다.

    python3 mutate_review.py
"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import mutate_guard                                       # noqa: E402
SUITE = ["python3", os.path.join(HERE, "test_review_sheet.py")]

MUT = [
    ("M1 에이전트 제안을 미리 눌러 둠", "review_sheet.py",
     "\"style='--c:%s'%s>%s <kbd>%s</kbd></button>\"",
     "\"style='--c:%s'%s aria-pressed='true'>%s <kbd>%s</kbd></button>\""),
    ("M2 에이전트 제안을 펼쳐 둠", "review_sheet.py",
     "<div class='agent' hidden>", "<div class='agent'>"),
    ("M3 지문에서 상자를 뺌", "review_sheet.py",
     '''    raw = "|".join([queue_row["Draft_ID"], queue_row.get("Crop_SHA256", ""),
                    queue_row.get("Proposal_Figure_BBox", ""),
                    queue_row.get("PDF_BBox", ""), queue_row.get("Raster_BBox", "")])''',
     '''    raw = "|".join([queue_row["Draft_ID"], queue_row.get("Crop_SHA256", "")])'''),
    ("M4 지문에서 크롭을 뺌", "review_sheet.py",
     'queue_row.get("Crop_SHA256", ""),\n                    queue_row.get("Proposal_Figure_BBox", ""),',
     'queue_row.get("Proposal_Figure_BBox", ""),'),
    ("M5 인테이크와 다른 공식으로 자름", "review_sheet.py",
     "    got = roundtrip.cut(Image.open(raster), dict(row, Figure_BBox=box_text))",
     "    _p = roundtrip.PAD\n    roundtrip.PAD = 0\n"
     "    got = roundtrip.cut(Image.open(raster), dict(row, Figure_BBox=box_text))\n"
     "    roundtrip.PAD = _p"),
    ("M6 페이지에 상자를 안 그림", "review_sheet.py",
     "        out.append(\n"
     "            \"<div class='pbox' data-box='%s' style='border-color:%s;\"",
     "        continue\n"
     "        out.append(\n"
     "            \"<div class='pbox' data-box='%s' style='border-color:%s;\""),
    ("M58 상자를 엉뚱한 자리에 겹침", "review_sheet.py",
     "            % (name, colour, box[0] / pw * 100, box[1] / ph * 100,",
     "            % (name, colour, 0.0, 0.0,"),
    ("M59 상자를 그림에 구워 넣음 (미리보기가 더러워짐)", "review_sheet.py",
     "    return _uri(Image.open(raster).convert(\"RGB\"), PAGE_WIDTH, 75)",
     "    from PIL import ImageDraw\n"
     "    _im = Image.open(raster).convert(\"RGB\")\n"
     "    ImageDraw.Draw(_im).rectangle([0, 0, 9, 9], outline=(255, 0, 0))\n"
     "    return _uri(_im, PAGE_WIDTH, 75)"),
    ("M7 지문 대조 제거", "review_sheet.py",
     "  else if (store[id].fp !== needed(card, store[id].choice)) { delete store[id]; dropped++; }",
     "  else if (false) { delete store[id]; dropped++; }"),
    ("M8 모르는 선택 값 허용", "review_sheet.py",
     "  if (!store[id] || VALID.indexOf(store[id].choice) < 0) { delete store[id]; dropped++; }",
     "  if (!store[id]) { delete store[id]; dropped++; }"),
    ("M9 저장소 쓰기 탐지 제거", "review_sheet.py",
     "  window.localStorage.setItem(probe, '1');", ""),
    ("M10 고르지 않은 행도 값을 내보냄", "review_sheet.py",
     "q['Human_Choice'] = kept ? kept.choice : '';",
     "q['Human_Choice'] = kept ? kept.choice : q['Agent_Choice'];"),
    ("M11 merge가 크롭 digest를 안 봄", "review_packet.py",
     '    if queue_row.get("Crop_SHA256") and queue_row["Crop_SHA256"] != crop_sha:',
     "    if False:"),
    ("M12 merge가 고른 상자를 안 봄", "review_packet.py",
     "    if was != now:", "    if False:"),
    ("M13 고르지 않은 상자까지 대조", "review_packet.py",
     "    column = CHOICE_BOX.get(choice)",
     "    for _c in CHOICE_BOX.values():\n"
     "        if queue_row.get(_c, '') != (region_row or {}).get(_c, ''):\n"
     "            return '어느 상자든 바뀜'\n"
     "    column = CHOICE_BOX.get(choice)"),
    ("M14 BLOCKED도 상자를 지목한 것으로", "review_packet.py",
     "    if column is None:                     # BLOCKED names no box\n        return \"\"",
     "    if column is None:\n        column = 'PDF_BBox'"),
    ("M15 merge가 stale을 안 부름", "review_packet.py",
     '        why = "" if already_applied(q, draft.get(q["Draft_ID"])) else stale(q, reg, now)',
     '        why = ""'),
    ("M16 거부를 적어 두지 않음", "review_packet.py",
     '            reg[STALE_CHOICE] = (q.get("Human_Choice") or "").strip().upper()',
     "            pass"),
    ("M17 거부된 행을 큐에 다시 넣지 않음", "review_packet.py",
     '        pending = bool((reg.get(STALE_CHOICE) or "").strip())',
     "        pending = False"),
    ("M18 다시 답해도 거부 표시가 남음", "review_packet.py",
     "                reg[STALE_CHOICE] = reg[STALE_REASON] = \"\"", "                pass"),
    ("M20 이미 적용된 선택도 거부", "review_packet.py",
     '        why = "" if already_applied(q, draft.get(q["Draft_ID"])) else stale(q, reg, now)',
     "        why = stale(q, reg, now)"),
    ("M21 상자와 무관하게 적용된 것으로 봄", "review_packet.py",
     '    return bool(box) and box == (draft_row.get("Figure_BBox") or "").strip()',
     "    return True"),
    ("M19 판정 페이지가 거부를 안 알림", "review_sheet.py",
     "        ) if (q.get(\"Stale_Choice\") or \"\").strip() else \"\"",
     "        ) if False else \"\""),

    # ------------------------------------------------ 사람이 직접 그리는 상자
    ("M22 그린 답도 제안자 지문에 묶음", "review_sheet.py",
     "  if (choice !== 'DRAWN') return card.dataset.fp;",
     "  return card.dataset.fp;"),
    ("M23 상자 없이도 DRAWN 허용", "review_sheet.py",
     "  if (choice === 'DRAWN' && !boxes[id]) {", "  if (false) {"),
    ("M24 상자 없어도 그리기 버튼 열어 둠", "review_sheet.py",
     "               \" disabled\" if name == \"DRAWN\" else \"\", esc(label), key)",
     "               \"\", esc(label), key)"),
    ("M25 고르지 않아도 그린 상자를 내보냄", "review_sheet.py",
     "    q['Human_Box'] = (kept && kept.choice === 'DRAWN' && boxes[r.Draft_ID])\n"
     "                     ? boxes[r.Draft_ID].box : '';",
     "    q['Human_Box'] = boxes[r.Draft_ID] ? boxes[r.Draft_ID].box : '';"),
    ("M42 다시 그리면 판정이 풀림", "review_sheet.py",
     "  choose(card, 'DRAWN', false);", "  choose(card, 'DRAWN');"),
    ("M43 버튼을 두 번 눌러도 안 풀림", "review_sheet.py",
     "  if (again !== false && store[id] && store[id].choice === choice) delete store[id];",
     "  if (false) delete store[id];"),
    ("M26 클릭도 상자로 침", "review_sheet.py",
     "  if (!moved) { overlay(card); return; }   // a click is not a box", ""),
    ("M27 상자를 화면 픽셀로 저장", "review_sheet.py",
     "    box: [f[0] * pw, f[1] * ph, f[2] * pw, f[3] * ph]",
     "    box: [f[0], f[1], f[2], f[3]]"),
    ("M28 페이지가 바뀌어도 지문이 같음", "review_sheet.py",
     '    raw = "|".join([raster, str(size), str(row.get("Page_Width_Pt", "")),\n'
     '                    str(row.get("Page_Height_Pt", ""))])',
     '    raw = "고정"'),
    ("M29 브라우저가 준 상자를 검사 없이 씀", "apply_validated.py",
     "    parts = str(text or \"\").split(\",\")\n"
     "    if len(parts) != 4:",
     "    parts = str(text or \"\").split(\",\")\n"
     "    if False:"),
    ("M30 너무 작은 상자도 받음", "apply_validated.py",
     "    if x1 - x0 < MIN_DRAWN_PT or y1 - y0 < MIN_DRAWN_PT:", "    if False:"),
    ("M31 페이지 밖 상자도 받음", "apply_validated.py",
     "    if x1 <= 0 or y1 <= 0 or x0 >= pw or y0 >= ph:", "    if False:"),
    ("M32 거꾸로 끈 상자를 바로 세우지 않음", "apply_validated.py",
     "    x0, x1 = min(x0, x1), max(x0, x1)\n    y0, y1 = min(y0, y1), max(y0, y1)", ""),
    ("M33 그린 상자를 쓰지 않고 제안자 상자를 씀", "apply_validated.py",
     "                target_box, why = drawn_box(reg.get(\"Human_Box\"), moved or d)\n"
     "                if why:\n"
     "                    skipped.append((d[\"Draft_ID\"], why))\n"
     "                    continue",
     "                target_box, why = reg.get(\"Human_Box\"), \"\""),
    ("M34 DRAWN을 아는 선택으로 치지 않음", "apply_validated.py",
     "HUMAN_CHOICES = (\"\", \"RASTER\", \"PDF\", \"TEXT\", \"DRAWN\", \"BLOCKED\")",
     "HUMAN_CHOICES = (\"\", \"RASTER\", \"PDF\", \"TEXT\", \"BLOCKED\")"),

    # --------------------------------- 다시 자른 크롭을 다시 재는가
    ("M44 다시 재지 않고 옛 등급을 남김", "apply_validated.py",
     '            d["Crop_Quality_Status"] = got[2]', "            pass"),
    ("M45 무조건 ACCEPTABLE로 적음", "apply_validated.py",
     '            d["Crop_Quality_Status"] = got[2]',
     '            d["Crop_Quality_Status"] = "ACCEPTABLE"'),
    ("M46 페이지 대비가 아니라 늘 통과", "roundtrip.py",
     "    if trimmed.height < THIN_FRACTION * page.height:", "    if False:"),
    ("M47 옆면 잉크를 안 봄", "roundtrip.py",
     "    return \"EDGE_CLIPPED\" if clipped else \"ACCEPTABLE\"",
     "    return \"ACCEPTABLE\""),
    ("M48 여백을 턴 뒤에 옆면을 봄 (답이 남지 않음)", "roundtrip.py",
     "    ink = np.asarray(image.convert(\"L\"), dtype=np.uint8) < INK\n"
     "    clipped = bool(",
     "    image = _trim_for_mutant(image)\n"
     "    ink = np.asarray(image.convert(\"L\"), dtype=np.uint8) < INK\n"
     "    clipped = bool("),
    ("M49 빈 상자도 그림으로 침", "roundtrip.py",
     "    if not ink.any():\n", "    if False:\n"),
    ("M50 cut_and_grade가 cut과 다르게 자름", "roundtrip.py",
     "    got = cut(page, row)\n    if got is None:\n        return None\n"
     "    image, pixel_box = got",
     "    got = cut(page, row)\n    if got is None:\n        return None\n"
     "    image, pixel_box = untrimmed, (left, top, right, bottom)"),

    # ------------------------------------------- 막힌 행 큐
    ("M51 사유 표가 없어도 목록을 지어냄", "review_packet.py",
     "    if not os.path.exists(path):\n        raise SystemExit(",
     "    if False:\n        raise SystemExit("),
    ("M52 막히지 않은 행까지 큐에 넣음", "review_packet.py",
     '        if say["Count_Blocked"] != "1":\n            continue', "        pass"),
    ("M53 사유를 들고 오지 않음", "review_packet.py",
     '            "Block_Reason": say.get("Reason", ""),', '            "Block_Reason": "",'),
    ("M54 상자로 풀리는지 안 알려 줌", "review_packet.py",
     '            "Box_Would_Open": say.get("Box_Would_Open", ""),',
     '            "Box_Would_Open": "1",'),
    ("M55 사유 표가 오래돼도 그냥 진행", "review_packet.py",
     "    if missing:\n        raise SystemExit(\"막힌 사유 표에 없는 초안 행",
     "    if False:\n        raise SystemExit(\"막힌 사유 표에 없는 초안 행"),
    ("M56 판정 페이지가 막힌 이유를 안 보여 줌", "review_sheet.py",
     '        block_block = ("<div class=\'why %s\'><b>막힌 이유</b> %s%s</div>"',
     '        block_block = ("" or "<div class=\'why %s\'>%s%s</div>"'),
    ("M57 상자로 못 푸는 행에도 아무 말 안 함", "review_sheet.py",
     '                          ("" if helps or needs_number else\n'
     '                           " <b>\u2014 \uc0c1\uc790\ub97c \uadf8\ub824\ub3c4 \uc774 \uc774\uc720\ub294 \ud480\ub9ac\uc9c0 \uc54a\uc2b5\ub2c8\ub2e4.</b>")',
     '                          ("" if True else\n'
     '                           " <b>\u2014 \uc0c1\uc790\ub97c \uadf8\ub824\ub3c4 \uc774 \uc774\uc720\ub294 \ud480\ub9ac\uc9c0 \uc54a\uc2b5\ub2c8\ub2e4.</b>")'),
    ("M110 \ubc88\ud638\uac00 \ud544\uc694\ud55c \ud589\uc5d0 \uadf8 \uce78\uc744 \uc548 \ub123\uc74c", "review_sheet.py",
     ') if needs_number else ""', ') if False else ""'),
    ("M111 \ubaa8\ub4e0 \ud589\uc5d0 \ubc88\ud638 \uce78\uc744 \ub123\uc74c", "review_sheet.py",
     ') if needs_number else ""', ') if why else ""'),
    ("M112 \ubc88\ud638 \uce78\uc774 CSV\uc5d0 \ub2ff\uc9c0 \uc54a\uc74c", "review_sheet.py",
     "    q['Human_Figure_Number'] = numbers[r.Draft_ID] || '';",
     "    q['Human_Figure_Number'] = '';"),
    ("M113 \uc801\uc740 \ubc88\ud638\ub97c \uc800\uc7a5\ud558\uc9c0 \uc54a\uc74c", "review_sheet.py",
     "    if (v) numbers[id] = v; else delete numbers[id];",
     "    if (false) numbers[id] = v; else delete numbers[id];"),


    # ----------------------------------------- 옆 쪽으로 옮겨 자르기
    ("M60 창 밖으로도 옮김", "apply_validated.py",
     "    if abs(there - here) > MOVE_REACH:", "    if False:"),
    ("M77 보여 주는 범위와 옮길 수 있는 거리가 어긋남", "apply_validated.py",
     "MOVE_REACH = _rp.PAGE_WINDOW", "MOVE_REACH = 1"),
    ("M78 큐가 창 밖의 쪽까지 실음", "review_packet.py",
     "    for other in range(page - reach, page + reach + 1):\n"
     "        if other < 1 or other == page:",
     "    for other in range(page - reach * 4, page + reach * 4 + 1):\n"
     "        if other < 1 or other == page:"),
    ("M81 사람이 막은 행에는 창을 안 줌", "review_packet.py",
     "                     or reg.get(\"Agreement\") == \"HUMAN_BLOCKED\")) else \"\",",
     "                     )) else \"\","),
    ("M82 상자가 있어도 창을 줌", "review_packet.py",
     "                and (not ((reg.get(\"PDF_BBox\") or \"\").strip()\n"
     "                          or (reg.get(\"Raster_BBox\") or \"\").strip())\n"
     "                     or reg.get(\"Agreement\") == \"HUMAN_BLOCKED\")) else \"\",",
     "                ) else \"\","),
    ("M79 큐가 캡션 쪽 자신도 실음", "review_packet.py",
     "        if other < 1 or other == page:", "        if other < 1:"),
    ("M80 쪽 넘김 띠를 안 보임", "review_sheet.py",
     "            seen = sorted([p for p, _u, _pw, _ph, _fp in others] + [this_page])",
     "            seen = []"),
    ("M61 PDF 크기와 안 맞아도 옮김", "apply_validated.py",
     "    if abs(said[0] - npw) > PAGE_SIZE_TOL_PT or abs(said[1] - nph) > PAGE_SIZE_TOL_PT:",
     "    if False:"),
    ("M62 PDF 크기를 확인 못 해도 옮김", "apply_validated.py",
     "    if said is None:\n        return None,",
     "    if said is None:\n        said = (npw, nph)\n    if False:\n        return None,"),
    ("M63 같은 그림 행이 있는 쪽으로도 옮김", "apply_validated.py",
     "    if twin:\n        return None, (\"p.%d에는 같은 그림", "    if False:\n        return None, (\"p.%d에는 같은 그림"),
    ("M64 옮겨도 캡션 쪽을 안 적음", "apply_validated.py",
     '    moved["Caption_Page"] = moved.get("Caption_Page") or str(here)',
     '    moved["Caption_Page"] = ""'),
    ("M65 옮겨도 래스터를 안 바꿈 (캡션 쪽에서 자름)", "apply_validated.py",
     '    moved["Page_Raster"] = target', '    moved["Page_Raster"] = raster'),
    ("M66 쪽 크기를 PDF가 아니라 캡션 쪽 것으로", "apply_validated.py",
     '    moved["Page_Width_Pt"] = "%.2f" % said[0]\n    moved["Page_Height_Pt"] = "%.2f" % said[1]',
     '    moved["Page_Width_Pt"] = "%.2f" % pw\n    moved["Page_Height_Pt"] = "%.2f" % ph'),
    ("M67 옮긴 행의 필드를 초안에 안 씀", "apply_validated.py",
     '                for col in ("Caption_Page", "Page", "Page_Raster",\n'
     '                            "Page_Width_Pt", "Page_Height_Pt"):\n'
     '                    d[col] = moved[col]',
     '                pass'),
    ("M68 쪽 번호를 읽지 못해도 진행", "apply_validated.py",
     '        return None, "그린 쪽 번호를 읽을 수 없음 (%r)" % (human_page,)',
     '        return dict(d), ""'),
    ("M69 큐가 옆 쪽 크기를 이 쪽 것으로 복사", "review_packet.py",
     '        out.append("%d:%.1fx%.1f" % (other, o.width / scale, o.height / scale))',
     '        out.append("%d:%.1fx%.1f" % (other, pw, ph))'),
    ("M70 큐가 옆 쪽을 안 실음", "review_packet.py",
     "        path = roundtrip.sibling_raster(raster, other)\n        if not path:\n            continue",
     "        continue"),
    ("M71 채워진 쪽 이름을 못 읽음", "roundtrip.py",
     '            out[int(name[len("page-"):-len(".png")])] = os.path.join(raster_dir, name)',
     '            _n = name[len("page-"):-len(".png")]\n'
     '            if _n != str(int(_n)):\n                continue\n'
     '            out[int(_n)] = os.path.join(raster_dir, name)'),
    ("M72 그린 쪽을 상자와 함께 저장하지 않음", "review_sheet.py",
     "  boxes[card.dataset.id] = { pfp: card.dataset.pfp, page: shownPage(card),",
     "  boxes[card.dataset.id] = { pfp: card.dataset.pfp,"),
    ("M73 옆 쪽에 그려도 쪽 번호 없이 내보냄", "review_sheet.py",
     "    q['Human_Page'] = (drawnOn !== null && capPage !== null\n"
     "                       && String(drawnOn) !== String(capPage)) ? String(drawnOn) : '';",
     "    q['Human_Page'] = '';"),
    ("M93 넘겨 보는 쪽도 캡션 쪽만큼 크게 실음", "review_sheet.py",
     "        out.append((page, _uri(Image.open(path).convert(\"RGB\"), WINDOW_WIDTH, 72),",
     "        out.append((page, _uri(Image.open(path).convert(\"RGB\"), PAGE_WIDTH, 75),"),
    ("M76 숨긴 쪽 그림이 그대로 보임", "review_sheet.py",
     "img.page[hidden]{display:none}", ""),
    ("M74 옆 쪽에서도 제안 상자를 그대로 보임", "review_sheet.py",
     "  card.querySelectorAll('.pbox').forEach(b => { b.hidden = !info.caption; });", ""),
    ("M75 옮긴 행의 캡션 상자를 새 쪽 제안자에게 넘김", "validate_regions.py",
     "                if cap_page and cap_page != str(r.get(\"Page\") or \"\").strip():",
     "                if False:"),

    # ------------------------------- 이미 답한 질문을 다시 묻지 않는가
    ("M83 답한 질문을 또 물음", "review_packet.py",
     "        if was and was == now:\n            continue", "        if False:\n            continue"),
    ("M84 답할 때 무엇을 물었는지 안 적음", "review_packet.py",
     "            key = question_key(q)\n"
     "            if reg.get(ANSWERED_KEY, \"\") != key:\n"
     "                reg[ANSWERED_KEY] = key\n"
     "                changed = True",
     "            pass"),
    ("M85 질문이 달라져도 안 물음", "review_packet.py",
     "        if was and was == now:", "        if was:"),
    ("M86 열쇠가 막힌 이유를 안 봄", "review_packet.py",
     '    raw = "|".join([reason] + [str(fields.get(k) or "").strip() for k in (',
     '    raw = "|".join([""] + [str(fields.get(k) or "").strip() for k in ('),
    ("M87 열쇠가 문서 창을 안 봄", "review_packet.py",
     '    raw += "|" + ("W" if str(fields.get(NEIGHBOURS) or "").strip() else "-")', "    pass"),
    ("M88 열쇠가 창의 내용까지 봄 (넓어지면 또 물음)", "review_packet.py",
     '    raw += "|" + ("W" if str(fields.get(NEIGHBOURS) or "").strip() else "-")',
     '    raw += "|" + str(fields.get(NEIGHBOURS) or "")'),
    ("M89 열쇠가 답까지 봄", "review_packet.py",
     '        "Crop_SHA256", "Proposal_Figure_BBox", "PDF_BBox", "Raster_BBox")])',
     '        "Crop_SHA256", "Proposal_Figure_BBox", "PDF_BBox", "Raster_BBox",\n'
     '        "Human_Choice", "Human_Box")])'),
    ("M91 머리말까지 질문으로 셈 (영영 돌아옴)", "review_packet.py",
     "    while reason.startswith(ASK_AGAIN):\n        reason = reason[len(ASK_AGAIN):]",
     "    pass"),
    ("M92 머리말을 한 번만 벗김", "review_packet.py",
     "    while reason.startswith(ASK_AGAIN):", "    if False and reason.startswith(ASK_AGAIN):"),
    ("M90 돌아온 행에 이유를 안 적음", "review_packet.py",
     '            r["Block_Reason"] = ASK_AGAIN + r["Block_Reason"]', "            pass"),

    # ------------------------------------------------------- 막은 것 되돌리기
    ("M35 막을 때 이전 상태를 안 적음", "apply_validated.py",
     "                    reg[\"Blocked_From\"] = reg.get(\"Agreement\") or \"\"", "                    pass"),
    ("M36 답을 비워도 큐에 안 돌아옴", "review_packet.py",
     "        if (not pending and reg.get(\"Agreement\") == \"HUMAN_BLOCKED\"\n"
     "                and (reg.get(\"Human_Choice\") or \"\").strip().upper() == \"BLOCKED\"):",
     "        if not pending and reg.get(\"Agreement\") == \"HUMAN_BLOCKED\":"),
    ("M37 되돌리기가 셀 수 있는 상태도 되살림", "review_packet.py",
     "        if was in COUNTABLE:", "        if False:"),
    ("M38 되돌리기가 막히지 않은 행도 건드림", "review_packet.py",
     "        if reg.get(\"Agreement\") != \"HUMAN_BLOCKED\":", "        if False:"),
    ("M39 되돌려도 답이 남음", "review_packet.py",
     "        reg[\"Human_Choice\"] = \"\"", "        pass"),
    ("M40 그린 답을 크롭 digest로 거부", "review_packet.py",
     "    if choice == \"DRAWN\":\n"
     "        if not (queue_row.get(HUMAN_BOX) or \"\").strip():",
     "    if False:\n"
     "        if not (queue_row.get(HUMAN_BOX) or \"\").strip():"),
    ("M41 큐가 그린 상자를 들고 오지 않음", "review_packet.py",
     "            HUMAN_BOX: reg.get(HUMAN_BOX, \"\"),", ""),
    # ---------------------- 사람의 상자가 이미 세는 그림에 내려앉으면: 적고, 묻지 않는다
    ("M94 옮기기 거부를 적어 두지 않음", "apply_validated.py",
     "                            reg[DUPLICATE_OF] = got_move[2]\n"
     "                            reg[DUPLICATE_PAGE] = human_page\n",
     ""),
    ("M95 새 답이 와도 옛 중복 기록이 남음", "apply_validated.py",
     "            if reg.get(DUPLICATE_OF) or reg.get(DUPLICATE_PAGE):\n"
     "                reg[DUPLICATE_OF] = reg[DUPLICATE_PAGE] = \"\"\n",
     ""),
    ("M96 moved_page가 어느 행이 세는지 말하지 않음", "apply_validated.py",
     "                      % (there, d[\"Figure_Number\"], twin)), twin",
     "                      % (there, d[\"Figure_Number\"], twin))"),
    ("M97 큐가 중복 행을 도로 물음", "review_packet.py",
     "        if (say.get(\"Duplicate_Of\") or \"\").strip():\n"
     "            settled += 1\n            continue\n",
     ""),
    ("M98 병합이 옛 중복 기록을 지우지 않음", "review_packet.py",
     "            if reg.get(DUPLICATE_OF) or reg.get(DUPLICATE_PAGE):\n"
     "                reg[DUPLICATE_OF] = reg[DUPLICATE_PAGE] = \"\"\n"
     "                changed = True\n",
     ""),
    # ------------------------------------- 번호 칸: 큐 → 병합 → 적용, 그리고 열쇠
    ("M99 큐가 번호 칸을 들고 나가지 않음", "review_packet.py",
     '            "Number_Would_Open": say.get("Number_Would_Open", ""),\n',
     '            "Number_Would_Open": "",\n'),
    ("M100 병합이 적어 낸 번호를 버림", "review_packet.py",
     '                    "Agent_Choice", "Agent_Note", HUMAN_NUMBER):',
     '                    "Agent_Choice", "Agent_Note"):'),
    ("M101 번호만 적은 것은 답으로 안 침", "review_packet.py",
     '    return readable_number((q.get(HUMAN_NUMBER) or "").strip())',
     '    return False'),
    ("M120 거부 사유를 큐에 안 실음", "review_packet.py",
     '"Number_Refused": number_refused(reg.get(HUMAN_NUMBER, "")),',
     '"Number_Refused": "",'),
    ("M121 카드가 거부 사유를 안 실음", "review_sheet.py",
     "number_block = ((number_block + \"<div class='numbad'>%s</div>\"",
     "number_block = ((number_block + \"\" + \"\" * len(\"%s\")"),
    ("M119 읽을 수 없는 번호를 답으로 침", "review_packet.py",
     '    return readable_number((q.get(HUMAN_NUMBER) or "").strip())',
     '    return bool((q.get(HUMAN_NUMBER) or "").strip())'),
    ("M102 번호 칸이 생겨도 같은 질문으로 침", "review_packet.py",
     'if str(fields.get("Number_Would_Open") or "").strip() == "1":\n        raw += "|N"',
     'if False:\n        raw += "|N"'),
    ("M103 번호가 없는 행의 열쇠까지 바꿈", "review_packet.py",
     'if str(fields.get("Number_Would_Open") or "").strip() == "1":\n        raw += "|N"',
     'if True:\n        raw += "|N" if str(fields.get("Number_Would_Open") or "").strip() == "1" else "|-"'),
    ("M104 번호가 필요한 행을 뒤로 보냄", "review_packet.py",
     'out.sort(key=lambda r: (r["Box_Would_Open"] != "1"\n'
     '                            and r["Number_Would_Open"] != "1",',
     'out.sort(key=lambda r: (r["Box_Would_Open"] != "1",'),
    ("M105 적용이 번호를 초안에 안 씀", "apply_validated.py",
     '            d["Figure_Number"] = want\n            d["Number_Source"] = "HUMAN"\n',
     ''),
    ("M106 사람이 적었다는 표시를 안 남김", "apply_validated.py",
     '            d["Number_Source"] = "HUMAN"\n', ''),
    ("M107 읽을 수 없는 번호를 조용히 빈 값으로", "apply_validated.py",
     '    if not m:\n        return "", ("그림 번호',
     '    if not m:\n        return "", ("" and ("그림 번호'),
    ("M108 아무 글자나 번호로 받음", "apply_validated.py",
     'NUMBER_SPELLING = re.compile(', 'NUMBER_SPELLING = re.compile("^(?P<ext>x)?(?P<n>.*?)(?P<sub>x)?$") or re.compile('),
    ("M109 번호를 받은 행도 다시 잘렸다고 침", "apply_validated.py",
     'if "BLOCKED" not in x and "중복" not in x and "(번호 " not in x}',
     'if "BLOCKED" not in x and "중복" not in x}'),
    ("M110 왜 다시 묻는지 말하지 않음", "review_packet.py",
     '            r["Ask_Again_Why"] = ask_again_why(\n'
     '                r, reg.get(ANSWERED_WINDOW, ""), reg.get(ANSWERED_REASON, ""))',
     '            r["Ask_Again_Why"] = ""'),
    ("M111 창이 생긴 것을 말하지 않음", "review_packet.py",
     '    if was_window == "-" and window_flag(fields) == "W":',
     '    if False:'),
    ("M112 이유보다 창을 먼저 말함", "review_packet.py",
     '    if was_reason and was_reason != reason_key(fields):',
     '    if (was_reason and was_reason != reason_key(fields)\n'
     '            and window_flag(fields) == "-"):'),
    ("M113 기록이 없어도 아는 척함", "review_packet.py",
     '    if not was_window and not was_reason:\n'
     '        return ASK_AGAIN_WHY["UNKNOWN"]\n', ''),
    ("M114 답할 때의 창 여부를 안 남김", "review_packet.py",
     '(ANSWERED_WINDOW, window_flag(q)),', '(ANSWERED_WINDOW, ""),'),
    ("M115 답할 때의 이유를 안 남김", "review_packet.py",
     '(ANSWERED_REASON, reason_key(q))', '(ANSWERED_REASON, "")'),
    ("M116 창 표시에 쪽 목록을 그대로 씀", "review_packet.py",
     '    return "W" if str(fields.get(NEIGHBOURS) or "").strip() else "-"',
     '    return str(fields.get(NEIGHBOURS) or "").strip() or "-"'),
    ("M117 이유 열쇠가 머리말을 안 벗김", "review_packet.py",
     '        _reason_of(fields).encode("utf-8")).hexdigest()[:16]',
     '        str(fields.get("Block_Reason") or "").strip()'
     '.encode("utf-8")).hexdigest()[:16]'),
    ("M118 카드가 그 문장을 안 실음", "review_sheet.py",
     "again_block = (\"<div class='again'><b>다시 묻는 이유</b> %s</div>\"",
     "again_block = \"\" and (\"<div class='again'><b>다시 묻는 이유</b> %s</div>\""),
]


def run():
    r = subprocess.run(SUITE, capture_output=True, text=True, cwd=HERE)
    fails = [l.split("FAIL", 1)[1].strip() for l in r.stdout.splitlines()
             if l.strip().startswith("FAIL")]
    return r.returncode, fails


mutate_guard.restore_any(HERE)

bad = 0
for name, filename, old, new in mutate_guard.slice_of(MUT):
    path = os.path.join(HERE, filename)
    base = open(path, encoding="utf-8").read()
    if old not in base:
        print("PATCH_FAILED %s" % name)
        bad += 1
        continue
    with mutate_guard.mutation(path, base.replace(old, new, 1)):
        code, fails = run()
    killed = code != 0
    print("%-9s %-30s %s" % ("KILLED" if killed else "SURVIVED", name,
                             ("| " + "; ".join(f[:56] for f in fails[:2])) if killed
                             else "<-- 이 가드를 지키는 시나리오가 없다"))
    if not killed:
        bad += 1

code, _ = run()
print("\n복원 후: %s" % ("통과" if code == 0 else "실패 - 복원되지 않았습니다"))
sys.exit(1 if bad or code else 0)
