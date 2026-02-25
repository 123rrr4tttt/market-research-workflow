# 爬虫适配器信息收集不足问题分析与改进方案

## 1. 当前问题分析

### 1.1 信息收集对比表

| 适配器类型 | 历史数据 | sales_volume | revenue | jackpot | draw_number | 奖级详情 | 中奖号码 |
|-----------|---------|--------------|---------|---------|-------------|----------|---------|
| **CaliforniaLotteryMarketAdapter** | ❌ 仅最新 | ❌ | ⚠️ 估算值 | ✅ | ❌ | ⚠️ 部分 | ❌ |
| **CaliforniaPowerballAdapter** | ❌ 仅最新 | ❌ | ⚠️ 估算值 | ✅ | ❌ | ⚠️ 部分 | ❌ |
| **CaliforniaMegaMillionsAdapter** | ❌ 仅最新 | ❌ | ⚠️ 估算值 | ✅ | ❌ | ⚠️ 部分 | ❌ |
| **TexasLotteryMarketAdapter** | ✅ 30条 | ❌ | ❌ | ✅ | ❌ | ❌ | ❌ |
| **USPowerballAdapter** | ✅ 10条 | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ |
| **Magayo API** | ✅ 多条 | ✅ | ✅ | ✅ | ⚠️ | ⚠️ | ⚠️ |
| **NY Open Data API** | ✅ 500条 | ❌ | ✅ | ✅ | ⚠️ | ❌ | ❌ |

**图例**:
- ✅ 完整收集
- ⚠️ 部分收集/估算值
- ❌ 未收集

### 1.2 具体问题

#### 问题1: 历史数据获取不足

**CA适配器问题**:
```python
# 当前实现：只能获取最新一次开奖
class CaliforniaLotteryMarketAdapter(MarketAdapter):
    def fetch_records(self):
        # 只爬取首页的最新开奖信息
        # 无法获取历史数据
        yield MarketRecord(...)  # 只有1条记录
```

**影响**:
- 无法进行历史趋势分析
- 无法计算准确的同比增长率（YoY）
- 数据更新频率受限（依赖单次开奖）

#### 问题2: 关键字段缺失

**sales_volume缺失**:
```python
# 当前实现：无法获取实际销售额
MarketRecord(
    sales_volume=None,  # ❌ 缺失
    revenue=total_payout,  # ⚠️ 用总奖金估算（不准确）
)
```

**draw_number缺失**:
```python
# 当前实现：没有开奖期号
MarketRecord(
    draw_number=None,  # ❌ 缺失
)
```

**影响**:
- 无法准确计算revenue（应该用sales_volume，而不是total_payout）
- 无法追踪具体开奖期次
- 数据质量下降

#### 问题3: 数据不准确

**revenue计算问题**:
```python
# 当前实现：用总奖金估算revenue（错误）
total_payout = 0.0
for row in table.css("tbody tr"):
    prize_value = self._parse_money(prize_raw)
    tickets_value = self._parse_int(tickets_raw)
    total_payout += prize_value * tickets_value  # 这是总奖金，不是revenue

revenue = total_payout if total_payout > 0 else None  # ❌ 错误
```

**正确理解**:
- `revenue` = 销售额（ticket sales）
- `total_payout` = 总奖金支出（prize payout）
- 这两个是不同的概念

#### 问题4: 信息挖掘不充分

**页面上的其他信息未收集**:
- 各奖级的中奖人数
- 各奖级的奖金金额
- Power Play倍数
- 销售截止时间
- 下一期奖池预测

## 2. 改进方案

### 2.1 增强型MarketRecord结构

