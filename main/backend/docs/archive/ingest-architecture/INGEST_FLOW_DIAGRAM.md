# 数据摄取流程图

## 市场数据摄取流程图

```
┌─────────────────────────────────────────────────────────────┐
│                    API请求入口                                │
│              POST /api/v1/ingest/market                      │
│         {state: "CA", game: null, source_hint: null}        │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│              ingest_market_data()                           │
│  1. 根据state/game/source_hint选择适配器                      │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│              get_market_adapters()                           │
│  - CA + 无game → 返回所有CA适配器                            │
│  - CA + game="Powerball" → 返回Powerball适配器                │
│  - source_hint="magayo" → 返回Magayo适配器                   │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
         ┌───────────┴───────────┐
         │                       │
         ▼                       ▼
┌──────────────────┐   ┌──────────────────┐
│  网页爬虫适配器    │   │   API适配器       │
│  - CA Lottery    │   │  - Magayo API    │
│  - CA Powerball  │   │  - LotteryData   │
│  - CA Mega       │   │  - NY Open Data  │
│  - TX Lottery    │   │                  │
│  - US Powerball  │   │                  │
└────────┬─────────┘   └────────┬─────────┘
         │                       │
         └───────────┬───────────┘
                     │
                     ▼
         ┌───────────────────────┐
         │  adapter.fetch_records()│
         │  - HTTP请求/API调用    │
         │  - 解析HTML/JSON       │
         │  - 返回MarketRecord[]  │
         └───────────┬───────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│              处理每条MarketRecord                            │
└────────────────────┬────────────────────────────────────────┘
                     │
         ┌───────────┴───────────┐
         │                       │
         ▼                       ▼
    ┌─────────┐           ┌─────────┐
    │date=None│           │有date    │
    └────┬────┘           └────┬─────┘
         │                     │
         │ skip                │
         │                     ▼
         │          ┌──────────────────────┐
         │          │ _get_existing()       │
         │          │ 查找现有记录          │
         │          └──────┬───────────────┘
         │                 │
         │    ┌────────────┴────────────┐
         │    │                         │
         │    ▼                         ▼
         │  ┌──────────┐          ┌──────────┐
         │  │  存在     │          │  不存在   │
         │  └────┬─────┘          └────┬─────┘
         │       │                     │
         │       ▼                     ▼
         │  ┌──────────────────┐  ┌────────────────────┐
         │  │_update_existing() │  │_calculate_growth() │
         │  │- 补充缺失字段     │  │- 计算MoM/YoY       │
         │  │- 更新game字段     │  └──────┬─────────────┘
         │  │- 更新元数据        │         │
         │  └──────┬────────────┘         │
         │         │                      │
         │         └──────────┬───────────┘
         │                    │
         │                    ▼
         │          ┌────────────────────┐
         │          │ 插入/更新数据库     │
         │          │ MarketStat          │
         │          └──────┬─────────────┘
         │                 │
         └─────────────────┘
                     │
                     ▼
         ┌───────────────────────┐
         │   session.commit()     │
         │   complete_job()       │
         └───────────────────────┘
```

## 匹配逻辑详细流程

```
_get_existing(record)
    │
    ├─ 查询同一天同一州的所有记录
    │
    ├─ 如果record.game存在
    │   ├─ 精确匹配（忽略大小写）
    │   │   └─ 找到 → 返回
    │   │
    │   └─ 精确匹配失败
    │       └─ 匹配game=None的记录
    │           └─ 找到 → 返回（用于补充game字段）
    │
    └─ 如果record.game为None
        ├─ 匹配有game字段的记录
        │   ├─ 优先返回有数据的记录
        │   └─ 否则返回第一个有game的记录
        │
        └─ 都没有 → 返回None（创建新记录）
```

## 数据更新策略

```
_update_existing(existing, new_record)
    │
    ├─ 数值字段（只补充None值）
    │   ├─ sales_volume: None → 补充
    │   ├─ revenue: None → 补充
    │   ├─ jackpot: None → 补充
    │   └─ ticket_price: None → 补充
    │
    ├─ game字段
    │   ├─ existing.game = None → 补充new_record.game
    │   └─ 不一致 → 使用new_record.game（修正）
    │
    └─ 元数据字段（总是更新）
        ├─ source_name
        ├─ source_uri
        ├─ draw_number
        └─ extra
```

## 适配器选择逻辑

```
get_market_adapters(state, game, source_hint)
    │
    ├─ source_hint指定？
    │   ├─ "magayo" → MagayoCaliforniaAdapter
    │   └─ "lotterydata" → LotteryDataCaliforniaAdapter
    │
    ├─ state = "CA"?
    │   ├─ game指定？
    │   │   ├─ "Powerball" → CaliforniaPowerballAdapter
    │   │   ├─ "Mega Millions" → CaliforniaMegaMillionsAdapter
    │   │   └─ "SuperLotto Plus" → CaliforniaLotteryMarketAdapter
    │   │
    │   └─ 无game → 返回所有CA适配器
    │       ├─ CaliforniaLotteryMarketAdapter
    │       ├─ CaliforniaPowerballAdapter
    │       ├─ CaliforniaMegaMillionsAdapter
    │       └─ USPowerballAdapter
    │
    └─ 其他state
        ├─ "NY" → NewYorkLotteryMarketAdapter
        └─ "TX" → TexasLotteryMarketAdapter
```

## 数据质量评估（建议实现）

```
评估每条记录的数据质量
    │
    ├─ 字段完整度
    │   ├─ 必需字段: state, date
    │   ├─ 重要字段: revenue, jackpot
    │   └─ 可选字段: sales_volume, ticket_price
    │
    ├─ 数据新鲜度
    │   └─ 距离当前时间的天数
    │
    ├─ 数据源可靠性
    │   ├─ 官方数据源 > API数据源 > 第三方爬虫
    │   └─ 历史准确率
    │
    └─ 数据一致性
        ├─ 与其他数据源的冲突
        └─ 异常值检测
```

