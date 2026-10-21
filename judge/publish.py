"""The judge's outputs (SYSTEM_V2_PREREG.md §3.3): reports/judge/REPORT.md (Arabic first, every check with its
evidence), reports/forward_site/judge/index.html (Arabic, RTL) and reports/forward_site/judge/VolMapJudge.csv
(IMPLEMENTATION_REGISTER R-JF-1, R-JF-2)."""
import html
from pathlib import Path

from .common import iso_s, write_text_atomic
from .verdict import REASONS, REPORT_SPELLING, reason_valid

CHECK_AR = {
    "J1": "تطابق البيانات الخام مع تنزيل مستقل من المصدر",
    "J2": "تسجيل كل قاعدة قبل نتائجها وثبات ملفاتها",
    "J3": "عدم تعديل السجلات والبيانات الخام بعد كتابتها",
    "J4": "ثبات الملفات المجمدة وكود الحكم",
    "J5": "إعادة حساب التوقعات والإشارة والمعايرة والصفقات وملف الحالة",
    "J6": "أداء التوقع ونسبة لمس الوقف على البيانات الجديدة",
    "J7": "حداثة ملف الحالة وخلو آخر تشغيل من الأعطال",
    "J8": "عدم إعادة كتابة تاريخ المستودع",
    "J9": "مقارنة السعر بمصدر مستقل",
}
STATUS_AR = {"ok": "سليم", "warning": "تحذير", "violation": "مخالفة"}
# an ok check that verified nothing in this run (J1 no side compared, J8 no anchor, J9 the latest day not compared:
# «لم يُتحقق»; J6 no complete forward week: «لا بيانات بعد»). Display only: checks_ok and the verdict are unchanged
# (R-J9-5).
IDLE_AR = {"unverified": "لم يُتحقق", "no_data": "لا بيانات بعد"}
VERDICT_AR = {"SOUND": "سليم", "WARNING": "تحذير", "VIOLATION": "مخالفة"}


def shown(c):
    """(Arabic label, css class) of a check's result on the page and in REPORT.md."""
    if c.status == "ok" and getattr(c, "idle", ""):
        return IDLE_AR[c.idle], "s-unverified"
    return STATUS_AR[c.status], f"s-{c.status}"


def counts(checks):
    """(ok and verified, ok but nothing verified in this run)."""
    idle = sum(1 for c in checks if c.status == "ok" and getattr(c, "idle", ""))
    return sum(1 for c in checks if c.status == "ok") - idle, idle


def summary_ar(checks, total):
    """Amendment B3 item 3: the «، ولم يُتحقق من y» clause is dropped when nothing is unverified (y = 0)."""
    x, y = counts(checks)
    return f"الفحوص السليمة {x} من {total}" + (f"، ولم يُتحقق من {y}" if y else "")


def judge_csv(asof, head, verdict, code, ok, total):
    reason = REASONS[code]
    assert reason_valid(reason), code
    lines = ["key,value", "version,1", f"asof_utc,{iso_s(asof)}", f"head_sha,{head}", f"verdict,{verdict}",
             f"reason_ar,{reason}", f"checks_ok,{int(ok)}", f"checks_total,{int(total)}"]
    lines.append(f"end,{len(lines)}")
    return ("\n".join(lines) + "\n").encode("utf-8")


def report_md(asof, head, verdict, code, ok, total, checks, extra, judge_sha):
    reason = REPORT_SPELLING.get(code, REASONS[code])
    L = ["<div dir=\"rtl\" lang=\"ar\">", "", "# تقرير الحَكَم المستقل", "",
         f"**الحكم: {VERDICT_AR[verdict]}** · السبب: {reason}", "",
         f"- وقت الفحص: {iso_s(asof)}", f"- {summary_ar(checks, total)}", ""]
    L.append("| الفحص | ما يتحقق منه | النتيجة |")
    L.append("|---|---|---|")
    for c in checks:
        L.append(f"| {c.id} | {CHECK_AR[c.id]} | {shown(c)[0]} |")
    L += ["", "حدود الحَكَم: يكشف الأخطاء والتعديلات اللاحقة، لكنه يعمل على الحساب نفسه ومن صنع الجهة نفسها، "
              "فلا يحمي من تلاعب متعمّد.", "", "</div>", ""]
    idle = [c.id for c in checks if c.status == "ok" and getattr(c, "idle", "")]
    L += ["## Evidence", "", f"- Verdict: **{verdict}** (reason code `{code}`), checks ok {ok} of {total}"
          + (f"; of these, nothing was verified in this run by: {', '.join(idle)}" if idle else ""),
          f"- HEAD checked: `{head}`", f"- Judge code sha256 (live manifest): `{judge_sha}`",
          "- Binding spec: xauusd-quant `research/system/SYSTEM_V2_PREREG.md` §3 with Amendments B1 item 2 and B2 "
          "items 5-7, "
          "SYSTEM_V1_PREREG.md with Amendment A1, research/system/IMPLEMENTATION_REGISTER.md", ""]
    for line in extra:
        L.append(f"- {line}")
    L.append("")
    for c in checks:
        L.append(f"### {c.id}: {c.status.upper()}")
        L.append("")
        for e in c.evidence[:200]:
            L.append(f"- {e}")
        if len(c.evidence) > 200:
            L.append(f"- ... {len(c.evidence) - 200} more lines")
        for u in c.unverified:
            L.append(f"- unverified: {u}")
        L.append("")
    return "\n".join(L)


