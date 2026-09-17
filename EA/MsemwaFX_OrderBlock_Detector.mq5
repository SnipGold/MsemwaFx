#property strict

struct OrderBlock
{
   double high;
   double low;
   int candle;
   bool bullish;
};

OrderBlock DetectOrderBlock(string symbol)
{
   OrderBlock ob;

   ob.high=0;
   ob.low=0;
   ob.candle=-1;
   ob.bullish=false;

   for(int i=2;i<=20;i++)
   {
      double open=iOpen(symbol,PERIOD_M15,i);
      double close=iClose(symbol,PERIOD_M15,i);

      // Bullish Order Block
      if(close<open)
      {
         ob.high=iHigh(symbol,PERIOD_M15,i);
         ob.low=iLow(symbol,PERIOD_M15,i);
         ob.candle=i;
         ob.bullish=true;
         break;
      }
   }

   return ob;
}
