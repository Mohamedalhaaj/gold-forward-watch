"""The lab v2 dashboard section (SYSTEM_V2_PREREG.md §2.4, Amendment B2 items 2-3). OPS, Python standard library
only, so the crash recorder (v2_crash.py) can render it even when numpy, pandas or a lab v2 module cannot be imported.

- reports/forward_site/system/lab_v2/index.html: «المختبر، الإصدار الثاني», static HTML with the data written in: the v2
  seeds with their record (trades, sum and mean net $/oz, progress E/E*) next to the v1 coin control C1 over the same
  days. While lab v2 is not RUNNING the page shows the banner «المختبر الثاني متوقف مؤقتًا» and makes no claim about
  v1 (Amendment B2 item 3). A link leads back to the v1 lab page (../), which links here (B2 item 2).
- reports/forward_site/system/lab_v2/lab_v2.json: the summary without NaN, halt_reasons last.
Both are built from the summary dict alone (v2_publish.summary, or the PAUSED summary of v2_crash.record).
"""
import html
import json
import math
from pathlib import Path

TITLE_AR = "المختبر، الإصدار الثاني"
WARMUP_AR = "في مرحلة الإحماء حتى تكتمل بياناتها"
COIN_AR = "عملة عشوائية: لتعرف شكل الحظ"
PAUSED_AR = "المختبر الثاني متوقف مؤقتًا"
BACK_AR = "العودة إلى مختبر إشارات البيع والشراء"

CSS = """:root{color-scheme:dark;--page:#0f0f0e;--panel:#151514;--line:#2a2a27;--ink:#efece4;--ink-2:#b9b5a8;
--ink-3:#8f8b80;--gold:#d9a43b;--warn:#f0c846;--bad:#f05f55}
@media (prefers-color-scheme:light){:root{color-scheme:light;--page:#f3f1eb;--panel:#fbfaf7;--line:#e3e0d6;
--ink:#141412;--ink-2:#4f4c45;--ink-3:#6c685f;--gold:#9a6b12;--warn:#8a6a00;--bad:#c0392b}}
*{box-sizing:border-box}html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--page);color:var(--ink);font-family:"Plex Arabic",system-ui,-apple-system,"Segoe UI",
sans-serif;font-size:15px;line-height:1.7}
main{max-width:860px;margin:0 auto;padding:28px 16px 48px}
h1{font-size:1.45rem;margin:0 0 4px;font-weight:700}.sub{color:var(--ink-2);margin:0 0 20px}
.card{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:16px 18px;margin-bottom:14px}
.table-wrap{overflow-x:auto}table{width:100%;border-collapse:collapse;font-size:.92rem}
th,td{text-align:right;padding:8px 6px;border-bottom:1px solid var(--line);vertical-align:top}
th{color:var(--ink-3);font-weight:500;white-space:nowrap}td.title{min-width:11em}
td.num{font-variant-numeric:tabular-nums;direction:ltr;text-align:right;white-space:nowrap}
.note{color:var(--ink-2);font-size:.9rem}.warm{color:var(--warn)}.paused{color:var(--bad);font-weight:600}
tr.coin td{color:var(--ink-2)}a{color:var(--gold)}"""


def _n(x, fmt):
    return "–" if x is None or (isinstance(x, float) and not math.isfinite(x)) else format(x, fmt)


def page_html(s):
    """The dashboard section from a summary dict (only Python types: str, int, float, bool, None, list, dict)."""
    e = html.escape
    rows = []
    for r in s["rules"]:
        name = e(r["title_ar"])
        if r.get("warmup"):
            name += f'<div class="warm">{e(WARMUP_AR)}</div>'
        prog = "–" if r.get("progress") is None else f"{100 * r['progress']:.1f}%"
        rows.append(f'<tr><td class="title">{name}</td><td>{e(r["state_ar"])}</td><td class="num">{r["n"]}</td>'
                    f'<td class="num">{_n(r["net_sum"], "+.2f")}</td><td class="num">{_n(r["net_avg"], "+.2f")}</td>'
                    f'<td class="num">{prog}</td></tr>')
    c = s["c1"]
    c_avg = c["net_sum"] / c["n"] if c["n"] else None
    rows.append(f'<tr class="coin"><td class="title">{e(COIN_AR)}</td><td>مرجع للمقارنة</td><td class="num">{c["n"]}</td>'
                f'<td class="num">{_n(c["net_sum"], "+.2f")}</td><td class="num">{_n(c_avg, "+.2f")}</td>'
                f'<td class="num">–</td></tr>')
    state = f'<p class="paused">{e(PAUSED_AR)}</p>' if s["state"] != "RUNNING" else ""
    start = e(s["start"] or "لم يُحدَّد بعد")
    return f"""<!doctype html>
<html lang="ar" dir="rtl">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="robots" content="noindex, nofollow, noarchive">
<meta name="color-scheme" content="dark light">
<title>{e(TITLE_AR)}</title>
<link rel="stylesheet" href="../../fonts/fonts.css">
<style>
{CSS}
</style>
</head>
<body>
<main>
<h1>{e(TITLE_AR)}</h1>
<p class="sub">أربع أفكار من بحثنا السابق تُختبر على بيانات جديدة فقط، مقارنةً بالعملة العشوائية في الأيام نفسها.</p>
{state}
<section class="card">
<div class="table-wrap">
<table>
<thead><tr><th>الفكرة</th><th>الحالة</th><th>الصفقات</th><th>صافي $ للأونصة</th><th>متوسط الصفقة</th><th>التقدم نحو الاعتماد</th></tr></thead>
<tbody>
{chr(10).join(rows)}
</tbody>
</table>
</div>
</section>
<section class="card note">
<p>بداية المختبر الثاني: <bdi dir="ltr">{start}</bdi> · أيام التداول المحسوبة: <bdi>{s["days"]}</bdi></p>
<p>الاعتماد يحتاج دليلًا قويًا جدًا، فهذه الأفكار لن تُعتمد عمليًا إلا إذا ظهرت لها ميزة أكبر بكثير مما رأيناه في البحث.</p>
<p class="note">آخر تحديث <bdi dir="ltr">{e(s["asof_utc"])}</bdi></p>
<p class="note"><a href="../">{e(BACK_AR)}</a></p>
</section>
</main>
</body>
</html>
"""


def _clean(x):
    """Strict JSON values: a non-finite float becomes None."""
    if isinstance(x, float):
        return x if math.isfinite(x) else None
    if isinstance(x, dict):
        return {k: _clean(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_clean(v) for v in x]
    return x


def write_json(path, obj):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(_clean(obj), ensure_ascii=False, indent=1, allow_nan=False) + "\n", encoding="utf-8")


def site_json(s):
    return {k: v for k, v in s.items() if k != "halt_reasons"} | {"halt_reasons": s.get("halt_reasons", [])}


def write_site(site_dir, s):
    """lab_v2.json and index.html from the summary dict `s`."""
    site = Path(site_dir)
    site.mkdir(parents=True, exist_ok=True)
    write_json(site / "lab_v2.json", site_json(s))
    (site / "index.html").write_text(page_html(s), encoding="utf-8")
