"""Rule grammar L2G-1 (L2 draft §5, adopted by SYSTEM_V1_PREREG.md §3, adapted to M15 mid bars). FROZEN: grammar.

A spec is a JSON object:
  T          "HHMM", decision time on the model clock, 15-minute grid, 01:45 <= T <= 23:15
  side       ["LONG"] | ["SHORT"] | ["FOLLOW", a, b] | ["FADE", a, b]   (FOLLOW = sign of MOVE(a,b), FADE = minus it)
             ["COIN"] is the coin control C1 only (REF, never promotable, never proposed)
  when       0, 1 or 2 predicates [FEAT, a, b, OP, theta], joined by AND
  FEAT       MOVE | ABSMOVE | RANGE | POS | LWICK | UWICK ;  OP  GE | LE
  theta      decimal string with at most 2 decimals, |theta| <= 9.99, canonical form "-?D.DD"
  hold       integer h >= 1 with T + 15h <= 23:30
  stop       H10 | S10
  days       weekday mask 1..31 (Mon 1, Tue 2, Wed 4, Thu 8, Fri 16)
  skip_event 0 | 1
Windows: 01:30 <= a < b <= T on the 15-minute grid; W = the M15 bars starting in [a, b); O(a) = open of the bar
starting at a; C(b) = close of the bar ending at b. Features are in units of U = C(T)·(exp(F_RAW_H1(slot of T)/1e4) − 1).

Decision on day d at T (L2 §5.3 plus the v1 amendments): trigger iff the day is eligible (weekday in `days`, not an
NYSE full closure or early close, not an event day when skip_event = 1, d >= first_day, and on a Friday T + 15h <=
22:45, §3 item 4), every window bar and the bar ending at T is a valid M15 bar, U is defined and positive, the stop's
forecast is finite and positive, every predicate holds and side != 0. Outcomes: trigger, no_trigger, abstain_day, abstain_data, abstain_U.
"""
import hashlib
import json
import re
from decimal import Decimal

import numpy as np

GRAMMAR_VERSION = 1
FEATURES = ("MOVE", "ABSMOVE", "RANGE", "POS", "LWICK", "UWICK")
OPS = ("GE", "LE")
STOPS = {"H10": 1.049036930300697, "S10": 1.0540339626212611}
SIDE_MODES = ("LONG", "SHORT", "FOLLOW", "FADE", "COIN")
T_MIN, T_MAX = 105, 1395            # 01:45, 23:15 in minutes
WIN_MIN = 90                        # 01:30
EXIT_MAX = 1410                     # 23:30
FRIDAY_EXIT_MAX = 1365              # 22:45 (§3 item 4)
THETA_RE = re.compile(r"^-?\d(\.\d{1,2})?$")
OUTCOMES = ("trigger", "no_trigger", "abstain_day", "abstain_data", "abstain_U")


class SpecError(ValueError):
    pass


def hhmm(m):
    return f"{m // 60:02d}{m % 60:02d}"


def minutes(s):
    if not isinstance(s, str) or not re.fullmatch(r"\d{4}", s):
        raise SpecError(f"time {s!r} is not HHMM")
    h, m = int(s[:2]), int(s[2:])
    if h > 23 or m > 59:
        raise SpecError(f"time {s!r} out of range")
    return h * 60 + m


def canon_theta(t):
    if not isinstance(t, str) or not THETA_RE.match(t):
        raise SpecError(f"theta {t!r} must be a decimal string with at most 2 decimals")
    d = Decimal(t)
    if abs(d) > Decimal("9.99"):
        raise SpecError(f"|theta| {t} > 9.99")
    return f"{d:.2f}"


def _window(a, b, T):
    am, bm = minutes(a), minutes(b)
    if am % 15 or bm % 15:
        raise SpecError("window bounds must be on the 15-minute grid")
    if not (WIN_MIN <= am < bm <= T):
        raise SpecError(f"window [{a}, {b}) must satisfy 01:30 <= a < b <= T")
    return am, bm


