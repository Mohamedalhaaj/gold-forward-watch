"""§16.18 A15 (2026-10-29): reviews, as the judge rebuilds them from the register text. R-AN-92's open set, its options
and the `review` block of `analyst-context/5`, with the `XAUUSD_M30R` request; R-AN-94's overlap weights and clusters.
§16.18 A17 (2026-11-06): the open set with extensions (A17-R7), the subject of a time window (A17-R2) and the `review`
block of `analyst-context/6` (A17-R5).
Pure functions: the judge's own reading of the records feeds them (jlib/judge.py)."""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field

from . import td
from .common import fmt_utc, is_utc, parse_utc, rel_eq

M30R_REQ = "XAUUSD_M30R"
HALF = dt.timedelta(minutes=30)
NORMAL_ACTIONS = ["buy", "sell", "stay_out"]
REVIEW_STATUSES = ("review_hold", "review_close")
REVIEW_ACTIONS = ("hold", "close", "reverse", "add")
TRADE_ACTIONS = ("buy", "sell", "reverse", "add")
NOTE = (" review prices come from Twelve Data 30-minute bars in UTC and are indicative; settlement uses Dukascopy "
        "minutes, where an open trade may already have reached its stop or target.")
BLOCK_KEYS = ("open", "options", "ref_px", "ref_utc")
OPEN_KEYS = ("call_id", "action", "side", "entry_utc", "exit_utc", "stop_usd", "target_usd", "stop_mult",
             "target_mult", "entry_px", "move_usd", "move_r", "high_since_entry", "low_since_entry", "stop_touched",
             "target_touched", "minutes_left")
REL_KEYS = ("move_usd", "move_r")                 # R-AN-68 (A15): relative 1e-9; every other value exact
# §16.18 A17-R5, R-AN-23 (analyst-context/6): the block's kind and extend_until_utc, open[].extended after exit_utc
EXTEND = "review_extend"                          # A17-R6: the status of `extend`
TIME_OPTIONS = ["extend", "close"]
KIND_REVIEW, KIND_TIME = "review", "time"
BLOCK_KEYS_V6 = ("kind", "open", "options", "ref_px", "ref_utc", "extend_until_utc")
OPEN_KEYS_V6 = OPEN_KEYS[:OPEN_KEYS.index("exit_utc") + 1] + ("extended",) + OPEN_KEYS[OPEN_KEYS.index("exit_utc") + 1:]
MIN_EXTENSION = dt.timedelta(minutes=60)          # A17-D3: exit_utc <= day_end(d) − 60 min


def options(n: int):
    """R-AN-92's options for |O(R)| = n, in its order: None for a window that is not a review. Judge decision
    (README J-D61): more than two open trades (A15 `open_cap`) are judged with the two-trade options."""
    if n <= 0:
        return None
    return ["hold", "close", "reverse", "add"] if n == 1 else ["hold", "close"]


# ---------------------------------------------------------------- the open set (R-AN-92)

@dataclass
class OpenSets:
    open: dict = field(default_factory=dict)        # call_id -> [call_ids of O(R)] in window order
    closed_by: dict = field(default_factory=dict)   # trade call_id -> the closing window's call_id
    eff_exit: dict = field(default_factory=dict)    # trade call_id -> eff_exit (datetime)
    managed: dict = field(default_factory=dict)     # trade call_id -> entry of its closing window (datetime)
    extended: dict = field(default_factory=dict)    # §16.18 A17-R7: trade call_id -> the time window that extended it
    flags: dict = field(default_factory=dict)       # A17-R5: call_id -> [extended at R, for each trade of O(R)]
    time_of: dict = field(default_factory=dict)     # A17-R9: trade call_id -> the time window at its exit (X(w))


def is_trade(status) -> bool:
    return status == "called"


def is_time(w) -> bool:
    """A time window `<d>_X<hhmm>` (§16.18 A17-R1)."""
    return bool(w.get("time")) or str(w.get("cid", "")).rsplit("_", 1)[-1].startswith("X")


def closes(status, action) -> bool:
    return status == "review_close" or (status == "called" and action == "reverse")


