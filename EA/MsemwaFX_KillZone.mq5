//+------------------------------------------------------------------+
//| MsemwaFX_KillZone.mq5                                             |
//| Automatic London & New York Kill Zone                            |
//+------------------------------------------------------------------+
#property strict

bool IsKillZone()
{
   MqlDateTime t;
   TimeToStruct(TimeCurrent(), t);

   int hour=t.hour;

   // London Kill Zone: 08:00-11:59 UTC
   bool london=(hour>=8 && hour<12);

   // New York Kill Zone: 13:00-16:59 UTC
   bool newYork=(hour>=13 && hour<17);

   return(london || newYork);
}
