import unittest

from modules.decision_engine import (
    _dealing_range,
    _premium_discount,
    _price_digits,
    _structure_confirmed,
)


def candle(i, high, low, close=None):
    close = (high + low) / 2 if close is None else close
    return {
        "time": str(i), "open": close, "high": high, "low": low, "close": close
    }


class DecisionLogicTests(unittest.TestCase):
    def test_dealing_range_uses_confirmed_pivots_not_latest_unconfirmed_extremes(self):
        candles = []
        # Stable background with confirmed swing lows at 3/5 and swing high at 9.
        # Keep the low at index 4 above 5: a value of 2 there is itself a
        # valid confirmed pivot under the two-candle rule and would make the
        # expected range low of 5 contradictory.
        lows = [8, 7, 6, 5, 6, 5, 6, 7, 8, 9, 7, 6, 5, 6, 7, 8, 7, 6, 5, 4]
        highs = [10, 9, 8, 7, 6, 8, 9, 10, 11, 15, 12, 10, 9, 8, 7, 6, 5, 4, 3, 30]
        for i, (lo, hi) in enumerate(zip(lows, highs)):
            candles.append(candle(i, hi, lo))
        result = _dealing_range(candles, lookback=20, pivot_span=2)
        self.assertIsNotNone(result)
        self.assertEqual(result["low"], 5.0)
        self.assertEqual(result["high"], 15.0)
        self.assertEqual(result["equilibrium"], 10.0)

    def test_no_confirmed_high_or_low_returns_no_range(self):
        candles = [candle(i, 10 + i, 5 + i) for i in range(20)]
        self.assertIsNone(_dealing_range(candles, lookback=20, pivot_span=2))

    def test_buy_and_sell_premium_discount_classification(self):
        h4 = [candle(i, 110, 90) for i in range(20)]
        self.assertEqual(_premium_discount(95, "BUY", h4)[0], "DISCOUNT")
        self.assertEqual(_premium_discount(105, "SELL", h4)[0], "PREMIUM")

    def test_buy_at_equilibrium_is_not_a_discount_entry(self):
        h4 = [candle(i, 110, 90) for i in range(20)]
        location, _ = _premium_discount(100, "BUY", h4)
        self.assertEqual(location, "EQUILIBRIUM")

    def test_sell_at_equilibrium_is_not_a_premium_entry(self):
        h4 = [candle(i, 110, 90) for i in range(20)]
        location, _ = _premium_discount(100, "SELL", h4)
        self.assertEqual(location, "EQUILIBRIUM")

    def test_jpy_pairs_keep_three_decimal_precision(self):
        self.assertEqual(_price_digits("EUR/JPY"), 3)
        self.assertEqual(_price_digits("USD/JPY"), 3)
        self.assertEqual(_price_digits("GBP/USD"), 5)

    def test_structure_confirmation_requires_a_real_event(self):
        self.assertTrue(_structure_confirmed({"event": "BOS"}, {"event": "NONE"}))
        self.assertTrue(_structure_confirmed({"event": "NONE"}, {"event": "CHoCH"}))
        self.assertFalse(_structure_confirmed({"event": "NONE"}, {"event": "NONE"}))


if __name__ == "__main__":
    unittest.main()
