def _swing_high(c,i):
    h=c[i]["high"]
    return h>c[i-1]["high"] and h>c[i-2]["high"] and h>c[i+1]["high"] and h>c[i+2]["high"]

def _swing_low(c,i):
    l=c[i]["low"]
    return l<c[i-1]["low"] and l<c[i-2]["low"] and l<c[i+1]["low"] and l<c[i+2]["low"]

def analyze_structure(candles):
    if len(candles)<10:return {"bias":"NEUTRAL","event":"NONE"}
    highs=[]; lows=[]
    for i in range(2,len(candles)-2):
        if _swing_high(candles,i):highs.append((i,candles[i]["high"]))
        if _swing_low(candles,i):lows.append((i,candles[i]["low"]))
    if len(highs)<2 or len(lows)<2:return {"bias":"NEUTRAL","event":"NONE"}
    h1,h2=highs[-2],highs[-1]; l1,l2=lows[-2],lows[-1]
    if h2[1]>h1[1] and l2[1]>l1[1]:bias="BULLISH"
    elif h2[1]<h1[1] and l2[1]<l1[1]:bias="BEARISH"
    else:bias="NEUTRAL"
    close=candles[-1]["close"]; event="NONE"
    if bias=="BULLISH":
        if close>h2[1]:event="BOS"
        elif close>h1[1]:event="CHoCH"
    elif bias=="BEARISH":
        if close<l2[1]:event="BOS"
        elif close<l1[1]:event="CHoCH"
    return {"bias":bias,"event":event,"last_swing_high":h2[1],"last_swing_low":l2[1]}
