from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


class EvolutionRegistryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.registry_path = Path(self.temp_dir.name) / "registry.json"
        self.promotions_path = Path(self.temp_dir.name) / "promotions.json"

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_read_family_registry_creates_empty_default(self) -> None:
        from backend import evolution_registry

        with patch.object(evolution_registry, "FAMILY_REGISTRY_PATH", self.registry_path), patch.object(
            evolution_registry, "PROMOTION_LOG_PATH", self.promotions_path
        ):
            payload = evolution_registry.read_family_registry()

        self.assertEqual(payload["version"], 1)
        self.assertEqual(payload["families"], [])
        self.assertTrue(self.registry_path.exists())

    def test_create_family_records_active_instance(self) -> None:
        from backend import evolution_registry

        with patch.object(evolution_registry, "FAMILY_REGISTRY_PATH", self.registry_path), patch.object(
            evolution_registry, "PROMOTION_LOG_PATH", self.promotions_path
        ):
            family = evolution_registry.create_family(
                family_id="family-btc-trend-001",
                name="BTC Trend Paper Line",
                active_instance_id="paper-default",
                current_preset_id="trend-following-v7",
            )
            payload = evolution_registry.read_family_registry()

        self.assertEqual(family["activeInstanceId"], "paper-default")
        self.assertEqual(family["currentPresetId"], "trend-following-v7")
        self.assertEqual(payload["families"][0]["id"], "family-btc-trend-001")

    def test_attach_shadow_instance_appends_unique_shadow_id(self) -> None:
        from backend import evolution_registry

        with patch.object(evolution_registry, "FAMILY_REGISTRY_PATH", self.registry_path), patch.object(
            evolution_registry, "PROMOTION_LOG_PATH", self.promotions_path
        ):
            evolution_registry.create_family(
                family_id="family-btc-trend-001",
                name="BTC Trend Paper Line",
                active_instance_id="paper-default",
            )
            updated = evolution_registry.attach_shadow_instance("family-btc-trend-001", "paper-a1b2c3d4")
            updated_again = evolution_registry.attach_shadow_instance("family-btc-trend-001", "paper-a1b2c3d4")

        self.assertEqual(updated["shadowInstanceIds"], ["paper-a1b2c3d4"])
        self.assertEqual(updated_again["shadowInstanceIds"], ["paper-a1b2c3d4"])

    def test_detach_shadow_instance_removes_shadow_id(self) -> None:
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
            evolution_registry.attach_shadow_instance("family-btc-trend-001", "paper-e5f6g7h8")
            updated = evolution_registry.detach_shadow_instance("family-btc-trend-001", "paper-a1b2c3d4")

        self.assertEqual(updated["activeInstanceId"], "paper-default")
        self.assertEqual(updated["shadowInstanceIds"], ["paper-e5f6g7h8"])

    def test_record_promotion_writes_log_entry(self) -> None:
        from backend import evolution_registry

        with patch.object(evolution_registry, "FAMILY_REGISTRY_PATH", self.registry_path), patch.object(
            evolution_registry, "PROMOTION_LOG_PATH", self.promotions_path
        ):
            evolution_registry.create_family(
                family_id="family-btc-trend-001",
                name="BTC Trend Paper Line",
                active_instance_id="paper-default",
            )
            promotion = evolution_registry.record_promotion(
                family_id="family-btc-trend-001",
                from_instance_id="paper-default",
                to_instance_id="paper-a1b2c3d4",
                reason="shadow_outperformed_active",
                score_delta=4.2,
                auto=False,
            )
            log_payload = evolution_registry.read_promotion_log()

        self.assertEqual(promotion["familyId"], "family-btc-trend-001")
        self.assertEqual(log_payload["records"][0]["toInstanceId"], "paper-a1b2c3d4")


if __name__ == "__main__":
    unittest.main()
