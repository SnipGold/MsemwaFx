import unittest
from modules.zones import _directional_key_levels


class ZoneDirectionTests(unittest.TestCase):
    def test_support_is_below_price_and_resistance_is_above(self):
        demand = [
            {"low": 175.50, "high": 176.00},
            {"low": 176.20, "high": 176.48},
        ]
        supply = [
            {"low": 176.42, "high": 176.80},
            {"low": 177.00, "high": 177.30},
        ]
        support, resistance = _directional_key_levels(demand, supply, 176.45)
        self.assertEqual(support, 176.00)
        self.assertEqual(resistance, 177.00)
        self.assertLess(support, 176.45)
        self.assertGreater(resistance, 176.45)

    def test_missing_level_is_none_not_a_reversed_level(self):
        support, resistance = _directional_key_levels(
            [{"low": 176.20, "high": 176.50}],
            [{"low": 175.70, "high": 176.10}],
            176.40,
        )
        self.assertIsNone(support)
        self.assertIsNone(resistance)


if __name__ == "__main__":
    unittest.main()
