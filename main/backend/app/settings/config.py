import os
from pathlib import Path
from typing import Optional

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = BACKEND_ROOT.parents[1] if len(BACKEND_ROOT.parents) > 1 else BACKEND_ROOT
ENV_FILE_CANDIDATES = (str(BACKEND_ROOT / ".env"), str(REPO_ROOT / ".env"))

SUCCESSOR_MOUNT_MODES: tuple[str, ...] = ("local_only", "production_registry")
_SUCCESSOR_MOUNT_DEFAULT_PREFIX = "/api/v1/successor-runtime"


def _get_default_database_url() -> str:
    """根据环境自动选择数据库URL"""
    if os.getenv("DOCKER_ENV") == "true" or os.path.exists("/.dockerenv"):
        return "postgresql+psycopg2://postgres:postgres@db:5432/postgres"
    return "postgresql+psycopg2://postgres:postgres@localhost:5432/postgres"


def _get_default_es_url() -> str:
    """根据环境自动选择Elasticsearch URL"""
    if os.getenv("DOCKER_ENV") == "true" or os.path.exists("/.dockerenv"):
        return "http://es:9200"
    return "http://localhost:9200"


def _get_default_redis_url() -> str:
    """根据环境自动选择Redis URL"""
    if os.getenv("DOCKER_ENV") == "true" or os.path.exists("/.dockerenv"):
        return "redis://redis:6379/0"
    return "redis://localhost:6379/0"


