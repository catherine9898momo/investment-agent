# W5 上下文工程实验设计 · D4-D5

> 投递倒计时载体文档。2026-05-22 W5 D2 晚定稿。
> 目标：5/25 跑出 4 策略对比数据 + 1 张曲线图 + 简历段落升级。

---

## 1. 问题与动机

### 1.1 工程现实（5/22 D2 实测推出）

- `claude-agent-sdk 0.1.80` 默认跑在 **Sonnet 4 1M context window**，auto-compact 阈值 **967,000 tokens (92%)**
- 投资 Agent 3 轮短对话 totalTokens = 25,290（占 2-3%），距阈值差 38×
- 单轮 cost = O(N) of 轮数；**累计 N 轮 cost = O(N²)**
- 无压缩的 stateful Agent 跑过 100 轮 = 单轮 100× cost + 累计 5000× cost — 物理上无法商业化

### 1.2 SDK 内置能力（5/22 D2 源码考古）

| 能力 | 接口 | 用途 |
|---|---|---|
| 观测 | `client.get_context_usage()` | 实时 token 分桶（system / tools / messages / mcpTools / memoryFiles） |
| 自动压缩 | 默认 enabled，CLI 黑盒实现 | 到阈值自动触发 |
| 拦截 | `PreCompactHook(trigger, custom_instructions)` | 用户可注入领域 instructions |
| 阈值配置 | `autoCompactThreshold` | options 暴露 |

**关键发现**：`PreCompactHookInput.custom_instructions: str | None` 字段 — 允许在压缩前注入领域知识保留指令。这是策略 C 杀招的入口。

### 1.3 投资 Agent 的领域特殊性

通用 LLM 摘要压缩**会丢失**这类领域关键事实：
- 拆股 ratio（2020-08 5:1 + 2022-08 3:1 累计 15:1）
- 复权后成本计算（$1200 ÷ 15 = $80）
- 拆股事件日期
- ground truth 工具调用结果（corporate_actions / quote / news 数据）

这跟 W2 corporate_actions 反例闭环 **是同一血脉的方法论问题**：通用机制（LLM 训练知识 / LLM 摘要）在领域关键事实上不可靠，必须有领域兜底（ground truth server / PreCompact 注入）。

---

## 2. 实验矩阵

| 策略 | 实施 | 单轮 cost | 累计 cost | 保留率（预期） | 复杂度 |
|---|---|---|---|---|---|
| **0 观测** | 已上线 5/22 D2 | — | — | — | 极低 |
| **A 滑动窗口** | 切 `query()` + Python 自管 messages + 保留最近 K 轮 | 常数 | O(N) | 低（早期事实直接丢） | 低 |
| **B SDK 默认 auto-compact** | ClaudeSDKClient 不动 | 触发前 O(N)、后回落 | 阶梯式 O(N²)（次平方） | 中（LLM 摘要泛化丢数字） | 极低 |
| **C PreCompact + 领域 instructions** ★ | hook 注入"保留所有拆股 ratio / 复权计算 / 持仓数字 / 工具调用结果数据" | 同 B | 同 B + 微增 | **高（预期 >80%）** | 中 |

---

## 3. 长对话构造方案（方案 D：混合 A2A + 200K 模型）

### 3.1 模型切换

`ClaudeAgentOptions` 改用 200K 模型（去掉 `context-1m-2025-08-07` beta 头），阈值降至约 **184,000 tokens**。

**加速比**：1M → 200K = 5× 实验速度。原本要 100+ 轮触发的实验，30 轮就能跑出。

### 3.2 持仓 fixture（多 symbol、多市场、覆盖拆股边界）

| Symbol | 市场 | 数量 | 成本价 | 拆股事实 |
|---|---|---|---|---|
| TSLA | US | 1000 | $1200 | 2020-08 5:1 + 2022-08 3:1（累计 15:1） |
| NVDA | US | 200 | $40 | 2021-07 4:1 + 2024-06 10:1（累计 40:1） |
| AAPL | US | 500 | $150 | 历史拆股、近期无 |
| 09988.HK | HK | 100 | $280 | 无拆股、真实 -52% |
| 600519.SS | CN | 10 | $1680 | 无拆股 |

### 3.3 Agent-to-Agent（A2A）模拟

新建 `src/agents/synthetic_user.py`：
- 用 `query()` 一次性调用扮演"投资用户"
- system_prompt：你是有持仓的投资用户，会问"你的助手"持仓 / 行情 / 拆股 / 复权 / 浮盈 / 新闻 / 建议
- 输出 1 个 turn 的 user message，喂给 stateful_assistant 下一轮
- 30-50 轮目标

新建 `src/agents/long_dialogue_runner.py`：
- 串起 synthetic_user + stateful_assistant
- 每轮记录 `get_context_usage()` 数据点到 CSV
- 到达 percentage 阈值时打 marker

### 3.4 负例验证轮（关键事实保留率度量）

**Ground truth 关键事实清单**（10 条）：

