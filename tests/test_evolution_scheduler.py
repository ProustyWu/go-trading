from __future__ import annotations

import unittest
from unittest.mock import patch


def _lab_settings(**overrides):
    settings = {
        "enabled": True,
        "reviewIntervalHours": 24,
        "reviewLookbackDays": 7,
        "minClosedTrades": 12,
        "minDecisions": 20,
        "autoCreateCandidate": True,
        "autoPromoteToPaper": False,
        "allowCandidateSourceMutation": False,
        "shadow": {
            "enabled": True,
            "minShadowDecisions": 20,
            "minShadowClosedTrades": 10,
            "requiredScoreDelta": 3.0,
        },
    }
    settings.update(overrides)
    if "shadow" in overrides and isinstance(overrides["shadow"], dict):
        shadow = dict(settings["shadow"])
        shadow.update(overrides["shadow"])
        settings["shadow"] = shadow
    return settings


class EvolutionSchedulerTests(unittest.TestCase):
    def test_run_family_evolution_cycle_creates_candidate_and_shadow(self) -> None:
        from backend import server

        family = {
            "id": "family-paper-default",
            "name": "Paper Default Evolution Line",
            "activeInstanceId": "paper-default",
            "shadowInstanceIds": [],
            "currentPresetId": "paper-default-active-v1",
        }
        family_review = {
            "id": "review-family",
            "familyId": "family-paper-default",
            "instanceId": None,
            "finalScore": 8.5,
            "insufficientSample": False,
            "sample": {"decisions": 24, "closedTrades": 12},
        }
        active_review = {
            "id": "review-active",
            "familyId": None,
            "instanceId": "paper-default",
            "finalScore": 7.2,
            "insufficientSample": False,
            "sample": {"decisions": 24, "closedTrades": 12},
        }
        candidate = {"preset": {"id": "paper-default-candidate-v1", "name": "paper_default_candidate_v1"}}
        shadow = {"instance": {"id": "paper-shadow-v1", "name": "Paper Default · SHADOW · paper_default_candidate_v1"}}

        with patch.object(server, "read_family_registry", return_value={"families": [family]}), patch.object(
            server, "read_instance", return_value={"id": "paper-default", "name": "Paper Default", "type": "paper"}
        ), patch.object(server, "read_trading_settings", return_value={"evolutionLab": _lab_settings()}), patch.object(
            server, "write_review_report", side_effect=[family_review, active_review]
        ) as write_review, patch.object(server, "generate_candidate_prompt", return_value=candidate) as generate_candidate, patch.object(
            server, "create_shadow_instance_from_candidate", return_value=shadow
        ) as create_shadow, patch.object(server, "promote_shadow_to_active") as promote_shadow:
            result = server.run_family_evolution_cycle("family-paper-default", reason="scheduled")

        self.assertEqual(result["familyReview"]["id"], "review-family")
        self.assertEqual(result["activeReview"]["id"], "review-active")
        self.assertEqual(result["candidate"]["preset"]["id"], "paper-default-candidate-v1")
        self.assertEqual(result["shadow"]["instance"]["id"], "paper-shadow-v1")
        self.assertIsNone(result["promotion"])
        self.assertEqual(write_review.call_count, 2)
        generate_candidate.assert_called_once_with(family_review, instance_id="paper-default", candidate_payload=None)
        create_shadow.assert_called_once_with(
            active_instance_id="paper-default",
            family_id="family-paper-default",
            candidate_preset_id="paper-default-candidate-v1",
        )
        promote_shadow.assert_not_called()

    def test_run_family_evolution_cycle_auto_promotes_best_shadow(self) -> None:
        from backend import server

        family = {
            "id": "family-paper-default",
            "name": "Paper Default Evolution Line",
            "activeInstanceId": "paper-default",
            "shadowInstanceIds": ["paper-shadow-v1"],
            "currentPresetId": "paper-default-active-v1",
        }
        family_review = {
            "id": "review-family",
            "familyId": "family-paper-default",
            "instanceId": None,
            "finalScore": 8.5,
            "insufficientSample": False,
            "sample": {"decisions": 24, "closedTrades": 12},
        }
        active_review = {
            "id": "review-active",
            "familyId": None,
            "instanceId": "paper-default",
            "finalScore": 7.2,
            "insufficientSample": False,
            "sample": {"decisions": 24, "closedTrades": 12},
        }
        shadow_review = {
            "id": "review-shadow",
            "familyId": None,
            "instanceId": "paper-shadow-v1",
            "finalScore": 12.6,
            "insufficientSample": False,
            "sample": {"decisions": 26, "closedTrades": 14},
        }
        preview = {
            "shadowInstanceId": "paper-shadow-v1",
            "scoreDelta": 5.4,
            "requiredScoreDelta": 3.0,
            "promotable": True,
            "winner": "shadow",
            "reasons": [],
        }
        promotion = {"toInstanceId": "paper-shadow-v1", "reason": "scheduled_auto_promote"}

        with patch.object(server, "read_family_registry", return_value={"families": [family]}), patch.object(
            server, "read_instance", return_value={"id": "paper-default", "name": "Paper Default", "type": "paper"}
        ), patch.object(
            server,
            "read_trading_settings",
            return_value={"evolutionLab": _lab_settings(autoCreateCandidate=False, autoPromoteToPaper=True)},
        ), patch.object(
            server, "write_review_report", side_effect=[family_review, active_review, shadow_review]
        ), patch.object(server, "compare_active_and_shadow", return_value=preview) as compare_reviews, patch.object(
            server, "promote_shadow_to_active", return_value=promotion
        ) as promote_shadow, patch.object(server, "generate_candidate_prompt") as generate_candidate:
            result = server.run_family_evolution_cycle("family-paper-default", reason="scheduled")

        self.assertEqual(result["promotion"]["toInstanceId"], "paper-shadow-v1")
        compare_reviews.assert_called_once()
        promote_shadow.assert_called_once_with(
            family_id="family-paper-default",
            shadow_instance_id="paper-shadow-v1",
            reason="scheduled_auto_promote",
            score_delta=5.4,
            auto=False,
        )
        generate_candidate.assert_not_called()

    def test_maybe_start_scheduled_evolution_starts_due_family(self) -> None:
        from backend import server

        runtime = server.AppRuntime()
        family = {
            "id": "family-paper-default",
            "name": "Paper Default Evolution Line",
            "activeInstanceId": "paper-default",
            "shadowInstanceIds": [],
            "currentPresetId": "paper-default-active-v1",
            "status": "active",
        }

        with patch.object(server, "read_family_registry", return_value={"families": [family]}), patch.object(
            server, "read_instance", return_value={"id": "paper-default", "name": "Paper Default", "type": "paper"}
        ), patch.object(server, "read_trading_settings", return_value={"evolutionLab": _lab_settings()}), patch.object(
            server, "_latest_reports", return_value=[]
        ), patch.object(runtime, "start_evolution", return_value=True) as start_evolution:
            runtime._maybe_start_scheduled_evolution()

        start_evolution.assert_called_once_with("family-paper-default", "scheduled")

    def test_maybe_start_scheduled_evolution_skips_recent_family(self) -> None:
        from backend import server

        runtime = server.AppRuntime()
        family = {
            "id": "family-paper-default",
            "name": "Paper Default Evolution Line",
            "activeInstanceId": "paper-default",
            "shadowInstanceIds": [],
            "currentPresetId": "paper-default-active-v1",
            "status": "active",
        }
        recent_review = {
            "id": "review-family-paper-default-latest",
            "familyId": "family-paper-default",
            "instanceId": None,
            "generatedAt": server.now_iso(),
        }

        with patch.object(server, "read_family_registry", return_value={"families": [family]}), patch.object(
            server, "read_instance", return_value={"id": "paper-default", "name": "Paper Default", "type": "paper"}
        ), patch.object(server, "read_trading_settings", return_value={"evolutionLab": _lab_settings()}), patch.object(
            server, "_latest_reports", return_value=[recent_review]
        ), patch.object(runtime, "start_evolution", return_value=True) as start_evolution:
            runtime._maybe_start_scheduled_evolution()

        start_evolution.assert_not_called()

    def test_maybe_start_scheduled_evolution_skips_paused_family(self) -> None:
        from backend import server

        runtime = server.AppRuntime()
        family = {
            "id": "family-paper-default",
            "name": "Paper Default Evolution Line",
            "activeInstanceId": "paper-default",
            "shadowInstanceIds": [],
            "currentPresetId": "paper-default-active-v1",
            "status": "paused",
        }

        with patch.object(server, "read_family_registry", return_value={"families": [family]}), patch.object(
            server, "read_instance", return_value={"id": "paper-default", "name": "Paper Default", "type": "paper"}
        ), patch.object(server, "read_trading_settings", return_value={"evolutionLab": _lab_settings()}), patch.object(
            server, "_latest_reports", return_value=[]
        ), patch.object(
            runtime, "start_evolution", return_value=True
        ) as start_evolution:
            runtime._maybe_start_scheduled_evolution()

        start_evolution.assert_not_called()


if __name__ == "__main__":
    unittest.main()
