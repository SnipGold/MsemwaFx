//+------------------------------------------------------------------+
//| MsemwaFX_Core_EA.mq5                                              |
//| Engine 1 - Institutional Scanner                                 |
//| Version: 1.20                                                     |
//+------------------------------------------------------------------+
#property strict
#property version "1.20"

//========================= INCLUDES =========================
#include "MsemwaFX_Decision_Engine.mq5"
#include "MsemwaFX_BOS_Detector.mq5"
#include "MsemwaFX_CHOCH_Detector.mq5"
#include "MsemwaFX_OrderBlock_Detector.mq5"
#include "MsemwaFX_FVG_Detector.mq5"
#include "MsemwaFX_LiquiditySweep_Detector.mq5"
#include "MsemwaFX_Webhook.mq5"
#include "MsemwaFX_KillZone.mq5"

//=========================== PAIRS ==========================
string Symbols[]={
   "GBPUSD",
   "EURUSD",
   "USDJPY",
   "EURJPY",
   "AUDUSD",
   "USDCHF",
   "XAUUSD"
};

//============================ INIT ==========================
int OnInit()
{
   EventSetTimer(60);          // Scan every 60 seconds
   Print("MsemwaFX Engine 1 Started.");
   return(INIT_SUCCEEDED);
}

//=========================== DEINIT =========================
void OnDeinit(const int reason)
{
   EventKillTimer();
}

//============================ TIMER =========================
void OnTimer()
{
   for(int i=0;i<ArraySize(Symbols);i++)
      ScanPair(Symbols[i]);
}

//=========================== SCANNER ========================
void ScanPair(string symbol)
{
   // Timeframe prices
   double h4=iClose(symbol,PERIOD_H4,0);
   double h1=iClose(symbol,PERIOD_H1,0);
   double m15=iClose(symbol,PERIOD_M15,0);

   // Institutional Detectors
   string bos=DetectBOS(symbol);
   string choch=DetectCHoCH(symbol);
   OrderBlock ob=DetectOrderBlock(symbol);
   FVGZone fvg=DetectFVG(symbol);
   LiquiditySweep ls=DetectLiquiditySweep(symbol);

   // Decision Engine
 bool killZone=IsKillZone();     // Tutafanya automatic baadaye

   int score=CalculateScore(
      bos,
      choch,
      ob,
      fvg,
      ls,
      killZone
   );

   string signal=GetDecision(score);

   // Send only confirmed trade signals
   if(signal!="NO TRADE")
   {
      SendSignal(symbol,signal,score);
   }

   // Journal Output
   Print(
      symbol,
      " | H4=",DoubleToString(h4,_Digits),
      " | H1=",DoubleToString(h1,_Digits),
      " | M15=",DoubleToString(m15,_Digits),
      " | BOS=",bos,
      " | CHoCH=",choch,
      " | OB=",ob.bullish?"Bull":"Bear",
      " | FVG=",fvg.found?"Yes":"No",
      " | LS=",ls.found?"Yes":"No",
      " | Score=",score,
      " | Signal=",signal
   );
}
//+------------------------------------------------------------------+
