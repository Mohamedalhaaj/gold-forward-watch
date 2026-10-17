"""L3 estimator, activation and hysteresis, shrinkage and clamp; the green-suppression (drift) flag; z* (§4, §9)."""
import json

import numpy as np
import pandas as pd
import pytest

import bars
import l3
import system_common as sc


def obs_frame(rows):
    df = pd.DataFrame(rows, columns=["day", "slot", "r", "bucket"])
    d = pd.to_datetime(df.day)
    iso = d.dt.isocalendar()
    df["week"] = (iso.year.astype(int) * 100 + iso.week.astype(int)).values
    df["month"] = d.dt.strftime("%Y-%m").values
    return df


def test_estimator_by_hand():
    rows = [("2026-11-02", 3, 1.2, "N_ASIA"), ("2026-11-03", 3, 1.0, "N_ASIA"), ("2026-11-10", 3, 0.7, "N_ASIA"),
            ("2026-11-17", 3, 1.5, "N_ASIA"), ("2026-11-18", 3, 1.1, "N_ASIA")]
    o = obs_frame(rows)
    n, G, m, se, z = l3.bucket_stats(o, event=False)
    wm = np.array([1.1, 0.7, 1.3])                                   # ISO-week means
    assert (n, G) == (5, 3)
    assert m == pytest.approx(np.mean([1.2, 1.0, 0.7, 1.5, 1.1]))
    assert se == pytest.approx(wm.std(ddof=1) / np.sqrt(3))
    assert z == pytest.approx((m - 1) / se)
    n, G, m, se, z = l3.bucket_stats(o.assign(bucket="CPI"), event=True)
    r = np.array([1.2, 1.0, 0.7, 1.5, 1.1])
    assert se == pytest.approx(r.std(ddof=1) / np.sqrt(5))


def test_eligibility_and_multiplier():
    assert not l3.eligible("N_NY", 500, 7) and l3.eligible("N_NY", 500, 8)
    assert l3.eligible("REOPEN", 40, 8) and not l3.eligible("REOPEN", 400, 7)
    assert not l3.eligible("CPI", 5, 5) and l3.eligible("CPI", 6, 6)
    assert l3.multiplier("N_NY", 100, 8, 1.2) == pytest.approx(1 + 0.2 * 8 / 16)
    assert l3.multiplier("CPI", 6, 6, 1.4) == pytest.approx(1 + 0.4 * 6 / 12)
    assert l3.multiplier("N_NY", 1000, 1000, 2.0) == 1.25                    # clamp
    assert l3.multiplier("N_NY", 1000, 1000, 0.5) == 0.80


def week_obs(month_weeks, mean, sd, bucket="N_NY", seed=0, per_week=20):
    rng = np.random.default_rng(seed)
    rows = []
    for d in month_weeks:
        for i in range(per_week):
            rows.append((str(pd.Timestamp(d).date()), 14, mean + sd * rng.standard_normal(), bucket))
    return obs_frame(rows)


def test_activation_and_hysteresis():
    mondays = pd.date_range("2026-11-02", "2027-02-22", freq="7D")
    strong = week_obs(mondays, 1.3, 0.05)
    rows = l3.update(strong, "2027-01", {}, zstar=3.5)
    ny = next(r for r in rows if r["bucket"] == "N_NY")
    assert ny["eligible"] == 1 and abs(ny["z"]) >= 3.5 and ny["active_after"] == 1
    assert ny["m"] == pytest.approx(l3.multiplier("N_NY", ny["n"], ny["G"], ny["mean_r"]))
    others = [r for r in rows if r["bucket"] != "N_NY"]
    assert all(r["active_after"] == 0 and r["m"] == 1.0 for r in others)
    # an active bucket stays active while |z| >= z*/2, and turns off below it
    o = week_obs(mondays, 1.01, 0.05, seed=3)
    n, G, m, se, z = l3.bucket_stats(o[pd.to_datetime(o.day) < "2027-01-01"], False)
    assert np.isfinite(z) and G >= 8
    zs = 2.0 * abs(z) * 0.9                                                    # so that z*/2 < |z| < z*
    keep = next(r for r in l3.update(o, "2027-01", {"N_NY": True}, zs) if r["bucket"] == "N_NY")
    fresh = next(r for r in l3.update(o, "2027-01", {"N_NY": False}, zs) if r["bucket"] == "N_NY")
    assert keep["active_after"] == 1 and fresh["active_after"] == 0
    off = next(r for r in l3.update(o, "2027-01", {"N_NY": True}, 2.0 * abs(z) * 1.1) if r["bucket"] == "N_NY")
    assert off["active_after"] == 0 and off["m"] == 1.0


def test_ineligible_buckets_never_activate():
    few = week_obs(pd.date_range("2026-11-02", periods=5, freq="7D"), 1.5, 0.01)
    rows = l3.update(few, "2027-01", {"N_NY": True}, zstar=3.5)
    assert next(r for r in rows if r["bucket"] == "N_NY")["active_after"] == 0


