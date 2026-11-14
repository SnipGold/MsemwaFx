MsemwaFX

Institutional Smart Money Concept (SMC/ICT) Forex Trading Engine.

Features

- BOS Detector
- CHoCH Detector
- Order Block Detector
- Fair Value Gap (FVG) Detector
- Liquidity Sweep Detector
- Kill Zone Filter
- Decision Engine (0–100 Score)
- Trade Levels (Entry, SL, TP1, TP2)
- Railway Webhook Integration

Version: 1.20

 
## Personal Android app

The `android/` directory contains the personal Android client. It reads the signal history from the single private API; it does not run another market scanner.

## Single-engine deployment

See [smc_bot/DEPLOYMENT.md](smc_bot/DEPLOYMENT.md) before switching production scanning from GitHub Actions to the persistent service. A persistent volume is required for the SQLite signal database.
