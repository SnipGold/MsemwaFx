#property strict

double GetSwingHigh(string symbol, ENUM_TIMEFRAMES tf, int lookback=20)
{
   double high=iHigh(symbol,tf,1);

   for(int i=2;i<=lookback;i++)
   {
      if(iHigh(symbol,tf,i)>high)
         high=iHigh(symbol,tf,i);
   }

   return high;
}

double GetSwingLow(string symbol, ENUM_TIMEFRAMES tf, int lookback=20)
{
   double low=iLow(symbol,tf,1);

   for(int i=2;i<=lookback;i++)
   {
      if(iLow(symbol,tf,i)<low)
         low=iLow(symbol,tf,i);
   }

   return low;
}

string DetectBOS(string symbol)
{
   double swingHigh=GetSwingHigh(symbol,PERIOD_H1);
   double swingLow=GetSwingLow(symbol,PERIOD_H1);
   double current=iClose(symbol,PERIOD_H1,0);

   if(current>swingHigh)
      return "Bullish BOS";

   if(current<swingLow)
      return "Bearish BOS";

   return "No BOS";
}
