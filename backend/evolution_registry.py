from __future__ import annotations

from pathlib import Path
from typing import Any

from .utils import DATA_DIR, now_iso, read_json, write_json


EVOLUTION_DIR = DATA_DIR / "evolution"
FAMILY_REGISTRY_PATH = EVOLUTION_DIR / "registry.json"
PROMOTION_LOG_PATH = EVOLUTION_DIR / "promotions.json"


def _default_registry_payload() -> dict[str, Any]:
    return {
        "version": 1,
        "updatedAt": now_iso(),
        "families": [],
    }


def _default_promotion_payload() -> dict[str, Any]:
    return {
        "version": 1,
        "updatedAt": now_iso(),
        "records": [],
    }


def _normalize_family(item: dict[str, Any]) -> dict[str, Any]:
    family_id = str(item.get("id") or "").strip()
    if not family_id:
        raise ValueError("Family id is required.")
    created_at = str(item.get("createdAt") or now_iso())
    updated_at = str(item.get("updatedAt") or created_at)
    shadow_ids: list[str] = []
    for value in item.get("shadowInstanceIds", []):
        shadow_id = str(value or "").strip()
        if shadow_id and shadow_id not in shadow_ids:
            shadow_ids.append(shadow_id)
    return {
        "id": family_id,
        "name": str(item.get("name") or family_id),
        "activeInstanceId": str(item.get("activeInstanceId") or "").strip(),
        "shadowInstanceIds": shadow_ids,
        "currentPresetId": item.get("currentPresetId"),
        "createdAt": created_at,
        "updatedAt": updated_at,
    }


def _normalize_promotion(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(item.get("id") or f"promotion-{now_iso()}"),
        "familyId": str(item.get("familyId") or "").strip(),
        "fromInstanceId": str(item.get("fromInstanceId") or "").strip(),
        "toInstanceId": str(item.get("toInstanceId") or "").strip(),
        "reason": str(item.get("reason") or "manual"),
        "scoreDelta": item.get("scoreDelta"),
        "approvedAt": str(item.get("approvedAt") or now_iso()),
        "auto": bool(item.get("auto")),
    }


def read_family_registry() -> dict[str, Any]:
    payload = read_json(FAMILY_REGISTRY_PATH, None)
    if not isinstance(payload, dict):
        payload = _default_registry_payload()
        write_json(FAMILY_REGISTRY_PATH, payload)
    families: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for item in payload.get("families", []):
        if not isinstance(item, dict):
            continue
        try:
            normalized = _normalize_family(item)
        except Exception:
            continue
        if normalized["id"] in seen_ids:
            continue
        seen_ids.add(normalized["id"])
        families.append(normalized)
    return {
        "version": int(payload.get("version") or 1),
        "updatedAt": str(payload.get("updatedAt") or now_iso()),
        "families": families,
    }


def write_family_registry(payload: dict[str, Any]) -> dict[str, Any]:
    families = payload.get("families") if isinstance(payload.get("families"), list) else []
    normalized = [_normalize_family(item) for item in families if isinstance(item, dict)]
    next_payload = {
        "version": int(payload.get("version") or 1),
        "updatedAt": now_iso(),
        "families": normalized,
    }
    write_json(FAMILY_REGISTRY_PATH, next_payload)
    return next_payload


def read_promotion_log() -> dict[str, Any]:
    payload = read_json(PROMOTION_LOG_PATH, None)
    if not isinstance(payload, dict):
        payload = _default_promotion_payload()
        write_json(PROMOTION_LOG_PATH, payload)
    records = payload.get("records") if isinstance(payload.get("records"), list) else []
    normalized = [_normalize_promotion(item) for item in records if isinstance(item, dict)]
    return {
        "version": int(payload.get("version") or 1),
        "updatedAt": str(payload.get("updatedAt") or now_iso()),
        "records": normalized,
    }


