.PHONY: data fx irs all run run-fx run-irs run-union clean

# Fetch H.10/H.15 into data/{rates.csv,fx.csv}
data:
\tpython scripts/fetch_fred_data.py

# Consolidate CME SDR FX CSVs in FX/ → trades/real_fx_usd_consolidated.csv
fx:
\tpython scripts/consolidate_fx_usd.py --in_dir FX --out trades/real_fx_usd_consolidated.csv

# Consolidate CME SDR IRS CSVs in IRS/ → trades/real_irs_usd_consolidated.csv
irs:
\tpython scripts/consolidate_irs_usd.py --in_dir IRS --out trades/real_irs_usd_consolidated.csv

# Run on sample trades
run:
\tpython run_sim.py --outdir outputs/sample

# Run on real FX
run-fx:
\tpython run_sim.py --trades trades/real_fx_usd_consolidated.csv --outdir outputs/fx_usd

# Run on real IRS
run-irs:
\tpython run_sim.py --trades trades/real_irs_usd_consolidated.csv --outdir outputs/irs_usd

# Combine IRS+FX then run
run-union:
\tpython - << 'PY'\nimport pandas as pd; irs=pd.read_csv("trades/real_irs_usd_consolidated.csv"); fx=pd.read_csv("trades/real_fx_usd_consolidated.csv"); pd.concat([irs,fx], ignore_index=True).to_csv("trades/real_irs_fx_usd.csv", index=False); print("Wrote trades/real_irs_fx_usd.csv")\nPY
\tpython run_sim.py --trades trades/real_irs_fx_usd.csv --outdir outputs/irs_fx_usd

clean:
\trm -rf outputs/*
