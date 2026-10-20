import unittest
from modules.zones import analyze_zones


def candles_from_closes(rows):
    out = []
    for i, (o, h, l, c) in enumerate(rows):
        out.append({"time": str(i), "open": o, "high": h, "low": l, "close": c})
    return out


class ZoneTests(unittest.TestCase):
    def test_insufficient_history_returns_safe_empty_result(self):
        result = analyze_zones([{"open": 1, "high": 1.1, "low": .9, "close": 1}])
        self.assertEqual(result["demand"], [])
        self.assertEqual(result["supply"], [])
        self.assertIsNone(result["support"])
        self.assertIsNone(result["resistance"])

    def test_detects_demand_and_supply_and_key_levels(self):
        # Clear swing low around index 5 and swing high around index 10;
        # later candles stay within both distal edges, so neither is broken.
        rows = [
            (1.100,1.102,1.098,1.100),
            (1.100,1.101,1.097,1.099),
            (1.099,1.100,1.095,1.097),
            (1.097,1.099,1.092,1.096),
            (1.096,1.098,1.090,1.094),
            (1.094,1.097,1.080,1.092),
            (1.092,1.099,1.088,1.096),
            (1.096,1.104,1.094,1.101),
            (1.101,1.110,1.099,1.106),
            (1.106,1.120,1.104,1.112),
            (1.112,1.115,1.105,1.109),
            (1.109,1.111,1.100,1.104),
            (1.104,1.108,1.096,1.101),
            (1.101,1.106,1.094,1.099),
            (1.099,1.104,1.092,1.097),
            (1.097,1.103,1.091,1.098),
            (1.098,1.105,1.093,1.100),
            (1.100,1.106,1.094,1.101),
            (1.101,1.107,1.095,1.102),
            (1.102,1.108,1.096,1.103),
            (1.103,1.109,1.097,1.104),
            (1.104,1.110,1.098,1.105),
        ]
        result = analyze_zones(candles_from_closes(rows), pivot_span=2)
        self.assertGreater(len(result["demand"]), 0)
        self.assertGreater(len(result["supply"]), 0)
        self.assertIsNotNone(result["support"])
        self.assertIsNotNone(result["resistance"])
        for zone in result["demand"] + result["supply"]:
            self.assertLessEqual(zone["low"], zone["high"])
            self.assertGreaterEqual(zone["touches"], 0)
            self.assertEqual(zone["fresh"], zone["touches"] == 0)

    def test_zone_invalidated_by_close_through_far_edge(self):
        rows = []
        # 20 candles with a clear pivot low at index 8, then a later close below it.
        for i in range(20):
            base = 1.100 + (0.001 if i % 2 else 0)
            rows.append((base, base + .002, base - .002, base))
        rows[6] = (1.100, 1.102, 1.095, 1.099)
        rows[7] = (1.099, 1.101, 1.090, 1.095)
        rows[8] = (1.095, 1.100, 1.080, 1.092)
        rows[9] = (1.092, 1.100, 1.088, 1.096)
        rows[10] = (1.096, 1.102, 1.094, 1.100)
        rows[11] = (1.100, 1.102, 1.096, 1.101)
        rows[18] = (1.090, 1.092, 1.085, 1.087)
        rows[19] = (1.087, 1.090, 1.080, 1.082)
        result = analyze_zones(candles_from_closes(rows), pivot_span=2)
        self.assertTrue(all(z["low"] >= 1.082 for z in result["demand"]))


if __name__ == "__main__":
    unittest.main()
