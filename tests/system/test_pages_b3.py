"""Amendment B3 item 3 (SYSTEM_V2_PREREG.md): Arabic number agreement on the two pages, display only.

The page code is inline JavaScript, so these tests cut the helpers and the expressions that build the text out of the
HTML and run them in node with stub formatters. They skip when node is not installed.

- reports/forward_site/index.html (the forward-watch dashboard): the plural helper tests n mod 100; a count that
  stands alone (the day cell's aria-label and title) uses the nominative dual «صفقتان»; «متوقع» replaces «متوقعة»; the
  trigger-day tooltip prints |B_pts| with one decimal after ارتفع/انخفض, and «بلا تغيير» at 0.
- reports/forward_site/system/index.html (v1's lab page, an OPS file): the chosen-rules sentence agrees for 1 and 2;
  the 0 branch is unchanged.
"""
import json
import re
import shutil
import subprocess

import pytest

DASH = pytest.ROOT / "reports" / "forward_site" / "index.html"
LAB = pytest.ROOT / "reports" / "forward_site" / "system" / "index.html"


def node(tmp_path, js):
    exe = shutil.which("node")
    if exe is None:
        pytest.skip("node is not installed")
    f = tmp_path / "page_check.js"
    f.write_text(js, encoding="utf-8")
    r = subprocess.run([exe, str(f)], capture_output=True, text=True, encoding="utf-8")
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


def one(pattern, text):
    found = re.findall(pattern, text, flags=re.M)
    assert len(found) == 1, (pattern, found)
    return found[0]


# ---------------------------------------------------------------- the forward-watch dashboard
CASES = [0, 1, 2, 3, 10, 11, 99, 100, 101, 102, 103, 105, 110, 111, 203, 1005]
TRADES = {0: "بلا صفقات", 1: "صفقة واحدة", 2: "صفقتين", 3: "3 صفقات", 10: "10 صفقات", 11: "11 صفقة", 99: "99 صفقة",
          100: "100 صفقة", 101: "101 صفقة", 102: "102 صفقة", 103: "103 صفقات", 105: "105 صفقات", 110: "110 صفقات",
          111: "111 صفقة", 203: "203 صفقات", 1005: "1005 صفقات"}
DAYS = {1: "يوم واحد", 2: "يومين", 3: "3 أيام", 10: "10 أيام", 11: "11 يومًا", 20: "20 يومًا", 103: "103 أيام"}
TIPS = [(None, "DAY: لم يكتمل"), ({"trigger": 0, "B_pts": -0.2}, "DAY: لا ذيل"),
        ({"trigger": 1, "B_pts": -24.3}, "DAY: انخفض 24.3 نقطة"), ({"trigger": 1, "B_pts": 5}, "DAY: ارتفع 5.0 نقطة"),
        ({"trigger": 1, "B_pts": 2}, "DAY: ارتفع 2.0 نقطة"), ({"trigger": 1, "B_pts": -0.2}, "DAY: انخفض 0.2 نقطة"),
        ({"trigger": 1, "B_pts": 120}, "DAY: ارتفع 120.0 نقطة"), ({"trigger": 1, "B_pts": 0}, "DAY: بلا تغيير")]
CELLS = [(None, "LONG: لم يكتمل بعد", "DAY — لم يكتمل بعد"),
         ({"net": 3.26, "trades": 2}, "LONG: $3.26، صفقتان", "DAY — $3.26، صفقتان"),
         ({"net": -1.5, "trades": 1}, "LONG: $-1.5، صفقة واحدة", "DAY — $-1.5، صفقة واحدة"),
         ({"net": 0, "trades": 0}, "LONG: $0، بلا صفقات", "DAY — $0، بلا صفقات"),
         ({"net": 4.1, "trades": 7}, "LONG: $4.1، 7 صفقات", "DAY — $4.1، 7 صفقات"),
         ({"net": 4.1, "trades": 12}, "LONG: $4.1، 12 صفقة", "DAY — $4.1، 12 صفقة")]


@pytest.fixture(scope="module")
def dash():
    return DASH.read_text(encoding="utf-8")


