//+------------------------------------------------------------------+
//|                                             MA_Crossover_EA.mq5  |
//| Separate MA strategy branch: ma-crossover-ea                      |
//+------------------------------------------------------------------+
#property strict
#property version "1.01"
#property description "EMA 9/20 crossover, EMA 50/200 trend filter, ATR SL and 2R TP."

#include <Trade/Trade.mqh>
CTrade trade;

input ENUM_TIMEFRAMES InpTimeframe = PERIOD_H1;
input int InpFastMA = 9;
input int InpSignalMA = 20;
input int InpTrendMA = 50;
input int InpMajorMA = 200;
input ENUM_MA_METHOD InpMAMethod = MODE_EMA;
input ENUM_APPLIED_PRICE InpPrice = PRICE_CLOSE;

input double InpRiskPercent = 1.0;       // $10 planned risk on $1,000 equity
input double InpMaxDailyLossPct = 3.0;   // $30 daily loss threshold on $1,000 baseline
input double InpRewardRisk = 2.0;
input int InpATRPeriod = 14;
input double InpATRMultiplier = 1.5;
input int InpMaxSpreadPoints = 30;

input bool InpAllowBuy = true;
input bool InpAllowSell = true;
input bool InpOnePosition = true;
input bool InpUseSession = false;
input int InpSessionStart = 7; // broker/server time
input int InpSessionEnd = 20;
input ulong InpMagic = 20261009;

int hFast = INVALID_HANDLE, hSignal = INVALID_HANDLE;
int hTrend = INVALID_HANDLE, hMajor = INVALID_HANDLE, hATR = INVALID_HANDLE;
datetime lastBarTime = 0;
double dayStartEquity = 0.0;
int dayOfYearStored = -1;

int OnInit()
{
   trade.SetExpertMagicNumber(InpMagic);
   trade.SetDeviationInPoints(20);
   hFast = iMA(_Symbol, InpTimeframe, InpFastMA, 0, InpMAMethod, InpPrice);
   hSignal = iMA(_Symbol, InpTimeframe, InpSignalMA, 0, InpMAMethod, InpPrice);
   hTrend = iMA(_Symbol, InpTimeframe, InpTrendMA, 0, InpMAMethod, InpPrice);
   hMajor = iMA(_Symbol, InpTimeframe, InpMajorMA, 0, InpMAMethod, InpPrice);
   hATR = iATR(_Symbol, InpTimeframe, InpATRPeriod);

   if(hFast == INVALID_HANDLE || hSignal == INVALID_HANDLE ||
      hTrend == INVALID_HANDLE || hMajor == INVALID_HANDLE || hATR == INVALID_HANDLE)
   {
      Print("MA_Crossover_EA: indicator initialization failed. Error=", GetLastError());
      return INIT_FAILED;
   }
   ResetDailyBaseline();
   Print("MA_Crossover_EA initialized on ", _Symbol, " timeframe ", EnumToString(InpTimeframe));
   return INIT_SUCCEEDED;
}

void OnDeinit(const int reason)
{
   if(hFast != INVALID_HANDLE) IndicatorRelease(hFast);
   if(hSignal != INVALID_HANDLE) IndicatorRelease(hSignal);
   if(hTrend != INVALID_HANDLE) IndicatorRelease(hTrend);
   if(hMajor != INVALID_HANDLE) IndicatorRelease(hMajor);
   if(hATR != INVALID_HANDLE) IndicatorRelease(hATR);
}

void OnTick()
{
   UpdateDailyBaseline();
   if(DailyLossLimitReached()) return;
   if(!IsNewBar() || !TradingSessionAllowed() || !SpreadAllowed()) return;
   if(InpOnePosition && HasOurOpenPosition()) return;

   MqlRates rates[];
   double fast[], signal[], trend[], major[], atr[];
   ArraySetAsSeries(rates, true);
   ArraySetAsSeries(fast, true);
   ArraySetAsSeries(signal, true);
   ArraySetAsSeries(trend, true);
   ArraySetAsSeries(major, true);
   ArraySetAsSeries(atr, true);

   if(CopyRates(_Symbol, InpTimeframe, 0, 3, rates) < 3) return;
   if(CopyBuffer(hFast, 0, 0, 3, fast) < 3) return;
   if(CopyBuffer(hSignal, 0, 0, 3, signal) < 3) return;
   if(CopyBuffer(hTrend, 0, 0, 3, trend) < 3) return;
   if(CopyBuffer(hMajor, 0, 0, 3, major) < 3) return;
   if(CopyBuffer(hATR, 0, 0, 3, atr) < 3) return;

   // Closed-candle entries only: bar 1 is last closed, bar 2 is prior.
   bool buySignal = fast[2] <= signal[2] && fast[1] > signal[1] &&
                    trend[1] > major[1] && rates[1].close > trend[1];
   bool sellSignal = fast[2] >= signal[2] && fast[1] < signal[1] &&
                     trend[1] < major[1] && rates[1].close < trend[1];

   if(buySignal && InpAllowBuy) OpenPosition(ORDER_TYPE_BUY, atr[1]);
   if(sellSignal && InpAllowSell) OpenPosition(ORDER_TYPE_SELL, atr[1]);
}

