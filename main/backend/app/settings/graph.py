"""图谱构建配置"""
from __future__ import annotations

from typing import Dict, Set, Optional

# 停用词配置（按语言）
STOPWORDS: Dict[str, Set[str]] = {
    "en": {
        "the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for", "of", "with",
        "by", "from", "as", "is", "was", "are", "were", "been", "be", "have", "has", "had",
        "do", "does", "did", "will", "would", "should", "could", "may", "might", "must",
        "can", "this", "that", "these", "those", "i", "you", "he", "she", "it", "we", "they",
        "http", "https", "www", "com", "rt", "reddit", "subreddit", "u/", "r/",
    },
    "zh": {
        "的", "了", "在", "是", "我", "有", "和", "就", "不", "人", "都", "一", "一个",
        "上", "也", "很", "到", "说", "要", "去", "你", "会", "着", "没有", "看", "好",
        "自己", "这", "http", "https", "www", "com",
    }
}

# 共现窗口大小（0表示整帖共现，>0表示滑动窗口）
COOCCUR_WINDOW: int = 0

# 是否使用TF-IDF计算边权重
USE_TFIDF: bool = True

# 时间衰减参数（天数，None表示不使用时间衰减）
TIME_DECAY_TAU_DAYS: Optional[int] = None

# 每个帖子最多保留的关键词数量
MAX_KEYWORDS_PER_POST: int = 10

# 关键词ID生成规则：sha1(lower(text)+lang)
# 实体ID生成规则：kb_id or sha1(canonical_name+type)