def dashboard_js(html):
    helpers = "\n".join(one(rf"^\s*(const {name} = .*;)$", html) for name in ("plural", "daysAr", "tradesAr"))
    aria = one(r'"aria-label": (`[^`]*tradesAr\([^`]*`)', html)
    title = one(r"title: (`[^`]*tradesAr\([^`]*`)", html)
    tip = one(r"title: (`[^`]*B_pts[^`]*`)", html)
    summary = one(r"^\s*(sm\.append\(.*للأونصة من.*\);)$", html)
    return f"""
{helpers}
const longFmt = {{ format: () => "LONG" }}, dayFmt = {{ format: () => "DAY" }}, d0 = x => x;
const fmtMoney = x => "$" + x, fmtPct = x => "P" + x, el = (tag, attrs, ...kids) => kids.join("");
const day = "2026-10-19";
const cell = r => [{aria}, {title}];
const tip = r => {tip};
const summary = (D, st, IS) => {{ let OUT; const sm = {{ append: (...a) => {{ OUT = a.join(""); }} }}; {summary} return OUT; }};
const T = {json.dumps(CASES)};
console.log(JSON.stringify({{
  trades: T.map(n => tradesAr(n)), tradesNom: T.map(n => tradesAr(n, true)),
  days: {json.dumps(list(DAYS))}.map(n => daysAr(n)),
  cells: {json.dumps([c[0] for c in CELLS])}.map(cell),
  tips: {json.dumps([t[0] for t in TIPS])}.map(tip),
  summary: [summary({{ days_done: 5 }}, {{ total: 12.5, trades: 105, avg_day: 2.5, days_pos: 0.6 }}, {{ avg_day: 0.48 }}),
            summary({{ days_done: 2 }}, {{ total: -3, trades: 2, avg_day: -1.5, days_pos: 0 }}, {{ avg_day: 0.48 }})],
}}));
"""


@pytest.fixture(scope="module")
def dash_out(dash, tmp_path_factory):
    return node(tmp_path_factory.mktemp("dash"), dashboard_js(dash))


def test_the_plural_helper_tests_n_mod_100(dash_out):
    assert dash_out["trades"] == [TRADES[n] for n in CASES]
    assert dash_out["days"] == list(DAYS.values())


def test_a_count_that_stands_alone_takes_the_nominative_dual(dash_out):
    assert dash_out["tradesNom"] == [("صفقتان" if n == 2 else TRADES[n]) for n in CASES]
    assert dash_out["cells"] == [[a, t] for _, a, t in CELLS]


def test_the_summary_says_mutawaqqa_masculine_and_keeps_the_genitive_dual_after_min(dash, dash_out):
    assert dash_out["summary"] == [
        "بعد 5 أيام: $12.5 للأونصة من 105 صفقات. متوسط اليوم $2.5 مقابل $0.48 متوقع، وP0.6 من أيام التداول رابحة.",
        "بعد يومين: $-3 للأونصة من صفقتين. متوسط اليوم $-1.5 مقابل $0.48 متوقع، وP0 من أيام التداول رابحة."]
    assert "متوقعة" not in dash


def test_the_trigger_day_tooltip_prints_the_absolute_points_with_one_decimal(dash_out):
    assert dash_out["tips"] == [want for _, want in TIPS]


# ---------------------------------------------------------------- v1's lab page (OPS file)
PREFIX = "آخر جولة بحث 2027-01-02. فُحصت 1,920 قاعدة على آخر 60 يومًا من بيانات المختبر، "
CHOSEN = {0: "ولم تتجاوز أفضل نتيجة ما تعطيه الصدفة، فلم تُضف قاعدة.",
          1: "وأُضيفت قاعدة واحدة منها لأنها تجاوزت ما تعطيه الصدفة. تُحاسَب على الأيام التالية لتسجيلها فقط.",
          2: "وأُضيفت قاعدتان منها لأنهما تجاوزتا ما تعطيه الصدفة. تُحاسَبان على الأيام التالية لتسجيلهما فقط."}


def lab_js(html):
    helpers = re.search(r"^  const fmt = .*?^  const ltr = [^\n]*;$", html, flags=re.M | re.S).group(0)
    block = re.search(r"^    const pr = d\.proposer;$.*?(?=^    const l3 = )", html, flags=re.M | re.S).group(0)
    assert block.count('document.getElementById("proposer").innerHTML =') == 1
    block = block.replace('document.getElementById("proposer").innerHTML =', "OUT =")
    runs = [{"run_date": "2027-01-02", "n_rules": 1920, "n_train": 60, "chosen": [{"id": f"P{i}"} for i in range(k)]}
            for k in (0, 1, 2)]
    return f"""
{helpers}
const proposer = d => {{ let OUT; {block} return OUT; }};
console.log(JSON.stringify({json.dumps(runs)}.map(pr => proposer({{ proposer: pr }})).concat([proposer({{}})])));
"""


def test_the_chosen_rules_sentence_agrees_for_one_and_two(tmp_path):
    html = LAB.read_text(encoding="utf-8")
    out = node(tmp_path, lab_js(html))
    for k, got in enumerate(out[:3]):
        assert got.startswith("<h2>البحث عن قواعد جديدة</h2><p>") and got.endswith("</p>")
        text = re.sub(r"<[^>]+>", "", got[len("<h2>البحث عن قواعد جديدة</h2>"):])
        assert text == PREFIX + CHOSEN[k]
    assert out[3] == ('<h2>البحث عن قواعد جديدة</h2><p class="muted">لم تبدأ جولات البحث بعد. تبدأ بعد أن يجمع المختبر 40'
                      " يومًا من بياناته، ثم تتكرر كل أربعة أسابيع</p>")
