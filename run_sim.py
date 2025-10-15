#!/usr/bin/env python3
"""
Run Bilateral vs CCP comparison for a given trades CSV.

What it does
------------
1) Builds per-trade daily P&L (IRS via DV01×Δrate; FX via notional×Δspot)
2) Aggregates P&L into:
   - Bilateral netting sets (by counterparty)
   - Single CCP netting set (all trades together)
3) Computes:
   - VM path (daily outflows), cumulative plots
   - IM (99% 1d HS-VaR × √10) for bilateral and CCP
   - Netting efficiency, collateral delta, and worst 5-day liquidity
4) Writes charts + results.json to --outdir

Inputs
------
--trades  : CSV with columns [trade_id,cpty,product,notional,ccy,tenor_yrs,fixed_rate,pay_fixed,ccypair,side]
--rates   : CSV with columns [date,rate_2y,rate_5y,rate_10y] (decimals)
--fx      : CSV with columns [date, EURUSD, GBPUSD, ...] as available

Usage
-----
python run_sim.py --trades trades/sample_trades.csv --rates data/rates.csv --fx data/fx.csv --outdir outputs
"""

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from src.pricing import pnl_timeseries
from src.netting import netting_sets_bilateral, netting_set_ccp, aggregate_set_pnl
from src.margin import vm_outflows, im_hs_var, collateral_delta
from src.charts import plot_im_comparison, plot_vm_paths


def main(
    trades_path: str,
    rates_path: str,
    fx_path: str,
    outdir: str,
    stress_mult: float = 1.0,
    conc_threshold: float = 0.0,
    conc_addon_pct: float = 0.0,
):
    outdir = Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    # --- Load inputs
    trades = pd.read_csv(trades_path)
    rates = pd.read_csv(rates_path)
    fx = pd.read_csv(fx_path)

    # Normalize/align dates just in case
    for df in (rates, fx):
        if "date" in df.columns:
            df["date"] = pd.to_datetime(df["date"]).dt.tz_localize(None)

    # --- Build per-trade P&L timeseries
    pnl_df = pnl_timeseries(trades, rates, fx)
    if stress_mult != 1.0:
        pnl_df = pnl_df * float(stress_mult)

    # --- Netting sets
    bil_sets = netting_sets_bilateral(trades)
    ccp_set = netting_set_ccp(trades)

    bil_pnl = aggregate_set_pnl(pnl_df, bil_sets)   # columns: BILAT::<CP1>, BILAT::<CP2>, ...
    ccp_pnl = aggregate_set_pnl(pnl_df, ccp_set)    # single column: CCP::ALL

    # --- VM paths (outflows only)
    vm_bil_series = bil_pnl.apply(vm_outflows).sum(axis=1)
    vm_ccp_series = vm_outflows(ccp_pnl.iloc[:, 0])

    # --- IM (99% HS-VaR 1d × √10)
    im_bilateral = sum(im_hs_var(bil_pnl[col]) for col in bil_pnl.columns)
    im_ccp = im_hs_var(ccp_pnl.iloc[:, 0])

    # --- Optional: concentration add-on
    if conc_threshold > 0.0 and conc_addon_pct > 0.0:
        abs_notional_by_cpty = trades.groupby("cpty")["notional"].apply(lambda s: float(np.abs(s).sum()))
        addon_factor_bil = 1.0
        for total_abs in abs_notional_by_cpty.values:
            if total_abs > conc_threshold:
                addon_factor_bil += conc_addon_pct
        im_bilateral *= addon_factor_bil

        total_abs_notional = float(np.abs(trades["notional"]).sum())
        if total_abs_notional > conc_threshold:
            im_ccp *= (1.0 + conc_addon_pct)

    # --- VM totals + liquidity
    vm_bilateral_total = float(vm_bil_series.sum())
    vm_ccp_total = float(vm_ccp_series.sum())

    worst5_bil = float(vm_bil_series.rolling(5).sum().max())
    worst5_ccp = float(vm_ccp_series.rolling(5).sum().max())

    # --- KPIs
    net_eff = 1.0 - (im_ccp / im_bilateral) if im_bilateral > 0 else np.nan
    coll_delta = collateral_delta(im_ccp, vm_ccp_total, im_bilateral, vm_bilateral_total)

    # --- Plots
    plot_im_comparison(im_bilateral, im_ccp, str(outdir / "im_comparison.png"))
    plot_vm_paths(vm_bil_series, vm_ccp_series, str(outdir / "vm_paths.png"))

    # --- Persist results
    results = {
        "im_bilateral": im_bilateral,
        "im_ccp": im_ccp,
        "netting_efficiency": net_eff,
        "vm_bilateral_total": vm_bilateral_total,
        "vm_ccp_total": vm_ccp_total,
        "collateral_delta": coll_delta,
        "worst5_liquidity_bilateral": worst5_bil,
        "worst5_liquidity_ccp": worst5_ccp,
        "stress_mult": stress_mult,
        "concentration_threshold": conc_threshold,
        "concentration_addon_pct": conc_addon_pct,
    }
    (outdir / "results.json").write_text(json.dumps(results, indent=2))
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--trades", default="trades/sample_trades.csv", help="Trades CSV (simulator schema).")
    ap.add_argument("--rates", default="data/rates.csv", help="Rates CSV with date, rate_2y, rate_5y, rate_10y.")
    ap.add_argument("--fx", default="data/fx.csv", help="FX CSV with date and pairs (EURUSD, GBPUSD, ...).")
    ap.add_argument("--outdir", default="outputs", help="Output folder for charts + results.json.")
    ap.add_argument("--stress_mult", type=float, default=1.0, help="Scale factor for shocks (e.g., 1.5 for stress).")
    ap.add_argument("--conc_threshold", type=float, default=0.0, help="Abs notional threshold for concentration add-on.")
    ap.add_argument("--conc_addon_pct", type=float, default=0.0, help="Add-on percent (e.g., 0.10 = +10%) when threshold breached.")
    args = ap.parse_args()

    main(
        trades_path=args.trades,
        rates_path=args.rates,
        fx_path=args.fx,
        outdir=args.outdir,
        stress_mult=args.stress_mult,
        conc_threshold=args.conc_threshold,
        conc_addon_pct=args.conc_addon_pct,
    )
