"""Checks J1-J4 and J6-J9 of the independent judge (SYSTEM_V2_PREREG.md §3.1, §3.2 and Amendment B1 item 2;
IMPLEMENTATION_REGISTER §13 for J9). J5 (recomputation) is judge/recompute.py.

Each check returns a Check with status "ok", "warning" or "violation" and its evidence lines. "unverified" parts
(a failed download, no Twelve Data key) never count as a mismatch.
"""
import json
import math
import os
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

from . import dukascopy, gitio, manifests, registry, store, vendored
from .common import (JUDGE_DIR, iso_s, is_numeric_text, load_json, model_to_utc, parse_utc, read_csv_text,
                     read_dicts, rel_equal, sha256_bytes, sha256_file, weekdays_between,
                     write_csv_append)


@dataclass
class Check:
    id: str
    status: str = "ok"                      # ok | warning | violation
    reasons: list = field(default_factory=list)   # reason codes (verdict.REASONS)
    evidence: list = field(default_factory=list)
    unverified: list = field(default_factory=list)

    def warn(self, code, line):
        if self.status == "ok":
            self.status = "warning"
        self.reasons.append(code)
        self.evidence.append(line)

    def violate(self, code, line):
        self.status = "violation"
        self.reasons.append(code)
        self.evidence.append(line)

    def note(self, line):
        self.evidence.append(line)


# ======================================================================== history preconditions (§3.1 pins)
PIN_NAMES = ("lab-v1-freeze", "lab-v2-freeze", "judge-v1-freeze")


def load_pins():
    p = load_json(JUDGE_DIR / "FROZEN_PINS.json") or {}
    return {k: p.get(k) for k in PIN_NAMES}


def history_state(repo, pins):
    """(usable, problems, tag violations). usable = a git repository, not shallow, every pinned commit present."""
    probs, tagv = [], []
    if not gitio.is_repo(repo):
        return False, ["not a git repository"], []
    if gitio.is_shallow(repo):
        probs.append("the checkout is shallow")
    for name, sha in pins.items():
        if not sha:
            continue
        if not gitio.has_commit(repo, sha):
            probs.append(f"pinned commit {name} = {sha[:12]} is missing")
        t = gitio.tag_commit(repo, name)
        if t is not None and t != sha:
            tagv.append(f"tag {name} resolves to {t[:12]}, pinned {sha[:12]}")
    return not probs, probs, tagv


# ======================================================================== J1
J1_LOG = "reports/judge/j1_checks.csv"
J1_HEAD = ["utc", "store", "day", "side", "result", "committed_sha256", "refetch_sha256", "http"]
KNOWN = "reports/judge/known_revisions.csv"
KNOWN_HEAD = ["utc", "store", "day", "side", "committed_sha256", "refetch_sha256"]


def j1(data_root, out_root, now, transport, sample=20, max_new_days=None, rng_seed=None):
    """J1: independent re-download of days new since the last judge run plus a rotating sample of 20 older days."""
    c = Check("J1")
    data_root, out_root = Path(data_root), Path(out_root)
    log = read_dicts(out_root / J1_LOG)
    known = {(r["store"], r["day"], r["side"]) for r in read_dicts(out_root / KNOWN)}
    side_done = {}
    for r in log:
        if r["result"] in ("same", "revised", "known"):
            k = (r["store"], r["day"], r["side"])
            side_done[k] = max(side_done.get(k, ""), r["utc"])
    stores = {"v1": store.Store(data_root / "data/system"),
              "lookback": store.Store(data_root / "data/system/lab_v2/lookback")}
    days = {}
    for name, st in stores.items():
        for (d, s), r in st.status(now).items():
            if r["status"] == "ok":
                days.setdefault((name, d), []).append((s, r))
    checked = {}          # a day is checked once every ok side of it was compared (same, revised or known)
    for (name, d), sides in days.items():
        ts = [side_done.get((name, d, s)) for s, _ in sides]
        if all(ts):
            checked[(name, d)] = min(ts)
    # the system's own store first, newest day first; then the lab v2 lookback store
    new_all = sorted((k for k in days if k not in checked), key=lambda k: (k[0] != "v1", [-ord(ch) for ch in k[1]]))
    old = sorted((k for k in days if k in checked), key=lambda k: (checked[k], k))
    new = new_all if max_new_days is None else new_all[:max_new_days]
    picked = new + old[:sample]
    rows, n_same, n_rev, n_unv = [], 0, 0, 0
    for name, d in picked:
        st = stores[name]
        for s, r in sorted(days[(name, d)], key=lambda x: 0 if x[0] == "BID" else 1):
            try:
                mine = dukascopy.records(st.body(d, s, r))
            except (store.StoreProblem, dukascopy.BadBody) as e:
                c.note(f"{name} {d} {s}: committed file unreadable ({e}); J3 judges the store")
                continue
            got = transport.get(dukascopy.url(d, s))
            if got is None:
                rows.append([iso_s(now), name, d, s, "unverified", r["sha256"], "", "budget"])
                n_unv += 1
                continue
            status, body = got
            if status != 200:
                rows.append([iso_s(now), name, d, s, "unverified", r["sha256"], "", status])
                n_unv += 1
                continue
            try:
                theirs = dukascopy.valid(body)
            except dukascopy.BadBody:
                rows.append([iso_s(now), name, d, s, "unverified", r["sha256"], sha256_bytes(body), status])
                n_unv += 1
                continue
            if dukascopy.arrays_equal(mine, theirs):
                rows.append([iso_s(now), name, d, s, "same", r["sha256"], sha256_bytes(body), status])
                n_same += 1
            elif (name, d, s) in known:
                rows.append([iso_s(now), name, d, s, "known", r["sha256"], sha256_bytes(body), status])
            else:
                rows.append([iso_s(now), name, d, s, "revised", r["sha256"], sha256_bytes(body), status])
                write_csv_append(out_root / KNOWN, KNOWN_HEAD,
                                 [[iso_s(now), name, d, s, r["sha256"], sha256_bytes(body)]])
                known.add((name, d, s))
                n_rev += 1
                c.warn("j1_revised", f"{name} {d} {s}: the source now serves different data (listed as known from "
                                     "now on)")
    write_csv_append(out_root / J1_LOG, J1_HEAD, rows)
    c.note(f"days new since the last judge run: {len(new_all)} (checked now: {len(new)}); older days sampled: {min(sample, len(old))}; "
           f"sides compared equal: {n_same}; revised: {n_rev}; unverified downloads: {n_unv}")
    if n_unv:
        c.unverified.append(f"{n_unv} downloads failed (unverified, not a mismatch)")
    return c


