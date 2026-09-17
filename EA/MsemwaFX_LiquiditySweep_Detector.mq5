#property strict

// Returns TRUE if a valid Liquidity Sweep is found
bool DetectLiquiditySweep(string symbol)
{
   for(int i=2; i<=20; i++)
   {
      double high = iHigh(symbol, PERIOD_M15, i);
      double low = iLow(symbol, PERIOD_M15, i);

      double prevHigh = iHigh(symbol, PERIOD_M15, i+1);
      double prevLow = iLow(symbol, PERIOD_M15, i+1);

      double close = iClose(symbol, PERIOD_M15, i);

      // Bearish stop hunt
      if(high > prevHigh && close < prevHigh)
         return true;

      // Bullish stop hunt
      if(low < prevLow && close > prevLow)
         return true;
   }

   return false;
}
