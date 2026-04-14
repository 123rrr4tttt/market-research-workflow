"""关键词生成服务 - 独立模块"""
from __future__ import annotations

import logging
from typing import List, Optional, Dict

from .llm.provider import get_chat_model
from .llm.config_loader import get_llm_config, format_prompt_template, ensure_prompt_has_guidelines
from .ingest.keyword_library import (
    clean_keywords as clean_lottery_keywords,
    store_keywords as store_lottery_keywords,
)
from ..settings.config import settings

logger = logging.getLogger(__name__)

_BILINGUAL_LANG_MODES = {"bi", "bilingual", "zh-en", "zh_en", "both", "multi", "multilingual"}


def _is_bilingual_mode(language: str | None) -> bool:
    return str(language or "").strip().lower() in _BILINGUAL_LANG_MODES


def _social_language_label(language: str) -> str:
    if _is_bilingual_mode(language):
        return "中英文双语（search关键词需同时包含中文与英文；subreddit关键词保持英文）"
    return "英文" if language.lower().startswith("en") else "中文"


def _has_zh(text: str) -> bool:
    return any("\u4e00" <= ch <= "\u9fff" for ch in str(text or ""))


def _has_en(text: str) -> bool:
    return any(("a" <= ch.lower() <= "z") for ch in str(text or ""))


def _ensure_bilingual_search_keywords(
    keywords: List[str],
    topic: str,
    platform: Optional[str],
) -> List[str]:
    if not keywords:
        return keywords
    has_zh = any(_has_zh(k) for k in keywords)
    has_en = any(_has_en(k) for k in keywords)
    if has_zh and has_en:
        return keywords
    supplemental = _get_fallback_keywords(topic, "zh" if not has_zh else "en", platform)
    out = list(keywords)
    for kw in supplemental:
        if kw not in out:
            out.append(kw)
    return out


