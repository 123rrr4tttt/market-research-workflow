from __future__ import annotations

import re
from typing import Any

from ...contracts.schemas.writing import TemplateValidateRequest, TemplateValidateResponse

_VAR_RE = re.compile(r"\{\{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\}\}")
_BUILTIN_TEMPLATES = [
    {
        "template_key": "market_weekly",
        "label": "Market Weekly",
        "description": "Weekly market report template",
        "template_content": "# Executive Summary\n\n## Signals\n\n- {{market_signal}}\n",
    },
    {
        "template_key": "policy_brief",
        "label": "Policy Brief",
        "description": "Policy brief template",
        "template_content": "# Policy Brief\n\n## Regulation\n\n- {{policy_subject}}\n",
    },
    {
        "template_key": "company_deep_dive",
        "label": "Company Deep Dive",
        "description": "Company research template",
        "template_content": "# Company Deep Dive\n\n## Company Snapshot\n\n- {{company_name}}\n",
    },
]


def _extract_template_variables(template_text: str) -> list[str]:
    seen: list[str] = []
    for match in _VAR_RE.findall(template_text):
        if match not in seen:
            seen.append(match)
    return seen


def validate_template_payload(payload: TemplateValidateRequest) -> TemplateValidateResponse:
    template_text = str(payload.template_content or "").strip()
    template_key = str(payload.template_key or payload.template_id or "").strip()
    errors: list[str] = []
    warnings: list[str] = []

    if not template_key and not template_text:
        errors.append("template_key_or_content_required")
    if template_text and len(template_text) < 16:
        warnings.append("template_content_too_short")

    variables = _extract_template_variables(template_text)
    missing_vars = [name for name in variables if name not in payload.sample_payload]
    if missing_vars:
        if payload.strict:
            errors.extend([f"missing_variable:{name}" for name in missing_vars])
        else:
            warnings.extend([f"missing_variable:{name}" for name in missing_vars])

    return TemplateValidateResponse(
        valid=len(errors) == 0,
        errors=sorted(set(errors)),
        warnings=sorted(set(warnings)),
        normalized_template={
            "template_key": template_key or None,
            "template_content": template_text,
            "variables": variables,
        },
        rules={
            "template_key_or_content_required": True,
            "variables_must_be_bound_in_strict_mode": True,
        },
        observability={
            "variable_count": len(variables),
            "missing_variables": missing_vars,
            "strict": payload.strict,
        },
    )


def list_templates() -> list[dict[str, Any]]:
    return [dict(item) for item in _BUILTIN_TEMPLATES]
