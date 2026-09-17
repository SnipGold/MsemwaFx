#property strict

struct LiquiditySweep
{
   bool found;
   bool bullish;
   double level;
   int candle;
};

LiquiditySweep DetectLiquiditySweep(string symbol)
{
   LiquiditySweep ls;
   ls.found=false;
   ls.bullish=false;
   ls.level=0;
   ls.candle=-1;

   for(int i=2;i<=20;i++)
   {
      double high=iHigh(symbol,PERIOD_M15,i);
      double low=iLow(symbol,PERIOD_M15,i);

      double prevHigh=iHigh(symbol,PERIOD_M15,i+1);
      double prevLow=iLow(symbol,PERIOD_M15,i+1);

      double close=iClose(symbol,PERIOD_M15,i);

      // Bearish stop hunt (sweeps highs then closes below)
      if(high>prevHigh && close<prevHigh)
      {
         ls.found=true;
         ls.bullish=false;
         ls.level=high;
         ls.candle=i;
         return ls;
      }

      // Bullish stop hunt (sweeps lows then closes above)
      if(low<prevLow && close>prevLow)
      {
         ls.found=true;
         ls.bullish=true;
         ls.level=low;
         ls.candle=i;
         return ls;
      }
   }

   return ls;
}