def generate_social_keywords(
    topic: str, 
    language: str = "zh", 
    platform: Optional[str] = None,
    base_keywords: Optional[List[str]] = None,
    return_combined: bool = True
) -> Dict[str, List[str]] | List[str]:
    """
    为社交平台生成关键词
    
    如果return_combined=True，一次LLM调用生成两种关键词：
    - search_keywords: 用于搜索帖子的关键词
    - subreddit_keywords: 用于发现子论坛的关键词
    
    Args:
        topic: 主题或话题
        language: 语言代码 (zh/en)
        platform: 平台名称 (reddit/twitter等)，可选
        base_keywords: 基础关键词列表（可选），用于生成更多相关关键词
        return_combined: 是否返回合并格式（搜索关键词+子论坛关键词），默认True
        
    Returns:
        如果return_combined=True: 返回字典 {"search_keywords": [...], "subreddit_keywords": [...]}
        如果return_combined=False: 返回搜索关键词列表（向后兼容）
    """
    # 如果没有配置LLM，使用fallback
    if settings.llm_provider == "openai" and not settings.openai_api_key:
        logger.info("generate_social_keywords: using fallback (no LLM key), topic=%s lang=%s platform=%s", 
                   topic, language, platform)
        if return_combined:
            search_kw = clean_lottery_keywords(_get_fallback_keywords(topic, language, platform))
            if platform and search_kw:
                store_lottery_keywords(platform, search_kw)
            subreddit_kw = _get_fallback_subreddit_keywords(topic, base_keywords)
            return {"search_keywords": search_kw, "subreddit_keywords": subreddit_kw}
        fallback_keywords = clean_lottery_keywords(_get_fallback_keywords(topic, language, platform))
        if platform and fallback_keywords:
            store_lottery_keywords(platform, fallback_keywords)
        return fallback_keywords
    
    try:
        # 如果return_combined=True，使用social_keyword_generation配置（已更新为合并格式）
        if return_combined:
            config_name = "social_keyword_generation"
            config = get_llm_config(config_name)
            logger.info(
                "generate_social_keywords: config_name=%s has_config=%s has_template=%s",
                config_name, config is not None, bool(config and config.get("user_prompt_template")),
            )
            if config and config.get("user_prompt_template"):
                from ..project_customization import get_project_customization
                guidelines = get_project_customization().get_social_keyword_guidelines()
                if guidelines:
                    updated = ensure_prompt_has_guidelines(
                        config_name,
                        config.get("user_prompt_template"),
                        guidelines,
                    )
                    if updated:
                        config["user_prompt_template"] = updated
                template_to_use = config.get("user_prompt_template", "")
                
                # 使用合并配置生成两种关键词
                language_str = _social_language_label(language)
                platform_str = f"，适合在{platform}平台" if platform else ""
                base_keywords_str = f"\n基础关键词：{', '.join(base_keywords)}" if base_keywords else ""
                
                logger.info(f"Generating keywords: language={language} -> language_str={language_str}, platform={platform}, topic={topic}")
                
                prompt = format_prompt_template(
                    template_to_use,
                    language=language_str,
                    topic=topic,
                    platform=platform_str,
                    base_keywords=base_keywords_str
                )
                
                logger.debug(f"Formatted prompt (first 400 chars):\n{prompt[:400]}")
                
                model = get_chat_model(
                    model=config.get("model"),
                    temperature=config.get("temperature", 0.5),
                    max_tokens=config.get("max_tokens", 500),
                    top_p=config.get("top_p"),
                    presence_penalty=config.get("presence_penalty"),
                    frequency_penalty=config.get("frequency_penalty"),
                )
                
                response = model.invoke(prompt)
                text = response.content if hasattr(response, "content") else str(response)
                
                logger.debug(f"LLM response text (first 500 chars): {text[:500]}")
                
                # 解析响应，分离两种关键词
                search_keywords: List[str] = []
                subreddit_keywords: List[str] = []
                
                current_section = None
                lines = text.splitlines()
                
                for line in lines:
                    line_original = line
                    line = line.strip()
                    if not line:
                        continue
                    
                    # 检测章节标题（更宽松的匹配，支持中英文）
                    line_lower = line.lower()
                    # 搜索关键词章节标记
                    if ("搜索关键词" in line or "search keyword" in line_lower or 
                        "第一类" in line or "第一" in line or 
                        ("搜索" in line or "search" in line_lower) and ("关键词" in line or "keyword" in line_lower) or
                        line_lower.startswith("search")):
                        current_section = "search"
                        logger.debug(f"Found search section marker: {line}")
                        continue
                    # 子论坛关键词章节标记
                    elif ("子论坛关键词" in line or "subreddit keyword" in line_lower or 
                          "第二类" in line or "第二" in line or 
                          ("子论坛" in line or "subreddit" in line_lower) and ("关键词" in line or "keyword" in line_lower) or
                          line_lower.startswith("subreddit")):
                        current_section = "subreddit"
                        logger.debug(f"Found subreddit section marker: {line}")
                        continue
                    
                    # 清理关键词
                    keyword = line.strip("- •*1234567890. ")
                    if not keyword or len(keyword) < 2:
                        continue
                    
                    # 跳过明显的标题行和元数据行
                    keyword_lower = keyword.lower()
                    if (keyword.endswith("：") or keyword.endswith(":") or
                        keyword.startswith("主题：") or keyword.startswith("主题:") or
                        keyword.startswith("topic:") or keyword.startswith("topic：") or
                        "搜索关键词" in keyword or "search keyword" in keyword_lower or
                        "子论坛关键词" in keyword or "subreddit keyword" in keyword_lower or
                        keyword in ["搜索关键词", "search keywords", "子论坛关键词", "subreddit keywords", "第一类", "第二类"]):
                        continue
                    
                    # 根据章节添加到对应列表
                    if current_section == "search":
                        search_keywords.append(keyword)
                        logger.debug(f"Added search keyword: {keyword}")
                    elif current_section == "subreddit":
                        # 子论坛关键词需要特殊处理：转换为小写、下划线分隔
                        keyword_clean = keyword.lower().strip().replace(" ", "_").replace("-", "_")
                        keyword_clean = "".join(c for c in keyword_clean if c.isalnum() or c == "_")
                        if keyword_clean and len(keyword_clean) > 1:
                            subreddit_keywords.append(keyword_clean)
                            logger.debug(f"Added subreddit keyword: {keyword_clean}")
                    else:
                        # 如果没有明确的章节，尝试根据格式判断
                        # 如果包含下划线或全小写，可能是子论坛关键词
                        if "_" in keyword or (keyword.islower() and len(keyword) > 3):
                            keyword_clean = keyword.lower().strip().replace(" ", "_").replace("-", "_")
                            keyword_clean = "".join(c for c in keyword_clean if c.isalnum() or c == "_")
                            if keyword_clean:
                                subreddit_keywords.append(keyword_clean)
                                logger.debug(f"Auto-detected subreddit keyword: {keyword_clean}")
                        else:
                            search_keywords.append(keyword)
                            logger.debug(f"Auto-detected search keyword: {keyword}")
                
                logger.info(f"Parsed keywords: search={len(search_keywords)}, subreddit={len(subreddit_keywords)}")
                logger.info(f"Search keywords: {search_keywords}")
                logger.info(f"Subreddit keywords: {subreddit_keywords}")
                
                # 如果解析失败，使用fallback
                if not search_keywords and not subreddit_keywords:
                    logger.warning("Failed to parse combined keywords, using fallback")
                    search_kw = clean_lottery_keywords(
                        _get_fallback_keywords(topic, language, platform)
                    )
                    if platform:
                        store_lottery_keywords(platform, search_kw)
                    subreddit_kw = _get_fallback_subreddit_keywords(topic, base_keywords)
                    return {"search_keywords": search_kw, "subreddit_keywords": subreddit_kw}
                
                # 如果某个列表为空，使用fallback补充
                if not search_keywords:
                    logger.warning("No search keywords parsed, using fallback")
                    search_keywords = _get_fallback_keywords(topic, language, platform)
                if not subreddit_keywords:
                    logger.warning("No subreddit keywords parsed, using fallback")
                    subreddit_keywords = _get_fallback_subreddit_keywords(topic, base_keywords)
                
                # 如果提供了基础关键词，也添加到搜索关键词中
                if base_keywords:
                    for kw in base_keywords:
                        if kw not in search_keywords:
                            search_keywords.append(kw)

                raw_search = search_keywords.copy()
                search_keywords = clean_lottery_keywords(search_keywords)
                if not search_keywords:
                    if raw_search:
                        search_keywords = raw_search[:10]
                    elif base_keywords:
                        search_keywords = list(dict.fromkeys(str(k).strip() for k in base_keywords if str(k).strip()))
                    if not search_keywords:
                        search_keywords = clean_lottery_keywords(
                            _get_fallback_keywords(topic, language, platform)
                        ) or ([topic.strip()] if topic.strip() else [])

                if _is_bilingual_mode(language):
                    search_keywords = _ensure_bilingual_search_keywords(search_keywords, topic, platform)

                if platform and search_keywords:
                    store_lottery_keywords(platform, search_keywords)
                    logger.info(
                        "Stored %d social keywords for platform=%s",
                        len(search_keywords),
                        platform,
                    )
                
                result = {
                    "search_keywords": search_keywords[:10],  # 最多10个搜索关键词
                    "subreddit_keywords": subreddit_keywords[:15]  # 最多15个子论坛关键词
                }
                logger.info(
                    "generate_social_keywords: LLM result search_keywords=%s subreddit_keywords=%s topic=%s",
                    result["search_keywords"], result["subreddit_keywords"], topic,
                )
                return result
        
        # 如果return_combined=False，使用原来的逻辑（向后兼容）
        # 优先使用社交平台专用的配置
        config_name = "social_keyword_generation"
        config = get_llm_config(config_name)
        
        # 如果没有社交平台专用配置，使用通用关键词生成配置
        if not config:
            config = get_llm_config("keyword_generation")
        
        if config and config.get("user_prompt_template"):
            from ..project_customization import get_project_customization
            guidelines = get_project_customization().get_social_keyword_guidelines()
            if guidelines:
                updated = ensure_prompt_has_guidelines(
                    config_name,
                    config.get("user_prompt_template"),
                    guidelines,
                )
                if updated:
                    config["user_prompt_template"] = updated
            # 使用配置的提示词
            language_str = _social_language_label(language)
            platform_str = f"，适合在{platform}平台搜索" if platform else ""
            # format_prompt_template 使用 {变量} 格式，直接传递 platform 参数
            template = config["user_prompt_template"]
            # 如果模板中包含 {platform}，直接传递给 format_prompt_template
            if "{platform}" in template:
                prompt = format_prompt_template(
                    template,
                    language=language_str,
                    topic=topic,
                    platform=platform_str
                )
            else:
                # 如果模板中没有 platform 变量，先格式化其他变量
                prompt = format_prompt_template(
                    template,
                    language=language_str,
                    topic=topic
                )
                # 如果提供了平台，追加到提示词末尾
                if platform:
                    prompt = f"{prompt}\n{platform_str}"
            model = get_chat_model(
                model=config.get("model"),
                temperature=config.get("temperature"),
                max_tokens=config.get("max_tokens"),
                top_p=config.get("top_p"),
                presence_penalty=config.get("presence_penalty"),
                frequency_penalty=config.get("frequency_penalty"),
            )
        else:
            # 使用默认提示词（针对社交平台优化）
            language_str = _social_language_label(language)
            platform_hint = f"，适合在{platform}平台搜索" if platform else ""
            from ..project_customization import get_project_customization
            guidelines = get_project_customization().get_social_keyword_guidelines()
            guidelines_str = f"\n{guidelines}" if guidelines else ""
            prompt = (
                f"你是一名社交媒体关键词生成助手。请基于用户主题，生成 3~5 个多样化的{language_str}搜索关键词"
                f"{platform_hint}。"
                f"{guidelines_str}"
                f"\n\n主题：{topic}"
            )
            model = get_chat_model()
        
        response = model.invoke(prompt)
        text = response.content if hasattr(response, "content") else str(response)
        keywords: List[str] = []
        for line in text.splitlines():
            line = line.strip("- •*1234567890. ")
            if line and len(line) > 2:  # 过滤太短的关键词
                keywords.append(line)
        
        if keywords:
            logger.info(
                "generate_social_keywords: raw llm keywords=%s (topic=%s, platform=%s)",
                keywords,
                topic,
                platform,
            )
            cleaned_keywords = clean_lottery_keywords(keywords)
            if not cleaned_keywords:
                logger.warning("No valid lottery keywords after cleaning raw llm output, using fallback")
                cleaned_keywords = clean_lottery_keywords(
                    _get_fallback_keywords(topic, language, platform)
                )
            if platform and cleaned_keywords:
                store_lottery_keywords(platform, cleaned_keywords)
            if cleaned_keywords:
                logger.info(
                    "generate_social_keywords: cleaned llm keywords=%s (topic=%s, platform=%s)",
                    cleaned_keywords,
                    topic,
                    platform,
                )
                return cleaned_keywords[:10]  # 最多返回10个关键词
    except Exception as e:
        logger.warning(
            "generate_social_keywords: LLM failed, fallback to static keywords: %s", e, exc_info=True
        )

    # Fallback without LLM
    logger.info("generate_social_keywords: using static fallback topic=%s", topic)
    if return_combined:
        search_kw = clean_lottery_keywords(_get_fallback_keywords(topic, language, platform))
        if not search_kw and base_keywords:
            search_kw = list(dict.fromkeys(str(k).strip() for k in base_keywords if str(k).strip()))
        if not search_kw:
            search_kw = [topic.strip()] if topic.strip() else []
        if platform and search_kw:
            store_lottery_keywords(platform, search_kw)
        subreddit_kw = _get_fallback_subreddit_keywords(topic, base_keywords)
        logger.info("generate_social_keywords: fallback search_keywords=%s subreddit_keywords=%s", search_kw, subreddit_kw)
        return {"search_keywords": search_kw, "subreddit_keywords": subreddit_kw}
    fallback_keywords = clean_lottery_keywords(_get_fallback_keywords(topic, language, platform))
    if platform and fallback_keywords:
        store_lottery_keywords(platform, fallback_keywords)
    return fallback_keywords


