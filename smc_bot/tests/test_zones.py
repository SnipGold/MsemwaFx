import unittest
from modules.zones import identify_key_zones


class DemandSupplyZoneTests(unittest.TestCase):
    def test_returns_nearby_support_and_resistance(self):
        candles = []
        for i in range(20):
            base = 1.1000 + (0.0002 if i % 2 else 0.0)
            candles.append({"open": base, "close": base, "high": base + 0.0010, "low": base - 0.0010})
        result = identify_key_zones(candles, price=1.1000)
        self.assertIn("demand", result)
        self.assertIn("supply", result)
        self.assertIsNotNone(result["support"])
        self.assertIsNotNone(result["resistance"])

    def test_insufficient_data_returns_empty_levels(self):
        result = identify_key_zones([{"high": 1.0, "low": 0.9, "close": 0.95}] * 3)
        self.assertEqual(result, {"demand": None, "supply": None, "support": None, "resistance": None})


if __name__ == "__main__":
    unittest.main()
