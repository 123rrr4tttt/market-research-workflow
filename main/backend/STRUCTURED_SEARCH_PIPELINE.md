# 结构化搜索与入库流程（精简版）

## 核心目标

解决两个关键问题：
1. **从关键词搜索升级到结构化提取**：使用 LLM 提取实体、属性、关系
2. **时间维度处理**：避免重复搜索相同信息，只获取新内容

---

## 精简架构（3个核心步骤）

```
搜索 → 结构化提取 → 入库（去重+时间过滤）
```

### 1. 智能搜索（时间感知）
- 检查上次搜索时间，只搜索新内容
- 过滤已入库的文档
- 时间排序（新信息优先）

### 2. 结构化提取（LLM）
- 使用 LLM 提取关键字段（政策/市场数据）
- 存储在 `extracted_data` JSONB 字段

### 3. 入库存储
- URL 去重（已存在则跳过）
- 文本 hash 去重（内容相同则跳过）
- 记录时间戳，支持增量查询

---

## 实施计划（分3个阶段）

### Phase 1: 时间维度处理 ⭐ 优先级最高

**目标**：解决"避免重复搜索"的问题

**实现**：
1. 添加时间过滤搜索函数
2. 过滤已存在的文档（URL 检查）
3. 记录搜索历史（简单的表）

**代码**：
```python
# 核心函数：智能搜索（自动增量）
def smart_search(topic: str, days_back: int = 30) -> List[dict]:
    """智能搜索：自动判断是否增量，只返回新信息"""
    # 1. 检查上次搜索时间
    last_time = get_last_search_time(topic)
    
    # 2. 确定搜索范围
    if last_time:
        since_date = last_time  # 增量搜索
    else:
        since_date = datetime.now() - timedelta(days=days_back)  # 首次搜索
    
    # 3. 执行搜索
    results = search_sources(topic, max_results=20)
    
    # 4. 过滤已存在的文档
    new_results = filter_existing(results)
    
    # 5. 时间排序
    sorted_results = sort_by_time(new_results)
    
    return sorted_results[:10]

def filter_existing(results: List[dict]) -> List[dict]:
    """过滤已入库的文档"""
    urls = [r.get("link") for r in results if r.get("link")]
    if not urls:
        return results
    
    with SessionLocal() as session:
        existing = {
            row[0] for row in session.execute(
                select(Document.uri).where(Document.uri.in_(urls))
            ).all()
        }
    
    return [r for r in results if r.get("link") not in existing]
```

**数据库**：
```sql
-- 简单的搜索历史表
CREATE TABLE search_history (
    id SERIAL PRIMARY KEY,
    topic VARCHAR(255) NOT NULL,
    last_search_time TIMESTAMP DEFAULT NOW(),
    UNIQUE(topic)
);
```

**工作量**：1-2天

---

### Phase 2: 结构化提取（LLM）

**目标**：提取结构化信息，存储到 `extracted_data` 字段

**实现**：
1. 定义 Pydantic 模型（Policy/MarketData）
2. 使用 LLM structured output 提取
3. 存储到 `documents.extracted_data` JSONB 字段

**代码**：
```python
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import date

class PolicyExtracted(BaseModel):
    """政策提取结构"""
    state: Optional[str] = None
    effective_date: Optional[date] = None
    policy_type: Optional[str] = None
    key_points: List[str] = Field(default_factory=list)

def extract_policy_info(text: str) -> dict:
    """提取政策结构化信息"""
    model = get_chat_model()
    
    prompt = f"""
    从以下文本中提取政策的关键信息：
    
    {text[:3000]}  # 限制长度
    
    请提取：州、生效日期、政策类型、关键要点
    """
    
    # 使用 structured output
    if hasattr(model, 'with_structured_output'):
        result = model.with_structured_output(PolicyExtracted).invoke(prompt)
        return result.dict()
    else:
        # Fallback: JSON 模式
        response = model.invoke(prompt + "\n\n请以 JSON 格式返回。")
        import json
        return json.loads(response.content)

# 在入库时调用
def store_document_with_extraction(doc_data: dict):
    """入库时提取结构化信息"""
    # 提取结构化信息
    if doc_data.get("doc_type") == "policy":
        extracted = extract_policy_info(doc_data["content"])
        doc_data["extracted_data"] = extracted
    
    # 存储文档
    doc = Document(**doc_data)
    session.add(doc)
    session.commit()
```