def open_sets(wins, day_end: dt.datetime | None = None) -> OpenSets:
    """R-AN-92 over one model day of one mode. `wins`: the day's windows in window order, each a dict with `cid`,
    `entry`, `exit` (datetimes), `status` (its call status: the terminal's for the judge), `action` (its plan's
    action or None) and `names` (the call_ids its context's `review.open` names, or None). A trade is a `called`
    window; a `review_close` or `called` reverse window closes the trades of its O that its context names.
    (§16.18 A17-R7) day_end: day_end(d) for a model day >= a17_from (None before it: no extension). A time window
    closes nothing, opens nothing and is a review of no trade; with status `review_extend` and its context's
    `review.open` naming its subject (the trade whose exit is its entry, not closed before), that trade's eff_exit is
    day_end(d) for the windows after it, and a later closing window may close it there. A trade is extended once."""
    out = OpenSets()
    trades = []
    for w in wins:
        e = w["entry"]
        O = [t["cid"] for t in trades if out.eff_exit[t["cid"]] > e]
        out.open[w["cid"]] = O
        out.flags[w["cid"]] = [cid in out.extended for cid in O]
        if is_time(w):
            for t in trades:
                if t["exit"] == e:
                    out.time_of.setdefault(t["cid"], w["cid"])
            if day_end is not None and w["status"] == EXTEND:
                names = set(w.get("names") or [])
                for t in trades:
                    cid = t["cid"]
                    if cid in names and t["exit"] == e and cid not in out.closed_by and cid not in out.extended:
                        out.extended[cid] = w["cid"]
                        out.eff_exit[cid] = day_end
            continue
        if closes(w["status"], w.get("action")):
            names = set(w.get("names") or [])
            for cid in O:
                if cid in names and cid not in out.closed_by:
                    out.closed_by[cid] = w["cid"]
                    out.managed[cid] = e
                    out.eff_exit[cid] = e
        if is_trade(w["status"]):
            trades.append(w)
            out.eff_exit[w["cid"]] = w["exit"]
    return out


def max_open(r: OpenSets) -> int:
    return max((len(v) for v in r.open.values()), default=0)


def subject_at(wins, e: dt.datetime, day_end: dt.datetime):
    """§16.18 A17-R2: the subject of a time window entering at e (its check T = e − 30 min): the trade w of d with
    exit_utc(w) = e whose eff_exit, by A17-R7 for a window entering at e, equals exit_utc(w) (no earlier window
    closed it), if exit_utc(w) <= day_end(d) − 60 min; else None. `wins` as for `open_sets`."""
    before = [w for w in wins if w["entry"] < e]
    r = open_sets(before, day_end)
    for w in before:
        if is_time(w) or not is_trade(w["status"]):
            continue
        if w["exit"] == e and r.eff_exit.get(w["cid"]) == w["exit"] and w["exit"] <= day_end - MIN_EXTENSION:
            return w["cid"]
    return None


# ---------------------------------------------------------------- the `review` block (R-AN-92)

def floor_half(t: dt.datetime) -> dt.datetime:
    return t.replace(minute=0 if t.minute < 30 else 30, second=0, microsecond=0)


def m30r_needed(trades, asof: dt.datetime) -> bool:
    """`context` makes `XAUUSD_M30R` iff O(R) is not empty and some trade has entry_utc + 30 min <= asof_utc."""
    return any(parse_utc(t["entry_utc"]) + HALF <= asof for t in trades)


def m30r_bounds(trades, asof: dt.datetime):
    """(A, B): A = the earliest entry_utc of O(R), B = asof_utc floored to the half hour."""
    return min(parse_utc(t["entry_utc"]) for t in trades), floor_half(asof)


def m30r_url(a: dt.datetime, b: dt.datetime) -> str:
    """R-AN-90's URL with A and B (R-AN-87's form)."""
    return (f"{td.BASE}?symbol=XAU/USD&interval=30min&start_date={td.td_time(a)}"
            f"&end_date={td.td_time(b)}&timezone=UTC&order=asc&outputsize=5000&dp=5")


def m30r_problems(f, a: dt.datetime, b: dt.datetime, asof: dt.datetime) -> list:
    """R-AN-87's provenance rules for the `XAUUSD_M30R` request (A4): R-AN-90's URL with (A, B), and its `bars`
    every element with A <= t_utc and t_utc + 30 min <= asof_utc (so t_utc <= B − 30 min), in time order."""
    from . import watch
    if not isinstance(f, dict) or set(f) != td.PROV_KEYS:
        return ["keys"]
    out = [p for p in td.provenance_problems(dict(f, bars=[]), M30R_REQ, m30r_url(a, b), set(), asof)
           if not p.startswith("bars")]
    if f.get("status") == "ok":
        out += watch.m30_bar_problems(f.get("bars"), a, b - HALF, f.get("values_n"))
    return out