def write_promotion_log(payload: dict[str, Any]) -> dict[str, Any]:
    records = payload.get("records") if isinstance(payload.get("records"), list) else []
    normalized = [_normalize_promotion(item) for item in records if isinstance(item, dict)]
    next_payload = {
        "version": int(payload.get("version") or 1),
        "updatedAt": now_iso(),
        "records": normalized,
    }
    write_json(PROMOTION_LOG_PATH, next_payload)
    return next_payload


def _family_index(families: list[dict[str, Any]], family_id: str) -> int:
    target = str(family_id or "").strip()
    for index, family in enumerate(families):
        if family["id"] == target:
            return index
    raise ValueError(f"Family not found: {target}")


def family_for_instance(instance_id: str | None) -> dict[str, Any] | None:
    target = str(instance_id or "").strip()
    if not target:
        return None
    registry = read_family_registry()
    for family in registry["families"]:
        if family.get("activeInstanceId") == target:
            return family
        shadow_ids = family.get("shadowInstanceIds") if isinstance(family.get("shadowInstanceIds"), list) else []
        if target in shadow_ids:
            return family
    return None


def create_family(
    family_id: str,
    name: str,
    active_instance_id: str,
    current_preset_id: str | None = None,
) -> dict[str, Any]:
    registry = read_family_registry()
    target = str(family_id or "").strip()
    if any(item["id"] == target for item in registry["families"]):
        raise ValueError(f"Family already exists: {target}")
    family = _normalize_family(
        {
            "id": target,
            "name": name,
            "activeInstanceId": active_instance_id,
            "shadowInstanceIds": [],
            "currentPresetId": current_preset_id,
            "createdAt": now_iso(),
            "updatedAt": now_iso(),
        }
    )
    registry["families"].append(family)
    write_family_registry(registry)
    return family


def attach_shadow_instance(family_id: str, shadow_instance_id: str) -> dict[str, Any]:
    registry = read_family_registry()
    index = _family_index(registry["families"], family_id)
    family = dict(registry["families"][index])
    shadow_id = str(shadow_instance_id or "").strip()
    shadow_ids = [item for item in family["shadowInstanceIds"] if item]
    if shadow_id and shadow_id not in shadow_ids:
        shadow_ids.append(shadow_id)
    family["shadowInstanceIds"] = shadow_ids
    family["updatedAt"] = now_iso()
    registry["families"][index] = _normalize_family(family)
    write_family_registry(registry)
    return registry["families"][index]


def record_promotion(
    family_id: str,
    from_instance_id: str,
    to_instance_id: str,
    reason: str,
    score_delta: float | None = None,
    auto: bool = False,
    current_preset_id: str | None = None,
) -> dict[str, Any]:
    registry = read_family_registry()
    index = _family_index(registry["families"], family_id)
    family = dict(registry["families"][index])
    next_active_id = str(to_instance_id or "").strip()
    previous_active_id = str(family.get("activeInstanceId") or from_instance_id or "").strip()
    shadow_ids = [
        str(item or "").strip()
        for item in family.get("shadowInstanceIds", [])
        if str(item or "").strip() and str(item or "").strip() != next_active_id
    ]
    if previous_active_id and previous_active_id != next_active_id and previous_active_id not in shadow_ids:
        shadow_ids.append(previous_active_id)
    family["activeInstanceId"] = next_active_id
    family["shadowInstanceIds"] = shadow_ids
    if current_preset_id is not None:
        family["currentPresetId"] = str(current_preset_id or "").strip() or None
    family["updatedAt"] = now_iso()
    registry["families"][index] = _normalize_family(family)
    write_family_registry(registry)

    log_payload = read_promotion_log()
    record = _normalize_promotion(
        {
            "familyId": family_id,
            "fromInstanceId": from_instance_id,
            "toInstanceId": to_instance_id,
            "reason": reason,
            "scoreDelta": score_delta,
            "approvedAt": now_iso(),
            "auto": auto,
        }
    )
    log_payload["records"].append(record)
    write_promotion_log(log_payload)
    return record
