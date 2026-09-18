//+------------------------------------------------------------------+
//| MsemwaFX_Webhook.mq5                                              |
//| Sends GO signals to Railway                                       |
//+------------------------------------------------------------------+
#property strict

string WEBHOOK_URL="https://YOUR-RAILWAY-URL.up.railway.app/api/signal";

bool SendSignal(
   string symbol,
   string signal,
   int score
)
{
   string body=
      "{\"symbol\":\""+symbol+
      "\",\"signal\":\""+signal+
      "\",\"score\":"+IntegerToString(score)+"}";

   char data[];
   StringToCharArray(body,data);

   char result[];
   string headers="Content-Type: application/json\r\n";

   int timeout=5000;

   int res=WebRequest(
      "POST",
      WEBHOOK_URL,
      headers,
      timeout,
      data,
      result,
      headers
   );

   if(res==-1)
   {
      Print("Webhook failed: ",GetLastError());
      return false;
   }

   Print("Webhook sent: ",symbol);
   return true;
}
