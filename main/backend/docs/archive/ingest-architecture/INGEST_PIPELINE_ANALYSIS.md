# 数据摄取流程深度分析

## 1. 整体架构

### 1.1 核心组件

```
API层 (app/api/ingest.py)
    ↓
服务层 (app/services/ingest/)
    ├── market.py        # 市场数据摄取
    ├── policy.py        # 政策文档摄取
    ├── news.py          # 新闻摄取
    └── reports/         # 报告摄取
    ↓
适配器层 (app/services/ingest/adapters/)
    ├── MarketAdapter     # 市场数据适配器基类
    ├── PolicyAdapter    # 政策文档适配器基类
    └── 具体实现...
    ↓
数据模型层 (app/models/entities.py)
    ├── MarketStat       # 市场统计数据
    ├── Document         # 文档
    └── EtlJobRun        # ETL任务运行记录
```

### 1.2 数据流向

```
外部数据源 (网站/API)
    ↓ fetch_records()
适配器 (Adapter)
    ↓ MarketRecord/PolicyDocument
摄取服务 (Ingest Service)
    ↓ 去重/匹配逻辑
数据库 (PostgreSQL)
    ↓ 索引
搜索引擎 (Elasticsearch)
```

## 2. 市场数据摄取流程 (Market Data Ingestion)

### 2.1 流程步骤

```python
ingest_market_data(state, source_hint, game, limit)
├── 1. 获取适配器列表
│   └── get_market_adapters() 
│       ├── 根据state选择适配器
│       ├── 根据game过滤（可选）
│       └── 根据source_hint指定数据源（可选）
│
├── 2. 从适配器获取数据
│   └── adapter.fetch_records()
│       ├── HTTP请求/API调用
│       ├── HTML解析/JSON解析
│       └── 转换为MarketRecord对象
│
├── 3. 处理每条记录
│   ├── 验证日期（跳过date为None的记录）
│   ├── 查找现有记录 (_get_existing)
│   │   ├── 精确匹配 (state + game + date)
│   │   ├── 模糊匹配 (game=None的情况)
│   │   └── 返回匹配的记录或None
│   │
│   ├── 如果存在记录
│   │   └── 更新现有记录 (_update_existing)
│   │       ├── 补充缺失字段（只补充None值）
│   │       ├── 更新game字段（如果新记录有而旧记录没有）
│   │       └── 更新元数据（source_name, uri等）
│   │
│   └── 如果不存在记录
│       ├── 计算增长率 (_calculate_growth)
│       │   ├── 环比增长率 (MoM)
│       │   └── 同比增长率 (YoY)
│       └── 插入新记录
│
└── 4. 提交事务并记录任务
    ├── session.commit()
    └── complete_job()
```

### 2.2 适配器类型

#### 2.2.1 网页爬虫适配器
- **CaliforniaLotteryMarketAdapter**: 爬取CA州彩票官网
- **CaliforniaPowerballAdapter**: 爬取CA Powerball页面
- **CaliforniaMegaMillionsAdapter**: 爬取CA Mega Millions页面
- **TexasLotteryMarketAdapter**: 爬取TX州彩票官网
- **USPowerballAdapter**: 爬取powerball.com全国数据

**特点**:
- 只能获取最新一次开奖数据
- 依赖HTML结构和CSS选择器
- 易受网站结构变化影响

#### 2.2.2 API适配器
- **NewYorkLotteryMarketAdapter**: 使用NY州开放数据API
- **MagayoCaliforniaAdapter**: 使用Magayo API
- **LotteryDataCaliforniaAdapter**: 使用LotteryData.io API

**特点**:
- 可以获取历史数据（取决于API限制）
- 数据结构化，更稳定
- 需要API密钥

### 2.3 去重与匹配策略

#### 2.3.1 唯一约束
```sql
UNIQUE (state, game, date)
```

#### 2.3.2 匹配逻辑 (_get_existing)

**问题场景**:
1. 同一个游戏，不同数据源返回的game字段格式不一致
2. 某些适配器返回game=None，某些返回具体game名称
3. 同一天可能有多个游戏的记录

**当前解决方案**:
```python
# 1. 精确匹配（忽略大小写）
if game_normalized:
    for result in all_results:
        if result.game and result.game.strip().upper() == game_normalized:
            return result
    
    # 2. 如果精确匹配失败，尝试匹配game=None的记录
    for result in all_results:
        if result.game is None:
            return result
else:
    # 3. 如果新记录game=None，匹配有game的记录
    # 优先返回有数据的记录
```

**潜在问题**:
- 当同一天有多个不同game的记录时，game=None的记录可能匹配到错误的记录
- 如果新记录game="Powerball"，但数据库中已有game=None和game="Mega Millions"的记录，会匹配到game=None的记录（可能不是同一游戏）

### 2.4 数据更新策略 (_update_existing)

**原则**: 只补充缺失字段，不覆盖已有数据

```python
# 只更新None值的字段
if record.revenue is not None and entry.revenue is None:
    entry.revenue = record.revenue
    changed = True

# 更新game字段（补充或修正）
if record_game_normalized:
    if not entry_game_normalized:
        entry.game = record_game_normalized  # 补充
    elif entry_game_normalized.upper() != record_game_normalized.upper():
        entry.game = record_game_normalized  # 修正不一致
```

## 3. 政策文档摄取流程 (Policy Document Ingestion)

### 3.1 流程步骤

