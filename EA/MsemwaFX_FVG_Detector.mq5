#property strict

struct FVGZone
{
   double upper;
   double lower;
   bool bullish;
   bool found;
};

FVGZone DetectFVG(string symbol)
{
   FVGZone fvg;
   fvg.found=false;

   for(int i=3;i<=30;i++)
   {
      double high1=iHigh(symbol,PERIOD_M15,i);
      double low1=iLow(symbol,PERIOD_M15,i);

      double high3=iHigh(symbol,PERIOD_M15,i-2);
      double low3=iLow(symbol,PERIOD_M15,i-2);

      // Bullish FVG
      if(high1<low3)
      {
         fvg.upper=low3;
         fvg.lower=high1;
         fvg.bullish=true;
         fvg.found=true;
         return fvg;
      }

      // Bearish FVG
      if(low1>high3)
      {
         fvg.upper=low1;
         fvg.lower=high3;
         fvg.bullish=false;
         fvg.found=true;
         return fvg;
      }
   }

   return fvg;
}
