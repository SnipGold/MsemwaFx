import unittest
from modules.decision_engine import _direction_candidates


class DirectionCandidateTests(unittest.TestCase):
    def test_aligned_bullish_bias_maps_to_buy(self):
        self.assertEqual(_direction_candidates("BULLISH", "BULLISH"), ["BUY"])

    def test_aligned_bearish_bias_maps_to_sell(self):
        self.assertEqual(_direction_candidates("BEARISH", "BEARISH"), ["SELL"])

    def test_mixed_bias_prefers_h1_direction_then_alternative(self):
        self.assertEqual(_direction_candidates("BULLISH", "BEARISH"), ["SELL", "BUY"])

    def test_neutral_bias_checks_both_trade_directions(self):
        self.assertEqual(_direction_candidates("NEUTRAL", "NEUTRAL"), ["BUY", "SELL"])


if __name__ == "__main__":
    unittest.main()
