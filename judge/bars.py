"""The judge's own bar arithmetic (SYSTEM_V2_PREREG.md §2.2; IMPLEMENTATION_REGISTER R-V1-13, R-V1-14, R-V1-28,
R-V2-6 .. R-V2-8).

- mid M1: per side, frames concatenated in day order, sorted by time, first of duplicates kept; outer join of bid and
  ask on time; mid_x = (bid_x + ask_x) / 2 in double; flats kept; a one-sided minute has NaN mids.
- model frame: the index on the model clock, stable sort.
- lab M15 bars (v1): weekdays, 15-minute bins, first/max/min/last over the rows present, n rows, nvol rows with
  volume on both sides; reindexed to 01:30 .. 23:15; valid = nvol >= 12 and o, c defined.
- seed bars (v2): bins of TF minutes labelled and closed left, first/max/min/last of the non-NaN mids, n = count of
  non-NaN closes, empty bins dropped; `day` = the bar start's model date. No volume filter.
"""
import numpy as np
import pandas as pd

from .common import V2_INPUT_START, to_model

COLS = ("o", "h", "l", "c")


def _side(frames, pre):
    if frames:
        d = pd.concat(frames, ignore_index=True)
    else:
        d = pd.DataFrame({"ts": pd.DatetimeIndex([], tz="UTC"), "o": [], "h": [], "l": [], "c": [], "vol": []})
    d = d.sort_values("ts", kind="mergesort").drop_duplicates("ts", keep="first").set_index("ts")
    return d.rename(columns={**{x: f"{pre}_{x}" for x in COLS}, "vol": f"{pre}_vol"})


def mid_m1(frames):
    """frames: {"BID": [frame, ...], "ASK": [...]} (judge.dukascopy.frame). Returns the UTC-indexed M1 frame."""
    b, a = _side(frames.get("BID", []), "bid"), _side(frames.get("ASK", []), "ask")
    m = b.join(a, how="outer").sort_index()
    for x in COLS:
        m[x] = (m[f"bid_{x}"].to_numpy() + m[f"ask_{x}"].to_numpy()) / 2
    m["spread_c"] = m["ask_c"] - m["bid_c"]
    return m


def model_frame(m):
    """The mid M1 frame on the model clock (tz-naive), stably sorted by model time."""
    out = m.copy()
    out["_utc"] = m.index.tz_convert("UTC").tz_localize(None).values
    out.index = to_model(m.index)
    order = np.argsort(out.index.values, kind="mergesort")
    out = out.iloc[order]
    out.index.name = "ts"
    return out


# ---------------------------------------------------------------- v1 lab M15 bars (R-V1-28)
def lab_m15(mf):
    w = mf[mf.index.dayofweek < 5]
    key = w.index.floor("15min")
    g = w.groupby(key)
    vol = ((w["bid_vol"] > 0) & (w["ask_vol"] > 0)).astype(int)
    agg = pd.DataFrame({"o": g["o"].first(), "h": g["h"].max(), "l": g["l"].min(), "c": g["c"].last(),
                        "n": g["o"].size(), "nvol": vol.groupby(key).sum()})
    days = pd.DatetimeIndex(w.index.normalize().unique()).sort_values()
    offs = pd.to_timedelta(90 + 15 * np.arange((23 * 60 + 15 - 90) // 15 + 1), unit="min")
    starts = pd.DatetimeIndex((days.values[:, None] + offs.values[None, :]).ravel())
    out = agg.reindex(starts)
    out["n"] = out["n"].fillna(0).astype(int)
    out["nvol"] = out["nvol"].fillna(0).astype(int)
    out["valid"] = (out["nvol"] >= 12) & out["o"].notna() & out["c"].notna()
    return out


# ---------------------------------------------------------------- v2 seed bars (R-V2-7, R-V2-8)
def seed_input(mf):
    x = mf[(mf.index >= V2_INPUT_START) & (mf.index.dayofweek < 5)]
    return x[list(COLS)]


def seed_bars(inp, tf_minutes):
    key = inp.index.floor(f"{int(tf_minutes)}min")
    g = inp.groupby(key)
    b = pd.DataFrame({"o": g["o"].first(), "h": g["h"].max(), "l": g["l"].min(), "c": g["c"].last(),
                      "n": g["c"].count()}).dropna()
    b.index.name = "ts"
    b["day"] = b.index.normalize()
    return b


# ---------------------------------------------------------------- minutes of one model day
class DayMinutes:
    """Arrays over the 1,440 minutes of a model day (index 0 = 00:00). Missing rows are NaN with has_row False."""

    FIELDS = ("bid_o", "bid_h", "bid_l", "bid_c", "ask_o", "ask_h", "ask_l", "ask_c", "o", "h", "l", "c",
              "bid_vol", "ask_vol")

    def __init__(self, mf, day):
        d0 = pd.Timestamp(day).normalize()
        sub = mf[(mf.index >= d0) & (mf.index < d0 + pd.Timedelta(days=1))]
        mins = ((sub.index - d0) // pd.Timedelta(minutes=1)).astype(int)
        self.has_row = np.zeros(1440, dtype=bool)
        self.a = {}
        # a duplicated model minute (never on a weekday) keeps the first row of the stable order
        _, first = np.unique(mins, return_index=True)
        mm = np.asarray(mins)[first]
        self.has_row[mm] = True
        for f in self.FIELDS:
            arr = np.full(1440, np.nan)
            arr[mm] = sub[f].to_numpy(dtype=float)[first]
            self.a[f] = arr

    def __getitem__(self, k):
        return self.a[k]

    def vol_both(self, m):
        return bool(self.a["bid_vol"][m] > 0 and self.a["ask_vol"][m] > 0)


class MinuteCache:
    def __init__(self, mf):
        self.mf = mf
        self.cache = {}

    def day(self, d):
        k = pd.Timestamp(d).normalize()
        if k not in self.cache:
            self.cache[k] = DayMinutes(self.mf, k)
        return self.cache[k]
