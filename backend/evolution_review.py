from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from .evolution_registry import read_family_registry
from .instances import instance_paths
from .utils import DATA_DIR, now_iso, num, read_json, write_json


LEGACY_DECISIONS_DIR = DATA_DIR / "trading-agent" / "decisions"
REVIEWS_DIR = DATA_DIR / "evolution" / "reviews"


def _parse_ts(value: Any) -> float:
    if not value:
        return 0.0
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp()
    except Exception:
        return 0.0


def _decisions_dir(instance_id: str | None = None) -> Path:
    if instance_id:
        return instance_paths(instance_id)["decisions_dir"]
    return LEGACY_DECISIONS_DIR


def _family_instance_ids(family_id: str) -> list[str]:
    target = str(family_id or "").strip()
    if not target:
        return []
    registry = read_family_registry()
    family = next((item for item in registry.get("families", []) if item.get("id") == target), None)
    if not isinstance(family, dict):
        return []
    result: list[str] = []
    for value in [family.get("activeInstanceId"), *(family.get("shadowInstanceIds") or [])]:
        instance_id = str(value or "").strip()
        if instance_id and instance_id not in result:
            result.append(instance_id)
    return result


def _read_instance_decisions(instance_id: str, limit: int) -> list[dict[str, Any]]:
    root = _decisions_dir(instance_id)
    if not root.exists():
        return []
    rows: list[dict[str, Any]] = []
    for day_dir in sorted(root.iterdir()):
        if not day_dir.is_dir():
            continue
        for path in sorted(day_dir.glob("*.json")):
            payload = read_json(path, {})
            if not isinstance(payload, dict):
                continue
            ts = _parse_ts(payload.get("finishedAt") or payload.get("startedAt"))
            if ts <= 0:
                continue
            rows.append({"ts": ts, "payload": payload, "path": path})
    rows.sort(key=lambda item: item["ts"])
    return [item["payload"] for item in rows[-limit:]]


def load_family_decisions(
    *,
    instance_id: str | None = None,
    family_id: str | None = None,
    limit: int = 500,
) -> list[dict[str, Any]]:
    if instance_id:
        instance_ids = [str(instance_id).strip()]
    elif family_id:
        instance_ids = _family_instance_ids(str(family_id))
    else:
        return []

    rows: list[dict[str, Any]] = []
    for current_id in instance_ids:
        for payload in _read_instance_decisions(current_id, limit):
            row_instance_id = str(payload.get("instanceId") or payload.get("strategyMeta", {}).get("instanceId") or current_id).strip()
            row_family_id = str(payload.get("familyId") or payload.get("strategyMeta", {}).get("familyId") or "").strip() or None
            if instance_id and row_instance_id != str(instance_id).strip():
                continue
            if family_id and row_family_id != str(family_id).strip():
                continue
            rows.append(
                {
                    **payload,
                    "instanceId": row_instance_id,
                    "familyId": row_family_id,
                }
            )
    rows.sort(key=lambda item: _parse_ts(item.get("finishedAt") or item.get("startedAt")))
    return rows[-limit:]


