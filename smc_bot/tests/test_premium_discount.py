import unittest

from modules.decision_engine import _dealing_range, _premium_discount


def bars(low, high, close, count=24):
    return [
        {"open": close, "high": high, "low": low, "close": close, "time": str(i)}
        for i in range(count)
    ]


class PremiumDiscountTests(unittest.TestCase):
    def test_dealing_range_uses_h4_not_recent_m15_range(self):
        h4 = bars(0.5560, 0.5900, 0.5680)
        result = _dealing_range(h4)
        self.assertAlmostEqual(result["low"], 0.5560)
        self.assertAlmostEqual(result["high"], 0.5900)
        self.assertAlmostEqual(result["equilibrium"], 0.5730)

    def test_price_below_h4_equilibrium_is_discount(self):
        h4 = bars(0.5560, 0.5900, 0.5680)
        location, _ = _premium_discount(0.5680, "BUY", h4)
        self.assertEqual(location, "DISCOUNT")

    def test_price_above_h4_equilibrium_is_premium(self):
        h4 = bars(1.3190, 1.3520, 1.3340)
        location, _ = _premium_discount(1.3400, "BUY", h4)
        self.assertEqual(location, "PREMIUM")

    def test_missing_range_is_safe(self):
        location, dealing = _premium_discount(1.0, "BUY", [])
        self.assertIsNone(location)
        self.assertIsNone(dealing)


if __name__ == "__main__":
    unittest.main()
