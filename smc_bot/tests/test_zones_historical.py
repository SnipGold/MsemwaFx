import csv
import unittest
from pathlib import Path

from modules.zones import analyze_zones


ROOT = Path(__file__).resolve().parents[2]
HISTORICAL_FILES = (
    ROOT / "replay_data" / "EURUSD_15min.csv",
    ROOT / "replay_data" / "EURJPY_15min.csv",
    ROOT / "replay_data" / "GBPUSD_15min.csv",
)


def load_bars(path):
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter=";")
        return [
            {
                "open": float(row["open"]),
                "high": float(row["high"]),
                "low": float(row["low"]),
                "close": float(row["close"]),
            }
            for row in reader
        ]


class HistoricalZoneSmokeTests(unittest.TestCase):
    def test_zone_engine_handles_committed_historical_m15_data(self):
        checked = 0
        for path in HISTORICAL_FILES:
            if not path.exists():
                continue
            bars = load_bars(path)
            self.assertGreaterEqual(len(bars), 100, f"Insufficient historical bars in {path.name}")
            result = analyze_zones(bars)
            self.assertGreaterEqual(len(result["demand"]), 0)
            self.assertGreaterEqual(len(result["supply"]), 0)
            for zone in result["demand"] + result["supply"]:
                self.assertLessEqual(zone["low"], zone["high"])
                self.assertGreaterEqual(zone["age_candles"], 0)
                self.assertGreaterEqual(zone["touches"], 0)
            checked += 1
        self.assertGreater(checked, 0, "No committed historical M15 datasets were found")


if __name__ == "__main__":
    unittest.main()
