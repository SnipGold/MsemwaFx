# Original vs Sweep Model Test Branch

**Branch:** `test/original-vs-sweep`  
**Purpose:** offline research only. The default/live workflow on `main` is unchanged.

## Models being compared

1. **ORIGINAL** — restores the pre-sweep-gated entry logic from the repository history: H4 and H1 bias must agree; a directional order block is required; FVG and liquidity sweep are context fields, not mandatory entry gates; target levels are 2R and 3R.
2. **SWEEP** — current `analyze_pair_diagnostic` decision engine: sweep-linked displacement-origin OB, aligned FVG, liquidity targets, premium/discount, HTF structure/reversal confirmation, and score gates.

## Test protocol

- Run both models over the **same replay candles**, symbols, and timestamps.
- Evaluate entry only after the signal candle; do not use future candles to construct a setup.
- Record each model's signals, rejected signals/reasons, entry touch, SL/TP outcome, R multiple, max drawdown, and signals per symbol/week.
- If SL and TP are touched inside the same M15 candle and tick order is unavailable, mark the result ambiguous rather than choosing the favorable outcome.
- Compare the ORIGINAL and SWEEP models separately before considering any combined scanner.

## Risk controls for any simulated trade

- Keep the structural stop loss; do not remove SL to increase signal count.
- Cap position size using account equity and stop distance; the current fixed 0.01 lot is not a substitute for risk-based sizing.
- Enforce a configurable maximum daily loss and stop taking new simulated trades after it is reached.
- Require at least 1:2 planned reward-to-risk for acceptance in the comparison harness; flag legacy setups that do not meet it rather than silently changing the historical model.

## Important limitations

The legacy model's original targets were synthetic 2R/3R levels, not measured external-liquidity targets. This branch preserves that distinction so the comparison is honest. The legacy module is for backtesting only and must not be wired into live alerts without separate review.
