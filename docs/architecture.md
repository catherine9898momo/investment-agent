# 架构设计

## 整体架构

```
┌──────────────────────────────────────────────────┐
│                   用户交互层                       │
│  ┌────────────┐  ┌────────────┐  ┌─────────────┐ │
│  │  CLI 对话   │  │  周报推送   │  │  即时查询    │ │
│  └─────┬──────┘  └─────┬──────┘  └──────┬──────┘ │
├────────┴───────────────┴────────────────┴────────┤
│                 Agent 编排层                       │
│  ┌──────────────────────────────────────────────┐ │
│  │           Claude Agent SDK                    │ │
│  │  ┌─────────────┐  ┌────────────────────────┐ │ │
│  │  │ Chat Agent   │  │ Weekly Analyst Agent   │ │ │
│  │  │ (日常问答)    │  │ (周报生成)              │ │ │
│  │  └─────────────┘  └────────────────────────┘ │ │
│  └──────────────────────────────────────────────┘ │
├──────────────────────────────────────────────────┤
│                  MCP 工具层                        │
│  ┌──────────┐  ┌──────────┐  ┌────────────────┐  │
│  │ News MCP │  │Finance   │  │ Memory MCP     │  │
│  │          │  │MCP       │  │                │  │
│  │ -NewsAPI │  │ -Yahoo   │  │ -持仓管理       │  │
│  │ -Google  │  │  Finance │  │ -关注列表       │  │
│  │  News    │  │ -Alpha   │  │ -偏好设置       │  │
│  │          │  │  Vantage │  │ -历史分析       │  │
│  └──────────┘  └──────────┘  └────────────────┘  │
├──────────────────────────────────────────────────┤
│                  数据存储层                        │
│  ┌──────────────────────────────────────────────┐ │
│  │  SQLite (memory.db)                          │ │
│  │  ├── portfolio     # 持仓记录                 │ │
│  │  ├── watchlist     # 关注公司                 │ │
│  │  ├── preferences   # 投资偏好                 │ │
│  │  ├── analyses      # 历史分析                 │ │
│  │  └── news_cache    # 新闻缓存                 │ │
│  └──────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────┘
```

## 核心工作流

### 1. 每周分析流程

```
触发 (cron / 手动)
    │
    ▼
[拉取全球热点新闻] ──→ TOP 10 事件摘要
    │
    ▼
[拉取关注公司新闻] ──→ 每个公司的近期动态
    │
    ▼
[影响分析]
    ├── 事件与公司的关联度评估
    ├── 利好/利空/中性判断
    ├── 影响程度评分 (1-10)
    └── 结合投资者风格给出观点
    │
    ▼
[持仓审视]
    ├── 当前持仓是否受影响
    ├── 关注列表中是否有机会
    └── 风险提示
    │
    ▼
[生成周报] ──→ 推送给用户
```

### 2. 日常对话流程

```
用户提问
    │
    ▼
[意图识别]
    ├── 查询类: 调用数据工具获取信息后回答
    ├── 分析类: 调用多个工具 → 综合分析 → 回答
    ├── 管理类: 更新持仓/关注列表/偏好
    └── 闲聊类: 直接回答
```

## Agent 设计

### Weekly Analyst Agent

**角色**: 每周自动运行的分析师
**工具**:
- `get_global_news()` — 获取全球热点
- `get_company_news(company)` — 获取公司新闻
- `get_portfolio()` — 读取当前持仓
- `get_watchlist()` — 读取关注列表
- `get_preferences()` — 读取投资偏好
- `save_analysis(report)` — 保存分析结果

**System Prompt 要点**:
- 你是一位严谨的投资分析师
- 参考用户欣赏的投资者的思维框架进行分析
- 区分事实与观点，标注信息来源
- 不给出具体买卖建议，只提供分析视角
- 对不确定的事项明确标注不确定性

### Chat Assistant Agent

**角色**: 日常投资助手
**工具**: 同上 + 持仓/关注列表的增删改查
**特点**: 对话式交互，支持追问和深度讨论

## 记忆系统设计

### 数据模型

```python
# 持仓
Portfolio:
    symbol: str        # 股票代码 e.g. AAPL, 600519.SS
    name: str          # 公司名
    market: str        # 市场 US/CN/HK
    shares: float      # 持仓数量
    avg_cost: float    # 平均成本
    added_at: datetime

# 关注列表
Watchlist:
    symbol: str
    name: str
    market: str
    reason: str        # 关注原因
    added_at: datetime

# 投资偏好
Preferences:
    admired_investors: list[str]    # 欣赏的投资者
    investment_style: str           # 投资风格描述
    risk_tolerance: str             # 风险偏好 conservative/moderate/aggressive
    focus_sectors: list[str]        # 关注行业
    analysis_language: str          # 分析语言 zh/en

# 历史分析
Analysis:
    date: date
    type: str          # weekly/adhoc
    content: text      # 分析内容 (markdown)
    companies: list    # 涉及公司
    events: list       # 涉及事件
```

## API Keys 需求

| 服务 | 用途 | 免费额度 |
|------|------|---------|
| Anthropic API | Claude Agent | 按量付费 |
| NewsAPI | 新闻数据 | 100 次/天 (免费) |
| Alpha Vantage | 美股数据 | 25 次/天 (免费) |
| Yahoo Finance | 行情数据 | 无限制 (yfinance 库) |

## 技术选型

- **语言**: Python 3.11+
- **Agent 框架**: Claude Agent SDK (`claude_agent_sdk`)
- **MCP 实现**: `mcp` Python SDK
- **数据存储**: SQLite (轻量，无需部署数据库)
- **定时任务**: cron (macOS launchd) 或 Python schedule
- **HTTP 客户端**: httpx
- **数据处理**: pandas (可选，用于财务数据分析)
