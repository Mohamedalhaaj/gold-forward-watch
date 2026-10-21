"""Verdict, adjudications and the latch (SYSTEM_V2_PREREG.md §3.2 "Verdict", "On VIOLATION", J5; §3.3 reason_ar
with IMPLEMENTATION_REGISTER R-JF-1, R-JF-2).

ADJUDICATIONS.csv (append-only): utc,ref,check,subject,decision,note
- the judge appends one `pending` row per new J5 mismatch (ref J5-<run>-<n>, subject = the mismatch key);
- Claude or the client appends, within 7 days, a row with the same ref and decision system_error, judge_error or
  spec_gap. Only system_error makes the verdict a VIOLATION (a manual, more conservative append); judge_error and
  spec_gap close the mismatch;
- a row with decision `clear` and ref `latch` (dated at or after the start of a latched VIOLATION) clears the latch;
  a `clear` row whose ref is a system_error ref withdraws that system_error.
"""
from pathlib import Path

import pandas as pd

from .common import iso_s, parse_utc, read_dicts, write_csv_append

ADJ = "reports/judge/ADJUDICATIONS.csv"
ADJ_HEAD = ["utc", "ref", "check", "subject", "decision", "note"]
VERDICTS = "reports/judge/VERDICTS.csv"
CHECK_IDS = ("J1", "J2", "J3", "J4", "J5", "J6", "J7", "J8", "J9")
V_HEAD = ["utc", "head_sha", "verdict", "reason_code", "checks_ok", "checks_total", "latched_since",
          "judge_code_sha"] + list(CHECK_IDS)

# reason_ar values: 1-40 characters, Arabic letters and spaces only, no diacritic, no punctuation (R-JF-1, R-JF-2)
REASONS = {
    "sound": "كل الفحوص سليمة",
    "unverified": "تعذر التحقق",
    "j5_mismatch": "إعادة الحساب لم تطابق قيد المراجعة",
    "j1_revised": "المصدر عدل بيانات يوم مخزن",
    "j9_price": "سعر مصدر مستقل يخالف البيانات",
    "j6_hit": "نسبة لمس الوقف خارج المجال المتوقع",
    "j6_qlike": "التوقع أضعف من طريقة بسيطة",
    "j4_self": "كود الحكم تغير دون تسجيل",
    "j7_stale": "تقرير المنظومة متأخر",
    "j7_ops": "تشغيل المنظومة سجل عطلا",
    "adj_system_error": "خطأ مؤكد في حساب المنظومة",
    "j8_rewritten": "إعادة كتابة تاريخ المستودع",
    "j4_tag": "وسم التجميد يشير إلى نسخة أخرى",
    "j4_frozen": "تغيير في الملفات المجمدة",
    "j3_raw": "ملف بيانات خام تغير أو حذف",
    "j3_ledger": "تعديل لاحق في سجلات المنظومة",
    "j3_judge": "تعديل لاحق في سجلات الحكم",
    "j2_register": "قاعدة سجلت بعد بياناتها",
    "j2_registry": "ملف قاعدة مسجلة تغير بعد تسجيلها",
    "j2_firstday": "سجلات قاعدة قبل يومها الأول",
    "j2_start": "تاريخ البداية تغير بعد تثبيته",
}
# REPORT.md and the site page may keep the prereg's own spellings (R-JF-1)
REPORT_SPELLING = {"unverified": "تعذّر التحقق", "j5_mismatch": "إعادة الحساب لم تطابق، قيد المراجعة"}
VIOLATION_ORDER = ("adj_system_error", "j8_rewritten", "j4_tag", "j4_frozen", "j3_raw", "j3_ledger", "j3_judge",
                   "j2_register", "j2_registry", "j2_firstday", "j2_start")
WARNING_ORDER = ("unverified", "j5_mismatch", "j1_revised", "j9_price", "j6_hit", "j6_qlike", "j4_self", "j7_stale",
                 "j7_ops")


def reason_valid(r):
    return (1 <= len(r) <= 40 and all((0x0621 <= ord(ch) <= 0x064A and ord(ch) != 0x0640) or ch == " "
                                      or "0" <= ch <= "9" or 0x0660 <= ord(ch) <= 0x0669 for ch in r)
            and 0x0621 <= ord(r[0]) <= 0x064A and r[-1] != " ")


