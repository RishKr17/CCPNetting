# Counterparty Risk Simulation and Netting Analysis

## Overview
This project models **counterparty exposure** and the impact of **netting** and **collateralization** across FX derivative trades.  
It simulates the mark-to-market (MtM) evolution of trades under both **bilateral** and **central counterparty (CCP)** frameworks, highlighting how netting reduces exposure and variation margin requirements.

The project combines **real FX trade data**, **interest rate curves**, and **FX rates** to compute margin requirements, cumulative variation margin, and exposure time series.



## Key Features
- Consolidation of real FX trade CSVs into unified datasets  
- Filtering and normalization of USD-based pairs (e.g., EURUSD, USDJPY, and more)  
- Integration of interest rate and FX market data  
- Simulation of trade mark-to-market evolution and margin paths  
- Comparison between **bilateral** and **CCP netting** exposures  
- Generation of output graphs showing P&L, variation margin (VM), and initial margin (IM) over time



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

