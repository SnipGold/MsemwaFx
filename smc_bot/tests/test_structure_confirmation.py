import unittest
from modules.decision_engine import _structure_confirmed


class StructureConfirmationTests(unittest.TestCase):
    def test_bos_on_either_aligned_htf_is_accepted(self):
        self.assertTrue(_structure_confirmed({"event": "BOS"}, {"event": "NONE"}))
        self.assertTrue(_structure_confirmed({"event": "NONE"}, {"event": "BOS"}))

    def test_choch_on_either_aligned_htf_is_accepted(self):
        self.assertTrue(_structure_confirmed({"event": "CHoCH"}, {"event": "NONE"}))
        self.assertTrue(_structure_confirmed({"event": "NONE"}, {"event": "CHOCH"}))

    def test_no_structural_event_is_rejected(self):
        self.assertFalse(_structure_confirmed({"event": "NONE"}, {"event": "NONE"}))


if __name__ == "__main__":
    unittest.main()
