"""Verdict, adjudications and the latch (SYSTEM_V2_PREREG.md §3.2 "Verdict", "On VIOLATION", J5, with Amendment B2
item 6; §3.3 reason_ar with IMPLEMENTATION_REGISTER R-JF-1, R-JF-2; R-JV-1 .. R-JV-4).

VIOLATION findings and their keys (B2 item 6, R-JV-1 .. R-JV-4):
- every VIOLATION finding has a stable key `<check>|<reason code>|<path>|<commit>` (judge/checks.py finding_key);
- reports/judge/FINDINGS.csv (append-only; utc,key,check,reason,detail) records each key once, at the first judge
  run that found it (utc = that run's time = when its latch began);
- a key stays open, and the verdict stays VIOLATION, until ADJUDICATIONS.csv has a row with ref `latch`, check = the
  key's check, subject = the key exactly, decision `clear`, and utc at or after the key's FINDINGS.csv utc. A key
  found in an earlier run and no longer found stays open until then (the latch);
- a cleared key no longer makes the verdict a VIOLATION, whether or not it is still found (a historical commit is
  found again by every run). The same kind of finding on a NEW commit has another key and is a new finding;
- a `clear` row that names no key, or a key not in FINDINGS.csv or this run, clears nothing;
- REPORT.md lists the keys found by the run, the open keys and every cleared key with the date of its clear row.

ADJUDICATIONS.csv (append-only): utc,ref,check,subject,decision,note
- the judge appends one `pending` row per new J5 mismatch (ref J5-<run>-<n>, subject = the mismatch key);
- Claude or the client appends, within 7 days, a row with the same ref and decision system_error, judge_error or
  spec_gap. Only system_error makes the verdict a VIOLATION (a manual, more conservative append); judge_error and
  spec_gap close the mismatch; a `clear` row whose ref is a system_error ref withdraws that system_error;
- `latch` rows clear VIOLATION finding keys as above.
"""
from pathlib import Path

import pandas as pd

from .common import iso_s, parse_utc, read_dicts, write_csv_append

ADJ = "reports/judge/ADJUDICATIONS.csv"
ADJ_HEAD = ["utc", "ref", "check", "subject", "decision", "note"]
FINDINGS = "reports/judge/FINDINGS.csv"
FINDINGS_HEAD = ["utc", "key", "check", "reason", "detail"]
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


def finding_log(out_root):
    """{key: first FINDINGS.csv row} (R-JV-1)."""
    out = {}
    for r in read_dicts(Path(out_root) / FINDINGS):
        if r.get("key"):
            out.setdefault(r["key"], r)
    return out


def cleared_keys(out_root, first_seen):
    """{key: utc of its first valid clear row} for the keys of first_seen ({key: utc first found}) (R-JV-2)."""
    def t(s):
        try:
            return parse_utc(s)
        except (ValueError, TypeError, AttributeError):
            return None

    out = {}
    for r in read_dicts(Path(out_root) / ADJ):
        k = r.get("subject", "")
        if not (r.get("decision") == "clear" and r.get("ref") == "latch" and k in first_seen
                and r.get("check") == k.split("|", 1)[0]):
            continue
        tr, tf = t(r.get("utc", "")), t(first_seen[k])
        if tr is not None and tf is not None and tr >= tf:
            out.setdefault(k, r["utc"])
    return out


def _key_reason(k):
    parts = k.split("|")
    return parts[1] if len(parts) > 1 else ""


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


def _current_findings(checks):
    cur = {}
    for c in checks:
        for k, code, line in getattr(c, "findings", []):
            cur.setdefault(k, (c.id, code, line))
    return cur


def decide(checks, out_root, now):
    """(verdict, reason_code, checks_ok, latched_since, detail lines). Checks whose every finding of this run is
    cleared are set back to ok (or warning) here (Check.clear)."""
    cur = _current_findings(checks)
    log = finding_log(out_root)
    first_seen = {k: r["utc"] for k, r in log.items()}
    for k in cur:
        first_seen.setdefault(k, iso_s(now))
    cleared = cleared_keys(out_root, first_seen)
    for c in checks:
        if hasattr(c, "clear"):
            c.clear(cleared)
    open_keys = [k for k in first_seen if k not in cleared]
    viol = [_key_reason(k) for k in open_keys]
    warn = [r for c in checks if c.status == "warning" for r in c.reasons]
    syserr = active_system_errors(out_root)
    if syserr:
        viol.append("adj_system_error")
    prev = read_dicts(Path(out_root) / VERDICTS)
    prev = prev[-1] if prev else None
    lines = []
    if viol:
        code = next((r for r in VIOLATION_ORDER if r in viol), viol[0])
        since = (prev["latched_since"] if prev and prev.get("verdict") == "VIOLATION" and prev.get("latched_since")
                 else iso_s(now))
        verdict = "VIOLATION"
        if code not in REASONS:
            code = "j3_ledger"
    elif warn:
        code = next((r for r in WARNING_ORDER if r in warn), warn[0])
        since = ""
        verdict = "WARNING"
    else:
        code, since, verdict = "sound", "", "SOUND"
    ok = sum(1 for c in checks if c.status == "ok")
    if cur:
        lines.append("violation finding keys of this run: " + "; ".join(sorted(cur)))
    for k in sorted(open_keys):
        lines.append(f"open finding key {k} (first found {first_seen[k]}"
                     + ("" if k in cur else "; latched, not found by this run")
                     + f"): cleared only by an ADJUDICATIONS.csv row "
                       f"`<utc>,latch,{k.split('|', 1)[0]},{k},clear,<note>` "
                       f"with utc at or after {first_seen[k]}")
    for k in sorted(cleared):
        lines.append(f"cleared finding key {k} (first found {first_seen[k]}; clear row {cleared[k]})"
                     + ("; still found by this run" if k in cur else ""))
    for e in syserr:
        lines.append(f"system_error adjudication {e['ref']} ({e['subject']}) recorded {e['utc']}")
    return verdict, code, ok, since, lines


def record(out_root, now, head, verdict, code, ok, total, since, code_sha, checks):
    st = {c.id: c.status for c in checks}
    log = finding_log(out_root)
    new = [[iso_s(now), k, chk, rc, "".join(ch if 32 <= ord(ch) < 127 else "?" for ch in line)[:300]]
           for k, (chk, rc, line) in sorted(_current_findings(checks).items()) if k not in log]
    if new:
        write_csv_append(Path(out_root) / FINDINGS, FINDINGS_HEAD, new)
    write_csv_append(Path(out_root) / VERDICTS, V_HEAD,
                     [[iso_s(now), head, verdict, code, ok, total, since, code_sha] + [st.get(i, "") for i in
                                                                                       CHECK_IDS]])
