# LLM Prompts (Version Controlled)

Prompt configs stored here are synced to each project's `llm_service_configs` table on app startup.

## Structure

- **default.yaml** – Base configs for all projects. Required.
- **{project_key}.yaml** – Optional overrides per project (e.g. `demo_proj.yaml`).
  - Merged with default by `service_name`; project entries override default.

## Sync (YAML → DB)

Runs automatically on FastAPI startup (after project schemas are ready).
Also run manually:

```bash
python scripts/sync_llm_prompts.py
```

## Export (DB → YAML)

Export prompts from database to YAML files (backup or version-control):

```bash
# Export all projects
python scripts/export_llm_prompts.py

# Export single project
python scripts/export_llm_prompts.py demo_proj
```

## Fields

| Field | Type | Description |
|-------|------|-------------|
| service_name | str | Unique key (e.g. `policy_classification`, `social_keyword_generation`) |
| description | str | Human-readable description |
| system_prompt | str | System message (optional) |
| user_prompt_template | str | User message template with `{variable}` placeholders |
| model | str \| null | Model name, null = use default |
| temperature | float | 0–1 |
| max_tokens | int | Max output tokens |
| enabled | bool | Whether config is active |
