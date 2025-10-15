import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
import datetime as dt
import matplotlib.pyplot as plt

# =====================================================
# PAGE CONFIG
# =====================================================
st.set_page_config(page_title="CCP Netting Dashboard", layout="wide")
st.title("💹 CCP Netting Simulation")
st.markdown(
    """
    Simulates mark-to-market (MTM), variation margin (VM), and initial margin (IM)
    under bilateral vs CCP netting using **real FX data (EURUSD, USDJPY, and more)**.
    """
)

# =====================================================
# HELPERS
# =====================================================
def daily_pnl_from_mtm(mtm_series: pd.Series) -> pd.Series:
    """Daily P&L from MTM path."""
    return mtm_series.diff().fillna(0.0)

def im_hs_var(pnl_series: pd.Series, cl: float = 0.99, horizon_days: int = 10) -> float:
    """Historical VaR (one-sided loss) scaled to √10."""
    losses = -pnl_series.dropna()
    if len(losses) < 10:
        return 0.0
    q = float(np.quantile(losses, cl))
    return q * np.sqrt(horizon_days)

def vm_outflows(pnl_series: pd.Series) -> pd.Series:
    """Daily VM outflows = max(-PnL, 0)."""
    return (-pnl_series).clip(lower=0.0)

# =====================================================
# STEP 1: Scenario controls
# =====================================================
st.sidebar.header("Scenario")
scenario = st.sidebar.radio("Select Scenario", ["Base", "Stress"], index=0)
stress_mult = st.sidebar.slider("Stress multiplier (vol ×)", 1.0, 2.0, 1.5, 0.1)

# =====================================================
# STEP 2: Sample trades
# =====================================================
np.random.seed(42)
trade_ids = [f"T{i+1}" for i in range(10)]
notionals = np.random.randint(1e6, 5e6, len(trade_ids))
pairs_universe = [
    "EURUSD=X", "USDJPY=X", "GBPUSD=X", "AUDUSD=X",
    "USDCAD=X", "NZDUSD=X", "USDCHF=X", "EURJPY=X",
    "GBPJPY=X", "EURGBP=X"
]
pairs = np.random.choice(pairs_universe, len(trade_ids))
entry_dates = [dt.date.today() - dt.timedelta(days=np.random.randint(300, 500)) for _ in trade_ids]

trades_df = pd.DataFrame({
    "trade_id": trade_ids,
    "pair": pairs,
    "notional": notionals,
    "entry_date": entry_dates
})
st.subheader("📘 Trade Book")
st.dataframe(trades_df)

# =====================================================
# STEP 3: Download FX data (real from Yahoo)
# =====================================================
start_date = min(entry_dates)
end_date = dt.date.today()
fx_data = {}

for pair in trades_df["pair"].unique():
    data = yf.download(pair, start=start_date, end=end_date, progress=False)
    if not data.empty:
        fx_data[pair] = data["Close"]
    else:
        st.warning(f"⚠️ No data for {pair}. Skipping.")

if not fx_data:
    st.error("❌ No FX data available.")
    st.stop()

fx_df = pd.concat(fx_data, axis=1)
fx_df.columns = fx_df.columns.get_level_values(-1)
fx_df.index = pd.to_datetime(fx_df.index)
st.subheader("📈 FX Rates")
st.line_chart(fx_df)

# =====================================================
# STEP 4: Compute MTM per trade
# =====================================================
mtm_records = []
for _, tr in trades_df.iterrows():
    pair, notional = tr["pair"], tr["notional"]
    if pair in fx_df.columns:
        fx_series = fx_df[pair]
        entry_price = fx_series.iloc[0]
        mtm = (fx_series - entry_price) * notional / entry_price
        mtm_records.append(pd.DataFrame({
            "date": fx_series.index,
            "trade_id": tr["trade_id"],
            "pair": pair,
            "mtm": mtm
        }))

mtm_df = pd.concat(mtm_records)
portfolio_mtm = mtm_df.groupby("date")["mtm"].sum()

# =====================================================
# STEP 5: Apply stress scenario
# =====================================================
if scenario == "Stress":
    mtm_df["mtm"] *= stress_mult
    portfolio_mtm = mtm_df.groupby("date")["mtm"].sum()

# =====================================================
# STEP 6: Derive daily PnL (preserve trade_id + date)
# =====================================================
pnl_records = []
for tid, grp in mtm_df.groupby("trade_id"):
    grp_sorted = grp.sort_values("date")
    pnl_series = daily_pnl_from_mtm(grp_sorted["mtm"])
    pnl_records.append(pd.DataFrame({
        "date": grp_sorted["date"],
        "trade_id": tid,
        "pnl": pnl_series
    }))

