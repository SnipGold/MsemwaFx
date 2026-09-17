//+------------------------------------------------------------------+
//| MsemwaFX_Decision_Engine.mq5                                     |
//| Institutional Scoring Engine                                     |
//+------------------------------------------------------------------+
#property strict

int CalculateScore(
   string bos,
   string choch,
   OrderBlock ob,
   FVGZone fvg,
   LiquiditySweep ls,
   bool killZone
)
{
   int score=0;

   // BOS
   if(bos=="Bullish BOS" || bos=="Bearish BOS")
      score+=25;

   // CHoCH
   if(choch=="Bullish CHoCH" || choch=="Bearish CHoCH")
      score+=20;

   // Order Block
   if(ob.candle!=-1)
      score+=20;

   // Fair Value Gap
   if(fvg.found)
      score+=15;

   // Liquidity Sweep
   if(ls.found)
      score+=10;

   // Kill Zone
   if(killZone)
      score+=10;

   return score;
}

//---------------------------------------------------

string GetDecision(int score)
{
   if(score>=80)
      return "GO";

   if(score>=55)
      return "WAIT";

   return "NO TRADE";
}