# ======================================================================== J2
def _first_commit_with_line(repo, rel, line):
    for sha, _, ct in gitio.commits_touching(repo, rel):
        b = gitio.show_bytes(str(repo), sha, rel)
        if b is not None and line in b.decode("utf-8", "replace").splitlines():
            return sha, ct
    return None


def _published_first_day(data_root, version, rid):
    if version == 1:
        j = load_json(Path(data_root) / "reports/forward_site/system/lab.json")
    else:
        j = load_json(Path(data_root) / "reports/system/lab_v2/summary.json")
    for r in (j or {}).get("rules", []) if isinstance(j, dict) else []:
        if r.get("id") == rid:
            return r.get("first_day"), True
    return None, False


def j2(repo, data_root, hist_ok):
    c = Check("J2")
    data_root = Path(data_root)
    git = gitio.is_repo(repo) and Path(repo).resolve() == data_root.resolve()
    if git and gitio.is_shallow(repo):
        git = False          # a truncated history cannot show when a row first appeared: unverified, not a finding
        c.note("shallow checkout: the commit-time and history rules were not evaluated")
    for version in (1, 2):
        lab = registry.Lab(data_root, version)
        sub = "reports/system/lab" if version == 1 else "reports/system/lab_v2"
        ev_rel = f"{sub}/registry/events.csv"
        evp = data_root / ev_rel
        lines = evp.read_text(encoding="utf-8").splitlines() if evp.exists() else []
        L = "reports/system/lab/" if version == 1 else "reports/system/lab_v2/"
        dec = read_dicts(data_root / (L + "decisions.csv"))
        trd = read_dicts(data_root / (L + "trades.csv"))
        seen = set()
        for i, e in enumerate(lab.events):
            if e["event"] != "REGISTERED":
                continue
            again = e["id"] in seen            # every REGISTERED row is dated by its commit; the first one counts
            seen.add(e["id"])
            rid, utc = e["id"], e["_utc"]
            line = lines[i + 1] if i + 1 < len(lines) else None
            tag = f"v{version} {rid}"
            if git and line is not None:
                fc = _first_commit_with_line(repo, ev_rel, line)
                if fc is None:
                    c.note(f"{tag}: REGISTERED row not committed yet")
                else:
                    sha, ct = fc
                    if ct > utc + pd.Timedelta(minutes=60):
                        c.violate("j2_register", f"{tag}: REGISTERED {e['utc']} first appears in {sha[:12]} "
                                                 f"committed {iso_s(ct)} (> utc + 60 min)")
                    reg_rel = f"{sub}/registry/{rid}.json"
                    old = gitio.show_bytes(str(repo), sha, reg_rel)
                    curp = data_root / reg_rel
                    cur = curp.read_bytes() if curp.exists() else None
                    if old is None:
                        c.violate("j2_register", f"{tag}: registry file absent from the registering commit {sha[:12]}")
                    elif cur != old:
                        c.violate("j2_registry", f"{tag}: registry file differs from its version in {sha[:12]}")
                    added = gitio.commits_touching(repo, reg_rel)
                    if added and added[0][2] > utc + pd.Timedelta(minutes=60):
                        c.violate("j2_register", f"{tag}: registry file first committed {iso_s(added[0][2])}, after "
                                                 f"its REGISTERED time {e['utc']}")
            elif not git:
                c.note(f"{tag}: no usable git history for this data (commit-time rule not evaluated)")
            if lab.start is None or again:
                continue
            fd = registry.first_day(utc, lab.start)
            pub, has = _published_first_day(data_root, version, rid)
            if has and pub not in (None, fd.strftime("%Y-%m-%d")):
                c.violate("j2_firstday", f"{tag}: published first_day {pub} != {fd.date()} (v1 §3 item 5)")
            for name, rows in (("decision", dec), ("trade", trd)):
                bad = [r["day"] for r in rows if r["id"] == rid and pd.Timestamp(r["day"]) < fd]
                if bad:
                    c.violate("j2_firstday", f"{tag}: {len(bad)} {name} rows dated before first_day {fd.date()} "
                                             f"(first {bad[0]})")
            c.note(f"{tag}: registered {e['utc']}, first_day {fd.date()}")
    # both START.json files unchanged since their first commit
    for rel in ("reports/system/START.json", "reports/system/lab_v2/START.json"):
        if not git:
            continue
        hist = gitio.commits_touching(repo, rel)
        if not hist:
            continue
        first = gitio.show_bytes(str(repo), hist[0][0], rel)
        for sha, _, _ in hist[1:]:
            if gitio.show_bytes(str(repo), sha, rel) != first:
                c.violate("j2_start", f"{rel} changed in {sha[:12]} after its first commit")
                break
        p = data_root / rel
        if p.exists() and p.read_bytes() != first:
            c.violate("j2_start", f"{rel} in the working tree differs from its first commit")
    if not hist_ok and c.status != "violation":
        c.warn("unverified", "history could not be verified (shallow checkout or a pinned commit missing)")
    return c


