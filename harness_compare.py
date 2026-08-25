#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Run two arms of a segmentation experiment so the comparison can be trusted.

The runtime harness (axis_reader / continuity / propose) decides where panels
are.  THIS file decides nothing about panels.  Its only job is to make an A/B
comparison of two code states honest, because one of them was not:

    a run that started before `captions.csv` existed survived the `pkill` that
    was meant to end it, finished after its replacement, and overwrote the
    shared output path.  A change that touches one reporting column appeared to
    move panel counts.  Three re-runs of the same command were byte-identical,
    which is what proved the pipeline deterministic and the baseline a ghost.

Every guard below exists because of one clause of that sentence:

    started before captions.csv existed  -> the input manifest, and the
                                            comparability gate that refuses to
                                            compare arms whose inputs differ
    survived the pkill                   -> the process group check, which
                                            catches a child THIS run leaked.  A
                                            ghost from an earlier session is
                                            outside our group and is caught by
                                            the next line instead.
    overwrote the shared output path     -> per-run output paths, atomic
                                            promotion, and the post-run hash
                                            re-verification.  A writer that no
                                            longer knows where the output lives
                                            cannot corrupt it, and one that
                                            somehow does is caught by the hash.
    three re-runs were identical         -> --replay, which makes that check a
                                            precondition instead of a discovery

