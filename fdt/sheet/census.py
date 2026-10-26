# -*- coding: utf-8 -*-
"""What a full visual pass over the sheet's countable rows found, row by row.

WHY THIS FILE EXISTS. `ACCEPTABLE` means the intake's own measurements found
nothing wrong with the crop. It does not mean the crop shows the figure: the
box is `corpus_intake.figure_bbox`, whose docstring says outright that it is
"a LOOK HERE for a contact sheet, not a crop anybody measures from" - the gap
above a caption, found from TEXT blocks, never consulting the drawings and
images the PDF carries. A pass over all 461 ACCEPTABLE rows of run2 found 336
of them showing no figure at all (body text, references, a table) or showing
one that is cut off. Nothing in the harness could see that, because every
check it had was a measurement of the crop rather than a look at what is in
it.

WHAT A ROW OF THE CENSUS IS. An observation bound to particular pixels:

    Crop_SHA256        the crop the observation was made on
    Agent_Visual_Code  what was seen, from the closed vocabulary below
    Human_Verdict      what a PERSON decided, which overrides the code

BOUND TO PIXELS ON PURPOSE. Draft_ID is a position in one walk's output and
`(document, label, page)` survives a rebuild, but neither says whether the
picture still looks the way it looked when somebody judged it. The crop's
digest does. So a verdict applies to a crop, and a crop that has been recut is
a crop nobody has looked at - which is `REVIEW_REQUIRED` here, not a silent
return to countable.

THE AGENT DOES NOT APPROVE. `Agent_Visual_Code` can only take a row OUT of
counting, never put one back: an agent observation is a reason to stop, and
`Human_Verdict` is the only thing in this file that can clear one.
"""
import csv
import io
import os


#: The vocabulary a code is built from, joined with "+" when more than one
#: applies ("CUT_B+TEXT_IN"). A CLOSED set: a code with an atom outside it is
#: refused at load rather than read as "nothing to report", because a typo
#: that silently means "countable" is how a safety rule gets deleted by
#: accident.
ATOMS = {
    "OK": "그림이 온전합니다",
    "TEXT_IN": "그림은 온전하고 본문이 함께 들어왔습니다",
    "NO_FIGURE": "상자 안에 그림이 없습니다 (본문·참고문헌·빈 영역)",
    "NO_PAGE": "페이지 기하를 잡을 수 없어 확인이 불가능합니다",
    "TABLE_IN": "그림이 아니라 표입니다",
    "MERGED": "두 그림이 한 상자에 들어왔습니다",
    "CUT_T": "그림 위쪽이 상자 밖으로 이어집니다",
    "CUT_B": "그림 아래쪽이 상자 밖으로 이어집니다",
    "CUT_L": "그림 왼쪽이 상자 밖으로 이어집니다",
    "CUT_R": "그림 오른쪽이 상자 밖으로 이어집니다",
}

#: The atoms that leave a row countable. Every other atom blocks, and a code
#: is countable only if ALL of its atoms are here - "CUT_B+TEXT_IN" is a cut
#: figure that also swallowed a paragraph, not a compromise between the two.
COUNTABLE_ATOMS = ("OK", "TEXT_IN")

#: What a person may write in `Human_Verdict`. Anything else is refused at
#: load: a verdict nobody can read is not a verdict, and guessing at it would
#: mean guessing at whether somebody may type a panel count.
HUMAN_BLANK, HUMAN_COUNTABLE, HUMAN_BLOCKED = "", "COUNTABLE", "BLOCKED"
HUMAN_VALUES = (HUMAN_BLANK, HUMAN_COUNTABLE, HUMAN_BLOCKED)

REQUIRED = ("Draft_ID", "Source_Document_ID", "Page", "Figure_Number",
            "Crop_SHA256", "Agent_Visual_Code", "Agent_Visual_Note",
            "Human_Verdict")


class CensusError(Exception):
    """The census cannot be read, so nothing may be counted from it."""


def countable_code(code):
    """True when every atom of `code` leaves the row countable."""
    atoms = [a for a in str(code).split("+") if a]
    return bool(atoms) and all(a in COUNTABLE_ATOMS for a in atoms)


def figure_id(doc, label, page):
    return (str(doc).strip(), str(label).strip().upper(), str(page).strip())