def _get_fallback_keywords(topic: str, language: str, platform: Optional[str] = None) -> List[str]:
    """获取fallback关键词"""
    if _is_bilingual_mode(language):
        zh = _get_fallback_keywords(topic, "zh", platform)
        en = _get_fallback_keywords(topic, "en", platform)
        out: List[str] = []
        for kw in [*zh, *en]:
            if kw not in out:
                out.append(kw)
        return out[:8]

    if language.lower().startswith("en"):
        keywords = [
            topic,
            f"{topic} discussion",
            f"{topic} community",
            f"{topic} experience",
        ]
        if platform == "reddit":
            keywords.extend([
                f"{topic} reddit",
                f"r/{topic.lower().replace(' ', '')}",
            ])
    else:
        keywords = [
            topic,
            f"{topic} 讨论",
            f"{topic} 社区",
            f"{topic} 体验",
        ]
        if platform == "reddit":
            keywords.extend([
                f"{topic} reddit",
            ])
    
    return keywords[:5]  # 最多返回5个


def generate_subreddit_keywords(topic: str, language: str = "en", base_keywords: Optional[List[str]] = None) -> List[str]:
    """
    专门为Reddit子论坛发现生成关键词
    
    这些关键词专门用于发现Reddit子论坛，应该：
    1. 简洁明了，适合作为子论坛名称
    2. 符合Reddit子论坛命名习惯（通常是小写、单词或短语）
    3. 包含主题相关的核心词汇
    4. 可能包含相关的同义词、变体或相关概念
    
    Args:
        topic: 主题或话题
        language: 语言代码 (zh/en)，Reddit子论坛通常使用英文
        base_keywords: 基础关键词列表（可选），用于生成更多相关关键词
        
    Returns:
        子论坛关键词列表
    """
    # Reddit子论坛通常使用英文，如果输入是中文，也需要生成英文关键词
    use_english = language.lower().startswith("en")
    
    # 如果没有配置LLM，使用fallback
    if settings.llm_provider == "openai" and not settings.openai_api_key:
        logger.info("generate_subreddit_keywords: using fallback (no LLM key), topic=%s", topic)
        return _get_fallback_subreddit_keywords(topic, base_keywords)
    
    try:
        # 尝试使用专门的子论坛关键词生成配置
        config_name = "subreddit_keyword_generation"
        config = get_llm_config(config_name)
        
        # 如果没有专门配置，使用社交平台关键词生成配置
        if not config:
            config = get_llm_config("social_keyword_generation")
        
        # 如果还是没有，使用通用关键词生成配置
        if not config:
            config = get_llm_config("keyword_generation")
        
        if config and config.get("user_prompt_template"):
            # 使用配置的提示词
            language_str = "英文" if use_english else "中文"
            base_keywords_str = f"，基础关键词：{', '.join(base_keywords)}" if base_keywords else ""
            
            # 构建提示词
            prompt = format_prompt_template(
                config["user_prompt_template"],
                language=language_str,
                topic=topic,
                base_keywords=base_keywords_str
            )
            
            model = get_chat_model(
                model=config.get("model"),
                temperature=config.get("temperature", 0.7),  # 稍高温度以增加多样性
                max_tokens=config.get("max_tokens"),
                top_p=config.get("top_p"),
                presence_penalty=config.get("presence_penalty"),
                frequency_penalty=config.get("frequency_penalty"),
            )
        else:
            # 使用默认提示词（专门针对Reddit子论坛）
            language_str = "英文" if use_english else "中文"
            base_keywords_str = f"\n基础关键词：{', '.join(base_keywords)}" if base_keywords else ""
            
            prompt = (
                f"你是一名Reddit子论坛关键词生成助手。请基于用户主题，生成 5~10 个适合用于发现Reddit子论坛的{language_str}关键词。\n"
                f"\n要求：\n"
                f"1. 关键词应该简洁明了，适合作为Reddit子论坛名称（通常是小写单词或短语）\n"
                f"2. 包含主题的核心词汇和相关概念\n"
                f"3. 可以包含同义词、变体或相关术语\n"
                f"4. 关键词应该符合Reddit社区命名习惯（避免空格，使用下划线或连字符）\n"
                f"5. 每行一个关键词\n"
                f"\n主题：{topic}"
                f"{base_keywords_str}"
            )
            model = get_chat_model(temperature=0.7)  # 稍高温度以增加多样性
        
        response = model.invoke(prompt)
        text = response.content if hasattr(response, "content") else str(response)
        keywords: List[str] = []
        
        for line in text.splitlines():
            line = line.strip("- •*1234567890. ")
            # 清理关键词：去除空格，转换为小写，替换空格为下划线或连字符
            if line and len(line) > 1:
                # 转换为小写（Reddit子论坛通常是小写）
                line_lower = line.lower().strip()
                # 替换空格为下划线或连字符
                line_clean = line_lower.replace(" ", "_").replace("-", "_")
                # 移除特殊字符，只保留字母、数字和下划线
                line_clean = "".join(c for c in line_clean if c.isalnum() or c == "_")
                if line_clean and len(line_clean) > 1:
                    keywords.append(line_clean)
        
        # 如果提供了基础关键词，也添加到列表中
        if base_keywords:
            for kw in base_keywords:
                kw_clean = kw.lower().strip().replace(" ", "_").replace("-", "_")
                kw_clean = "".join(c for c in kw_clean if c.isalnum() or c == "_")
                if kw_clean and kw_clean not in keywords:
                    keywords.append(kw_clean)
        
        if keywords:
            logger.info("generate_subreddit_keywords: llm keywords=%s (topic=%s)", keywords, topic)
            return keywords[:15]  # 最多返回15个关键词
    except Exception as e:
        logger.warning("generate_subreddit_keywords: llm failed, fallback to static keywords", exc_info=True)
    
    # Fallback without LLM
    return _get_fallback_subreddit_keywords(topic, base_keywords)


def _get_fallback_subreddit_keywords(topic: str, base_keywords: Optional[List[str]] = None) -> List[str]:
    """获取fallback子论坛关键词"""
    keywords = []
    
    # 使用基础关键词（如果提供）
    if base_keywords:
        for kw in base_keywords:
            kw_clean = kw.lower().strip().replace(" ", "_").replace("-", "_")
            kw_clean = "".join(c for c in kw_clean if c.isalnum() or c == "_")
            if kw_clean:
                keywords.append(kw_clean)
    
    # 从主题生成关键词
    topic_clean = topic.lower().strip().replace(" ", "_").replace("-", "_")
    topic_clean = "".join(c for c in topic_clean if c.isalnum() or c == "_")
    if topic_clean and topic_clean not in keywords:
        keywords.append(topic_clean)
    
    # 添加常见变体
    if topic_clean:
        # 单数形式
        if topic_clean.endswith("s") and len(topic_clean) > 1:
            singular = topic_clean[:-1]
            if singular not in keywords:
                keywords.append(singular)
        # 复数形式
        if not topic_clean.endswith("s"):
            plural = topic_clean + "s"
            if plural not in keywords:
                keywords.append(plural)
    
    return keywords[:10]  # 最多返回10个
