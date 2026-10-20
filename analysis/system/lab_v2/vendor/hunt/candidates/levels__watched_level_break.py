NAME = "watched_level_break"
IDEA = ("First touch of a headline level - a $100 big figure untouched for 4 hours, or the 40-day high/low "
        "(first touch of the day) - trade the break-through in the direction of approach for 2 hours.")
TF = "M5"
HOLD = 24  # 24 x M5 = 2 hours
import numpy as np
import pandas as pd

STEP = 100.0   # big figure
K = 48         # bars (4 hours) a big figure must have been untouched
N = 40         # days for the N-day high/low (completed days before today)


def signal(df):
    h, l, c = df.h.to_numpy(), df.l.to_numpy(), df.c.to_numpy()
    s = np.zeros(len(df), dtype=int)

    # 1) $100 big figures, first touch after K untouched bars
    pc = np.r_[np.nan, c[:-1]]
    up = np.ceil(pc / STEP) * STEP
    up = np.where(up == pc, up + STEP, up)
    dn = np.floor(pc / STEP) * STEP
    dn = np.where(dn == pc, dn - STEP, dn)
    hm = pd.Series(h).rolling(K, min_periods=1).max().shift(1).to_numpy()
    lm = pd.Series(l).rolling(K, min_periods=1).min().shift(1).to_numpy()
    b_up = (h >= up) & (hm < up)
    b_dn = (l <= dn) & (lm > dn)
    s += np.where(b_up & ~b_dn, 1, np.where(b_dn & ~b_up, -1, 0))

    # 2) N-day high/low from completed prior days, first intraday touch today (no trigger on the day's first bar)
    day = df["day"]
    d = day.to_numpy()
    g = df.groupby(day, sort=False)
    nh = g.h.max().rolling(N, min_periods=N).max().shift(1)
    nl = g.l.min().rolling(N, min_periods=N).min().shift(1)
    H_ = nh.reindex(day).to_numpy()
    L_ = nl.reindex(day).to_numpy()
    same = np.r_[False, d[1:] == d[:-1]]
    rh = pd.Series(h).groupby(d).cummax().shift(1).to_numpy()   # today's high before this bar
    rl = pd.Series(l).groupby(d).cummin().shift(1).to_numpy()
    n_up = same & (h >= H_) & (rh < H_)
    n_dn = same & (l <= L_) & (rl > L_)
    s += np.where(n_up & ~n_dn, 1, np.where(n_dn & ~n_up, -1, 0))

    return pd.Series(np.sign(s), index=df.index)