def ok_m30r_bars(f) -> list:
    """M: the bars of an `ok` `XAUUSD_M30R` provenance whose bars are numbers with UTC times, else []."""
    if not isinstance(f, dict) or f.get("status") != "ok" or not isinstance(f.get("bars"), list):
        return []
    out = []
    for x in f["bars"]:
        if not isinstance(x, dict) or not is_utc(x.get("t_utc")) or \
                not all(td._num(x.get(k)) for k in ("o", "h", "l", "c")):
            return []
        out.append(x)
    return sorted(out, key=lambda x: x["t_utc"])


def _side_name(s) -> str | None:
    return {1: "buy", -1: "sell"}.get(s)


def open_entry(t: dict, e_r: dt.datetime, bars: list, ref_px, ref_utc) -> dict:
    """One `review.open` object for trade t (its call file's fields: call_id, action, side, entry_utc, exit_utc, S,
    T, stop_mult, target_mult), with M = `bars`, every expression evaluated as R-AN-92 writes it."""
    s = t["side"]
    entry = t["entry_utc"]
    ep = next((x["o"] for x in bars if x["t_utc"] == entry), None)
    move = move_r = None
    if ep is not None and ref_px is not None and parse_utc(ref_utc) > parse_utc(entry):
        move = s * (ref_px - ep)
        move_r = move / t["S"]
    since = [x for x in bars if x["t_utc"] >= entry]
    hi = max(x["h"] for x in since) if since else None
    lo = min(x["l"] for x in since) if since else None
    st = tg = None
    if ep is not None and hi is not None and lo is not None:
        if s == 1:
            st, tg = lo <= ep - t["S"], hi >= ep + t["T"]
        else:
            st, tg = hi >= ep + t["S"], lo <= ep - t["T"]
    left = int((parse_utc(t["exit_utc"]) - e_r).total_seconds() // 60)
    vals = (t["call_id"], t["action"], _side_name(s), entry, t["exit_utc"], t["S"], t["T"], t["stop_mult"],
            t["target_mult"], ep, move, move_r, hi, lo, st, tg, left)
    return dict(zip(OPEN_KEYS, vals))


def review_block(trades, e_r: dt.datetime, bars) -> dict | None:
    """The `review` block (R-AN-92) for the trades of O(R) in window order, R's entry e_r and M = `bars` (the recorded
    `XAUUSD_M30R` bars, [] when the request was not made or is not `ok`). None when O(R) is empty."""
    if not trades:
        return None
    bars = sorted(bars or [], key=lambda x: x["t_utc"])
    ref_px = ref_utc = None
    if bars:
        ref_px = bars[-1]["c"]
        ref_utc = fmt_utc(parse_utc(bars[-1]["t_utc"]) + HALF)
    return {"open": [open_entry(t, e_r, bars, ref_px, ref_utc) for t in trades], "options": options(len(trades)),
            "ref_px": ref_px, "ref_utc": ref_utc}


def review_block_v6(trades, e_r: dt.datetime, bars, kind: str, day_end: dt.datetime, extended) -> dict | None:
    """The `analyst-context/6` `review` block (§16.18 A17-R5): `/5`'s block with `kind` first and `extend_until_utc`
    last. kind `review` (R-AN-92's review; options as before, extend_until_utc null) or `time` (a time window: open =
    [the subject], options ["extend", "close"], extend_until_utc = day_end(d)). Each `open` element gains `extended`
    (`extended[i]`) right after `exit_utc`; its `exit_utc` and `minutes_left` use the trade's current exit: day_end(d)
    when extended, else exit_utc. Every other value as for `/5`. None when `trades` is empty."""
    if not trades:
        return None
    flags = [x is True for x in (extended or [])]                    # a recorded non-bool is no extension
    flags += [False] * (len(trades) - len(flags))
    cur = [dict(t, exit_utc=fmt_utc(day_end)) if x is True else t for t, x in zip(trades, flags)]
    b = review_block(cur, e_r, bars)
    opens = []
    for o, x in zip(b["open"], flags):
        opens.append({k: (x if k == "extended" else o[k]) for k in OPEN_KEYS_V6})
    timed = kind == KIND_TIME
    return {"kind": kind, "open": opens, "options": list(TIME_OPTIONS) if timed else b["options"],
            "ref_px": b["ref_px"], "ref_utc": b["ref_utc"], "extend_until_utc": fmt_utc(day_end) if timed else None}


def _same(a, b) -> bool:
    return a == b and type(a) is type(b)


def compare_review_v6(exp, rec) -> list:
    """R-AN-68 (A15, A17): `/6`'s block as `/5`'s, plus `kind`, `extend_until_utc` and each `open[].extended`, all
    exact."""
    if exp is None or rec is None:
        return [] if exp is None and rec is None else ["review"]
    if not isinstance(rec, dict) or set(rec) != set(BLOCK_KEYS_V6):
        return ["review.keys"]
    out = [f"review.{k}" for k in ("kind", "options", "ref_utc", "extend_until_utc") if not _same(rec[k], exp[k])]
    if not _same(rec["ref_px"], exp["ref_px"]):
        out.append("review.ref_px")
    ro, eo = rec["open"], exp["open"]
    if not isinstance(ro, list) or len(ro) != len(eo):
        return sorted(out) + ["review.open"]
    for i, (a, b) in enumerate(zip(eo, ro)):
        if not isinstance(b, dict) or set(b) != set(OPEN_KEYS_V6):
            out.append(f"review.open[{i}].keys")
            continue
        for k in OPEN_KEYS_V6:
            if k in REL_KEYS:
                ok = (a[k] is None and b[k] is None) or (a[k] is not None and rel_eq(b[k], a[k]))
            elif isinstance(a[k], (int, float)) and not isinstance(a[k], bool):
                ok = isinstance(b[k], (int, float)) and not isinstance(b[k], bool) and b[k] == a[k]
            else:
                ok = _same(b[k], a[k])
            if not ok:
                out.append(f"review.open[{i}].{k}")
    return sorted(out)


def compare_review(exp, rec) -> list:
    """R-AN-68 (A15): the block's prices, booleans, times and minutes exact; move_usd and move_r relative 1e-9."""
    if exp is None or rec is None:
        return [] if exp is None and rec is None else ["review"]
    if not isinstance(rec, dict) or set(rec) != set(BLOCK_KEYS):
        return ["review.keys"]
    out = [f"review.{k}" for k in ("options", "ref_utc") if rec[k] != exp[k]]
    if not _same(rec["ref_px"], exp["ref_px"]):
        out.append("review.ref_px")
    ro, eo = rec["open"], exp["open"]
    if not isinstance(ro, list) or len(ro) != len(eo):
        return out + ["review.open"]
    for i, (a, b) in enumerate(zip(eo, ro)):
        if not isinstance(b, dict) or set(b) != set(OPEN_KEYS):
            out.append(f"review.open[{i}].keys")
            continue
        for k in OPEN_KEYS:
            if k in REL_KEYS:
                ok = (a[k] is None and b[k] is None) or (a[k] is not None and rel_eq(b[k], a[k]))
            elif isinstance(a[k], (int, float)) and not isinstance(a[k], bool):
                ok = isinstance(b[k], (int, float)) and not isinstance(b[k], bool) and b[k] == a[k]
            else:
                ok = _same(b[k], a[k])
            if not ok:
                out.append(f"review.open[{i}].{k}")
    return out


# ---------------------------------------------------------------- overlap weights and clusters (R-AN-94)

def overlap_weights(trades) -> dict:
    """{call_id: (weight, cluster)} over one mode's settled trades [(call_id, entry, x_end)] in window order: a and b
    overlap iff entry(a) < x_end(b) and entry(b) < x_end(a); weight 0.5 with an overlap, else 1.0; a cluster is a
    connected component of the overlap relation, named by its first trade in window order."""
    n = len(trades)
    parent = list(range(n))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i
    hit = [False] * n
    for i in range(n):
        for j in range(i + 1, n):
            a, b = trades[i], trades[j]
            if a[1] < b[2] and b[1] < a[2]:
                hit[i] = hit[j] = True
                ri, rj = find(i), find(j)
                if ri != rj:
                    parent[max(ri, rj)] = min(ri, rj)
    return {trades[i][0]: (0.5 if hit[i] else 1.0, trades[find(i)][0]) for i in range(n)}
