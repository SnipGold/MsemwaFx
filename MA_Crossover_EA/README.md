# MA_Crossover_EA (separate test branch)

This is an independent EA project on branch `ma-crossover-ea`. It does not change the default `main` branch or the MsemwaFX SMC/ICT bot files.

## Initial rules
- H1 timeframe
- EMA 9/20 crossover trigger
- EMA 50/200 trend filter
- Stop loss = 1.5 × ATR(14)
- Take profit = 2R
- Risk = 1% of current equity per trade
- Daily loss lockout = 3% of the day's starting equity
- One EA position per symbol/magic number
- Spread filter, no martingale

For $1,000 equity, the nominal 1% risk is $10 and the 3% daily threshold is $30, subject to actual equity and broker symbol contract specifications.

## Important validation notes
- Source has dynamic arrays, avoiding the earlier fixed-array/ArraySetAsSeries warnings.
- This source has NOT been compiled by MetaEditor in this environment.
- Daily baseline is held in memory and resets on a new broker-server day; terminal restarts may reset the baseline.
- Test and inspect Strategy Tester results on demo before any live use.
- Key loss risks: spread/slippage, news spikes, and false/whipsaw MA crossovers.
