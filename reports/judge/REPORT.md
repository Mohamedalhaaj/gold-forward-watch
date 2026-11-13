<div dir="rtl" lang="ar">

# تقرير الحَكَم المستقل

**الحكم: تحذير** · السبب: سعر مصدر مستقل يخالف البيانات

- وقت الفحص: 2026-11-13T20:27:55Z
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
- HEAD checked: `efd074c973e43baa29bf5a8eeff2be0e78803a4c`
- Judge code sha256 (live manifest): `7f61f148af6d424626748434ba4aa1f49dc9a1d009bdb9d523d4d41920327c72`
- Binding spec: xauusd-quant `research/system/SYSTEM_V2_PREREG.md` §3 with Amendments B1 item 2 and B2 items 5-7, SYSTEM_V1_PREREG.md with Amendment A1, research/system/IMPLEMENTATION_REGISTER.md

- judge run 2026-11-13T20:27:55Z; data root repo

### J1: OK

- days new since the last judge run: 0 (checked now: 0); older days sampled: 20; sides compared equal: 15; revised: 0; known revisions: 0; unverified downloads: 25
- unverified: 25 downloads failed (unverified, not a mismatch)

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

- v1 raw files checked against their days.csv rows: 146 (0 problems)
- lookback raw files checked against their days.csv rows: 486 (0 problems)
- raw folders: 27 commits of the whole history checked for a modified, deleted, renamed or retyped raw file (0 problems)
- v1 append-only files: 15 files, 47 commits since v1 freeze 6cd6d57ef62d checked (0 problems)
- v2 append-only files: 11 files, 13 commits since v2 freeze 7a5ce4d22da2 checked (0 problems)
- judge records: 9 append-only files, 56 commits since judge-v1-freeze c2f43d043f8b checked (0 problems)

### J4: OK

- analysis/system/FROZEN.sha256: 23 pinned entries, 0 problems
- analysis/system/lab_v2/FROZEN_V2.sha256: 26 pinned entries, 0 problems
- reports/system/L3_ZSTAR.json unchanged since lab-v1-freeze

### J5: OK

- recomputed: {'forecasts': {'store_rows': 1220, 'compared': 1220}, 'l1': {'blocks': 1, 'green_ok': 1, 'trials': 208}, 'l3': {'months': 0, 'rows': 0}, 'v1': {'days': 9, 'trades': 11}, 'v2': {'days': 9, 'checked_days': ['2026-11-03', '2026-11-04', '2026-11-06'], 'trades': 3}, 'summary': {'asof': '2026-11-13T17:17:25Z'}, 'status': {'asof': '2026-11-13T17:14:34Z', 'lines': 28}}
- lab v2 days recomputed this run: 3 (new 0, rotating sample 3); new adjudication rows: 0

### J6: OK

- (a) complete weeks 1, hour trials 115, pooled hit rate 0.1261 (95% CI nan .. nan)
- (b) QLIKE hours 208; DM stat 1.554; one-sided p (forecast worse) 0.9399
- (c) hit rate green 0.1186, red 0.3333
- (d) v1 C1: 9 trades, net -48.00 $/oz, mean -5.334
- (d) v1 S1: 1 trades, net -0.15 $/oz, mean -0.150
- (d) v1 S1R: 1 trades, net -0.92 $/oz, mean -0.925
- (d) v2 S2: 10 trades, net 104.09 $/oz, mean 10.409
- (d) v2 S3: 2 trades, net 30.45 $/oz, mean 15.225
- (d) v2 S4: 4 trades, net 3.42 $/oz, mean 0.856
- (d) v2 S5: 2 trades, net 10.24 $/oz, mean 5.121

### J7: OK

- latest commit of reports/forward_site/system/VolMapSystem.csv: 5abee84cc5ff at 2026-11-13T17:17:22Z
- age 0 trading day(s) (limit 2)
- STATUS.md lists no operational failure

### J8: OK

- the previous VERDICTS.csv row head 01c3bdfa84f3 is an ancestor of HEAD efd074c973e4
- the published VolMapJudge.csv head 01c3bdfa84f3 is an ancestor of HEAD efd074c973e4
- the deployed VolMapJudge.csv head 01c3bdfa84f3 is an ancestor of HEAD efd074c973e4

### J9: WARNING

- 2026-11-12 already checked (exceeds); no request sent
- the two most recent checked days 2026-11-11 and 2026-11-12 both exceed the limits (median > $0.50 or max > $5)
