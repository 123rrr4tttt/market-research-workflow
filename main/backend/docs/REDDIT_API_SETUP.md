# Reddit API 使用说明

> 最后更新：2026-02 | 文档索引：`docs/README.md`

## 简单方法（推荐）✨

**最简单的方法：使用真实的浏览器 User-Agent**

Reddit 的 JSON API 端点（在 URL 后加 `.json`）可以使用简单的 HTTP 请求访问，**不需要 OAuth 认证**，只需要使用真实的浏览器 User-Agent 即可。

### 实现方法

```python
import requests

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json",
    "Accept-Language": "en-US,en;q=0.9"
}

response = requests.get(
    "https://www.reddit.com/r/Lottery/hot.json?limit=20",
    headers=headers
)

data = response.json()
```

### 注意事项

- ✅ **不需要 OAuth 认证**
- ✅ **不需要注册应用**
- ✅ **简单易用**
- ⚠️ **有速率限制**（建议控制请求频率）
- ⚠️ **User-Agent 必须是真实的浏览器标识**

### 当前实现

代码已更新为使用真实的浏览器 User-Agent，可以正常访问 Reddit API。

---

## OAuth 认证方法（高级）

如果需要更高的速率限制或更稳定的访问，可以使用 OAuth 2.0 认证。

## 官方文档链接

- **Reddit 数据 API 维基**: https://support.reddithelp.com/hc/zh-cn/articles/16160319875092-Reddit-%E6%95%B0%E6%8D%AE-API-%E7%BB%B4%E5%9F%BA
- **Reddit API 文档**: https://www.reddit.com/dev/api/
- **开发者平台**: https://support.reddithelp.com/hc/zh-cn/articles/14945211791892-%E5%BC%80%E5%8F%91%E8%80%85%E5%B9%B3%E5%8F%B0%E4%B8%8E%E8%AE%BF%E9%97%AE-Reddit-%E6%95%B0%E6%8D%AE

## 重要要求

### 1. 身份验证（必需）

**Reddit API 要求必须使用 OAuth 2.0 进行身份验证**。客户端必须使用注册的 OAuth 令牌进行身份验证。

**未认证的请求会被阻止（403错误）**。

### 2. User-Agent 要求

User-Agent 字符串必须包含以下信息：
- 目标平台（如：`web`, `android`, `ios`）
- 应用程序 ID（从 Reddit 开发者平台获取）
- 版本号
- 您的 Reddit 用户名

**格式示例**：
```
<platform>:<app_id>:<version_string> (by /u/<reddit_username>)
```

例如：
```
web:lottery_intel:v1.0.0 (by /u/your_username)
```

### 3. 速率限制

- **每个 OAuth 客户端 ID 每分钟 100 次查询（QPM）**
- QPM 限制在时间窗口（10 分钟）内取平均值，以支持突发请求

**监控响应头**：
- `X-Ratelimit-Used`: 该期间使用的近似请求次数
- `X-Ratelimit-Remaining`: 剩余可用的近似请求数量
- `X-Ratelimit-Reset`: 该期间的剩余近似秒数

### 4. 内容删除要求

必须移除已从 Reddit 删除的用户内容，包括帖子、评论和用户信息。

## 注册应用程序步骤

1. **注册 Reddit 账户**（如果还没有）
2. **访问 Reddit 开发者平台**：https://www.reddit.com/prefs/apps
3. **创建应用程序**：
   - 点击 "create another app..." 或 "create app"
   - 选择应用类型：**script**（用于服务器端脚本）
   - 填写应用信息：
     - Name: 应用名称（如：Lottery Intel）
     - Description: 应用描述
     - About URL: 可选
     - Redirect URI: 对于 script 类型，可以使用 `http://localhost:8080`
   - 点击 "create app"
4. **获取凭证**：
   - **Client ID**: 在应用信息中显示（位于应用图标下方）
   - **Client Secret**: 在应用信息中显示（标记为 "secret"）
   - **User-Agent**: 按照格式要求构建

## 配置方法

在 `.env` 文件中配置以下变量：

```bash
# Reddit API 配置
REDDIT_CLIENT_ID=your_client_id_here
REDDIT_CLIENT_SECRET=your_client_secret_here
REDDIT_USER_AGENT=web:lottery_intel:v1.0.0 (by /u/your_username)
```

或者在设置页面（`settings.html`）中配置。

## OAuth 2.0 认证流程

### 1. 获取访问令牌（Access Token）

使用 **Client Credentials Grant**（适用于 script 类型应用）：

```python
import requests
import base64

client_id = "your_client_id"
client_secret = "your_client_secret"
user_agent = "web:lottery_intel:v1.0.0 (by /u/your_username)"

# 准备认证信息
auth = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()

# 获取访问令牌
response = requests.post(
    "https://www.reddit.com/api/v1/access_token",
    headers={
        "User-Agent": user_agent,
        "Authorization": f"Basic {auth}"
    },
    data={
        "grant_type": "client_credentials"
    }
)

access_token = response.json()["access_token"]
```

### 2. 使用访问令牌访问 API

```python
headers = {
    "User-Agent": user_agent,
    "Authorization": f"Bearer {access_token}"
}

response = requests.get(
    "https://oauth.reddit.com/r/Lottery/hot.json?limit=20",
    headers=headers
)
```

## 使用 PRAW 库（推荐）

PRAW (Python Reddit API Wrapper) 是 Reddit 官方推荐的 Python 库，简化了认证和 API 调用。

### 安装

```bash
pip install praw
```

### 配置

```python
import praw

reddit = praw.Reddit(
    client_id="your_client_id",
    client_secret="your_client_secret",
    user_agent="web:lottery_intel:v1.0.0 (by /u/your_username)"
)

# 获取子论坛热门帖子
subreddit = reddit.subreddit("Lottery")
for post in subreddit.hot(limit=20):
    print(post.title)
    print(post.url)
    print(post.created_utc)
```

