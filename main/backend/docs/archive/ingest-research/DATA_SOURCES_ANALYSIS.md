# 数据源深度分析报告

## 1. CA彩票网站分析

### 1.1 主页面结构

**页面**: `https://www.calottery.com/en/draw-games/{game}`

**发现的关键信息**:
- ✅ 开奖日期: `.draw-cards--draw-date`
- ✅ 开奖期号: `.draw-cards--draw-number` (格式: `Draw #4026`)
- ✅ 中奖号码: 可通过多种选择器提取
- ✅ 奖级详情表格: `table.table-last-draw` (10行数据)
- ✅ 中奖概率表格: 第二个表格显示各奖级中奖概率

**数据字段**:
- 表格列: `['Matching Numbers', 'Winning Tickets', 'Prize Amounts']`
- 可以提取: 奖级名称、中奖人数、单注奖金、总奖金支出

### 1.2 历史数据功能

**发现**: "PAST WINNING NUMBERS" 按钮
- 位置: 页面导航标签
- 目标元素: `#section-content-2-3`
- 配置信息: 包含API端点配置

**API配置** (从页面提取):
```json
{
    "drawGamePastDrawResultsApi": "/api/DrawGameApi/DrawGamePastDrawResults/",
    "pwnGameId": "8",  // SuperLotto Plus
    "useAksApiEndpoint": "false",
    "aksApiDomain": "https://local.calottery.com"
}
```

**游戏ID映射** (推测):
- SuperLotto Plus: 8
- Powerball: 需要查找
- Mega Millions: 需要查找

**API端点测试结果**:
- ❌ 直接访问返回404（可能需要认证或特定headers）
- ⚠️ 可能需要从页面上下文调用（CORS/Referer限制）

### 1.3 页面内数据

**表格1 - 开奖详情**:
- 10个奖级
- 包含: 奖级名称、中奖人数、单注奖金

**表格2 - 中奖概率**:
- 10个奖级的中奖概率
- 格式: `Odds 1 in X`

**其他发现**:
- 页面只显示最新一次开奖
- 没有直接的历史数据表格
- 历史数据需要通过"PAST WINNING NUMBERS"标签页加载（可能是AJAX）

## 2. 其他数据源网站

### 2.1 Powerball.com (官方全国网站)

**URL**: `https://www.powerball.com`

**发现**:
- ✅ 有历史数据页面: `/previous-results?gc=powerball`
- ✅ 有详细结果页面: `/draw-result?gc=powerball&date=2025`
- ⚠️ 数据可能是动态加载（AJAX）

**可提取信息**:
- 历史开奖记录
- 中奖号码
- 奖池金额
- 各州数据（包括CA）

**优势**:
- 官方数据源，可靠性高
- 可能包含更完整的历史数据
- 支持按日期查询

### 2.2 MegaMillions.com (官方全国网站)

**URL**: `https://www.megamillions.com`

**发现**:
- ✅ 有历史数据页面: `/Winning-Numbers/Previous-Drawings.aspx`
- ✅ 有最新开奖页面: `/Winning-Numbers/Watch-Latest-Draw.aspx`
- 📊 页面包含表格数据

**可提取信息**:
- 历史开奖记录
- 中奖号码
- 奖池金额

### 2.3 Lottery USA (第三方)

**URL**: `https://www.lotteryusa.com/california/`

**发现**:
- ✅ 可访问
- 📊 包含8个表格
- 🔗 有相关链接

**特点**:
- 第三方数据聚合
- 可能包含多州数据对比
- 数据更新频率需验证

## 3. 数据源对比

| 数据源 | 历史数据 | 数据完整性 | 访问难度 | 可靠性 |
|--------|---------|-----------|---------|--------|
| CA Lottery主页面 | ❌ 仅最新 | ⚠️ 中等 | ✅ 简单 | ✅ 高 |
| CA Lottery API | ✅ 可能 | ⚠️ 未知 | ⚠️ 需认证 | ✅ 高 |
| Powerball.com | ✅ 有 | ✅ 高 | ✅ 简单 | ✅ 高 |
| MegaMillions.com | ✅ 有 | ✅ 高 | ✅ 简单 | ✅ 高 |
| Lottery USA | ✅ 有 | ⚠️ 未知 | ✅ 简单 | ⚠️ 中等 |

## 4. 改进建议

### 4.1 短期改进（使用现有页面）

1. **提取更多字段** (已完成)
   - ✅ 开奖期号
   - ✅ 中奖号码
   - ✅ 奖级详情

2. **优化数据提取**
   - 改进中奖号码提取的准确性
   - 区分主号码和特殊号码（Powerball/Mega）
   - 提取Power Play倍数（如果页面有）

### 4.2 中期改进（使用其他数据源）

1. **集成Powerball.com历史数据**
   - 爬取 `/previous-results` 页面
   - 提取历史开奖记录
   - 可以获取更多历史数据

2. **集成MegaMillions.com历史数据**
   - 爬取历史数据页面
   - 提取完整的历史记录

3. **尝试CA Lottery API**
   - 模拟浏览器请求（包含Referer等headers）
   - 可能需要session/cookie
   - 测试不同的请求方式

### 4.3 长期改进（数据融合）

1. **多数据源融合**
   - CA官方 + Powerball.com + MegaMillions.com
   - 优先级: 官方 > 全国官网 > 第三方
   - 自动选择数据最完整的源

2. **增量更新策略**
   - 每日更新最新数据（使用CA官方）
   - 定期同步历史数据（使用其他源）
   - 数据验证和冲突解决

## 5. 发现的关键信息

### 5.1 CA Lottery API端点

```
/api/DrawGameApi/DrawGamePastDrawResults/
```

**参数** (推测):
- `gameId`: 游戏ID（SuperLotto Plus = 8）
- 可能需要其他参数（limit, offset等）

**调用方式** (需要验证):
- 可能需要POST请求
- 需要特定的headers（Referer, User-Agent等）
- 可能需要session

### 5.2 其他网站API

**Powerball.com**:
- 可能有AJAX API（需要分析JavaScript）
- 支持URL参数查询: `?gc=powerball&date=2025`

**MegaMillions.com**:
- 使用ASP.NET页面
- 可能有Web API接口

## 6. 下一步行动

### 优先级1: 验证API访问
1. 尝试模拟浏览器请求访问CA Lottery API
2. 测试不同的headers和参数组合
3. 如果成功，可以实现历史数据获取

### 优先级2: 集成其他网站
1. 实现Powerball.com适配器
2. 实现MegaMillions.com适配器
3. 提取历史数据

### 优先级3: 数据质量提升
1. 改进现有适配器的数据提取准确性
2. 实现数据验证和清洗
3. 实现多数据源融合

## 7. 总结

### 当前状态
- ✅ CA主页面：只能获取最新1条记录
- ✅ 可以提取：期号、中奖号码、奖级详情
- ⚠️ 历史数据：需要API或其他网站

### 改进方向
1. ✅ 已完成：提取更多字段（期号、号码、奖级）
2. ⏭️ 下一步：集成Powerball.com和MegaMillions.com获取历史数据
3. ⏭️ 未来：尝试访问CA Lottery API获取完整历史数据

### 数据源优先级
1. **CA Lottery官方** (主数据源，最新数据)
2. **Powerball.com/MegaMillions.com** (历史数据补充)
3. **第三方API** (Magayo, LotteryData.io) (备用)

