#property strict

double LastHigh(string symbol, ENUM_TIMEFRAMES tf)
{
   return iHigh(symbol, tf, 1);
}

double LastLow(string symbol, ENUM_TIMEFRAMES tf)
{
   return iLow(symbol, tf, 1);
}

string DetectCHOCH(string symbol)
{
   double current = iClose(symbol, PERIOD_M15, 0);
   double prevHigh = LastHigh(symbol, PERIOD_M15);
   double prevLow = LastLow(symbol, PERIOD_M15);

   if(current > prevHigh)
      return "Bullish CHoCH";

   if(current < prevLow)
      return "Bearish CHoCH";

   return "No CHoCH";
}