def index_html(asof, verdict, code, ok, total, checks):
    reason = REPORT_SPELLING.get(code, REASONS[code])
    color = {"SOUND": "#2e7d4f", "WARNING": "#a8780a", "VIOLATION": "#b3261e"}[verdict]
    rows = "\n".join(
        f"<tr><td>{c.id}</td><td>{html.escape(CHECK_AR[c.id])}</td><td class=\"{shown(c)[1]}\">"
        f"{shown(c)[0]}</td></tr>" for c in checks)
    return f"""<!doctype html>
<html lang="ar" dir="rtl">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex, nofollow">
<title>الحَكَم المستقل</title>
<style>
:root {{ --bg: #f7f6f2; --fg: #1d1d1b; --muted: #5f5e58; --line: #dedbd2; --card: #ffffff; }}
@media (prefers-color-scheme: dark) {{
  :root {{ --bg: #151513; --fg: #ecebe6; --muted: #a8a69e; --line: #34332f; --card: #1e1e1b; }}
}}
* {{ box-sizing: border-box; }}
body {{ margin: 0; background: var(--bg); color: var(--fg); font: 16px/1.6 system-ui, "Segoe UI", Tahoma, sans-serif; }}
main {{ max-width: 760px; margin: 0 auto; padding: 24px 16px 48px; }}
h1 {{ font-size: 1.5rem; margin: 0 0 12px; }}
.verdict {{ background: var(--card); border: 1px solid var(--line); border-inline-start: 6px solid {color};
  border-radius: 8px; padding: 16px; margin-bottom: 20px; }}
.verdict b {{ color: {color}; font-size: 1.25rem; }}
table {{ width: 100%; border-collapse: collapse; background: var(--card); border: 1px solid var(--line); }}
th, td {{ padding: 8px 10px; border-bottom: 1px solid var(--line); text-align: start; vertical-align: top; }}
td:first-child {{ font-variant-numeric: tabular-nums; direction: ltr; text-align: right; width: 3.5em; }}
.s-ok {{ color: #2e7d4f; }} .s-warning {{ color: #a8780a; }} .s-violation {{ color: #b3261e; font-weight: 600; }}
.s-unverified {{ color: var(--muted); }}
p.note {{ color: var(--muted); font-size: .9rem; }}
</style>
</head>
<body>
<main>
<h1>الحَكَم المستقل</h1>
<div class="verdict"><b>{VERDICT_AR[verdict]}</b><br>{html.escape(reason)}<br>
<span class="note">{summary_ar(checks, total)} · وقت الفحص <span dir="ltr">{iso_s(asof)}</span></span></div>
<table>
<thead><tr><th>الفحص</th><th>ما يتحقق منه</th><th>النتيجة</th></tr></thead>
<tbody>
{rows}
</tbody>
</table>
<p class="note">برنامج منفصل كُتب من القواعد المكتوبة وحدها ويعمل بعد كل تشغيل للمنظومة. يكشف الأخطاء والتعديلات
اللاحقة، لكنه يعمل على الحساب نفسه ومن صنع الجهة نفسها، فلا يحمي من تلاعب متعمّد.</p>
</main>
</body>
</html>
"""


def write_all(out_root, asof, head, verdict, code, ok, total, checks, extra, judge_sha):
    out_root = Path(out_root)
    raw = judge_csv(asof, head, verdict, code, ok, total)
    p = out_root / "reports/forward_site/judge/VolMapJudge.csv"
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_bytes(raw)
    tmp.replace(p)
    write_text_atomic(out_root / "reports/forward_site/judge/index.html",
                      index_html(asof, verdict, code, ok, total, checks))
    write_text_atomic(out_root / "reports/judge/REPORT.md",
                      report_md(asof, head, verdict, code, ok, total, checks, extra, judge_sha))
    return p