```python
@dataclass(slots=True)
class EnhancedMarketRecord(MarketRecord):
    """增强的市场数据记录"""
    # 基础字段（继承自MarketRecord）
    state: str
    date: date
    game: str | None = None
    
    # 核心数据字段
    sales_volume: float | None = None  # 销售额（必需）
    revenue: float | None = None  # 收入（应该等于sales_volume）
    jackpot: float | None = None  # 奖池金额
    ticket_price: float | None = None  # 票价
    
    # 开奖信息
    draw_number: str | None = None  # 开奖期号
    winning_numbers: list[str] | None = None  # 中奖号码
    powerball_number: str | None = None  # Powerball号码
    multiplier: float | None = None  # Power Play倍数
    
    # 奖级详情
    prize_tiers: list[PrizeTier] | None = None  # 各奖级详情
    
    # 元数据
    source_name: str | None = None
    uri: str | None = None
    extra: dict[str, Any] | None = None


@dataclass
class PrizeTier:
    """奖级详情"""
    tier: str  # 奖级名称（如 "5 + Powerball"）
    winners: int  # 中奖人数
    prize_amount: float  # 单注奖金
    total_payout: float  # 总奖金支出
```

### 2.2 历史数据获取策略

#### 方案A: 爬取历史页面

```python
class CaliforniaLotteryMarketAdapter(MarketAdapter):
    """增强版：支持获取历史数据"""
    
    BASE_URL = "https://www.calottery.com"
    HISTORY_URL_TEMPLATE = "{base}/en/draw-games/{game}/draw-history"
    
    def fetch_records(self, days_back: int = 30) -> Iterable[MarketRecord]:
        """获取指定天数内的历史数据"""
        # 1. 获取最新数据
        yield from self._fetch_latest()
        
        # 2. 获取历史数据
        if days_back > 0:
            yield from self._fetch_history(days_back)
    
    def _fetch_history(self, days_back: int) -> Iterable[MarketRecord]:
        """爬取历史开奖页面"""
        history_url = self.HISTORY_URL_TEMPLATE.format(
            base=self.BASE_URL,
            game=self._get_game_slug()
        )
        
        html, _ = fetch_html(history_url)
        parser = make_html_parser(html)
        
        # 解析历史记录表格
        history_table = parser.css_first("table.draw-history")
        if not history_table:
            return
        
        cutoff_date = date.today() - timedelta(days=days_back)
        
        for row in history_table.css("tbody tr"):
            record = self._parse_history_row(row)
            if record and record.date >= cutoff_date:
                yield record
```

#### 方案B: 使用API接口（如果可用）

```python
class CaliforniaLotteryMarketAdapter(MarketAdapter):
    """增强版：优先使用API，回退到爬虫"""
    
    API_URL = "https://www.calottery.com/api/v1/draws/{game}"
    
    def fetch_records(self, days_back: int = 30) -> Iterable[MarketRecord]:
        """尝试API，失败则使用爬虫"""
        try:
            yield from self._fetch_via_api(days_back)
        except Exception:
            yield from self._fetch_via_scraper(days_back)
```

### 2.3 改进数据提取逻辑

#### 改进后的CA适配器

