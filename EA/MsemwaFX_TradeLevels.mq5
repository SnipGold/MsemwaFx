//+------------------------------------------------------------------+
//| MsemwaFX_TradeLevels.mq5                                          |
//+------------------------------------------------------------------+
#property strict

struct TradeLevels
{
   double entry;
   double sl;
   double tp1;
   double tp2;
};

TradeLevels GetTradeLevels(string symbol,bool bullish)
{
   TradeLevels t;

   double high=iHigh(symbol,PERIOD_M15,1);
   double low=iLow(symbol,PERIOD_M15,1);
   double range=high-low;

   if(bullish)
   {
      t.entry=iClose(symbol,PERIOD_M15,0);
      t.sl=low;
      t.tp1=t.entry+range*2;
      t.tp2=t.entry+range*3;
   }
   else
   {
      t.entry=iClose(symbol,PERIOD_M15,0);
      t.sl=high;
      t.tp1=t.entry-range*2;
      t.tp2=t.entry-range*3;
   }

   return t;
}