def build_review_metrics(
    decisions: list[dict[str, Any]],
    *,
    min_decisions: int = 20,
    min_closed_trades: int = 12,
    confidence_floor: float = 70.0,
) -> dict[str, Any]:
    decision_count = len(decisions)
    closed_trades = 0
    realized_pnl = 0.0
    max_drawdown_pct = 0.0
    discipline_violations = 0
    low_confidence_entries = 0

    for decision in decisions:
        drawdown_pct = num((decision.get("accountAfter") or {}).get("drawdownPct")) or 0.0
        max_drawdown_pct = max(max_drawdown_pct, drawdown_pct)

        warnings = decision.get("warnings") if isinstance(decision.get("warnings"), list) else []
        discipline_violations += len([item for item in warnings if str(item or "").strip()])

        actions = decision.get("actions") if isinstance(decision.get("actions"), list) else []
        for action in actions:
            if not isinstance(action, dict):
                continue
            action_type = str(action.get("type") or "").strip().lower()
            if action_type in {"close", "reduce"}:
                closed_trades += 1
                realized_pnl += num(action.get("realizedPnlUsd")) or 0.0
                continue
            if action_type != "open":
                continue
            confidence = num(action.get("confidence"))
            if confidence is not None and confidence < confidence_floor:
                low_confidence_entries += 1
            if num(action.get("stopLoss")) is None or num(action.get("takeProfit")) is None:
                discipline_violations += 1

    expectancy = realized_pnl / closed_trades if closed_trades else 0.0
    discipline_penalty = round(discipline_violations * 2.0, 2)
    low_confidence_penalty = round(low_confidence_entries * 1.5, 2)
    return {
        "decisions": decision_count,
        "closedTrades": closed_trades,
        "realizedPnl": round(realized_pnl, 2),
        "expectancy": round(expectancy, 2),
        "maxDrawdownPct": round(max_drawdown_pct, 2),
        "disciplinePenalty": discipline_penalty,
        "lowConfidencePenalty": low_confidence_penalty,
        "insufficientSample": decision_count < int(min_decisions) or closed_trades < int(min_closed_trades),
    }


def score_review(metrics: dict[str, Any]) -> dict[str, Any]:
    scorecard = {
        "realizedPnl": round(num(metrics.get("realizedPnl")) or 0.0, 2),
        "expectancy": round(num(metrics.get("expectancy")) or 0.0, 2),
        "maxDrawdownPct": round(num(metrics.get("maxDrawdownPct")) or 0.0, 2),
        "disciplinePenalty": round(num(metrics.get("disciplinePenalty")) or 0.0, 2),
        "lowConfidencePenalty": round(num(metrics.get("lowConfidencePenalty")) or 0.0, 2),
    }
    final_score = round(
        scorecard["realizedPnl"]
        + scorecard["expectancy"] * 2.0
        - scorecard["maxDrawdownPct"] * 1.5
        - scorecard["disciplinePenalty"]
        - scorecard["lowConfidencePenalty"],
        2,
    )
    return {
        **metrics,
        "scorecard": scorecard,
        "finalScore": final_score,
    }


def write_review_report(
    *,
    instance_id: str | None = None,
    family_id: str | None = None,
    limit: int = 500,
    min_decisions: int = 20,
    min_closed_trades: int = 12,
) -> dict[str, Any]:
    decisions = load_family_decisions(instance_id=instance_id, family_id=family_id, limit=limit)
    metrics = build_review_metrics(
        decisions,
        min_decisions=min_decisions,
        min_closed_trades=min_closed_trades,
    )
    scored = score_review(metrics)
    generated_at = now_iso()
    slug = str(family_id or instance_id or "adhoc").strip() or "adhoc"
    review_id = f"review-{slug}-{generated_at.replace(':', '').replace('-', '').replace('Z', 'Z').replace('.', '')}"
    report = {
        "id": review_id,
        "generatedAt": generated_at,
        "familyId": str(family_id or "").strip() or None,
        "instanceId": str(instance_id or "").strip() or None,
        "window": {
            "from": decisions[0].get("startedAt") if decisions else None,
            "to": (decisions[-1].get("finishedAt") or decisions[-1].get("startedAt")) if decisions else None,
        },
        "sample": {
            "decisions": scored["decisions"],
            "closedTrades": scored["closedTrades"],
        },
        "decisions": scored["decisions"],
        "closedTrades": scored["closedTrades"],
        "scorecard": scored["scorecard"],
        "finalScore": scored["finalScore"],
        "insufficientSample": scored["insufficientSample"],
        "decisionIds": [str(item.get("id") or "") for item in decisions if str(item.get("id") or "").strip()],
    }
    write_json(REVIEWS_DIR / f"{review_id}.json", report)
    return report
