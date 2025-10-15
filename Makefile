.PHONY: data fx irs run run-fx run-irs run-union clean

data:
	python scripts/fetch_fred_data.py

fx:
	python scripts/consolidate_fx_usd.py --in_dir data/FX --out trades/real_fx_usd_consolidated.csv

irs:
	python scripts/consolidate_irs_usd.py --in_dir data/IRS --out trades/real_irs_usd_consolidated.csv

run:
	python run_sim.py --outdir outputs/sample

run-fx:
	python run_sim.py --trades trades/real_fx_usd_consolidated.csv --outdir outputs/fx_usd

run-irs:
	python run_sim.py --trades trades/real_irs_usd_consolidated.csv --outdir outputs/irs_usd

run-union:
	python -c 'import pandas as pd; irs=pd.read_csv("trades/real_irs_usd_consolidated.csv"); fx=pd.read_csv("trades/real_fx_usd_consolidated.csv"); pd.concat([irs,fx], ignore_index=True).to_csv("trades/real_irs_fx_usd.csv", index=False); print("Wrote trades/real_irs_fx_usd.csv")'
	python run_sim.py --trades trades/real_irs_fx_usd.csv --outdir outputs/irs_fx_usd

clean:
	rm -rf outputs/*
