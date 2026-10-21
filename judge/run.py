"""The independent judge, judge v1 (xauusd-quant research/system/SYSTEM_V2_PREREG.md §3 with Amendment B1 item 2).

    uv run --frozen python -I judge/run.py [--now ISO] [--out DIR] [--data-root DIR] [--repo DIR]
                                           [--j1-max-days N] [--j1-sample N] [--j1-max-requests N] [--no-network]
                                           [--j5-all] [--j5-sample N]
    uv run --frozen python -I judge/run.py --write-manifest     (rewrites judge/FROZEN_JUDGE.sha256)

It reads the system's committed data and outputs, the git history, its own vendored research files and its own
records under reports/judge/, and writes only reports/judge/** and reports/forward_site/judge/** (under --out).
It imports nothing from analysis/ and executes no system code. The Twelve Data key (J9) is read only from the
environment variable TWELVEDATA_API_KEY and sent only in the Authorization header.
"""
import argparse
import sys
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE.parent) not in sys.path:
    sys.path.insert(0, str(HERE.parent))

from judge import checks, dukascopy, gitio, publish, recompute, verdict  # noqa: E402
from judge.common import iso_s, now_utc, parse_utc, read_dicts, sha256_bytes, write_csv_append  # noqa: E402

J5_LOG = "reports/judge/j5_verified.csv"
J5_HEAD = ["utc", "version", "day", "result"]


def _guard(name, fn, *a, **k):
    """Run one check; an exception inside the judge means it could not verify (WARNING «تعذر التحقق»)."""
    try:
        return fn(*a, **k)
    except Exception as e:   # noqa: BLE001
        c = checks.Check(name)
        tb = traceback.format_exception_only(type(e), e)[-1].strip()
        c.warn("unverified", f"the judge could not complete this check: {tb[:300]}")
        return c


def v2_cover(out_root, data_root, sample, all_days):
    lab_days = read_dicts(Path(data_root) / "reports/system/lab_v2/lab_days.csv")
    days = [r["day"] for r in lab_days]
    if all_days:
        return set(days), days, []
    log = read_dicts(Path(out_root) / J5_LOG)
    last, res = {}, {}
    for r in log:
        if r["version"] == "2":
            last[r["day"]] = r["utc"]
            res[r["day"]] = r["result"]
    new = [d for d in days if d not in last or res.get(d) != "ok"]
    old = sorted((d for d in days if d in last), key=lambda d: (last[d], d))[:sample]
    return set(new) | set(old), new, old


