from __future__ import annotations

import unittest
from unittest.mock import patch


class EvolutionRunnerStateTests(unittest.TestCase):
    def test_evolution_families_payload_includes_runner_snapshot(self) -> None:
        from backend import server

        runtime = server.AppRuntime()
        runtime.evolution_runners["family-paper-default"] = {
            "running": True,
            "lastStartedAt": "2026-05-05T05:00:00Z",
            "lastFinishedAt": None,
            "lastError": None,
            "lastReason": "scheduled",
            "lastDurationSeconds": 12.4,
            "lastResult": {
                "familyScore": 8.5,
                "candidatePresetId": "paper-default-candidate-v3",
            },
        }
        family = {
            "id": "family-paper-default",
            "name": "Paper Default Evolution Line",
            "activeInstanceId": "paper-default",
            "shadowInstanceIds": [],
            "currentPresetId": "paper-default-active-v1",
        }
        active_card = {
            "id": "paper-default",
            "name": "Paper Default",
            "type": "paper",
            "createdAt": "2026-05-05T04:00:00Z",
        }
        active_prompt = {
            "presetId": "paper-default-active-v1",
            "name": "paper_default_active_v1",
            "updated": "2026-05-05T04:10:00Z",
        }

        with patch.object(server, "list_instances", return_value=[{"id": "paper-default"}]), patch.object(
            runtime, "instance_card_payload", return_value=active_card
        ), patch.object(server, "read_family_registry", return_value={"families": [family]}), patch.object(
            server, "read_promotion_log", return_value={"records": []}
        ), patch.object(server, "_latest_reports", return_value=[]), patch.object(
            server, "read_prompt_settings", return_value=active_prompt
        ), patch.object(
            server,
            "read_trading_settings",
            return_value={"evolutionLab": {"shadow": {"requiredScoreDelta": 3.0, "minShadowDecisions": 20, "minShadowClosedTrades": 10}}},
        ):
            payload = runtime.evolution_families_payload()

        row = payload["families"][0]
        self.assertIn("evolutionRunner", row)
        self.assertTrue(row["evolutionRunner"]["running"])
        self.assertEqual(row["evolutionRunner"]["lastReason"], "scheduled")
        self.assertEqual(row["evolutionRunner"]["lastResult"]["candidatePresetId"], "paper-default-candidate-v3")

    def test_run_evolution_job_records_last_result_summary(self) -> None:
        from backend import server

        runtime = server.AppRuntime()
        result = {
            "familyReview": {
                "id": "review-family-paper-default",
                "finalScore": 8.5,
                "insufficientSample": False,
                "sample": {"decisions": 24, "closedTrades": 12},
            },
            "activeReview": {
                "id": "review-active-paper-default",
                "finalScore": 7.1,
            },
            "shadowReviews": [{"id": "review-shadow-paper-v3"}],
            "candidate": {"preset": {"id": "paper-default-candidate-v3"}},
            "shadow": {"instance": {"id": "paper-shadow-v3"}},
            "promotion": {"toInstanceId": "paper-shadow-v3"},
        }

        with patch.object(server, "run_family_evolution_cycle", return_value=result):
            runtime._run_evolution_job("family-paper-default", "manual_cycle")

        runner = runtime._evolution_runner("family-paper-default")
        self.assertFalse(runner["running"])
        self.assertEqual(runner["lastReason"], "manual_cycle")
        self.assertIsNone(runner["lastError"])
        self.assertIsNotNone(runner["lastFinishedAt"])
        self.assertGreaterEqual(float(runner["lastDurationSeconds"]), 0.0)
        self.assertEqual(runner["lastResult"]["familyScore"], 8.5)
        self.assertEqual(runner["lastResult"]["candidatePresetId"], "paper-default-candidate-v3")
        self.assertEqual(runner["lastResult"]["promotionInstanceId"], "paper-shadow-v3")

    def test_run_evolution_job_records_last_error(self) -> None:
        from backend import server

        runtime = server.AppRuntime()

        with patch.object(server, "run_family_evolution_cycle", side_effect=ValueError("boom")):
            runtime._run_evolution_job("family-paper-default", "manual_cycle")

        runner = runtime._evolution_runner("family-paper-default")
        self.assertFalse(runner["running"])
        self.assertEqual(runner["lastReason"], "manual_cycle")
        self.assertEqual(runner["lastError"], "boom")
        self.assertIsNotNone(runner["lastFinishedAt"])
        self.assertGreaterEqual(float(runner["lastDurationSeconds"]), 0.0)
        self.assertIsNone(runner["lastResult"])


if __name__ == "__main__":
    unittest.main()
