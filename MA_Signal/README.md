# Independent MA Signals — Shared Candle Mode

Signal-generation only. This module is separate from the SMC/ICT decision rules and does not place trades or connect to MT5.

## Live scanner
- Eight FX pairs: EUR/USD, EUR/JPY, GBP/USD, AUD/USD, USD/CHF, USD/CAD, NZD/USD, USD/JPY.
- MA signals use completed H1 candles aggregated from the SMC scanner's cached M15 candles.
- The MA scanner makes **no Twelve Data requests**.
- EMA 9/20 crossover, EMA 50/200 trend filter; SL = 1.5 × ATR(14); TP = 2R.
- Reference capital USD 1,000; risk budget 1% ($10); daily loss threshold displayed as 3% ($30).
- The SMC workflow runs this scanner after its market-data scan. Duplicate alerts are tracked in `sent_signals.json`.
- Manual workflow dispatch is available, but requires a usable shared candle cache from a prior SMC scan.

## Cache and data requirements
- The SMC scanner requests 1,600 M15 candles per pair to provide enough complete H1 bars for EMA200 warm-up.
- Only complete H1 buckets built from four closed M15 candles are accepted.
- If the shared cache is missing or too short, the MA scanner fails closed and sends no signal rather than making a second API request.
- GitHub Actions cache restores are best-effort; check logs for `SHARED CACHE` and ensure cache restoration succeeded.

## Risks and limitations
- Signals are not trade instructions; no orders are placed.
- The MA rule can whipsaw in sideways markets; spreads/slippage and news spikes can materially change outcomes.
- The shared cache is a performance optimization, not a guaranteed durable market-data archive.