def lab_vs_c1(data_root):
    """J6 (d), descriptive: each lab rule's final trades against the C1 coin (dollars per oz; R units differ)."""
    out = []
    root = Path(data_root)
    for v, rel in ((1, "reports/system/lab/trades.csv"), (2, "reports/system/lab_v2/trades.csv")):
        by = {}
        for r in read_dicts(root / rel):
            if r.get("status") == "final":
                by.setdefault(r["id"], []).append(float(r["net_usd"]))
        for rid, xs in sorted(by.items()):
            out.append(f"v{v} {rid}: {len(xs)} trades, net {sum(xs):.2f} $/oz, mean {sum(xs) / len(xs):.3f}")
    if not out:
        out.append("no final lab trade yet")
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description="independent judge v1")
    ap.add_argument("--repo", default=str(HERE.parent))
    ap.add_argument("--data-root", default=None)
    ap.add_argument("--out", default=None)
    ap.add_argument("--now", default=None)
    ap.add_argument("--j1-max-days", type=int, default=None)
    ap.add_argument("--j1-sample", type=int, default=20)
    ap.add_argument("--j1-max-requests", type=int, default=150)
    ap.add_argument("--j1-pace-s", type=float, default=1.5)
    ap.add_argument("--no-network", action="store_true", help="J1 and J9 send no request (unverified)")
    ap.add_argument("--j5-all", action="store_true")
    ap.add_argument("--j5-sample", type=int, default=3)
    ap.add_argument("--write-manifest", action="store_true")
    a = ap.parse_args(argv)
    repo = Path(a.repo).resolve()
    if a.write_manifest:
        (HERE / "FROZEN_JUDGE.sha256").write_text(checks.judge_manifest_text(repo))
        print("judge/FROZEN_JUDGE.sha256 written")
        return 0
    data_root = Path(a.data_root).resolve() if a.data_root else repo
    out_root = Path(a.out).resolve() if a.out else repo
    now = parse_utc(a.now) if a.now else now_utc()

    pins = checks.load_pins()
    hist_ok, hist_probs, tagv = checks.history_state(repo, pins)
    head = gitio.head(repo) if gitio.is_repo(repo) else "0" * 40
    extra = [f"judge run {iso_s(now)}; data root {'repo' if data_root == repo else data_root}"]
    extra += [f"history: {p}" for p in hist_probs]

    if a.no_network:
        class _Off:
            def get(self, u):
                return None
        tr = _Off()
    else:
        tr = dukascopy.Transport(pace_s=a.j1_pace_s, max_requests=a.j1_max_requests)
    c1 = _guard("J1", checks.j1, data_root, out_root, now, tr, sample=a.j1_sample, max_new_days=a.j1_max_days)
    c2 = _guard("J2", checks.j2, repo, data_root, hist_ok)
    c3 = _guard("J3", checks.j3, repo, data_root, pins, hist_ok, out_root)
    c4 = _guard("J4", checks.j4, repo, data_root, pins, hist_ok, tagv, out_root, checks.pin_problems())

    # J5: recomputation
    c5 = checks.Check("J5")
    ctx = None
    try:
        ctx = recompute.Ctx(repo, data_root, now, pins)
        cover, new, old = v2_cover(out_root, data_root, a.j5_sample, a.j5_all)
        findings, info = recompute.run(ctx, v2_cover=cover)
        open_f, new_rows = verdict.j5_adjudicate(findings, out_root, now)
        for f, ref, d in open_f:
            c5.evidence.append(f"[{ref} {d}] {f.area}: {f.subject}: {f.detail}")
        undecided = verdict.undecided(out_root)
        for r in undecided:
            c5.evidence.append(f"awaiting adjudication: {r['ref']} {r['subject']} (since {r['utc']})")
        if undecided:
            c5.status = "warning"
            c5.reasons.append("j5_mismatch")
        c5.evidence.insert(0, f"recomputed: {info}"[:1500])
        c5.evidence.insert(1, f"lab v2 days recomputed this run: {len(cover)} (new {len(new)}, rotating sample "
                              f"{len(old)}); new adjudication rows: {len(new_rows)}")
        checked = sorted(set(info.get("v2", {}).get("checked_days", [])))
        bad_days = {f.subject.split()[-1] for f in findings if f.area == "v2"}
        write_csv_append(out_root / J5_LOG, J5_HEAD,
                         [[iso_s(now), "2", d, "mismatch" if d in bad_days else "ok"] for d in checked])
        for o in verdict.overdue(out_root, now):
            extra.append(f"adjudication overdue (> 7 days): {o['ref']} {o['subject']}")
    except Exception as e:   # noqa: BLE001
        tb = traceback.format_exception_only(type(e), e)[-1].strip()
        c5.warn("unverified", f"the judge could not complete the recomputation: {tb[:300]}")

    if ctx is not None:
        c6 = _guard("J6", lambda: checks.j6(ctx, out_root, now, lab_vs_c1(data_root))[0])
    else:
        c6 = checks.Check("J6")
        c6.warn("unverified", "J6 needs the recomputation inputs, which could not be loaded")
    c7 = _guard("J7", checks.j7, repo, data_root, now)
    c8 = _guard("J8", checks.j8, repo, out_root, hist_ok)
    if a.no_network:
        c9 = _guard("J9", checks.j9, data_root, out_root, now, env={})
    else:
        c9 = _guard("J9", checks.j9, data_root, out_root, now)
    allc = [c1, c2, c3, c4, c5, c6, c7, c8, c9]

    v, code, ok, since, lines = verdict.decide(allc, out_root, now)
    extra += lines
    jsha = sha256_bytes(checks.judge_manifest_text(repo).encode())
    verdict.record(out_root, now, head, v, code, ok, len(allc), since, jsha, allc)
    p = publish.write_all(out_root, now, head, v, code, ok, len(allc), allc, extra, jsha)
    print(f"judge {iso_s(now)}: {v} ({code}), checks ok {ok}/{len(allc)}; wrote {p}")
    for c in allc:
        print(f"  {c.id}: {c.status}" + (f" [{', '.join(sorted(set(c.reasons)))}]" if c.reasons else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
