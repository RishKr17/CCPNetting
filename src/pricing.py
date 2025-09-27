import numpy as np
import pandas as pd

def map_tenor_to_curve_col(tenor_yrs: int) -> str:
    if tenor_yrs <= 2:
        return "rate_2y"
    if tenor_yrs <= 5:
        return "rate_5y"
    return "rate_10y"

def dv01_usd(notional: float, tenor_yrs: float) -> float:
    # crude DV01: notional * (0.8*tenor) * 1bp * 0.9
    duration = 0.8 * float(tenor_yrs)
    return notional * duration * 1e-4 * 0.9

def pnl_irs_dv01(trade_row: pd.Series, rates_df: pd.DataFrame) -> pd.Series:
    tenor = int(trade_row["tenor_yrs"])
    col = map_tenor_to_curve_col(tenor)
    dr = rates_df[col].diff().fillna(0.0)       # Δrate (absolute)
    dv01 = dv01_usd(trade_row["notional"], tenor)
    sign = 1.0 if trade_row["pay_fixed"] else -1.0
    pnl = sign * dv01 * (-dr)                   # dPV ≈ -DV01 * Δr
    pnl.name = trade_row["trade_id"]
    return pnl

def pnl_fxfwd(trade_row: pd.Series, fx_df: pd.DataFrame) -> pd.Series:
    pair = str(trade_row["ccypair"])
    if pair not in fx_df.columns:
        raise ValueError(f"FX pair {pair} not found in fx data.")
    dS = fx_df[pair].diff().fillna(0.0)
    sign = 1.0 if trade_row["side"] == "BUY" else -1.0
    pnl = sign * trade_row["notional"] * dS
    pnl.name = trade_row["trade_id"]
    return pnl

def pnl_timeseries(trades: pd.DataFrame, rates_df: pd.DataFrame, fx_df: pd.DataFrame) -> pd.DataFrame:
    pnl_cols = []
    for _, tr in trades.iterrows():
        if tr["product"] == "IRS":
            pnl = pnl_irs_dv01(tr, rates_df)
        elif tr["product"] == "FXFWD":
            pnl = pnl_fxfwd(tr, fx_df)
        else:
            raise ValueError(f"Unsupported product: {tr['product']}")
        pnl_cols.append(pnl)
    pnl_df = pd.concat(pnl_cols, axis=1)
    pnl_df.index = pd.to_datetime(rates_df["date"])
    return pnl_df
