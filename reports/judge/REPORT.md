<div dir="rtl" lang="ar">

# تقرير الحَكَم المستقل

**الحكم: تحذير** · السبب: سعر مصدر مستقل يخالف البيانات

- وقت الفحص: 2026-11-12T17:38:25Z
- الفحوص السليمة 8 من 9

| الفحص | ما يتحقق منه | النتيجة |
|---|---|---|
| J1 | تطابق البيانات الخام مع تنزيل مستقل من المصدر | سليم |
| J2 | تسجيل كل قاعدة قبل نتائجها وثبات ملفاتها | سليم |
| J3 | عدم تعديل السجلات والبيانات الخام بعد كتابتها | سليم |
| J4 | ثبات الملفات المجمدة وكود الحكم | سليم |
| J5 | إعادة حساب التوقعات والإشارة والمعايرة والصفقات وملف الحالة | سليم |
| J6 | أداء التوقع ونسبة لمس الوقف على البيانات الجديدة | سليم |
| J7 | حداثة ملف الحالة وخلو آخر تشغيل من الأعطال | سليم |
| J8 | عدم إعادة كتابة تاريخ المستودع | سليم |
| J9 | مقارنة السعر بمصدر مستقل | تحذير |

حدود الحَكَم: يكشف الأخطاء والتعديلات اللاحقة، لكنه يعمل على الحساب نفسه ومن صنع الجهة نفسها، فلا يحمي من تلاعب متعمّد.

</div>

## Evidence

- Verdict: **WARNING** (reason code `j9_price`), checks ok 8 of 9
- HEAD checked: `833f4375e0a3552e76e462dfc66c970cf3ab4126`
- Judge code sha256 (live manifest): `7f61f148af6d424626748434ba4aa1f49dc9a1d009bdb9d523d4d41920327c72`
- Binding spec: xauusd-quant `research/system/SYSTEM_V2_PREREG.md` §3 with Amendments B1 item 2 and B2 items 5-7, SYSTEM_V1_PREREG.md with Amendment A1, research/system/IMPLEMENTATION_REGISTER.md

- judge run 2026-11-12T17:38:25Z; data root repo

### J1: OK

- days new since the last judge run: 0 (checked now: 0); older days sampled: 20; sides compared equal: 20; revised: 0; known revisions: 0; unverified downloads: 20
- unverified: 20 downloads failed (unverified, not a mismatch)

### J2: OK

- v1 S1: registered 2026-10-17T18:55:29Z, first_day 2026-11-02
- v1 S1R: registered 2026-10-17T18:55:29Z, first_day 2026-11-02
- v1 C1: registered 2026-10-17T18:55:29Z, first_day 2026-11-02
- v2 S2: registered 2026-10-22T08:42:33Z, first_day 2026-11-02
- v2 S3: registered 2026-10-22T08:42:33Z, first_day 2026-11-02
- v2 S4: registered 2026-10-22T08:42:33Z, first_day 2026-11-02
- v2 S5: registered 2026-10-22T08:42:33Z, first_day 2026-11-02
- reports/system/START.json: start 2026-11-02 follows the rule for first_cloud_run_utc 2026-10-17T18:55:29Z
- reports/system/START.json: first committed in c62943036404 at 2026-10-17T18:55:48Z (first_cloud_run_utc 2026-10-17T18:55:29Z)
- reports/system/lab_v2/START.json: start 2026-11-02 follows the rule for first_cloud_run_utc 2026-10-22T08:42:33Z
- reports/system/lab_v2/START.json: first committed in 78c13fa583e7 at 2026-10-22T08:42:36Z (first_cloud_run_utc 2026-10-22T08:42:33Z)

### J3: OK

- v1 raw files checked against their days.csv rows: 144 (0 problems)
- lookback raw files checked against their days.csv rows: 486 (0 problems)
- raw folders: 26 commits of the whole history checked for a modified, deleted, renamed or retyped raw file (0 problems)
- v1 append-only files: 15 files, 45 commits since v1 freeze 6cd6d57ef62d checked (0 problems)
- v2 append-only files: 11 files, 12 commits since v2 freeze 7a5ce4d22da2 checked (0 problems)
- judge records: 9 append-only files, 52 commits since judge-v1-freeze c2f43d043f8b checked (0 problems)

### J4: OK

- analysis/system/FROZEN.sha256: 23 pinned entries, 0 problems
- analysis/system/lab_v2/FROZEN_V2.sha256: 26 pinned entries, 0 problems
- reports/system/L3_ZSTAR.json unchanged since lab-v1-freeze

### J5: OK

- recomputed: {'forecasts': {'store_rows': 1197, 'compared': 1197}, 'l1': {'blocks': 1, 'green_ok': 1, 'trials': 185}, 'l3': {'months': 0, 'rows': 0}, 'v1': {'days': 8, 'trades': 8}, 'v2': {'days': 8, 'checked_days': ['2026-11-03', '2026-11-05', '2026-11-09'], 'trades': 7}, 'summary': {'asof': '2026-11-12T17:38:00Z'}, 'status': {'asof': '2026-11-12T17:37:11Z', 'lines': 28}}
- lab v2 days recomputed this run: 3 (new 0, rotating sample 3); new adjudication rows: 0

### J6: OK

- (a) complete weeks 1, hour trials 115, pooled hit rate 0.1261 (95% CI nan .. nan)
- (b) QLIKE hours 185; DM stat 1.386; one-sided p (forecast worse) 0.9171
- (c) hit rate green 0.1192, red 0.3333
- (d) v1 C1: 8 trades, net -18.15 $/oz, mean -2.269
- (d) v2 S2: 8 trades, net 94.40 $/oz, mean 11.799
- (d) v2 S3: 1 trades, net -4.49 $/oz, mean -4.490
- (d) v2 S4: 3 trades, net 6.02 $/oz, mean 2.007
- (d) v2 S5: 1 trades, net 22.79 $/oz, mean 22.788

### J7: OK

- latest commit of reports/forward_site/system/VolMapSystem.csv: 74950dcdb0e2 at 2026-11-12T17:37:56Z
- age 0 trading day(s) (limit 2)
- STATUS.md lists no operational failure

### J8: OK

- the previous VERDICTS.csv row head 63fdeac534cf is an ancestor of HEAD 833f4375e0a3
- the published VolMapJudge.csv head 63fdeac534cf is an ancestor of HEAD 833f4375e0a3
- the deployed VolMapJudge.csv head 63fdeac534cf is an ancestor of HEAD 833f4375e0a3

### J9: WARNING

- 2026-11-11 already checked (exceeds); no request sent
- the two most recent checked days 2026-11-09 and 2026-11-11 both exceed the limits (median > $0.50 or max > $5)
