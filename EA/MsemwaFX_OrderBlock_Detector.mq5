#property strict

struct OrderBlock
{
   double high;
   double low;
   int candle;
   bool bullish;
};

// Returns TRUE if a valid Order Block is found
bool DetectOrderBlock(string symbol)
{
   for(int i=2; i<=20; i++)
   {
      double open  = iOpen(symbol, PERIOD_M15, i);
      double close = iClose(symbol, PERIOD_M15, i);

      // Bullish Order Block
      if(close < open)
      {
         double nextClose = iClose(symbol, PERIOD_M15, i-1);

         if(nextClose > iHigh(symbol, PERIOD_M15, i))
            return true;
      }

      // Bearish Order Block
      if(close > open)
      {
         double nextClose = iClose(symbol, PERIOD_M15, i-1);

         if(nextClose < iLow(symbol, PERIOD_M15, i))
            return true;
      }
   }

   return false;
}
