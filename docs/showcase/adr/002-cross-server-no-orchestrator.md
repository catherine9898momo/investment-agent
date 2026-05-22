# ADR-002：跨 Server 协作不需要 orchestrator

- **状态**：Accepted
- **日期**：2026-05-13（W2 KR 当日验证）
- **决策者**：项目作者

---

## Context（背景）

investment-agent 有 4 个 MCP Server（memory / finance / news / corporate_actions）。一个典型用户问句 "腾讯为什么跌" 需要：

1. 拉 `finance.get_quote` 看当前价
2. 拉 `finance.get_history` 看近期走势
3. 拉 `news.get_news` 看消息面
4. 综合输出

直觉做法：写一个 `orchestrator` 模块，硬编码 "因果类问题 → 并取 quote + history + news" 的路由逻辑。

但 LLM 本身已经是个推理引擎。它读完 4 个 Server 的 `description` 后，能否自主决定调用顺序？

---

## Decision（决策）

**不写 orchestrator**。每个 Server 自己写好 description 边界（什么时候该调、什么时候不该调），由 LLM 自主决定调用顺序。

---

## Consequences（结果）

### 正面

- ✅ **代码量减少**：没有 orchestrator 模块 = 少一层抽象 = 少一处 bug 源
- ✅ **工具池线性扩展**：3 Server → 4 Server 协作仍稳定（5/13 + 5/14 实测）。加 Server 只需写好 description，不用改 orchestrator
- ✅ **跨客户端一致**：orchestrator 写在哪里都是问题（写在 Agent 里→Desktop 不能用、写在 Server 里→耦合）。不写就没这个问题
- ✅ **涌现行为**：Case D' 出现 3 个未设计的涌现（金句逐字命中 / 主动澄清 / 协同提议）——orchestrator 硬编码场景下不会有

### 负面

- ⚠️ **行为不可完全预测**：同样问句不同 session 可能调用顺序不同（Claude 的规划有 temperature）
- ⚠️ **description 设计要求高**：边界写不清楚 LLM 会乱调（5/12 description A/B 实验数据：v0 短描述在语义陷阱 case 上行为偏差）
- ⚠️ **工具池上限未测**：3 Server 协作仍成立，10+ 工具时 description 互相干扰的临界点未知

---

## Alternatives Considered（备选方案）

| 方案 | 优 | 劣 | 为什么没选 |
|---|---|---|---|
| 写 orchestrator 模块（硬编码路由） | 行为完全可预测 | 每加一个 Server 要改一处、跨客户端难复用 | 工具池扩展线性瓶颈 |
| 用 LangGraph Supervisor-Worker | 框架支持图状编排 | 引入框架依赖、Supervisor 也是 LLM 本质上没省事 | W7 才考虑（多 Agent 工作流场景），单 Agent 用 overkill |
| 用 ReAct + 自己写循环 | 完全可控 | 重新发明 claude-agent-sdk 已有的 loop | 重复造轮子 |
| 让 LLM 自主编排 ★ | 零代码、可扩展、涌现 | 行为有 variance、description 要求高 | description A/B 10/10 验证后选定 |

---

## 实测证据

### Case A — "腾讯为什么跌"（5/13）

LLM 自主并取 `finance.get_quote` + `finance.get_history` + `news.get_news`，3 路并取。无 orchestrator。

### Case D' — TSLA 持仓建议（5/14）

LLM 自主调用 7 次工具（跨 4 Server），其中 `corporate_actions.get_corporate_actions` 是 description nudge（"涉及历史价位先调本工具"）触发的——证明 description 边界写好后，LLM 能把"新工具加入工具池"这件事自己接住。

详见 [diagrams/03-case-d-sequence.md](../diagrams/03-case-d-sequence.md)。

---

## 后续验证

- ✅ 3 Server 协作稳定（5/13 + 5/14 多次复现）
- 🔲 工具池扩展到 10+ 时是否仍稳定（**W7 前补**）
- 🔲 description 互相干扰的临界点测试（"两个 Server 的 description 都说自己处理 X" 场景）

---

## 关联

- 跨 Server 协作 8 个 case 全文：[cross-server-cases.md](../../../../../memory/projects/investment-agent/cross-server-cases.md)
- description A/B 实验设计：[ADR-005](./005-description-vs-inputschema.md)
- 上游决策：[ADR-001 选 MCP](./001-why-mcp-not-langchain.md)
