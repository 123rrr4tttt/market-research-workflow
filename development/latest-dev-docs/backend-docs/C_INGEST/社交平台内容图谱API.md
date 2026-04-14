# 社交平台内容图谱API文档

> 最后更新：2026-02 | 文档索引：`docs/README.md`

## 概述

本文档描述了社交平台内容图谱的构建和导出功能。内容图谱聚焦于关键词、关键实体、主题与情感倾向，构建可查询的图结构。

## 架构

### 目录结构

```
app/services/graph/
├── __init__.py
├── models.py              # 数据模型定义
├── builder.py             # 核心构图逻辑
├── exporter.py            # 导出功能
└── adapters/
    ├── __init__.py        # 适配器注册
    └── reddit.py          # Reddit平台适配器

app/settings/
└── graph.py               # 图谱配置

scripts/
└── export_content_graph.py  # CLI导出脚本
```

## 数据模型

### NormalizedSocialPost

规范化社交媒体帖子结构（跨平台统一）：

```python
@dataclass
class NormalizedSocialPost:
    doc_id: int
    uri: str
    platform: str
    text: str
    username: Optional[str] = None
    subreddit: Optional[str] = None
    publish_date: Optional[datetime] = None
    createdAt: Optional[datetime] = None
    state: Optional[str] = None
    sentiment_orientation: Optional[str] = None
    sentiment_tags: List[str] = []
    key_phrases: List[str] = []
    emotion_words: List[str] = []
    topic: Optional[str] = None
    entities: List[Dict] = []
    keywords: List[str] = []
```

### Graph

图谱数据结构：

```python
@dataclass
class Graph:
    nodes: Dict[str, GraphNode]  # key: node_id, value: GraphNode
    edges: List[GraphEdge]
    schema_version: str = "v1"
```

## 节点类型

- **Post**: 帖子/文档节点
  - ID: `doc_id`（文档ID）
  - 属性: `uri`, `platform`, `publish_date`, `created_at`, `state`, `sentiment_orientation`

- **Keyword**: 关键词节点
  - ID: `sha1(lower(text)+lang)`
  - 属性: `text`

- **Entity**: 实体节点
  - ID: `kb_id`（优先）或 `sha1(canonical_name+type)`
  - 属性: `canonical_name`, `type`, `kb_id`

- **Topic**: 主题节点
  - ID: `label`（小写）
  - 属性: `label`

- **SentimentTag**: 情感标签节点
  - ID: `label`（小写）
  - 属性: `label`

- **User**: 用户节点
  - ID: `platform:username`
  - 属性: `platform`, `username`

- **Subreddit**: 子论坛节点
  - ID: `name`（小写）
  - 属性: `name`

## 边类型

- **MENTIONS_KEYWORD**: Post → Keyword
  - 属性: `weight`（TF-IDF或频次）

- **MENTIONS_ENTITY**: Post → Entity
  - 属性: `positions`, `confidence`

- **HAS_TOPIC**: Post → Topic

- **HAS_SENTIMENT**: Post → SentimentTag
  - 属性: `orientation`（positive/negative/neutral）

- **AUTHORED_BY**: Post → User

- **IN_SUBREDDIT**: Post → Subreddit

- **CO_OCCURS**: Keyword → Keyword（共现关系）
  - 属性: `weight`, `window`

## CLI使用

### 基本用法

```bash
# 导出最近7天的内容图谱
python scripts/export_content_graph.py -o output/graph.json --days 7

# 导出指定时间范围
python scripts/export_content_graph.py -o output/graph.json \
    --since 2025-01-01T00:00:00 \
    --until 2025-01-31T23:59:59

# 导出特定主题的子图
python scripts/export_content_graph.py -o output/topic_graph.json \
    --days 30 \
    --topic "lottery strategy"

# 导出特定州的数据
python scripts/export_content_graph.py -o output/ca_graph.json \
    --days 30 \
    --state CA

# 导出Reddit平台数据
python scripts/export_content_graph.py -o output/reddit_graph.json \
    --days 30 \
    --platform reddit
```

### 高级选项

```bash
# 使用滑动窗口共现（窗口大小=5）
python scripts/export_content_graph.py -o output/graph.json \
    --days 7 \
    --window 5

# 不使用TF-IDF（使用简单频次）
python scripts/export_content_graph.py -o output/graph.json \
    --days 7 \
    --no-tfidf

# 启用时间衰减（τ=30天）
python scripts/export_content_graph.py -o output/graph.json \
    --days 30 \
    --tau 30

# 限制处理文档数量
python scripts/export_content_graph.py -o output/graph.json \
    --days 7 \
    --limit 1000

# 跳过校验（加快导出速度）
python scripts/export_content_graph.py -o output/graph.json \
    --days 7 \
    --no-validate
```

## Python API使用

### 基本示例

```python
from app.models.base import SessionLocal
from app.models.entities import Document
from app.services.graph.adapters import normalize_document
from app.services.graph.builder import build_graph, build_topic_subgraph
from app.services.graph.exporter import export_to_json, validate_graph
from sqlalchemy import select, and_

# 1. 查询文档
with SessionLocal() as session:
    query = select(Document).where(
        and_(
            Document.doc_type == "social_sentiment",
            Document.extracted_data.isnot(None)
        )
    ).limit(1000)
    
    documents = session.execute(query).scalars().all()

# 2. 规范化文档
normalized_posts = []
for doc in documents:
    normalized = normalize_document(doc)
    if normalized:
        normalized_posts.append(normalized)

# 3. 构建图谱
graph = build_graph(
    normalized_posts,
    window=0,        # 共现窗口（0=整帖共现）
    use_tfidf=True,  # 使用TF-IDF
    tau=None         # 时间衰减参数（None=不使用）
)

# 4. 校验图谱
validation_result = validate_graph(graph)
print(f"校验结果: {validation_result}")

# 5. 导出JSON
json_data = export_to_json(graph)
print(f"节点数: {len(json_data['nodes'])}, 边数: {len(json_data['edges'])}")

# 6. 构建主题子图
topic_subgraph = build_topic_subgraph(
    graph,
    topic_label="lottery strategy",
    time_window=None  # 可选的时间窗口
)
```

