from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


class EvolutionShadowInstanceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.instance_root = Path(self.temp_dir.name) / "instances"
        self.index_path = self.instance_root / "index.json"
        self.registry_path = Path(self.temp_dir.name) / "registry.json"
        self.promotions_path = Path(self.temp_dir.name) / "promotions.json"

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_create_shadow_instance_from_candidate_clones_paper_active(self) -> None:
        from backend import config, evolution_lab, evolution_registry, instances

        candidate_payload = {
            "name": "paper_default_candidate_v1",
            "decision_logic": {
                "role": "You are a patient crypto futures trader.",
                "core_principles": ["Protect capital first and wait for cleaner pullbacks."],
                "entry_preferences": ["Prefer continuation setups with stronger confirmation."],
                "position_management": ["Reduce exposure faster when momentum fades."],
                "response_style": ["Return strict JSON only."],
            },
            "klineFeeds": {
                "1m": {"enabled": False, "limit": 120},
                "5m": {"enabled": True, "limit": 80},
                "15m": {"enabled": True, "limit": 64},
            },
        }

        with patch.object(instances, "INSTANCE_ROOT", self.instance_root), patch.object(
            instances, "INSTANCE_INDEX_PATH", self.index_path
        ), patch.object(evolution_registry, "FAMILY_REGISTRY_PATH", self.registry_path), patch.object(
            evolution_registry, "PROMOTION_LOG_PATH", self.promotions_path
        ):
            instances.ensure_instances_migrated()
            evolution_registry.create_family(
                family_id="family-paper-default",
                name="Paper Default Evolution Line",
                active_instance_id="paper-default",
            )
            saved = evolution_lab.persist_candidate_preset("paper-default", candidate_payload)
            created = evolution_lab.create_shadow_instance_from_candidate(
                active_instance_id="paper-default",
                family_id="family-paper-default",
                candidate_preset_id=saved["preset"]["id"],
            )

            shadow_id = created["instance"]["id"]
            shadow_settings = config.read_trading_settings(shadow_id)
            shadow_prompt = config.read_prompt_settings(shadow_id)
            shadow_library = config.read_prompt_library(shadow_id)
            registry = evolution_registry.read_family_registry()

        self.assertEqual(created["instance"]["type"], "paper")
        self.assertFalse(shadow_settings["paperTrading"]["enabled"])
        self.assertFalse(shadow_settings["liveTrading"]["enabled"])
        self.assertEqual(shadow_prompt["presetId"], saved["preset"]["id"])
        self.assertEqual(shadow_prompt["name"], saved["preset"]["name"])
        self.assertTrue(any(item["id"] == saved["preset"]["id"] for item in shadow_library["prompts"]))
        family = next(item for item in registry["families"] if item["id"] == "family-paper-default")
        self.assertIn(shadow_id, family["shadowInstanceIds"])
        self.assertEqual(created["preset"]["id"], saved["preset"]["id"])


if __name__ == "__main__":
    unittest.main()
