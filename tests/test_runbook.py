# -*- coding: utf-8 -*-
"""The reviewer's runbook is checked like code.

    python3 tests/test_runbook.py     # exit 0 = all scenarios pass

`docs/REVIEW_RUNBOOK.md` is the order a PERSON works in. A runbook that names a
flag nothing accepts, a file the run never writes, or an exit code the tools do
not return sends a reviewer to improvise - the one thing the file exists to
prevent. Every command line in it is parsed against the real parsers, and the
file paths and review-mode pairings it promises are read off the code.
"""
import _paths  # noqa: E402,F401  (puts fdt/ on sys.path)
import os

FAILURES, PASSED = [], [0]


def check(name, ok, detail=""):
    print(("  ok   " if ok else "  FAIL ") + name + ("" if ok else "  <- " + detail))
    if ok:
        PASSED[0] += 1
    else:
        FAILURES.append(name)


print("the runbook names commands and flags this package actually has")
# docs/REVIEW_RUNBOOK.md is the procedure a person follows, and a procedure that names a flag
# nothing accepts is worse than none: the reviewer runs it, gets an error, and
# improvises - which is the one thing the file exists to prevent. Every command
# line in it is parsed against the real parsers.
import re as _re                                                   # noqa: E402
import finalize_batch as _FIN                                      # noqa: E402
import review_preflight as _PF                                     # noqa: E402
import run_batch as _RB                                            # noqa: E402

_PILOT = os.path.join(_paths.ROOT, "docs", "REVIEW_RUNBOOK.md")
check("the runbook is in the package", os.path.exists(_PILOT))
_lines = [l.strip() for l in open(_PILOT, encoding="utf-8").read().splitlines()
          if l.strip().startswith("python3 ")]
_lines += [l.strip() for l in open(_PILOT, encoding="utf-8").read().splitlines()
           if _re.match(r"^\s+\d+\s+python3 ", l)]
_lines = [_re.sub(r"^\d+\s+", "", l) for l in _lines]
check("  and it gives a command for every step of the review",
      len(_lines) >= 5, "%s" % _lines)
_MODULES = {"run_batch.py": _RB, "review_preflight.py": _PF,
            "finalize_batch.py": _FIN}
_unknown = []
for _line in _lines:
    _parts = _line.split()
    _script = _parts[1][len("fdt/"):] if _parts[1].startswith("fdt/") else _parts[1]
    _module = _MODULES.get(_script) if _parts[1].startswith("fdt/") else None
    if _module is None:
        _unknown.append(_parts[1])
        continue
    _flags = {p for p in _parts[2:] if p.startswith("--")}
    _src = open(os.path.join(_paths.CODE, _script), encoding="utf-8").read()
    for _flag in _flags:
        if 'add_argument("%s"' % _flag not in _src:
            _unknown.append("%s %s" % (_parts[1], _flag))
check("  and every flag it names is one that module accepts",
      not _unknown, "%s" % _unknown)
# AND THE FILES IT TELLS A REVIEWER TO OPEN are the ones the run writes.
_named = set(_re.findall(r'`?(OUT/[A-Za-z0-9_./<>-]+)`?', open(_PILOT, encoding="utf-8").read()))
_writes = set(_RB.CANONICAL_DIRS) | set(_RB.CANONICAL_OUTPUTS) | {
    "value_review.csv", "inference_review.csv", "figure_values_accepted.csv"}
_missing = [n for n in _named
            if n.split("/")[1].split("<")[0].rstrip("_")
            not in {w.split("/")[0].rstrip("/") for w in _writes}
            and n.split("/")[1] not in _writes]
check("  and every file it tells a reviewer to open is one the run writes",
      not _missing, "%s / writes %s" % (sorted(_missing), sorted(_writes)))
# AND THE FIRST PILOT'S REVIEW MODE IS DESCRIBED IN FULL. v7.95. Publication 127
# Figure 4 is queued `BAR_MONO_GEOMETRY_RESOLVED`, which is not an overlay: it
# registers six artifacts and asks for four confirmations, and three of those
# four cannot be made from a panel picture. The printed tick numbers, the ink
# inside a 15 px bar and somebody else's reading of a legend are each somewhere
# else. A runbook that names the mode and then sends the reviewer to one overlay
# collects a signature on an axis nobody read - and v7.94's did exactly that.
#
# IN THE SECTION THAT NAMES THE MODE, not anywhere in the file. Scoped to the
# whole document the first version passed while the artifact-to-confirmation
# mapping was deleted: `Identity_Checked` also appears in the glossary further
# down, so "the word is present somewhere" is satisfied by a table that does not
# say WHICH picture answers it. What a reviewer needs is the pairing.
_text = open(_PILOT, encoding="utf-8").read()
_MODE = "BAR_MONO_GEOMETRY_RESOLVED"
_sections = [s for s in _re.split(r"^## ", _text, flags=_re.M) if _MODE in s]
check("  it walks through the longest review mode in a section of its own",
      _MODE in _RB.REVIEW_MODES and len(_sections) == 1,
      "%d section(s) mention it" % len(_sections))
_section = _sections[0] if _sections else ""
_unnamed = [a for a in _RB.REVIEW_MODES[_MODE] if a not in _section]
check("    and, in that section, every artifact that mode registers",
      not _unnamed, "%s" % _unnamed)
