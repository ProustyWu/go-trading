from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend.utils import write_json


class EvolutionReviewTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.instances_root = Path(self.temp_dir.name) / "instances"
        self.reviews_dir = Path(self.temp_dir.name) / "reviews"
        self.registry_path = Path(self.temp_dir.name) / "registry.json"
        self.promotions_path = Path(self.temp_dir.name) / "promotions.json"

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def _instance_paths(self, instance_id: str) -> dict[str, Path]:
        root = self.instances_root / str(instance_id)
        return {
            "root": root,
            "decisions_dir": root / "decisions",
        }

    def _write_decision(
        self,
        *,
        instance_id: str,
        decision_id: str,
        finished_at: str,
        family_id: str,
        realized_pnl_usd: float,
        drawdown_pct: float,
        actions: list[dict],
        warnings: list[str] | None = None,
    ) -> None:
        payload = {
            "id": decision_id,
            "startedAt": finished_at,
            "finishedAt": finished_at,
            "mode": "paper",
            "instanceId": instance_id,
            "familyId": family_id,
            "strategyMeta": {
                "instanceId": instance_id,
                "familyId": family_id,
                "presetId": "trend-following-v7",
                "promptName": "trend_following_v7",
                "promptHash": f"hash-{decision_id}",
            },
            "actions": actions,
            "warnings": warnings or [],
            "accountAfter": {
                "realizedPnlUsd": realized_pnl_usd,
                "drawdownPct": drawdown_pct,
            },
        }
        path = self._instance_paths(instance_id)["decisions_dir"] / finished_at[:10] / f"{decision_id}.json"
        write_json(path, payload)

    def test_load_family_decisions_reads_active_and_shadow_instances(self) -> None:
        from backend import evolution_registry, evolution_review

        with patch.object(evolution_registry, "FAMILY_REGISTRY_PATH", self.registry_path), patch.object(
            evolution_registry, "PROMOTION_LOG_PATH", self.promotions_path
        ), patch.object(evolution_review, "instance_paths", side_effect=self._instance_paths):
            evolution_registry.create_family(
                family_id="family-btc-trend-001",
                name="BTC Trend Paper Line",
                active_instance_id="paper-default",
            )
            evolution_registry.attach_shadow_instance("family-btc-trend-001", "paper-shadow")

            self._write_decision(
                instance_id="paper-default",
                decision_id="decision-001",
                finished_at="2026-05-05T00:10:00Z",
                family_id="family-btc-trend-001",
                realized_pnl_usd=25,
                drawdown_pct=2,
                actions=[],
            )
            self._write_decision(
                instance_id="paper-shadow",
                decision_id="decision-002",
                finished_at="2026-05-05T01:10:00Z",
                family_id="family-btc-trend-001",
                realized_pnl_usd=15,
                drawdown_pct=6,
                actions=[],
            )
            self._write_decision(
                instance_id="paper-other",
                decision_id="decision-003",
                finished_at="2026-05-05T02:10:00Z",
                family_id="family-other",
                realized_pnl_usd=99,
                drawdown_pct=1,
                actions=[],
            )

            decisions = evolution_review.load_family_decisions(family_id="family-btc-trend-001", limit=20)

        self.assertEqual([item["id"] for item in decisions], ["decision-001", "decision-002"])

    def test_write_review_report_scores_family_window(self) -> None:
        from backend import evolution_registry, evolution_review

        with patch.object(evolution_registry, "FAMILY_REGISTRY_PATH", self.registry_path), patch.object(
            evolution_registry, "PROMOTION_LOG_PATH", self.promotions_path
        ), patch.object(evolution_review, "instance_paths", side_effect=self._instance_paths), patch.object(
            evolution_review, "REVIEWS_DIR", self.reviews_dir
        ):
            evolution_registry.create_family(
                family_id="family-btc-trend-001",
                name="BTC Trend Paper Line",
                active_instance_id="paper-default",
            )
            evolution_registry.attach_shadow_instance("family-btc-trend-001", "paper-shadow")

            self._write_decision(
                instance_id="paper-default",
                decision_id="decision-001",
                finished_at="2026-05-05T00:10:00Z",
                family_id="family-btc-trend-001",
                realized_pnl_usd=25,
                drawdown_pct=2,
                actions=[
                    {"type": "open", "symbol": "BTCUSDT", "confidence": 82, "stopLoss": 100, "takeProfit": 120},
                    {"type": "close", "symbol": "BTCUSDT", "realizedPnlUsd": 25, "reason": "take_profit_hit"},
                ],
            )
            self._write_decision(
                instance_id="paper-shadow",
                decision_id="decision-002",
                finished_at="2026-05-05T01:10:00Z",
                family_id="family-btc-trend-001",
                realized_pnl_usd=15,
                drawdown_pct=6,
                actions=[
                    {"type": "open", "symbol": "ETHUSDT", "confidence": 62, "stopLoss": 90, "takeProfit": 95},
                    {"type": "close", "symbol": "ETHUSDT", "realizedPnlUsd": -10, "reason": "stop_loss_hit"},
                ],
                warnings=["Ignored invalid entry risk for ETHUSDT."],
            )

            report = evolution_review.write_review_report(
                family_id="family-btc-trend-001",
                min_decisions=2,
                min_closed_trades=2,
                limit=20,
            )

        self.assertEqual(report["decisions"], 2)
        self.assertEqual(report["closedTrades"], 2)
        self.assertFalse(report["insufficientSample"])
        self.assertEqual(report["scorecard"]["realizedPnl"], 15.0)
        self.assertEqual(report["scorecard"]["expectancy"], 7.5)
        self.assertEqual(report["scorecard"]["disciplinePenalty"], 2.0)
        self.assertEqual(report["scorecard"]["lowConfidencePenalty"], 1.5)
        self.assertEqual(report["finalScore"], 17.5)
        self.assertEqual(len(list(self.reviews_dir.glob("*.json"))), 1)

    def test_write_review_report_marks_insufficient_sample(self) -> None:
        from backend import evolution_registry, evolution_review

        with patch.object(evolution_registry, "FAMILY_REGISTRY_PATH", self.registry_path), patch.object(
            evolution_registry, "PROMOTION_LOG_PATH", self.promotions_path
        ), patch.object(evolution_review, "instance_paths", side_effect=self._instance_paths), patch.object(
            evolution_review, "REVIEWS_DIR", self.reviews_dir
        ):
            evolution_registry.create_family(
                family_id="family-btc-trend-001",
                name="BTC Trend Paper Line",
                active_instance_id="paper-default",
            )
            self._write_decision(
                instance_id="paper-default",
                decision_id="decision-001",
                finished_at="2026-05-05T00:10:00Z",
                family_id="family-btc-trend-001",
                realized_pnl_usd=0,
                drawdown_pct=1,
                actions=[],
            )

            report = evolution_review.write_review_report(
                family_id="family-btc-trend-001",
                min_decisions=2,
                min_closed_trades=1,
                limit=20,
            )

        self.assertTrue(report["insufficientSample"])
        self.assertEqual(report["decisions"], 1)
        self.assertEqual(report["closedTrades"], 0)


if __name__ == "__main__":
    unittest.main()
