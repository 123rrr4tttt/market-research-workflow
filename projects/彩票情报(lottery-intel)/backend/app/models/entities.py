from __future__ import annotations

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    ForeignKey,
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

from .base import Base


class Source(Base):
    __tablename__ = "sources"

    id = Column(Integer, primary_key=True)
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


class Document(Base):
    __tablename__ = "documents"

    id = Column(Integer, primary_key=True)
    source_id = Column(Integer, ForeignKey("sources.id", ondelete="SET NULL"))
    state = Column(String(8), nullable=True)
    doc_type = Column(String(16), nullable=False)
    title = Column(Text, nullable=True)
    status = Column(String(32), nullable=True)
    publish_date = Column(Date, nullable=True)
    content = Column(Text, nullable=True)
    summary = Column(Text, nullable=True)
    text_hash = Column(String(64), nullable=True, unique=True)
    uri = Column(Text, nullable=True)
    created_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    source = relationship("Source", back_populates="documents")


class MarketStat(Base):
    __tablename__ = "market_stats"
    __table_args__ = (UniqueConstraint("state", "game", "date", name="uq_market_state_game_date"),)

    id = Column(Integer, primary_key=True)
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


class ConfigState(Base):
    __tablename__ = "config_states"

    id = Column(Integer, primary_key=True)
    state_name = Column(String(32), nullable=False, unique=True)
    enabled = Column(Boolean, nullable=False, server_default=expression.true())


class Embedding(Base):
    __tablename__ = "embeddings"

    id = Column(Integer, primary_key=True)
    object_id = Column(Integer, nullable=False)
    object_type = Column(String(32), nullable=False)
    modality = Column(String(16), nullable=False)
    vector = Column(Vector(3072), nullable=False)
    dim = Column(Integer, nullable=False, server_default="3072")
    provider = Column(String(32), nullable=False, server_default="openai")
    model = Column(String(128), nullable=False, server_default="text-embedding-3-large")
    created_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class EtlJobRun(Base):
    __tablename__ = "etl_job_runs"

    id = Column(Integer, primary_key=True)
    job_type = Column(String(16), nullable=False)
    params = Column(JSONB, nullable=True)
    status = Column(String(16), nullable=False, server_default="queued")
    started_at = Column(DateTime(timezone=True), nullable=True)
    finished_at = Column(DateTime(timezone=True), nullable=True)
    error = Column(Text, nullable=True)

