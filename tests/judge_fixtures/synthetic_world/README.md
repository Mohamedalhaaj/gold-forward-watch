# Synthetic judge fixture: a complete v1 + lab v2 output tree

This folder is the output of the synthetic end-to-end dry run of the gold support system (v1 and lab v2), byte for
byte. It is a build and test input for the independent judge (xauusd-quant `research/system/SYSTEM_V2_PREREG.md` §3):
everything the judge reads from the real repository has the same paths and formats here, on synthetic data.
Binding description of every format and interpretation: xauusd-quant `research/system/IMPLEMENTATION_REGISTER.md`
(item R-FX describes this fixture).

## How it was produced

From the gold-forward-watch root, on branch `system-v2`:

```
uv run --frozen python -I analysis/system/lab_v2/run_v2.py --dry --synthetic --out tests/judge_fixtures/synthetic_world
uv run --frozen python -I analysis/system/lab_v2/v2_synth.py --manifest tests/judge_fixtures/synthetic_world
```

The first command builds the synthetic world, then runs v1 (`analysis/system/run.py` `one_run`, mode `synthetic`)
and lab v2 (`run_v2.one_run`, mode `synthetic`) in sequence at each simulated run time. The second writes
`MANIFEST.sha256` (sha256 of every file here except this README and the manifest). The test
`tests/system/lab_v2/test_v2_dry_run.py` regenerates the tree twice and requires both runs and this folder to be
byte-identical, so the fixture must be regenerated whenever v1 or v2 code changes.

## The synthetic world

- `data/system/raw/YYYY/MM/DD/{BID,ASK}.bi5`, UTC days 2026-09-01 .. 2026-12-04, from v1's `analysis/system/synth.py`
  (seed 7): a mid random walk from $4,200 with session volatility, flats in the model-clock daily break and on model
  weekends, a $0.30-0.50 spread. Then `analysis/system/lab_v2/v2_synth.py` `apply_edges` makes 11 deterministic edits
  (`EDGES`, model-clock times, 2026-11-16 .. 2026-12-02) so the runs reach every reachable branch of lab v2's
  decisions and execution (register R-FX lists them): a gap through a stop at an open, a 21-minute flat stretch inside
  a trade, wicks through $100 figures and through stops (in an entry minute, at an exit minute), and the ASK of UTC
  2026-12-01 `missing` (its days.csv row has status `missing` and fetched_utc = the day + 98 h 30 min, and there is no
  file), which leaves one-sided minutes with a NaN mid and undefined forecasts after it. Every edited file is still
  a valid body: 1,440 records with increasing seconds; only prices (and, for the flats, volumes) change.
- `data/system/lab_v2/lookback/raw/YYYY/MM/DD/{BID,ASK}.bi5`, UTC days 2026-01-01 .. 2026-08-31, from
  `analysis/system/lab_v2/v2_synth.py` (seed 11): the same kind of walk in whole cents, shifted to end at $4,200.000.
- Every file is a real Dukascopy body: LZMA-alone, big-endian `>5if` records (sec, open, close, low, high, volume),
  1,440 per day, prices × 1000 as int32. `days.csv` rows have `fetched_utc` = the day + 26 h 30 min (the one `missing`
  row: + 98 h 30 min), so each run sees exactly the days a real run would have fetched by then.
- No drift: no rule has an edge.
- The lookback store is complete before the first lab v2 run, so S3 never waits here (register R-V2-42). The waiting
  case (lookback days arriving late) is covered by `tests/system/lab_v2/test_v2_incomplete_lookback.py`, which
  compares its ledgers with this fixture's.

## The runs

UTC, all at 03:20: 2026-10-27 (Tue), 10-31, 11-03 (Tue), 11-07, 11-14, 11-21, 11-28, 12-05. v1 runs at every time;
lab v2 runs from 2026-11-03 (its first run). Results: v1 START 2026-11-02; v2 START 2026-11-09 (the later of v1's
START and the first Monday at least 2 days after 2026-11-03); v2 settles 2026-11-09 .. 2026-12-04 (20 days, the NYSE
holidays 2026-11-26 and 11-27 included with abstain_day decisions). Every decision outcome occurs (trade,
abstain_window, abstain_day, abstain_U, ignored_open), every trade exit reason (time, stop at X, stop at an open, gap)
and every twin exit reason, a twin that exits at another minute than its trade, and an entry at the earlier-close
fallback (S2 2026-12-01); `tests/system/lab_v2/test_v2_dry_run.py` checks each of them.

## The fake `registered_utc` convention (read this before using J2 or J8 on the fixture)

There is no git history here. Every REGISTERED row in `reports/system/lab/registry/events.csv` and
`reports/system/lab_v2/registry/events.csv` has `utc` = the simulated run time that first saw the registry files (v1
2026-10-27T03:20:00Z, v2 2026-11-03T03:20:00Z), `run_id` = `dry` and `head_sha` = `dry-placeholder`. The two START.json
files carry the simulated first run, run id and head the same way. Every other row's `*_utc` is the simulated run
time of the run that wrote it. So J2's "first appears in a commit whose committer time is <= utc + 60 min" and J8's
ancestry checks cannot be applied to this fixture; first_day, ledger dating, recomputation (J5), append-only
structure and every format check can.

## Layout

- `data/system/`: v1 raw store, `days.csv`, `forecasts.csv` (v1); `lab_v2/lookback/` (v2 lookback store).
- `reports/system/`: v1 `START.json`, `STATUS.md`, `L3_ZSTAR.json`, `l1_blocks.csv`, `l1_flags.json`,
  `ops_changes.csv`, `lab/` (v1 lab ledgers and registry); `lab_v2/` (v2 registry and events, `START.json`,
  `audit.csv`, `decisions.csv`, `trades.csv`, `twins.csv`, `eproc.csv`, `lab_days.csv`, `summary.json`,
  `STATUS.md`, `ops_changes.csv`).
- `reports/forward_site/system/`: v1 `VolMapSystem.csv` (with the `lab2_*` keys read from the previous v2 summary)
  and `lab.json`; `lab_v2/index.html` and `lab_v2.json` (the v2 dashboard section).

`ops_changes.csv` rows carry the sha256 of the OPS files at generation time and `head_sha` `dry-placeholder`.
