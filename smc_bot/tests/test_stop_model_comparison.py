import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.compare_stop_models import atr, baseline_stop, evaluate_stop, max_drawdown_r, realized_r, summarize


class StopModelComparisonTests(unittest.TestCase):
    def test_atr_uses_only_available_prior_close_data(self):
        candles = [
            {"open": 10, "high": 12, "low": 9, "close": 11},
            {"open": 11, "high": 13, "low": 10, "close": 12},
            {"open": 12, "high": 14, "low": 11, "close": 13},
        ]
        self.assertGreater(atr(candles, 2), 0)

    def test_baseline_stop_is_beyond_entry(self):
        candles = [
            {"time": None, "open": 10, "high": 11, "low": 9, "close": 10},
            {"time": None, "open": 10, "high": 12, "low": 9.5, "close": 11},
            {"time": None, "open": 11, "high": 13, "low": 10, "close": 12},
        ]
        self.assertLess(baseline_stop(candles, 2, "BUY", 12.5, 0.1), 12.5)
        self.assertGreater(baseline_stop(candles, 2, "SELL", 8.5, 0.1), 8.5)

    def test_same_bar_stop_and_target_is_ambiguous(self):
        candles = [{"low": 8.0, "high": 12.0}]
        outcome, _ = evaluate_stop(candles, 0, "BUY", 10, 9, 11, 12)
        self.assertEqual(outcome, "SAME_CANDLE_SL_TP_AMBIGUOUS")

    def test_realized_r_uses_half_at_tp1_half_at_tp2_and_cost(self):
        # 1R risk; TP1=2R, TP2=3R => gross 2.5R; spread cost is 0.1R.
        value = realized_r("TP2", 1.0, 10, 12, 13, "BUY", 1.0, 0.1)
        self.assertAlmostEqual(value, 2.4)

    def test_drawdown_is_peak_to_trough(self):
        self.assertEqual(max_drawdown_r([1.0, -0.5, -1.0, 0.5]), -1.5)

    def test_summary_keeps_unresolved_separate(self):
        result = summarize([{"net_r": 1.0}, {"net_r": -1.0}, {"net_r": None}])
        self.assertEqual(result["closed_trades"], 2)
        self.assertEqual(result["open_or_unresolved"], 1)
        self.assertEqual(result["net_r"], 0.0)


if __name__ == "__main__":
    unittest.main()
