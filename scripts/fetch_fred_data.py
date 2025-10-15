#!/usr/bin/env python3
import io
from pathlib import Path
from functools import reduce
import pandas as pd
import requests

OUT = Path("data")
OUT.mkdir(parents=True, exist_ok=True)

# H.15 Treasuries (percent -> decimals)
RATES_SERIES = {
    "rate_2y":  "DGS2",
    "rate_5y":  "DGS5",
    "rate_10y": "DGS10",
}

# H.10 FX (some are USD per foreign unit, some are foreign per USD)
# We map to intuitive column names and add inverses only if the base exists.
FX_SERIES = {
    "EURUSD": "DEXUSEU",  # USD per EUR
    "GBPUSD": "DEXUSUK",  # USD per GBP
    "USDJPY": "DEXJPUS",  # JPY per USD
    "USDCAD": "DEXCAUS",  # CAD per USD
    "USDMXN": "DEXMXUS",  # MXN per USD
    "USDBRL": "DEXBZUS",  # BRL per USD
}

INVERSES = [("USDJPY", "JPYUSD"), ("USDCAD", "CADUSD"), ("USDMXN", "MXNUSD"), ("USDBRL", "BRLUSD")]

def fred_csv(series_id: str) -> pd.DataFrame:
    """Fetch a FRED series as a tidy DataFrame [date, series_id]."""
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}"
    r = requests.get(url, timeout=30)
    r.raise_for_status()
    df = pd.read_csv(io.StringIO(r.text))
    df.columns = ["date", series_id]
    # FRED uses "." for missing; cast to NA and forward fill
    df[series_id] = pd.to_numeric(df[series_id].replace(".", pd.NA))
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date").ffill()
    # keep ~last 5 years
    cutoff = pd.Timestamp.today().normalize() - pd.Timedelta(days=5 * 365)
    return df[df["date"] >= cutoff]

def safe_outer_merge(frames):
    """Outer-merge a list of [date, col] frames on date."""
    if not frames:
        return pd.DataFrame({"date": []})
    out = frames[0]
    for f in frames[1:]:
        out = pd.merge(out, f, on="date", how="outer")
    return out.sort_values("date")

def main():
    # -------- Rates --------
    rate_frames = []
    fetched_rates = []
    for nice, fred_id in RATES_SERIES.items():
        try:
            df = fred_csv(fred_id)
            rate_frames.append(df.rename(columns={fred_id: nice}))
            fetched_rates.append(nice)
        except Exception as e:
            print(f"[WARN] Failed to fetch {fred_id} -> {nice}: {e}")

    rates = safe_outer_merge(rate_frames)
    if not rates.empty:
        # convert percent -> decimals for DGS*
        for nice in fetched_rates:
            rates[nice] = pd.to_numeric(rates[nice], errors="coerce")
        # trim to last ~520 rows for compactness
        rates = rates.ffill()
        if len(rates) > 520:
            rates = rates.iloc[-520:]
        rates["date"] = rates["date"].dt.date
        rates[["date"] + fetched_rates].to_csv(OUT / "rates.csv", index=False)
        print(f"[OK] Wrote {OUT/'rates.csv'} with columns: {['date']+fetched_rates}")
    else:
        print("[WARN] No rates written (all fetches failed).")

    # -------- FX --------
    fx_frames = []
    fetched_fx_cols = []
    for nice, fred_id in FX_SERIES.items():
        try:
            df = fred_csv(fred_id)
            fx_frames.append(df.rename(columns={fred_id: nice}))
            fetched_fx_cols.append(nice)
        except Exception as e:
            print(f"[WARN] Failed to fetch {fred_id} -> {nice}: {e}")

    fx = safe_outer_merge(fx_frames)
    if not fx.empty:
        fx = fx.ffill()
        # Add inverses only if the source exists
        for base, inv in INVERSES:
            if base in fx.columns:
                try:
                    fx[inv] = 1.0 / pd.to_numeric(fx[base], errors="coerce")
                    fetched_fx_cols.append(inv)
                except Exception as e:
                    print(f"[WARN] Could not compute inverse {inv} from {base}: {e}")

        # trim and write
        if len(fx) > 520:
            fx = fx.iloc[-520:]
        fx["date"] = fx["date"].dt.date
        cols = ["date"] + sorted(set(fetched_fx_cols))
        fx[cols].to_csv(OUT / "fx.csv", index=False)
        print(f"[OK] Wrote {OUT/'fx.csv'} with columns: {cols}")
    else:
        print("[WARN] No fx written (all fetches failed).")

if __name__ == "__main__":
    main()
