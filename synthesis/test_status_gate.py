# -*- coding: utf-8 -*-
"""Scenarios for the status gate's own checks.

    python3 test_status_gate.py      # exit 0 = all scenarios pass

Writes its own throwaway trees, so it reads nothing that has to exist.

WHY THIS SUITE EXISTS. `verify_synthesis_status.py` gained a check that reads
every module here, not only `test_*.py`, because two scripts in this folder
called `sys.path.insert` without importing `sys` and nothing noticed: the
grammar is legal, so `py_compile` passes, and neither file is a suite, so every
count in the gate looked past them. A guard added without a scenario is the
same class of thing it was added to stop - present, plausible, unobserved -
so each check below dies if the guard is reverted.
"""
import io
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import verify_synthesis_status as V                              # noqa: E402

FAIL, N = [], [0]


def check(name, ok, detail=''):
    print(('  ok   ' if ok else '  FAIL ') + name + ('' if ok else '  <- ' + detail))
    if ok:
        N[0] += 1
    else:
        FAIL.append(name)


def tree(**modules):
    """A directory holding the given `name.py: source` modules."""
    where = tempfile.mkdtemp(prefix='fdt-gate-')
    for name, source in modules.items():
        io.open(os.path.join(where, name + '.py'), 'w',
                encoding='utf-8').write(source)
    return where


def said(where):
    return V.unbound_names(where)


# ------------------------------------------------------------ the real defect
_MISSING = said(tree(helper='import os\nHERE = os.getcwd()\n'
                            'sys.path.insert(0, HERE)\n'))
check("a module that uses sys without importing it is reported",
      len(_MISSING) == 1, '%s' % _MISSING)
check("the report names the module, the line and the name",
      _MISSING and 'helper.py:3' in _MISSING[0] and 'sys' in _MISSING[0],
      '%s' % _MISSING)

# THE FILE IS NOT A SUITE. This is the whole point: the counts above this
# check only see `test_*.py`, and both real defects were in scripts.
check("the scan reaches modules that are not test files",
      _MISSING and _MISSING[0].startswith('helper.py'), '%s' % _MISSING)

# -------------------------------------------------------------- not a defect
check("a module that imports what it uses is clean",
      said(tree(ok='import sys\nsys.path.insert(0, ".")\n')) == [])
check("`from x import y` binds y",
      said(tree(ok='from os import path\nprint(path.sep)\n')) == [])
check("`import x.y as z` binds z, not x",
      said(tree(ok='import os.path as p\nprint(p.sep)\n')) == [])
check("builtins are not reported",
      said(tree(ok='print(len(list(range(3))))\n')) == [])
check("a def, a class and a comprehension target all bind",
      said(tree(ok='class C:\n    pass\n\n\ndef f():\n    return C\n\n\n'
                   'xs = [i for i in range(3)]\nprint(f(), xs)\n')) == [])
check("an except handler's name binds",
      said(tree(ok='try:\n    pass\nexcept ValueError as exc:\n'
                   '    print(exc)\n')) == [])
check("a function argument binds",
      said(tree(ok='def f(a):\n    return a\n')) == [])
check("assigning a name is not using it",
      said(tree(ok='undefined_thing = 1\n')) == [])

# THE OVER-APPROXIMATION IS DELIBERATE, so it is pinned rather than left to
# be discovered. A name bound in one function counts as bound everywhere; this
# check is the record of that trade, and it fails if the scan is ever
# tightened into a scope checker without anybody saying so.
check("a name bound only inside another function is not reported",
      said(tree(ok='def a():\n    thing = 1\n    return thing\n\n\n'
                   'def b():\n    return thing\n')) == [])

# ------------------------------------------------- could not look != nothing wrong
_BROKEN = tree(broken='def f(:\n')
check("a module that does not parse is reported, not skipped",
      len(said(_BROKEN)) == 1 and 'does not parse' in said(_BROKEN)[0],
      '%s' % said(_BROKEN))

_UNREADABLE = tree(gone='import sys\n')
os.chmod(os.path.join(_UNREADABLE, 'gone.py'), 0)
_SAID_UNREADABLE = said(_UNREADABLE)
check("a module that cannot be read is reported, not skipped",
      len(_SAID_UNREADABLE) == 1
      and 'could not be read' in _SAID_UNREADABLE[0],
      '%s' % _SAID_UNREADABLE)
os.chmod(os.path.join(_UNREADABLE, 'gone.py'), 0o600)

