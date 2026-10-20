import unittest

from main import evaluate_entry_path


def candle(low, high, close=100.0):
    return {"low": low, "high": high, "open": close, "close": close}


class EntryPathReplayTests(unittest.TestCase):
    def setup_data(self, direction="BUY"):
        return {
            "signal_index": 0,
            "direction": direction,
            "entry": 100.0,
            "sl": 95.0 if direction == "BUY" else 105.0,
            "tp1": 110.0 if direction == "BUY" else 90.0,
        }

    def test_old_entry_touch_followed_by_stop_is_not_current_trigger(self):
        setup = self.setup_data("BUY")
        m15 = [
            candle(98, 99),       # signal candle
            candle(99, 101),      # entry touched
            candle(94, 100),      # later SL
        ]
        status, _ = evaluate_entry_path(setup, m15)
        self.assertEqual(status, "STOPPED OUT")

    def test_tp1_before_entry_means_entry_missed(self):
        setup = self.setup_data("BUY")
        m15 = [
            candle(98, 99),
            candle(101, 111),     # TP1 reached, entry not touched
        ]
        status, _ = evaluate_entry_path(setup, m15)
        self.assertEqual(status, "ENTRY MISSED")

    def test_entry_touch_without_later_exit_is_triggered(self):
        setup = self.setup_data("BUY")
        m15 = [
            candle(98, 99),
            candle(99, 101),
            candle(100, 104),
        ]
        status, _ = evaluate_entry_path(setup, m15)
        self.assertEqual(status, "ENTRY TRIGGERED")

    def test_entry_and_sl_same_candle_is_ambiguous(self):
        setup = self.setup_data("BUY")
        m15 = [candle(98, 99), candle(94, 101)]
        status, _ = evaluate_entry_path(setup, m15)
        self.assertEqual(status, "AMBIGUOUS")


if __name__ == "__main__":
    unittest.main()