def validate(spec, allow_coin=False):
    """Validated canonical copy of `spec` (raises SpecError)."""
    if not isinstance(spec, dict):
        raise SpecError("spec must be an object")
    need = {"T", "side", "when", "hold", "stop", "days", "skip_event"}
    if set(spec) != need:
        raise SpecError(f"fields must be exactly {sorted(need)}")
    T = minutes(spec["T"])
    if T % 15 or not (T_MIN <= T <= T_MAX):
        raise SpecError("T must be on the 15-minute grid in [01:45, 23:15]")
    side = spec["side"]
    if not isinstance(side, list) or not side or side[0] not in SIDE_MODES:
        raise SpecError(f"bad side {side!r}")
    if side[0] in ("LONG", "SHORT") or side[0] == "COIN":
        if len(side) != 1:
            raise SpecError("LONG/SHORT/COIN take no window")
        if side[0] == "COIN" and not allow_coin:
            raise SpecError("COIN is reserved for the coin control")
        side_c = [side[0]]
    else:
        if len(side) != 3:
            raise SpecError("FOLLOW/FADE take a window [a, b]")
        _window(side[1], side[2], T)
        side_c = [side[0], side[1], side[2]]
    when = spec["when"]
    if not isinstance(when, list) or len(when) > 2:
        raise SpecError("when holds 0, 1 or 2 predicates")
    when_c = []
    for p in when:
        if not isinstance(p, list) or len(p) != 5:
            raise SpecError(f"bad predicate {p!r}")
        feat, a, b, op, th = p
        if feat not in FEATURES:
            raise SpecError(f"unknown feature {feat!r}")
        if op not in OPS:
            raise SpecError(f"unknown op {op!r}")
        _window(a, b, T)
        when_c.append([feat, a, b, op, canon_theta(th)])
    hold = spec["hold"]
    if not isinstance(hold, int) or isinstance(hold, bool) or hold < 1 or T + 15 * hold > EXIT_MAX:
        raise SpecError("hold must be an integer >= 1 with T + 15*hold <= 23:30")
    if spec["stop"] not in STOPS:
        raise SpecError(f"unknown stop {spec['stop']!r}")
    days = spec["days"]
    if not isinstance(days, int) or isinstance(days, bool) or not (1 <= days <= 31):
        raise SpecError("days must be a mask in 1..31")
    if spec["skip_event"] not in (0, 1) or isinstance(spec["skip_event"], bool):
        raise SpecError("skip_event must be 0 or 1")
    return {"T": spec["T"], "side": side_c, "when": when_c, "hold": hold, "stop": spec["stop"], "days": days,
            "skip_event": spec["skip_event"]}