## 当前代码问题

### 问题 1: 未使用 OAuth 认证

当前代码直接访问 `https://www.reddit.com/r/{subreddit}/hot.json`，没有使用 OAuth 认证，导致 403 错误。

**解决方案**：
- 使用 OAuth 2.0 认证
- 访问 `https://oauth.reddit.com/r/{subreddit}/hot.json`（而不是 `https://www.reddit.com`）

### 问题 2: User-Agent 格式不正确

当前 User-Agent: `Mozilla/5.0 (compatible; LotteryIntel/1.0)`

**解决方案**：
- 按照 Reddit 要求的格式构建 User-Agent
- 包含应用 ID 和用户名

### 问题 3: 未处理速率限制

**解决方案**：
- 监控响应头中的速率限制信息
- 实现请求延迟和重试机制

## 推荐实现方案

### 方案 1: 使用 PRAW 库（最简单）

```python
import praw
from ...settings.config import settings

class RedditAdapter:
    def __init__(self):
        if not settings.reddit_client_id or not settings.reddit_client_secret:
            raise ValueError("Reddit API credentials not configured")
        
        self.reddit = praw.Reddit(
            client_id=settings.reddit_client_id,
            client_secret=settings.reddit_client_secret,
            user_agent=settings.reddit_user_agent or "web:lottery_intel:v1.0.0"
        )
    
    def fetch_posts(self, subreddit: str, keywords: Optional[List[str]] = None, limit: int = 20):
        try:
            subreddit_obj = self.reddit.subreddit(subreddit)
            posts = []
            
            for post in subreddit_obj.hot(limit=limit):
                # 关键词过滤
                if keywords:
                    title_lower = post.title.lower()
                    text_lower = (post.selftext or "").lower()
                    if not any(kw.lower() in title_lower or kw.lower() in text_lower for kw in keywords):
                        continue
                
                posts.append(RedditPost(
                    title=post.title,
                    link=f"https://www.reddit.com{post.permalink}",
                    summary=post.selftext[:500] if post.selftext else None,
                    timestamp=datetime.utcfromtimestamp(post.created_utc),
                    username=post.author.name if post.author else None,
                    subreddit=subreddit,
                    likes=post.ups,
                    comments=post.num_comments,
                    text=post.selftext,
                ))
            
            return posts
        except Exception as exc:
            logger.warning("Reddit fetch failed for r/%s: %s", subreddit, exc)
            return []
```

### 方案 2: 手动实现 OAuth（更灵活）

```python
import requests
import base64
import time
from ...settings.config import settings

class RedditAdapter:
    def __init__(self):
        self.client_id = settings.reddit_client_id
        self.client_secret = settings.reddit_client_secret
        self.user_agent = settings.reddit_user_agent or "web:lottery_intel:v1.0.0"
        self.access_token = None
        self.token_expires_at = 0
        self.base_url = "https://oauth.reddit.com"
    
    def _get_access_token(self):
        """获取或刷新访问令牌"""
        if self.access_token and time.time() < self.token_expires_at:
            return self.access_token
        
        auth = base64.b64encode(f"{self.client_id}:{self.client_secret}".encode()).decode()
        
        response = requests.post(
            "https://www.reddit.com/api/v1/access_token",
            headers={
                "User-Agent": self.user_agent,
                "Authorization": f"Basic {auth}"
            },
            data={"grant_type": "client_credentials"}
        )
        
        if response.status_code == 200:
            data = response.json()
            self.access_token = data["access_token"]
            # 令牌有效期通常是1小时，提前5分钟刷新
            self.token_expires_at = time.time() + data.get("expires_in", 3600) - 300
            return self.access_token
        else:
            raise Exception(f"Failed to get access token: {response.status_code} {response.text}")
    
    def fetch_posts(self, subreddit: str, keywords: Optional[List[str]] = None, limit: int = 20):
        try:
            access_token = self._get_access_token()
            
            headers = {
                "User-Agent": self.user_agent,
                "Authorization": f"Bearer {access_token}"
            }
            
            url = f"{self.base_url}/r/{subreddit}/hot.json?limit={limit}"
            response = requests.get(url, headers=headers)
            
            # 检查速率限制
            if "X-Ratelimit-Remaining" in response.headers:
                remaining = int(response.headers["X-Ratelimit-Remaining"])
                if remaining < 10:
                    logger.warning(f"Reddit rate limit low: {remaining} requests remaining")
            
            if response.status_code == 200:
                data = response.json()
                # ... 处理数据
            else:
                logger.warning(f"Reddit API error: {response.status_code} {response.text}")
                return []
        except Exception as exc:
            logger.warning("Reddit fetch failed for r/%s: %s", subreddit, exc)
            return []
```

## 注意事项

1. **必须使用 OAuth 认证**：未认证的请求会被阻止
2. **User-Agent 格式必须正确**：包含应用 ID 和用户名
3. **遵守速率限制**：每分钟最多 100 次请求
4. **处理令牌过期**：访问令牌通常有效期为 1 小时，需要自动刷新
5. **错误处理**：实现重试机制和错误处理
6. **内容删除**：定期检查并删除已从 Reddit 删除的内容

## 参考资料

- Reddit 数据 API 维基: https://support.reddithelp.com/hc/zh-cn/articles/16160319875092-Reddit-%E6%95%B0%E6%8D%AE-API-%E7%BB%B4%E5%9F%BA
- Reddit API 文档: https://www.reddit.com/dev/api/
- PRAW 文档: https://praw.readthedocs.io/
- OAuth 2.0 规范: https://oauth.net/2/

