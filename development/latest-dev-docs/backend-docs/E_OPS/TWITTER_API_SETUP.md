# Twitter/X API 注册和使用指南

> 最后更新：2026-02 | 文档索引：`docs/README.md`

## 注册步骤

### 1. 访问 Twitter 开发者平台

访问：https://developer.twitter.com/ 或 https://developer.x.com/

### 2. 申请开发者账号

1. 点击右上角的 **"Sign up"** 或 **"Apply"** 按钮
2. 使用你的 Twitter/X 账号登录（如果没有账号，需要先注册）
3. 填写开发者申请表单：
   - **开发目的**：描述你计划如何使用 Twitter API
   - **应用类型**：选择你的应用类型（Web应用、移动应用等）
   - **使用案例**：详细说明你的使用场景
   - **是否计划发布推文**：根据需求选择
4. 提交申请，等待审核（通常需要几天时间）

### 3. 创建项目和应用

审核通过后：

1. 登录 [Twitter 开发者门户](https://developer.twitter.com/en/portal/dashboard)
2. 点击 **"Create Project"** 创建新项目
   - 填写项目名称和描述
   - 选择项目用途
3. 在项目中点击 **"Add App"** 添加应用
   - 填写应用名称
   - 选择应用类型（Web App、Native App等）
   - 填写回调URL（如果需要）

### 4. 获取 API 凭证

在应用详情页面：

1. 导航到 **"Keys and Tokens"** 标签
2. 获取以下凭证：
   - **API Key** (Consumer Key)
   - **API Secret Key** (Consumer Secret)
   - **Access Token** (需要点击"Generate"生成)
   - **Access Token Secret** (需要点击"Generate"生成)
3. **重要**：妥善保管这些凭证，不要泄露到代码仓库中

### 5. 配置应用权限

在应用设置中：
- 设置 **App Permissions**（读取、写入、读取和写入）
- 根据需求选择权限级别

## API 定价和限制

### 免费层级（Free Tier）

**注意**：Twitter/X 在 2023 年对 API 进行了重大改革，免费层级非常有限：

- **每月限制**：1,500 条推文读取（Tweet reads）
- **每月限制**：50,000 条推文读取（使用 Twitter API v2）
- **速率限制**：根据端点不同，有严格的速率限制

### 付费层级

- **Basic**：$100/月 - 10,000 条推文/月
- **Pro**：$5,000/月 - 1,000,000 条推文/月
- **Enterprise**：自定义定价

## 使用 Python 调用 Twitter API

### 安装 Tweepy 库

```bash
pip install tweepy
```

### 基本使用示例

```python
import tweepy

# API凭证
API_KEY = "your_api_key"
API_SECRET = "your_api_secret"
ACCESS_TOKEN = "your_access_token"
ACCESS_TOKEN_SECRET = "your_access_token_secret"

# 创建API客户端
client = tweepy.Client(
    bearer_token="your_bearer_token",  # 可选，用于只读操作
    consumer_key=API_KEY,
    consumer_secret=API_SECRET,
    access_token=ACCESS_TOKEN,
    access_token_secret=ACCESS_TOKEN_SECRET,
    wait_on_rate_limit=True  # 自动等待速率限制
)

# 搜索推文
tweets = client.search_recent_tweets(
    query="lottery",
    max_results=10,
    tweet_fields=['created_at', 'author_id', 'public_metrics']
)

# 获取用户推文
user_tweets = client.get_users_tweets(
    id="user_id",
    max_results=10
)
```

## 重要注意事项

1. **速率限制**：Twitter API 有严格的速率限制，建议使用 `wait_on_rate_limit=True` 自动处理
2. **数据使用**：遵守 Twitter 的使用条款，不要滥用 API
3. **凭证安全**：使用环境变量或配置文件存储 API 凭证，不要硬编码
4. **API 版本**：Twitter API v2 是推荐使用的版本，功能更强大
5. **审核时间**：开发者账号审核可能需要几天时间，请耐心等待

## 替代方案

如果免费层级不够用，可以考虑：

1. **Nitter**：Twitter 的替代前端（但存在限流问题）
2. **第三方服务**：如 Bright Data、Apify 等（需要付费）
3. **自建 Nitter 实例**：需要自己维护

## 相关链接

- [Twitter 开发者文档](https://developer.twitter.com/en/docs)
- [Twitter API v2 文档](https://developer.twitter.com/en/docs/twitter-api)
- [Tweepy 文档](https://docs.tweepy.org/)
- [Twitter 开发者门户](https://developer.twitter.com/en/portal/dashboard)

