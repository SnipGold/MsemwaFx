import unittest

from modules.orderblock import detect_order_block


class OrderBlockWithoutSweepTests(unittest.TestCase):
    def _candles(self, bias):
        candles = []
        # Baseline candles have no sweep/reclaim pattern.
        for i in range(12):
            candles.append({
                "time": f"2026-01-01T00:{i:02d}:00Z",
                "open": 100.0,
                "high": 101.0,
                "low": 99.0,
                "close": 100.2,
            })
        if bias == "BULLISH":
            candles[8].update({"open": 100.5, "high": 101.0, "low": 98.8, "close": 99.2})
            candles[10].update({"open": 100.0, "high": 102.0, "low": 99.8, "close": 101.5})
        else:
            candles[8].update({"open": 99.5, "high": 101.2, "low": 99.0, "close": 100.8})
            candles[10].update({"open": 100.0, "high": 100.2, "low": 98.0, "close": 98.5})
        return candles

    def test_bullish_ob_does_not_require_sweep(self):
        result = detect_order_block(self._candles("BULLISH"), "BULLISH")
        self.assertIsNotNone(result)
        self.assertEqual(result["type"], "BULLISH_OB")
        self.assertIsNone(result["sweep"])

    def test_bearish_ob_does_not_require_sweep(self):
        result = detect_order_block(self._candles("BEARISH"), "BEARISH")
        self.assertIsNotNone(result)
        self.assertEqual(result["type"], "BEARISH_OB")
        self.assertIsNone(result["sweep"])


if __name__ == "__main__":
    unittest.main()