def j5_adjudicate(findings, out_root, now):
    """New mismatches get a pending row; returns (status, open findings, system_error refs active, rows)."""
    out_root = Path(out_root)
    rows = read_dicts(out_root / ADJ)
    by_subject = {}
    for r in rows:
        if r.get("check") == "J5" and r.get("decision") == "pending":
            by_subject.setdefault(r["subject"], r["ref"])
    decided = {}
    for r in rows:
        if r.get("decision") in ("system_error", "judge_error", "spec_gap", "clear"):
            decided.setdefault(r["ref"], []).append(r)
    new_rows, n = [], 0
    stamp = now.strftime("%Y%m%d%H%M")
    seen = set()
    for f in findings:
        k = f.key()
        if k in by_subject or k in seen:
            continue
        seen.add(k)
        n += 1
        ref = f"J5-{stamp}-{n}"
        by_subject[k] = ref
        note = "".join(ch if 32 <= ord(ch) < 127 else "?" for ch in f.detail)[:300]
        new_rows.append([iso_s(now), ref, "J5", k, "pending", note])
    if new_rows:
        write_csv_append(out_root / ADJ, ADJ_HEAD, new_rows)
    open_f = []
    for f in findings:
        ref = by_subject.get(f.key())
        ds = [r["decision"] for r in decided.get(ref, []) if r["decision"] != "clear"]
        if ds and ds[-1] in ("judge_error", "spec_gap"):
            continue
        open_f.append((f, ref, ds[-1] if ds else "pending"))
    return open_f, new_rows


def active_system_errors(out_root):
    rows = read_dicts(Path(out_root) / ADJ)
    errs = {}
    for r in rows:
        if r.get("decision") == "system_error":
            errs[r["ref"]] = r
    for r in rows:
        if r.get("decision") == "clear" and r["ref"] in errs and r["utc"] >= errs[r["ref"]]["utc"]:
            errs.pop(r["ref"], None)
    return list(errs.values())


def latch_cleared(out_root, since):
    for r in read_dicts(Path(out_root) / ADJ):
        if r.get("decision") == "clear" and r.get("ref") == "latch" and r["utc"] >= since:
            return True
    return False


def undecided(out_root):
    """J5 rows still pending (no system_error, judge_error or spec_gap row with their ref): J5 stays a WARNING."""
    rows = read_dicts(Path(out_root) / ADJ)
    decided = {r["ref"] for r in rows if r.get("decision") in ("system_error", "judge_error", "spec_gap")}
    return [r for r in rows if r.get("check") == "J5" and r.get("decision") == "pending" and r["ref"] not in decided]


def overdue(out_root, now):
    """Pending J5 rows older than 7 days without a decision (listed in the report)."""
    rows = read_dicts(Path(out_root) / ADJ)
    decided = {r["ref"] for r in rows if r.get("decision") in ("system_error", "judge_error", "spec_gap")}
    return [r for r in rows if r.get("decision") == "pending" and r["ref"] not in decided
            and parse_utc(r["utc"]) + pd.Timedelta(days=7) < now]


def decide(checks, out_root, now):
    """(verdict, reason_code, checks_ok, latched_since, detail lines)."""
    viol = [r for c in checks if c.status == "violation" for r in c.reasons if r in VIOLATION_ORDER]
    warn = [r for c in checks if c.status == "warning" for r in c.reasons]
    syserr = active_system_errors(out_root)
    if syserr:
        viol.append("adj_system_error")
    prev = read_dicts(Path(out_root) / VERDICTS)
    prev = prev[-1] if prev else None
    latched = bool(prev and prev.get("latched_since") and not latch_cleared(out_root, prev["latched_since"]))
    lines = []
    if viol:
        code = next(r for r in VIOLATION_ORDER if r in viol)
        since = prev["latched_since"] if latched else iso_s(now)
        verdict = "VIOLATION"
    elif latched:
        code = prev.get("reason_code") or "j3_ledger"
        since = prev["latched_since"]
        verdict = "VIOLATION"
        lines.append(f"VIOLATION latched since {since}: no ADJUDICATIONS.csv row `clear,latch` dated after it")
    elif warn:
        code = next((r for r in WARNING_ORDER if r in warn), warn[0])
        since = ""
        verdict = "WARNING"
    else:
        code, since, verdict = "sound", "", "SOUND"
    ok = sum(1 for c in checks if c.status == "ok")
    for e in syserr:
        lines.append(f"system_error adjudication {e['ref']} ({e['subject']}) recorded {e['utc']}")
    return verdict, code, ok, since, lines


def record(out_root, now, head, verdict, code, ok, total, since, code_sha, checks):
    st = {c.id: c.status for c in checks}
    write_csv_append(Path(out_root) / VERDICTS, V_HEAD,
                     [[iso_s(now), head, verdict, code, ok, total, since, code_sha] + [st.get(i, "") for i in
                                                                                       CHECK_IDS]])
