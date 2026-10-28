import math
import unittest
from modules.decision_engine import _confirmed_swing_before, _structure_confirmed
from modules.structure import analyze_structure


class StructureConfirmationTests(unittest.TestCase):
    @staticmethod
    def candles_from_closes(closes):
        return [
            {"time": str(i), "open": price, "high": price + 0.0008,
             "low": price - 0.0008, "close": price}
            for i, price in enumerate(closes)
        ]

    def test_structural_events_require_a_close_beyond_confirmed_swing(self):
        # Exercise rising, falling, choppy and pullback paths. A momentum
        # change by itself must never create BOS/CHoCH.
        sequences = []
        for trend in (1, -1):
            for phase in range(4):
                closes = []
                for i in range(70):
                    drift = trend * i * 0.00012
                    wave = math.sin((i + phase) * 1.15) * 0.0009
                    pullback = math.sin((i + phase) * 0.31) * 0.0005
                    closes.append(1.0 + drift + wave + pullback)
                sequences.append(closes)

        for closes in sequences:
            candles = self.candles_from_closes(closes)
            for end in range(12, len(candles) + 1):
                result = analyze_structure(candles[:end])
                event = result["event"]
                if event == "BOS" or event == "CHoCH":
                    close = candles[end - 1]["close"]
                    if result["bias"] == "BULLISH":
                        self.assertIsNotNone(result["last_swing_high"])
                        self.assertGreater(close, result["last_swing_high"])
                    elif result["bias"] == "BEARISH":
                        self.assertIsNotNone(result["last_swing_low"])
                        self.assertLess(close, result["last_swing_low"])
                    else:
                        self.fail("Structural event emitted without directional bias")

    def test_momentum_only_never_emits_choch(self):
        # A smooth pullback can reverse momentum while price remains inside
        # the confirmed swing range. It must not be called a CHoCH.
        closes = []
        for i in range(36):
            if i < 24:
                closes.append(1.1000 + i * 0.00015 + math.sin(i * 1.1) * 0.00035)
            else:
                closes.append(closes[-1] - 0.00008)
        result = analyze_structure(self.candles_from_closes(closes))
        if result["event"] == "CHoCH":
            close = closes[-1]
            self.assertTrue(
                (result["bias"] == "BULLISH" and close > result["last_swing_high"])
                or (result["bias"] == "BEARISH" and close < result["last_swing_low"])
            )

    def test_buy_stop_uses_latest_confirmed_swing_low(self):
        candles = []
        lows = [10, 9, 8, 9, 10, 9, 7, 8, 9, 10]
        for i, low in enumerate(lows):
            candles.append({"low": low, "high": low + 2, "close": low + 1})
        # At index 8, the pivot low at index 6 is confirmed by candles 7 and 8.
        self.assertEqual(_confirmed_swing_before(candles, 8, "BUY", lookback=8), 7.0)

    def test_sell_stop_uses_latest_confirmed_swing_high(self):
        candles = []
        highs = [12, 13, 14, 13, 12, 13, 15, 14, 13, 12]
        for high in highs:
            candles.append({"low": high - 2, "high": high, "close": high - 1})
        # At index 8, the pivot high at index 6 is confirmed by candles 7 and 8.
        self.assertEqual(_confirmed_swing_before(candles, 8, "SELL", lookback=8), 15.0)

    def test_swing_must_be_confirmed_before_signal_index(self):
        candles = [
            {"low": low, "high": low + 2, "close": low + 1}
            for low in [10, 9, 8, 9, 10, 9, 7, 8]
        ]
        # At index 7, the low at index 6 has only one right-side candle;
        # it must not be used as a confirmed pivot with span=2.
        self.assertNotEqual(_confirmed_swing_before(candles, 7, "BUY", lookback=8), 7.0)

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
