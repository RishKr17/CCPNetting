import sys, traceback
import pandas as pd
from pathlib import Path
import datetime as dt

try:
    from pandas_datareader import data as pdr
except Exception:
    traceback.print_exc()
    sys.exit("Dependency import failed. Try: pip install --upgrade pandas pandas_datareader")

OUT = Path("data")
OUT.mkdir(parents=True, exist_ok=True)

end = dt.date.today()
start = end - dt.timedelta(days=5*365)  # ~5y back

# H.15 Treasuries (percent) -> decimals
rates = pdr.DataReader(["DGS2", "DGS5", "DGS10"], "fred", start, end)
rates = rates.ffill().dropna() / 100.0
rates.columns = ["rate_2y", "rate_5y", "rate_10y"]
rates = rates.reset_index().rename(columns={"index": "date"})
rates["date"] = pd.to_datetime(rates["date"]).dt.date

# H.10 FX (USD per EUR/GBP)
fx = pdr.DataReader(["DEXUSEU", "DEXUSUK"], "fred", start, end).ffill().dropna()
fx.columns = ["EURUSD", "GBPUSD"]
fx = fx.reset_index().rename(columns={"index": "date"})
fx["date"] = pd.to_datetime(fx["date"]).dt.date

# align calendars; trim to ~2y business days (optional)
df = pd.merge(rates, fx, on="date", how="inner").sort_values("date")
if len(df) > 520:
    df = df.iloc[-520:]

df[["date","rate_2y","rate_5y","rate_10y"]].to_csv(OUT/"rates.csv", index=False)
df[["date","EURUSD","GBPUSD"]].to_csv(OUT/"fx.csv", index=False)
print("Wrote:", OUT/"rates.csv", "and", OUT/"fx.csv")
