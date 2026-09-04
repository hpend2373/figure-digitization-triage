# -*- coding: utf-8 -*-
"""Put the source back even when the mutation run is killed.

WHY THIS FILE EXISTS. Every mutation runner restored its file in a `finally`,
which is enough for an exception and useless against a signal. On 2026-09-02 a
run hit a timeout and was killed between writing the mutant and restoring it,
and `census.py` was left holding

    if False:                       # was: if entry["Human_Verdict"] == HUMAN_COUNTABLE

- the line that lets a person's COUNTABLE verdict clear a defect. Git said the
file was modified; nothing else said anything. It was found only because a
LATER run reported PATCH_FAILED on an anchor the mutant had eaten. A person's
verdict was being ignored in the meantime.

A copy written to disk BEFORE the mutation is the one step a killed process
cannot skip. `restore_any` at the top of a run puts back whatever the last one
left behind, and says so loudly - a silent repair would hide exactly the fact
that matters.

AN EMPTY BACKUP MEANS NOTHING IS IN FLIGHT. Deleting the file would be the
obvious way to say that, and some places this runs cannot delete at all (a
sandboxed mount refuses `unlink` with EPERM). Emptying it works everywhere and
says the same thing without depending on a permission: a killed run always
leaves a backup with the source in it, because it is written before the
mutation; a finished one leaves an empty file.
"""
import contextlib
import io
import os

SUFFIX = ".mutant-backup"


def _release(backup):
    """Say 'nothing in flight' - by deleting where that is allowed, else by
    emptying. Both are read the same way by `restore_any`."""
    try:
        os.remove(backup)
    except OSError:
        io.open(backup, "w", encoding="utf-8").write("")


def slice_of(mutants):
    """The part of the list this run should try, from FDT_MUT_SLICE="a:b".

    A suite that takes two seconds times ninety mutants is three minutes, and
    the shell this runs in gives less than that. Splitting the list is the
    difference between "we ran the mutants" and "we ran the ones that fit".
    The default is everything, so a plain run is unchanged.
    """
    spec = os.environ.get("FDT_MUT_SLICE", "").strip()
    if not spec:
        return list(mutants)
    a, _, b = spec.partition(":")
    start = int(a) if a.strip() else 0
    stop = int(b) if b.strip() else len(mutants)
    return list(mutants)[start:stop]


def restore_any(where):
    """Undo whatever a killed run left mutated. Returns the files it fixed."""
    fixed = []
    for name in sorted(os.listdir(where)):
        if not name.endswith(SUFFIX):
            continue
        backup = os.path.join(where, name)
        target = os.path.join(where, name[:-len(SUFFIX)])
        held = io.open(backup, encoding="utf-8").read()
        if not held:                       # a finished run left this
            continue
        io.open(target, "w", encoding="utf-8").write(held)
        _release(backup)
        fixed.append(os.path.basename(target))
    if fixed:
        print("복원: 지난 변이 실행이 %s을(를) 되돌리지 못한 채 끝났습니다 — "
              "원본으로 되돌렸습니다." % ", ".join(fixed))
    return fixed


@contextlib.contextmanager
def mutation(path, text):
    """Hold `path` mutated to `text`, with a copy of the original on disk."""
    backup = path + SUFFIX
    original = io.open(path, encoding="utf-8").read()
    io.open(backup, "w", encoding="utf-8").write(original)
    try:
        io.open(path, "w", encoding="utf-8").write(text)
        yield
    finally:
        io.open(path, "w", encoding="utf-8").write(original)
        _release(backup)