```python
class EnhancedCaliforniaLotteryMarketAdapter(MarketAdapter):
    """增强版CA适配器"""
    
    def fetch_records(self) -> Iterable[MarketRecord]:
        html, _ = fetch_html(self.PAGE_URL)
        parser = make_html_parser(html)
        
        # 1. 提取基础信息
        draw_date = self._extract_draw_date(parser)
        draw_number = self._extract_draw_number(parser)
        winning_numbers = self._extract_winning_numbers(parser)
        
        # 2. 提取销售数据（如果页面有）
        sales_volume = self._extract_sales_volume(parser)
        
        # 3. 提取奖池信息
        jackpot = self._extract_jackpot(parser)
        
        # 4. 提取奖级详情
        prize_tiers = self._extract_prize_tiers(parser)
        
        # 5. 计算准确的数据
        revenue = sales_volume  # revenue应该等于sales_volume
        total_payout = sum(tier.total_payout for tier in prize_tiers)
        
        yield EnhancedMarketRecord(
            state=self.state,
            date=draw_date,
            game=self.GAME,
            draw_number=draw_number,
            sales_volume=sales_volume,
            revenue=revenue,  # 准确值
            jackpot=jackpot,
            ticket_price=1.0,
            winning_numbers=winning_numbers,
            prize_tiers=prize_tiers,
            source_name="California Lottery - SuperLotto Plus",
            uri=self.PAGE_URL,
            extra={
                "total_payout": total_payout,
                "profit_margin": (revenue - total_payout) / revenue if revenue else None,
            }
        )
    
    def _extract_sales_volume(self, parser) -> float | None:
        """提取销售额"""
        # 尝试多种选择器
        selectors = [
            ".sales-volume",
            ".total-sales",
            "[data-sales]",
            # 可能在PDF报告中，需要额外处理
        ]
        
        for selector in selectors:
            node = parser.css_first(selector)
            if node:
                return self._parse_money(node.text(strip=True))
        
        return None
    
    def _extract_draw_number(self, parser) -> str | None:
        """提取开奖期号"""
        # 查找包含"Draw"或"#"的元素
        draw_node = parser.css_first(".draw-number, [data-draw-number]")
        if draw_node:
            text = draw_node.text(strip=True)
            # 提取数字部分
            import re
            match = re.search(r'#?\s*(\d+)', text)
            if match:
                return match.group(1)
        return None
    
    def _extract_winning_numbers(self, parser) -> list[str]:
        """提取中奖号码"""
        numbers = []
        number_nodes = parser.css(".winning-number, .ball-number")
        for node in number_nodes:
            num = node.text(strip=True)
            if num.isdigit():
                numbers.append(num)
        return numbers
    
    def _extract_prize_tiers(self, parser) -> list[PrizeTier]:
        """提取奖级详情"""
        tiers = []
        table = parser.css_first("table.table-last-draw")
        if not table:
            return tiers
        
        for row in table.css("tbody tr"):
            cells = [cell.text(strip=True) for cell in row.css("td")]
            if len(cells) < 3:
                continue
            
            tier_name = cells[0]
            winners = self._parse_int(cells[1])
            prize_amount = self._parse_money(cells[2])
            
            if winners and prize_amount:
                tiers.append(PrizeTier(
                    tier=tier_name,
                    winners=winners,
                    prize_amount=prize_amount,
                    total_payout=prize_amount * winners
                ))
        
        return tiers
```

### 2.4 多数据源融合策略

```python
class CompositeMarketAdapter(MarketAdapter):
    """组合适配器：融合多个数据源"""
    
    def __init__(self, state: str):
        super().__init__(state)
        self.adapters = [
            OfficialScraperAdapter(state),  # 官方爬虫（优先级最高）
            MagayoAPIAdapter(state),  # API（补充数据）
            LotteryDataAdapter(state),  # 第三方API（备用）
        ]
    
    def fetch_records(self) -> Iterable[MarketRecord]:
        """融合多个数据源"""
        records_by_date = {}
        
        # 1. 从所有适配器获取数据
        for adapter in self.adapters:
            try:
                for record in adapter.fetch_records():
                    key = (record.state, record.game, record.date)
                    if key not in records_by_date:
                        records_by_date[key] = []
                    records_by_date[key].append(record)
            except Exception as e:
                logger.warning(f"Adapter {adapter} failed: {e}")
        
        # 2. 融合数据
        for key, records in records_by_date.items():
            yield self._merge_records(records)
    
    def _merge_records(self, records: list[MarketRecord]) -> MarketRecord:
        """合并多条记录，优先使用官方数据源"""
        # 按优先级排序
        records.sort(key=lambda r: self._get_priority(r.source_name))
        
        # 合并字段
        merged = records[0]
        for record in records[1:]:
            # 补充缺失字段
            if merged.sales_volume is None and record.sales_volume:
                merged.sales_volume = record.sales_volume
            if merged.draw_number is None and record.draw_number:
                merged.draw_number = record.draw_number
            # ... 其他字段
        
        return merged
    
    def _get_priority(self, source_name: str) -> int:
        """获取数据源优先级"""
        priorities = {
            "California Lottery": 1,  # 官方最高
            "Magayo Lottery API": 2,
            "LotteryData.io": 3,
        }
        return priorities.get(source_name, 99)
```

