from __future__ import annotations

from typing import Any


_RELATION_ONTOLOGY: dict[str, dict[str, Any]] = {
    "regulates": {
        "class": "governance",
        "aliases": ["regulate", "监管", "规范", "complies_with", "governs"],
    },
    "changes_rule": {
        "class": "governance",
        "aliases": ["change_rule", "rule_change", "amends", "修订", "变更规则"],
    },
    "announces": {
        "class": "event",
        "aliases": ["announce", "发布", "公布", "declares"],
    },
    "reports_sales": {
        "class": "metric",
        "aliases": ["report_sales", "sales_report", "披露销售"],
    },
    "reports_metric": {
        "class": "metric",
        "aliases": ["report_metric", "披露指标", "公布指标"],
    },
    "affects": {
        "class": "impact",
        "aliases": ["impact", "influences", "影响"],
    },
    "changes_metric": {
        "class": "impact",
        "aliases": ["change_metric", "modifies_metric", "变更指标", "改变指标"],
    },
    "partners_with": {
        "class": "collaboration",
        "aliases": ["partner_with", "cooperates_with", "合作", "allies_with"],
    },
    "depends_on": {
        "class": "dependency",
        "aliases": ["depend_on", "relies_on", "依赖"],
    },
    "uses_component": {
        "class": "composition",
        "aliases": ["use_component", "contains_component", "使用组件", "由...构成"],
    },
    "uses_strategy": {
        "class": "strategy",
        "aliases": ["use_strategy", "adopts_strategy", "采用策略", "执行策略"],
    },
    "supplies": {
        "class": "supply_chain",
        "aliases": ["supply", "provides", "供给", "供货"],
    },
    "distributes": {
        "class": "distribution",
        "aliases": ["distribute", "渠道分发", "分销"],
    },
    "competes_with": {
        "class": "competition",
        "aliases": ["compete_with", "竞争", "rivals"],
    },
    "operates_in": {
        "class": "operation",
        "aliases": ["operate_in", "运营于"],
    },
    "operates_on": {
        "class": "operation",
        "aliases": ["operate_on", "runs_on", "运行于", "运营于平台"],
    },
    "belongs_to": {
        "class": "taxonomy",
        "aliases": ["belong_to", "属于", "分类于"],
    },
    "targets_scenario": {
        "class": "targeting",
        "aliases": ["target_scenario", "面向场景", "targets"],
    },
    "targets_channel": {
        "class": "channel",
        "aliases": ["target_channel", "面向渠道", "通过渠道"],
    },
}

_ALIAS_INDEX: dict[str, str] = {}
for canonical, meta in _RELATION_ONTOLOGY.items():
    _ALIAS_INDEX[canonical] = canonical
    for alias in (meta.get("aliases") or []):
        _ALIAS_INDEX[str(alias)] = canonical


def _sanitize(value: str | None) -> str:
    s = str(value or "").strip().lower()
    s = s.replace("-", "_").replace(" ", "_")
    while "__" in s:
        s = s.replace("__", "_")
    return s


def canonical_predicate(value: str | None) -> str:
    token = _sanitize(value)
    if not token:
        return "unknown"
    return _ALIAS_INDEX.get(token, token)


def predicate_class(value: str | None) -> str:
    canonical = canonical_predicate(value)
    meta = _RELATION_ONTOLOGY.get(canonical, {})
    return str(meta.get("class") or "other")


def relation_annotation(value: str | None) -> dict[str, str]:
    canonical = canonical_predicate(value)
    return {
        "predicate_raw": str(value or ""),
        "predicate_norm": canonical,
        "relation_class": predicate_class(canonical),
    }