It reports counters and box-level deltas.  It does not say which arm is
correct: that is an attestation, and attestations are human-only (PILOT.md).
Every verdict field it writes is DEMO_ONLY.
"""
import argparse, csv, hashlib, json, os, shutil, signal, subprocess, sys, tempfile, time

SCHEMA = 1
DEMO_ONLY = "DEMO_ONLY"

# The code the arms differ in.  Hashed individually so a diff report can name
# the file that moved rather than saying "the tree changed".
# THE FILES AN ARM CAN DIFFER IN. `gate_trace.py` is here even though it decides
# nothing: it is what turns a run into a conclusion, so a change to it that moves
# a reported number must move the arm's code reference too.
CODE_FILES = ("axis_reader.py", "continuity.py", "propose.py", "x_reader.py",
              "caption.py", "panel_geometry.py", "gate_trace.py")

# Every knob that can change a measurement.  A key absent from the environment
# is recorded as its default, not omitted, so that "unset" and "set to the
# default" compare equal and "unset" and "set to 0" do not.
ENV_KEYS = ("SNAP", "CAP", "BROAD", "WIDE", "WIDE2", "SELFGAP", "MARKFRAG",
            "REINK", "NEAR", "FIGS", "DIG", "CLIPS", "CAPS")

# THE OBSERVATION FLAGS, RECORDED AS WHETHER THEY WERE ON. `TRACE` names a file,
# so stamping its value would make two arms differ because they wrote to different
# paths - which is not the experiment. What matters is whether the arm was
# observed at all, because a shadow measurement is made of observation.
DERIVED_ENV = {
    "TRACE_ENABLED": lambda e: e.get("TRACE", "") not in ("", "0"),
    "SHADOW_ENABLED": lambda e: e.get("SHADOW", "0") != "0",
    "SHADOW_GATE_ENABLED": lambda e: e.get("SHADOWGATE", "0") != "0",
}

# Two boxes from different arms are the same physical axis if their spine and
# baseline agree to within this.  Not a tuning knob for panel finding - it is
# how far a box may move and still be recognised as the same box.
SAME_AXIS_PX = 12


# ---------------------------------------------------------------- hashing

def sha(path):
    if not os.path.exists(path):
        return None
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def sha_text(s):
    return hashlib.sha256(s.encode()).hexdigest()


# ---------------------------------------------------------------- locking

class LockHeld(Exception):
    pass


def _alive(pid):
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def acquire_lock(root, run_id):
    """One comparison per run root at a time.

    A lock whose holder is gone is reclaimed - a crashed run must not wedge the
    directory forever - but a lock whose holder is alive is fatal, because the
    whole point is that two runs never share an output path again.
    """
    os.makedirs(root, exist_ok=True)
    path = os.path.join(root, ".lock")
    payload = json.dumps({"pid": os.getpid(), "run_id": run_id, "ts": time.time()})
    while True:
        try:
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
            os.write(fd, payload.encode())
            os.close(fd)
            return path
        except FileExistsError:
            try:
                with open(path) as f:
                    held = json.load(f)
            except Exception:
                held = {}
            pid = held.get("pid")
            if isinstance(pid, int) and _alive(pid) and pid != os.getpid():
                raise LockHeld("run root %s is locked by live pid %d (run %s)"
                               % (root, pid, held.get("run_id")))
            os.unlink(path)          # stale: holder is gone


def assert_lock_still_ours(path, run_id):
    """The lock is inside the run root, so anything that deletes the root deletes
    the lock - and then a second run walks straight in.

    That happened: an `rm -rf` of the run root between a kill and a relaunch left
    two comparisons interleaving in one directory, and the first one to reach the
    candidate arm removed the other's staging out from under it. The tool exists
    to stop exactly that, and it could not see it, because the thing it checks had
    been deleted along with everything else.
    """
    try:
        with open(path) as f:
            held = json.load(f)
    except Exception:
        raise LockHeld("the lock file %s is gone - the run root was deleted or "
                       "another run took it while this one was working" % path)
    if held.get("run_id") != run_id:
        raise LockHeld("the lock at %s now belongs to run %s, not %s"
                       % (path, held.get("run_id"), run_id))


def release_lock(path):
    try:
        os.unlink(path)
    except FileNotFoundError:
        pass


# ---------------------------------------------------------------- staging

def stage_tree(ref, dest, repo=None):
    """Materialise one arm's code into its own directory.

    `ref` is a git ref when a repo is given, otherwise a directory to copy.
    Either way the arm runs from a private copy: an arm must never be able to
    read a file another arm is writing.
    """
    os.makedirs(dest, exist_ok=True)
    if repo:
        tar = subprocess.run(["git", "-C", repo, "archive", "--format=tar", ref],
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if tar.returncode:
            raise RuntimeError("git archive %s failed: %s" % (ref, tar.stderr.decode()[:400]))
        p = subprocess.run(["tar", "-x", "-C", dest], input=tar.stdout,
                           stderr=subprocess.PIPE)
        if p.returncode:
            raise RuntimeError("tar failed: %s" % p.stderr.decode()[:400])
        head = subprocess.run(["git", "-C", repo, "rev-parse", ref],
                              stdout=subprocess.PIPE).stdout.decode().strip()
        return head
    for name in os.listdir(ref):
        src = os.path.join(ref, name)
        if os.path.isfile(src):
            shutil.copy2(src, os.path.join(dest, name))
    # The ref of a plain directory is taken over the CODE FILES only, not over
    # everything the directory happens to hold.  Taken over the listing, a log
    # file growing beside the tree makes two stagings of the SAME directory
    # differ, and the gate then refuses a comparison whose code never moved -
    # which is the "refuses everything" failure in its quietest form.
    return "tree:" + sha_text("".join(
        n + (sha(os.path.join(ref, n)) or "-") for n in CODE_FILES))


def link_inputs(inputs, dest):
    """Give the arm the corpus tables and rasters, by copy or symlink."""
    for name, src in inputs.items():
        if src is None:
            continue
        tgt = os.path.join(dest, name)
        if os.path.exists(tgt) or os.path.islink(tgt):
            os.remove(tgt)
        if os.path.isdir(src):
            os.symlink(os.path.abspath(src), tgt)
        else:
            shutil.copy2(src, tgt)


# ---------------------------------------------------------------- manifest

def raster_hashes(clips_csv, figures, clipdir):
    """Hash exactly the rasters this comparison will read.

    Hashing the whole clip directory would make every unrelated file a reason
    to refuse; hashing none of them would let a re-cropped figure pass as the
    same input.
    """
    out = {}
    if not (clips_csv and os.path.exists(clips_csv)):
        return out
    for r in csv.DictReader(open(clips_csv)):
        if figures and (r.get("pid"), r.get("fig")) not in figures:
            continue
        png = r.get("png")
        if png:
            out[png] = sha(os.path.join(clipdir, png))
    return out


def build_manifest(staging, figures, env, inputs, clips_path, clipdir, code_ref):
    """What this arm actually read, hashed.

    `inputs` is name -> source path; the hashes are taken from the arm's own
    staged copy, not from the source, because the copy is what it read.  A file
    the arm expected and did not find hashes to None, which is how "captions.csv
    did not exist yet" becomes a value that can differ instead of a silence.
    """
    return {
        "schema": SCHEMA,
        "code": dict({n: sha(os.path.join(staging, n)) for n in CODE_FILES},
                     ref=code_ref),
        "inputs": {n: sha(os.path.join(staging, n)) for n in sorted(inputs)},
        "rasters": raster_hashes(clips_path, figures, clipdir),
        "env": dict({k: env.get(k, "<unset>") for k in ENV_KEYS},
                    **{k: fn(env) for k, fn in sorted(DERIVED_ENV.items())}),
        "interpreter": {
            "python": sys.version.split()[0],
            "pillow": _ver("PIL"),
            "numpy": _ver("numpy"),
        },
        "figures": sorted("|".join(f) for f in figures) if figures else [],
    }


def _ver(mod):
    try:
        m = __import__(mod)
        return getattr(m, "__version__", "?")
    except Exception:
        return "absent"


def manifest_diff(a, b):
    """Flatten both manifests and return every key whose value differs.

    Deliberately total: the caller declares which differences are the
    experiment, and anything else it finds is a reason to refuse.  The
    contaminated baseline differed at inputs.captions.csv - one arm read a file
    that did not yet exist - and that is the key this would have printed.
    """
    def flat(d, pre=""):
        out = {}
        for k, v in d.items():
            key = pre + k
            if isinstance(v, dict):
                out.update(flat(v, key + "."))
            else:
                out[key] = v
        return out
    fa, fb = flat(a), flat(b)
    keys = set(fa) | set(fb)
    return {k: (fa.get(k, "<missing>"), fb.get(k, "<missing>"))
            for k in sorted(keys) if fa.get(k, "<missing>") != fb.get(k, "<missing>")}


# ---------------------------------------------------------------- running

def run_arm(arm, staging, out_path, env, cmd, timeout):
    """Run one arm in its own process group, write to a path no one else knows.

    `start_new_session=True` is not tidiness.  It is what makes the survivor
    check possible: after the arm exits, anything still alive in its group is a
    process that outlived its parent, which is exactly the failure this file
    exists to prevent.
    """
    partial = out_path + ".partial"
    for p in (out_path, partial):
        if os.path.exists(p):
            os.remove(p)
    e = dict(os.environ)
    e.update({k: v for k, v in env.items() if v is not None})
    e["OUT"] = partial
    t0 = time.time()
    proc = subprocess.Popen(cmd, cwd=staging, env=e, start_new_session=True,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        so, se = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        os.killpg(proc.pid, signal.SIGKILL)
        so, se = proc.communicate()
        return {"arm": arm, "returncode": -9, "timeout": True, "stderr": "timeout"}
    t1 = time.time()

    survivors = _group_survivors(proc.pid)

    promoted = False
    if proc.returncode == 0 and os.path.exists(partial):
        os.replace(partial, out_path)     # atomic: a reader sees old or new, never half
        promoted = True

    return {
        "arm": arm,
        "run_pid": proc.pid,
        "returncode": proc.returncode,
        "started": t0, "finished": t1, "seconds": round(t1 - t0, 2),
        "survivors": survivors,
        "promoted": promoted,
        "out_path": out_path,
        "out_sha": sha(out_path) if promoted else None,
        "stdout_tail": so.decode(errors="replace")[-2000:],
        "stderr_tail": se.decode(errors="replace")[-2000:],
        "cmd": cmd,
    }


def _group_survivors(pgid, grace=1.5):
    """Members of the arm's process group still alive after it exited."""
    deadline = time.time() + grace
    while time.time() < deadline:
        try:
            os.killpg(pgid, 0)
        except ProcessLookupError:
            return []
        except PermissionError:
            break
        time.sleep(0.1)
    return _pids_in_group(pgid)


