"""Round 3, lens "ctaflow": the trend-following community's flip flow, executed in the US morning.

Replica of the CTA community (trend followers run a continuum of lookbacks, not one): at 14:30 server (07:30 New
York, close of the 14:15 M15 bar) every lookback L = 10..60 trading days votes sign(log p_t - log p_{t-L}); S_t is the
mean vote and the vol-targeted exposure is E_t = clip(S_t x 10% / realised vol(20d), -1, 1). The signal is the
trend-flip FLOW Ft_t = (S_t - S_{t-1}) x V_{t-1}: the position change forced by lookbacks whose sign flipped since
yesterday (a change of exposure, not its level).

Rule: when |Ft_t| is in the top 30% of its trailing 250 days (quantile from prior days only), follow sign(Ft_t) from
the 14:30 open to the 16:30 close (HOLD = 8 M15 bars). The window holds the COMEX day-session open (15:20 server =
08:20 NY) and the US morning: the first deep liquidity after the flip, where mechanical position changes are worked.
Nothing touches the 23:30-01:30 rollover zone. US/UK DST-mismatch days are skipped by calendar (the 2019-2020 feed
shifts those days by one hour). Every lookback is <= 60 trading days.

Discovery evidence (2015-2020): n=397, net +$0.96/oz, z=3.59, 6/6 years, 2015-17 +0.94 / 2018-20 +0.97, long +1.13 /
short +0.77, hit 62.7%. Dose-response over the quantile (q0 +0.41 ... q0.9 +1.66 net). Placebos: the same flip measured
at 02:00/04:00/08:00/10:00/12:00/16:30/18:30 predicts nothing in the two hours that follow; the 14:30 signal predicts
nothing in 16:30-18:30, 18:30-20:30 or next-day Asia; applied one day late it earns +0.08. It subsumes the 24h-move
size, the London move, the 5-day trend, the exposure level and the round-2 7-day stretch (OLS t: flip 3.9, others < 1).
"""
from zoneinfo import ZoneInfo
import numpy as np
import pandas as pd

NAME = "cta_flip_flow_usmorning"
IDEA = ("A dense replica of trend followers (sign of 10..60-day returns, vol-targeted, sampled at 14:30 server): "
        "when the day's trend-flip flow is in its top 30%, follow it from 14:30 to 16:30 server (COMEX open, US morning).")
TF = "M15"
HOLD = 8                      # 14:30 open -> close of the 16:15 M15 bar (16:30 server = 09:30 New York)
CLOSE_BAR = 14 * 60 + 15      # replica daily price = close of the 14:15 M15 bar (14:30 server)
DEC_BAR = 14 * 60 + 15        # decided at that close; entry at the 14:30 bar open
LOOKS = tuple(range(10, 61))
TV, VOL_N = 0.10, 20
Q, QWIN, QMIN = 0.70, 250, 60

_NY, _LD = ZoneInfo("America/New_York"), ZoneInfo("Europe/London")


def _mismatch(days):
    return np.array([bool(pd.Timestamp(x).to_pydatetime().replace(hour=12, tzinfo=_NY).dst())
                     != bool(pd.Timestamp(x).to_pydatetime().replace(hour=12, tzinfo=_LD).dst()) for x in days], bool)


def signal(df):
    idx = df.index
    hm = idx.hour * 60 + idx.minute
    day = idx.normalize()
    at = hm == CLOSE_BAR
    p = pd.Series(df.c.to_numpy()[at], index=day[at])
    p = p[~p.index.duplicated()].astype(float)
    lp = np.log(p)
    S = pd.concat([np.sign(lp - lp.shift(L)) for L in LOOKS], axis=1).mean(axis=1, skipna=False)
    V = TV / (lp.diff().rolling(VOL_N, min_periods=VOL_N).std() * np.sqrt(252))
    Ft = (S - S.shift(1)) * V.shift(1)                   # trend-flip flow, known at 14:30 of day t
    a = Ft.abs()
    thr = a.rolling(QWIN, min_periods=QMIN).quantile(Q).shift(1)
    side = np.sign(Ft).where((a >= thr) & (a > 1e-12), 0).fillna(0)
    side[_mismatch(side.index)] = 0
    daily = pd.Series(side.reindex(day).to_numpy(), index=idx).fillna(0)
    return daily.where(hm == DEC_BAR, 0).astype(int)
