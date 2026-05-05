from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend import config
from backend.utils import read_json, write_json


class EvolutionLabConfigTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.instance_root = Path(self.temp_dir.name)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def _instance_path(self, instance_id: str | None, key: str, legacy_path: Path) -> Path:
        target = str(instance_id or "legacy").strip() or "legacy"
        return self.instance_root / target / f"{key}.json"

    def test_read_trading_settings_returns_default_evolution_lab(self) -> None:
        with patch.object(config, "_instance_path", side_effect=self._instance_path):
            settings = config.read_trading_settings("paper-test")

        self.assertIn("evolutionLab", settings)
        self.assertFalse(settings["evolutionLab"]["enabled"])
        self.assertTrue(settings["evolutionLab"]["shadow"]["enabled"])

    def test_write_trading_settings_persists_evolution_lab_patch(self) -> None:
        with patch.object(config, "_instance_path", side_effect=self._instance_path):
            updated = config.write_trading_settings(
                {
                    "evolutionLab": {
                        "enabled": True,
                        "reviewIntervalHours": 12,
                        "shadow": {
                            "enabled": False,
                            "requiredScoreDelta": 5,
                        },
                    }
                },
                "paper-test",
            )
            reloaded = config.read_trading_settings("paper-test")

        self.assertTrue(updated["evolutionLab"]["enabled"])
        self.assertEqual(updated["evolutionLab"]["reviewIntervalHours"], 12)
        self.assertFalse(updated["evolutionLab"]["shadow"]["enabled"])
        self.assertEqual(reloaded["evolutionLab"]["shadow"]["requiredScoreDelta"], 5)
        self.assertEqual(reloaded["evolutionLab"]["reviewLookbackDays"], 7)

    def test_read_trading_settings_backfills_missing_evolution_lab(self) -> None:
        target = self._instance_path("paper-legacy", "trading_settings", config.TRADING_SETTINGS_PATH)
        write_json(
            target,
            {
                "mode": "paper",
                "activeExchange": "binance",
                "server": {"host": "127.0.0.1", "port": 8788},
            },
        )

        with patch.object(config, "_instance_path", side_effect=self._instance_path):
            settings = config.read_trading_settings("paper-legacy")

        self.assertIn("evolutionLab", settings)
        self.assertEqual(settings["evolutionLab"]["minClosedTrades"], 12)
        self.assertEqual(settings["evolutionLab"]["shadow"]["minShadowClosedTrades"], 10)
        self.assertIsInstance(read_json(target, {}), dict)


if __name__ == "__main__":
    unittest.main()