# ======================================================================== J3
APPEND_V1 = ["data/system/days.csv", "data/system/attempts.csv", "data/system/rechecks.csv",
             "data/system/revisions.csv", "data/system/forecasts.csv", "reports/system/l3_updates.csv",
             "reports/system/ops_changes.csv", "reports/system/calendar_ext.csv",
             "reports/system/lab/lab_days.csv", "reports/system/lab/decisions.csv", "reports/system/lab/trades.csv",
             "reports/system/lab/eproc.csv", "reports/system/lab/twins.csv", "reports/system/lab/registry/events.csv"]
APPEND_V2 = ["data/system/lab_v2/lookback/days.csv", "data/system/lab_v2/lookback/attempts.csv"] + [
    f"reports/system/lab_v2/{n}.csv" for n in ("audit", "decisions", "trades", "twins", "eproc", "lab_days", "halts",
                                               "ops_changes")] + ["reports/system/lab_v2/registry/events.csv"]
APPEND_JUDGE = [f"reports/judge/{n}.csv" for n in ("VERDICTS", "ADJUDICATIONS", "cross_source", "known_revisions",
                                                  "judge_changes", "j1_checks", "j5_verified", "j6_checkpoints")]
RAW = ["data/system/raw", "data/system/lab_v2/lookback/raw"]


def prefix_problem(old, new, tol=1e-12):
    """None if every row of `old` is kept, in place, in `new` (numeric fields at rel <= tol, others exact)."""
    if old is None:
        return None
    if new is None:
        return "the file was deleted"
    ho, ro = read_csv_text(old.decode("utf-8", "replace"))
    hn, rn = read_csv_text(new.decode("utf-8", "replace"))
    if ho and ho != hn:
        return "the header changed"
    if len(rn) < len(ro):
        return f"{len(ro) - len(rn)} past rows removed"
    for i, (a, b) in enumerate(zip(ro, rn)):
        if a == b:
            continue
        if len(a) != len(b):
            return f"row {i + 2} rewritten"
        for x, y in zip(a, b):
            if x == y:
                continue
            if is_numeric_text(x) and is_numeric_text(y) and rel_equal(float(x), float(y), tol):
                continue
            return f"row {i + 2} rewritten"
    return None


def blocks_problem(old, new):
    """l1_blocks.csv: a complete = 1 row never changes and complete never goes 1 -> 0."""
    if old is None or new is None:
        return None
    ho, ro = read_csv_text(old.decode("utf-8", "replace"))
    hn, rn = read_csv_text(new.decode("utf-8", "replace"))
    a = {r[0]: dict(zip(ho, r)) for r in ro if r}
    b = {r[0]: dict(zip(hn, r)) for r in rn if r}
    for k, r in a.items():
        if str(r.get("complete")) in ("1", "True"):
            if k not in b:
                return f"complete block {k} removed"
            for f, v in r.items():
                w = b[k].get(f, "")
                if v != w and not (is_numeric_text(v) and is_numeric_text(w) and rel_equal(float(v), float(w), 1e-12)):
                    return f"complete block {k} changed ({f})"
    return None


def _history_problems(repo, rel, base, checker):
    probs = []
    for sha, parents, _ in gitio.commits_touching(repo, rel, base):
        new_b = gitio.blob(str(repo), sha, rel)
        for p in parents:
            old_b = gitio.blob(str(repo), p, rel)
            if old_b == new_b or old_b is None:
                continue
            pr = checker(gitio.show_bytes(str(repo), p, rel),
                         gitio.show_bytes(str(repo), sha, rel) if new_b else None)
            if pr:
                probs.append(f"{rel}: {pr} in {sha[:12]}")
    return probs