class Census(object):
    def __init__(self, entries):
        self.entries = entries
        self.by_sha = {}
        self.by_figure = {}
        for e in entries:
            self.by_sha[e["Crop_SHA256"]] = e
            key = figure_id(e["Source_Document_ID"], e["Figure_Number"],
                            e["Page"])
            self.by_figure.setdefault(key, []).append(e)

    def __len__(self):
        return len(self.entries)


def parse(rows, fieldnames):
    """Validate and index census rows. Raises `CensusError` on anything odd."""
    missing = [c for c in REQUIRED if c not in (fieldnames or ())]
    if missing:
        raise CensusError("census에 없는 칸: %s" % ", ".join(missing))
    seen = {}
    entries = []
    for i, r in enumerate(rows, 2):
        code = str(r.get("Agent_Visual_Code") or "").strip()
        if not code:
            raise CensusError("%d행 %s: Agent_Visual_Code가 비어 있습니다"
                              % (i, r.get("Draft_ID")))
        for atom in code.split("+"):
            if atom not in ATOMS:
                raise CensusError(
                    "%d행 %s: 모르는 판정 코드 %r — 아는 것은 %s 뿐입니다"
                    % (i, r.get("Draft_ID"), atom, ", ".join(sorted(ATOMS))))
        human = str(r.get("Human_Verdict") or "").strip()
        if human not in HUMAN_VALUES:
            raise CensusError(
                "%d행 %s: Human_Verdict가 %r입니다 — 쓸 수 있는 값은 %s 뿐입니다"
                % (i, r.get("Draft_ID"), human,
                   ", ".join(v or "(빈칸)" for v in HUMAN_VALUES)))
        sha = str(r.get("Crop_SHA256") or "").strip().lower()
        if len(sha) != 64:
            raise CensusError(
                "%d행 %s: Crop_SHA256이 64자가 아닙니다 (%r) — 판정은 특정 "
                "픽셀에 묶여야 합니다" % (i, r.get("Draft_ID"), sha))
        prior = seen.get(sha)
        if prior and (prior["Agent_Visual_Code"] != code
                      or prior["Human_Verdict"] != human):
            raise CensusError(
                "같은 크롭(%s…)에 서로 다른 판정이 있습니다: %s와 %s"
                % (sha[:12], prior["Draft_ID"], r.get("Draft_ID")))
        entry = dict(r)
        entry["Crop_SHA256"], entry["Agent_Visual_Code"] = sha, code
        entry["Human_Verdict"] = human
        seen[sha] = entry
        entries.append(entry)
    return Census(entries)


def load(path):
    """Read the census at `path`. A missing file is the caller's decision."""
    with io.open(path, encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        return parse(list(reader), reader.fieldnames)


def reason(census, row, crop_sha):
    """Why the census refuses this row. Empty string means it says nothing.

    `row` needs Source_Document_ID, Figure_Number and Page - the identity that
    survives a rebuild - and `crop_sha` is the digest of the crop this build
    is actually showing.
    """
    if census is None:
        return ""
    entry = census.by_sha.get(str(crop_sha).strip().lower()) if crop_sha else None
    if entry is None:
        # THE PIXELS MOVED. Somebody looked at this figure and found it
        # defective; the crop on the sheet is no longer the one they looked
        # at. That is not a fix - nobody has seen the new one.
        key = figure_id(row.get("Source_Document_ID"), row.get("Figure_Number"),
                        row.get("Page"))
        prior = census.by_figure.get(key, ())
        if any(not countable_code(e["Agent_Visual_Code"])
               and e["Human_Verdict"] != HUMAN_COUNTABLE for e in prior):
            return ("육안 조사에서 결함으로 본 그림인데 크롭 픽셀이 그때와 "
                    "다릅니다 — 다시 보기 전에는 셀 수 없습니다 "
                    "(REVIEW_REQUIRED).")
        return ""
    if entry["Human_Verdict"] == HUMAN_BLOCKED:
        return ("사람이 계수 불가로 표시했습니다: %s"
                % (entry.get("Human_Note") or entry.get("Agent_Visual_Note")
                   or "사유 없음"))
    if entry["Human_Verdict"] == HUMAN_COUNTABLE:
        return ""
    if countable_code(entry["Agent_Visual_Code"]):
        return ""
    return ("육안 전수조사 — %s: %s (사람이 census의 Human_Verdict를 "
            "COUNTABLE로 바꾸면 다시 열립니다)"
            % (" + ".join(ATOMS[a] for a in entry["Agent_Visual_Code"].split("+")),
               entry.get("Agent_Visual_Note") or ""))
