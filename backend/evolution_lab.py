from __future__ import annotations

import json
from typing import Any

from .config import (
    read_llm_provider,
    read_network_settings,
    read_prompt_preset,
    read_prompt_settings,
    save_prompt_preset,
    write_prompt_settings,
    write_trading_settings,
)
from .evolution_registry import attach_shadow_instance, family_for_instance
from .instances import clone_instance, read_instance
from .llm import generate_structured_json


CANDIDATE_SYSTEM_PROMPT = (
    "You are an AI trading strategy researcher. "
    "Return strict JSON only. "
    "You may only propose mutations to prompt decision logic and optional kline feeds. "
    "Do not change risk limits, live execution settings, network settings, exchange credentials, or provider credentials."
)

ALLOWED_CANDIDATE_ROOT_KEYS = {
    "name",
    "decision_logic",
    "klineFeeds",
    "notes",
    "summary",
    "thesis",
    "reviewId",
}

FORBIDDEN_MUTATION_KEYS = {
    "activeExchange",
    "allowShorts",
    "apiKey",
    "apiPassphrase",
    "apiSecret",
    "baseUrl",
    "customHeaders",
    "exchange",
    "exchangeCredentials",
    "liveExecution",
    "liveTrading",
    "maxAccountDrawdownPct",
    "maxGrossExposurePct",
    "maxNewPositionsPerCycle",
    "maxOpenPositions",
    "maxPositionNotionalUsd",
    "minConfidence",
    "network",
    "paperFeesBps",
    "paperTrading",
    "proxyEnabled",
    "proxyUrl",
    "recvWindow",
    "riskPerTradePct",
    "server",
    "selfLearning",
}


def build_research_prompt(review_report: dict[str, Any], current_prompt: dict[str, Any]) -> str:
    review_json = json.dumps(review_report, ensure_ascii=False, indent=2, sort_keys=True)
    prompt_json = json.dumps(
        {
            "name": current_prompt.get("name"),
            "presetId": current_prompt.get("presetId"),
            "klineFeeds": current_prompt.get("klineFeeds"),
            "decision_logic": current_prompt.get("decision_logic"),
        },
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    )
    return (
        "You are revising a trading prompt after a scored review window.\n"
        "Use the review report to produce one safer or stronger candidate prompt preset.\n"
        "Only mutate decision_logic and optional klineFeeds.\n"
        "Return a single JSON object with keys: name, decision_logic, klineFeeds.\n"
        "Do not include any risk, execution, network, provider, or exchange credential fields.\n\n"
        "## Review Report\n"
        f"{review_json}\n\n"
        "## Current Prompt\n"
        f"{prompt_json}\n"
    )


def _collect_forbidden_keys(payload: Any) -> set[str]:
    found: set[str] = set()
    if isinstance(payload, dict):
        for key, value in payload.items():
            if str(key) in FORBIDDEN_MUTATION_KEYS:
                found.add(str(key))
            found.update(_collect_forbidden_keys(value))
    elif isinstance(payload, list):
        for item in payload:
            found.update(_collect_forbidden_keys(item))
    return found


