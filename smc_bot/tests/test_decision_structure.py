import unittest

from modules.decision_engine import _direction_candidates, _structure_confirmed


class DecisionStructureGateTests(unittest.TestCase):
    def test_structure_event_required(self):
        self.assertFalse(_structure_confirmed(
            {"bias": "BULLISH", "event": "NONE"},
            {"bias": "BULLISH", "event": "NONE"},
        ))

    def test_bos_on_either_aligned_timeframe_is_accepted(self):
        self.assertTrue(_structure_confirmed(
            {"bias": "BULLISH", "event": "BOS"},
            {"bias": "BULLISH", "event": "NONE"},
        ))
        self.assertTrue(_structure_confirmed(
            {"bias": "BULLISH", "event": "NONE"},
            {"bias": "BULLISH", "event": "BOS"},
        ))

    def test_choch_on_either_aligned_timeframe_is_accepted(self):
        self.assertTrue(_structure_confirmed(
            {"bias": "BEARISH", "event": "CHoCH"},
            {"bias": "BEARISH", "event": "NONE"},
        ))
        self.assertTrue(_structure_confirmed(
            {"bias": "BEARISH", "event": "NONE"},
            {"bias": "BEARISH", "event": "CHOCH"},
        ))

    def test_no_event_is_not_promoted_by_bias_alone(self):
        self.assertFalse(_structure_confirmed(
            {"bias": "BEARISH", "event": "NONE"},
            {"bias": "BEARISH", "event": "NONE"},
        ))

    def test_misaligned_bias_candidates_still_get_rejected_by_htf_gate(self):
        self.assertEqual(
            _direction_candidates("BULLISH", "BEARISH"),
            ["BEARISH", "BULLISH"],
        )


if __name__ == "__main__":
    unittest.main()