bool IsNewBar()
{
   datetime t = iTime(_Symbol, InpTimeframe, 0);
   if(t == 0 || t == lastBarTime) return false;
   lastBarTime = t;
   return true;
}

void OpenPosition(ENUM_ORDER_TYPE type, double atrValue)
{
   if(atrValue <= 0.0) return;
   double point = SymbolInfoDouble(_Symbol, SYMBOL_POINT);
   int digits = (int)SymbolInfoInteger(_Symbol, SYMBOL_DIGITS);
   double entry = (type == ORDER_TYPE_BUY) ? SymbolInfoDouble(_Symbol, SYMBOL_ASK)
                                           : SymbolInfoDouble(_Symbol, SYMBOL_BID);
   double slDistance = MathMax(atrValue * InpATRMultiplier,
      (double)SymbolInfoInteger(_Symbol, SYMBOL_TRADE_STOPS_LEVEL) * point);
   if(slDistance <= 0.0) return;

   double sl, tp;
   if(type == ORDER_TYPE_BUY)
   {
      sl = NormalizeDouble(entry - slDistance, digits);
      tp = NormalizeDouble(entry + slDistance * InpRewardRisk, digits);
   }
   else
   {
      sl = NormalizeDouble(entry + slDistance, digits);
      tp = NormalizeDouble(entry - slDistance * InpRewardRisk, digits);
   }

   double lots = CalculateRiskLot(entry, sl);
   if(lots <= 0.0)
   {
      Print("MA_Crossover_EA: calculated lot is below broker minimum or invalid.");
      return;
   }
   bool ok = (type == ORDER_TYPE_BUY)
      ? trade.Buy(lots, _Symbol, 0.0, sl, tp, "MA_Crossover_EA BUY")
      : trade.Sell(lots, _Symbol, 0.0, sl, tp, "MA_Crossover_EA SELL");

   if(!ok)
      Print("Order failed: ", trade.ResultRetcode(), " ", trade.ResultRetcodeDescription());
   else
      Print("Order opened: ", EnumToString(type), " lot=", DoubleToString(lots, 2),
            " SL=", DoubleToString(sl, digits), " TP=", DoubleToString(tp, digits));
}

double CalculateRiskLot(double entry, double sl)
{
   double riskMoney = AccountInfoDouble(ACCOUNT_EQUITY) * InpRiskPercent / 100.0;
   double tickSize = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_SIZE);
   double tickValue = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_VALUE);
   double minLot = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN);
   double maxLot = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MAX);
   double step = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_STEP);
   if(riskMoney <= 0 || tickSize <= 0 || tickValue <= 0 || step <= 0) return 0.0;

   double lossPerLot = MathAbs(entry - sl) / tickSize * tickValue;
   if(lossPerLot <= 0) return 0.0;
   double lots = MathMin(riskMoney / lossPerLot, maxLot);
   lots = MathFloor(lots / step) * step;
   if(lots < minLot) return 0.0;

   int volDigits = 0;
   double scaledStep = step;
   while(volDigits < 8 && MathAbs(scaledStep - MathRound(scaledStep)) > 1e-8)
   {
      scaledStep *= 10.0;
      volDigits++;
   }
   return NormalizeDouble(lots, volDigits);
}

bool HasOurOpenPosition()
{
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong ticket = PositionGetTicket(i);
      if(ticket == 0) continue;
      if(PositionGetString(POSITION_SYMBOL) == _Symbol &&
         (ulong)PositionGetInteger(POSITION_MAGIC) == InpMagic) return true;
   }
   return false;
}

bool SpreadAllowed()
{
   double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
   double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
   double point = SymbolInfoDouble(_Symbol, SYMBOL_POINT);
   if(point <= 0) return false;
   return ((ask - bid) / point) <= InpMaxSpreadPoints;
}

bool TradingSessionAllowed()
{
   if(!InpUseSession) return true;
   MqlDateTime dt;
   TimeToStruct(TimeCurrent(), dt);
   if(InpSessionStart == InpSessionEnd) return true;
   if(InpSessionStart < InpSessionEnd)
      return dt.hour >= InpSessionStart && dt.hour < InpSessionEnd;
   return dt.hour >= InpSessionStart || dt.hour < InpSessionEnd;
}

void ResetDailyBaseline()
{
   MqlDateTime dt;
   TimeToStruct(TimeCurrent(), dt);
   dayOfYearStored = dt.day_of_year;
   dayStartEquity = AccountInfoDouble(ACCOUNT_EQUITY);
}

void UpdateDailyBaseline()
{
   MqlDateTime dt;
   TimeToStruct(TimeCurrent(), dt);
   if(dayOfYearStored != dt.day_of_year) ResetDailyBaseline();
}

bool DailyLossLimitReached()
{
   if(dayStartEquity <= 0.0) return false;
   double equity = AccountInfoDouble(ACCOUNT_EQUITY);
   return ((dayStartEquity - equity) / dayStartEquity * 100.0) >= InpMaxDailyLossPct;
}
//+------------------------------------------------------------------+