**数据库**：
```sql
-- 添加 extracted_data 字段（如果还没有）
ALTER TABLE documents ADD COLUMN IF NOT EXISTS extracted_data JSONB;
```

**工作量**：2-3天

---

### Phase 2.5: 轻量实体-关系抽取（保留）

**目标**：在不引入复杂训练与新存储的前提下，保留“可用”的实体-关系（ER）抽取能力，用于后续检索/统计。

**权威参考（工程/研究并重）**：
- OpenNRE（神经关系抽取工具包，总览与框架）[arXiv](https://arxiv.org/abs/1909.13078)
- PFN：Partition Filter Network（联合抽取路线）[arXiv](https://arxiv.org/abs/2108.12202)
- Dynamic Span Graphs（信息抽取通用图式）[arXiv](https://arxiv.org/abs/1904.03296)
- 中文实践/综述（便于落地）：
  - 关系抽取技术综述（从文本到知识图谱）[developer.baidu.com](https://developer.baidu.com/article/details/3305515)
  - PaddleNLP 关系抽取实现流程[developer.baidu.com](https://developer.baidu.com/article/details/2978172)

**最小 JSON Schema（写入 `documents.extracted_data`）**：
```python
from typing import List, Literal, Optional
from pydantic import BaseModel, Field

class ExtractedEntity(BaseModel):
    text: str
    type: Literal["ORG","LOC","PERSON","AGENCY","LAW","GAME"]  # 精简类型
    span: Optional[List[int]] = None  # [start, end] 可选

class ExtractedRelation(BaseModel):
    subject: str
    predicate: Literal["regulates","affects","announces","changes_rule","reports_sales"]
    object: str
    evidence: str = Field(default="")
    confidence: float = Field(ge=0.0, le=1.0)
    date: Optional[str] = None  # ISO 日期，可选

class ERPayload(BaseModel):
    entities: List[ExtractedEntity] = Field(max_items=5)
    relations: List[ExtractedRelation] = Field(max_items=3)
```

**提取方式（免训练优先，双重兜底）**：
- 级别1（优先）：LLM 结构化输出（严格使用上述 Schema，限制数量与谓词集合，提示词限定“与彩票政策/销售直接相关”）
- 级别2（兜底）：轻量规则/模板（触发词 + 依存/正则），如“委员会/监管部门 + 发布/修订/生效 + 规则/公告/销售”

**示例（LLM 结构化输出）**：
```python
def extract_entities_relations(text: str) -> dict:
    from ..llm.provider import get_chat_model
    model = get_chat_model()

    prompt = (
        "请从以下文本中抽取与彩票政策/市场直接相关的实体与关系，"
        "最多5个实体、3条关系；谓词必须在 {regulates, affects, announces, changes_rule, reports_sales} 中。\n\n"
        + text[:3000]
    )

    if hasattr(model, "with_structured_output"):
        return model.with_structured_output(ERPayload).invoke(prompt).dict()
    else:
        resp = model.invoke(prompt + "\n\n请以上述 JSON Schema 返回。")
        import json
        return json.loads(getattr(resp, "content", str(resp)))
```

**存储与查询（先简后繁）**：
- 仅写入 `documents.extracted_data.entities/relations`（JSONB）；不新增表，降低改造成本
- 若后续需要跨文档关系检索，再增一张轻量表 `document_relations(doc_id, subject, predicate, object, confidence, date)`

**时间维度融合**：
- 从正文/元数据中尽量补齐 `relations[].date`；与“时间过滤与增量搜索”联动，仅对新入库文档做 ER 抽取，避免重复

**说明**：
- 做“少量+高质”抽取，避免 LLM 幻觉导致低质数据淹没库表
- 固定小型谓词集合，降低歧义与治理成本；后续可按需扩展
- 先 JSONB，再表结构演进，符合“先用起来、后演进”的策略

---

### Phase 3: 增强搜索（可选）

**目标**：改进搜索质量

**实现**：
1. 时间感知的关键词生成
2. 向量搜索（语义相似度）
3. 混合检索（关键词 + 向量）

**工作量**：3-5天（可选，根据需求）

---

## 核心代码集成点

### 1. 修改 `search_sources` 函数

```python
# backend/app/services/search/web.py

def search_sources(
    topic: str,
    language: str = "en",
    max_results: int = 10,
    provider: str = "auto",
    days_back: Optional[int] = None,  # 新增：时间过滤
    exclude_existing: bool = True,     # 新增：排除已存在
) -> List[dict]:
    """搜索外部资源（带时间过滤）"""
    
    # 时间过滤逻辑
    if days_back:
        # 添加时间关键词
        time_keywords = [f"{datetime.now().year}", "recent", "latest"]
        # ... 在关键词生成时加入时间限定
    
    # 执行搜索（原有逻辑）
    results = _execute_search(...)
    
    # 过滤已存在的文档
    if exclude_existing:
        results = filter_existing_documents(results)
    
    # 时间排序
    results = sort_by_time_relevance(results)
    
    return results
```

### 2. 修改 `store_results` 函数

```python
# backend/app/services/discovery/store.py

def store_results(results: List[Dict]) -> Dict[str, int]:
    """存储搜索结果（带结构化提取）"""
    
    for item in results:
        # ... 现有的去重逻辑 ...
        
        # 新增：结构化提取
        if doc.doc_type == "policy" and doc.content:
            try:
                extracted = extract_policy_info(doc.content)
                doc.extracted_data = extracted
            except Exception as e:
                logger.warning(f"提取失败: {e}")
        
        # ... 存储文档 ...
```

---

## 实施建议

### 最小可行版本（MVP）

**只做 Phase 1**：
- ✅ 时间过滤搜索
- ✅ 过滤已存在文档
- ✅ 搜索历史记录

**效果**：解决"避免重复搜索"的核心问题

**时间**：1-2天

### 完整版本

**Phase 1 + Phase 2**：
- ✅ 时间维度处理
- ✅ LLM 结构化提取
- ✅ 存储到 JSONB 字段

**效果**：完整的结构化搜索和入库流程

**时间**：3-5天

---

## 技术栈（最小化）

- **LLM**：已有的 `get_chat_model()`（支持 structured output）
- **数据库**：PostgreSQL（已有 `documents` 表）
- **存储**：JSONB 字段（无需新表）
- **搜索**：现有的 `search_sources` 函数

**无需新增**：
- ❌ 知识图谱数据库
- ❌ 复杂的实体关系表
- ❌ 图查询引擎

---

## 使用示例

```python
# 示例1：智能搜索（自动增量）
results = smart_search("California lottery policy", days_back=30)

# 示例2：手动时间过滤
results = search_sources(
    topic="lottery regulation",
    days_back=7,          # 只搜索最近7天
    exclude_existing=True  # 排除已存在
)

# 示例3：查看提取的结构化数据
doc = session.query(Document).first()
if doc.extracted_data:
    print(doc.extracted_data["state"])
    print(doc.extracted_data["effective_date"])
```

---

## 总结

**核心思路**：
1. **时间维度**：记录搜索历史，只搜索新内容
2. **结构化提取**：LLM 提取关键字段，存 JSONB
3. **渐进式实施**：先做时间过滤，再做结构化提取

**避免过度设计**：
- ❌ 不要一开始就做知识图谱
- ❌ 不要一开始就做复杂的实体关系抽取
- ✅ 先解决核心问题（时间过滤 + 基础结构化提取）
- ✅ 后续根据需求再扩展

**预期效果**：
- ✅ 不再重复搜索相同信息
- ✅ 只获取新内容
- ✅ 结构化信息便于查询和分析
