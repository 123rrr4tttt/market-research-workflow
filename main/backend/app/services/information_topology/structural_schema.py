"""Cross-module structural attributes for topology creation and read models.

Module profiles own domain-specific attributes. This overlay reserves a small
set of structural fields that every creator may use without extending each
profile separately. Legacy field names remain source-owned; read models derive
the structural fields instead of rewriting persisted data.
"""
from __future__ import annotations

from dataclasses import replace
from typing import Any, Mapping, TypeAlias

from .profiles import AttributeRule, TypeRule


STRUCTURAL_ATTRIBUTE_TYPES = {
    "content_name": "string",
    "content_summary": "string",
    "content_order": "integer",
    "structural_role": "string",
    "source_uri": "string",
    "source_status": "string",
}

TypeRules: TypeAlias = Mapping[str, TypeRule]

# Derived read-model field for the domain relation token a profile declares.
# It is never an authored attribute and never becomes part of a persisted state.
RELATION_TOKEN_FIELD = "relation_token"
# Derived read-model field naming the source → target endpoint roles of a
# relation type, so readers can realize it as one edge without module knowledge.
RELATION_AXIS_FIELD = "relation_axis"

CONTENT_NAME_FIELDS: Mapping[str, tuple[str, ...]] = {
    "material": ("title",),
    "judgment": ("judgment",),
    "evidence": ("name", "original_excerpt"),
    "clue": ("name",),
    "attempt": ("result_note", "actual_query"),
    "domain_vocabulary": ("name",),
    "outline_root": ("name",),
    "section": ("title", "name"),
    "method": ("name",),
}


def _text(value: Any) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    return value.strip()


def _first_text(attributes: Mapping[str, Any], fields: tuple[str, ...]) -> str | None:
    for field in fields:
        value = _text(attributes.get(field))
        if value is not None:
            return value
    return None


def derive_structural_attributes(type_id: str, attributes: Mapping[str, Any]) -> dict[str, Any]:
    """Project legacy/module fields into the common structural read fields."""
    common = dict(attributes)
    content_name = _first_text(attributes, CONTENT_NAME_FIELDS.get(type_id, ("name", "title", "judgment", "description")))
    if content_name is not None:
        common.setdefault("content_name", content_name)

    summary = _first_text(attributes, ("content_summary", "summary", "inference_note", "description"))
    if summary is not None:
        common.setdefault("content_summary", summary)

    source_uri = _first_text(attributes, ("source_uri", "uri", "url"))
    if source_uri is not None:
        common.setdefault("source_uri", source_uri)

    source_status = _first_text(attributes, ("source_status", "reference_status", "status"))
    if source_status is not None:
        common.setdefault("source_status", source_status)

    if type(attributes.get("content_order", attributes.get("order"))) is int:
        common.setdefault("content_order", int(attributes.get("content_order", attributes.get("order"))))
    if type(attributes.get("structural_role")) is str:
        common["structural_role"] = attributes["structural_role"]
    return common


def with_structural_attributes(types: TypeRules) -> dict[str, TypeRule]:
    """Attach the optional structural overlay to one explicitly bound profile.

    The core profile validator remains closed. A project/module adapter calls
    this helper only when its semantic contract opts into the structural fields.
    """
    overlay = {
        name: AttributeRule(value_type)
        for name, value_type in STRUCTURAL_ATTRIBUTE_TYPES.items()
    }
    return {
        type_id: replace(rule, attributes={**rule.attributes, **overlay})
        for type_id, rule in types.items()
    }


def declared_relation_token(type_rule: TypeRule | None, attributes: Mapping[str, Any]) -> str | None:
    """Read the profile-declared domain relation token from one element's attributes."""
    attribute_name = getattr(type_rule, "relation_token_attribute", None)
    if not attribute_name:
        return None
    return _text(attributes.get(attribute_name))


def derive_read_model_attributes(
    type_id: str,
    attributes: Mapping[str, Any],
    type_rule: TypeRule | None = None,
) -> dict[str, Any]:
    """Derive the reader-facing attribute view for one element in a read model.

    Structural fields stay derived: they are projections over source-owned
    attributes, so readers may consume them without writing them back.
    """
    common = derive_structural_attributes(type_id, attributes)
    token = declared_relation_token(type_rule, attributes)
    if token is not None:
        common[RELATION_TOKEN_FIELD] = token
    declared_role = getattr(type_rule, "structural_role", None)
    if declared_role and _text(attributes.get("structural_role")) is None:
        common["structural_role"] = declared_role
    if common.get("structural_role") == "relation":
        axis = getattr(type_rule, "relation_axis", None)
        if axis:
            common[RELATION_AXIS_FIELD] = [str(role) for role in axis]
    return common