def j3(repo, data_root, pins, hist_ok, out_root=None):
    c = Check("J3")
    data_root = Path(data_root)
    git = gitio.is_repo(repo) and Path(repo).resolve() == data_root.resolve()
    # committed raw files are never modified or deleted (whole history) and match their days rows
    for name, base in (("v1", data_root / "data/system"), ("lookback", data_root / "data/system/lab_v2/lookback")):
        st = store.Store(base)
        for (d, s), r in st.status(None).items():
            if r["status"] != "ok":
                continue
            p = st.path(d, s)
            if not p.exists():
                c.violate("j3_raw", f"{name} raw {d} {s}: missing")
            elif sha256_file(p) != r["sha256"]:
                c.violate("j3_raw", f"{name} raw {d} {s}: sha256 differs from its days row")
    if git and gitio.is_shallow(repo):
        for stt, p in gitio.worktree_diff(repo, RAW):
            c.violate("j3_raw", f"{p}: {stt} in the working tree")
        c.note("shallow checkout: the history rules were not evaluated")
    elif git:
        for sha, stt, p in gitio.changed_paths(repo, RAW):
            c.violate("j3_raw", f"{p}: {stt} in commit {sha[:12]}")
        for stt, p in gitio.worktree_diff(repo, RAW):
            c.violate("j3_raw", f"{p}: {stt} in the working tree")
        groups = [(APPEND_V1, pins.get("lab-v1-freeze"), "v1"), (APPEND_V2, pins.get("lab-v2-freeze"), "v2")]
        for files, base, tag in groups:
            if not base:
                c.note(f"{tag} append-only files: no freeze pinned yet, not checked")
                continue
            if not gitio.has_commit(repo, base):
                continue
            for rel in files:
                for pr in _history_problems(repo, rel, base, prefix_problem):
                    c.violate("j3_ledger", pr)
                cur = data_root / rel
                headb = gitio.show_bytes(str(repo), "HEAD", rel)
                pr = prefix_problem(headb, cur.read_bytes() if cur.exists() else None)
                if pr:
                    c.violate("j3_ledger", f"{rel}: {pr} in the working tree")
            if tag == "v1":
                rel = "reports/system/l1_blocks.csv"
                for pr in _history_problems(repo, rel, base, blocks_problem):
                    c.violate("j3_ledger", pr)
        # the judge's own append-only records (§3.1 self-integrity)
        jbase = pins.get("judge-v1-freeze") if pins.get("judge-v1-freeze") and \
            gitio.has_commit(repo, pins["judge-v1-freeze"]) else None
        for rel in APPEND_JUDGE:
            for pr in _history_problems(repo, rel, jbase, prefix_problem):
                c.violate("j3_judge", pr)
            cur = (Path(out_root) if out_root else data_root) / rel
            headb = gitio.show_bytes(str(repo), "HEAD", rel)
            pr = prefix_problem(headb, cur.read_bytes() if cur.exists() else None)
            if pr and headb is not None:
                c.violate("j3_judge", f"{rel}: {pr} in the working tree")
    else:
        c.note("no git history for this data: only the raw files against their days rows were checked")
    if not hist_ok and c.status != "violation":
        c.warn("unverified", "history could not be verified (shallow checkout or a pinned commit missing)")
    return c


# ======================================================================== J4
JUDGE_MANIFEST = "judge/FROZEN_JUDGE.sha256"


def judge_files():
    """The judge's own frozen set: every .py and .json under judge/ (vendor included) and the workflow."""
    out = []
    for p in sorted(JUDGE_DIR.rglob("*")):
        if not p.is_file() or "__pycache__" in p.parts:
            continue
        if p.name == "FROZEN_PINS.json":
            continue          # written by the freeze follow-up commit (§5); the pins are checked by their own rules
        if p.suffix in (".py", ".json") or p.name == "SHA256SUMS":
            out.append(p)
    return out


def judge_manifest_text(repo):
    lines = []
    repo = Path(repo).resolve()
    for p in judge_files():
        lines.append(f"{sha256_file(p)}  {p.resolve().relative_to(JUDGE_DIR.parent).as_posix()}")
    wf = JUDGE_DIR.parent / ".github/workflows/judge.yml"
    if wf.exists():
        lines.append(f"{sha256_file(wf)}  .github/workflows/judge.yml")
    return "\n".join(lines) + "\n"


V1_FREEZE = "6cd6d57ef62d8eb8710dd5151c7b5ddc2612d095"    # SYSTEM_V2_PREREG.md §3.1


def pins_history(judge_repo):
    """Problems with judge/FROZEN_PINS.json over its git history: a pin, once set, never changes or disappears."""
    probs = []
    rel = "judge/FROZEN_PINS.json"
    if not gitio.is_repo(judge_repo) or gitio.is_shallow(judge_repo):
        return probs
    first = {}
    versions = []
    for sha, _, _ in gitio.commits_touching(judge_repo, rel):
        b = gitio.show_bytes(str(judge_repo), sha, rel)
        try:
            versions.append((sha, json.loads(b.decode("utf-8")) if b else {}))
        except ValueError:
            versions.append((sha, {}))
    cur = load_json(JUDGE_DIR / "FROZEN_PINS.json") or {}
    versions.append(("working tree", cur))
    for sha, v in versions:
        for k in PIN_NAMES:
            val = v.get(k) if isinstance(v, dict) else None
            if k in first and val != first[k]:
                probs.append(f"FROZEN_PINS.json: {k} changed from {first[k][:12]} at {sha[:12]}")
            elif val and k not in first:
                first[k] = val
    return probs


def pin_problems():
    """The judge's own judge/FROZEN_PINS.json: lab-v1-freeze is the prereg's value and no pin ever changed."""
    pins = load_json(JUDGE_DIR / "FROZEN_PINS.json") or {}
    probs = []
    if pins.get("lab-v1-freeze") != V1_FREEZE:
        probs.append(f"the lab-v1-freeze pin {str(pins.get('lab-v1-freeze'))[:12]} is not the prereg's "
                     f"{V1_FREEZE[:12]}")
    return probs + pins_history(JUDGE_DIR.parent)