def _pids_in_group(pgid):
    """Members of a process group, by whatever the platform offers.

    /proc first because it needs no subprocess; `ps` second because macOS has
    no /proc and a check that silently raises there is a check the person
    running the suite on their laptop cannot use.
    """
    me = os.getpid()
    if os.path.isdir("/proc"):
        out = []
        for pid in os.listdir("/proc"):
            if not pid.isdigit():
                continue
            try:
                if os.getpgid(int(pid)) == pgid and int(pid) != me:
                    out.append(int(pid))
            except Exception:
                pass
        return out
    try:
        ps = subprocess.run(["ps", "-A", "-o", "pid=,pgid="],
                            stdout=subprocess.PIPE, timeout=10)
    except Exception:
        return []
    out = []
    for line in ps.stdout.decode(errors="replace").splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
            if int(parts[1]) == pgid and int(parts[0]) != me:
                out.append(int(parts[0]))
    return out


# ---------------------------------------------------------------- rows

def load_rows(path):
    with open(path) as f:
        rows = [r for r in csv.DictReader(f) if r.get("panel")]
    for r in rows:
        for k in ("x0", "x1", "y0", "y1", "spine_x", "baseline_y"):
            v = r.get(k)
            r[k] = float(v) if v not in (None, "") else None
    return rows


