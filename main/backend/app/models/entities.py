from __future__ import annotations

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    ForeignKey,
    BigInteger,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from pgvector.sqlalchemy import Vector
from sqlalchemy.sql import expression

from .base import Base, BigIDMixin


class Source(BigIDMixin, Base):
    __tablename__ = "sources"

    name = Column(String(255), nullable=False)
    kind = Column(String(32), nullable=False)
    base_url = Column(String(1024), nullable=True)
    enabled = Column(Boolean, nullable=False, server_default=expression.true())
    created_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    documents = relationship("Document", back_populates="source")


class Document(BigIDMixin, Base):
    __tablename__ = "documents"

    source_id = Column(BigInteger, ForeignKey("sources.id", ondelete="SET NULL"))
    state = Column(String(8), nullable=True)
    doc_type = Column(String(16), nullable=False)
    title = Column(Text, nullable=True)
    status = Column(String(32), nullable=True)
    publish_date = Column(Date, nullable=True)
    content = Column(Text, nullable=True)
    summary = Column(Text, nullable=True)
    text_hash = Column(String(64), nullable=True, unique=True)
    uri = Column(Text, nullable=True)
    extracted_data = Column(JSONB, nullable=True)
    created_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    source = relationship("Source", back_populates="documents")


class MarketStat(BigIDMixin, Base):
    __tablename__ = "market_stats"
    __table_args__ = (UniqueConstraint("state", "game", "date", name="uq_market_state_game_date"),)

    state = Column(String(8), nullable=False)
    game = Column(String(32), nullable=True)
    date = Column(Date, nullable=False)
    sales_volume = Column(Numeric(18, 2), nullable=True)
    revenue = Column(Numeric(18, 2), nullable=True)
    revenue_estimated = Column(Numeric(18, 2), nullable=True)
    jackpot = Column(Numeric(18, 2), nullable=True)
    ticket_price = Column(Numeric(10, 2), nullable=True)
    draw_number = Column(String(32), nullable=True)
    yoy = Column(Numeric(10, 4), nullable=True)
    mom = Column(Numeric(10, 4), nullable=True)
    source_name = Column(String(128), nullable=True)
    source_uri = Column(Text, nullable=True)
    extra = Column(JSONB, nullable=True)
    created_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ConfigState(BigIDMixin, Base):
    __tablename__ = "config_states"

    state_name = Column(String(32), nullable=False, unique=True)
    enabled = Column(Boolean, nullable=False, server_default=expression.true())


class Embedding(BigIDMixin, Base):
    __tablename__ = "embeddings"

    object_id = Column(BigInteger, nullable=False)
    object_type = Column(String(32), nullable=False)
    modality = Column(String(16), nullable=False)
    vector = Column(Vector(3072), nullable=False)
    dim = Column(Integer, nullable=False, server_default="3072")
    provider = Column(String(32), nullable=False, server_default="openai")
    model = Column(String(128), nullable=False, server_default="text-embedding-3-large")
    created_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class EtlJobRun(BigIDMixin, Base):
    __tablename__ = "etl_job_runs"

    job_type = Column(String(16), nullable=False)
    params = Column(JSONB, nullable=True)
    status = Column(String(16), nullable=False, server_default="queued")
    started_at = Column(DateTime(timezone=True), nullable=True)
    finished_at = Column(DateTime(timezone=True), nullable=True)
    error = Column(Text, nullable=True)