# ------------------------------------------------------- every module, not one
_MANY = said(tree(one='import sys\nsys.exit(0)\n',
                  two='os.getcwd()\n',
                  three='json.dumps({})\n'))
check("every module is scanned, not just the first",
      len(_MANY) == 2, '%s' % _MANY)
check("each report names its own module",
      sorted(m.split('.py')[0] for m in _MANY) == ['three', 'two'],
      '%s' % _MANY)

# ------------------------------------------- what cannot be imported is not a module
_LITTER = tempfile.mkdtemp(prefix='fdt-gate-')
io.open(os.path.join(_LITTER, 'helper.py'), 'w',
        encoding='utf-8').write('import sys\nsys.exit(0)\n')
io.open(os.path.join(_LITTER, 'helper 2.py'), 'w',
        encoding='utf-8').write('sys.exit(0)\n')
check("a stem that is not an identifier is skipped - nothing can import it",
      said(_LITTER) == [], '%s' % said(_LITTER))

# AND THE FILTER IS NOT A LICENCE TO SKIP. The sync copies are excluded
# because `import helper 2` is not a sentence, not because defects in files
# with odd names do not matter; a normally-named module is still read.
io.open(os.path.join(_LITTER, 'helper_two.py'), 'w',
        encoding='utf-8').write('sys.exit(0)\n')
check("a module with an importable name is still reported",
      [m.split(':')[0] for m in said(_LITTER)] == ['helper_two.py'],
      '%s' % said(_LITTER))

# ------------------------------------------------------------- this tree, now
check("no module in synthesis/ uses a name it never binds",
      V.unbound_names() == [], '%s' % V.unbound_names())

# ------------------------------ the same rule decides which files are suites
# THE FILE-SET CHECK HAD THE SAME BLIND SPOT IN REVERSE. It read every
# `test_*.py` on disk, so the sync copies arrived as suites nobody declared
# and the gate could not pass in a synced checkout at all. One function now
# answers "what is a module here" for both checks.
_SUITES = tempfile.mkdtemp(prefix='fdt-gate-')
for _f in ('test_real.py', 'test_real 2.py', 'helper.py', 'helper 2.py'):
    io.open(os.path.join(_SUITES, _f), 'w', encoding='utf-8').write('x = 1\n')
check("the suite list skips names nothing can import",
      [os.path.basename(m) for m in V._modules(_SUITES, 'test_*.py')]
      == ['test_real.py'],
      '%s' % V._modules(_SUITES, 'test_*.py'))
check("and the same rule answers for every module, not only suites",
      [os.path.basename(m) for m in V._modules(_SUITES)]
      == ['helper.py', 'test_real.py'], '%s' % V._modules(_SUITES))

# --------------------------------------------- and the gate actually asks it
# A CHECK THAT NOTHING CALLS IS A CHECK THAT PASSES. Every scenario above
# calls `unbound_names` directly, so deleting the one line in `main` that
# consults it left all of them green - the mutation run found that, and this
# is the scenario it was missing. `main` is driven over an empty tree so it
# reaches the verdict without running the suites.
_EMPTY = tempfile.mkdtemp(prefix='fdt-gate-')
io.open(os.path.join(_EMPTY, 'README.md'), 'w', encoding='utf-8').write(
    '<!-- CURRENT_SYNTHESIS_SCENARIO_COUNT: 0 -->\n')
_KEEP = (V.HERE, V.CI_SUITES, V.BUNDLE_SUITES, V.unbound_names,
         V.vacuous_scenarios)
V.HERE, V.CI_SUITES, V.BUNDLE_SUITES = _EMPTY, (), ()
V.vacuous_scenarios = lambda: []
V.unbound_names = lambda *a, **k: ['sentinel.py:1 uses nothing and never binds it']
import contextlib                                                # noqa: E402
_out = io.StringIO()
try:
    with contextlib.redirect_stdout(_out):
        V.main()
    _raised = False
except SystemExit:
    _raised = True
finally:
    (V.HERE, V.CI_SUITES, V.BUNDLE_SUITES, V.unbound_names,
     V.vacuous_scenarios) = _KEEP
check("main fails when a module uses a name it never binds",
      _raised, _out.getvalue()[-200:])
check("and main says which module, in its own words",
      'sentinel.py:1' in _out.getvalue(), _out.getvalue()[-200:])

print()
print('FDT_SCENARIOS_RUN=%d' % N[0])
print('%d scenarios run' % N[0])
if FAIL:
    print('%d FAILED: %s' % (len(FAIL), FAIL))
    raise SystemExit(1)
print('all scenarios passed')