def j4(repo, data_root, pins, hist_ok, tagv, out_root=None, pin_probs=()):
    c = Check("J4")
    repo = Path(repo)
    for t in tagv:
        c.violate("j4_tag", t)
    for p in pin_probs:
        c.violate("j4_frozen", p)
    git = gitio.is_repo(repo)
    for name, rel in (("lab-v1-freeze", "analysis/system/FROZEN.sha256"),
                      ("lab-v2-freeze", "analysis/system/lab_v2/FROZEN_V2.sha256")):
        pin = pins.get(name)
        if not pin:
            c.note(f"{name}: not pinned yet ({rel} not checked)")
            continue
        if not git or not gitio.has_commit(repo, pin):
            continue
        pinned = manifests.read_manifest(repo, pin, rel)
        if not pinned:
            c.violate("j4_frozen", f"{rel} does not exist at {name} {pin[:12]}")
            continue
        probs, n = manifests.verify(repo, rel, pinned)
        for p in probs:
            c.violate("j4_frozen", p)
        c.note(f"{rel}: {n} pinned entries, {len(probs)} problems")
    # z* (A1 item 6) is fixed before START: reports/system/L3_ZSTAR.json equals its version at lab-v1-freeze
    pin = pins.get("lab-v1-freeze")
    if git and pin and gitio.has_commit(repo, pin):
        zs_rel = "reports/system/L3_ZSTAR.json"
        old = gitio.show_bytes(str(repo), pin, zs_rel)
        curz = Path(data_root) / zs_rel
        if old is not None and (not curz.exists() or curz.read_bytes() != old):
            c.violate("j4_frozen", f"{zs_rel} differs from its version at lab-v1-freeze")
        elif old is not None:
            c.note(f"{zs_rel} unchanged since lab-v1-freeze")
    # self-integrity of the judge (§3.1). OPS fixes of judge files are allowed only with a row in
    # reports/judge/judge_changes.csv (utc,file,old_sha256,new_sha256,reason) naming the file's new sha256.
    vp = vendored.check()
    for p in vp:
        c.warn("j4_self", f"judge {p}")
    mp = JUDGE_DIR / "FROZEN_JUDGE.sha256"
    cur = manifests.parse(mp.read_text()) if mp.exists() else {}
    live = manifests.parse(judge_manifest_text(repo))
    jpin = pins.get("judge-v1-freeze")
    logged = {(r.get("file"), r.get("new_sha256")) for r in
              read_dicts(Path(out_root or data_root) / "reports/judge/judge_changes.csv")}
    ref = cur
    if jpin and git and gitio.has_commit(repo, jpin):
        ref = manifests.read_manifest(repo, jpin, JUDGE_MANIFEST) or {}
        if not ref:
            c.warn("j4_self", f"{JUDGE_MANIFEST} does not exist at judge-v1-freeze")
    elif not jpin:
        c.note("judge-v1-freeze: not pinned yet (the judge's manifest is checked against its own files only)")
    if not cur:
        c.warn("j4_self", f"{JUDGE_MANIFEST} is missing")
    for p, h in ref.items():
        now_h = live.get(p)
        if now_h != h and (p, now_h) not in logged:
            c.warn("j4_self", f"judge file {p} differs from its frozen sha256 and judge_changes.csv has no row for it")
    for p in live:
        if p not in ref and ref:
            c.warn("j4_self", f"judge file {p} is not in the frozen manifest")
    if not hist_ok and c.status == "ok":
        c.warn("unverified", "pinned commits could not be verified (shallow checkout or a pinned commit missing)")
    return c


# ======================================================================== J6
J6_LOG = "reports/judge/j6_checkpoints.csv"
J6_HEAD = ["utc", "month", "weeks", "n_trials", "hit_rate", "ci_lo", "ci_hi", "a_flag", "n_qlike", "dm_stat",
           "p_worse", "b_flag"]


def hit_ci(trials):
    """Pooled hit rate with a 95% CI clustered by ISO week. trials: [(week, hits, n)]."""
    if not trials:
        return float("nan"), float("nan"), float("nan"), 0
    wk = {}
    for w, h, n in trials:
        a = wk.setdefault(w, [0, 0])
        a[0] += h
        a[1] += n
    H = sum(v[0] for v in wk.values())
    N = sum(v[1] for v in wk.values())
    p = H / N if N else float("nan")
    G = len(wk)
    if G < 2 or N == 0:
        return p, float("nan"), float("nan"), G
    s = sum((v[0] - p * v[1]) ** 2 for v in wk.values())
    se = math.sqrt(G / (G - 1) * s) / N
    return p, p - 1.96 * se, p + 1.96 * se, G


