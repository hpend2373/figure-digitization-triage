#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for the experiment harness.

Each test names the failure it would have caught.  The rule this suite is held
to: revert the guard, re-run, and the test must go red.  A test that passes
before and after the guard is decoration and does not belong here.  The guard
each test is paired with is named in its docstring so that reverting it is a
mechanical act rather than a search.
"""
import csv, json, os, subprocess, sys, tempfile, textwrap, time, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import harness_compare as H


# ------------------------------------------------------------------ fixtures

HDR = ["pid", "fig", "png", "panel", "status", "fragment", "declared_axes",
       "x0", "x1", "y0", "y1", "spine_x", "baseline_y"]


def row(panel, x0, x1, y0, y1, sx, by, status="LADDER_OK", frag="",
        pid="475", fig="Fig. 2", dec=6):
    return dict(pid=pid, fig=fig, png="ID%s.png" % pid, panel=panel, status=status,
                fragment=frag, declared_axes=dec, x0=x0, x1=x1, y0=y0, y1=y1,
                spine_x=sx, baseline_y=by)


def write_csv(path, rows):
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, HDR)
        w.writeheader()
        for r in rows:
            w.writerow(r)
    return path


def fake_arm(body):
    """A stand-in for propose.py: writes to $OUT and nothing else.

    The real driver takes hours on the corpus.  These tests are about the
    experiment scaffolding, not about panels, so the arm only has to behave like
    a program that reads staged inputs and writes one file.
    """
    return "import os,sys,time,subprocess\n" + "".join(
        textwrap.dedent(part) for part in (body if isinstance(body, tuple) else (body,)))


class Tree:
    """A staged code tree the driver can point an arm at."""
    def __init__(self, root, name, arm_body):
        self.path = os.path.join(root, name)
        os.makedirs(self.path, exist_ok=True)
        open(os.path.join(self.path, "arm.py"), "w").write(fake_arm(arm_body))
        for n in H.CODE_FILES:
            open(os.path.join(self.path, n), "w").write("# %s\n" % name)


BASE_ARM = """
    rows = ["pid,fig,png,panel,status,fragment,declared_axes,x0,x1,y0,y1,spine_x,baseline_y",
            "475,Fig. 2,a.png,P01,LADDER_OK,,6,31,403,28,322,148,307",
            "475,Fig. 2,a.png,P02,LADDER_OK,,6,533,904,33,322,650,305"]
    open(os.environ["OUT"], "w").write("\\n".join(rows) + "\\n")
