//+------------------------------------------------------------------+
//| MsemwaFX_Core_EA.mq5                                              |
//| Engine 1 - Institutional Scanner                                 |
//| Version: 1.0                                                     |
//+------------------------------------------------------------------+
#property strict
#property version "1.00"

string Symbols[]={
   "GBPUSD",
   "EURUSD",
   "USDJPY",
   "EURJPY",
   "AUDUSD",
   "USDCHF",
   "XAUUSD"
};

//---------------------------------------------------
// EA inaanza
int OnInit()
{
   EventSetTimer(60); // Scan every 60 seconds
   Print("MsemwaFX Engine 1 Started.");
   return(INIT_SUCCEEDED);
}

//---------------------------------------------------
// EA inafungwa
void OnDeinit(const int reason)
{
   EventKillTimer();
}

//---------------------------------------------------
// Timer
void OnTimer()
{
   for(int i=0;i<ArraySize(Symbols);i++)
   {
      ScanPair(Symbols[i]);
   }
}

//---------------------------------------------------
// Scanner
void ScanPair(string symbol)
{
   double h4=iClose(symbol,PERIOD_H4,0);
   double h1=iClose(symbol,PERIOD_H1,0);
   double m15=iClose(symbol,PERIOD_M15,0);

   Print(
      symbol,
      " | H4: ",DoubleToString(h4,_Digits),
      " | H1: ",DoubleToString(h1,_Digits),
      " | M15: ",DoubleToString(m15,_Digits)
   );
}