## 配置

配置文件位于 `app/settings/graph.py`：

```python
# 停用词（按语言）
STOPWORDS: Dict[str, Set[str]] = {...}

# 共现窗口大小（0=整帖共现）
COOCCUR_WINDOW: int = 0

# 是否使用TF-IDF
USE_TFIDF: bool = True

# 时间衰减参数（天数，None=不使用）
TIME_DECAY_TAU_DAYS: Optional[int] = None

# 每个帖子最多保留的关键词数量
MAX_KEYWORDS_PER_POST: int = 10
```

## 导出格式

JSON输出格式：

```json
{
  "graph_schema_version": "v1",
  "nodes": [
    {
      "type": "Post",
      "id": "123",
      "uri": "https://...",
      "platform": "reddit",
      "sentiment_orientation": "positive"
    },
    {
      "type": "Keyword",
      "id": "sha1:...",
      "text": "powerball"
    }
  ],
  "edges": [
    {
      "type": "MENTIONS_KEYWORD",
      "from": {"type": "Post", "id": "123"},
      "to": {"type": "Keyword", "id": "sha1:..."},
      "weight": 1.5
    }
  ]
}
```

## 平台扩展

添加新平台支持：

1. 创建适配器文件 `app/services/graph/adapters/<platform>.py`：

```python
from . import PlatformAdapter
from ...models.entities import Document
from ..models import NormalizedSocialPost

class TwitterAdapter:
    def to_normalized(self, doc: Document) -> Optional[NormalizedSocialPost]:
        # 实现字段映射逻辑
        ...
```

2. 注册适配器（在 `adapters/__init__.py` 中）：

```python
from .twitter import TwitterAdapter
register_adapter("twitter", TwitterAdapter)
```

3. 无需修改核心构图逻辑，`build_graph` 只依赖 `NormalizedSocialPost`。

## 校验规则

- **节点ID唯一性**: 检查是否有重复的节点ID
- **边端点存在性**: 检查所有边的源节点和目标节点是否存在
- **空值比例**: 警告空属性节点比例过高（>30%）

## 性能建议

- 分页扫描文档，流式产出
- 先使用整帖共现作为基线（`window=0`）
- 按 `created_at` 时间窗增量处理
- 使用 `--limit` 限制处理数量进行测试

## 示例工作流

```bash
# 1. 导出最近30天的完整图谱
python scripts/export_content_graph.py -o graphs/full_30d.json --days 30

# 2. 导出特定主题的子图
python scripts/export_content_graph.py -o graphs/topic_strategy.json \
    --days 30 --topic "lottery strategy"

# 3. 导出特定州的数据
python scripts/export_content_graph.py -o graphs/ca_only.json \
    --days 30 --state CA

# 4. 导出Reddit平台数据（带时间衰减）
python scripts/export_content_graph.py -o graphs/reddit_decay.json \
    --days 30 --platform reddit --tau 30
```

## 注意事项

1. 确保数据库中有 `doc_type='social_sentiment'` 的文档
2. 文档的 `extracted_data` 字段需要包含必要的字段（text, sentiment等）
3. 如果数据量很大，建议使用 `--limit` 先测试
4. 导出前会自动进行校验，可以通过 `--no-validate` 跳过

## 内容图谱数据结构快速参考（已并入）

以下内容整合自历史文档 `main/backend/docs/archive/graph-specs/社交平台数据结构说明.md`，用于 API 使用时快速核对输入/输出结构。

### 最小输入字段（来自 `extracted_data`）

```json
{
  "text": "<string>",
  "keywords": ["<string>"],
  "entities": [{"text": "<string>", "type": "<ORG|GAME|...>"}],
  "sentiment": {
    "sentiment_orientation": "positive|negative|neutral",
    "sentiment_tags": ["<string>"],
    "key_phrases": ["<string>"],
    "emotion_words": ["<string>"],
    "topic": "<string>"
  },
  "username": "<string?>",
  "subreddit": "<string?>"
}
```

### 核心节点与边（最小集合）

- 节点：`Post`、`Keyword`、`Entity`、`Topic`、`SentimentTag`、`User`、`Subreddit`
- 边：`MENTIONS_KEYWORD`、`MENTIONS_ENTITY`、`HAS_TOPIC`、`HAS_SENTIMENT`、`AUTHORED_BY`、`IN_SUBREDDIT`、`CO_OCCURS`

### 常见映射规则（摘要）

- `keywords[]` -> `Keyword` 节点 + `Post -> Keyword`
- `entities[]` -> `Entity` 节点 + `Post -> Entity`
- `sentiment.topic` -> `Topic` 节点 + `Post -> Topic`
- `sentiment.sentiment_tags[]` -> `SentimentTag` 节点 + `Post -> SentimentTag`
- `username/subreddit` -> 用户与子论坛节点

详细建模原则请优先参考 `main/backend/docs/社交平台图谱生成标准文档.md`。
