from __future__ import annotations

import unittest
from unittest.mock import patch


class EvolutionInstancePayloadTests(unittest.TestCase):
    def test_evolution_instance_payload_marks_shadow_role_and_actions(self) -> None:
        from backend import server

        runtime = server.AppRuntime()
        runtime.evolution_runners["family-paper-default"] = {
            "running": False,
            "lastStartedAt": "2026-05-05T05:00:00Z",
            "lastFinishedAt": "2026-05-05T05:00:04Z",
            "lastError": None,
            "lastReason": "manual_cycle",
            "lastDurationSeconds": 4.0,
            "lastResult": {"familyScore": 10.2},
        }
        family_payload = {
            "families": [
                {
                    "id": "family-paper-default",
                    "name": "Paper Default Evolution Line",
                    "activeInstanceId": "paper-active",
                    "shadowInstanceIds": ["paper-shadow"],
                    "status": "paused",
                    "currentPresetId": "paper-default-active-v3",
                    "activeInstance": {"id": "paper-active", "name": "Paper Active", "type": "paper"},
                    "shadowInstances": [{"id": "paper-shadow", "name": "Paper Shadow", "type": "paper"}],
                    "evolutionRunner": dict(runtime.evolution_runners["family-paper-default"]),
                    "latestFamilyReview": {"id": "review-family", "finalScore": 10.2},
                    "latestActiveReview": {"id": "review-active", "instanceId": "paper-active", "finalScore": 8.0},
                    "latestShadowReviews": [{"id": "review-shadow", "instanceId": "paper-shadow", "finalScore": 12.5}],
                    "latestCandidate": {"presetId": "paper-default-candidate-v4", "instanceId": "paper-shadow"},
                    "promotionPreview": {
                        "shadowInstanceId": "paper-shadow",
                        "shadowScore": 12.5,
                        "activeScore": 8.0,
                        "scoreDelta": 4.5,
                        "requiredScoreDelta": 3.0,
                        "promotable": True,
                        "highlights": ["expectancy +1.2", "drawdown +1.5"],
                    },
                    "promotionCount": 1,
                    "lastPromotion": {"approvedAt": "2026-05-05T04:40:00Z", "toInstanceId": "paper-active"},
                }
            ]
        }

        with patch.object(runtime, "evolution_families_payload", return_value=family_payload):
            payload = runtime.evolution_instance_payload("paper-shadow")

        self.assertEqual(payload["role"], "shadow")
        self.assertEqual(payload["family"]["id"], "family-paper-default")
        self.assertEqual(payload["family"]["status"], "paused")
        self.assertTrue(payload["actions"]["canRetireShadow"])
        self.assertFalse(payload["actions"]["canPromoteShadow"])
        self.assertFalse(payload["actions"]["canCreateCandidate"])
        self.assertFalse(payload["actions"]["canPauseFamily"])
        self.assertTrue(payload["actions"]["canResumeFamily"])
        self.assertTrue(payload["actions"]["canArchiveFamily"])
        self.assertEqual(payload["promotionPreview"]["shadowInstanceId"], "paper-shadow")
        self.assertEqual(payload["promotionPreview"]["highlights"][0], "expectancy +1.2")
        self.assertEqual(payload["latestInstanceReview"]["id"], "review-shadow")

    def test_evolution_instance_payload_marks_unbound_instance(self) -> None:
        from backend import server

        runtime = server.AppRuntime()

        with patch.object(runtime, "evolution_families_payload", return_value={"families": []}):
            payload = runtime.evolution_instance_payload("paper-lonely")

        self.assertEqual(payload["role"], "unbound")
        self.assertIsNone(payload["family"])
        self.assertFalse(payload["actions"]["canRunCycle"])
        self.assertFalse(payload["actions"]["canRetireShadow"])
        self.assertFalse(payload["actions"]["canPauseFamily"])
        self.assertFalse(payload["actions"]["canResumeFamily"])
        self.assertFalse(payload["actions"]["canArchiveFamily"])


if __name__ == "__main__":
    unittest.main()