def canonical_json(spec, allow_coin=False):
    return json.dumps(validate(spec, allow_coin), sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def spec_sha256(spec, allow_coin=False):
    return hashlib.sha256(canonical_json(spec, allow_coin).encode("utf-8")).hexdigest()


def question_key(spec):
    """L2 §10.4: the spec without its side mode (FOLLOW = FADE, LONG = SHORT)."""
    s = validate(spec, allow_coin=True)
    s["side"] = ["DIR", s["side"][1], s["side"][2]] if len(s["side"]) == 3 else ["FIXED"]
    return json.dumps(s, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


# ---------------------------------------------------------------- features and decisions
def _bar_index(day_bars):
    """{minute of day: row} for the day's M15 bars (bars.lab_bars rows of one model day)."""
    st = day_bars.start
    mins = (st.dt.hour * 60 + st.dt.minute).values
    return {int(m): i for i, m in enumerate(mins)}


class DayBars:
    """The M15 mid bars of one model day as arrays keyed by start minute."""

    def __init__(self, day_bars):
        self.idx = _bar_index(day_bars)
        self.o = day_bars.o.values.astype(float)
        self.h = day_bars.h.values.astype(float)
        self.l = day_bars.l.values.astype(float)
        self.c = day_bars.c.values.astype(float)
        self.valid = day_bars.valid.values.astype(bool)

    def ok(self, start):
        i = self.idx.get(start)
        return i is not None and self.valid[i]

    def window_ok(self, a, b):
        return all(self.ok(m) for m in range(a, b, 15))

    def O(self, a):
        return self.o[self.idx[a]]

    def C(self, b):
        return self.c[self.idx[b - 15]]

    def hilo(self, a, b):
        ii = [self.idx[m] for m in range(a, b, 15)]
        return float(np.max(self.h[ii])), float(np.min(self.l[ii]))


def feature(db, feat, a, b, U):
    """Feature value, or None when undefined (POS with a zero range)."""
    o, c = db.O(a), db.C(b)
    hi, lo = db.hilo(a, b)
    if feat == "MOVE":
        return (c - o) / U
    if feat == "ABSMOVE":
        return abs(c - o) / U
    if feat == "RANGE":
        return (hi - lo) / U
    if feat == "POS":
        den = hi - lo
        return None if not den > 0 else (c - lo) / den
    if feat == "LWICK":
        return (min(o, c) - lo) / U
    if feat == "UWICK":
        return (hi - max(o, c)) / U
    raise SpecError(feat)


def coin_side(day):
    """C1 (L2 §8.3): +1 if int(sha256("L2-C1|YYYY-MM-DD")[:8], 16) is even, else -1."""
    h = hashlib.sha256(f"L2-C1|{str(day)[:10]}".encode()).hexdigest()
    return 1 if int(h[:8], 16) % 2 == 0 else -1


def slot_of(T):
    """H1 slot (0 = 01:00 hour) of decision minute T."""
    return T // 60 - 1


def day_eligible(spec, day, weekday, first_day, holiday, event_day):
    """Day rules of §5.3 item 1 plus Friday eligibility (§3 item 4). Roll days do not exist on Dukascopy."""
    T = minutes(spec["T"])
    if not (spec["days"] >> weekday) & 1:
        return False
    if holiday:
        return False
    if spec["skip_event"] and event_day:
        return False
    if first_day is None or str(day)[:10] < str(first_day)[:10]:
        return False
    if weekday == 4 and T + 15 * spec["hold"] > FRIDAY_EXIT_MAX:
        return False
    return True


def decide(spec, db, day, weekday, first_day, holiday, event_day, F_H1, F_S):
    """Decision record: outcome, side, U and the feature values (in predicate order)."""
    s = validate(spec, allow_coin=True)
    T = minutes(s["T"])
    rec = {"outcome": None, "side": 0, "U": np.nan, "feats": []}
    if not day_eligible(s, day, weekday, first_day, holiday, event_day):
        rec["outcome"] = "abstain_day"
        return rec
    wins = [(minutes(p[1]), minutes(p[2])) for p in s["when"]]
    if len(s["side"]) == 3:
        wins.append((minutes(s["side"][1]), minutes(s["side"][2])))
    if not db.ok(T - 15) or not all(db.window_ok(a, b) for a, b in wins):
        rec["outcome"] = "abstain_data"
        return rec
    F_stop = F_H1 if s["stop"] == "H10" else F_S
    C_T = db.C(T)
    U = C_T * (np.exp(F_H1 / 1e4) - 1) if np.isfinite(F_H1) else np.nan
    if not (np.isfinite(U) and U > 0 and np.isfinite(F_stop) and F_stop > 0):
        rec["outcome"] = "abstain_U"
        return rec
    rec["U"] = U
    ok = True
    for p in s["when"]:
        v = feature(db, p[0], minutes(p[1]), minutes(p[2]), U)
        if v is None:
            rec["outcome"] = "abstain_data"
            return rec
        rec["feats"].append(v)
        th = float(p[4])
        ok = ok and (v >= th if p[3] == "GE" else v <= th)
    mode = s["side"][0]
    if mode == "LONG":
        side = 1
    elif mode == "SHORT":
        side = -1
    elif mode == "COIN":
        side = coin_side(day)
    else:
        mv = feature(db, "MOVE", minutes(s["side"][1]), minutes(s["side"][2]), U)
        side = int(np.sign(mv)) * (1 if mode == "FOLLOW" else -1)
    if not ok or side == 0:
        rec["outcome"] = "no_trigger"
        return rec
    rec["outcome"] = "trigger"
    rec["side"] = side
    return rec
