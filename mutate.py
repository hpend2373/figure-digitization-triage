#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Revert one guard, run the scenarios, see which go red.

    python3 mutate.py MATRIX.json

`unobserved: none` is the pass condition. A guard whose reversion leaves every
scenario green is decoration, and a scenario that stays green when its guard is
gone is decoration too - this is the tool that decides which.

IT LIVES IN THE REPOSITORY BECAUSE IT FAILED IN /tmp. Two copies were started
against one file: the first was still restoring when the second applied its
mutation, and the matrix that came out reported one guard unobserved and another
observed by a scenario that was failing for a third reason. A tool whose output
this project's discipline rests on cannot be a script in a temporary directory
with no lock and no baseline check. So:

    A LOCK, refused rather than waited on - two matrices over one tree is not a
      slower run, it is a wrong answer
    A DECLARED HASH per file, checked before anything runs - a matrix carries the
      hash of the tree it was written against, which is the only check that can
      see a leftover, because a hash taken at start-up would take the leftover
      AS the baseline
    (A per-mutation re-check was written too and then removed: the restore in the
      `finally` repairs any drift a suite could cause before the next mutation
      reads it, so reverting the check turned nothing red - decoration, by this
      package's own rule, and the lock is what actually guards the hazard)
    RESTORE ON SIGNAL as well as on exception, because the way it actually died
      was a kill

MATRIX.json:

    {"suites": ["test_x.py"],
     "files": {"tick_ocr.py": "<sha256 of the file this matrix was written for>"},
     "mutations": [{"name": "...", "file": "...", "old": "...", "new": "..."}]}

`files` is what closes the leftover case. A hash taken when the RUN starts cannot
see that the file was already mutated when it started - the leftover IS its
baseline - so the matrix declares the hash it was written against, and a run over
a tree that has moved refuses instead of measuring. `python3 mutate.py --stamp
a.py b.py` prints the block to paste in.

`old` must appear EXACTLY ONCE in the file. A mutation that matches twice is not
applied and is reported as such: it would be two changes measured as one.
"""
import hashlib
import json
import os
import re
import shutil
import signal
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
LOCK = os.path.join(HERE, ".mutate.lock")
FAIL = re.compile(r"^(?:FAIL|ERROR): (\w+) \(", re.M)


def sha(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def acquire():
    """Exclusive, and refused rather than waited on."""
    try:
        fd = os.open(LOCK, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        try:
            held = open(LOCK).read().strip()
        except OSError:
            held = "?"
        raise SystemExit("another mutation run holds %s (pid %s). Two matrices "
                         "over one tree is not a slower run, it is a wrong "
                         "answer." % (LOCK, held))
    os.write(fd, str(os.getpid()).encode())
    os.close(fd)


def release():
    try:
        os.unlink(LOCK)
    except OSError:
        pass


def run_suite(mod):
    p = subprocess.run([sys.executable, mod], cwd=HERE,
                       capture_output=True, text=True)
    return sorted(set(FAIL.findall(p.stdout + p.stderr))), p.returncode


def clear_cache():
    shutil.rmtree(os.path.join(HERE, "__pycache__"), ignore_errors=True)


def main(spec_path):
    spec = json.load(open(spec_path))
    suites = spec["suites"]
    muts = spec["mutations"]
    files = sorted({m["file"] for m in muts})
    base = {}
    for f in files:
        path = os.path.join(HERE, f)
        base[f] = (open(path, encoding="utf-8").read(), sha(path))

    # DECLARED, AND CHECKED BEFORE ANYTHING RUNS. A run whose tree is not the one
    # the matrix was written against is measuring something else - a leftover
    # from a killed run, or a change made since - and there is no way to tell
    # which from inside.
    declared = spec.get("files") or {}
    moved = [f for f, want in declared.items()
             if f in base and base[f][1] != want]
    if moved:
        print("refused: %s is not the file this matrix was written against.\n"
              "  Re-stamp with `python3 mutate.py --stamp %s` once the tree is "
              "what you meant it to be." % (", ".join(moved), " ".join(moved)))
        return 1
    missing = [f for f in files if f not in declared]
    if declared and missing:
        print("refused: %s has no declared hash in the matrix" % ", ".join(missing))
        return 1

    acquire()
    current = None
    def restore(*_a):
        # THE WAY IT ACTUALLY DIED WAS A KILL, so this runs on signals too.
        if current:
            f, path = current
            open(path, "w", encoding="utf-8").write(base[f][0])
            clear_cache()
        release()
        raise SystemExit("interrupted; the tree was restored")
    for s in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
        try:
            signal.signal(s, restore)
        except (ValueError, OSError):
            pass

    try:
        red_before = []
        for m in suites:
            r, rc = run_suite(m)
            if rc:
                red_before.append((m, r))
        print("baseline: " + ("green" if not red_before
                              else "RED %s" % red_before))
        if red_before:
            return 1

        unobserved = []
        for m in muts:
            f, path = m["file"], os.path.join(HERE, m["file"])
            src = open(path, encoding="utf-8").read()
            if src.count(m["old"]) != 1:
                print("  !! %-44s NOT APPLIED (%d matches)"
                      % (m["name"], src.count(m["old"])))
                unobserved.append(m["name"] + " [not applied]")
                continue
            current = (f, path)
            open(path, "w", encoding="utf-8").write(
                src.replace(m["old"], m["new"]))
            clear_cache()
            red = []
            try:
                for mod in suites:
                    r, rc = run_suite(mod)
                    red += r
                    # A SUITE THAT EXITS NON-ZERO IS RED, whatever its output
                    # looks like. The names above come from unittest's
                    # "FAIL: name (" lines; a suite written in the check()
                    # style prints "  FAIL name" and matched nothing, so
                    # fourteen mutants of caption_fulltext.py were reported
                    # as NOTHING WENT RED while every one of them exited 1.
                    if rc and not r:
                        red.append("%s exit %d" % (mod, rc))
            finally:
                open(path, "w", encoding="utf-8").write(src)
                clear_cache()
                current = None
            print("  %-44s -> %s" % (m["name"],
                                     ", ".join(sorted(set(red))) if red
                                     else "NOTHING WENT RED"))
            if not red:
                unobserved.append(m["name"])
        print("unobserved: " + (", ".join(unobserved) if unobserved else "none"))
        return 1 if unobserved else 0
    finally:
        for f in files:
            path = os.path.join(HERE, f)
            if sha(path) != base[f][1]:
                open(path, "w", encoding="utf-8").write(base[f][0])
        clear_cache()
        release()


def stamp(paths):
    """The `files` block for a matrix, so it can be pasted rather than typed."""
    print(json.dumps({"files": {p: sha(os.path.join(HERE, p)) for p in paths}},
                     indent=2))
    return 0


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--stamp":
        sys.exit(stamp(sys.argv[2:]))
    sys.exit(main(sys.argv[1]))