class Settings(BaseSettings):
    env: str = Field(default="dev")

    # Database
    database_url: str = Field(default_factory=_get_default_database_url)
    db_pool_size: int = Field(default=10)
    db_pool_max_overflow: int = Field(default=5)
    db_pool_timeout_seconds: int = Field(default=5)
    db_pool_recycle_seconds: int = Field(default=3600)
    db_pool_pre_ping: bool = Field(default=True)
    db_pool_echo: bool = Field(default=False)
    deep_health_pool_gate_enabled: bool = Field(default=True)
    deep_health_pool_exhaustion_ratio: float = Field(default=1.0)
    db_connect_timeout_seconds: int = Field(default=2)
    db_statement_timeout_ms: int = Field(default=30000)
    db_lock_timeout_ms: int = Field(default=5000)
    db_idle_in_transaction_timeout_ms: int = Field(default=120000)
    db_transaction_isolation_level: str = Field(default="read committed")
    db_transaction_retry_attempts: int = Field(default=2)
    db_transaction_retry_base_backoff_ms: int = Field(default=120)
    db_transaction_retry_max_backoff_ms: int = Field(default=1500)
    # Neutral default project key for local bootstrap.
    active_project_key: str = Field(default="default")
    project_key_enforcement_mode: str = Field(default="warn")  # warn | require
    project_key_require_in_non_dev: bool = Field(default=True)
    project_schema_prefix: str = Field(default="project_")
    bootstrap_create_initial_project: bool = Field(default=False)
    enable_legacy_default_to_online_lottery_migration: bool = Field(default=False)
    default_reddit_subreddit: str = Field(default="news")

    # Elasticsearch / Redis
    es_url: str = Field(default_factory=_get_default_es_url)
    redis_url: str = Field(default_factory=_get_default_redis_url)
    celery_log_level: str = Field(default="info")
    celery_concurrency: int = Field(default=3)
    celery_prefetch_multiplier: int = Field(default=2)
    celery_max_tasks_per_child: int = Field(default=100)
    celery_max_memory_per_child: int = Field(default=500000)
    celery_queues: str = Field(default="celery")
    agent_batch_lane_main_queue: str = Field(default="celery")
    agent_batch_lane_subagent_queue: str = Field(default="celery")
    agent_batch_lane_system_queue: str = Field(default="celery")
    skill_loop_guard_enabled: bool = Field(default=True)
    skill_loop_guard_threshold: int = Field(default=10)
    skill_loop_guard_ttl_seconds: int = Field(default=600)
    agent_batch_approval_ttl_seconds: int = Field(default=900)
    graph_structured_async_dispatch_workers: int = Field(default=4)
    graph_node_projection_write_mode: str = Field(default="shadow")  # off | shadow | on
    graph_node_projection_read_mode: str = Field(default="a_only")  # a_only | b_canary | b_primary
    graph_node_projection_canary_projects: str = Field(default="demo_proj")
    ingest_frontdoor_rollout_mode: str = Field(default="on")  # on | off | canary | passthrough
    ingest_frontdoor_canary_projects: str = Field(default="demo_proj")
    url_batch_path_default_mode: str = Field(default="batch_runtime_targets")  # legacy_per_url | batch_runtime_targets
    ingest_enable_strict_gate: bool = Field(default=False)
    ingest_guardrail_rollout_mode: str = Field(default="canary")  # off | canary | on | passthrough
    ingest_guardrail_canary_projects: str = Field(default="demo_proj")
    ingest_low_value_domains: str = Field(default="news.google.com,x.com,actiontoaction.ai")
    ingest_low_value_path_keywords: str = Field(default="/search,/login,/home,/showcase,/topics/,/stargazers,/sitemap")
    ingest_shell_signatures: str = Field(default="window.wiz_progre,var bodyCacheable = true,self.__next_f,errorContainer")
    ingest_min_semantic_len: int = Field(default=500)
    llm_report_enabled: bool = Field(default=True)
    llm_report_gate_mode: str = Field(default="strict")  # off | warn | strict
    llm_report_auto_source_enabled: bool = Field(default=True)
    llm_report_auto_source_target_count: int = Field(default=6)
    workflow_graph_db_store_enabled: bool = Field(default=True)
    workflow_graph_db_store_fail_closed: bool = Field(default=True)
    agent_session_db_store_enabled: bool = Field(default=True)
    agent_session_db_store_fail_closed: bool = Field(default=False)
    agent_runtime_v2_enabled: bool = Field(default=True)
    agent_stream_enabled: bool = Field(default=True)
    agent_batch_as_tool_enabled: bool = Field(default=True)
    agent_session_memory_token_threshold: int = Field(default=4000)
    agent_session_memory_tool_threshold: int = Field(default=12)
    agent_session_memory_event_threshold: int = Field(default=16)
    codex_auth_enabled: bool = Field(default=False)
    codex_auth_tokens: str = Field(default="")
    codex_auth_protected_prefixes: str = Field(
        default=(
            "/api/v1/agent-chat,/api/v1/agent-batch,/api/v1/agent-sessions,"
            "/api/v1/agent-approvals,/api/v1/workflow-graph,/api/v1/skills,"
            + _SUCCESSOR_MOUNT_DEFAULT_PREFIX
        )
    )
    codex_oauth_enabled: bool = Field(default=True)
    codex_oauth_authorize_url: str = Field(default="")
    codex_oauth_token_url: str = Field(default="")
    codex_oauth_client_id: str = Field(default="app_EMoamEEZ73f0CkXaXp7hrann")
    codex_oauth_client_secret: str = Field(default="")
    codex_oauth_scope: str = Field(
        default="openid profile email offline_access api.connectors.read api.connectors.invoke"
    )
    codex_oauth_redirect_uri: str = Field(default="http://localhost:8000/api/v1/codex-auth/callback")
    codex_oauth_frontend_success_url: str = Field(default="/")
    codex_oauth_frontend_error_url: str = Field(default="/")
    codex_oauth_cookie_name: str = Field(default="codex_session")
    codex_oauth_cookie_secure: bool = Field(default=False)
    codex_oauth_state_ttl_seconds: int = Field(default=600)
    codex_oauth_provider: str = Field(default="openai")  # openai | custom
    codex_oauth_originator: str = Field(default="codex_cli_rs")
    codex_oauth_token_sink_enabled: bool = Field(default=True)
    codex_oauth_token_sink_path: str = Field(default="~/.codex/auth_openai.json")
    codex_oauth_token_sink_profile: str = Field(default="default")
    codex_cli_auth_path: str = Field(default="~/.codex/auth.json")
    codex_cli_install_command: str = Field(default="auto")
    codex_cli_llm_fallback_enabled: bool = Field(default=True)
    codex_cli_llm_command: str = Field(default="codex")
    codex_cli_llm_model: str = Field(default="gpt-5.4-mini")
    codex_cli_llm_reasoning_effort: str = Field(default="none")
    codex_cli_llm_ignore_user_config: bool = Field(default=True)
    codex_cli_llm_disabled_features: str = Field(default="plugins,browser_use,memories,multi_agent,apps,tool_search,tool_suggest,chronicle,realtime_conversation")
    codex_cli_llm_workdir: str = Field(default="")
    codex_cli_llm_timeout_seconds: int = Field(default=120)
    codex_cli_llm_persistent_enabled: bool = Field(default=True)
    codex_cli_llm_reuse_thread: bool = Field(default=False)
    codex_cli_llm_persistent_idle_ttl_seconds: int = Field(default=300)
    codex_cli_llm_persistent_start_timeout_seconds: int = Field(default=20)
    agent_chat_turn_decision_timeout_seconds: int = Field(default=8)
    agent_chat_model_answer_timeout_seconds: int = Field(default=45)
    agent_core_e2e_scripted_provider_enabled: bool = Field(default=False)
    agent_core_model_provider: str = Field(
        default="auto"
    )  # auto | openai | codex_cli ; auto preserves current OpenAI-then-Codex behavior

    # LLM providers
    # Allowed values now include: openai | azure | ollama | litellm | local
    llm_provider: str = Field(default="openai")
    openai_api_key: Optional[str] = Field(default=None)
    openai_api_base: Optional[str] = Field(default=None)

    # LiteLLM (OpenAI-compatible proxy) settings
    litellm_api_key: Optional[str] = Field(default=None)
    litellm_api_base: Optional[str] = Field(default=None)

    azure_api_key: Optional[str] = Field(default=None)
    azure_api_base: Optional[str] = Field(default=None)
    azure_api_version: Optional[str] = Field(default="2024-06-01")
    azure_chat_deployment: Optional[str] = Field(default=None)
    azure_embedding_deployment: Optional[str] = Field(default=None)

    ollama_base_url: Optional[str] = Field(default="http://localhost:11434")
    extraction_max_parallel: int = Field(default=8)
    topic_workflow_max_parallel: int = Field(default=8)

    # Local emergency fallback (non-production)
    local_llm_enabled: bool = Field(default=True)

    # External APIs
    legiscan_api_key: Optional[str] = Field(default=None)
    news_api_key: Optional[str] = Field(default=None)
    serpapi_key: Optional[str] = Field(default=None)
    serpstack_key: Optional[str] = Field(default=None)
    serper_api_key: Optional[str] = Field(default=None)
    google_search_api_key: Optional[str] = Field(default=None)
    google_search_cse_id: Optional[str] = Field(default=None)
    azure_search_endpoint: Optional[str] = Field(default="https://lotto.search.windows.net")
    azure_search_key: Optional[str] = Field(default=None)
    azure_search_index_name: Optional[str] = Field(default="index1761979777378")
    magayo_api_key: Optional[str] = Field(default=None)
    lotterydata_api_key: Optional[str] = Field(default=None)
    reddit_client_id: Optional[str] = Field(default=None)
    reddit_client_secret: Optional[str] = Field(default=None)
    reddit_user_agent: Optional[str] = Field(default=None)
    # Twitter/X API credentials
    twitter_api_key: Optional[str] = Field(default=None)
    twitter_api_secret: Optional[str] = Field(default=None)
    twitter_bearer_token: Optional[str] = Field(default=None)
    twitter_access_token: Optional[str] = Field(default=None)
    twitter_access_token_secret: Optional[str] = Field(default=None)
    rapidapi_key: Optional[str] = Field(default=None)

    # Embeddings
    embedding_model: str = Field(default="text-embedding-3-large")
    embedding_dim: int = Field(default=3072)

    # Successor runtime v2 mount (Lane A production wiring).
    # local_only keeps the import-time closed fixture mount; production_registry
    # requires an injected server registry resolver plus codex auth by default.
    successor_mount_mode: str = Field(default="local_only")
    successor_production_requires_auth: bool = Field(default=True)

    @field_validator("successor_mount_mode")
    @classmethod
    def _normalize_successor_mount_mode(cls, value: str) -> str:
        normalized = str(value or "").strip().lower()
        if normalized not in SUCCESSOR_MOUNT_MODES:
            raise ValueError(
                "successor_mount_mode must be one of "
                f"{SUCCESSOR_MOUNT_MODES}; got {value!r}"
            )
        return normalized

    @model_validator(mode="after")
    def _validate_successor_mount(self) -> "Settings":
        validate_successor_mount_mode(
            mount_mode=self.successor_mount_mode,
            production_requires_auth=self.successor_production_requires_auth,
            codex_auth_enabled=self.codex_auth_enabled,
        )
        return self

    # Prefer backend-local .env so runtime reload and settings-manager writes stay consistent.
    model_config = SettingsConfigDict(
        env_file=ENV_FILE_CANDIDATES,
        extra="ignore",
    )


