import json
import os
import tempfile
import unittest
from unittest.mock import patch

import database


class DatabaseTests(unittest.TestCase):
    def test_signal_upsert_and_read(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "signals.sqlite3")
            with patch.object(database, "DB_PATH", path):
                setup = {
                    "direction": "BUY",
                    "signal_candle": "2026-11-14 08:00:00",
                    "generated_at": "2026-11-14 11:00:00 EAT",
                    "entry": 1.1,
                    "entry_low": 1.099,
                    "entry_high": 1.101,
                    "sl": 1.095,
                    "tp1": None,
                    "tp2": None,
                    "tp3": None,
                }
                database.save_signal("EUR/USD", setup, "WAIT FOR ENTRY", "Wait")
                database.save_signal("EUR/USD", setup, "ENTRY TRIGGERED", "Touched")
                rows = database.list_signals()
                self.assertEqual(len(rows), 1)
                self.assertEqual(rows[0]["status"], "ENTRY TRIGGERED")
                self.assertEqual(rows[0]["tp1"], None)
                self.assertEqual(json.loads(rows[0]["payload_json"])["direction"], "BUY")


if __name__ == "__main__":
    unittest.main()
