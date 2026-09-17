#property strict

// Returns TRUE if a valid Fair Value Gap is found
bool DetectFVG(string symbol)
{
   for(int i=3; i<=30; i++)
   {
      double high1 = iHigh(symbol, PERIOD_M15, i);
      double low1  = iLow(symbol, PERIOD_M15, i);

      double high3 = iHigh(symbol, PERIOD_M15, i-2);
      double low3  = iLow(symbol, PERIOD_M15, i-2);

      // Bullish FVG
      if(high1 < low3)
         return true;

      // Bearish FVG
      if(low1 > high3)
         return true;
   }

   return false;
}
