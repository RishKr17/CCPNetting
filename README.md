# Counterparty Risk Simulation and Netting Analysis

## Overview
This project models **counterparty exposure** and the impact of **netting** and **collateralization** across FX derivative trades.  
It simulates the mark-to-market (MtM) evolution of trades under both **bilateral** and **central counterparty (CCP)** frameworks, highlighting how netting reduces exposure and variation margin requirements.

The project combines **real FX trade data**, **interest rate curves**, and **FX rates** to compute margin requirements, cumulative variation margin, and exposure time series.



## Key Features
- Real FX Market Integration
Pulls daily FX close prices (EURUSD, USDJPY, GBPUSD, AUDUSD, USDCAD, NZDUSD, USDCHF, EURJPY, GBPJPY, EURGBP) via Yahoo Finance.

- Trade Simulation Engine
Generates random notional trades across multiple currency pairs, computes MTM and PnL from real price changes.

- IM & VM Modeling

Variation Margin (VM): Daily PnL outflows per trade and at portfolio level.

Initial Margin (IM): 99% one-sided 10-day Historical VaR (HS-VaR × √10).

Bilateral vs CCP: Compares IM under stand-alone vs. netted exposures.

Stress Scenario: Applies 1.5× volatility multiplier to simulate 2008-like market stress.

- Liquidity Metrics

Daily VM outflows

Worst 5-day liquidity at risk (rolling sum of outflows)

- Visualizations

Trade-level and portfolio MTM paths

Cumulative VM outflows (Bilateral vs CCP)

IM reduction and liquidity metrics

- Downloadable CSVs for MTM, PnL, and summary results



## Concepts Illustrated
 
- Counterparty Credit Risk
Measurement of exposure across OTC derivative portfolios.

- Netting Sets: Bilateral vs. CCP
How central clearing pools offsetting positions to reduce margin.

- Collateral & Margining
Dynamic computation of variation and initial margin requirements.

- Historical Simulation VaR (99%, 10-day)
Used to estimate IM under both netting frameworks.

- Stress Testing
Shock scenario (volatility scaling) to evaluate IM expansion and liquidity strain.