def axis_key(r):
    """A panel's physical identity: where its spine stands and where its data sit.

    Not the box.  A box that shrinks is the same axis measured worse; two boxes
    on one spine are one axis segmented twice.  Counting boxes cannot tell those
    apart, which is how eight fragments once read as eight panels.
    """
    if r["spine_x"] is None or r["baseline_y"] is None:
        return None
    return (r["spine_x"], r["baseline_y"])


def _bucket(r):
    if axis_key(r) is None:
        return None
    return (round(r["spine_x"] / SAME_AXIS_PX), round(r["baseline_y"] / SAME_AXIS_PX))


def metrics(rows, declared=None):
    keyed = [r for r in rows if axis_key(r) is not None]
    buckets = {}
    for r in keyed:
        buckets.setdefault(_bucket(r), []).append(r)
    dup = sum(len(v) - 1 for v in buckets.values())

    foreign = 0
    for r in rows:
        if r["x0"] is None:
            continue
        for o in keyed:
            if o is r or o["spine_x"] is None:
                continue
            inside_x = r["x0"] + 2 < o["spine_x"] < r["x1"] - 2
            overlap = not (o["y1"] < r["y0"] or o["y0"] > r["y1"])
            if inside_x and overlap and _bucket(o) != _bucket(r):
                foreign += 1
                break

    area = sum((r["x1"] - r["x0"]) * (r["y1"] - r["y0"])
               for r in rows if r["x0"] is not None)
    m = {
        "panel_count": len(rows),
        "unique_axis_count": len(buckets),
        "duplicate_axis_count": dup,
        "ladder_pass_count": sum(1 for r in rows if r.get("status") == "LADDER_OK"),
        "fragment_flag_count": sum(1 for r in rows if r.get("fragment")),
        "foreign_axis_count": foreign,
        "boxed_area_px": int(area),
    }
    if declared is not None:
        m["declared"] = declared
        m["count_equals_declared"] = (len(rows) == declared)
        m["unique_axes_equals_declared"] = (len(buckets) == declared)
    return m


def match_rows(a, b):
    """Pair boxes across arms by the axis they stand on, nearest first.

    Greedy on distance rather than by row order: propose.py numbers panels in
    the order it finds them, and a segmentation change reorders them.  Matching
    P03 to P03 would report every reorder as a moved box.
    """
    pairs, used = [], set()
    cand = []
    for i, ra in enumerate(a):
        if axis_key(ra) is None:
            continue
        for j, rb in enumerate(b):
            if axis_key(rb) is None:
                continue
            d = max(abs(ra["spine_x"] - rb["spine_x"]), abs(ra["baseline_y"] - rb["baseline_y"]))
            if d <= SAME_AXIS_PX:
                cand.append((d, i, j))
    for d, i, j in sorted(cand):
        if ("a", i) in used or ("b", j) in used:
            continue
        used.add(("a", i)); used.add(("b", j))
        pairs.append((a[i], b[j], d))
    dropped = [a[i] for i in range(len(a)) if ("a", i) not in used]
    added = [b[j] for j in range(len(b)) if ("b", j) not in used]
    return pairs, dropped, added


def shared_column_diff(pairs):
    """For matched axes, every column BOTH arms wrote, and where they disagree.

    A change that only adds columns must leave the old ones alone, and there is
    no way to see that in a count.  Comparing the intersection turns "additive"
    into a number that can be zero: any old column that moved shows up here with
    the axis it moved on.
    """
    cols, examples = {}, []
    compared = set()
    for ra, rb, _d in pairs:
        shared = set(ra) & set(rb)
        compared |= shared
        for k in sorted(shared):
            if ra[k] != rb[k]:
                cols[k] = cols.get(k, 0) + 1
                if len(examples) < 12:
                    examples.append({"column": k, "axis": [ra["spine_x"], ra["baseline_y"]],
                                     "base": ra[k], "candidate": rb[k]})
    return {"columns_compared": len(compared), "mismatched": cols, "examples": examples,
            "only_in_base": [], "only_in_candidate": []}


