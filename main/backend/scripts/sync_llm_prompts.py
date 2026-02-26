"""
Sync LLM prompts from YAML files into database.

Reads llm_prompts/default.yaml and optional llm_prompts/{project_key}.yaml,
then upserts into each enabled project's llm_service_configs table.

Run after DB migration, e.g. from docker-entrypoint.sh.
"""
from __future__ import annotations

import sys
from pathlib import Path

backend_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_dir))

import yaml
from sqlalchemy import text

from app.models.base import SessionLocal, engine
from app.services.projects.context import bind_schema


PROMPTS_DIR = backend_dir / "llm_prompts"
DEFAULT_FILE = PROMPTS_DIR / "default.yaml"


def _load_yaml(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data if isinstance(data, list) else []


def _get_configs_for_project(project_key: str) -> list[dict]:
    """Load configs: default + project overrides (merge by service_name)."""
    default = _load_yaml(DEFAULT_FILE)
    project_file = PROMPTS_DIR / f"{project_key}.yaml"
    overrides = _load_yaml(project_file)

    by_name = {c["service_name"]: c for c in default}
    for c in overrides:
        by_name[c["service_name"]] = c
    return list(by_name.values())


def _config_to_row(c: dict) -> dict:
    """Convert YAML config to DB row (null handling)."""
    return {
        "service_name": c["service_name"],
        "description": c.get("description"),
        "system_prompt": c.get("system_prompt"),
        "user_prompt_template": c.get("user_prompt_template"),
        "model": c.get("model"),
        "temperature": c.get("temperature"),
        "max_tokens": c.get("max_tokens"),
        "top_p": c.get("top_p"),
        "presence_penalty": c.get("presence_penalty"),
        "frequency_penalty": c.get("frequency_penalty"),
        "enabled": c.get("enabled", True),
    }


def _upsert_config(conn, schema: str, row: dict) -> None:
    """Upsert one config into schema.llm_service_configs."""
    conn.execute(text(f'SET search_path TO "{schema}"'))
    sn = row["service_name"]
    # Use raw SQL to avoid ORM schema binding; table exists in tenant schema
    conn.execute(
        text("""
            INSERT INTO llm_service_configs (
                service_name, description, system_prompt, user_prompt_template,
                model, temperature, max_tokens, top_p, presence_penalty, frequency_penalty, enabled
            ) VALUES (
                :service_name, :description, :system_prompt, :user_prompt_template,
                :model, :temperature, :max_tokens, :top_p, :presence_penalty, :frequency_penalty, :enabled
            )
            ON CONFLICT (service_name) DO UPDATE SET
                description = EXCLUDED.description,
                system_prompt = EXCLUDED.system_prompt,
                user_prompt_template = EXCLUDED.user_prompt_template,
                model = EXCLUDED.model,
                temperature = EXCLUDED.temperature,
                max_tokens = EXCLUDED.max_tokens,
                top_p = EXCLUDED.top_p,
                presence_penalty = EXCLUDED.presence_penalty,
                frequency_penalty = EXCLUDED.frequency_penalty,
                enabled = EXCLUDED.enabled,
                updated_at = now()
        """),
        {
            "service_name": sn,
            "description": row.get("description"),
            "system_prompt": row.get("system_prompt"),
            "user_prompt_template": row.get("user_prompt_template"),
            "model": row.get("model"),
            "temperature": row.get("temperature"),
            "max_tokens": row.get("max_tokens"),
            "top_p": row.get("top_p"),
            "presence_penalty": row.get("presence_penalty"),
            "frequency_penalty": row.get("frequency_penalty"),
            "enabled": row.get("enabled", True),
        },
    )


def sync_prompts() -> int:
    """Sync prompts for all enabled projects. Returns count of configs upserted."""
    with engine.begin() as conn:
        conn.execute(text("SET search_path TO public"))
        rows = conn.execute(
            text("SELECT project_key, schema_name FROM public.projects WHERE enabled = true")
        ).fetchall()

    total = 0
    for project_key, schema_name in rows:
        if not schema_name:
            continue
        configs = _get_configs_for_project(project_key)
        if not configs:
            continue
        with engine.begin() as conn:
            for c in configs:
                row = _config_to_row(c)
                _upsert_config(conn, schema_name, row)
                total += 1
        print(f"  [{project_key}] synced {len(configs)} LLM configs")
    return total


def main() -> int:
    if not DEFAULT_FILE.exists():
        print(f"⚠️  {DEFAULT_FILE} not found, skip sync")
        return 0
    print("📝 Syncing LLM prompts from llm_prompts/ to database...")
    n = sync_prompts()
    print(f"✅ LLM prompts sync done ({n} configs)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