def j6_stats(ctx):
    """(a) pooled k10 hour-stop hit rate on mid over hours with a defined RAW F_H1 and >= 48 minutes; (b) QLIKE of
    F_H1 against the same-hour 20-trading-day mean range, DM with Newey-West lag 24; (c) green vs red; (d) lab rules
    vs C1."""
    from . import l1 as L1
    core, _, _ = vendored.volmap()
    start = ctx.lab1.start
    res = {"weeks": 0, "n_trials": 0}
    if start is None:
        return res
    sm = ctx.store_map()
    g = ctx.grid()
    gy = {(r.day, int(r.slot)): r.y for r in g.itertuples()}
    trs = L1.trials(sm, ctx.mf(), start, ctx.cu)
    rows = []
    for t in trs:
        d = t["day"]
        slot = int(t["origin"].hour) - 1
        y = gy.get((d.strftime("%Y-%m-%d"), slot), float("nan"))
        if not math.isfinite(y) or not t["entry"]:
            continue
        iso = d.isocalendar()
        rows.append((iso[0] * 100 + iso[1], int(t["long"]) + int(t["short"]), 2, t["state"]))
    # complete weeks: ISO weeks whose Friday 24:00 model is final
    weeks = sorted({w for w, *_ in rows})
    complete = []
    for w in weeks:
        y, n = divmod(w, 100)
        fri = pd.Timestamp.fromisocalendar(y, n, 5) + pd.Timedelta(days=1)
        if model_to_utc(fri) <= ctx.cu:
            complete.append(w)
    sel = [(w, h, n) for w, h, n, _ in rows if w in complete]
    p, lo, hi, G = hit_ci(sel)
    res.update({"weeks": len(complete), "n_trials": sum(n for *_, n in sel) // 2, "hit_rate": p, "ci_lo": lo,
                "ci_hi": hi})
    res["a_flag"] = int(len(complete) >= 13 and math.isfinite(lo) and (hi < 0.06 or lo > 0.14))
    for st in ("GREEN", "RED"):
        s2 = [(w, h, n) for w, h, n, s in rows if s == st]
        res[f"hit_{st.lower()}"] = hit_ci(s2)[0]
    # (b) QLIKE against the same-hour 20-trading-day mean range
    gg = g.copy()
    gg["d"] = pd.to_datetime(gg["day"])
    gg = gg[gg["d"].dt.dayofweek < 5]
    piv = gg.pivot_table(index="d", columns="slot", values="y", aggfunc="first").sort_index()
    # the mean of the valid ranges of the same hour over the previous 20 trading days (at least 10 of them)
    bench = piv.rolling(20, min_periods=10).mean().shift(1)
    lm, lb = [], []
    for (day, slot), r in sorted(sm.items()):
        d = pd.Timestamp(day)
        F = r["F_H1"]
        if d < start or not (math.isfinite(F) and F > 0):
            continue
        if model_to_utc(pd.Timestamp(r["origin"]) + pd.Timedelta(hours=1)) > ctx.cu:
            continue
        y = gy.get((day, slot), float("nan"))
        if not (math.isfinite(y) and y > 0):
            continue
        b = bench.at[d, slot] if (d in bench.index and slot in bench.columns) else float("nan")
        if not (math.isfinite(b) and b > 0):
            continue
        lm.append(float(core.qlike(y, F)))
        lb.append(float(core.qlike(y, b)))
    res["n_qlike"] = len(lm)
    if len(lm) >= 2:
        stat, _ = core.dm_test(lb, lm, 24)
        res["dm_stat"] = float(stat)
        res["p_worse"] = float(core.norm_sf(-stat))
        res["qlike_model"] = float(np.mean(lm))
        res["qlike_bench"] = float(np.mean(lb))
    else:
        res["dm_stat"], res["p_worse"] = float("nan"), float("nan")
    res["b_flag"] = int(len(lm) >= 500 and math.isfinite(res["p_worse"]) and res["p_worse"] < 0.01)
    return res


def j6(ctx, out_root, now, lab_vs_c1):
    c = Check("J6")
    res = j6_stats(ctx)
    month = now.strftime("%Y-%m")         # the first judge run of each calendar month (UTC) is the checkpoint
    log = read_dicts(Path(out_root) / J6_LOG)
    if not any(r["month"] == month for r in log):
        row = [iso_s(now), month, res.get("weeks", 0), res.get("n_trials", 0)] + [
            repr(float(res.get(k, float("nan")))) for k in ("hit_rate", "ci_lo", "ci_hi")] + [
            res.get("a_flag", 0), res.get("n_qlike", 0), repr(float(res.get("dm_stat", float("nan")))),
            repr(float(res.get("p_worse", float("nan")))), res.get("b_flag", 0)]
        write_csv_append(Path(out_root) / J6_LOG, J6_HEAD, [row])
        c.note(f"monthly checkpoint {month} recorded (first judge run of the month)")
        log = read_dicts(Path(out_root) / J6_LOG)
    last2 = log[-2:]
    if len(last2) == 2:
        if all(r["a_flag"] == "1" for r in last2):
            c.warn("j6_hit", "(a) the hit-rate CI lay outside [6%, 14%] at two consecutive monthly checkpoints")
        if all(r["b_flag"] == "1" for r in last2):
            c.warn("j6_qlike", "(b) the forecast lost to the 20-day same-hour mean (p < 0.01) at two consecutive "
                               "monthly checkpoints")
    hr = res.get("hit_rate", float("nan"))
    c.note(f"(a) complete weeks {res.get('weeks', 0)}, hour trials {res.get('n_trials', 0)}, pooled hit rate "
           f"{hr:.4f} (95% CI {res.get('ci_lo', float('nan')):.4f} .. {res.get('ci_hi', float('nan')):.4f})"
           if math.isfinite(hr) else f"(a) no complete forward week yet (weeks {res.get('weeks', 0)})")
    c.note(f"(b) QLIKE hours {res.get('n_qlike', 0)}; DM stat {res.get('dm_stat', float('nan')):.3f}; "
           f"one-sided p (forecast worse) {res.get('p_worse', float('nan')):.4f}")
    c.note(f"(c) hit rate green {res.get('hit_green', float('nan')):.4f}, red {res.get('hit_red', float('nan')):.4f}")
    for line in lab_vs_c1:
        c.note(f"(d) {line}")
    return c, res