def validate_candidate_mutation_scope(candidate_payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(candidate_payload, dict):
        raise ValueError("Candidate prompt payload must be a JSON object.")
    forbidden = sorted(_collect_forbidden_keys(candidate_payload))
    if forbidden:
        raise ValueError(f"Candidate prompt touches forbidden fields: {', '.join(forbidden)}")
    unexpected = sorted(key for key in candidate_payload.keys() if key not in ALLOWED_CANDIDATE_ROOT_KEYS)
    if unexpected:
        raise ValueError(f"Candidate prompt contains unsupported root fields: {', '.join(unexpected)}")
    decision_logic = candidate_payload.get("decision_logic")
    kline_feeds = candidate_payload.get("klineFeeds")
    if not isinstance(decision_logic, dict) and not isinstance(kline_feeds, dict):
        raise ValueError("Candidate prompt must include decision_logic or klineFeeds.")
    validated: dict[str, Any] = {}
    if str(candidate_payload.get("name") or "").strip():
        validated["name"] = str(candidate_payload.get("name")).strip()
    if isinstance(decision_logic, dict):
        validated["decision_logic"] = decision_logic
    if isinstance(kline_feeds, dict):
        validated["klineFeeds"] = kline_feeds
    return validated


def persist_candidate_preset(
    instance_id: str,
    candidate_payload: dict[str, Any],
    *,
    current_prompt: dict[str, Any] | None = None,
) -> dict[str, Any]:
    current_prompt = current_prompt or read_prompt_settings(instance_id)
    validated = validate_candidate_mutation_scope(candidate_payload)
    preset_payload = {
        "name": validated.get("name") or f"{current_prompt.get('name') or 'trading_logic'}_candidate",
        "decision_logic": validated.get("decision_logic", current_prompt.get("decision_logic")),
        "klineFeeds": validated.get("klineFeeds", current_prompt.get("klineFeeds")),
    }
    return save_prompt_preset(preset_payload, instance_id)


def generate_candidate_prompt(
    review_report: dict[str, Any],
    *,
    instance_id: str,
    candidate_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if review_report.get("insufficientSample") is True:
        raise ValueError("Cannot generate candidate prompt from an insufficient-sample review.")
    current_prompt = read_prompt_settings(instance_id)
    llm_result: dict[str, Any] | None = None
    candidate = candidate_payload
    if candidate is None:
        research_prompt = build_research_prompt(review_report, current_prompt)
        llm_result = generate_structured_json(
            research_prompt,
            provider=read_llm_provider(instance_id),
            network_settings=read_network_settings(instance_id),
            system_prompt=CANDIDATE_SYSTEM_PROMPT,
        )
        candidate = llm_result.get("parsed") if isinstance(llm_result, dict) else None
    validated = validate_candidate_mutation_scope(candidate if isinstance(candidate, dict) else {})
    saved = persist_candidate_preset(instance_id, validated, current_prompt=current_prompt)
    return {
        **saved,
        "candidate": validated,
        "reviewId": str(review_report.get("id") or "").strip() or None,
        "llm": llm_result.get("provider") if isinstance(llm_result, dict) else None,
    }


def create_shadow_instance_from_candidate(
    *,
    active_instance_id: str,
    family_id: str | None = None,
    candidate_preset_id: str | None = None,
    candidate_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    active_instance = read_instance(active_instance_id)
    if active_instance["type"] != "paper":
        raise ValueError("Shadow instances can only be cloned from a paper active instance.")

    family = family_for_instance(active_instance_id)
    target_family_id = str(family_id or (family.get("id") if isinstance(family, dict) else "")).strip() or None

    preset: dict[str, Any]
    if str(candidate_preset_id or "").strip():
        preset = read_prompt_preset(str(candidate_preset_id).strip(), active_instance_id)
    else:
        if not isinstance(candidate_payload, dict):
            raise ValueError("Candidate preset id or candidate payload is required.")
        saved = persist_candidate_preset(active_instance_id, candidate_payload)
        preset = saved["preset"]

    shadow_name = f"{active_instance['name']} · SHADOW · {preset['name']}"
    shadow_instance = clone_instance(active_instance_id, "paper", shadow_name)
    shadow_instance_id = shadow_instance["id"]

    # 明确将候选 preset 绑定为 shadow 当前策略，避免仅复制库但未切换激活 prompt。
    write_prompt_settings(
        {
            "name": preset["name"],
            "presetId": preset["id"],
            "klineFeeds": preset["klineFeeds"],
            "decision_logic": preset["decision_logic"],
        },
        shadow_instance_id,
    )
    write_trading_settings(
        {
            "mode": "paper",
            "paperTrading": {"enabled": False},
            "liveTrading": {"enabled": False},
        },
        shadow_instance_id,
    )

    if target_family_id:
        attach_shadow_instance(target_family_id, shadow_instance_id)

    return {
        "instance": read_instance(shadow_instance_id),
        "preset": preset,
        "familyId": target_family_id,
    }
