"""Lab v2 seeds, the online signal and the online-vs-full causality audit (SYSTEM_V2_PREREG.md §2.1, §2.2).
FROZEN (lab v2).

Seeds (vendored byte-identically from xauusd-quant research/hunt/candidates, see vendor/SHA256SUMS), loaded with the
harness's own importer (harness._import):

| id | file | TF | HOLD |
|---|---|---|---|
| S2 | levels__watched_level_break.py | M5 | 24 |
| S3 | r3_ctaflow__cta_flip_flow_usmorning.py | M15 | 8 |
| S4 | r2_orb__inplay_comex_orb60.py | M5 | 48 |
| S5 | r2_exhaustion__databar_stretch_settle.py | M15 | 14 |

Signal values are normalised exactly as harness.trades does: reindex to the bars, fillna(0), clip(−1, 1), round,
astype(int).
- Full-data value at bar b: the normalised signal(all bars available at this run) at b.
- Online value at bar b: the normalised signal(bars[: b + 1]) at b, i.e. the seed run on the bars up to and including
  b only. The traded signal is the online value (§2.2).
- T = the signal bar's close = its start + TF minutes (minutes of the bar's model day; 1440 for a bar starting
  at 24:00 − TF).
- Eligibility window of a bar: T >= 01:30 and T + HOLD·TF <= 23:30 model (22:45 on a Friday).
- Audit (§2.2): for each newly settled day and every bar of that day inside the eligibility window, online value ==
  full-data value; any difference halts v2 and voids the seed (L2 §7.3). Online values are computed for every bar of
  the day (decisions use them, including abstain_window rows); a difference outside the window is counted but does
  not halt.
"""
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

import v2_data

SEEDS = (("S2", "levels__watched_level_break.py", "M5", 24),
         ("S3", "r3_ctaflow__cta_flip_flow_usmorning.py", "M15", 8),
         ("S4", "r2_orb__inplay_comex_orb60.py", "M5", 48),
         ("S5", "r2_exhaustion__databar_stretch_settle.py", "M15", 14))
TF_MIN = {"M5": 5, "M15": 15}
WIN_FIRST_T = 90           # 01:30
WIN_EXIT_MAX = 1410        # 23:30
WIN_EXIT_MAX_FRI = 1365    # 22:45

_MODS = {}


def seed_table():
    return {s[0]: {"file": s[1], "tf": s[2], "hold": s[3]} for s in SEEDS}


def load_seed(sid):
    """The seed module (harness._import of the vendored file), checked against the prereg's TF and HOLD."""
    if sid not in _MODS:
        t = seed_table()[sid]
        mod = v2_data.harness()._import(v2_data.CANDIDATES / t["file"])
        if mod.TF != t["tf"] or int(mod.HOLD) != t["hold"]:
            raise ValueError(f"{sid}: TF/HOLD {mod.TF}/{mod.HOLD} differ from the prereg {t['tf']}/{t['hold']}")
        _MODS[sid] = mod
    return _MODS[sid]


def normalise(sig, index):
    """harness.trades: reindex, fillna(0), clip(−1, 1), round, astype(int)."""
    return sig.reindex(index).fillna(0).clip(-1, 1).round().astype(int)


def full_values(mod, bars):
    """Full-data values of every bar (int array)."""
    return normalise(mod.signal(bars), bars.index).to_numpy()


def online_value(mod, bars, i):
    """The online value at bar position i: the seed run on bars[: i + 1], read at its last bar."""
    part = bars.iloc[: i + 1]
    s = mod.signal(part)
    return int(normalise(s, part.index[-1:]).iloc[0])


def bar_T(start, tf_min):
    """Close of the bar starting at `start` (minutes of its model day)."""
    return start.hour * 60 + start.minute + tf_min


def in_window(T, hold_min, weekday):
    return T >= WIN_FIRST_T and T + hold_min <= (WIN_EXIT_MAX_FRI if weekday == 4 else WIN_EXIT_MAX)


@dataclass
class DaySignals:
    """One seed's bars on one model day: start minute, T, online and full values, window flag."""
    sid: str
    day: pd.Timestamp
    tf_min: int
    hold_min: int
    start: list = field(default_factory=list)
    T: list = field(default_factory=list)
    online: list = field(default_factory=list)
    full: list = field(default_factory=list)
    window: list = field(default_factory=list)

    def mismatches(self, inside=True):
        return [k for k in range(len(self.T)) if self.window[k] == inside and self.online[k] != self.full[k]]


def day_signals(sid, bars, full, day, online=True):
    """DaySignals of seed `sid` on model day `day` from its TF bars and their full-data values.

    online=False fills the online values with the full-data ones (the tripwire's recomputation, §2.2 note in the
    implementation register)."""
    mod = load_seed(sid)
    tf_min = TF_MIN[mod.TF]
    hold_min = int(mod.HOLD) * tf_min
    day = pd.Timestamp(day).normalize()
    pos = np.flatnonzero((bars.day == day).to_numpy())
    out = DaySignals(sid=sid, day=day, tf_min=tf_min, hold_min=hold_min)
    for i in pos:
        st = bars.index[i]
        T = bar_T(st, tf_min)
        out.start.append(st.hour * 60 + st.minute)
        out.T.append(T)
        out.full.append(int(full[i]))
        out.online.append(online_value(mod, bars, int(i)) if online else int(full[i]))
        out.window.append(bool(in_window(T, hold_min, day.dayofweek)))
    return out
