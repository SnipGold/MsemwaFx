//+------------------------------------------------------------------+
//| MsemwaFX_Core_EA.mq5                                              |
//| Engine 1 - Institutional Scanner                                 |
//| Version: 1.10                                                    |
//+------------------------------------------------------------------+
#property strict
#property version "1.10"

// Detectors
#include "MsemwaFX_Decision_Engine.mq5"
#include "MsemwaFX_BOS_Detector.mq5"
#include "MsemwaFX_CHOCH_Detector.mq5"
#include "MsemwaFX_OrderBlock_Detector.mq5"
#include "MsemwaFX_FVG_Detector.mq5"
#include "MsemwaFX_LiquiditySweep_Detector.mq5"

// Pairs
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
int OnInit()
{
   EventSetTimer(60);
   Print("MsemwaFX Engine 1 Started.");
   return(INIT_SUCCEEDED);
}

//---------------------------------------------------
void OnDeinit(const int reason)
{
   EventKillTimer();
}

//---------------------------------------------------
void OnTimer()
{
   for(int i=0;i<ArraySize(Symbols);i++)
      ScanPair(Symbols[i]);
}

//---------------------------------------------------
void ScanPair(string symbol)
{
   double h4=iClose(symbol,PERIOD_H4,0);
   double h1=iClose(symbol,PERIOD_H1,0);
   double m15=iClose(symbol,PERIOD_M15,0);

   bool bos=DetectBOS(symbol);
   bool choch=DetectCHOCH(symbol);
   bool ob=DetectOrderBlock(symbol);
   bool fvg=DetectFVG(symbol);
   bool ls=DetectLiquiditySweep(symbol);

   string signal="WAIT";

   if(bos && choch && ob && fvg && ls)
      signal="GO";

   Print(
      symbol,
      " | H4:",DoubleToString(h4,5),
      " | H1:",DoubleToString(h1,5),
      " | M15:",DoubleToString(m15,5),
      " | BOS:",bos,
      " | CHOCH:",choch,
      " | OB:",ob,
      " | FVG:",fvg,
      " | LS:",ls,
      " | SIGNAL:",signal
   );
}