```python
GROUND_TRUTH = [
    {"id": "tsla_split_2020", "text_match": ["2020-08", "5:1", "5-for-1"]},
    {"id": "tsla_split_2022", "text_match": ["2022-08", "3:1", "3-for-1"]},
    {"id": "tsla_cumulative", "text_match": ["15:1", "15倍", "累计 15"]},
    {"id": "tsla_adjusted_cost", "text_match": ["$80", "80 美元", "复权后"]},
    {"id": "nvda_split_2024", "text_match": ["2024-06", "10:1", "10-for-1"]},
    {"id": "nvda_cost_basis", "text_match": ["$40", "200 股"]},
    {"id": "alibaba_no_split", "text_match": ["无拆股", "下跌"]},
    {"id": "moutai_no_split", "text_match": ["600519", "无拆股"]},
    {"id": "portfolio_count", "text_match": ["5", "五"]},
    {"id": "tool_corp_actions_called", "text_match": ["get_corporate_actions", "corporate_actions"]},
]
```

**验证协议**：
1. 长对话跑过 auto-compact 触发点后（譬如第 30 轮）
2. 第 35 轮强制问："重新算下整体浮盈，分别说明每个持仓的复权后成本和拆股事实"
3. 抽取 assistant.text → 对每条 ground truth 做 substring 匹配
4. **保留率 = 命中条数 / 10**

### 3.5 PreCompact hook 注入内容（策略 C 核心）

```python
PRE_COMPACT_INSTRUCTIONS = """
压缩对话时务必逐字保留以下领域关键事实，不要泛化或摘要：

1. 所有持仓的 symbol / 数量 / 成本价（精确到数字）
2. 所有拆股事件的 日期 + ratio（不能用"曾经拆过股"概括）
3. 拆股累计因子（如 TSLA 15:1、NVDA 40:1）
4. 已计算的复权后成本数字（如 TSLA $80）
5. corporate_actions / get_quote / get_history 等工具的原始返回数据（特别是日期、价格、ratio 字段）
6. ground truth 校验过的结论（避免下次重新调工具）

其他可以摘要：闲聊、推理过程、重复的"建议持有/加仓"判断。

原则：金融垂直 Agent 的关键事实是不可丢失的具体数字，决策建议可以丢失。
"""
```

这正是 W2 corporate_actions 反例闭环里"**触发器 / 具体事实 / 决策建议**"三层模式的**自然延续** —— 压缩时也要按这三层差异化处理。

---

## 4. 实施时间表

| 日 | 任务 | 产出 |
|---|---|---|
| **5/22 D2 晚** ✅ | 策略 0 仪表盘 + baseline 数据 + 设计文档 | 本文档 |
| **5/23 D3** | README + push GitHub（W5 数据回灌） | GitHub 仓库公开 |
| **5/24 D4 上半** | 切 200K 模型 + 持仓 fixture 入库 | `config/portfolio.yaml` 5 持仓 |
| **5/24 D4 下半** | `synthetic_user.py` + `long_dialogue_runner.py` | 长对话脚本跑通 |
| **5/25 D5 上半** | 策略 A 手写滑动窗口 + 策略 B 跑长对话拿 baseline | A/B 数据点 |
| **5/25 D5 下半** | 策略 C PreCompact hook 注入 + 跑对比 | C 数据点 + 保留率 |
| **5/26 D6** | 4 策略对比图 + resume-snippet W5 段落升级 + 口述 1 题 | 1 张图 + 简历更新 |
| **5/27 D7** | 复盘 daily-lesson + 待抽查清单追加 + 口述 2 题 | 沉淀完成 |
| **5/28 D8** | 兜底缓冲 / push 检查 / 投递准备 | — |
| **5/29** | 投递 | — |

---

## 5. 度量协议（CSV schema）

每轮记录到 `logs/w5-d4-{strategy}-{timestamp}.csv`：

```csv
round_idx,strategy,total_tokens,percentage,messages_tokens,cost_usd,turns,compact_triggered,key_facts_retained
1,B,15234,8.27,2103,0.31,4,false,
2,B,18567,10.08,5436,0.35,1,false,
...
30,B,184321,99.96,170190,0.94,3,false,
31,B,52340,28.42,38209,0.41,2,true,
35,B,68210,37.05,54079,0.47,2,false,8/10  # 验证轮
...
35,C,71203,38.7,57072,0.49,2,false,9/10  # 同样长度，C 保留率更高
```

---

## 6. 简历叙事预案（5/26 写完图后回填）

**predicted（待实测）**：

> 在 200K context window 下，用 Agent-to-Agent 模拟构造 30+ 轮金融投资对话，触发 SDK 默认 auto-compact 后，关键事实保留率仅 **N/10**（拆股 ratio / 复权成本 / 工具调用 ground truth 大面积丢失）—— **垂直 Agent 致命错误**。通过 `PreCompactHook.custom_instructions` 注入"触发器 / 具体事实 / 决策建议"三层差异化压缩指令，保留率提升至 **M/10**。这是 W2 corporate_actions 反例闭环抽象出的"知识分层模式"在上下文工程层的**方法论复用**。

---

## 7. 风险与降级方案

| 风险 | 降级 |
|---|---|
| A2A synthetic_user 跑得太慢 / 跑跑停停 | 改人工敲 30 轮（备好 prompt 模板） |
| 200K 模型在 SDK 里改不动 / 文档没说清 | 退回 1M + 接受跑 100 轮的成本（cost 估算 < $20） |
| PreCompact hook trigger 文档跟实际行为不一致 | 先在小对话用 `/compact` 手动触发（trigger=manual）验证接口，再上 auto |
| 保留率度量字符串匹配偏差 | 加 LLM-as-judge 二审（仅必要时） |
| D4-D5 时间超支 | 砍策略 A（手写滑动窗口）作为对照；只保 B vs C 主对比 |
