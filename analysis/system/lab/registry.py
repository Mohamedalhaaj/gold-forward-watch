"""Registry, event log, states, registration time and first_day (L2 §7 with SYSTEM_V1_PREREG.md §3 items 5-9). FROZEN.

- One file per candidate, reports/system/lab/registry/<id>.json, never edited after its commit. It holds the spec,
  its canonical sha256, γ, α, D at arrival, α_j, E*, the entry delay, costs and the Arabic title.
- registered_utc (§3 item 5) is not in the file: it is the UTC time at which a lab run in GitHub Actions first finds
  the file at origin/main HEAD, logged as REGISTERED (with the run id and the HEAD sha) in the append-only
  reports/system/lab/registry/events.csv. A local or dry run logs a placeholder REGISTERED instead.
- first_day = the first trading day d (model-clock weekday) with d 01:00 model >= registered_utc + 1 h, and d >= START.
- States: PAPER -> LIVE -> (SUSPENDED <-> LIVE) -> DEMOTED -> RETIRED; PAPER -> RETIRED. REF streams stay REF.
- START (§0) = the later of Monday 2026-11-02 and the first Monday at least 2 calendar days after the first
  successful cloud run of the frozen code (reports/system/START.json, written once by that run).
- Titles (Amendment A1 item 3): the Arabic title of every record is at most 31 characters of Arabic letters, spaces
  and ASCII digits, begins with an Arabic letter, does not end with a space and has no double space. It is what the
  indicator shows after «قاعدة اتجاه اجتازت الاختبار: » for a LIVE rule; record() refuses any other title.
"""
import csv
import datetime as dt
import hashlib
import json
from pathlib import Path

import pandas as pd

import bars
from lab import eproc, grammar

EVENT_COLS = ["utc", "id", "event", "reason", "n", "E", "K", "D_total", "run_id", "head_sha"]
EVENTS = ("REGISTERED", "PROMOTED", "DEMOTED", "SUSPENDED", "RESUMED", "RETIRED")
EARLIEST_START = dt.date(2026, 11, 2)
LAB_VERSION = 1
COSTS = {"allowance_usd": 0.10, "stress_add_usd": 0.25}
TITLE_MAX = 31
START_RULE = ("later of 2026-11-02 and the first Monday >= 2 days after the first successful cloud run "
              "(SYSTEM_V1_PREREG.md §0)")


# ---------------------------------------------------------------- titles (A1 item 3)
def _arabic_letter(ch):
    return "ء" <= ch <= "ي" and ch != "ـ"                  # hamza .. yeh, without the tatweel


def title_ok(s):
    """True iff `s` is a valid record title (A1 item 3; see the module doc)."""
    if not isinstance(s, str) or not 1 <= len(s) <= TITLE_MAX:
        return False
    if not _arabic_letter(s[0]) or s[-1] == " " or "  " in s:
        return False
    return all(_arabic_letter(c) or c == " " or "0" <= c <= "9" for c in s)


# ---------------------------------------------------------------- START and first_day
def start_from_first_run(first_run_utc):
    d = pd.Timestamp(first_run_utc).date() + dt.timedelta(days=2)
    monday = d + dt.timedelta(days=(7 - d.weekday()) % 7)
    return max(EARLIEST_START, monday)


def start_record(first_run_utc, run_id, head_sha):
    """The content of reports/system/START.json, written once by the first non-halted cloud run (§0)."""
    t = pd.Timestamp(first_run_utc)
    t = t.tz_localize("UTC") if t.tzinfo is None else t.tz_convert("UTC")
    return {"first_cloud_run_utc": t.strftime("%Y-%m-%dT%H:%M:%SZ"), "run_id": run_id, "head_sha": head_sha,
            "start": str(start_from_first_run(t)), "rule": START_RULE}


def first_day(registered_utc, start):
    """First model weekday d with d 01:00 model >= registered_utc + 1 h, and d >= START."""
    if registered_utc is None or start is None:
        return None
    t = pd.Timestamp(registered_utc)
    t = (t.tz_localize("UTC") if t.tzinfo is None else t.tz_convert("UTC")) + pd.Timedelta(hours=1)
    d = max(bars.to_model(pd.DatetimeIndex([t]))[0].normalize() - pd.Timedelta(days=1), pd.Timestamp(start))
    while True:
        if d.dayofweek < 5 and bars.model_to_utc(d + pd.Timedelta(hours=1)) >= t and d >= pd.Timestamp(start):
            return d.strftime("%Y-%m-%d")
        d += pd.Timedelta(days=1)


# ---------------------------------------------------------------- files
def record(cid, spec, *, tier, promotable, gamma, D, title_ar, source, entry_delay_min=1, allow_coin=False,
           extra=None):
    s = grammar.validate(spec, allow_coin=allow_coin)
    if not title_ok(title_ar):
        raise ValueError(f"{cid}: title {title_ar!r} breaks the title rule (A1 item 3)")
    rec = {"id": cid, "lab_version": LAB_VERSION, "grammar": grammar.GRAMMAR_VERSION, "spec": s,
           "spec_sha256": grammar.spec_sha256(s, allow_coin=allow_coin), "question": grammar.question_key(s),
           "tier": tier, "promotable": bool(promotable), "gamma": gamma, "alpha": eproc.ALPHA_V1,
           "D_at_arrival": int(D), "alpha_j": eproc.alpha_j(gamma, D),
           "E_star": eproc.e_star(gamma, D) if gamma > 0 else None,
           "entry_delay_min": int(entry_delay_min), "cost": dict(COSTS), "title_ar": title_ar, "source": source}
    if extra:
        rec.update(extra)
    return rec


