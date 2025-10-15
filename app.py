import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
import datetime as dt
import matplotlib.pyplot as plt

# -----------------------------------------------
# PAGE CONFIG
# -----------------------------------------------
st.set_page_config(page_title="CCP Netting Dashboard", layout="wide")
st.title("💹 CCP Netting Simulation")
st.markdown("Simulating variation margin and initial margin impact using real FX data (EURUSD, USDJPY).")

# -----------------------------------------------
# STEP 1: Generate Sample Trade Data
# -----------------------------------------------
np.random.seed(42)

trade_ids = [f"T{i+1}" for i in range(10)]
notionals = np.random.randint(1e6, 5e6, len(trade_ids))
ccy_pairs = np.random.choice(["EURUSD=X", "USDJPY=X"], len(trade_ids))
entry_dates = [dt.date.today() - dt.timedelta(days=np.random.randint(300, 500)) for _ in trade_ids]

trades_df = pd.DataFrame({
    "trade_id": trade_ids,
    "pair": ccy_pairs,
    "notional": notionals,
    "entry_date": entry_dates
})

st.subheader("📘 Trade Book")
st.dataframe(trades_df)

# -----------------------------------------------
# STEP 2: Download FX Data from Yahoo Finance (Safe)
# -----------------------------------------------
start_date = min(entry_dates)
end_date = dt.date.today()
fx_data = {}

for pair in trades_df["pair"].unique():
    data = yf.download(pair, start=start_date, end=end_date, progress=False)
    if not data.empty:
        fx_data[pair] = data["Close"]
    else:
        st.warning(f"⚠️ No data found for {pair}. Skipping this pair.")

if not fx_data:
    st.error("❌ No FX data available. Please try again later.")
    st.stop()

# Combine FX rates into one DataFrame
fx_df = pd.concat(fx_data, axis=1)
fx_df.columns = fx_df.columns.get_level_values(-1)
fx_df.index = pd.to_datetime(fx_df.index)

st.subheader("📈 FX Rate Data")
st.line_chart(fx_df)

# -----------------------------------------------
# STEP 3: Compute Mark-to-Market (MTM)
# -----------------------------------------------
mtm_records = []

for _, trade in trades_df.iterrows():
    pair = trade["pair"]
    notional = trade["notional"]

    if pair in fx_df.columns:
        fx_series = fx_df[pair]
        entry_price = fx_series.iloc[0]  # first day’s price
        mtm = (fx_series - entry_price) * notional / entry_price
        mtm_records.append(pd.DataFrame({
            "date": fx_series.index,
            "trade_id": trade["trade_id"],
            "pair": pair,
            "mtm": mtm
        }))

mtm_df = pd.concat(mtm_records)

# Portfolio-level MTM
portfolio_mtm = mtm_df.groupby("date")["mtm"].sum()

# -----------------------------------------------
# STEP 4: Compute Initial Margin (IM)
# -----------------------------------------------
bilateral_im = mtm_df.groupby("trade_id")["mtm"].std().sum()
ccp_im = mtm_df.groupby("date")["mtm"].sum().std()
im_reduction = 100 * (1 - ccp_im / bilateral_im) if bilateral_im != 0 else 0

# -----------------------------------------------
# STEP 5: Display Charts
# -----------------------------------------------
st.subheader("📊 Variation Margin (MTM) Paths")

fig, ax = plt.subplots(figsize=(10, 4))
for trade_id, group in mtm_df.groupby("trade_id"):
    ax.plot(group["date"], group["mtm"], alpha=0.5, label=trade_id)
ax.plot(portfolio_mtm.index, portfolio_mtm.values, color="black", linewidth=2, label="Portfolio MTM")
ax.set_title("Trade and Portfolio MTM Paths")
ax.set_xlabel("Date")
ax.set_ylabel("MTM ($)")
ax.legend()
st.pyplot(fig)

# -----------------------------------------------
# STEP 6: Display Summary Metrics
# -----------------------------------------------
st.subheader("📊 Summary Metrics")
col1, col2, col3 = st.columns(3)

col1.metric("Bilateral IM", f"${bilateral_im:,.0f}")
col2.metric("CCP IM", f"${ccp_im:,.0f}")
col3.metric("IM Reduction (%)", f"{im_reduction:.2f}%")