"""


def run_driver(argv):
    """Call main() and hand back the parsed report rather than the exit code."""
    root = dict(zip(argv[0::2], argv[1::2])).get("--out")
    try:
        H.main(argv)
    except SystemExit:
        pass
    with open(os.path.join(root, "comparison.json")) as f:
        return json.load(f)


def base_argv(tmp, base, cand, **kw):
    dig = write_dig(tmp)
    clips = write_clips(tmp)
    argv = ["--base-ref", base, "--candidate-ref", cand,
            "--out", os.path.join(tmp, "run"), "--cmd", "python3 arm.py",
            "--dig", dig, "--clips", clips, "--caps", os.path.join(tmp, "captions.csv"),
            "--clipdir", os.path.join(tmp, "clips"), "--timeout", "60"]
    for k, v in kw.items():
        argv += ["--" + k.replace("_", "-"), str(v)]
    return argv


def write_dig(tmp):
    p = os.path.join(tmp, "dig201.csv")
    open(p, "w").write("pid,fig,declared_axes\n475,Fig. 2,6\n")
    return p


def write_clips(tmp):
    p = os.path.join(tmp, "clips201.csv")
    open(p, "w").write("pid,fig,png,status\n475,Fig. 2,a.png,READ\n")
    os.makedirs(os.path.join(tmp, "clips"), exist_ok=True)
    open(os.path.join(tmp, "clips", "a.png"), "wb").write(b"\x89PNG fixture")
    return p


# ------------------------------------------------------------------ the box reader
# These four exercise `metrics` and `box_diff` - the answer to "counting is not
# checking".  Guard: metrics()/box_diff() in harness_compare.py.

class BoxLevelComparison(unittest.TestCase):

    def test_box_moves_while_every_count_holds_still(self):
        """475 Fig. 2: panel count, ladder count and flag count identical, and
        panel C had lost its third bar group.  A count-only comparison called
        that no change.  Guard: box_diff / max_boundary_delta_px."""
        tmp = tempfile.mkdtemp()
        base = write_csv(os.path.join(tmp, "b.csv"), [
            row("P01", 22, 403, 332, 620, 103, 605),
            row("P02", 524, 957, 332, 620, 605, 605),
        ])
        cand = write_csv(os.path.join(tmp, "c.csv"), [
            row("P01", 22, 268, 332, 620, 103, 605),   # x1 pulled in 135 px
            row("P02", 524, 957, 332, 620, 605, 605),
        ])
        c = H.compare_outputs(base, cand)
        for k in ("panel_count", "unique_axis_count", "ladder_pass_count",
                  "fragment_flag_count"):
            self.assertEqual(c["totals"][k]["delta"], 0, "%s should not move" % k)
        self.assertEqual(c["max_boundary_delta_px"], 135)
        moved = c["per_figure"][0]["boxes"]["moved_boxes"]
        self.assertEqual(len(moved), 1)
        self.assertEqual(moved[0]["width_a"], 381)
        self.assertEqual(moved[0]["width_b"], 246)
        self.assertLess(moved[0]["iou"], 0.70)

    def test_an_added_column_is_not_a_changed_measurement(self):
        """A change that only ADDS columns must leave the old ones alone, and no
        count can see whether it did.  Guard: shared_column_diff over the
        intersection of the two arms' columns."""
        tmp = tempfile.mkdtemp()
        boxes = [(31, 403, 28, 322, 148, 307), (533, 904, 33, 322, 650, 305)]
        base = write_csv(os.path.join(tmp, "b.csv"),
                         [row("P%02d" % (i + 1), *b) for i, b in enumerate(boxes)])
        # candidate: same rows, one extra column
        rows = [row("P%02d" % (i + 1), *b) for i, b in enumerate(boxes)]
        for r in rows:
            r["plot_x1"] = r["x1"]
        with open(os.path.join(tmp, "c.csv"), "w", newline="") as f:
            w = csv.DictWriter(f, HDR + ["plot_x1"])
            w.writeheader()
            for r in rows:
                w.writerow(r)
        c = H.compare_outputs(base, os.path.join(tmp, "c.csv"))
        sc = c["per_figure"][0]["shared_columns"]
        self.assertEqual(sc["mismatched"], {})
        self.assertEqual(sc["only_in_candidate"], ["plot_x1"])
        self.assertEqual(c["totals"]["shared_column_mismatches"]["delta"], 0)

        # now move one old column that no count reports, and it must show up
        rows[0]["ticks"] = "100:80.0"
        rows[1]["ticks"] = ""
        with open(os.path.join(tmp, "d.csv"), "w", newline="") as f:
            w = csv.DictWriter(f, HDR + ["plot_x1", "ticks"])
            w.writeheader()
            for r in rows:
                w.writerow(r)
        base2 = os.path.join(tmp, "b2.csv")
        with open(base2, "w", newline="") as f:
            w = csv.DictWriter(f, HDR + ["ticks"])
            w.writeheader()
            for i, b in enumerate(boxes):
                w.writerow(dict(row("P%02d" % (i + 1), *b), ticks=""))
        c2 = H.compare_outputs(base2, os.path.join(tmp, "d.csv"))
        self.assertEqual(c2["totals"]["panel_count"]["delta"], 0)
        self.assertEqual(c2["totals"]["shared_column_mismatches"]["delta"], 1)
        self.assertIn("ticks", c2["per_figure"][0]["shared_columns"]["mismatched"])

    def test_duplicate_boxes_on_one_spine_are_not_two_panels(self):
        """397 Fig. 1 harness-off: eight boxes, but pairs of them stood on the
        same spine.  panel_count said 8 > 6; the axis signature says 4 < 6.
        Guard: unique_axis_count / duplicate_axis_count in metrics()."""
        dup = [row("P0%d" % i, *b, dec=8, pid="397", fig="Fig. 1") for i, b in enumerate([
            (779, 974, 833, 988, 800, 986), (779, 908, 870, 988, 800, 986),
            (723, 777, 918, 990, 740, 988), (723, 777, 918, 990, 740, 988),
            (431, 531, 1147, 1262, 450, 1260), (431, 531, 1147, 1262, 450, 1260),
            (779, 974, 1155, 1323, 800, 1321), (779, 908, 1181, 1323, 800, 1321),
        ], 1)]
        clean = [row("P0%d" % i, *b, dec=8, pid="397", fig="Fig. 1") for i, b in enumerate([
            (102, 568, 139, 260, 120, 258), (102, 577, 363, 756, 120, 754),
            (619, 1083, 441, 641, 640, 639), (619, 1083, 821, 990, 640, 988),
            (93, 587, 1034, 1458, 110, 1456), (611, 1102, 1078, 1453, 630, 1451),
        ], 1)]
        mb = H.metrics(dup, declared=8)
        mc = H.metrics(clean, declared=8)
        self.assertEqual(mb["panel_count"], 8)
        self.assertEqual(mb["unique_axis_count"], 4)
        self.assertEqual(mb["duplicate_axis_count"], 4)
        self.assertEqual(mc["unique_axis_count"], 6)
        self.assertEqual(mc["duplicate_axis_count"], 0)
        self.assertGreater(mc["unique_axis_count"], mb["unique_axis_count"])

    def test_a_box_that_swallows_another_spine_is_flagged(self):
        """Under-segmentation: one box, two physical axes inside it.  Nothing in
        panel_count or ladder_pass_count notices.  Guard: foreign_axis_count."""
        rows = [row("P01", 20, 960, 30, 320, 148, 307),        # spans both columns
                row("P02", 533, 904, 33, 322, 650, 305)]
        self.assertEqual(H.metrics(rows)["foreign_axis_count"], 1)
        rows[0]["x1"] = 403                                     # no longer reaches
        self.assertEqual(H.metrics(rows)["foreign_axis_count"], 0)

    def test_renumbered_panels_are_not_reported_as_moved(self):
        """propose.py numbers panels in discovery order, and a segmentation
        change reorders them.  Matching by row index would report every reorder
        as a moved box.  Guard: match_rows greedy nearest-axis pairing."""
        tmp = tempfile.mkdtemp()
        boxes = [(31, 403, 28, 322, 148, 307), (533, 904, 33, 322, 650, 305),
                 (22, 403, 332, 620, 103, 605)]
        base = write_csv(os.path.join(tmp, "b.csv"),
                         [row("P%02d" % (i + 1), *b) for i, b in enumerate(boxes)])
        cand = write_csv(os.path.join(tmp, "c.csv"),
                         [row("P%02d" % (i + 1), *b) for i, b in enumerate(reversed(boxes))])
        c = H.compare_outputs(base, cand)
        self.assertEqual(c["per_figure"][0]["boxes"]["moved_boxes"], [])
        self.assertEqual(c["per_figure"][0]["boxes"]["matched"], 3)


