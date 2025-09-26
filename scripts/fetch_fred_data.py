import io
import datetime as dt
from pathlib import Path
import pandas as pd
import requests

OUT = Path("data")
OUT.mkdir(parents=True, exist_ok=True)

# Map FRED series -> simulator column names
SERIES = {
    # H.15 Treasuries (percent)
    "DGS2":  "rate_2y",
    "DGS5":  "rate_5y",
    "DGS10": "rate_10y",
    # H.10 FX (USD per EUR/GBP)
    "DEXUSEU": "EURUSD",
    "DEXUSUK": "GBPUSD",
}

def fetch_fred_csv(series_id: str) -> pd.DataFrame:
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}"
    r = requests.get(url, timeout=30)
    r.raise_for_status()
    df = pd.read_csv(io.StringIO(r.text))
    # Columns: DATE, <series_id>
    df.columns = ["date", series_id]
    df[series_id] = pd.to_numeric(df[series_id].replace(".", pd.NA))
    df[series_id] = df[series_id].ffill()
    df["date"] = pd.to_datetime(df["date"])
    # Keep ~last 5 years
    cutoff = pd.Timestamp.today().normalize() - pd.Timedelta(days=5*365)
    return df[df["date"] >= cutoff]

def main():
    frames = [fetch_fred_csv(sid) for sid in SERIES]
    from functools import reduce
    df = reduce(lambda a,b: pd.merge(a,b,on="date", how="inner"), frames).sort_values("date")

    # Convert Treasuries % -> decimals
    for sid in ["DGS2","DGS5","DGS10"]:
        df[sid] = df[sid] / 100.0

    # Rename to simulator columns
    df = df.rename(columns={sid: SERIES[sid] for sid in SERIES})

    # Trim to ~2y business days (optional, makes files small)
    if len(df) > 520:
        df = df.iloc[-520:]

    rates = df[["date", "rate_2y", "rate_5y", "rate_10y"]].copy()
    fx    = df[["date", "EURUSD", "GBPUSD"]].copy()
    rates["date"] = rates["date"].dt.date
    fx["date"]    = fx["date"].dt.date

    OUT.joinpath("rates.csv").write_text(rates.to_csv(index=False))
    OUT.joinpath("fx.csv").write_text(fx.to_csv(index=False))
    print("Wrote:", OUT/"rates.csv", "and", OUT/"fx.csv")

if __name__ == "__main__":
    main()
