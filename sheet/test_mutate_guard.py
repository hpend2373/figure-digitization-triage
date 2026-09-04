# -*- coding: utf-8 -*-
"""Does the source come back when the mutation run is killed?

    python3 test_mutate_guard.py

The runners restored their files in a `finally`, which a signal walks straight
past. A timeout killed one on 2026-09-02 and `census.py` kept the mutant - the
line that lets a person's COUNTABLE verdict clear a defect became `if False:`
and stayed there. So the scenario that matters here is not "does the context
manager restore on the happy path": it is **SIGKILL**, sent for real, to a
real child process holding a real mutation.
"""
import io
import os
import signal
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import mutate_guard as G                                        # noqa: E402

N, FAIL = [0], []


def check(name, ok, detail=""):
    N[0] += 1
    print("  %s %s%s" % ("ok  " if ok else "FAIL", name,
                         "" if ok else "  <- %s" % (detail,)))
    if not ok:
        FAIL.append(name)


TMP = tempfile.mkdtemp(prefix="fdt-guard-")
SRC = os.path.join(TMP, "victim.py")
ORIGINAL = "GUARD = True\n"
io.open(SRC, "w", encoding="utf-8").write(ORIGINAL)

# ------------------------------------------------------------- the happy path
with G.mutation(SRC, "GUARD = False\n"):
    check("the file is mutated inside the block",
          io.open(SRC, encoding="utf-8").read() == "GUARD = False\n")
    check("a copy of the original is on disk while it is mutated",
          io.open(SRC + G.SUFFIX, encoding="utf-8").read() == ORIGINAL)
check("it is back afterwards",
      io.open(SRC, encoding="utf-8").read() == ORIGINAL)
check("and the backup no longer claims anything is in flight",
      not os.path.exists(SRC + G.SUFFIX)
      or io.open(SRC + G.SUFFIX, encoding="utf-8").read() == "")
check("so a later run finds nothing to restore", G.restore_any(TMP) == [])

# ----------------------------------------------------------- and on an error
try:
    with G.mutation(SRC, "GUARD = None\n"):
        raise RuntimeError("시나리오가 일부러 낸 오류")
except RuntimeError:
    pass
check("an exception still puts it back",
      io.open(SRC, encoding="utf-8").read() == ORIGINAL)

# ------------------------------------------------------------------- SIGKILL
# 진짜로 죽입니다. `finally`가 지나칠 수 있는 유일한 길이고, 실제로 지나갔습니다.
CHILD = os.path.join(TMP, "child.py")
io.open(CHILD, "w", encoding="utf-8").write(
    "import sys, time\n"
    "sys.path.insert(0, %r)\n"
    "import mutate_guard as G\n"
    "with G.mutation(%r, 'GUARD = KILLED\\n'):\n"
    "    print('in', flush=True)\n"
    "    time.sleep(30)\n" % (HERE, SRC))
p = subprocess.Popen([sys.executable, CHILD], stdout=subprocess.PIPE, text=True)
line = p.stdout.readline()
check("the child got as far as holding the mutation", line.strip() == "in", line)
os.kill(p.pid, signal.SIGKILL)
p.wait()
check("a killed run leaves the file mutated (this is the failure being fixed)",
      io.open(SRC, encoding="utf-8").read() == "GUARD = KILLED\n",
      io.open(SRC, encoding="utf-8").read())
check("but the original is sitting on disk beside it",
      io.open(SRC + G.SUFFIX, encoding="utf-8").read() == ORIGINAL)
_fixed = G.restore_any(TMP)
check("the next run puts it back", io.open(SRC, encoding="utf-8").read() == ORIGINAL)
check("and names the file it repaired, rather than fixing it silently",
      _fixed == ["victim.py"], _fixed)
check("a second call has nothing left to do", G.restore_any(TMP) == [])

# 빈 백업은 '진행 중인 것 없음'입니다 - 지울 수 없는 곳에서도 같은 뜻이어야
# 합니다. 이것을 복원해 버리면 파일이 빈 파일로 덮어씌워집니다.
io.open(SRC + G.SUFFIX, "w", encoding="utf-8").write("")
check("an empty backup is not treated as something to restore",
      G.restore_any(TMP) == []
      and io.open(SRC, encoding="utf-8").read() == ORIGINAL)

# 모든 러너가 실제로 이 가드를 쓰고 있는가 - 하나라도 빠지면 그 파일이 다음
# 희생자입니다.
import glob                                                      # noqa: E402
_runners = [f for f in sorted(glob.glob(os.path.join(HERE, "mutate_*.py")))
            if not f.endswith("mutate_guard.py")]
_unguarded = [os.path.basename(f) for f in _runners
              if "mutate_guard.mutation(" not in io.open(f, encoding="utf-8").read()]
check("변이 러너 %d개가 모두 이 가드를 쓴다" % len(_runners), not _unguarded, _unguarded)
_no_restore = [os.path.basename(f) for f in _runners
               if "restore_any" not in io.open(f, encoding="utf-8").read()]
check("모두 시작할 때 지난 실행의 잔해를 되돌린다", not _no_restore, _no_restore)

import shutil                                                    # noqa: E402
shutil.rmtree(TMP, ignore_errors=True)
print()
print("FDT_SCENARIOS_RUN=%d" % N[0])
print("%d scenarios run" % N[0])
if FAIL:
    print("%d FAILED: %s" % (len(FAIL), FAIL))
    raise SystemExit(1)
print("all scenarios passed")
