"""Exhaustion lens, round 2: a Bollinger stretch at the US data bar is NOT exhausted -- it resumes after the eruption.

Measure: z = (close - mean80) / std80 on M15 closes (80 bars = 20 hours), read at the close of the 15:15-15:30 bar
(15:30 server = 08:30 New York, the US data release / just after the COMEX open). If |z| >= 1.75, take that direction
at the close of the 16:45-17:00 bar (after the 15:30-17:00 data/NY-open eruption, which carries no direction) and
hold 14 M15 bars: entry 17:00 open, exit at the close of the 20:15-20:30 bar (the 13:30 NY COMEX settlement).
Nothing touches the 23:30-01:30 rollover zone. Discovery 2015-2020: n~462, mean net ~+$0.91/oz, both halves positive.
"""
import numpy as np
import pandas as pd

NAME = "databar_stretch_settle"
IDEA = ("A >=1.75-sigma 20-hour Bollinger stretch at the 15:30 US-data bar keeps going after the eruption: "
        "follow it from 17:00 to the 20:30 COMEX settle.")
TF = "M15"
HOLD = 14
WIN = 80
THR = 1.75


def signal(df):
    c = df.c
    z = (c - c.rolling(WIN).mean()) / c.rolling(WIN).std()
    start = df.index.hour * 60 + df.index.minute
    day = df.index.normalize()
    meas = pd.Series(np.where(start == 15 * 60 + 15, z.to_numpy(), np.nan), index=df.index)
    z1530 = meas.groupby(day).transform("max")  # one 15:15 bar per day; only read at 16:45 below (causal)
    dec = start == 16 * 60 + 45
    s = np.where(dec & (z1530.abs() >= THR).to_numpy(), np.sign(z1530.to_numpy()), 0.0)
    return pd.Series(np.nan_to_num(s).astype(int), index=df.index)
