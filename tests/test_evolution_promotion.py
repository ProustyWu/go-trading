from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


class EvolutionPromotionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.instance_root = Path(self.temp_dir.name) / "instances"
        self.index_path = self.instance_root / "index.json"
        self.registry_path = Path(self.temp_dir.name) / "registry.json"
        self.promotions_path = Path(self.temp_dir.name) / "promotions.json"

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_compare_active_and_shadow_marks_promotable_when_delta_clears_gate(self) -> None:
        from backend import evolution_lab

        active_review = {
            "id": "review-active",
            "instanceId": "paper-default",
            "finalScore": 11.5,
            "insufficientSample": False,
            "sample": {"decisions": 24, "closedTrades": 12},
            "scorecard": {
                "realizedPnl": 12.0,
                "expectancy": 1.0,
                "maxDrawdownPct": 6.0,
                "disciplinePenalty": 2.0,
                "lowConfidencePenalty": 1.5,
            },
        }
        shadow_review = {
            "id": "review-shadow",
            "instanceId": "paper-shadow",
            "finalScore": 16.2,
            "insufficientSample": False,
            "sample": {"decisions": 26, "closedTrades": 14},
            "scorecard": {
                "realizedPnl": 14.0,
                "expectancy": 2.2,
                "maxDrawdownPct": 4.5,
                "disciplinePenalty": 1.0,
                "lowConfidencePenalty": 0.0,
            },
        }

        comparison = evolution_lab.compare_active_and_shadow(
            active_review=active_review,
            shadow_review=shadow_review,
            required_score_delta=3.0,
        )

        self.assertTrue(comparison["promotable"])
        self.assertEqual(comparison["winner"], "shadow")
        self.assertEqual(comparison["scoreDelta"], 4.7)
        self.assertIn("componentDelta", comparison)
        self.assertGreater(comparison["componentDelta"]["expectancy"], 0)
        self.assertTrue(comparison["highlights"])

    def test_promote_shadow_to_active_swaps_family_active_and_records_promotion(self) -> None:
        from backend import config, evolution_lab, evolution_registry, instances

        with patch.object(instances, "INSTANCE_ROOT", self.instance_root), patch.object(
            instances, "INSTANCE_INDEX_PATH", self.index_path
        ), patch.object(evolution_registry, "FAMILY_REGISTRY_PATH", self.registry_path), patch.object(
            evolution_registry, "PROMOTION_LOG_PATH", self.promotions_path
        ):
            instances.ensure_instances_migrated()
            config.write_prompt_settings(
                {
                    "name": "paper_default_active",
                    "presetId": "paper-default-active-v1",
                },
                "paper-default",
            )
            evolution_registry.create_family(
                family_id="family-paper-default",
                name="Paper Default Evolution Line",
                active_instance_id="paper-default",
                current_preset_id="paper-default-active-v1",
            )
            shadow_instance = instances.create_instance("Paper Shadow", "paper")
            shadow_id = shadow_instance["id"]
            config.write_prompt_settings(
                {
                    "name": "paper_default_candidate_v2",
                    "presetId": "paper-default-candidate-v2",
                },
                shadow_id,
            )
            evolution_registry.attach_shadow_instance("family-paper-default", shadow_id)

            promotion = evolution_lab.promote_shadow_to_active(
                family_id="family-paper-default",
                shadow_instance_id=shadow_id,
                reason="shadow_outperformed_active",
                score_delta=5.4,
                auto=False,
            )
            registry = evolution_registry.read_family_registry()
            promotion_log = evolution_registry.read_promotion_log()

        family = next(item for item in registry["families"] if item["id"] == "family-paper-default")
        self.assertEqual(family["activeInstanceId"], shadow_id)
        self.assertEqual(family["currentPresetId"], "paper-default-candidate-v2")
        self.assertIn("paper-default", family["shadowInstanceIds"])
        self.assertNotIn(shadow_id, family["shadowInstanceIds"])
        self.assertEqual(promotion["toInstanceId"], shadow_id)
        self.assertEqual(promotion_log["records"][-1]["toInstanceId"], shadow_id)

    def test_promote_shadow_to_active_rejects_live_auto_promotion(self) -> None:
        from backend import evolution_lab, evolution_registry, instances

        with patch.object(instances, "INSTANCE_ROOT", self.instance_root), patch.object(
            instances, "INSTANCE_INDEX_PATH", self.index_path
        ), patch.object(evolution_registry, "FAMILY_REGISTRY_PATH", self.registry_path), patch.object(
            evolution_registry, "PROMOTION_LOG_PATH", self.promotions_path
        ):
            instances.ensure_instances_migrated()
            evolution_registry.create_family(
                family_id="family-live-default",
                name="Live Default Evolution Line",
                active_instance_id="live-default",
            )
            shadow_instance = instances.create_instance("Paper Shadow", "paper")

            with self.assertRaisesRegex(ValueError, "Automatic promotion to live is not allowed"):
                evolution_lab.promote_shadow_to_active(
                    family_id="family-live-default",
                    shadow_instance_id=shadow_instance["id"],
                    reason="shadow_outperformed_active",
                    score_delta=4.0,
                    auto=True,
                )


if __name__ == "__main__":
    unittest.main()
