# Gold forward watch: cloud runner

Runs the two pre-registered forward watches on GitHub Actions and redeploys the dashboard, so it no longer
depends on the Mac being on.

- Dashboard: https://gold-watch-mq1dqc.xauusd-quant.workers.dev
- Rules: `reports/FORWARD_DOUBLETOP_PREREG.md` (frozen at xauusd-quant e2a1012) and
  `reports/FORWARD_WICK_PREREG.md` (frozen at 07932d7). Nothing in this repo changes them.

## The rule code is not edited

`analysis/` holds byte-identical copies of the trackers at xauusd-quant HEAD `e7ec199`. Check with
`shasum -a 256 analysis/*.py`:

| file | sha256 | git blob |
|---|---|---|
| `forward_doubletop_tracker.py` | `80724c0bc7d4b89f0c535adc90d8862a4d89f854cdc0bcba4fb8850a70fd091d` | `34158868af9a` |
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

This job is the only writer of the ledgers. The schedule stays commented out until the Mac LaunchAgents
(`com.xauusd.forwardwick`, `com.xauusd.forwarddoubletop`) are disabled, so there are never two writers.

## Secrets

The only secret is `CLOUDFLARE_API_TOKEN` (Workers Scripts: Edit on the one account), stored in GitHub
Secrets. It is never written to a file. The account ID in the workflow is not a secret.

## Reading the ledgers on the Mac

```bash
git -C ~/Documents/gold-forward-watch pull
```
