# MA Strategy Backtest

Independent H1 historical test. No trade execution and no changes to the SMC/ICT bot.

Rules: closed H1 candles; entry at next bar open; BUY when EMA9 crosses above EMA20, EMA50>EMA200 and close>EMA50; SELL inverse; SL=1.5x ATR(14); TP=2R; reference capital USD 1,000; 1% equity risk per entry; block new entries after realized UTC-day loss reaches 3%; count SL first if SL and TP are touched in one candle.

Outputs: Actions summary, results artifact (summary.json, trades.csv), Telegram report if bot token and chat ID secrets are configured.

Limitations: requests up to 5,000 H1 candles per pair and refuses fewer than 1,000 closed bars; gross results exclude spread, commission, swaps and slippage. The 1/1.5/2-pip cost scenarios are assumptions, not actual HFM Cent spreads. Daily loss lockout blocks new entries only; it does not force-close open positions. OHLC simulation is not tick-level. Historical results do not promise future performance.