def box_diff(a_rows, b_rows):
    pairs, dropped, added = match_rows(a_rows, b_rows)
    moved = []
    for ra, rb, d in pairs:
        if None in (ra["x0"], rb["x0"]):
            continue
        delta = {"dx0": rb["x0"] - ra["x0"], "dx1": rb["x1"] - ra["x1"],
                 "dy0": rb["y0"] - ra["y0"], "dy1": rb["y1"] - ra["y1"]}
        worst = max(abs(v) for v in delta.values())
        if worst == 0:
            continue
        ix0, ix1 = max(ra["x0"], rb["x0"]), min(ra["x1"], rb["x1"])
        iy0, iy1 = max(ra["y0"], rb["y0"]), min(ra["y1"], rb["y1"])
        inter = max(0.0, ix1 - ix0) * max(0.0, iy1 - iy0)
        union = ((ra["x1"] - ra["x0"]) * (ra["y1"] - ra["y0"])
                 + (rb["x1"] - rb["x0"]) * (rb["y1"] - rb["y0"]) - inter)
        moved.append({
            "axis": [ra["spine_x"], ra["baseline_y"]],
            "panel_a": ra.get("panel"), "panel_b": rb.get("panel"),
            "box_a": [ra["x0"], ra["x1"], ra["y0"], ra["y1"]],
            "box_b": [rb["x0"], rb["x1"], rb["y0"], rb["y1"]],
            "delta": delta,
            "max_boundary_delta_px": worst,
            "iou": round(inter / union, 4) if union else 0.0,
            "width_a": ra["x1"] - ra["x0"], "width_b": rb["x1"] - rb["x0"],
            "status_a": ra.get("status"), "status_b": rb.get("status"),
        })
    moved.sort(key=lambda m: -m["max_boundary_delta_px"])
    return {
        "matched": len(pairs),
        "moved_boxes": moved,
        "max_boundary_delta_px": max([m["max_boundary_delta_px"] for m in moved], default=0),
        "min_iou": min([m["iou"] for m in moved], default=1.0),
        "dropped_axes": [[r.get("panel"), r["spine_x"], r["baseline_y"]] for r in dropped],
        "added_axes": [[r.get("panel"), r["spine_x"], r["baseline_y"]] for r in added],
    }


def compare_outputs(a_csv, b_csv, declared_by_fig=None):
    A, B = load_rows(a_csv), load_rows(b_csv)
    figs = sorted({(r["pid"], r["fig"]) for r in A} | {(r["pid"], r["fig"]) for r in B})
    per = []
    for pid, fig in figs:
        ra = [r for r in A if (r["pid"], r["fig"]) == (pid, fig)]
        rb = [r for r in B if (r["pid"], r["fig"]) == (pid, fig)]
        dec = (declared_by_fig or {}).get((pid, fig))
        if dec is None and ra:
            dec = _int(ra[0].get("declared_axes"))
        if dec is None and rb:
            dec = _int(rb[0].get("declared_axes"))
        pairs, _dropped, _added = match_rows(ra, rb)
        shared = shared_column_diff(pairs)
        shared["only_in_base"] = sorted(set().union(*[set(r) for r in ra]) -
                                        set().union(*[set(r) for r in rb])) if ra and rb else []
        shared["only_in_candidate"] = sorted(set().union(*[set(r) for r in rb]) -
                                             set().union(*[set(r) for r in ra])) if ra and rb else []
        per.append({
            "pid": pid, "fig": fig, "declared": dec,
            "base": metrics(ra, dec), "candidate": metrics(rb, dec),
            "boxes": box_diff(ra, rb),
            "shared_columns": shared,
        })
    keys = ("panel_count", "unique_axis_count", "duplicate_axis_count",
            "ladder_pass_count", "fragment_flag_count", "foreign_axis_count")
    totals = {k: {"base": sum(p["base"][k] for p in per),
                  "candidate": sum(p["candidate"][k] for p in per)} for k in keys}
    for k in totals:
        totals[k]["delta"] = totals[k]["candidate"] - totals[k]["base"]
    totals["boxes_moved"] = {"base": None, "candidate": None,
                             "delta": sum(len(p["boxes"]["moved_boxes"]) for p in per)}
    totals["shared_column_mismatches"] = {
        "base": None, "candidate": None,
        "delta": sum(sum(p["shared_columns"]["mismatched"].values()) for p in per)}
    return {"per_figure": per, "totals": totals,
            "max_boundary_delta_px": max([p["boxes"]["max_boundary_delta_px"] for p in per],
                                         default=0)}


