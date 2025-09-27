import numpy as np
import pandas as pd

def vm_outflows(pnl_series: pd.Series) -> pd.Series:
    return (-pnl_series).clip(lower=0.0)

def im_hs_var(pnl_series: pd.Series, cl: float = 0.99, horizon_days: int = 10) -> float:
    losses = -pnl_series.dropna()
    if len(losses) < 50:
        q = np.quantile(losses, cl)
    else:
        q = losses.quantile(cl, interpolation="linear")
    return float(q * np.sqrt(horizon_days))

def collateral_delta(im_ccp: float, vm_ccp: float, im_bil: float, vm_bil: float) -> float:
    return (im_ccp + vm_ccp) - (im_bil + vm_bil)
