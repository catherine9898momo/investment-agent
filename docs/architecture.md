# 架构设计

> **设计取向**：Agent 系统的本质 = LLM + 控制循环 + 外部能力。围绕三个核心矛盾分层：**LLM 不可靠 / 上下文有限 / 工具调用有副作用**。

## 静态分层 — 五层框架与当前实现的对应关系

```mermaid
flowchart TB
    subgraph L1["① Orchestrator 层（轻量·Python 入口脚本）"]
        A1[stateful_assistant.py<br/>长对话 / W5 主战场]
        A2[weekly_analyst.py<br/>周报 stateless]
        A3[long_dialogue_runner.py<br/>合成多轮压测]
        A4[regression_runner.py<br/>9 case 回归]
    end

    subgraph L2["② Planner 层（隐式·LLM 自决策）"]
        P1["ReAct loop<br/>不物化 plan"]
    end

    subgraph L3["③ Executor 层（Claude Agent SDK）"]
        E1[ClaudeSDKClient<br/>stateful client]
        E2[query<br/>stateless 调用]
        E3["PreToolUse / PostToolUse Hook<br/>参数校验 + 结果落盘"]
        E4["PreCompact Hook<br/>W5 在做·注入领域 instructions"]
    end

    subgraph L4["④ Tool 层（4 个 MCP Server·零修改复用）"]
        T1[memory_server<br/>持仓 / 偏好 / 关注]
        T2[finance_server<br/>quote / history]
        T3[news_server<br/>新闻]
        T4[corporate_actions_server<br/>拆股 ground truth ⭐]
    end

    subgraph L5["⑤ Memory 层"]
        M1[Short-term:<br/>SDK message history]
        M2["Working:<br/>tool 结果回灌（同 message history）"]
        M3[Long-term:<br/>SQLite memory.db]
    end

    L1 --> L2 --> L3
    L3 -.tool call.-> L4
    L4 -.读写.-> M3
    L3 -.维护.-> M1
    L3 -.维护.-> M2

    style L2 fill:#fff3cd
    style E4 fill:#fff3cd
    style T4 fill:#d4edda
```

**关键说明**：
- 黄色块 = 隐式实现 / W5 进行中
- 绿色块 = 项目核心差异化（拆股 ground truth 兜底 LLM 训练知识漂移）
- **没有独立 Orchestrator 进程**：Orchestrator = Python 入口脚本本身。多客户端零修改复用（Claude Desktop / Claude Code / 自研 agent）靠 MCP 协议层实现
- **没有显式 Planner**：当前场景是短链只读查询（2-4 个 tool call），ReAct 隐式 plan 够用。切换到显式 Plan-and-Execute 的条件：任务步数 >5-7、出现不可逆写操作、需要用户审批 plan

## 动态时序 — 一次完整调用（以拆股查询为例）

```mermaid
sequenceDiagram
    autonumber
    actor U as User
    participant O as stateful_assistant.py<br/>(Orchestrator)
    participant S as ClaudeSDKClient<br/>(Executor)
    participant L as Claude Sonnet 4.6
    participant H as Hook 层
    participant M as memory_server
    participant C as corporate_actions_server
    participant F as finance_server

    U->>O: "我 TSLA 1000股 成本$1200，现在啥情况"
    O->>S: client.query(input)
    S->>L: messages + tools schema

    Note over L: 隐式 plan:<br/>1.查持仓 2.查拆股 3.查行情

    L-->>S: tool_use: list_portfolio
    S->>H: PreToolUse 校验
    H->>M: 执行
    M-->>S: portfolio data
    S->>H: PostToolUse 落盘
    S->>L: tool_result 回灌

    L-->>S: tool_use: get_corporate_actions(TSLA)
    S->>C: 执行
    C-->>S: 2022 拆股 3:1 ground truth ⭐
    S->>L: tool_result 回灌

    L-->>S: tool_use: get_quote(TSLA)
    S->>F: 执行
    F-->>S: 当前价
    S->>L: tool_result 回灌

    L-->>S: 综合回答(复权后成本 $400, 浮盈 +457%)
    S-->>O: AssistantMessage
    O-->>U: 输出

    Note over S,L: 第 2 轮提问时<br/>SDK 自动带上完整 history<br/>= 隐式 working memory
```

**这张图体现的工程价值**：
1. **LLM 自路由**：步骤 4 / 7 / 10 三次 tool_use 顺序完全由 LLM 决定，无外部调度器
2. **Ground truth 夹在推理链路中间**（步骤 8）而不是事后校验，所以能在 LLM 推理时直接矫正训练知识漂移
3. **Hook 是基础设施**：每次 tool call 都有 Pre/Post 拦截，是 9/9 回归测试能跑通的前提

## Agent 入口清单

| 入口 | 状态 | 用途 | 备注 |
|---|---|---|---|
| `stateful_assistant.py` | W5 主战场 | 长对话 stateful 骨架 | 验证跨 query 的 message 维护 |
| `weekly_analyst.py` | 稳定 | 周报生成 | stateless `query()` |
| `long_dialogue_runner.py` | 实验 | 合成多轮压测 | 配 `synthetic_user.py` |
| `regression_runner.py` | 稳定 | 9 case 回归 | 正样本 + 负样本全过 |

System Prompt 共同要点：
- 严谨投资分析师定位，区分事实与观点
- 涉及历史价位判断**强制先调 `get_corporate_actions`** 拿拆股 ground truth
- 不给买卖建议，只提供分析视角
- 不确定的事项明确标注

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