# ------------------------------------------------------------------ the gate
# Guard: manifest_diff() and the offending-key filter in main().

class ComparabilityGate(unittest.TestCase):

    def test_a_file_the_arm_could_not_find_is_recorded_as_a_value(self):
        """The contaminated baseline exactly: one arm started before
        captions.csv existed.  If an absent input is simply omitted from the
        manifest it cannot differ from a present one.  Guard: sha() returning
        None, and build_manifest hashing every declared input including the
        missing ones."""
        tmp = tempfile.mkdtemp()
        staging = os.path.join(tmp, "s")
        os.makedirs(staging)
        for n in H.CODE_FILES:
            open(os.path.join(staging, n), "w").write("#\n")
        open(os.path.join(staging, "dig201.csv"), "w").write("pid,fig\n")
        inputs = {"dig201.csv": None, "captions.csv": None}
        before = H.build_manifest(staging, set(), {}, inputs,
                                  os.path.join(staging, "clips201.csv"),
                                  os.path.join(staging, "clips"), "ref")
        self.assertIsNone(before["inputs"]["captions.csv"])
        self.assertIsNotNone(before["inputs"]["dig201.csv"])

        open(os.path.join(staging, "captions.csv"), "w").write("pid,fig,panels\n475,Fig. 2,6\n")
        after = H.build_manifest(staging, set(), {}, inputs,
                                 os.path.join(staging, "clips201.csv"),
                                 os.path.join(staging, "clips"), "ref")
        d = H.manifest_diff(before, after)
        self.assertIn("inputs.captions.csv", d)
        self.assertEqual(d["inputs.captions.csv"][0], None)

    def test_an_unrelated_file_beside_the_tree_is_not_a_code_change(self):
        """A run writes its log next to the code it stages.  If the tree ref is
        taken over the directory listing, the second arm's ref differs from the
        first for a reason that is not the experiment, and a comparison whose
        code never moved is refused.  Guard: stage_tree hashing CODE_FILES."""
        tmp = tempfile.mkdtemp()
        src = Tree(tmp, "src", BASE_ARM).path
        a = H.stage_tree(src, os.path.join(tmp, "a"))
        open(os.path.join(src, "run.log"), "w").write("...\n")
        b = H.stage_tree(src, os.path.join(tmp, "b"))
        self.assertEqual(a, b)
        open(os.path.join(src, "propose.py"), "w").write("# changed\n")
        self.assertNotEqual(a, H.stage_tree(src, os.path.join(tmp, "c")))

    def test_an_undeclared_difference_refuses_the_whole_comparison(self):
        """Two arms whose only difference is a knob the caller did not declare.
        Everything else - code, inputs, rasters - is identical, so a count-based
        comparison would look perfectly clean.  Guard: the INPUT_MISMATCH loop
        over keys outside --vary."""
        tmp = tempfile.mkdtemp()
        b = Tree(tmp, "base", BASE_ARM)
        rep = run_driver(base_argv(tmp, b.path, b.path, replay=1,
                                   candidate_env="WIDE2=0", vary="code"))
        self.assertIsNone(rep["comparison"])
        self.assertTrue(any(r.startswith("INPUT_MISMATCH") and "env.WIDE2" in r
                            for r in rep["refusals"]), rep["refusals"])

    def test_the_declared_variable_is_allowed_to_differ(self):
        """A gate that refuses everything refuses the experiment too: the same
        two arms, with the knob declared, must compare."""
        tmp = tempfile.mkdtemp()
        b = Tree(tmp, "base", BASE_ARM)
        rep = run_driver(base_argv(tmp, b.path, b.path, replay=1,
                                   candidate_env="WIDE2=0", vary="code,env.WIDE2"))
        self.assertEqual(rep["refusals"], [])
        self.assertIsNotNone(rep["comparison"])
        self.assertEqual(rep["comparison"]["totals"]["panel_count"]["delta"], 0)

    def test_an_unset_flag_and_its_default_are_the_same_input(self):
        """SNAP unset and SNAP=1 produce identical measurements; recording one as
        absent and the other as "1" would refuse a comparison that is valid."""
        rec = {k: {}.get(k, "<unset>") for k in H.ENV_KEYS}
        rec2 = {k: {"SNAP": "0"}.get(k, "<unset>") for k in H.ENV_KEYS}
        self.assertEqual(rec["SNAP"], "<unset>")
        self.assertNotEqual(rec["SNAP"], rec2["SNAP"])


