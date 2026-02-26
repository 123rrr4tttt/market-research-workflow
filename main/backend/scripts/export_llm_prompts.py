"""
Export LLM prompts from database to YAML files.

Reads each project's llm_service_configs table and writes to llm_prompts/{project_key}.yaml.
Use to backup or version-control prompts that were configured in the DB.
"""
from __future__ import annotations

import sys
from decimal import Decimal
from pathlib import Path

backend_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_dir))

import yaml
from sqlalchemy import text

from app.models.base import engine

PROMPTS_DIR = backend_dir / "llm_prompts"


def _row_to_config(row) -> dict:
    """Convert DB row to YAML-serializable dict."""
    def _val(v):
        if v is None:
            return None
        if isinstance(v, Decimal):
            return float(v)
        if isinstance(v, bool):
            return v
        return str(v) if v else None

    r = row._mapping if hasattr(row, "_mapping") else row
    return {
        "service_name": r["service_name"],
        "description": _val(r.get("description")),
        "system_prompt": _val(r.get("system_prompt")),
        "user_prompt_template": _val(r.get("user_prompt_template")),
        "model": _val(r.get("model")),
        "temperature": _val(r.get("temperature")),
        "max_tokens": r.get("max_tokens"),
        "top_p": _val(r.get("top_p")),
        "presence_penalty": _val(r.get("presence_penalty")),
        "frequency_penalty": _val(r.get("frequency_penalty")),
        "enabled": bool(r.get("enabled", True)),
    }


def export_project(project_key: str, schema_name: str) -> int:
    """Export one project's configs to YAML. Returns count."""
    with engine.connect() as conn:
        conn.execute(text("SET search_path TO public"))
        conn.execute(text(f'SET search_path TO "{schema_name}"'))
        result = conn.execute(
            text("""
                SELECT service_name, description, system_prompt, user_prompt_template,
                       model, temperature, max_tokens, top_p, presence_penalty, frequency_penalty, enabled
                FROM llm_service_configs
                ORDER BY service_name
            """)
        )
        rows = result.fetchall()

    if not rows:
        return 0

    # Build configs list (rows are Row objects with named columns)
    configs = []
    for r in rows:
        configs.append(_row_to_config(r))

    out_path = PROMPTS_DIR / f"{project_key}.yaml"
    PROMPTS_DIR.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        yaml.dump(
            configs,
            f,
            allow_unicode=True,
            default_flow_style=False,
            sort_keys=False,
            width=120,
        )
    print(f"  [{project_key}] exported {len(configs)} configs -> {out_path.name}")
    return len(configs)


def export_prompts(project_key: str | None = None) -> int:
    """
    Export prompts for all enabled projects (or single project if project_key given).
    Returns total configs exported.
    """
    with engine.connect() as conn:
        conn.execute(text("SET search_path TO public"))
        if project_key:
            result = conn.execute(
                text("""
                    SELECT project_key, schema_name FROM public.projects
                    WHERE enabled = true AND project_key = :pk
                """),
                {"pk": project_key.strip().lower()},
            )
        else:
            result = conn.execute(
                text("SELECT project_key, schema_name FROM public.projects WHERE enabled = true")
            )
        rows = result.fetchall()

    total = 0
    for pk, schema_name in rows:
        if not schema_name:
            continue
        n = export_project(pk, schema_name)
        total += n
    return total


def main() -> int:
    project_key = sys.argv[1] if len(sys.argv) > 1 else None
    print("📤 Exporting LLM prompts from database to llm_prompts/...")
    n = export_prompts(project_key)
    print(f"✅ Export done ({n} configs)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
