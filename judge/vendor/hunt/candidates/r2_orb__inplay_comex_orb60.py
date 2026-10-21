"""ORB lens (Zarattini/Aziz 'stocks in play' analog for one instrument): in-play COMEX opening-range breakout.

Opening range = the first COMEX hour, 15:20-16:20 server (08:20-09:20 New York; it contains the 08:30 data minute).
'In play' = that hour's high-low range is >= 1.25x the average of the same hour over the previous 14 days (Zarattini
uses 14-day relative volume; we have no volume, so relative range is the proxy). On in-play days only, the first M5
close beyond the opening-range high (low) between 16:20 and 18:20 is followed long (short) for 48 M5 bars = 4 hours,
so every exit falls by ~22:25 server: before the 16:00 NY close window and the 23:30-01:30 rollover zone.

Mechanism (hypothesis): an unusually wide first COMEX hour marks an information day (data surprise, macro repricing);
on those days the breakout carries for hours (slow digestion / post-announcement drift), while on ordinary days ORB
breaks are noise. Discovery evidence is weak: net +$0.61/trade, z 1.16, 6/6 years positive, both halves positive;
the textbook rel >= 1.0 filter is flat, and the effect does not replicate at the London or Asia opens.
"""
NAME = "inplay_comex_orb60"
IDEA = ("In-play COMEX ORB: when the first COMEX hour (15:20-16:20 server) is >= 1.25x its 14-day average range, "
        "follow the first M5 close beyond that hour's high/low within the next 2 hours and hold 4 hours.")
TF = "M5"
HOLD = 48  # 48 x M5 = 4 hours; last possible entry 18:25 -> exit at the 22:20 bar close
import numpy as np
import pandas as pd

OR_START, OR_LEN, WIN, LOOK, THR = 920, 60, 120, 14, 1.25  # minutes of the server day


def signal(df):
    m = (df.index.hour * 60 + df.index.minute).to_numpy()
    day = df["day"].to_numpy()
    inor = (m >= OR_START) & (m < OR_START + OR_LEN)
    g = df[inor].groupby("day")
    R = pd.DataFrame({"hi": g.h.max(), "lo": g.l.min(), "cnt": g.h.count()})
    R = R[R.cnt >= OR_LEN // 5 * 0.6]          # need most of the opening-range bars
    rng = R.hi - R.lo
    R["rel"] = rng / rng.rolling(LOOK, min_periods=7).mean().shift(1)   # previous days only
    hi = R.hi.reindex(day).to_numpy()
    lo = R.lo.reindex(day).to_numpy()
    rel = R.rel.reindex(day).to_numpy()
    c = df.c.to_numpy()
    out = np.zeros(len(df), dtype=int)
    done_day = None
    t0 = OR_START + OR_LEN
    for i in np.flatnonzero((m >= t0) & (m < t0 + WIN)):   # bars that start after the opening range is complete
        if day[i] == done_day or not (rel[i] >= THR):
            continue
        if c[i] > hi[i]:
            out[i] = 1
            done_day = day[i]
        elif c[i] < lo[i]:
            out[i] = -1
            done_day = day[i]
    return pd.Series(out, index=df.index)
