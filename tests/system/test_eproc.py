"""E-process, e-LOND thresholds, promotion conjuncts, demotion, retirement and the interpreter flag (§3 items 7-8)."""
import numpy as np
import pytest

from lab import eproc


def test_e_and_k_by_hand():
    y = [0.5, -1.0, 2.0]
    lam = eproc.LAMBDAS
    E = np.mean([np.prod([1 + l * v for v in y]) for l in lam])
    K = np.mean([np.prod([1 - l * v for v in y]) for l in lam])
    assert eproc.e_value(y) == pytest.approx(E, rel=1e-15)
    assert eproc.k_value(y) == pytest.approx(K, rel=1e-15)
    assert eproc.e_value([]) == 1.0
    assert list(eproc.e_path(y)) == pytest.approx([eproc.e_value(y[:i]) for i in (1, 2, 3)])
    assert min(1 - max(lam) * 2, 1 + max(lam) * -2) > 0           # every factor >= 0.2 > 0 at the clip


def test_e_star_values_of_the_spec():
    """§3 item 7: S1 = 83.3 at D = 0, the first proposal 71.4, the second 214; the pool sums to 0.70."""
    assert eproc.e_star(eproc.GAMMA_S1, 0) == pytest.approx(83.333, abs=1e-3)
    assert eproc.e_star(eproc.gamma_proposal(1), 0) == pytest.approx(71.43, abs=1e-2)
    assert eproc.e_star(eproc.gamma_proposal(2), 0) == pytest.approx(214.29, abs=1e-2)
    assert eproc.e_star(eproc.GAMMA_S1, 1) == pytest.approx(83.333 / 2, abs=1e-3)
    assert sum(eproc.gamma_proposal(k) for k in range(1, 100000)) == pytest.approx(0.70, abs=1e-5)
    assert eproc.GAMMA_S1 + 0.70 == pytest.approx(1.0)
    assert eproc.alpha_version(1) == 0.04
    # A1 item 5: v >= 2 get 0.01·2^-(v-1), so the program total is 0.04 + 0.01 = 0.05
    assert [eproc.alpha_version(v) for v in (2, 3, 4)] == [0.005, 0.0025, 0.00125]
    assert sum(eproc.alpha_version(v) for v in range(1, 200)) == pytest.approx(0.05, abs=1e-15)


def test_ville_bound_on_null_streams():
    """20,000 null streams of 300 trades (E[y] = 0): P(sup E >= 20) <= 1/20 (plus Monte Carlo error)."""
    rng = np.random.default_rng(20261017)
    hits = 0
    N = 20000
    for c in range(0, N, 2000):
        y = np.clip(rng.normal(0.0, 0.6, size=(2000, 300)), -2, 2)  # symmetric, so E[y] = 0
        paths = np.stack([np.cumprod(1 + lam * y, axis=1) for lam in eproc.LAMBDAS]).mean(axis=0)
        hits += int((paths.max(axis=1) >= 20).sum())
    p = hits / N
    se = np.sqrt(0.05 * 0.95 / N)
    assert p <= 0.05 + 3 * se, p


def trades(n, mean, days_apart=2, side=1, seed=0):
    rng = np.random.default_rng(seed)
    R = rng.normal(mean, 0.45, size=n)
    out = []
    for i, r in enumerate(R):
        d = np.datetime64("2026-11-02") + np.timedelta64(i * days_apart, "D")
        out.append({"day": str(d), "side": side, "y": float(np.clip(r, -2, 2)), "R": float(r),
                    "net_usd": float(r * 5), "net_stress_usd": float(r * 5 - 0.25)})
    return out


def test_promotion_conjuncts():
    good = trades(80, 0.6)
    c = eproc.promotion_checks(good, 83.3, mu_long=0.0, lab_running=True)
    assert c["P1"] and c["P2"] and c["P3"] and c["P4"] and c["P5"] and c["P7"] and c["all"]
    assert not eproc.promotion_checks(good, 83.3, 0.0, lab_running=False)["all"]               # P7
    assert not eproc.promotion_checks(good[:39], 1e-9, 0.0, True)["P2"]                         # n < 40
    short = trades(45, 0.6, days_apart=1)
    assert not eproc.promotion_checks(short, 1e-9, 0.0, True)["P2"]                             # span < 56 days
    assert not eproc.promotion_checks(good, 1e12, 0.0, True)["P1"]
    drift = eproc.promotion_checks(good, 83.3, mu_long=5.0, lab_running=True)                   # P4: drift only
    assert not drift["P4"] and not drift["all"]
    thin = [dict(t, net_stress_usd=-1.0) for t in good]                                        # P3 stress
    assert not eproc.promotion_checks(thin, 83.3, 0.0, True)["P3"]
    one = [dict(t, R=-0.01, y=-0.01, net_usd=0.1) for t in good]
    one[5] = dict(one[5], R=50.0)                                                               # P5: one day
    assert not eproc.promotion_checks(one, 1e-9, 0.0, True)["P5"]


def test_demotion_rules():
    assert eproc.demotion_check([0.1] * 10, [0.1] * 10)[0] is None
    bad = [-2.0] * 12
    assert eproc.demotion_check(bad, bad)[0] == "D1"                  # K >= 10 first
    assert eproc.demotion_check([-0.5] * 10 + [-0.01], [-0.0] * 11)[0] == "D2"
    flat = [0.01] * 99 + [-1.0]                                       # at 100 trades, sum R <= 0
    assert eproc.demotion_check(flat, [0.0] * 100)[0] == "D3"
    assert eproc.demotion_check([0.01] * 99, [0.0] * 99)[0] is None


def test_retirement_and_interpreter_flag():
    assert eproc.retirement_check(150, -0.1, "2026-11-01T00:00Z", "2027-01-01T00:00Z") == "n150"
    assert eproc.retirement_check(149, -0.1, "2026-11-01T00:00Z", "2027-01-01T00:00Z") is None
    assert eproc.retirement_check(10, 1.0, "2026-11-01T00:00Z", "2028-11-01T00:00Z") == "age"
    assert eproc.interpreter_needed(21.0, 83.3, 20, True, False)
    assert not eproc.interpreter_needed(20.0, 83.3, 20, True, False)
    assert not eproc.interpreter_needed(30.0, 83.3, 19, True, False)
    assert not eproc.interpreter_needed(30.0, 83.3, 30, False, False)
    assert eproc.interpreter_needed(1.0, 83.3, 0, False, True)
