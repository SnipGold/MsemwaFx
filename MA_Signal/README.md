# Independent MA Signals — Option A

Signal-generation only. This module is separate from the SMC/ICT bot and does not place trades or connect to MT5.

Rules:
- Eight FX pairs: EUR/USD, EUR/JPY, GBP/USD, AUD/USD, USD/CHF, USD/CAD, NZD/USD, USD/JPY.
- H1 closed candles only; newest potentially incomplete candle is excluded.
- BUY: EMA 9 crosses above EMA 20, EMA 50 > EMA 200, and close > EMA 50.
- SELL: EMA 9 crosses below EMA 20, EMA 50 < EMA 200, and close < EMA 50.
- SL = 1.5 × ATR(14); TP = 2R.
- Reference capital $1,000; risk budget 1% ($10); daily loss threshold 3% ($30).
- This is a signal, not a trade instruction. It does not calculate broker-specific lot size or execute orders.

Required GitHub Actions repository secrets:
- TWELVEDATA_API_KEY
- TELEGRAM_BOT_TOKEN
- TELEGRAM_CHAT_ID

Workflow: hourly UTC plus manual run. Eight Twelve Data requests are spaced by 9 seconds. Check actual API quotas. Live API and Telegram delivery have not been verified from this setup. Main risks if traded: whipsaw crossovers, spread/slippage, and news spikes.
