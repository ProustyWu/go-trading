from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend import config


class EvolutionCandidatePromptTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.instance_root = Path(self.temp_dir.name) / "instances"

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def _instance_path(self, instance_id: str | None, key: str, legacy_path: Path) -> Path:
        target = str(instance_id or "legacy").strip() or "legacy"
        filename_map = {
            "prompt": "trading_prompt.json",
            "prompt_library": "trading_prompt_library.json",
            "trading_settings": "trading_settings.json",
        }
        return self.instance_root / target / filename_map.get(key, f"{key}.json")

    def _review_report(self) -> dict:
        return {
            "id": "review-family-paper-default-20260505T022249Z",
            "familyId": "family-paper-default",
            "decisions": 12,
            "closedTrades": 8,
            "scorecard": {
                "realizedPnl": 28.5,
                "expectancy": 3.56,
                "maxDrawdownPct": 4.0,
                "disciplinePenalty": 2.0,
                "lowConfidencePenalty": 0.0,
            },
            "finalScore": 27.62,
            "insufficientSample": False,
        }

    def test_generate_candidate_prompt_persists_target_instance_preset(self) -> None:
        from backend import evolution_lab

        candidate_payload = {
            "name": "trend_following_v8_shadow",
            "klineFeeds": {
                "1m": {"enabled": False, "limit": 120},
                "5m": {"enabled": True, "limit": 80},
                "15m": {"enabled": True, "limit": 64},
            },
            "decision_logic": {
                "role": "You are a patient crypto futures trader.",
                "core_principles": ["Trade only when trend and momentum agree."],
                "entry_preferences": ["Wait for pullback confirmation before entering."],
                "position_management": ["Scale out faster when momentum stalls."],
                "response_style": ["Return strict JSON only."],
            },
        }

        with patch.object(config, "_instance_path", side_effect=self._instance_path), patch.object(
            evolution_lab, "generate_structured_json", return_value={"parsed": candidate_payload, "rawText": json.dumps(candidate_payload)}
        ):
            result = evolution_lab.generate_candidate_prompt(self._review_report(), instance_id="paper-default")
            library = config.read_prompt_library("paper-default")

        self.assertEqual(result["preset"]["name"], "trend_following_v8_shadow")
        self.assertEqual(result["preset"]["decision_logic"]["role"], "You are a patient crypto futures trader.")
        self.assertTrue(any(item["name"] == "trend_following_v8_shadow" for item in library["prompts"]))
        target_file = self._instance_path("paper-default", "prompt_library", config.PROMPT_LIBRARY_PATH)
        self.assertTrue(target_file.exists())
        payload = json.loads(target_file.read_text(encoding="utf-8"))
        self.assertEqual(len(payload["prompts"]), 1)

    def test_generate_candidate_prompt_rejects_forbidden_mutation_scope(self) -> None:
        from backend import evolution_lab

        bad_payload = {
            "name": "bad_candidate",
            "decision_logic": {
                "role": "You are still a trader.",
                "core_principles": ["Be careful."],
                "entry_preferences": ["Take selective entries."],
                "position_management": ["Keep losses small."],
                "response_style": ["Return strict JSON only."],
            },
            "riskPerTradePct": 9,
        }

        with patch.object(config, "_instance_path", side_effect=self._instance_path), patch.object(
            evolution_lab, "generate_structured_json", return_value={"parsed": bad_payload, "rawText": json.dumps(bad_payload)}
        ):
            with self.assertRaisesRegex(ValueError, "riskPerTradePct"):
                evolution_lab.generate_candidate_prompt(self._review_report(), instance_id="paper-default")

    def test_validate_candidate_mutation_scope_only_allows_prompt_fields(self) -> None:
        from backend import evolution_lab

        validated = evolution_lab.validate_candidate_mutation_scope(
            {
                "name": "trend_following_v8_shadow",
                "decision_logic": {
                    "role": "You are a patient crypto futures trader.",
                    "core_principles": ["Trade only when trend and momentum agree."],
                    "entry_preferences": ["Wait for pullback confirmation before entering."],
                    "position_management": ["Scale out faster when momentum stalls."],
                    "response_style": ["Return strict JSON only."],
                },
                "klineFeeds": {
                    "1m": {"enabled": False, "limit": 120},
                    "5m": {"enabled": True, "limit": 80},
                    "15m": {"enabled": True, "limit": 64},
                },
                "notes": "Candidate generated from review report.",
            }
        )

        self.assertEqual(validated["name"], "trend_following_v8_shadow")
        self.assertIn("decision_logic", validated)
        self.assertIn("klineFeeds", validated)
        self.assertNotIn("notes", validated)


if __name__ == "__main__":
    unittest.main()
