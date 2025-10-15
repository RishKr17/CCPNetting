#!/usr/bin/env python3
"""
Consolidate CME SDR Interest Rate (IRS) day/hour CSVs into a USD-denominated snapshot
that matches the simulator schema.

- Reads all files in --in_dir (CSV or CSV.zip), e.g., RT.IRS.20250926.XXXX.csv(.zip)
- De-dupes across slices: drops CANCEL events, keeps latest NEW/TRADE/CORRECT per id
- Keeps swaps with a USD leg; uses the USD leg notional as 'notional' (USD P&L friendly)
- Infers tenor_yrs from effectiveDate → maturityDate
- Tries to infer pay_fixed from leg rate types & pay/receive; falls back to True
- Writes CSV: trades/real_irs_usd_consolidated.csv
"""

import argparse
import re
from pathlib import Path
from typing import List, Optional

import numpy as np
import pandas as pd


# -------- helpers --------

def list_input_files(in_dir: Path) -> List[Path]:
    pats = ["RT.IRS.*.csv", "RT.IRS.*.csv.zip", "*.csv", "*.csv.zip"]
    files = []
    for p in pats:
        files += list(in_dir.glob(p))
    # keep IRS-looking files only
    return sorted({f for f in files if "IRS" in f.name.upper()})

def read_any_csv(path: Path) -> pd.DataFrame:
    try:
        df = pd.read_csv(path)
    except Exception:
        df = pd.read_csv(path, encoding="latin-1")
    df["__source_file"] = path.name
    return df

def find_col(df: pd.DataFrame, *candidates) -> Optional[str]:
    lower = {c.lower(): c for c in df.columns}
    for name in candidates:
        if not name:
            continue
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
    # e.g., RT.IRS.20250926.1900.csv -> 1900
    m = re.search(r"\.(\d{4})\.csv", fname)
    return int(m.group(1)) if m else 0

def to_dt_utc(s: pd.Series) -> pd.Series:
    return pd.to_datetime(s, errors="coerce", utc=True)

def prefer_usd_leg_amount(r) -> (float, str):
    """Pick the USD leg notional if reported; else the larger leg."""
    l1_amt = pd.to_numeric(r.get("leg1NotionalAmount"), errors="coerce")
    l2_amt = pd.to_numeric(r.get("leg2NotionalAmount"), errors="coerce")
    l1_ccy = str(r.get("leg1NotionalCurrency") or "").upper()
    l2_ccy = str(r.get("leg2NotionalCurrency") or "").upper()
    if l1_ccy == "USD" and pd.notna(l1_amt):
        return float(l1_amt), "USD"
    if l2_ccy == "USD" and pd.notna(l2_amt):
        return float(l2_amt), "USD"
    # fallback: pick larger leg if available
    candidates = []
    if pd.notna(l1_amt): candidates.append((float(l1_amt), l1_ccy or "USD"))
    if pd.notna(l2_amt): candidates.append((float(l2_amt), l2_ccy or "USD"))
    if candidates:
        amt, ccy = sorted(candidates, key=lambda x: x[0], reverse=True)[0]
        return amt, ccy
    return np.nan, "USD"

def infer_tenor_years(eff, mat) -> int:
    e = pd.to_datetime(eff, errors="coerce")
    m = pd.to_datetime(mat, errors="coerce")
    if pd.notna(e) and pd.notna(m):
        yrs = int(round((m - e).days / 365.25))
        return max(1, min(30, yrs))
    return 5  # sensible fallback

def parse_rate_type(val: str) -> str:
    v = (val or "").upper()
    if "FIX" in v: return "FIXED"
    if "FLOAT" in v or "FLT" in v: return "FLOAT"
    return ""

def parse_payrec(val: str) -> str:
    v = (val or "").upper()
    if v.startswith("P"): return "PAY"
    if v.startswith("R") or v.startswith("REC"): return "REC"
    return ""

def infer_pay_fixed(row) -> bool:
    """
    Heuristics:
      - If a leg has rateType FIXED and payReceive PAY -> pay_fixed=True
      - If the FIXED leg is REC -> False
      - Else if a 'payFixed' or similar exists, use it
      - Fallback: True
    """
    # leg-level hints
    l1_rate = parse_rate_type(row.get("leg1RateType") or row.get("leg1Type") or row.get("leg1FixedFloating") or "")
    l2_rate = parse_rate_type(row.get("leg2RateType") or row.get("leg2Type") or row.get("leg2FixedFloating") or "")
    l1_pr = parse_payrec(row.get("leg1PayReceive") or row.get("leg1PayRec") or row.get("leg1Direction") or "")
    l2_pr = parse_payrec(row.get("leg2PayReceive") or row.get("leg2PayRec") or row.get("leg2Direction") or "")

    if l1_rate == "FIXED" and l1_pr:
        return l1_pr == "PAY"
    if l2_rate == "FIXED" and l2_pr:
        return l2_pr == "PAY"

    # generic columns
    pf = str(row.get("payFixed") or row.get("payerFixed") or "").strip().lower()
    if pf in ("true", "t", "1", "yes", "y"): return True
    if pf in ("false", "f", "0", "no", "n"): return False

    # cannot tell — default True (ok for demo-scale IM/VM)
    return True


# -------- main transform --------

