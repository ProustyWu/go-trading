from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


class EngineStrategyFamilyMetaTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.registry_path = Path(self.temp_dir.name) / "registry.json"
        self.promotions_path = Path(self.temp_dir.name) / "promotions.json"
        self.decisions_dir = Path(self.temp_dir.name) / "decisions"

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_family_for_instance_matches_active_and_shadow(self) -> None:
        from backend import evolution_registry

        with patch.object(evolution_registry, "FAMILY_REGISTRY_PATH", self.registry_path), patch.object(
            evolution_registry, "PROMOTION_LOG_PATH", self.promotions_path
        ):
            evolution_registry.create_family(
                family_id="family-btc-trend-001",
                name="BTC Trend Paper Line",
                active_instance_id="paper-default",
            )
            evolution_registry.attach_shadow_instance("family-btc-trend-001", "paper-a1b2c3d4")

            active = evolution_registry.family_for_instance("paper-default")
            shadow = evolution_registry.family_for_instance("paper-a1b2c3d4")

        self.assertEqual(active["id"], "family-btc-trend-001")
        self.assertEqual(shadow["id"], "family-btc-trend-001")

    def test_archive_decision_contains_strategy_family_metadata(self) -> None:
        from backend import engine, evolution_registry

        prompt_settings = {
            "name": "trend_following_v7",
            "presetId": "trend-following-v7",
            "klineFeeds": {"15m": {"enabled": True, "limit": 64}},
            "decision_logic": {
                "role": "You are a careful crypto futures trader.",
                "core_principles": ["Protect capital first."],
            },
        }
        raw_decision = {
            "id": "decision-001",
            "startedAt": "2026-05-05T00:00:00Z",
            "finishedAt": "2026-05-05T00:01:00Z",
            "runnerReason": "manual",
            "mode": "paper",
            "prompt": "test prompt",
            "promptSummary": "test summary",
            "output": {},
            "actions": [],
            "candidateUniverse": [],
            "accountBefore": {},
            "accountAfter": {},
        }

        with patch.object(evolution_registry, "FAMILY_REGISTRY_PATH", self.registry_path), patch.object(
            evolution_registry, "PROMOTION_LOG_PATH", self.promotions_path
        ), patch.object(engine, "_decisions_dir", return_value=self.decisions_dir):
            evolution_registry.create_family(
                family_id="family-btc-trend-001",
                name="BTC Trend Paper Line",
                active_instance_id="paper-default",
                current_preset_id="trend-following-v7",
            )
            decision = engine.apply_strategy_metadata(raw_decision, prompt_settings=prompt_settings, instance_id="paper-default")
            normalized = engine.normalize_decision(decision)
            engine.archive_decision(normalized, "paper-default")

        archived_files = list(self.decisions_dir.glob("*/*.json"))
        self.assertEqual(len(archived_files), 1)
        payload = archived_files[0].read_text(encoding="utf-8")
        self.assertIn('"instanceId": "paper-default"', payload)
        self.assertIn('"familyId": "family-btc-trend-001"', payload)
        self.assertIn('"presetId": "trend-following-v7"', payload)
        self.assertIn('"promptName": "trend_following_v7"', payload)
        self.assertIn('"strategyMeta"', payload)

        import json

        parsed = json.loads(payload)
        self.assertEqual(parsed["strategyMeta"]["instanceId"], "paper-default")
        self.assertEqual(parsed["strategyMeta"]["familyId"], "family-btc-trend-001")
        self.assertEqual(parsed["strategyMeta"]["promptName"], "trend_following_v7")
        self.assertEqual(parsed["promptHash"], parsed["strategyMeta"]["promptHash"])
        self.assertTrue(parsed["promptHash"])


if __name__ == "__main__":
    unittest.main()