pnl_df = pd.concat(pnl_records, ignore_index=True)
port_pnl = pnl_df.groupby("date")["pnl"].sum().sort_index()

# =====================================================
# STEP 7: IM computation (99% HS-VaR × √10)
# =====================================================
im_bilateral = 0.0
for _, g in pnl_df.groupby("trade_id"):
    im_bilateral += im_hs_var(g.set_index("date")["pnl"], cl=0.99, horizon_days=10)
im_ccp = im_hs_var(port_pnl, cl=0.99, horizon_days=10)
im_reduction = 100 * (1 - im_ccp / im_bilateral) if im_bilateral > 0 else 0.0

# =====================================================
# STEP 8: VM & liquidity metrics
# =====================================================
vm_bilateral_daily = (
    pnl_df.groupby("date")["pnl"].apply(lambda s: vm_outflows(s).sum()).sort_index()
)
vm_ccp_daily = vm_outflows(port_pnl)
worst5_bilateral = float(vm_bilateral_daily.rolling(5).sum().max())
worst5_ccp = float(vm_ccp_daily.rolling(5).sum().max())

# =====================================================
# STEP 9: Charts
# =====================================================
st.subheader(f"📊 MTM Paths — {scenario}")
fig, ax = plt.subplots(figsize=(10, 4))
for tid, grp in mtm_df.groupby("trade_id"):
    ax.plot(grp["date"], grp["mtm"], alpha=0.5, label=tid)
ax.plot(portfolio_mtm.index, portfolio_mtm.values, color="black", lw=2, label="Portfolio MTM")
ax.set_xlabel("Date"); ax.set_ylabel("MTM ($)")
ax.set_title(f"Trade & Portfolio MTM ({scenario})")
ax.legend()
st.pyplot(fig)

# VM chart
st.subheader("Cumulative VM Outflows")
fig2, ax2 = plt.subplots(figsize=(10, 4))
vm_bilateral_daily.cumsum().plot(ax=ax2, label="Bilateral VM (cum)")
vm_ccp_daily.cumsum().plot(ax=ax2, label="CCP VM (cum)")
ax2.legend(); ax2.set_ylabel("USD"); ax2.set_xlabel("Date")
st.pyplot(fig2)

# =====================================================
# STEP 10: Summary metrics
# =====================================================
st.subheader(f"📈 Margin & Liquidity Metrics — {scenario}")
c1, c2, c3 = st.columns(3)
c1.metric("Bilateral IM (99% 10-day HS-VaR)", f"${im_bilateral:,.0f}")
c2.metric("CCP IM (99% 10-day HS-VaR)", f"${im_ccp:,.0f}")
c3.metric("IM Reduction (%)", f"{im_reduction:.2f}%")

st.markdown("### 🧮 Liquidity")
d1, d2 = st.columns(2)
d1.metric("Worst 5-day Liquidity (Bilateral)", f"${worst5_bilateral:,.0f}")
d2.metric("Worst 5-day Liquidity (CCP)", f"${worst5_ccp:,.0f}")

# =====================================================
# STEP 11: Downloads
# =====================================================
summary_df = pd.DataFrame({
    "Metric": [
        "Bilateral IM (99% 10d HS-VaR)",
        "CCP IM (99% 10d HS-VaR)",
        "IM Reduction (%)",
        "Worst 5d Liquidity Bilateral",
        "Worst 5d Liquidity CCP",
        "Scenario"
    ],
    "Value": [
        im_bilateral, im_ccp, im_reduction,
        worst5_bilateral, worst5_ccp, scenario
    ]
})
mtm_csv = mtm_df.to_csv(index=False).encode("utf-8")
pnl_csv = pnl_df.to_csv(index=False).encode("utf-8")
summary_csv = summary_df.to_csv(index=False).encode("utf-8")

st.subheader("⬇️ Export Results")
colA, colB, colC = st.columns(3)
colA.download_button("📄 Download MTM (CSV)", mtm_csv, "mtm_timeseries.csv", "text/csv")
colB.download_button("📄 Download PnL (CSV)", pnl_csv, "pnl_timeseries.csv", "text/csv")
colC.download_button("📊 Download Summary (CSV)", summary_csv, "im_summary.csv", "text/csv")

st.success("✅ Simulation complete")
