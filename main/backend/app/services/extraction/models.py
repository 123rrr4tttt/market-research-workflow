"""结构化提取的Pydantic模型"""
from __future__ import annotations

from typing import List, Optional
from datetime import date
from pydantic import BaseModel, Field


class PolicyExtracted(BaseModel):
    """政策提取结构"""
    state: Optional[str] = None
    effective_date: Optional[date] = None
    policy_type: Optional[str] = None
    key_points: List[str] = Field(default_factory=list)


class MarketExtracted(BaseModel):
    """市场数据提取结构"""
    state: Optional[str] = None
    game: Optional[str] = None
    report_date: Optional[date] = None
    sales_volume: Optional[float] = None
    revenue: Optional[float] = None
    jackpot: Optional[float] = None
    ticket_price: Optional[float] = None
    draw_number: Optional[str] = None
    yoy_change: Optional[float] = None  # 同比变化百分比
    mom_change: Optional[float] = None  # 环比变化百分比
    key_findings: List[str] = Field(default_factory=list)  # 关键发现


class ExtractedEntity(BaseModel):
    """提取的实体。type 接受任意非空字符串，空字符串的实体在 _payload_to_dict 中过滤，不入图"""
    text: str
    type: str = ""
    span: Optional[List[int]] = None  # [start, end] 可选


class ExtractedRelation(BaseModel):
    """提取的关系。subject/predicate/object 须非空，空字符串的关系在 _payload_to_dict 中过滤，不入图"""
    subject: str
    predicate: str = ""
    object: str
    evidence: str = Field(default="")
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    date: Optional[str] = None  # ISO 日期，可选


class ERPayload(BaseModel):
    """实体-关系提取载荷"""
    entities: List[ExtractedEntity] = Field(max_items=5)
    relations: List[ExtractedRelation] = Field(max_items=3)

