import unittest
from modules.structure import analyze_structure


def trend_candles(highs, lows, final_close):
    rows = []
    for i in range(25):
        rows.append({"time": str(i), "open": 102.0, "high": 103.0, "low": 101.0, "close": 102.0})
    for i, value in zip((3, 8, 13, 18), highs):
        rows[i] = {"time": str(i), "open": value - 1, "high": value, "low": value - 2, "close": value - 1}
    for i, value in zip((5, 10, 15, 20), lows):
        rows[i] = {"time": str(i), "open": value + 1, "high": value + 2, "low": value, "close": value + 1}
    rows[-1]["close"] = final_close
    rows[-1]["open"] = final_close - 0.2
    rows[-1]["high"] = max(rows[-1]["high"], final_close + 0.2)
    rows[-1]["low"] = min(rows[-1]["low"], final_close - 0.2)
    return rows


class StructureBiasTests(unittest.TestCase):
    def test_bearish_structure_stays_bearish_during_bullish_recovery(self):
        candles = trend_candles([110, 108, 106, 104], [100, 98, 96, 94], 103.0)
        result = analyze_structure(candles)
        self.assertEqual(result["trend_structure"], "BEARISH")
        self.assertEqual(result["bias"], "BEARISH")
        self.assertEqual(result["phase"], "PULLBACK")

    def test_first_break_against_bearish_structure_is_transition_not_bullish_trend(self):
        candles = trend_candles([110, 108, 106, 104], [100, 98, 96, 94], 105.0)
        result = analyze_structure(candles)
        self.assertEqual(result["bias"], "NEUTRAL")
        self.assertEqual(result["event"], "CHoCH_BULLISH")
        self.assertEqual(result["phase"], "BULLISH_REVERSAL_PENDING")

    def test_bullish_structure_survives_a_normal_pullback(self):
        candles = trend_candles([104, 106, 108, 110], [90, 92, 94, 96], 109.0)
        result = analyze_structure(candles)
        self.assertEqual(result["trend_structure"], "BULLISH")
        self.assertEqual(result["bias"], "BULLISH")
        self.assertEqual(result["phase"], "PULLBACK")


if __name__ == "__main__":
    unittest.main()
