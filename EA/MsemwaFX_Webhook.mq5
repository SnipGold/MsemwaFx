//+------------------------------------------------------------------+
//| MsemwaFX_Webhook.mq5                                              |
//| Sends Institutional Signals to Railway                           |
//| Version: 1.60                                                    |
//+------------------------------------------------------------------+
#property strict

// Railway Webhook URL
string WEBHOOK_URL="https://msemwa-ai-school-production.up.railway.app/api/signal";

//---------------------------------------------------
void SendSignal(
   string symbol,
   string signal,
   int score,
   TradeLevels trade
)
{
   string body=
      "{"
      "\"symbol\":\""+symbol+"\","
      "\"signal\":\""+signal+"\","
      "\"score\":"+IntegerToString(score)+","
      "\"entry\":"+DoubleToString(trade.entry,_Digits)+","
      "\"sl\":"+DoubleToString(trade.sl,_Digits)+","
      "\"tp1\":"+DoubleToString(trade.tp1,_Digits)+","
      "\"tp2\":"+DoubleToString(trade.tp2,_Digits)+
      "}";

   char data[];
   StringToCharArray(body,data);

   char result[];
   string responseHeaders;
   string headers="Content-Type: application/json\r\n";

   int status=WebRequest(
      "POST",
      WEBHOOK_URL,
      headers,
      5000,
      data,
      result,
      responseHeaders
   );

   if(status==-1)
   {
      Print("Webhook Error: ",GetLastError());
   }
   else
   {
      Print("Signal sent successfully. HTTP Status: ",status);
   }
}
//+------------------------------------------------------------------+
