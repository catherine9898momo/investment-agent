# ADR-004：三层知识分层设计模式

- **状态**：Accepted（作为通用模式沉淀）
- **日期**：2026-05-13
- **决策者**：项目作者

---

## Context（背景）

5/13 反例暴露：LLM 训练知识在同一天不同 session 给出不同精度。问题不是"LLM 不够聪明"，是"工程上没区分什么任务该让 LLM 做、什么任务不该"。

需要一套**通用决策标准**指导未来所有"LLM + 工具"的设计：哪些信息让 LLM 处理 OK，哪些必须走结构化工具。

---

## Decision（决策）

**三层知识分层模式**：

| 层 | 角色 | 提供者 | 容错率 | LLM hop |
|---|---|---|---|---|
| 1. 触发器 | "可能有问题"信号 | **LLM 训练知识** | 高 | 可 >0 |
| 2. 具体事实 | 日期 / 比例 / 数字 | **外部 ground truth** | **必须 0** | **必须 0** |
| 3. 决策建议 | 持有 / 加仓 / 减仓 | **LLM 综合推理** | 高 | 可 >0 |

**核心原则**：LLM 提示要存在感、不要权威感。

---

## 机制层归因

这一模式不是经验主义。背后的机制是：

> **LLM 处理非结构化自然语言由于注意力机制，天然存在对关键事实数据产生忽略、压缩等处理偏移的可能性。**

所以：

- **需要保真的信息**（数字 / 日期 / ID）必须 hop=0（结构化字段直给）
- **需要判断的信息**（意图 / 利好利空 / 异常感）可以 hop>0（LLM 越想越好）

详见 [llm-hop-minimization.md](../../../../../memory/shared/best-practices/llm-hop-minimization.md)。

---

## Consequences（结果）

### 正面

- ✅ **可被任何"LLM + 工具"项目复用**：从 investment-agent 抽象出来，不绑定金融领域
- ✅ **决策标准清晰**：设计工具时只需问"这条信息保真度要求几？hop 几次？"
- ✅ **简历叙事价值高**：机制层归因（注意力 → 压缩偏移）是 P6+ 工程师对 LLM 失败模式的认知证据
- ✅ **5/14 Case D' 真实验证**：Claude 自发输出"价位异常 → 先查历史拆股事实"——金句与设计文档措辞高度一致，证明模式可指导 LLM 行为

### 负面

- ⚠️ **设计阶段更复杂**：每个工具的每个字段都要做三层归类
- ⚠️ **边界模糊场景**：有些信息介于"事实"和"判断"之间（如"这家公司财报好吗"——好坏是判断、具体 EPS 是事实），需要拆开
- ⚠️ **不解决"工具本身坏"**：ground truth 工具如果挂了，第 2 层就失守（要 stale fallback 兜底）

---

## Alternatives Considered（备选方案）

| 方案 | 问题 |
|---|---|
| "全靠 LLM"（不分层） | 5/13 反例已证伪 |
| "全靠工具"（LLM 只做路由） | 失去 LLM 的综合推理价值（Case D' 涌现 3 行为不会出现） |
| 两层分（事实 vs 判断） | 漏掉"触发器"角色——触发器是 LLM 训练知识的合法用法，不应该被禁掉 |
| 五层 / 七层细分 | 过度设计，决策时无法快速判断 |
| **三层 ★** | 触发器（LLM）/ 事实（工具）/ 建议（LLM）覆盖所有 case，决策成本低 |

---

## 应用案例

1. **investment-agent corporate_actions**（5/14）
   - 触发器：LLM "$1200 看起来比现价高"
   - 事实：`get_corporate_actions` 返回 15.0
   - 建议：LLM "复权后浮盈 +457%，建议持有"

2. **未来 W6 实体记忆系统设计**
   - 触发器：LLM "这个用户提到 NVDA 了"
   - 事实：`entity_store.get("user_X", "holdings")` 返回结构化持仓
   - 建议：LLM "基于持仓 + 风险偏好给推荐"

3. **W4 weekly_analyst Agent**
   - 触发器：cron 触发"该出周报了"
   - 事实：各 MCP Server 拉数据
   - 建议：LLM 综合输出周报

---

## 后续验证

- ✅ Case D' 5/14 验证
- 🔲 W6 记忆系统应用本模式（实体 = 事实层，召回策略 = 判断层）
- 🔲 W7 多 Agent 工作流中三层映射到不同 Agent（事实 Agent / 判断 Agent）

---

## 关联

- 模式视觉化：[diagrams/02-knowledge-layering.md](../diagrams/02-knowledge-layering.md)
- 机制层归因：[llm-hop-minimization.md](../../../../../memory/shared/best-practices/llm-hop-minimization.md)
- 工程落地：[ADR-003 corporate_actions](./003-corporate-actions-data-source.md)
- 反例叙事：[case-study-corporate-actions.md](../case-study-corporate-actions.md)