# ======================================================================== J7
def j7(repo, data_root, now):
    c = Check("J7")
    rel = "reports/forward_site/system/VolMapSystem.csv"
    t = None
    if gitio.is_repo(repo) and Path(repo).resolve() == Path(data_root).resolve():
        lc = gitio.last_commit_touching(repo, rel)
        if lc:
            t = lc[1]
            c.note(f"latest commit of {rel}: {lc[0][:12]} at {iso_s(t)}")
    if t is None:
        p = Path(data_root) / rel
        if p.exists():
            for ln in p.read_text(encoding="utf-8").splitlines():
                if ln.startswith("asof_utc,"):
                    t = parse_utc(ln.split(",", 1)[1])
            c.note(f"no commit history: the status file's asof_utc {iso_s(t) if t else '-'} is used")
    if t is None:
        c.warn("j7_stale", f"{rel} is missing")
    else:
        age = weekdays_between(t.tz_localize(None), now.tz_localize(None))
        c.note(f"age {age} trading day(s) (limit 2)")
        if age > 2:
            c.warn("j7_stale", f"the status file was last committed {age} trading days ago")
    sm = Path(data_root) / "reports/system/STATUS.md"
    if sm.exists():
        txt = sm.read_text(encoding="utf-8")
        if "**Operational failures**" in txt:
            fails = [ln for ln in txt.split("**Operational failures**", 1)[1].splitlines()[1:8] if ln.startswith("- ")]
            c.warn("j7_ops", "STATUS.md lists operational failures in its latest run: " + "; ".join(fails)[:300])
        else:
            c.note("STATUS.md lists no operational failure")
    else:
        c.warn("j7_stale", "reports/system/STATUS.md is missing")
    return c


# ======================================================================== J8
def deployed_judge_csv(site_url, opener=None):
    """The VolMapJudge.csv currently deployed at <site_url>/judge/VolMapJudge.csv (an anchor outside git), or None."""
    import urllib.request
    if not site_url:
        return None
    opener = opener or (lambda req, timeout: urllib.request.urlopen(req, timeout=timeout))
    try:
        req = urllib.request.Request(site_url.rstrip("/") + "/judge/VolMapJudge.csv",
                                     headers={"User-Agent": "gold-forward-watch judge-v1"})
        with opener(req, 30) as r:
            return r.read().decode("utf-8", "replace")
    except Exception:   # noqa: BLE001
        return None


def j8(repo, out_root, hist_ok, site_url=None):
    c = Check("J8")
    out_root = Path(out_root)
    if not gitio.is_repo(repo):
        c.note("not a git repository: J8 not applicable")
        return c
    head = gitio.head(repo)
    cands = []
    v = read_dicts(out_root / "reports/judge/VERDICTS.csv")
    if v:
        cands.append(("the previous VERDICTS.csv row", v[-1].get("head_sha", "")))
    jf = out_root / "reports/forward_site/judge/VolMapJudge.csv"
    if jf.exists():
        for ln in jf.read_text(encoding="utf-8", errors="replace").splitlines():
            if ln.startswith("head_sha,"):
                cands.append(("the published VolMapJudge.csv", ln.split(",", 1)[1]))
    site_url = site_url if site_url is not None else os.environ.get("JUDGE_SITE_URL", "")
    if site_url:
        txt = deployed_judge_csv(site_url)
        if txt is None:
            c.unverified.append("the deployed VolMapJudge.csv could not be fetched")
        else:
            for ln in txt.splitlines():
                if ln.startswith("head_sha,"):
                    cands.append(("the deployed VolMapJudge.csv", ln.split(",", 1)[1].strip()))
    for what, sha in cands:
        if not sha or set(sha) == {"0"}:
            continue
        if sha == head or gitio.is_ancestor(repo, sha, head):
            c.note(f"{what} head {sha[:12]} is an ancestor of HEAD {head[:12]}")
        elif not hist_ok:
            c.warn("unverified", f"{what} head {sha[:12]}: ancestry unverifiable (shallow checkout)")
        else:
            c.violate("j8_rewritten", f"{what} head {sha[:12]} is not an ancestor of HEAD {head[:12]} "
                                      "(history rewritten)")
    if not cands:
        c.note("no previous judge run recorded")
    return c


# ======================================================================== J9 (Amendment B1 item 2, register §13)
TD_URL = "https://api.twelvedata.com/time_series"
CS = "reports/judge/cross_source.csv"
CS_HEAD = ["utc", "day", "result", "reason", "n_hours", "median_abs_usd", "max_abs_usd", "credits"]


def j9_day(v1, now):
    """R-J9-2: the latest UTC weekday before complete_utc whose BID and ASK rows are both ok."""
    cu = store.complete_utc(v1, now)
    st = v1.status(now)
    d = cu.tz_localize(None) - pd.Timedelta(days=1)
    while d >= pd.Timestamp("2026-09-01"):
        ds = d.strftime("%Y-%m-%d")
        if d.dayofweek < 5 and all(st.get((ds, s), {}).get("status") == "ok" for s in ("BID", "ASK")):
            return ds
        d -= pd.Timedelta(days=1)
    return None


