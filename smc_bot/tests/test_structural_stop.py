import unittest
from modules.decision_engine import _confirmed_swing_reference


def candles(highs, lows):
    return [
        {"time": str(i), "open": 100.0, "high": h, "low": l, "close": 100.0}
        for i, (h, l) in enumerate(zip(highs, lows))
    ]


class StructuralStopTests(unittest.TestCase):
    def test_buy_uses_latest_confirmed_swing_low_not_only_recent_six_bars(self):
        highs = [103.0] * 25
        lows = [101.0] * 25
        for i, value in zip((3, 8, 13, 18), (108, 107, 106, 105)):
            highs[i], lows[i] = value, value - 2
        for i, value in zip((5, 10, 15, 20), (98, 97, 96, 94)):
            highs[i], lows[i] = value + 2, value
        reference, basis, swing = _confirmed_swing_reference(
            candles(highs, lows), 24, "BUY", 100.0, 99.5, 100.5
        )
        self.assertEqual(reference, 94.0)
        self.assertEqual(swing, 94.0)
        self.assertEqual(basis, "CONFIRMED_SWING_LOW@20")

    def test_sell_uses_latest_confirmed_swing_high(self):
        highs = [103.0] * 25
        lows = [101.0] * 25
        for i, value in zip((3, 8, 13, 18), (108, 109, 110, 112)):
            highs[i], lows[i] = value, value - 2
        for i, value in zip((5, 10, 15, 20), (98, 99, 100, 101)):
            highs[i], lows[i] = value + 2, value
        reference, basis, swing = _confirmed_swing_reference(
            candles(highs, lows), 24, "SELL", 105.0, 104.5, 105.5
        )
        self.assertEqual(reference, 112.0)
        self.assertEqual(swing, 112.0)
        self.assertEqual(basis, "CONFIRMED_SWING_HIGH@18")


if __name__ == "__main__":
    unittest.main()
