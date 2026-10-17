"""Merge per-year Dukascopy m1 bid/ask CSVs into a single m1 parquet.

Output columns: ts (UTC), bid_o/h/l/c, ask_o/h/l/c, bid_vol, ask_vol,
mid_o/h/l/c, spread_c (ask_c - bid_c). Rows sorted, deduplicated on ts.
Rows present on only one side are kept with NaNs and counted (audit flags them).
"""

from pathlib import Path

import pandas as pd

RAW = Path(__file__).resolve().parent.parent / "data" / "raw"
OUT = Path(__file__).resolve().parent.parent / "data" / "parquet"
OUT.mkdir(parents=True, exist_ok=True)


def load_side(side: str) -> pd.DataFrame:
    files = sorted(RAW.glob(f"xauusd-m1-{side}-*.csv"))
    if not files:
        msg = f"no CSVs found for side {side}"
        raise SystemExit(msg)
    frames = [pd.read_csv(f) for f in files]
    df = pd.concat(frames, ignore_index=True)
    df["ts"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
    df = df.drop(columns=["timestamp"]).sort_values("ts")
    df = df.drop_duplicates(subset="ts", keep="first").set_index("ts")
    return df.rename(
        columns={
            "open": f"{side}_o",
            "high": f"{side}_h",
            "low": f"{side}_l",
            "close": f"{side}_c",
            "volume": f"{side}_vol",
        }
    )


def main() -> None:
    bid, ask = load_side("bid"), load_side("ask")
    m = bid.join(ask, how="outer")
    only_bid = int(m["ask_c"].isna().sum())
    only_ask = int(m["bid_c"].isna().sum())
    for p in "ohlc":
        m[f"mid_{p}"] = (m[f"bid_{p}"] + m[f"ask_{p}"]) / 2
    m["spread_c"] = m["ask_c"] - m["bid_c"]
    m.to_parquet(OUT / "m1.parquet")
    print(f"rows={len(m)} bid_only={only_bid} ask_only={only_ask}")
    print(f"range: {m.index.min()} .. {m.index.max()}")


if __name__ == "__main__":
    main()