def validate_successor_mount_mode(
    *,
    mount_mode: str | None,
    production_requires_auth: bool | None = None,
    codex_auth_enabled: bool | None = None,
) -> str:
    """Validate successor mount mode and its fail-closed auth coupling.

    Raises ``ValueError`` for unknown modes and for the production registry
    mode running without codex auth when production auth is required.
    """

    normalized = str(mount_mode or "").strip().lower()
    if normalized not in SUCCESSOR_MOUNT_MODES:
        raise ValueError(
            "successor_mount_mode must be one of "
            f"{SUCCESSOR_MOUNT_MODES}; got {mount_mode!r}"
        )
    if (
        normalized == "production_registry"
        and bool(production_requires_auth)
        and not bool(codex_auth_enabled)
    ):
        raise ValueError(
            "successor_mount_mode=production_registry requires "
            "codex_auth_enabled=true when "
            "successor_production_requires_auth=true"
        )
    return normalized


def successor_mount_mode_is_production() -> bool:
    """Return whether the successor mount should use the server registry."""

    return (
        validate_successor_mount_mode(
            mount_mode=getattr(settings, "successor_mount_mode", "local_only"),
            production_requires_auth=getattr(
                settings, "successor_production_requires_auth", True
            ),
            codex_auth_enabled=getattr(settings, "codex_auth_enabled", False),
        )
        == "production_registry"
    )


settings = Settings()


def _normalize_project_key_enforcement_mode(raw_mode: str | None) -> str:
    mode = str(raw_mode or "").strip().lower()
    if mode == "require":
        return "require"
    return "warn"


def get_effective_project_key_enforcement_mode(
    *,
    env_name: str | None = None,
    explicit_mode: str | None = None,
    require_in_non_dev: bool | None = None,
) -> str:
    mode = _normalize_project_key_enforcement_mode(
        explicit_mode if explicit_mode is not None else settings.project_key_enforcement_mode
    )
    if mode == "require":
        return mode

    normalized_env = str(env_name if env_name is not None else settings.env or "dev").strip().lower()
    resolved_require_in_non_dev = (
        bool(require_in_non_dev)
        if require_in_non_dev is not None
        else bool(getattr(settings, "project_key_require_in_non_dev", False))
    )
    if normalized_env != "dev" and resolved_require_in_non_dev:
        return "require"
    return mode


def reload_settings() -> Settings:
    global settings
    new_settings = Settings()
    # Keep object identity so modules that imported `settings` by reference
    # observe refreshed values after reload.
    for field_name in new_settings.model_fields.keys():
        setattr(settings, field_name, getattr(new_settings, field_name))
    return settings
