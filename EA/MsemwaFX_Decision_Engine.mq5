#property strict

int CalculateScore(bool bos,bool choch,bool ob,bool fvg,bool ls,bool killZone)
{
   int score=0;

   if(bos) score+=20;
   if(choch) score+=20;
   if(ob) score+=20;
   if(fvg) score+=15;
   if(ls) score+=15;
   if(killZone) score+=10;

   return score;
}

string GetDecision(int score)
{
   if(score>=90) return "GO";
   if(score>=75) return "WAIT";
   return "NO TRADE";
}
