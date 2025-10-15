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

def compute_netting_metrics(pnl_df: pd.DataFrame, trades: pd.DataFrame) -> pd.DataFrame:
    """
    Compute PnL aggregated under bilateral and CCP netting sets.

    Args:
        pnl_df (pd.DataFrame): Time series of trade-level PnL.
        trades (pd.DataFrame): Trade metadata containing 'trade_id' and 'cpty'.

    Returns:
        pd.DataFrame: Aggregated PnL across netting sets (columns are netting sets).
    """
    # Define bilateral and CCP netting structures
    bilateral_sets = netting_sets_bilateral(trades)
    ccp_set = netting_set_ccp(trades)

    # Combine the mappings
    all_sets = {**bilateral_sets, **ccp_set}

    # Aggregate PnL by netting set
    agg_pnl = aggregate_set_pnl(pnl_df, all_sets)

    return agg_pnl