def test_due_months_and_current_multipliers():
    assert l3.due_months("2026-12-31", set()) == []
    assert l3.due_months("2027-03-02", {"2027-01"}) == ["2027-02", "2027-03"]
    upd = pd.DataFrame([{"month": "2027-01", "bucket": b, "m": 1.0, "n": 5} for b in sc.BUCKETS] +
                       [{"month": "2027-02", "bucket": b, "m": 1.1 if b == "N_NY" else 1.0, "n": 9}
                        for b in sc.BUCKETS])
    m, asof = l3.current_multipliers(upd)
    assert asof == "2027-02" and m["N_NY"] == (1.1, 9) and m["CPI"] == (1.0, 9)


def test_bucket_is_the_shared_definition():
    assert sc.bucket(14, 1, 1, 0) == "CPI" and sc.bucket(20, 1, 0, 1) == "FOMC" and sc.bucket(14, 1, 0, 0) == "NFP"
    assert sc.bucket(0, 0, 0, 0) == "REOPEN" and sc.bucket(8, 0, 0, 0) == "N_ASIA"
    assert sc.bucket(9, 0, 0, 0) == "N_LONDON" and sc.bucket(13, 0, 0, 0) == "N_LONDON" and sc.bucket(14, 0, 0, 0) == "N_NY"


# ---------------------------------------------------------------- drift flag (green suppression)
def trials_for(blocks, start="2026-11-02", per_day=10):
    """Synthetic GREEN trials per 13-week block with given pooled hit rates (None = an incomplete block)."""
    rows = []
    for k, hr in enumerate(blocks):
        a = pd.Timestamp(start) + pd.Timedelta(days=91 * k)
        for d in pd.date_range(a, a + pd.Timedelta(days=90), freq="D"):
            if d.dayofweek >= 5:
                continue
            for s in range(23):
                entry = 1 if hr is not None else int(s < 5)
                hit = (s < per_day) and hr is not None and ((d.day * 23 + s) % 100) < hr * 100
                rows.append({"day": str(d.date()), "slot": s, "state": sc.GREEN if s < per_day else sc.YELLOW,
                             "entry": entry, "hit_long": int(hit), "hit_short": int(hit)})
    return pd.DataFrame(rows)


def run_blocks(hrs):
    start = pd.Timestamp("2026-11-02")
    end = bars.model_to_utc(start + pd.Timedelta(days=91 * len(hrs)))      # the last block has just ended
    return l3.green_blocks(trials_for(hrs), start, end, set())


def test_drift_flag_suppresses_after_two_high_blocks_and_restores_after_two_in_band():
    rows, ok = run_blocks([0.10, 0.20])
    assert ok == 1
    rows, ok = run_blocks([0.20, 0.20])
    assert ok == 0 and [r["green_ok_after"] for r in rows] == [1, 0]
    rows, ok = run_blocks([0.20, 0.20, 0.10, 0.20, 0.10, 0.10])
    assert [r["green_ok_after"] for r in rows] == [1, 0, 0, 0, 0, 1]
    rows, ok = run_blocks([0.20, None, 0.20])                  # an incomplete block neither counts nor breaks
    assert [r["complete"] for r in rows] == [1, 0, 1] and ok == 0
    rows, ok = run_blocks([0.20, 0.03, 0.20])                  # below 6% breaks the run
    assert ok == 1


def test_judge_green_definition():
    st, rs, c = sc.judge(1, 0, 2, 5, 0, 0, 0, 8.0, 0.25, 1)
    assert st == sc.GREEN and rs == 0
    assert sc.judge(1, 0, 2, 5, 0, 1, 0, 8.0, 0.25, 1)[0] == sc.RED
    assert sc.judge(1, 0, 2, 5, 0, 0, 0, 3.0, 0.25, 1)[0] == sc.YELLOW


def test_zstar_file_follows_the_rule():
    z = json.loads((pytest.ROOT / "reports/system/L3_ZSTAR.json").read_text())
    assert z["paths_per_cell"] >= 20000 and len(z["cells"]) == 18
    assert {(c["rho"], c["icc"]) for c in z["cells"]} == {(r, i) for r in (0.0, 0.3, 0.6) for i in (0.05, 0.15, 0.30)}
    key = f"{z['zstar']:.2f}"
    worst = max(c["p_any_by_z"][key] for c in z["cells"])
    assert worst <= 0.10
    if z["zstar"] > 3.5:
        below = f"{z['zstar'] - 0.25:.2f}"
        assert max(c["p_any_by_z"][below] for c in z["cells"]) > 0.10
    import hashlib
    assert z["l3_sha256"] == hashlib.sha256((pytest.ROOT / "analysis/system/l3.py").read_bytes()).hexdigest()