```python
ingest_policy_documents(state, source_hint)
├── 1. 获取适配器
│   └── get_policy_adapter()
│
├── 2. 获取文档列表
│   └── adapter.fetch_documents()
│
├── 3. 处理每条文档
│   ├── 内容哈希去重 (_hash_text)
│   │   └── SHA256(content)
│   │
│   ├── 检查是否已存在
│   │   └── Document.text_hash == hash
│   │
│   ├── 创建或获取Source
│   │   └── _get_or_create_source()
│   │
│   └── 插入新文档
│
└── 4. 索引文档
    └── index_policy_documents()
```

### 3.2 去重策略

**基于内容哈希**:
- 优点: 完全去重，即使URL不同，内容相同也会被识别
- 缺点: 无法检测内容相似但不完全相同的情况

## 4. 发现的问题与改进建议

### 4.1 市场数据匹配问题

**问题1**: game字段匹配不够智能
- 当前: game=None的记录可能匹配到错误的游戏
- 改进: 增加数据相似度检查（revenue、jackpot等）

**问题2**: 同一天多个游戏的记录无法区分
- 当前: 依赖game字段，但某些适配器不提供game
- 改进: 使用source_name、uri等辅助信息进行匹配

**问题3**: 无数据记录的处理
- 当前: 某些适配器（如USPowerballAdapter）只返回日期，没有revenue/jackpot
- 改进: 考虑是否应该插入只有日期的记录，或者等待有数据的适配器

### 4.2 数据完整性问题

**问题**: 不同适配器提供的数据字段不完整
- CaliforniaLotteryMarketAdapter: 只有revenue和jackpot，没有sales_volume
- NewYorkLotteryMarketAdapter: 只有revenue和jackpot，没有sales_volume
- USPowerballAdapter: 只有日期，没有其他数据

**改进建议**:
1. 为每个适配器定义数据字段映射和期望值
2. 记录数据质量指标（哪些字段缺失）
3. 优先使用数据完整的适配器

### 4.3 错误处理与重试

**当前状态**:
- 适配器级别的错误处理不统一
- 某些适配器在失败时返回空列表，某些会抛出异常
- 没有重试机制

**改进建议**:
1. 统一错误处理接口
2. 实现指数退避重试
3. 记录失败原因到job_logger

### 4.4 性能优化

**问题**:
- 顺序处理记录，没有批量操作
- 每次都要查询数据库检查是否存在
- 增长率计算每次都查询历史数据

**改进建议**:
1. 批量查询现有记录（一次查询所有state+date的记录）
2. 缓存增长率计算结果
3. 使用批量插入（如果数据库支持）

### 4.5 监控与可观测性

**当前状态**:
- 有job_logger记录任务状态
- 但没有详细的指标（处理时间、数据质量等）

**改进建议**:
1. 添加性能指标（每个适配器的耗时、成功率）
2. 添加数据质量指标（字段完整度、重复率）
3. 添加告警机制（数据源失效、数据异常）

## 5. 推荐的重构方案

### 5.1 智能匹配策略

```python
def _get_existing_smart(session, record: MarketRecord) -> MarketStat | None:
    """
    智能匹配：使用多个信号进行匹配
    1. 精确匹配 (state + game + date)
    2. 数据相似度匹配 (state + date + 相似revenue/jackpot)
    3. 源信息匹配 (state + date + source_name)
    """
    # 1. 精确匹配
    exact_match = _exact_match(session, record)
    if exact_match:
        return exact_match
    
    # 2. 数据相似度匹配（如果game为None）
    if not record.game:
        similar_match = _similar_data_match(session, record)
        if similar_match:
            return similar_match
    
    # 3. 源信息匹配
    source_match = _source_match(session, record)
    if source_match:
        return source_match
    
    return None
```

### 5.2 数据质量评估

```python
class DataQuality:
    completeness: float  # 字段完整度 0-1
    freshness: float     # 数据新鲜度（距离当前时间）
    source_reliability: float  # 数据源可靠性
    conflicts: List[str]  # 与其他数据源的冲突
```

### 5.3 适配器注册机制

```python
@register_adapter(state="CA", game="Powerball", priority=1)
class CaliforniaPowerballAdapter(MarketAdapter):
    """高优先级适配器"""
    pass

@register_adapter(state="CA", game="Powerball", priority=2)
class USPowerballAdapter(MarketAdapter):
    """低优先级适配器（作为补充）"""
    pass
```

### 5.4 增量摄取策略

```python
def ingest_market_data_incremental(state: str, since_date: date = None):
    """
    增量摄取：只获取指定日期之后的数据
    """
    if since_date is None:
        # 获取数据库中最新的日期
        since_date = get_latest_date(state)
    
    adapters = get_market_adapters(state)
    for adapter in adapters:
        # 适配器需要支持日期过滤
        records = adapter.fetch_records(since_date=since_date)
        # ... 处理记录
```

## 6. 总结

### 当前优势
1. ✅ 清晰的适配器模式，易于扩展
2. ✅ 支持多种数据源（网页、API）
3. ✅ 基本的去重和更新逻辑
4. ✅ 任务日志记录

### 需要改进
1. ⚠️ 匹配逻辑需要更智能（数据相似度、源信息）
2. ⚠️ 数据质量评估和监控
3. ⚠️ 错误处理和重试机制
4. ⚠️ 性能优化（批量操作、缓存）
5. ⚠️ 增量摄取支持

### 优先级
1. **高优先级**: 改进匹配逻辑，解决game=None的匹配问题
2. **中优先级**: 添加数据质量评估和监控
3. **低优先级**: 性能优化和增量摄取