class SearchHistory(BigIDMixin, Base):
    __tablename__ = "search_history"
    __table_args__ = (UniqueConstraint("topic", name="uq_search_history_topic"),)

    topic = Column(String(255), nullable=False)
    last_search_time = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class LlmServiceConfig(BigIDMixin, Base):
    __tablename__ = "llm_service_configs"
    __table_args__ = (UniqueConstraint("service_name", name="uq_llm_service_config_service_name"),)

    service_name = Column(String(64), nullable=False, unique=True)
    description = Column(Text, nullable=True)
    system_prompt = Column(Text, nullable=True)
    user_prompt_template = Column(Text, nullable=True)
    model = Column(String(128), nullable=True)
    temperature = Column(Numeric(3, 2), nullable=True)
    max_tokens = Column(Integer, nullable=True)
    top_p = Column(Numeric(5, 4), nullable=True)
    presence_penalty = Column(Numeric(5, 4), nullable=True)
    frequency_penalty = Column(Numeric(5, 4), nullable=True)
    enabled = Column(Boolean, nullable=False, server_default=expression.true())
    created_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class Topic(BigIDMixin, Base):
    __tablename__ = "topics"
    __table_args__ = (UniqueConstraint("topic_name", name="uq_topic_topic_name"),)

    topic_name = Column(String(128), nullable=False, unique=True)
    domains = Column(JSONB, nullable=False)  # List of domains: macro, industry, commodity, ecom, social
    languages = Column(JSONB, nullable=False)  # List of languages: zh, en
    keywords_seed = Column(JSONB, nullable=True)  # List of seed keywords
    subreddits = Column(JSONB, nullable=True)  # List of default subreddits for social domain
    enabled = Column(Boolean, nullable=False, server_default=expression.true())
    description = Column(Text, nullable=True)
    created_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class Project(BigIDMixin, Base):
    __tablename__ = "projects"
    __table_args__ = (
        UniqueConstraint("project_key", name="uq_projects_project_key"),
        UniqueConstraint("schema_name", name="uq_projects_schema_name"),
    )

    project_key = Column(String(64), nullable=False, unique=True)
    name = Column(String(255), nullable=False)
    schema_name = Column(String(128), nullable=False, unique=True)
    enabled = Column(Boolean, nullable=False, server_default=expression.true())
    is_active = Column(Boolean, nullable=False, server_default=expression.false())
    created_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class ProjectSyncState(BigIDMixin, Base):
    __tablename__ = "project_sync_state"
    __table_args__ = (
        UniqueConstraint("project_key", "object_name", name="uq_project_sync_state_object"),
    )

    project_key = Column(String(64), nullable=False)
    object_name = Column(String(64), nullable=False)
    cursor_value = Column(String(255), nullable=True)
    updated_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class SharedIngestChannel(BigIDMixin, Base):
    __tablename__ = "shared_ingest_channels"
    __table_args__ = (UniqueConstraint("channel_key", name="uq_shared_ingest_channel_key"),)

    channel_key = Column(String(128), nullable=False, unique=True)
    name = Column(String(255), nullable=False)
    kind = Column(String(64), nullable=False)
    provider = Column(String(64), nullable=False)
    description = Column(Text, nullable=True)
    credential_refs = Column(JSONB, nullable=True)
    default_params = Column(JSONB, nullable=True)
    param_schema = Column(JSONB, nullable=True)
    extends_channel_key = Column(String(128), nullable=True)
    enabled = Column(Boolean, nullable=False, server_default=expression.true())
    extra = Column(JSONB, nullable=True)
    created_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class SharedSourceLibraryItem(BigIDMixin, Base):
    __tablename__ = "shared_source_library_items"
    __table_args__ = (UniqueConstraint("item_key", name="uq_shared_source_library_item_key"),)

    item_key = Column(String(128), nullable=False, unique=True)
    name = Column(String(255), nullable=False)
    channel_key = Column(String(128), nullable=False)
    description = Column(Text, nullable=True)
    params = Column(JSONB, nullable=True)
    tags = Column(JSONB, nullable=True)
    schedule = Column(String(128), nullable=True)
    extends_item_key = Column(String(128), nullable=True)
    enabled = Column(Boolean, nullable=False, server_default=expression.true())
    extra = Column(JSONB, nullable=True)
    created_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class IngestChannel(BigIDMixin, Base):
    __tablename__ = "ingest_channels"
    __table_args__ = (UniqueConstraint("channel_key", name="uq_ingest_channel_key"),)

    channel_key = Column(String(128), nullable=False, unique=True)
    name = Column(String(255), nullable=False)
    kind = Column(String(64), nullable=False)
    provider = Column(String(64), nullable=False)
    description = Column(Text, nullable=True)
    credential_refs = Column(JSONB, nullable=True)
    default_params = Column(JSONB, nullable=True)
    param_schema = Column(JSONB, nullable=True)
    extends_channel_key = Column(String(128), nullable=True)
    enabled = Column(Boolean, nullable=False, server_default=expression.true())
    extra = Column(JSONB, nullable=True)
    created_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class SourceLibraryItem(BigIDMixin, Base):
    __tablename__ = "source_library_items"
    __table_args__ = (UniqueConstraint("item_key", name="uq_source_library_item_key"),)

    item_key = Column(String(128), nullable=False, unique=True)
    name = Column(String(255), nullable=False)
    channel_key = Column(String(128), nullable=False)
    description = Column(Text, nullable=True)
    params = Column(JSONB, nullable=True)
    tags = Column(JSONB, nullable=True)
    schedule = Column(String(128), nullable=True)
    extends_item_key = Column(String(128), nullable=True)
    enabled = Column(Boolean, nullable=False, server_default=expression.true())
    extra = Column(JSONB, nullable=True)
    created_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class MarketMetricPoint(BigIDMixin, Base):
    __tablename__ = "market_metric_points"
    __table_args__ = (
        UniqueConstraint("metric_key", "date", "source_uri", name="uq_metric_key_date_source"),
    )

    metric_key = Column(String(128), nullable=False)
    date = Column(Date, nullable=False)
    value = Column(Numeric(18, 6), nullable=False)
    unit = Column(String(32), nullable=True)
    currency = Column(String(16), nullable=True)
    source_name = Column(String(128), nullable=True)
    source_uri = Column(Text, nullable=True)
    extra = Column(JSONB, nullable=True)
    created_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class Product(BigIDMixin, Base):
    __tablename__ = "products"
    __table_args__ = (UniqueConstraint("name", "source_uri", name="uq_product_name_source"),)

    name = Column(String(255), nullable=False)
    category = Column(String(64), nullable=True)
    source_name = Column(String(128), nullable=True)
    source_uri = Column(Text, nullable=True)
    selector_hint = Column(Text, nullable=True)
    currency = Column(String(16), nullable=True)
    enabled = Column(Boolean, nullable=False, server_default=expression.true())
    extra = Column(JSONB, nullable=True)
    created_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class PriceObservation(BigIDMixin, Base):
    __tablename__ = "price_observations"
    __table_args__ = (
        UniqueConstraint("product_id", "captured_at", name="uq_price_product_captured_at"),
    )

    product_id = Column(BigInteger, ForeignKey("products.id", ondelete="CASCADE"), nullable=False)
    captured_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    price = Column(Numeric(18, 6), nullable=False)
    currency = Column(String(16), nullable=True)
    availability = Column(String(32), nullable=True)
    source_uri = Column(Text, nullable=True)
    extra = Column(JSONB, nullable=True)
    created_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class SharedResourcePoolUrl(BigIDMixin, Base):
    """Shared pool (总库) URL storage in public schema."""

    __tablename__ = "shared_resource_pool_urls"
    __table_args__ = (
        UniqueConstraint("url", name="uq_shared_resource_pool_urls_url"),
        {"schema": "public"},
    )

    url = Column(Text, nullable=False)
    domain = Column(String(255), nullable=True)
    source = Column(String(32), nullable=False)
    source_ref = Column(JSONB, nullable=True)
    created_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ResourcePoolUrl(BigIDMixin, Base):
    """Project pool (子项目库) URL storage in project schema."""

    __tablename__ = "resource_pool_urls"
    __table_args__ = (UniqueConstraint("url", name="uq_resource_pool_urls_url"),)

    url = Column(Text, nullable=False)
    domain = Column(String(255), nullable=True)
    source = Column(String(32), nullable=False)
    source_ref = Column(JSONB, nullable=True)
    project_key = Column(String(64), nullable=True)
    created_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ResourcePoolCaptureConfig(BigIDMixin, Base):
    """Capture config: which job_types to capture URLs for, scope, enabled."""

    __tablename__ = "resource_pool_capture_config"
    __table_args__ = (
        UniqueConstraint("project_key", name="uq_resource_pool_capture_config_project"),
        {"schema": "public"},
    )

    project_key = Column(String(64), nullable=False)
    scope = Column(String(16), nullable=False, server_default="project")
    job_types = Column(JSONB, nullable=False)
    enabled = Column(Boolean, nullable=False, server_default=expression.true())
    created_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class SharedResourcePoolSiteEntry(BigIDMixin, Base):
    """Shared pool (总库) site entry storage in public schema."""

    __tablename__ = "shared_resource_pool_site_entries"
    __table_args__ = (
        UniqueConstraint("site_url", name="uq_shared_resource_pool_site_entries_site_url"),
        {"schema": "public"},
    )

    site_url = Column(Text, nullable=False)
    domain = Column(String(255), nullable=True)
    entry_type = Column(String(32), nullable=False, server_default="domain_root")
    template = Column(Text, nullable=True)
    name = Column(String(255), nullable=True)
    capabilities = Column(JSONB, nullable=True)
    source = Column(String(32), nullable=False, server_default="manual")
    source_ref = Column(JSONB, nullable=True)
    tags = Column(JSONB, nullable=True)
    enabled = Column(Boolean, nullable=False, server_default=expression.true())
    extra = Column(JSONB, nullable=True)
    created_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class ResourcePoolSiteEntry(BigIDMixin, Base):
    """Project pool (子项目库) site entry storage in project schema."""

    __tablename__ = "resource_pool_site_entries"
    __table_args__ = (
        UniqueConstraint("site_url", name="uq_resource_pool_site_entries_site_url"),
    )

    site_url = Column(Text, nullable=False)
    domain = Column(String(255), nullable=True)
    entry_type = Column(String(32), nullable=False, server_default="domain_root")
    template = Column(Text, nullable=True)
    name = Column(String(255), nullable=True)
    capabilities = Column(JSONB, nullable=True)
    source = Column(String(32), nullable=False, server_default="manual")
    source_ref = Column(JSONB, nullable=True)
    tags = Column(JSONB, nullable=True)
    enabled = Column(Boolean, nullable=False, server_default=expression.true())
    project_key = Column(String(64), nullable=True)
    extra = Column(JSONB, nullable=True)
    created_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class IngestConfig(Base):
    """Project ingest config: structure/schedule configs keyed by project_key + config_key."""

    __tablename__ = "ingest_config"
    __table_args__ = (
        {"schema": "public"},
    )

    project_key = Column(String(64), primary_key=True, nullable=False)
    config_key = Column(String(128), primary_key=True, nullable=False)
    config_type = Column(String(64), nullable=False)
    payload = Column(JSONB, nullable=True)
    created_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
