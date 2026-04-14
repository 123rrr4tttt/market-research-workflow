# 数据源发现总结

## 🔍 关键发现

### 1. CA Lottery网站

#### 主页面 (`/en/draw-games/{game}`)
- ✅ **可提取字段**（已改进）:
  - 开奖日期
  - 开奖期号 (`Draw #4026`)
  - 中奖号码（6个号码）
  - 奖级详情（10个奖级）
  - 奖池金额
  - 总奖金支出

- ⚠️ **限制**:
  - 只能获取最新1条记录
  - 没有销售额数据（页面未显示）

- 🔍 **历史数据功能**:
  - "PAST WINNING NUMBERS" 按钮存在
  - 配置显示有106条历史记录 (`pwnTotalResults: "106"`)
  - API端点: `/api/DrawGameApi/DrawGamePastDrawResults/`
  - 游戏ID: SuperLotto Plus = 8
  - ❌ 直接API访问返回404（可能需要特殊认证）

#### 建议改进方向:
1. 尝试使用浏览器自动化（Selenium/Playwright）访问历史数据标签页
2. 或者使用Powerball.com/MegaMillions.com作为历史数据源

### 2. Powerball.com (官方全国网站) ⭐⭐⭐

**URL**: `https://www.powerball.com`

#### 发现的数据源:

1. **历史结果列表**: `/previous-results?gc=powerball`
   - ✅ 包含61+条历史记录链接
   - ✅ 每条记录包含：日期、中奖号码、Power Play倍数
   - ✅ 可以直接爬取

2. **详细结果页面**: `/draw-result?gc=powerball&date=2025-11-01`
   - ✅ 包含完整信息：
     - 日期: `Sat, Nov 1, 2025`
     - 中奖号码: `22 26 43 44 62` + Powerball `22`
     - Power Play: `2x`
     - 奖池金额: `$404 Million`
     - 现金价值: `$191.1 Million`
   - ✅ 可能包含更多详情（表格数据）

#### 优势:
- ✅ 官方数据源，可靠性高
- ✅ 历史数据丰富（61+条）
- ✅ 数据结构清晰
- ✅ 支持按日期查询
- ✅ 包含CA州的数据

#### 可提取字段:
- 日期
- 中奖号码（5个主号码 + Powerball）
- Power Play倍数
- 奖池金额
- 现金价值
- 可能还有各奖级详情

### 3. MegaMillions.com (官方全国网站) ⭐⭐⭐

**URL**: `https://www.megamillions.com`

#### 发现的数据源:

1. **历史数据页面**: `/Winning-Numbers/Previous-Drawings.aspx`
   - ✅ 包含历史开奖记录
   - ✅ 页面有表格数据

2. **最新开奖页面**: `/Winning-Numbers/Watch-Latest-Draw.aspx`
   - ✅ 包含最新开奖信息

#### 优势:
- ✅ 官方数据源
- ✅ 包含历史数据
- ✅ 包含CA州的数据

### 4. Lottery USA (第三方)

**URL**: `https://www.lotteryusa.com/california/`

- ✅ 可访问
- 📊 包含多个表格
- ⚠️ 数据可靠性需验证

## 📊 数据源对比总结

| 数据源 | 最新数据 | 历史数据 | 数据完整度 | 访问难度 | 推荐度 |
|--------|---------|---------|-----------|---------|--------|
| **CA Lottery主页面** | ✅ 1条 | ❌ | ⚠️ 70% | ✅ 简单 | ⭐⭐⭐ |
| **CA Lottery API** | ❓ | ❓ 106条 | ❓ | ⚠️ 需认证 | ⭐⭐ |
| **Powerball.com** | ✅ | ✅ 61+条 | ✅ 高 | ✅ 简单 | ⭐⭐⭐⭐⭐ |
| **MegaMillions.com** | ✅ | ✅ 多条 | ✅ 高 | ✅ 简单 | ⭐⭐⭐⭐⭐ |
| **Lottery USA** | ✅ | ✅ | ⚠️ 未知 | ✅ 简单 | ⭐⭐⭐ |

## 🎯 推荐的数据源策略

### 策略1: 多数据源融合（推荐）

```
最新数据（每日更新）:
  CA Lottery主页面
    ↓
  提取: 期号、号码、奖级详情

历史数据（定期同步）:
  Powerball.com / MegaMillions.com
    ↓
  提取: 完整历史记录
```

### 策略2: 优先级顺序

1. **CA Lottery主页面** - 获取最新数据（已完成改进）
2. **Powerball.com** - 补充Powerball历史数据
3. **MegaMillions.com** - 补充Mega Millions历史数据
4. **CA Lottery API** - 如果能够访问，作为主要历史数据源

## 💡 实施建议

### 立即实施（已完成）
- ✅ 改进CA适配器提取更多字段
- ✅ 提取期号、中奖号码、奖级详情

### 短期实施（1-2周）
1. **实现Powerball.com适配器**
   - 爬取 `/previous-results` 页面
   - 提取历史记录列表
   - 访问详细结果页面获取完整数据
   - 预期：可获取60+条历史记录

2. **实现MegaMillions.com适配器**
   - 爬取历史数据页面
   - 提取历史记录
   - 预期：可获取多条历史记录

### 中期实施（1个月）
3. **尝试访问CA Lottery API**
   - 使用浏览器自动化工具
   - 或者分析JavaScript找到正确的调用方式
   - 预期：可获取106条历史记录

4. **数据融合逻辑**
   - 实现多数据源融合
   - 数据去重和验证
   - 优先级管理

## 📋 数据字段完整度对比

### CA Lottery主页面（改进后）
- ✅ date: 100%
- ✅ game: 100%
- ✅ draw_number: 100% (新增)
- ✅ jackpot: 100%
- ✅ winning_numbers: 100% (新增，在extra中)
- ✅ prize_tiers: 100% (新增，在extra中)
- ✅ total_payout: 100% (新增，在extra中)
- ❌ sales_volume: 0% (页面无此数据)
- ⚠️ revenue: 估算值（用total_payout代替）

### Powerball.com（预期）
- ✅ date: 100%
- ✅ game: 100%
- ✅ draw_number: 可能
- ✅ jackpot: 100%
- ✅ winning_numbers: 100%
- ✅ power_play: 100%
- ✅ cash_value: 100%
- ✅ prize_tiers: 可能
- ❌ sales_volume: 未知

## 🚀 下一步行动

1. ✅ **已完成**: 改进CA适配器提取更多字段
2. ⏭️ **下一步**: 实现Powerball.com适配器获取历史数据
3. ⏭️ **下一步**: 实现MegaMillions.com适配器获取历史数据
4. ⏭️ **未来**: 研究CA Lottery API访问方式

## 📝 技术实现要点

### Powerball.com适配器实现要点

```python
class PowerballComAdapter(MarketAdapter):
    """Powerball.com历史数据适配器"""
    
    BASE_URL = "https://www.powerball.com"
    PREVIOUS_RESULTS_URL = f"{BASE_URL}/previous-results?gc=powerball"
    
    def fetch_records(self, limit: int = 50) -> Iterable[MarketRecord]:
        # 1. 获取历史结果列表页面
        # 2. 提取所有结果链接
        # 3. 访问每个详细结果页面
        # 4. 提取完整数据
        pass
```

### 关键发现的数据字段

**Powerball.com详细结果页面包含**:
- 日期
- 中奖号码（5个主号码 + Powerball）
- Power Play倍数
- 奖池金额（Estimated Jackpot）
- 现金价值（Cash Value）
- 可能还有各奖级详情（需要进一步分析）

