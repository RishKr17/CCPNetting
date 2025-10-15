#!/usr/bin/env python3
"""
Consolidate CME SDR FX day(s) into one USD-leg snapshot CSV for the simulator.

- Reads all files in --in_dir matching RT.FX.*.(csv|csv.zip)
- Merges slices across the day, drops CANCELs, keeps latest event per trade id
- Filters to FX asset class and pairs containing USD (EURUSD/USDCAD/etc.)
- Picks the USD leg notional (or largest leg if neither leg is USD)
- Writes a simulator-ready CSV with columns:
  trade_id, cpty, product, notional, ccy, tenor_yrs, fixed_rate, pay_fixed, ccypair, side
"""

import argparse
import io
import os
import re
from pathlib import Path
from typing import List, Optional

import numpy as np
import pandas as pd


# --------- helpers ---------

def list_input_files(in_dir: Path) -> List[Path]:
    pats = ["RT.FX.*.csv", "RT.FX.*.csv.zip", "*.csv", "*.csv.zip"]
    files = []
    for p in pats:
        files += list(in_dir.glob(p))
    # keep FX-looking files only
    files = [f for f in files if "FX" in f.name.upper()]
    return sorted(set(files))

def read_any_csv(path: Path) -> pd.DataFrame:
    """Read CSV or CSV in ZIP. Add __source_file column."""
    try:
        if path.suffix.lower() == ".zip":
            # pandas can read a CSV directly from a .zip path
            df = pd.read_csv(path)
        else:
            df = pd.read_csv(path)
    except Exception:
        df = pd.read_csv(path, encoding="latin-1")
    df["__source_file"] = path.name
    return df

def find_col(df: pd.DataFrame, *candidates) -> Optional[str]:
    """Return the first matching column name (case-insensitive), or None."""
    lower = {c.lower(): c for c in df.columns}
    for name in candidates:
        if name is None: 
            continue
        # allow regex via "re:<pattern>"
        if isinstance(name, str) and name.startswith("re:"):
            pat = re.compile(name[3:], re.I)
            for lc, orig in lower.items():
                if pat.search(lc):
                    return orig
        else:
            hit = lower.get(str(name).lower())
            if hit:
                return hit
    return None

def slice_order_from_name(fname: str) -> int:
    # e.g. RT.FX.20250926.1400.csv  ->  1400
    m = re.search(r"\.(\d{4})\.csv", fname)
    return int(m.group(1)) if m else 0

def to_datetime_utc(series: pd.Series) -> pd.Series:
    return pd.to_datetime(series, errors="coerce", utc=True)

def choose_usd_leg_amount(row) -> (float, str):
    """Prefer the USD leg notional; else the larger leg with its currency."""
    l1_amt = pd.to_numeric(row.get("leg1NotionalAmount"), errors="coerce")
    l2_amt = pd.to_numeric(row.get("leg2NotionalAmount"), errors="coerce")
    l1_ccy = str(row.get("leg1NotionalCurrency") or "").upper()
    l2_ccy = str(row.get("leg2NotionalCurrency") or "").upper()

    if l1_ccy == "USD" and pd.notna(l1_amt):
        return float(l1_amt), "USD"
    if l2_ccy == "USD" and pd.notna(l2_amt):
        return float(l2_amt), "USD"

    candidates = []
    if pd.notna(l1_amt):
        candidates.append((float(l1_amt), l1_ccy or "USD"))
    if pd.notna(l2_amt):
        candidates.append((float(l2_amt), l2_ccy or "USD"))
    if candidates:
        # pick the larger
        amt, ccy = sorted(candidates, key=lambda x: x[0], reverse=True)[0]
        return amt, ccy
    return np.nan, "USD"

def derive_ccypair(row) -> str:
    # Prefer UPI Underlier name like "EUR USD" -> "EURUSD"
    val = row.get("upiUnderlierName")
    if isinstance(val, str) and val.strip():
        parts = val.strip().split()
        if len(parts) == 2 and all(len(p) == 3 for p in parts):
            return (parts[0] + parts[1]).upper()

    for k in ("ccyPair", "pair", "symbol"):
        v = row.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip().upper()
    # currency1/currency2 pattern
    c1 = str(row.get("currency1") or row.get("baseCurrency") or "").upper()
    c2 = str(row.get("currency2") or row.get("quoteCurrency") or "").upper()
    if len(c1) == 3 and len(c2) == 3:
        return c1 + c2
    return ""

def is_usd_pair(ccypair: str) -> bool:
    s = (ccypair or "").upper()
    return len(s) == 6 and "USD" in s


# --------- main consolidation ---------

