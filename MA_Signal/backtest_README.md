# MA Strategy Backtest — Version 2

Independent H1 historical test. This is separate from the SMC/ICT bot and never places trades.

Rules:
- Entry: closed H1 EMA 9/20 crossover, EMA 50/200 trend filter, and close on the EMA 50 trend side.
- Sideways filter: ADX(14) >= 20. This is an initial test threshold, not a proven optimum.
- Stop: latest confirmed swing high/low, using 3 candles on each side and a 50-bar search; swing must already be confirmed at signal time. Add/subtract a 0.10 x ATR(14) buffer.
- Entry at next H1 candle open.
- Session filter: entry candle must be in the overlap when London and New York are both between 08:00 and 17:00 local time. Uses Europe/London and America/New_York zones, handling their daylight-saving changes separately.
- Take profit: 2R from entry to the actual swing-based stop.
- Capital USD 1,000; planned risk 1% equity per trade; block new entries after 3% realized UTC-day loss.
- If SL and TP are both touched within one H1 candle, count SL first.

Outputs: Actions summary and artifacts summary.json, trades.csv, telegram_status.txt. Telegram report is attempted if bot token and chat ID secrets exist.

Limitations: requests up to 5,000 H1 candles per pair and refuses fewer than 1,000 closed candles. Gross results exclude actual spread, commission, swaps and slippage. Cost scenarios are assumptions, not measured HFM Cent costs. Daily lockout blocks new entries but does not force-close open positions. OHLC is not tick-level. Historical results do not promise future performance.
