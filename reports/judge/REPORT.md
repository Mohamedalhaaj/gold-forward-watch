<div dir="rtl" lang="ar">

# تقرير الحَكَم المستقل

**الحكم: سليم** · السبب: كل الفحوص سليمة

- وقت الفحص: 2026-10-21T14:34:13Z
- الفحوص السليمة 7 من 9، ولم يُتحقق من 2

| الفحص | ما يتحقق منه | النتيجة |
|---|---|---|
| J1 | تطابق البيانات الخام مع تنزيل مستقل من المصدر | سليم |
| J2 | تسجيل كل قاعدة قبل نتائجها وثبات ملفاتها | سليم |
| J3 | عدم تعديل السجلات والبيانات الخام بعد كتابتها | سليم |
| J4 | ثبات الملفات المجمدة وكود الحكم | سليم |
| J5 | إعادة حساب التوقعات والإشارة والمعايرة والصفقات وملف الحالة | سليم |
| J6 | أداء التوقع ونسبة لمس الوقف على البيانات الجديدة | لا بيانات بعد |
| J7 | حداثة ملف الحالة وخلو آخر تشغيل من الأعطال | سليم |
| J8 | عدم إعادة كتابة تاريخ المستودع | لم يُتحقق |
| J9 | مقارنة السعر بمصدر مستقل | سليم |

حدود الحَكَم: يكشف الأخطاء والتعديلات اللاحقة، لكنه يعمل على الحساب نفسه ومن صنع الجهة نفسها، فلا يحمي من تلاعب متعمّد.

</div>

## Evidence

- Verdict: **SOUND** (reason code `sound`), checks ok 9 of 9; of these, nothing was verified in this run by: J6, J8
- HEAD checked: `9a18fc9c10aff1f64226f8f6cd7ea2a1ebcf9f93`
- Judge code sha256 (live manifest): `7f61f148af6d424626748434ba4aa1f49dc9a1d009bdb9d523d4d41920327c72`
- Binding spec: xauusd-quant `research/system/SYSTEM_V2_PREREG.md` §3 with Amendments B1 item 2 and B2 items 5-7, SYSTEM_V1_PREREG.md with Amendment A1, research/system/IMPLEMENTATION_REGISTER.md

- judge run 2026-10-21T14:34:13Z; data root repo

### J1: OK

- days new since the last judge run: 293 (checked now: 293); older days sampled: 0; sides compared equal: 15; revised: 0; known revisions: 0; unverified downloads: 571
- unverified: 571 downloads failed (unverified, not a mismatch)

### J2: OK

- v1 S1: registered 2026-10-17T18:55:29Z, first_day 2026-11-02
- v1 S1R: registered 2026-10-17T18:55:29Z, first_day 2026-11-02
- v1 C1: registered 2026-10-17T18:55:29Z, first_day 2026-11-02
- reports/system/START.json: start 2026-11-02 follows the rule for first_cloud_run_utc 2026-10-17T18:55:29Z
- reports/system/START.json: first committed in c62943036404 at 2026-10-17T18:55:48Z (first_cloud_run_utc 2026-10-17T18:55:29Z)

### J3: OK

- v1 raw files checked against their days.csv rows: 100 (0 problems)
- lookback raw files checked against their days.csv rows: 486 (0 problems)
- raw folders: 9 commits of the whole history checked for a modified, deleted, renamed or retyped raw file (0 problems)
- v1 append-only files: 15 files, 9 commits since v1 freeze 6cd6d57ef62d checked (0 problems)
- v2 append-only files: 11 files, 2 commits since v2 freeze 7a5ce4d22da2 checked (0 problems)
- judge records: 9 append-only files, 0 commits since judge-v1-freeze c2f43d043f8b checked (0 problems)

### J4: OK

- analysis/system/FROZEN.sha256: 23 pinned entries, 0 problems
- analysis/system/lab_v2/FROZEN_V2.sha256: 26 pinned entries, 0 problems
- reports/system/L3_ZSTAR.json unchanged since lab-v1-freeze

### J5: OK

- recomputed: {'forecasts': {'store_rows': 830, 'compared': 830}, 'l1': {'blocks': 0, 'green_ok': 1, 'trials': 0}, 'l3': {'months': 0, 'rows': 0}, 'v1': {'days': 0, 'trades': 0}, 'v2': {'days': 0, 'checked_days': [], 'trades': 0}, 'summary': {}, 'status': {'asof': '2026-10-21T14:30:56Z', 'lines': 24}}
- lab v2 days recomputed this run: 0 (new 0, rotating sample 0); new adjudication rows: 0

### J6: OK

- monthly checkpoint 2026-10 recorded (first judge run of the month)
- (a) no complete forward week yet (weeks 0)
- (b) QLIKE hours 0; DM stat nan; one-sided p (forecast worse) nan
- (c) hit rate green nan, red nan
- (d) no final lab trade yet

### J7: OK

- latest commit of reports/forward_site/system/VolMapSystem.csv: 1b63de112779 at 2026-10-21T14:32:44Z
- age 0 trading day(s) (limit 2)
- STATUS.md lists no operational failure

### J8: OK

- no previous judge run recorded
- unverified: the deployed VolMapJudge.csv could not be fetched (unverified, not a mismatch)

### J9: OK

- 2026-10-20: ok; credits 1