def _td_request(day, key, opener, sleep):
    """At most 2 requests (one retry after 20 s on a connection error or 5xx). Returns (status, json|None, credits)."""
    import urllib.error
    import urllib.parse
    import urllib.request
    d = pd.Timestamp(day)
    q = urllib.parse.urlencode({"symbol": "XAU/USD", "interval": "1h", "timezone": "UTC",
                                "start_date": f"{d:%Y-%m-%d} 00:00:00",
                                "end_date": f"{d + pd.Timedelta(days=1):%Y-%m-%d} 00:00:00"})
    credits = 0
    status, body = 0, None
    for attempt in range(2):
        credits += 1
        req = urllib.request.Request(f"{TD_URL}?{q}", headers={"Authorization": f"apikey {key}",
                                                                 "User-Agent": "gold-forward-watch judge-v1"})
        try:
            with opener(req, 60) as resp:
                status, raw = resp.status, resp.read()
            try:
                body = json.loads(raw.decode("utf-8"))
            except (ValueError, UnicodeDecodeError):
                body = None
            return status, body, credits, raw is not None
        except urllib.error.HTTPError as e:
            status, body = e.code, None
            if not (500 <= e.code < 600):
                return status, None, credits, False
        except (urllib.error.URLError, OSError, TimeoutError):
            status, body = 0, None
        if attempt == 0:
            sleep(20)
    return status, None, credits, False


def j9(data_root, out_root, now, opener=None, sleep=None, env=None):
    import time
    import urllib.request
    c = Check("J9")
    env = os.environ if env is None else env
    opener = opener or (lambda req, timeout: urllib.request.urlopen(req, timeout=timeout))
    sleep = sleep or time.sleep
    out_root = Path(out_root)
    v1 = store.Store(Path(data_root) / "data/system")
    day = j9_day(v1, now)
    log = read_dicts(out_root / CS)
    checked = {r["day"]: r["result"] for r in log if r["result"] in ("ok", "exceeds")}
    row = None
    if day is not None and day in checked:
        c.note(f"{day} already checked ({checked[day]}); no request sent")
    else:
        key = env.get("TWELVEDATA_API_KEY", "")
        if day is None:
            row = [iso_s(now), "", "unverified", "no complete day", "", "", "", 0]
        elif not key:
            row = [iso_s(now), day, "unverified", "no key", "", "", "", 0]
        else:
            status, body, credits, _ = _td_request(day, key, opener, sleep)
            key = None
            row = _j9_compare(v1, day, now, status, body, credits)
        write_csv_append(out_root / CS, CS_HEAD, [row])
        c.note(f"{row[1] or '-'}: {row[2]}{(' (' + row[3] + ')') if row[3] else ''}; credits {row[7]}")
        if row[2] == "unverified":
            c.unverified.append(f"J9 {row[1] or '-'}: {row[3]}")
    log = read_dicts(out_root / CS)
    chk = sorted(((r["day"], r["result"]) for r in log if r["result"] in ("ok", "exceeds")))
    last = {}
    for d, r in chk:
        last[d] = r
    days = sorted(last)[-2:]
    if len(days) == 2 and all(last[d] == "exceeds" for d in days):
        c.warn("j9_price", f"the two most recent checked days {days[0]} and {days[1]} both exceed the limits "
                           "(median > $0.50 or max > $5)")
    return c


def _j9_compare(v1, day, now, status, body, credits):
    base = [iso_s(now), day]
    if status == 429 or (isinstance(body, dict) and str(body.get("code")) == "429"):
        return base + ["unverified", "quota", "", "", "", credits]
    if status != 200:
        return base + ["unverified", f"http {status}", "", "", "", credits]
    if not isinstance(body, dict):
        return base + ["unverified", "bad response", "", "", "", credits]
    if body.get("status") == "error":
        return base + ["unverified", f"api {body.get('code')}", "", "", "", credits]
    vals = body.get("values")
    if not isinstance(vals, list):
        return base + ["unverified", "bad response", "", "", "", credits]
    d0 = pd.Timestamp(day)
    td = {}
    for v in vals:
        try:
            t = pd.Timestamp(v["datetime"])
            cl = float(v["close"])
        except (KeyError, ValueError, TypeError):
            return base + ["unverified", "bad response", "", "", "", credits]
        if not math.isfinite(cl):
            return base + ["unverified", "bad response", "", "", "", credits]
        if d0 <= t < d0 + pd.Timedelta(days=1):
            td[t] = cl
    st = v1.status(now)
    frames = {}
    for s in ("BID", "ASK"):
        frames[s] = dukascopy.frame(v1.body(day, s, st[(day, s)]), day).set_index("ts")
    b, a = frames["BID"], frames["ASK"]
    j = b.join(a, lsuffix="_b", rsuffix="_a", how="inner")
    j = j[(j["vol_b"] > 0) & (j["vol_a"] > 0)]
    diffs = []
    for t, cl in sorted(td.items()):
        tu = t.tz_localize("UTC")
        w = j[(j.index >= tu) & (j.index < tu + pd.Timedelta(hours=1))]
        if w.empty:
            continue
        last = w.iloc[-1]
        mid = (float(last["c_b"]) + float(last["c_a"])) / 2
        diffs.append(abs(cl - mid))
    if not diffs:
        return base + ["unverified", "no common hour", "", "", "", credits]
    med = float(np.median(diffs))
    mx = float(max(diffs))
    res = "exceeds" if (med > 0.50 or mx > 5.00) else "ok"
    return base + [res, "", len(diffs), repr(med), repr(mx), credits]