def dumps(rec):
    return json.dumps(rec, sort_keys=True, indent=1, ensure_ascii=False) + "\n"


def write(reg_dir, rec):
    p = Path(reg_dir) / f"{rec['id']}.json"
    if p.exists():
        raise FileExistsError(f"{p} exists: registry files are never edited")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(dumps(rec))
    return p


def load(reg_dir):
    """Registry records in arrival order (seeds first by their `arrival`, then proposals by proposal number)."""
    recs = []
    for p in sorted(Path(reg_dir).glob("*.json")):
        recs.append(json.loads(p.read_text()))
    return sorted(recs, key=lambda r: (r.get("arrival", 1_000_000), r["id"]))


def verify(reg_dir):
    """Every file's spec hash and its E* (from γ and D) recomputed; returns a list of problems (empty = OK)."""
    bad = []
    for r in load(reg_dir):
        allow = r["spec"]["side"][0] == "COIN"
        try:
            if grammar.spec_sha256(r["spec"], allow_coin=allow) != r["spec_sha256"]:
                bad.append(f"{r['id']}: spec_sha256 mismatch")
        except grammar.SpecError as e:
            bad.append(f"{r['id']}: invalid spec ({e})")
        if r["promotable"] and abs(eproc.e_star(r["gamma"], r["D_at_arrival"]) - r["E_star"]) > 1e-9 * r["E_star"]:
            bad.append(f"{r['id']}: E_star does not follow from gamma and D")
        if not r["promotable"] and r["gamma"] != 0:
            bad.append(f"{r['id']}: a REF stream must have gamma 0")
        if not title_ok(r.get("title_ar")):
            bad.append(f"{r['id']}: title breaks the title rule (A1 item 3)")
    return bad


def file_sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


# ---------------------------------------------------------------- events and states
def read_events(path):
    path = Path(path)
    if not path.exists():
        return []
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def append_events(path, rows):
    if not rows:
        return
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    new = not path.exists()
    with open(path, "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=EVENT_COLS, lineterminator="\n")
        if new:
            w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in EVENT_COLS})


def states(recs, events, start):
    """{id: {"state", "registered_utc", "first_day", "promoted_utc", "demoted_utc", "retired_utc"}}."""
    out = {}
    for r in recs:
        out[r["id"]] = {"state": "PENDING", "registered_utc": None, "first_day": None, "promoted_utc": None,
                        "demoted_utc": None, "retired_utc": None, "promotable": r["promotable"]}
    for e in events:
        s = out.get(e["id"])
        if s is None:
            continue
        ev = e["event"]
        if ev == "REGISTERED" and s["registered_utc"] is None:
            s["registered_utc"] = e["utc"]
            s["state"] = "PAPER" if s["promotable"] else "REF"
        elif ev == "PROMOTED":
            s["state"], s["promoted_utc"] = "LIVE", e["utc"]
        elif ev == "SUSPENDED":
            s["state"] = "SUSPENDED"
        elif ev == "RESUMED":
            s["state"] = "LIVE"
        elif ev == "DEMOTED":
            s["state"], s["demoted_utc"] = "DEMOTED", e["utc"]
        elif ev == "RETIRED":
            s["state"], s["retired_utc"] = "RETIRED", e["utc"]
    for cid, s in out.items():
        s["first_day"] = first_day(s["registered_utc"], start)
    return out


def promotions_count(events):
    return sum(1 for e in events if e["event"] == "PROMOTED")


def register_new(recs, events, now_utc, run_id, head_sha, tracked):
    """REGISTERED rows for files that are tracked at HEAD and have no REGISTERED event yet."""
    have = {e["id"] for e in events if e["event"] == "REGISTERED"}
    rows = []
    for r in recs:
        if r["id"] in have or r["id"] not in tracked:
            continue
        rows.append({"utc": now_utc, "id": r["id"], "event": "REGISTERED", "reason": "found at HEAD", "n": 0,
                     "E": 1.0, "K": 1.0, "D_total": promotions_count(events), "run_id": run_id, "head_sha": head_sha})
    return rows


# ---------------------------------------------------------------- seeds (§3 item 9)
S1_SPEC = {"T": "2300", "side": ["FADE", "2245", "2300"], "when": [["ABSMOVE", "2245", "2300", "GE", "0.50"]],
           "hold": 2, "stop": "H10", "days": 15, "skip_event": 0}
C1_SPEC = {"T": "1500", "side": ["COIN"], "when": [], "hold": 8, "stop": "H10", "days": 31, "skip_event": 0}


def seed_records():
    return [
        record("S1", S1_SPEC, tier="SEED", promotable=True, gamma=eproc.GAMMA_S1, D=0,
               title_ar="عكس حركة إغلاق نيويورك قبل 23",
               source="L2 §8.1 NY-close fade, days Mon-Thu, entry T+1 min at bid/ask, no penalty (SYSTEM_V1 §3.9)",
               extra={"arrival": 1}),
        record("S1R", S1_SPEC, tier="REF", promotable=False, gamma=0.0, D=0, entry_delay_min=0,
               title_ar="الفكرة نفسها بدخول فوري عند 23",
               source="L2 §8.2: S1 with entry at T (no delay); REF, never promotable", extra={"arrival": 2}),
        record("C1", C1_SPEC, tier="REF", promotable=False, gamma=0.0, D=0, allow_coin=True,
               title_ar="رمية عملة عند 15 لتعرف شكل الحظ",
               source="L2 §8.3 coin control; REF, never promotable, never published", extra={"arrival": 3}),
    ]