def consolidate_irs_usd(in_dir: Path, out_csv: Path, keep_events=("TRAD", "NEWT", "NEW", "CORR")) -> pd.DataFrame:
    files = list_input_files(in_dir)
    if not files:
        raise SystemExit(f"No IRS CSV/ZIP files found in {in_dir}")

    # read & stack
    frames = [read_any_csv(p) for p in files]
    raw = pd.concat(frames, ignore_index=True)

    # soft schema
    id_col = find_col(raw, "disseminationIdentifier", "transactionId", "transactionIdentifier", "uti", "usi", "executionId", "re:.*(uti|usi).*")
    ts_col = find_col(raw, "eventDateTime", "executionTimestamp", "executionTime", "reportedTimestamp", "submissionTime", "timestamp", "tradeDateTime")
    event_col = find_col(raw, "event", "eventType", "action", "msgType")

    # normalize
    raw["_slice_order"] = raw["__source_file"].apply(slice_order_from_name)
    raw["_ts"] = to_dt_utc(raw[ts_col]) if ts_col else pd.NaT
    raw["_event"] = raw[event_col].astype(str).str.upper() if event_col else ""
    raw["_asset"] = raw.get("assetClass", "").astype(str).str.upper()

    # Keep interest-rate only if tagged
    rate_mask = raw["_asset"].isin(["RATE", "RATES", "INTEREST RATE"])
    if rate_mask.sum() > 0:
        raw = raw[rate_mask].copy()

    # sort & drop CANCELs
    raw = raw.sort_values(by=["_ts", "_slice_order"], ascending=[True, True])
    non_cancel = raw[~raw["_event"].str.contains("CANC", na=False)].copy()

    # de-dup by id (or composite)
    if id_col:
        if keep_events:
            non_cancel = non_cancel[non_cancel["_event"].isin(set(keep_events)) | non_cancel["_event"].eq("")].copy()
        dedup = non_cancel.drop_duplicates(subset=[id_col], keep="last")
    else:
        keys = []
        for guess in ("effectiveDate","startDate","maturity","maturityDate","endDate","fixedRate",
                      "leg1RateType","leg2RateType","leg1NotionalAmount","leg2NotionalAmount"):
            c = find_col(non_cancel, guess)
            if c: keys.append(c)
        keys = keys or ["__source_file"]
        dedup = non_cancel.drop_duplicates(subset=keys, keep="last")

    # event filter
    if keep_events:
        dedup = dedup[dedup["_event"].isin(set(keep_events)) | dedup["_event"].eq("")].copy()

    # derive tenor & notional (USD)
    eff_col = find_col(dedup, "effectiveDate", "startDate")
    mat_col = find_col(dedup, "maturity", "maturityDate", "endDate")
    tenor_yrs = dedup.apply(lambda r: infer_tenor_years(r.get(eff_col), r.get(mat_col)), axis=1)

    # pick USD leg notional
    amt_ccy = dedup.apply(prefer_usd_leg_amount, axis=1, result_type="expand")
    amt_ccy.columns = ["__notional", "__ccy"]

    mask_usd = amt_ccy["__ccy"].astype(str).str.upper().eq("USD")
    mask_amt = pd.to_numeric(amt_ccy["__notional"], errors="coerce").fillna(0) > 0

    snap = dedup[mask_usd & mask_amt].copy()
    tenor_yrs = tenor_yrs.loc[snap.index]
    amt = pd.to_numeric(amt_ccy.loc[snap.index, "__notional"], errors="coerce").astype(float)

    # fixed rate (if reported)
    fixed_rate_col = find_col(snap, "fixedRate", "fixedCoupon", "rate")
    fixed_rate = pd.to_numeric(snap[fixed_rate_col], errors="coerce") if fixed_rate_col else pd.Series([np.nan]*len(snap))

    # pay_fixed inference
    pay_fixed_series = snap.apply(infer_pay_fixed, axis=1)

    # build simulator schema
    trades = pd.DataFrame({
        "trade_id": [f"IRST{i:06d}" for i in range(1, len(snap)+1)],
        "cpty": ["UNKNOWN"]*len(snap),
        "product": ["IRS"]*len(snap),
        "notional": amt.values,
        "ccy": ["USD"]*len(snap),
        "tenor_yrs": tenor_yrs.values,
        "fixed_rate": fixed_rate.fillna("").values,
        "pay_fixed": pay_fixed_series.values,
        "ccypair": ["" for _ in range(len(snap))],  # not used for IRS
        "side": ["" for _ in range(len(snap))]
    })

    out_csv.parent.mkdir(parents=True, exist_ok=True)
    trades.to_csv(out_csv, index=False)

    print(f"Files read: {len(files)}  |  Raw rows: {len(raw)}  |  Kept USD IRS: {len(trades)}")
    print(f"Wrote: {out_csv}")
    return trades


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in_dir", default="IRS", help="Folder containing CME SDR IRS CSVs/ZIPs")
    ap.add_argument("--out", default="trades/real_irs_usd_consolidated.csv", help="Output CSV for simulator")
    ap.add_argument("--keep_events", default="TRAD,NEWT,NEW,CORR", help="Comma list: TRAD, NEWT/NEW, CORR")
    args = ap.parse_args()

    in_dir = Path(args.in_dir)
    out_csv = Path(args.out)
    keep_events = tuple(x.strip().upper() for x in args.keep_events.split(",")) if args.keep_events else None

    consolidate_irs_usd(in_dir, out_csv, keep_events)


if __name__ == "__main__":
    main()