def _int(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------- driver

def parse_figures(spec):
    if not spec:
        return set()
    return {tuple(t.split("|")) for t in spec.split(";") if t.strip()}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--base-ref", required=True, help="git ref, or a directory when --repo is absent")
    ap.add_argument("--candidate-ref", required=True)
    ap.add_argument("--repo", default=None, help="git repo the refs live in")
    ap.add_argument("--figures", default="", help='"pid|fig;pid|fig"')
    ap.add_argument("--out", required=True, help="run root")
    ap.add_argument("--dig", default="dig201.csv")
    ap.add_argument("--clips", default="clips201.csv")
    ap.add_argument("--caps", default="captions.csv")
    ap.add_argument("--clipdir", default="clips")
    ap.add_argument("--base-env", default="", help="K=V,K=V applied to the base arm only")
    ap.add_argument("--candidate-env", default="", help="K=V,K=V applied to the candidate arm only")
    ap.add_argument("--vary", default="code",
                    help="comma list of manifest key prefixes allowed to differ, e.g. code,env.WIDE2")
    ap.add_argument("--replay", type=int, default=2,
                    help="times to run each arm; >1 requires byte-identical output")
    ap.add_argument("--cmd", default="python3 propose.py")
    ap.add_argument("--timeout", type=int, default=14400)
    ap.add_argument("--record", default=None,
                    help="write experiments/<ID>.json and <ID>_boxes.csv beside this "
                         "repository, so a rejected approach can be re-checked "
                         "mechanically instead of re-read as prose")
    a = ap.parse_args(argv)

    figures = parse_figures(a.figures)
    run_id = "%s-%d" % (time.strftime("%Y%m%dT%H%M%S"), os.getpid())
    root = os.path.abspath(a.out)
    lock = acquire_lock(root, run_id)
    report = {"schema": SCHEMA, "run_id": run_id, "verdict": DEMO_ONLY, "refusals": []}
    try:
        arms = {}
        for arm, ref, extra in (("baseline", a.base_ref, a.base_env),
                                ("candidate", a.candidate_ref, a.candidate_env)):
            arm_root = os.path.join(root, arm)
            shutil.rmtree(arm_root, ignore_errors=True)
            os.makedirs(arm_root)
            env = {"DIG": os.path.basename(a.dig), "CLIPS": os.path.basename(a.clips),
                   "CAPS": os.path.basename(a.caps)}
            if a.figures:
                env["FIGS"] = a.figures
            for kv in [t for t in extra.split(",") if t.strip()]:
                k, _, v = kv.partition("=")
                env[k.strip()] = v.strip()

            hashes, stamps = [], []
            for rep in range(max(1, a.replay)):
                staging = os.path.join(arm_root, "rep%d" % rep)
                code_ref = stage_tree(ref, staging, a.repo)
                link_inputs({os.path.basename(a.dig): a.dig,
                             os.path.basename(a.clips): a.clips,
                             os.path.basename(a.caps): a.caps if os.path.exists(a.caps) else None,
                             os.path.basename(a.clipdir): a.clipdir}, staging)
                out_path = os.path.join(arm_root, "output.rep%d.%s.csv" % (rep, run_id))
                st = run_arm(arm, staging, out_path, env, a.cmd.split(), a.timeout)
                st["replicate"] = rep
                stamps.append(st)
                hashes.append(st["out_sha"])
                if rep == 0:
                    man = build_manifest(
                        staging, figures, env,
                        {os.path.basename(a.dig): a.dig,
                         os.path.basename(a.clips): a.clips,
                         os.path.basename(a.caps): a.caps},
                        os.path.join(staging, os.path.basename(a.clips)),
                        os.path.join(staging, os.path.basename(a.clipdir)),
                        code_ref)
                    json.dump(man, open(os.path.join(arm_root, "input_manifest.json"), "w"),
                              indent=2, sort_keys=True)

            assert_lock_still_ours(lock, run_id)
            arms[arm] = {"manifest": man, "stamps": stamps, "hashes": hashes,
                         "output": stamps[0]["out_path"]}
            json.dump(stamps, open(os.path.join(arm_root, "run_stamp.json"), "w"), indent=2)

            for st in stamps:
                if st["returncode"] != 0:
                    report["refusals"].append("ARM_FAILED: %s rep%d rc=%s %s"
                                              % (arm, st["replicate"], st["returncode"],
                                                 st.get("stderr_tail", "")[-300:]))
                if st.get("survivors"):
                    report["refusals"].append("SURVIVING_PROCESS: %s rep%d left pids %s alive"
                                              % (arm, st["replicate"], st["survivors"]))
                if not st["promoted"]:
                    report["refusals"].append("NO_OUTPUT: %s rep%d never promoted a complete file"
                                              % (arm, st["replicate"]))
            if len(set(hashes)) > 1:
                report["refusals"].append(
                    "NONDETERMINISTIC: %s produced %d distinct outputs over %d replays: %s"
                    % (arm, len(set(hashes)), len(hashes), hashes))

        # the gate the contaminated baseline would have hit
        allowed = tuple(t.strip() for t in a.vary.split(",") if t.strip())
        diff = manifest_diff(arms["baseline"]["manifest"], arms["candidate"]["manifest"])
        offending = {k: v for k, v in diff.items()
                     if not any(k == p or k.startswith(p + ".") for p in allowed)}
        report["manifest_diff"] = diff
        report["declared_variables"] = list(allowed)
        for k, (x, y) in offending.items():
            report["refusals"].append("INPUT_MISMATCH: %s  base=%s  candidate=%s" % (k, x, y))

        # the guard against a writer that outlives its run
        for arm in arms:
            now = sha(arms[arm]["output"])
            if now != arms[arm]["stamps"][0]["out_sha"]:
                report["refusals"].append(
                    "OUTPUT_CHANGED_AFTER_RUN: %s output was rewritten after its process exited "
                    "(recorded %s, now %s)" % (arm, arms[arm]["stamps"][0]["out_sha"], now))

        # A FACT THAT SEPARATES TWO VERY DIFFERENT RESULTS. An arm whose output is
        # byte-identical to the base's changed NOTHING - and "the flag was
        # evaluated and agreed" and "the flag never reached the code it gates"
        # look the same from here. `VERT` was reported as no effect twice before
        # the second reading turned out to be a gate of mine that was shut.
        # Telling those apart needs counters from inside the tree under test:
        # candidates discovered, offered, and where each was refused. This line
        # is the half that can be measured from outside.
        report["outputs_identical"] = (arms["baseline"]["hashes"][0]
                                       == arms["candidate"]["hashes"][0])
        if report["refusals"]:
            report["comparison"] = None
        else:
            report["comparison"] = compare_outputs(arms["baseline"]["output"],
                                                   arms["candidate"]["output"])
        report["arms"] = {k: {"code_ref": v["manifest"]["code"]["ref"],
                              "output": v["output"], "hashes": v["hashes"]}
                          for k, v in arms.items()}
    finally:
        release_lock(lock)

    path = os.path.join(root, "comparison.json")
    with open(path, "w") as f:
        json.dump(report, f, indent=2, sort_keys=False)
    print(render(report))
    print("\nwritten: %s" % path)
    if a.record:
        for p in write_record(a.record, report):
            print("recorded: %s" % p)
    return 2 if report["refusals"] else 0


def write_record(record_id, report):
    """The experiment as data, next to the prose that interprets it.

    Everything here is derivable from a run root, and every run root so far has
    been thrown away with the container it ran in - which left four rejected
    approaches documented only as sentences. A sentence has to be re-read and
    believed; a row can be re-checked. NO RASTER GOES IN: the figures are
    publisher material, so what is kept is hashes, flags, metrics and boxes.
    """
    out_dir = os.path.join("experiments")
    os.makedirs(out_dir, exist_ok=True)
    doc = {
        "experiment_id": record_id,
        "schema": SCHEMA,
        "run_id": report.get("run_id"),
        "verdict": report.get("verdict"),
        "refusals": report.get("refusals", []),
        "outputs_identical": report.get("outputs_identical"),
        "declared_variables": report.get("declared_variables", []),
        "manifest_diff": report.get("manifest_diff", {}),
        "arms": report.get("arms", {}),
        "totals": (report.get("comparison") or {}).get("totals"),
        "per_figure": [
            {k: p[k] for k in ("pid", "fig", "declared", "base", "candidate")}
            for p in (report.get("comparison") or {}).get("per_figure", [])
        ],
    }
    jpath = os.path.join(out_dir, "%s.json" % record_id)
    with open(jpath, "w") as f:
        json.dump(doc, f, indent=2, sort_keys=True)
    written = [jpath]

    cpath = os.path.join(out_dir, "%s_boxes.csv" % record_id)
    cols = ["pid", "fig", "declared", "kind", "panel_base", "panel_candidate",
            "spine_x", "baseline_y", "base_x0", "base_x1", "base_y0", "base_y1",
            "cand_x0", "cand_x1", "cand_y0", "cand_y1", "width_base",
            "width_candidate", "max_boundary_delta_px", "iou",
            "status_base", "status_candidate"]
    with open(cpath, "w", newline="") as f:
        w = csv.DictWriter(f, cols)
        w.writeheader()
        for p in (report.get("comparison") or {}).get("per_figure", []):
            for m in p["boxes"]["moved_boxes"]:
                w.writerow({
                    "pid": p["pid"], "fig": p["fig"], "declared": p["declared"],
                    "kind": "MOVED",
                    "panel_base": m["panel_a"], "panel_candidate": m["panel_b"],
                    "spine_x": m["axis"][0], "baseline_y": m["axis"][1],
                    "base_x0": m["box_a"][0], "base_x1": m["box_a"][1],
                    "base_y0": m["box_a"][2], "base_y1": m["box_a"][3],
                    "cand_x0": m["box_b"][0], "cand_x1": m["box_b"][1],
                    "cand_y0": m["box_b"][2], "cand_y1": m["box_b"][3],
                    "width_base": m["width_a"], "width_candidate": m["width_b"],
                    "max_boundary_delta_px": m["max_boundary_delta_px"],
                    "iou": m["iou"],
                    "status_base": m["status_a"], "status_candidate": m["status_b"]})
            for kind, key in (("ONLY_IN_BASE", "dropped_axes"),
                              ("ONLY_IN_CANDIDATE", "added_axes")):
                for panel, sx, by in p["boxes"][key]:
                    w.writerow({"pid": p["pid"], "fig": p["fig"],
                                "declared": p["declared"], "kind": kind,
                                "panel_base": panel if kind == "ONLY_IN_BASE" else "",
                                "panel_candidate": panel if kind == "ONLY_IN_CANDIDATE" else "",
                                "spine_x": sx, "baseline_y": by})
    written.append(cpath)
    return written


def render(rep):
    if rep["refusals"]:
        lines = ["REFUSED TO COMPARE (%d reason%s)" % (len(rep["refusals"]),
                                                       "" if len(rep["refusals"]) == 1 else "s"), ""]
        lines += ["  " + r for r in rep["refusals"]]
        lines += ["", "No comparison was written.  A refused comparison is the point:",
                  "the numbers you would have read were not measuring what you asked."]
        return "\n".join(lines)
    c = rep["comparison"]
    w = ["COMPARED  (verdict field: %s - this tool reports, it does not judge)" % rep["verdict"], ""]
    if rep.get("outputs_identical"):
        w.append("  the two arms produced BYTE-IDENTICAL output. Whether the change was")
        w.append("  evaluated and agreed, or never reached, cannot be told from here.")
        w.append("")
    w.append("  %-24s %8s %10s %8s" % ("metric", "base", "candidate", "delta"))
    for k, v in c["totals"].items():
        if v["base"] is None:
            w.append("  %-24s %8s %10s %8d" % (k, "-", "-", v["delta"]))
        else:
            w.append("  %-24s %8d %10d %+8d" % (k, v["base"], v["candidate"], v["delta"]))
    w.append("")
    w.append("  boxes that moved while counts held still: %d (max boundary delta %g px)"
             % (c["totals"]["boxes_moved"]["delta"], c["max_boundary_delta_px"]))
    added = sorted({col for p in c["per_figure"] for col in p["shared_columns"]["only_in_candidate"]})
    gone = sorted({col for p in c["per_figure"] for col in p["shared_columns"]["only_in_base"]})
    if added or gone:
        w.append("  columns only in candidate: %s" % (", ".join(added) or "none"))
        w.append("  columns only in base:      %s" % (", ".join(gone) or "none"))
    mism = {}
    for p in c["per_figure"]:
        for k, n in p["shared_columns"]["mismatched"].items():
            mism[k] = mism.get(k, 0) + n
    w.append("  shared columns that disagree: %s"
             % (", ".join("%s x%d" % (k, n) for k, n in sorted(mism.items())) or "none"))
    for p in c["per_figure"]:
        mv = p["boxes"]["moved_boxes"]
        if not (mv or p["boxes"]["added_axes"] or p["boxes"]["dropped_axes"]):
            continue
        w.append("")
        w.append("  %s %s  (declared %s)" % (p["pid"], p["fig"], p["declared"]))
        for m in mv[:6]:
            w.append("    axis %-16s width %g -> %g   iou %.2f   %s -> %s"
                     % (m["axis"], m["width_a"], m["width_b"], m["iou"],
                        m["status_a"], m["status_b"]))
        if p["boxes"]["dropped_axes"]:
            w.append("    axes only in base:      %s" % p["boxes"]["dropped_axes"])
        if p["boxes"]["added_axes"]:
            w.append("    axes only in candidate: %s" % p["boxes"]["added_axes"])
    return "\n".join(w)


if __name__ == "__main__":
    sys.exit(main())