def consolidate_fx_usd(in_dir: Path, out_trades: Path, keep_events=("TRAD", "NEWT", "NEW", "CORR")) -> pd.DataFrame:
    files = list_input_files(in_dir)
    if not files:
        raise SystemExit(f"No FX CSV/ZIP files found in {in_dir}")

    frames = [read_any_csv(p) for p in files]
    raw = pd.concat(frames, ignore_index=True)

    # Soft schema detection
    id_col = find_col(raw, "disseminationIdentifier", "transactionId", "transactionIdentifier", "uti", "usi", "uniqueId", "executionId", "re:.*(uti|usi).*")
    ts_col = find_col(raw, "eventDateTime", "executionTimestamp", "executionTime", "reportedTimestamp", "submissionTime", "timestamp", "tradeDateTime")
    event_col = find_col(raw, "event", "eventType", "action", "msgType")

    # Normalize
    raw["_slice_order"] = raw["__source_file"].apply(slice_order_from_name)
    raw["_ts"] = to_datetime_utc(raw[ts_col]) if ts_col else pd.NaT
    raw["_event"] = raw[event_col].astype(str).str.upper() if event_col else ""
    raw["_asset"] = raw.get("assetClass", "").astype(str).str.upper()

    # Keep FX only (if assetClass exists), otherwise heuristic (rows with FX-ish underlier)
    fx_mask = raw["_asset"].eq("FX")
    if fx_mask.sum() == 0:
        # fallback heuristic: any row with FX-looking pair fields
        maybe_pair = raw.apply(derive_ccypair, axis=1)
        fx_mask = maybe_pair.str.len().eq(6)
    raw = raw[fx_mask].copy()

    # De-dup: drop CANCELs, keep latest by id (or composite if no id)
    raw = raw.sort_values(by=["_ts", "_slice_order"], ascending=[True, True])
    non_cancel = raw[~raw["_event"].str.contains("CANC", na=False)].copy()

    if id_col:
        # If keep_events set, filter to those
        if keep_events:
            non_cancel = non_cancel[non_cancel["_event"].isin(set(keep_events)) | non_cancel["_event"].eq("")].copy()
        dedup = non_cancel.drop_duplicates(subset=[id_col], keep="last")
    else:
        # Composite key fallback (best-effort)
        keys = []
        for guess in ("upiUnderlierName","pair","symbol","leg1NotionalAmount","leg1NotionalCurrency",
                      "leg2NotionalAmount","leg2NotionalCurrency","price","rate","effectiveDate","maturityDate"):
            c = find_col(non_cancel, guess)
            if c: keys.append(c)
        keys = keys or ["__source_file"]
        dedup = non_cancel.drop_duplicates(subset=keys, keep="last")

    # Keep only trading events for snapshot
    if keep_events:
        dedup = dedup[dedup["_event"].isin(set(keep_events)) | dedup["_event"].eq("")].copy()

    # Derive pair & USD notional
    dedup["__ccypair"] = dedup.apply(derive_ccypair, axis=1)
    amt_ccy = dedup.apply(choose_usd_leg_amount, axis=1, result_type="expand")
    amt_ccy.columns = ["__notional", "__ccy"]

    # Filter to USD pairs and rows where we hold USD notional
    mask_usd_pair = dedup["__ccypair"].apply(is_usd_pair)
    mask_usd_ccy  = amt_ccy["__ccy"].astype(str).str.upper().eq("USD")
    mask_amt_pos  = pd.to_numeric(amt_ccy["__notional"], errors="coerce").fillna(0) > 0

    snap = dedup[mask_usd_pair & mask_usd_ccy & mask_amt_pos].copy()

    # Build simulator schema
    trades = pd.DataFrame({
        "trade_id": [f"FXT{i:06d}" for i in range(1, len(snap)+1)],
        "cpty": ["UNKNOWN"] * len(snap),
        "product": ["FXFWD"] * len(snap),  # treat forwards/swaps alike for now
        "notional": pd.to_numeric(amt_ccy.loc[snap.index, "__notional"], errors="coerce").astype(float),
        "ccy": ["USD"] * len(snap),
        "tenor_yrs": ["" for _ in range(len(snap))],
        "fixed_rate": ["" for _ in range(len(snap))],
        "pay_fixed": ["" for _ in range(len(snap))],
        "ccypair": snap["__ccypair"].values,
        "side": ["" for _ in range(len(snap))]
    })

    out_trades.parent.mkdir(parents=True, exist_ok=True)
    trades.to_csv(out_trades, index=False)

    # Simple log to stdout
    print(f"Input files: {len(files)}  |  Raw rows: {len(raw)}  |  Kept USD rows: {len(trades)}")
    print(f"Wrote simulator-ready trades: {out_trades}")
    return trades


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in_dir", default="FX", help="Folder containing CME SDR FX CSVs/ZIPs")
    ap.add_argument("--out", default="trades/real_fx_usd_consolidated.csv", help="Output CSV path")
    ap.add_argument("--keep_events", default="TRAD,NEWT,NEW,CORR", help="Comma list of events to keep")
    args = ap.parse_args()

    in_dir = Path(args.in_dir)
    out = Path(args.out)
    keep_events = tuple(x.strip().upper() for x in args.keep_events.split(",")) if args.keep_events else None

    consolidate_fx_usd(in_dir, out, keep_events)


if __name__ == "__main__":
    main()