#
# AND THE CONFIRMATIONS ARE CHECKED ON THE `->` LINES, which are the mapping from
# a picture to the claim it answers. Checked against the section's prose instead,
# the mutation that deletes the mapping passes: the paragraph above the steps
# lists all four confirmations by name, so the file can say WHICH claims are
# wanted while no longer saying which artifact answers any of them. The pairing
# is the part a reviewer cannot reconstruct.
#
# AND THE TEMPLATE STEP NAMES ITS FILES ONE BY ONE. "Writes both decision files"
# is true of an R3 run and false of the first pilot: `--template` writes
# `inference_review.csv` only where there are reconstructed cells, 127 has none,
# and a reviewer told to expect two starts by hunting for a missing one. The
# tier that makes the second file conditional is read from the code, so the
# sentence cannot go stale against `CELL_CONFIRMATION_TIERS` either.
import provenance as _PROV                                         # noqa: E402
_step2 = [b for b in _text.split("\n\n") if "--template" in b]
_want2 = (["value_review.csv", "inference_review.csv"]
          + list(_PROV.CELL_CONFIRMATION_TIERS))
_absent2 = [w for w in _want2 if not any(w in b for b in _step2)]
check("  the template step names each decision file, and when the second exists",
      _step2 and not _absent2, "%s missing from %s" % (_absent2, _step2))
_mapped = " ".join(l for l in _section.splitlines() if l.strip().startswith("->"))
_unasked = [c for c in _RB.REVIEW_CONFIRMATIONS[_MODE] if c not in _mapped]
check("    and every confirmation it asks a person to make, against the picture "
      "that answers it",
      not _unasked, "%s / mapped %r" % (_unasked, _mapped))

print()
print("every command the documentation names is one this package has")
# The same rule for every document a person or an agent follows: a command line
# `python3 fdt/<script>.py` names a script that exists, and every `--flag` on it
# is one that script's parser declares. The docs moved when the code moved to
# `fdt/`; this is what keeps them moving together.
import glob as _glob                                               # noqa: E402
_DOCS = ([os.path.join(_paths.ROOT, "README.md"), os.path.join(_paths.ROOT, "SKILL.md"),
          os.path.join(_paths.CODE, "sheet", "README.md"),
          os.path.join(_paths.ROOT, "examples", "quickstart", "README.md")]
         + sorted(_glob.glob(os.path.join(_paths.ROOT, "docs", "*.md"))))
_bad, _seen = [], 0
for _doc in _DOCS:
    for _line in open(_doc, encoding="utf-8"):
        for _m in _re.finditer(r"python3 (fdt/[\w/]+\.py)([^\n#|`]*)", _line):
            _seen += 1
            _script = os.path.join(_paths.ROOT, _m.group(1))
            if not os.path.exists(_script):
                _bad.append("%s: %s does not exist" % (os.path.basename(_doc), _m.group(1)))
                continue
            _src = open(_script, encoding="utf-8").read()
            for _flag in _re.findall(r"(?<![\w-])(--[a-z][\w-]*)", _m.group(2)):
                if '"%s"' % _flag not in _src and "'%s'" % _flag not in _src:
                    _bad.append("%s: %s %s" % (os.path.basename(_doc), _m.group(1), _flag))
check("the documents name commands at all", _seen >= 40, "%d" % _seen)
check("  and every script they name exists, with every flag it accepts",
      not _bad, "%s" % _bad)
# AND NO DOCUMENT STILL SENDS A READER TO THE OLD FLAT LAYOUT.
_flat = []
_names = set(os.listdir(_paths.CODE))
for _doc in _DOCS:
    for _n, _line in enumerate(open(_doc, encoding="utf-8"), 1):
        for _m in _re.finditer(r"python3 ([a-z_]+\.py)\b", _line):
            if _m.group(1) in _names:
                _flat.append("%s:%d %s" % (os.path.basename(_doc), _n, _m.group(1)))
check("  and none of them runs a pipeline script from the old flat layout",
      not _flat, "%s" % _flat)

# AND EVERY RELATIVE LINK IN THEM LEADS SOMEWHERE. The documents moved into
# `docs/` and the code into `fdt/`; a link that still points at the old place
# is a reader sent to a page that is not there.
_dead = []
for _doc in _DOCS:
    for _m in _re.finditer(r"\]\(([^)#\s]+)(#[^)]*)?\)", open(_doc, encoding="utf-8").read()):
        _target = _m.group(1)
        if _target.startswith(("http://", "https://", "mailto:")):
            continue
        if not os.path.exists(os.path.normpath(os.path.join(os.path.dirname(_doc), _target))):
            _dead.append("%s -> %s" % (os.path.relpath(_doc, _paths.ROOT), _target))
check("  and every relative link in them resolves", not _dead, "%s" % _dead)

print()
print("FDT_SCENARIOS_RUN=%d" % (PASSED[0] + len(FAILURES)))
print("%d scenarios run" % (PASSED[0] + len(FAILURES)))
if FAILURES:
    print("%d FAILED: %s" % (len(FAILURES), FAILURES))
    raise SystemExit(1)
print("all scenarios passed")