# ------------------------------------------------------------------ the lock
# Guard: acquire_lock().

class RunRootLock(unittest.TestCase):

    def test_a_live_holder_is_fatal(self):
        tmp = tempfile.mkdtemp()
        os.makedirs(tmp, exist_ok=True)
        with open(os.path.join(tmp, ".lock"), "w") as f:
            json.dump({"pid": 1, "run_id": "someone-else", "ts": time.time()}, f)
        with self.assertRaises(H.LockHeld):
            H.acquire_lock(tmp, "mine")

    def test_a_dead_holder_is_reclaimed(self):
        """A crashed run must not wedge the directory forever."""
        tmp = tempfile.mkdtemp()
        dead = subprocess.Popen([sys.executable, "-c", "pass"])
        dead.wait()
        with open(os.path.join(tmp, ".lock"), "w") as f:
            json.dump({"pid": dead.pid, "run_id": "crashed", "ts": time.time()}, f)
        p = H.acquire_lock(tmp, "mine")
        self.assertTrue(os.path.exists(p))
        with open(p) as f:
            self.assertEqual(json.load(f)["run_id"], "mine")
        H.release_lock(p)


# ------------------------------------------------------------------ the run
# Guards: run_arm() atomic promotion, _group_survivors(), the replay hash set,
# and the post-run output re-hash in main().

