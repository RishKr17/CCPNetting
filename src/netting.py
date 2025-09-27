import pandas as pd

def netting_sets_bilateral(trades: pd.DataFrame) -> dict:
    sets = {}
    for cpty, g in trades.groupby("cpty"):
        sets[f"BILAT::{cpty}"] = list(g["trade_id"])
    return sets

def netting_set_ccp(trades: pd.DataFrame) -> dict:
    return {"CCP::ALL": list(trades["trade_id"])}

def aggregate_set_pnl(pnl_df: pd.DataFrame, netting_map: dict) -> pd.DataFrame:
    out = {}
    for set_name, ids in netting_map.items():
        cols = [c for c in ids if c in pnl_df.columns]
        out[set_name] = pnl_df[cols].sum(axis=1)
    return pd.DataFrame(out)
