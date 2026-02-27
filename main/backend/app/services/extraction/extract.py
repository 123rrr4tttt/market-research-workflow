"""结构化提取模块"""
from __future__ import annotations

import json
import logging
from typing import Optional, Dict, Any

from ..llm.provider import get_chat_model
from ..llm.config_loader import get_llm_config, format_prompt_template
from ...subprojects import get_extraction_adapter
from .models import PolicyExtracted, MarketExtracted, ERPayload
from .json_utils import extract_json_payload
from .numeric import normalize_market_payload


logger = logging.getLogger(__name__)


def _normalize_er_raw(data: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize raw ER data. Filter out entities/relations with empty key fields to avoid corrupting graph."""
    out = dict(data)
    entities = out.get("entities", [])
    normalized_entities = []
    for e in entities:
        if isinstance(e, str):
            t = e.strip()
            if t:
                normalized_entities.append({"text": t, "type": "OTHER"})
        elif isinstance(e, dict):
            text = str(e.get("text", "")).strip()
            etype = str(e.get("type", "")).strip()
            if text and etype:
                normalized_entities.append({"text": text, "type": etype})
        else:
            continue
    out["entities"] = normalized_entities

    relations = out.get("relations", [])
    normalized_relations = []
    for r in relations:
        if isinstance(r, dict):
            rel = dict(r)
            subj = str(rel.get("subject", "")).strip()
            pred = str(rel.get("predicate", "")).strip()
            obj = str(rel.get("object", "")).strip()
            if subj and pred and obj:
                if "confidence" not in rel or rel["confidence"] is None:
                    rel["confidence"] = 0.5
                normalized_relations.append(rel)
    out["relations"] = normalized_relations
    return out


def _payload_to_dict(payload: ERPayload) -> Optional[Dict[str, Any]]:
    """校验并转为dict。过滤空字符串的实体/关系，避免破坏图谱"""
    entities = []
    for e in payload.entities:
        text = (e.text or "").strip()
        etype = (e.type or "").strip()
        if text and etype:
            entities.append({"text": e.text, "type": e.type, "span": e.span})
    relations = []
    for r in payload.relations:
        subj = (r.subject or "").strip()
        pred = (r.predicate or "").strip()
        obj = (r.object or "").strip()
        if subj and pred and obj:
            relations.append({
                "subject": r.subject, "predicate": r.predicate, "object": r.object,
                "evidence": r.evidence, "confidence": r.confidence, "date": r.date,
            })
    return {"entities": entities, "relations": relations}


def extract_policy_info(text: str) -> Optional[Dict[str, Any]]:
    """提取政策结构化信息"""
    if not text or len(text.strip()) < 50:
        return None
    
    try:
        # 尝试从数据库读取配置
        config = get_llm_config("policy_extraction")
        
        # 限制文本长度
        text_snippet = text[:3000]
        
        if config and config.get("user_prompt_template"):
            # 使用配置的提示词
            prompt = format_prompt_template(config["user_prompt_template"], text=text_snippet)
            model = get_chat_model(
                model=config.get("model"),
                temperature=config.get("temperature"),
                max_tokens=config.get("max_tokens"),
                top_p=config.get("top_p"),
                presence_penalty=config.get("presence_penalty"),
                frequency_penalty=config.get("frequency_penalty"),
            )
        else:
            # 使用默认提示词（向后兼容）
            prompt = f"""从以下文本中提取政策的关键信息：

{text_snippet}

请提取：州、生效日期、政策类型、关键要点。请以JSON格式返回，包含以下字段：
- state: 州名（如CA, NY等）
- effective_date: 生效日期（YYYY-MM-DD格式，如果无法确定则为null）
- policy_type: 政策类型（如regulation, bill, announcement等）
- key_points: 关键要点列表（最多5条）
"""
            model = get_chat_model()
        
        # 尝试使用 structured output
        if hasattr(model, 'with_structured_output'):
            try:
                result = model.with_structured_output(PolicyExtracted).invoke(prompt)
                data = result.model_dump()
                # 将date对象转换为字符串，以便JSON序列化
                if data.get("effective_date") and hasattr(data["effective_date"], "isoformat"):
                    data["effective_date"] = data["effective_date"].isoformat()
                return get_extraction_adapter().augment_policy(data)
            except Exception as e:
                logger.warning("extract_policy_info: structured_output failed, fallback to JSON: %s", e)
        
        # Fallback: JSON 模式
        response = model.invoke(prompt + "\n\n请以 JSON 格式返回。")
        content = response.content if hasattr(response, "content") else str(response)
        
        # 尝试解析JSON
        try:
            data = extract_json_payload(content)
            if not data:
                return None
            # 验证并转换为PolicyExtracted格式
            extracted = PolicyExtracted(**data)
            return get_extraction_adapter().augment_policy(extracted.model_dump())
        except (json.JSONDecodeError, Exception) as e:
            logger.warning("extract_policy_info: JSON parse failed: %s", e)
            return None
            
    except Exception as e:
        logger.warning("extract_policy_info: extraction failed: %s", e, exc_info=True)
        return None


def extract_entities_relations(text: str) -> Optional[Dict[str, Any]]:
    """提取实体和关系"""
    if not text or len(text.strip()) < 50:
        return None
    
    try:
        # 尝试从数据库读取配置
        config = get_llm_config("entities_relations_extraction")
        
        text_snippet = text[:3000]
        
        if config and config.get("user_prompt_template"):
            # 使用配置的提示词
            prompt = format_prompt_template(config["user_prompt_template"], text=text_snippet)
            model = get_chat_model(
                model=config.get("model"),
                temperature=config.get("temperature"),
                max_tokens=config.get("max_tokens"),
                top_p=config.get("top_p"),
                presence_penalty=config.get("presence_penalty"),
                frequency_penalty=config.get("frequency_penalty"),
            )
        else:
            # 使用默认提示词（向后兼容）
            prompt = (
                "Extract up to five entities and up to three relations that are directly related to lottery policies or lottery markets from the text below.\n"
                "All returned values must be in English.\n"
                "Each entity requires fields: text (English), type (one of ORG, LOC, PERSON, AGENCY, LAW, GAME), and optional span.\n"
                "Each relation requires fields: subject (entity text), predicate (one of regulates, affects, announces, changes_rule, reports_sales), object (entity text), evidence (string), confidence (number between 0 and 1), and optional date (ISO).\n"
                "Return JSON strictly matching the schema {\"entities\": [...], \"relations\": [...]} without extra commentary.\n\n"
                f"Text:\n{text_snippet}"
            )
            model = get_chat_model()
        
        if hasattr(model, "with_structured_output"):
            try:
                result = model.with_structured_output(ERPayload).invoke(prompt)
                payload = ERPayload.model_validate(result.model_dump())
                validated = _payload_to_dict(payload)
                if not validated:
                    return None
                return validated
            except Exception as e:
                logger.warning("extract_entities_relations: structured_output failed: %s", e)
        
        # Fallback
        response = model.invoke(prompt + "\n\nReturn the answer strictly in the JSON schema described above.")
        content = response.content if hasattr(response, "content") else str(response)
        
        try:
            data = extract_json_payload(content)
            if not data:
                return None
            data = _normalize_er_raw(data)
            extracted = ERPayload(**data)
            validated = _payload_to_dict(extracted)
            if not validated:
                return None
            return validated
        except (json.JSONDecodeError, Exception) as e:
            logger.warning("extract_entities_relations: JSON parse failed: %s", e)
            return None
            
    except Exception as e:
        logger.warning("extract_entities_relations: extraction failed: %s", e, exc_info=True)
        return None


def extract_market_info(text: str) -> Optional[Dict[str, Any]]:
    """提取市场数据结构化信息"""
    if not text or len(text.strip()) < 50:
        return None
    
    try:
        # 尝试从数据库读取配置
        config = get_llm_config("market_info_extraction")
        
        # 限制文本长度
        text_snippet = text[:3000]
        
        if config and config.get("user_prompt_template"):
            # 使用配置的提示词
            prompt = format_prompt_template(config["user_prompt_template"], text=text_snippet)
            model = get_chat_model(
                model=config.get("model"),
                temperature=config.get("temperature"),
                max_tokens=config.get("max_tokens"),
                top_p=config.get("top_p"),
                presence_penalty=config.get("presence_penalty"),
                frequency_penalty=config.get("frequency_penalty"),
            )
        else:
            # 使用默认提示词（向后兼容）
            prompt = f"""Extract key lottery market data information from the following text:

{text_snippet}

Extract the following fields and return in JSON format. All text values must be in English:
- state: State code (e.g., CA, NY)
- game: Game type (e.g., Powerball, Mega Millions)
- report_date: Report date (YYYY-MM-DD format, null if unavailable)
- sales_volume: Sales volume (number, null if unavailable)
- revenue: Revenue (number, null if unavailable)
- jackpot: Jackpot amount (number, null if unavailable)
- ticket_price: Ticket price (number, null if unavailable)
- draw_number: Draw numbers (string, null if unavailable)
- yoy_change: Year-over-year change percentage (number, null if unavailable)
- mom_change: Month-over-month change percentage (number, null if unavailable)
- key_findings: List of key findings (up to 5 items, all must be in English)
"""
            model = get_chat_model()
        
        # 尝试使用 structured output
        if hasattr(model, "with_structured_output"):
            try:
                result = model.with_structured_output(MarketExtracted).invoke(prompt)
                data = result.model_dump()
                # 将date对象转换为字符串，以便JSON序列化
                if data.get("report_date") and hasattr(data["report_date"], "isoformat"):
                    data["report_date"] = data["report_date"].isoformat()
                # 确保key_findings中的文本都是英文
                if "key_findings" in data and isinstance(data["key_findings"], list):
                    data["key_findings"] = [str(item) for item in data["key_findings"]]
                try:
                    data, quality = normalize_market_payload(data, scope="lottery.market")
                    data["numeric_quality"] = quality
                except Exception as e:
                    logger.warning("extract_market_info: market normalization failed (structured): %s", e)
                return get_extraction_adapter().augment_market(data)
            except Exception as e:
                logger.warning("extract_market_info: structured_output failed, fallback to JSON: %s", e)
        
        # Fallback: JSON 模式
        response = model.invoke(prompt + "\n\nReturn the result in JSON format. All text values must be in English.")
        content = response.content if hasattr(response, "content") else str(response)
        
        # 尝试解析JSON
        try:
            data = extract_json_payload(content)
            if not data:
                return None
            # 验证并转换为MarketExtracted格式
            extracted = MarketExtracted(**data)
            data = extracted.model_dump()
            # 转换日期
            if data.get("report_date") and hasattr(data["report_date"], "isoformat"):
                data["report_date"] = data["report_date"].isoformat()
            # 确保key_findings中的文本都是英文
            if "key_findings" in data and isinstance(data["key_findings"], list):
                data["key_findings"] = [str(item) for item in data["key_findings"]]
            try:
                data, quality = normalize_market_payload(data, scope="lottery.market")
                data["numeric_quality"] = quality
            except Exception as e:
                logger.warning("extract_market_info: market normalization failed (json fallback): %s", e)
            return get_extraction_adapter().augment_market(data)
        except (json.JSONDecodeError, Exception) as e:
            logger.warning("extract_market_info: JSON parse failed: %s", e)
            return None
            
    except Exception as e:
        logger.warning("extract_market_info: extraction failed: %s", e, exc_info=True)
        return None
