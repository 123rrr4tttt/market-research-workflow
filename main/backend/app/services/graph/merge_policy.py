from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
import json
import logging
from typing import Any

from ...settings.config import settings
from ..ingest_config import get_config as get_ingest_config


logger = logging.getLogger(__name__)
MERGE_POLICY_SELECTOR_CONFIG_KEY = "graph_node_merge_policy_selector"


@dataclass(frozen=True)
class MergePolicyResult:
    """Structured decision output for merge policy execution."""

    decision: str
    confidence: float
    reason: str
    evidence: dict[str, Any] = field(default_factory=dict)


class MergePolicy(ABC):
    """Base contract for pluggable merge decision policies."""

    name: str

    @abstractmethod
    def evaluate(
        self,
        *,
        query_text: str,
        candidates: list[dict[str, Any]],
    ) -> MergePolicyResult:
        raise NotImplementedError


class DefaultMergePolicy(MergePolicy):
    """Safe baseline policy before integrating external LLM providers."""

    name = "default"

    def evaluate(
        self,
        *,
        query_text: str,
        candidates: list[dict[str, Any]],
    ) -> MergePolicyResult:
        candidate_ids: list[int] = []
        for row in candidates:
            try:
                candidate_ids.append(int(row.get("node_id")))
            except Exception:
                continue

        evidence = {
            "query_text": query_text,
            "candidate_count": len(candidates),
            "candidate_ids": candidate_ids,
            "merges": [],
        }

        if len(candidate_ids) < 2:
            return MergePolicyResult(
                decision="skip",
                confidence=1.0,
                reason="Insufficient merge-eligible candidates.",
                evidence=evidence,
            )

        return MergePolicyResult(
            decision="skip",
            confidence=0.3,
            reason="Default policy is a non-LLM placeholder and emits no merge clusters.",
            evidence=evidence,
        )


DEFAULT_MERGE_POLICY = DefaultMergePolicy.name
_MERGE_POLICIES: dict[str, MergePolicy] = {
    DefaultMergePolicy.name: DefaultMergePolicy(),
}


def register_merge_policy(policy: MergePolicy, *, override: bool = False) -> None:
    key = getattr(policy, "name", "").strip().lower()
    if not key:
        raise ValueError("policy.name must be non-empty")
    if (not override) and key in _MERGE_POLICIES:
        raise ValueError(f"merge policy '{key}' already registered")
    _MERGE_POLICIES[key] = policy


def get_merge_policy(name: str | None = None) -> MergePolicy:
    key = (name or DEFAULT_MERGE_POLICY).strip().lower()
    policy = _MERGE_POLICIES.get(key)
    if policy is None:
        raise KeyError(f"unknown merge policy: {key}")
    return policy


def _normalize_selector_part(value: str | None, *, wildcard_default: str = "*") -> str:
    text = str(value or "").strip().lower()
    return text or wildcard_default


def _parse_policy_selector(raw_json: str | None) -> dict[tuple[str, str], str]:
    text = str(raw_json or "").strip()
    if not text:
        return {}
    try:
        payload = json.loads(text)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Invalid graph_node_merge_policy_selector_json, fallback to default policy: %s", exc)
        return {}

    if not isinstance(payload, dict):
        logger.warning("graph_node_merge_policy_selector_json must be a JSON object, got %s", type(payload).__name__)
        return {}

    parsed: dict[tuple[str, str], str] = {}
    for project_key, node_mapping in payload.items():
        project_norm = _normalize_selector_part(str(project_key), wildcard_default="*")
        if isinstance(node_mapping, str):
            policy_name = node_mapping.strip().lower()
            if policy_name:
                parsed[(project_norm, "*")] = policy_name
            continue
        if not isinstance(node_mapping, dict):
            continue
        for node_type, policy_name in node_mapping.items():
            if not isinstance(policy_name, str):
                continue
            policy_norm = policy_name.strip().lower()
            if not policy_norm:
                continue
            node_norm = _normalize_selector_part(str(node_type), wildcard_default="*")
            parsed[(project_norm, node_norm)] = policy_norm
    return parsed


def _resolve_policy_name_from_selector(*, project_key: str | None, node_type: str | None) -> str:
    selector = _parse_policy_selector(settings.graph_node_merge_policy_selector_json)
    project_norm = _normalize_selector_part(project_key, wildcard_default="*")
    node_norm = _normalize_selector_part(node_type, wildcard_default="*")
    candidates = (
        (project_norm, node_norm),
        (project_norm, "*"),
        ("*", node_norm),
        ("*", "*"),
    )
    for key in candidates:
        policy_name = selector.get(key)
        if policy_name:
            return policy_name
    return str(settings.graph_node_merge_policy_default or DEFAULT_MERGE_POLICY).strip().lower()


def _extract_policy_from_payload(payload: Any, *, node_type: str) -> str | None:
    if isinstance(payload, str):
        policy = payload.strip().lower()
        return policy or None
    if not isinstance(payload, dict):
        return None
    direct = payload.get(node_type)
    if isinstance(direct, str) and direct.strip():
        return direct.strip().lower()
    wildcard = payload.get("*")
    if isinstance(wildcard, str) and wildcard.strip():
        return wildcard.strip().lower()
    return None


def _resolve_policy_name_from_db(*, project_key: str | None, node_type: str | None) -> str | None:
    if not bool(getattr(settings, "graph_node_merge_policy_selector_db_enabled", True)):
        return None
    node_norm = _normalize_selector_part(node_type, wildcard_default="*")
    project_norm = _normalize_selector_part(project_key, wildcard_default="*")

    try:
        if project_norm != "*":
            project_cfg = get_ingest_config(project_norm, MERGE_POLICY_SELECTOR_CONFIG_KEY)
            if isinstance(project_cfg, dict):
                policy = _extract_policy_from_payload(project_cfg.get("payload"), node_type=node_norm)
                if policy:
                    return policy

        global_cfg = get_ingest_config("*", MERGE_POLICY_SELECTOR_CONFIG_KEY)
        if isinstance(global_cfg, dict):
            policy = _extract_policy_from_payload(global_cfg.get("payload"), node_type=node_norm)
            if policy:
                return policy
    except Exception as exc:  # noqa: BLE001
        logger.warning("failed to read DB merge policy selector, fallback to JSON selector: %s", exc)
        return None
    return None


def select_merge_policy(*, project_key: str | None = None, node_type: str | None = None) -> tuple[MergePolicy, str | None]:
    resolved_name = _resolve_policy_name_from_db(project_key=project_key, node_type=node_type)
    if not resolved_name:
        resolved_name = _resolve_policy_name_from_selector(project_key=project_key, node_type=node_type)
    fallback_reason: str | None = None
    policy = _MERGE_POLICIES.get(resolved_name)
    if policy is None:
        fallback_reason = (
            f"unknown merge policy '{resolved_name}' for project_key='{project_key or '*'}' "
            f"node_type='{node_type or '*'}'; fallback to '{DEFAULT_MERGE_POLICY}'"
        )
        logger.warning(fallback_reason)
        policy = _MERGE_POLICIES[DEFAULT_MERGE_POLICY]
    return policy, fallback_reason


def list_merge_policies() -> list[str]:
    return sorted(_MERGE_POLICIES.keys())