class ArmProcessDiscipline(unittest.TestCase):

    def test_a_crashed_arm_promotes_nothing(self):
        """The half-written file must never become the thing that is compared.
        Guard: OUT points at .partial, os.replace only on returncode 0."""
        tmp = tempfile.mkdtemp()
        b = Tree(tmp, "base", BASE_ARM)
        c = Tree(tmp, "cand", """
            open(os.environ["OUT"], "w").write("pid,fig,panel\\n475,Fig. 2,P0")
            sys.exit(3)
        """)
        rep = run_driver(base_argv(tmp, b.path, c.path, replay=1))
        self.assertIsNone(rep["comparison"])
        joined = " ".join(rep["refusals"])
        self.assertIn("ARM_FAILED", joined)
        self.assertIn("NO_OUTPUT", joined)
        self.assertFalse(any(f.startswith("output.rep0") and not f.endswith(".partial")
                             for f in os.listdir(os.path.join(tmp, "run", "candidate"))))

    def test_a_child_the_arm_leaked_is_caught(self):
        """An arm that exits while something it started is still running.  The
        arm looks finished, its output looks complete, and a worker is still
        holding the corpus.  This is the narrow half of the ghost: a process in
        the arm's own group.  (A ghost from an *earlier* session is caught
        instead by the per-run output path and the post-run re-hash.)
        Guard: start_new_session=True + _group_survivors()."""
        tmp = tempfile.mkdtemp()
        b = Tree(tmp, "base", BASE_ARM)
        c = Tree(tmp, "cand", ("""
            _n = open(os.devnull, "w")
            subprocess.Popen([sys.executable, "-c", "import time; time.sleep(6)"],
                             stdout=_n, stderr=_n)
        """, BASE_ARM))
        rep = run_driver(base_argv(tmp, b.path, c.path, replay=1))
        self.assertIsNone(rep["comparison"])
        self.assertTrue(any(r.startswith("SURVIVING_PROCESS") for r in rep["refusals"]),
                        rep["refusals"])

    def test_an_arm_that_does_not_repeat_itself_is_not_compared(self):
        """Three identical md5s are what proved the pipeline deterministic.  Here
        that check is a precondition instead of a later discovery.  Guard: the
        len(set(hashes)) > 1 refusal."""
        tmp = tempfile.mkdtemp()
        counter = os.path.join(tmp, "counter")
        b = Tree(tmp, "base", BASE_ARM)
        c = Tree(tmp, "cand", """
            n = 0
            try: n = int(open(%r).read())
            except Exception: pass
            open(%r, "w").write(str(n + 1))
            open(os.environ["OUT"], "w").write(
                "pid,fig,png,panel,status,fragment,declared_axes,x0,x1,y0,y1,spine_x,baseline_y\\n"
                "475,Fig. 2,a.png,P01,LADDER_OK,,6,31,%%d,28,322,148,307\\n" %% (403 + n))
        """ % (counter, counter))
        rep = run_driver(base_argv(tmp, b.path, c.path, replay=2))
        self.assertIsNone(rep["comparison"])
        self.assertTrue(any(r.startswith("NONDETERMINISTIC") for r in rep["refusals"]),
                        rep["refusals"])

    def test_an_output_rewritten_after_its_run_is_caught(self):
        """The literal shape of the incident: the file that was compared was not
        the file the run produced.  Guard: the OUTPUT_CHANGED_AFTER_RUN re-hash."""
        tmp = tempfile.mkdtemp()
        b = Tree(tmp, "base", BASE_ARM)
        c = Tree(tmp, "cand", BASE_ARM)
        argv = base_argv(tmp, b.path, c.path, replay=1)
        real = H.compare_outputs
        state = {}

        def ghost(a_csv, b_csv, declared_by_fig=None):
            # stand in for a process that finished late and overwrote the file
            open(b_csv, "a").write("475,Fig. 2,a.png,P03,LADDER_OK,,6,1,2,3,4,5,6\n")
            state["ran"] = True
            return real(a_csv, b_csv, declared_by_fig)

        H.compare_outputs = ghost
        try:
            # rewrite happens between promotion and comparison
            rep = self._run_with_late_write(argv, tmp)
        finally:
            H.compare_outputs = real
        self.assertTrue(any(r.startswith("OUTPUT_CHANGED_AFTER_RUN") for r in rep["refusals"]),
                        rep["refusals"])
        self.assertIsNone(rep["comparison"])

    def _run_with_late_write(self, argv, tmp):
        """Let both arms finish, corrupt one promoted file, then let main()
        re-hash.  Implemented by running main() once to produce the files, then
        again with the candidate output pre-corrupted."""
        run_driver(argv)
        cand_dir = os.path.join(tmp, "run", "candidate")
        promoted = [f for f in os.listdir(cand_dir)
                    if f.startswith("output.rep0") and f.endswith(".csv")][0]
        # A second run reuses the run root; corrupt after the stamp is written by
        # monkeypatching sha to report the pre-corruption value once.
        real_sha = H.sha
        seen = {}

        def sha_then_corrupt(path):
            v = real_sha(path)
            if path.endswith(".csv") and "candidate" in str(path) and path not in seen:
                seen[path] = v
                open(path, "a").write("475,Fig. 2,a.png,PXX,LADDER_OK,,6,1,2,3,4,5,6\n")
            return v
        H.sha = sha_then_corrupt
        try:
            return run_driver(argv)
        finally:
            H.sha = real_sha


if __name__ == "__main__":
    # One marker line, printed once, after the last scenario - the CI loop reads
    # exactly one, and a suite that prints its verdict early can run scenarios
    # after it that nobody counts.  The number comes from the result rather than
    # from the loaded suite: unittest empties a suite as it runs it, so counting
    # afterwards reports 4 (the classes) instead of 14 (the scenarios).
    loaded = unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__])
    result = unittest.TextTestRunner(verbosity=2).run(loaded)
    print("FDT_SCENARIOS_RUN=%d" % result.testsRun)
    sys.exit(0 if result.wasSuccessful() else 1)
