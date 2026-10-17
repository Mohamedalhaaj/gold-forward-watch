"""Shared definitions of the gold support system v1 (research/system/SYSTEM_V1_PREREG.md §2 and §4).

Python twin of mt5/VolMapLight.mqh. The cloud job vendors this file byte-identically. Parity with the MQL5/C++ version is
checked over the full truth table by mt5/volmap_parity/light_replay.cpp + compare_light.py.
"""

GREY, GREEN, YELLOW, RED = 0, 1, 2, 3

# reason bits, in display order
R_UNDEF = 1 << 0
R_CLOSED = 1 << 1
R_CPI = 1 << 2
R_WEEKOPEN = 1 << 3
R_COSTHIGH = 1 << 4
R_NFP = 1 << 5
R_FOMC = 1 << 6
R_REOPEN = 1 << 7
R_COST = 1 << 8
R_WEEKEND = 1 << 9
R_DRIFT = 1 << 10

COST_YELLOW = 0.06
COST_HIGH = 0.12
RED_MASK = R_CPI | R_WEEKOPEN

BUCKETS = ("CPI", "FOMC", "NFP", "REOPEN", "N_ASIA", "N_LONDON", "N_NY")


def judge(ok, closed, w, slot, nfp, cpi, fomc, hour_usd, cost_usd, green_ok):
    """Conditions light of one hour (§2). w: 0=Mon..4=Fri, slot: hour-1, model clock. Returns (state, reasons, c)."""
    if not ok or not (hour_usd > 0.0 and hour_usd < 1e12):
        return GREY, R_UNDEF, 0.0
    if closed:
        return GREY, R_CLOSED, 0.0
    c = cost_usd / hour_usd
    r = 0
    if cpi:
        r |= R_CPI
    if w == 0 and slot == 0:
        r |= R_WEEKOPEN
    if c >= COST_HIGH:
        r |= R_COSTHIGH
    if nfp:
        r |= R_NFP
    if fomc:
        r |= R_FOMC
    if slot == 0 and w >= 1:
        r |= R_REOPEN
    if COST_YELLOW <= c < COST_HIGH:
        r |= R_COST
    if w == 4 and slot >= 21:
        r |= R_WEEKEND
    if not green_ok:
        r |= R_DRIFT
    if r & RED_MASK:
        return RED, r, c
    return (YELLOW if r else GREEN), r, c


def session_of_slot(slot):
    """0 Asia, 1 London, 2 New York; same split as research/volmap/core.session_of_hour (hour = slot + 1)."""
    hour = slot + 1
    if hour < 10:
        return 0
    if hour < 15:
        return 1
    return 2


def bucket(slot, nfp, cpi, fomc):
    """L3 calibration bucket of one hour (§4): first match wins."""
    if cpi:
        return "CPI"
    if fomc:
        return "FOMC"
    if nfp:
        return "NFP"
    if slot == 0:
        return "REOPEN"
    return ("N_ASIA", "N_LONDON", "N_NY")[session_of_slot(slot)]