### 2.5 增量摄取优化

```python
class IncrementalMarketAdapter(MarketAdapter):
    """支持增量摄取的适配器"""
    
    def fetch_records(self, since_date: date | None = None) -> Iterable[MarketRecord]:
        """只获取指定日期之后的数据"""
        if since_date is None:
            # 如果没有指定，获取最近30天的数据
            since_date = date.today() - timedelta(days=30)
        
        # 获取历史数据
        for record in self._fetch_history():
            if record.date >= since_date:
                yield record
            else:
                break  # 因为历史数据是按日期倒序的
```

## 3. 实施优先级

### 阶段1: 核心字段补充（高优先级）
1. ✅ 添加`draw_number`提取逻辑
2. ✅ 添加`winning_numbers`提取逻辑
3. ✅ 改进`revenue`计算（使用sales_volume而不是total_payout）
4. ✅ 添加`prize_tiers`详细信息

### 阶段2: 历史数据支持（中优先级）
1. ✅ 实现历史页面爬取
2. ✅ 添加增量摄取支持
3. ✅ 优化性能（批量处理）

### 阶段3: 数据融合（低优先级）
1. ✅ 实现多数据源融合
2. ✅ 添加数据质量评估
3. ✅ 添加冲突检测和解决

## 4. 数据库扩展

如果需要存储更多信息，可以扩展`extra`字段或添加新字段：

```python
class MarketStat(Base):
    # ... 现有字段 ...
    
    # 新增字段（可选）
    winning_numbers = Column(JSONB, nullable=True)  # 中奖号码数组
    prize_tiers_data = Column(JSONB, nullable=True)  # 奖级详情
    sales_period_start = Column(DateTime, nullable=True)  # 销售开始时间
    sales_period_end = Column(DateTime, nullable=True)  # 销售截止时间
    next_draw_date = Column(Date, nullable=True)  # 下一期开奖日期
    next_jackpot_estimate = Column(Numeric(18, 2), nullable=True)  # 下一期奖池预估
```

## 5. 测试建议

```python
def test_enhanced_adapter():
    """测试增强适配器"""
    adapter = EnhancedCaliforniaLotteryMarketAdapter("CA")
    records = list(adapter.fetch_records())
    
    # 验证字段完整性
    assert len(records) > 0, "应该至少有一条记录"
    record = records[0]
    
    assert record.date is not None, "date字段必需"
    assert record.draw_number is not None, "draw_number应该存在"
    assert record.sales_volume is not None or record.revenue is not None, "至少有一个销售数据"
    assert record.winning_numbers is not None, "中奖号码应该存在"
    assert record.prize_tiers is not None, "奖级详情应该存在"
    
    # 验证数据准确性
    if record.sales_volume and record.revenue:
        assert abs(record.sales_volume - record.revenue) < 0.01, "revenue应该等于sales_volume"
```

## 6. 总结

### 当前问题
1. ❌ 历史数据获取不足（只能获取最新1条）
2. ❌ 关键字段缺失（sales_volume, draw_number）
3. ❌ 数据不准确（revenue计算错误）
4. ❌ 信息挖掘不充分（奖级详情、中奖号码等）

### 改进方向
1. ✅ 增强MarketRecord结构
2. ✅ 实现历史数据爬取
3. ✅ 改进数据提取逻辑
4. ✅ 多数据源融合
5. ✅ 增量摄取支持

### 预期效果
- 📈 数据量：从1条/次 → 30+条/次
- 📊 字段完整度：从40% → 90%+
- 🎯 数据准确性：显著提升
- 📅 历史分析能力：支持30天+历史趋势分析

