# Gold forward watch: cloud runner

Runs the two pre-registered forward watches on GitHub Actions and redeploys the dashboard, so it no longer
depends on the Mac being on.

- Dashboard: https://gold-watch-mq1dqc.xauusd-quant.workers.dev
- Rules: `reports/FORWARD_DOUBLETOP_PREREG.md` (frozen at xauusd-quant e2a1012), amended by
  `reports/FORWARD_DOUBLETOP_CAUSAL_PREREG.md` (b369671: the CAUSAL first-touch version is the primary,
  STRICT is a labelled non-executable reference), and `reports/FORWARD_WICK_PREREG.md` (frozen at 07932d7).
  Nothing in this repo changes them.

## The rule code is not edited

`analysis/` holds byte-identical copies of the trackers at xauusd-quant HEAD `c67ca11` (the double-top tracker
last changed in b369671, the wick tracker in e7ec199). Check with
`shasum -a 256 analysis/*.py`:

| file | sha256 | git blob |
|---|---|---|
| `forward_doubletop_tracker.py` | `fb3db8659b1a525c55aeb2622a3bda732cbc5c198abe456593cc93e01ab8b834` | `f46e0a3e1072` |
| `forward_wick_tracker.py` | `d1dc9d233cd95c929da192c07beefc66a3c2f9c529cad084e9eb4f4ad65b94b1` | `aab6618c044a` |

`pyproject.toml` and `uv.lock` are the research repo's, and the job runs `uv run --frozen` on Python 3.14, so
numpy 2.5.2 and pandas 3.0.5 match the Mac. The folder layout matches too, so the scripts write to the same
relative paths.

## What the job does

`.github/workflows/forward-watch.yml`, at the old LaunchAgent times (01:45, 12:15 and 18:15 Africa/Tripoli):

1. Wick tracker, then double-top tracker (each retried up to 3 times if the Yahoo fetch fails). A missed run is
   harmless: Yahoo keeps 60 days of 15-minute bars, so the next run backfills.
2. `wrangler deploy` of `reports/forward_site` (the trackers run without `--deploy`).
3. Commits `reports/forward_doubletop/trades.csv`, `reports/forward_wick/ledger.csv`, `STATUS.md`,
   `forward_strip.png`, `data.json` and every raw fetch under `data/forward_*/raw/` (the pre-registrations
   require every fetch to be kept untouched).
4. After both verdicts exist (or after 2026-12-15) it disables itself, as the old agents uninstalled themselves.

This job is the only writer of the ledgers. The Mac LaunchAgents (`com.xauusd.forwardwick`,
`com.xauusd.forwarddoubletop`) were unloaded on 2026-10-16 and their plists moved to
`~/Library/LaunchAgents/disabled/`. The Mac's earlier raw fetches were copied into `data/forward_*/raw/`.

## Secrets

The only secret is `CLOUDFLARE_API_TOKEN` (Workers Scripts: Edit on the one account), stored in GitHub
Secrets. It is never written to a file. The account ID in the workflow is not a secret.

## Reading the ledgers on the Mac

```bash
git -C ~/Documents/gold-forward-watch pull
```

## Gold support system v1 (branch `system-v1`, not enabled yet)

The binding spec is xauusd-quant `research/system/SYSTEM_V1_PREREG.md` (commit 39a685d) with its Amendment A1
(commit d1e8306). The job is `.github/workflows/system.yml` (03:20 and 09:20 UTC, Tuesday to Saturday, concurrency
group `forward-watch`), which runs `uv run --frozen python -I analysis/system/run.py`: Dukascopy M1 bid/ask fetch, the
write-once forecast store, L3 calibration and the green suppression, the forward signal lab, publish, then the same
wrangler deploy. It writes only `data/system/`, `reports/system/` and `reports/forward_site/system/`; the watches above
are untouched.

- Frozen semantics: `analysis/system/FROZEN.sha256` (check: `uv run --frozen python -I analysis/system/frozen_hashes.py`).
  `run.py` is I/O orchestration only; every lab and calibration decision is in a frozen module (A1 item 9).
- Vendored, byte-identical copies of xauusd-quant files: `analysis/system/vendor/SHA256SUMS`.
  `reports/system/L3_ZSTAR.json` is byte-identical to xauusd-quant `research/system/L3_ZSTAR.json` (a test pins them).
- Cloud mode runs only on `main` (`GITHUB_REF = refs/heads/main`). Exit code 1 = halted (lab PAUSED); 2 = an
  operation failed (the fetch raised, the deploy failed, complete data lag more than 2 trading days, the event
  calendars end within 60 days, or a calendar extension line was rejected or lost). Either way GitHub emails the owner.
- Event calendars after 2027: append official dates to `analysis/system/calendars_ext/events.csv`
  (`event,ts_utc,source_url`, e.g. `NFP,2028-01-07 13:30:00+00:00,https://www.bls.gov/schedule/news_release/empsit.htm`),
  at least 14 days ahead. The file is append-only and not frozen; each line is accepted or rejected for good the first
  time a cloud run sees it (`reports/system/calendar_ext.csv`). NYSE closures come from pandas_market_calendars per year.
- Tests: `uv run --frozen pytest tests/system` (the forecast parity against the client's HYCM log is blocking).
- Local runs only with `--dry` (a temp folder; on market data the lab is never run before the freeze):
  `run.py --dry --raw-from data/system` (real data: fetch, forecasts, L3, publish) and `run.py --dry --synthetic`
  (the end-to-end lab dry run on a synthetic random walk).
- Status file for the indicator: `/system/VolMapSystem.csv` (UTF-8 without a BOM; every line ASCII except a LIVE
  rule's Arabic title); lab card: `/system/`.
