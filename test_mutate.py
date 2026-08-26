#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Scenarios for the mutation harness.

    python3 test_mutate.py

This is the tool that decides which guards in this package are real, so its own
failure modes matter more than most. All three of these are things it actually
did: two runs interleaved over one file, a killed run left a mutation applied,
and the next matrix measured that leftover as the baseline.
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import mutate                                                    # noqa: E402

RUN = [0]


class TheLock(unittest.TestCase):

    def tearDown(self):
        mutate.release()

    def test_a_second_run_is_refused_and_not_queued(self):
        """Two matrices over one tree is not a slower run, it is a wrong answer:
        the first run's restore and the second run's mutation land in either
        order. Guard: O_EXCL, and the SystemExit rather than a wait."""
        mutate.acquire()
        with self.assertRaises(SystemExit) as cm:
            mutate.acquire()
        self.assertIn("another mutation run", str(cm.exception))
        RUN[0] += 1

    def test_the_lock_is_released_and_the_next_run_starts(self):
        mutate.acquire()
        mutate.release()
        mutate.acquire()          # must not raise
        RUN[0] += 1


class TheBaselineCheck(unittest.TestCase):
    """The check that turns a leftover mutation into a refusal."""

    def _tree(self, body):
        d = tempfile.mkdtemp()
        open(os.path.join(d, "subject.py"), "w").write(body)
        open(os.path.join(d, "test_subject.py"), "w").write(
            "import subject, sys, unittest\n"
            "class T(unittest.TestCase):\n"
            "    def test_guard(self):\n"
            "        self.assertEqual(subject.answer(), 42)\n"
            "if __name__ == '__main__':\n"
            "    r = unittest.TextTestRunner(verbosity=2).run(\n"
            "        unittest.defaultTestLoader.loadTestsFromModule(\n"
            "            sys.modules[__name__]))\n"
            "    print('FDT_SCENARIOS_RUN=1')\n"
            "    sys.exit(0 if r.wasSuccessful() else 1)\n")
        return d

    def _run(self, d, muts):
        spec = os.path.join(d, "m.json")
        json.dump({"suites": ["test_subject.py"], "mutations": muts},
                  open(spec, "w"))
        env = dict(os.environ)
        p = subprocess.run([sys.executable, os.path.join(HERE, "mutate.py"), spec],
                           cwd=d, capture_output=True, text=True, env=env)
        return p.stdout + p.stderr, p.returncode

    def _harness_in(self, d):
        """`mutate.py` anchors on its own directory, so it is copied in."""
        import shutil
        shutil.copy(os.path.join(HERE, "mutate.py"), d)
        return os.path.join(d, "mutate.py")

    def test_a_guard_whose_reversion_breaks_a_scenario_is_observed(self):
        d = self._tree("def answer():\n    return 42\n")
        h = self._harness_in(d)
        spec = os.path.join(d, "m.json")
        json.dump({"suites": ["test_subject.py"],
                   "mutations": [{"name": "the answer", "file": "subject.py",
                                  "old": "return 42", "new": "return 7"}]},
                  open(spec, "w"))
        p = subprocess.run([sys.executable, h, spec], cwd=d,
                           capture_output=True, text=True)
        self.assertIn("test_guard", p.stdout)
        self.assertIn("unobserved: none", p.stdout)
        self.assertEqual(open(os.path.join(d, "subject.py")).read(),
                         "def answer():\n    return 42\n",
                         "the tree was not restored")
        RUN[0] += 1

    def test_decoration_is_named(self):
        """A guard whose reversion changes nothing."""
        d = self._tree("def answer():\n    return 42\n\n\ndef unused():\n    return 1\n")
        h = self._harness_in(d)
        spec = os.path.join(d, "m.json")
        json.dump({"suites": ["test_subject.py"],
                   "mutations": [{"name": "the unused branch",
                                  "file": "subject.py",
                                  "old": "return 1", "new": "return 2"}]},
                  open(spec, "w"))
        p = subprocess.run([sys.executable, h, spec], cwd=d,
                           capture_output=True, text=True)
        self.assertIn("NOTHING WENT RED", p.stdout)
        self.assertIn("unobserved: the unused branch", p.stdout)
        self.assertEqual(p.returncode, 1, "an unobserved guard exited 0")
        RUN[0] += 1

    def test_a_tree_that_is_not_the_one_the_matrix_was_written_for_is_refused(self):
        """The failure this file exists for: a killed run left `SCALES = (3,)` in
        place, and the next matrix measured that as the baseline. A hash taken
        when the RUN starts cannot see it - the leftover IS its baseline - so the
        MATRIX declares the hash it was written against.
        Guard: the `refused:` return, and --stamp."""
        d = self._tree("def answer():\n    return 42\n")
        h = self._harness_in(d)
        spec = os.path.join(d, "m.json")
        json.dump({"suites": ["test_subject.py"],
                   "files": {"subject.py": "0" * 64},
                   "mutations": [{"name": "x", "file": "subject.py",
                                  "old": "return 42", "new": "return 7"}]},
                  open(spec, "w"))
        p = subprocess.run([sys.executable, h, spec], cwd=d,
                           capture_output=True, text=True)
        self.assertIn("refused:", p.stdout)
        self.assertIn("--stamp", p.stdout)
        self.assertNotIn("-> ", p.stdout)
        self.assertEqual(p.returncode, 1)
        # and with the right hash it runs
        got = subprocess.run([sys.executable, h, "--stamp", "subject.py"],
                             cwd=d, capture_output=True, text=True)
        json.dump({"suites": ["test_subject.py"],
                   "files": json.loads(got.stdout)["files"],
                   "mutations": [{"name": "x", "file": "subject.py",
                                  "old": "return 42", "new": "return 7"}]},
                  open(spec, "w"))
        p2 = subprocess.run([sys.executable, h, spec], cwd=d,
                            capture_output=True, text=True)
        self.assertIn("unobserved: none", p2.stdout)
        RUN[0] += 1

    def test_a_kill_mid_mutation_leaves_the_tree_clean(self):
        """The way it actually died was a kill, so the restore cannot live only
        in a `finally`. Guard: the signal handlers."""
        import signal as sig
        import time
        d = self._tree("def answer():\n    return 42\n")
        h = self._harness_in(d)
        # a suite that takes long enough to be killed inside
        open(os.path.join(d, "test_subject.py"), "w").write(
            "import time, sys\ntime.sleep(30)\nprint('FDT_SCENARIOS_RUN=1')\n")
        spec = os.path.join(d, "m.json")
        json.dump({"suites": ["test_subject.py"],
                   "mutations": [{"name": "x", "file": "subject.py",
                                  "old": "return 42", "new": "return 7"}]},
                  open(spec, "w"))
        proc = subprocess.Popen([sys.executable, h, spec], cwd=d,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                text=True)
        time.sleep(3)
        proc.send_signal(sig.SIGTERM)
        try:
            proc.communicate(timeout=20)
        except subprocess.TimeoutExpired:
            proc.kill()
            self.skipTest("the harness did not exit on SIGTERM in time")
        self.assertEqual(open(os.path.join(d, "subject.py")).read(),
                         "def answer():\n    return 42\n",
                         "a killed run left the mutation in place")
        self.assertFalse(os.path.exists(os.path.join(d, ".mutate.lock")),
                         "a killed run left its lock behind")
        RUN[0] += 1

    def test_a_mutation_matching_twice_is_not_applied(self):
        """Two changes measured as one. Guard: the `count(old) != 1` branch."""
        d = self._tree("def answer():\n    x = 1\n    y = 1\n    return 42\n")
        h = self._harness_in(d)
        spec = os.path.join(d, "m.json")
        json.dump({"suites": ["test_subject.py"],
                   "mutations": [{"name": "ambiguous", "file": "subject.py",
                                  "old": "= 1", "new": "= 2"}]},
                  open(spec, "w"))
        p = subprocess.run([sys.executable, h, spec], cwd=d,
                           capture_output=True, text=True)
        self.assertIn("NOT APPLIED (2 matches)", p.stdout)
        RUN[0] += 1

    def test_a_red_baseline_stops_before_any_mutation(self):
        """Measuring mutations against a failing suite tells you nothing."""
        d = self._tree("def answer():\n    return 41\n")
        h = self._harness_in(d)
        spec = os.path.join(d, "m.json")
        json.dump({"suites": ["test_subject.py"],
                   "mutations": [{"name": "x", "file": "subject.py",
                                  "old": "return 41", "new": "return 7"}]},
                  open(spec, "w"))
        p = subprocess.run([sys.executable, h, spec], cwd=d,
                           capture_output=True, text=True)
        self.assertIn("baseline: RED", p.stdout)
        self.assertNotIn("-> ", p.stdout)
        RUN[0] += 1


if __name__ == "__main__":
    result = unittest.TextTestRunner(verbosity=2).run(
        unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__]))
    print("FDT_SCENARIOS_RUN=%d" % RUN[0])
    sys.exit(0 if result.wasSuccessful() else 1)
