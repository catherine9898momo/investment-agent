# ADR-005：description 写边界，inputSchema 约束结构

- **状态**：Accepted
- **日期**：2026-05-12（description A/B 实验当日）
- **决策者**：项目作者

---

## Context（背景）

MCP Tool 定义有两个字段会影响 LLM 行为：

- `description`：自然语言描述
- `inputSchema`：JSON Schema（required / enum / type）

社区文档对两者职责描述模糊。实操时容易把"什么时候调"塞进 description，但具体到边界条件（"看好特斯拉"是不是该调 add_holding？）不知道写在哪。

需要明确两者的职责分工。

---

## Decision（决策）

**两者分工互不替代**：

| 字段 | 解决什么失败模式 | 写什么 | 不写什么 |
|---|---|---|---|
| `description` | **决策错**（语义层）| 边界（什么时候**不**该调） + 推理余地（让 LLM 自主决定更高阶行为） | 重复 inputSchema 已表达的字段约束 |
| `inputSchema` | **结构错**（机械层）| required / enum / type / format | 业务规则、决策提示 |

---

## 设计原则

### description 的三条规则

1. **写边界比写功能更重要**
   - ✅ "用于添加或更新一只股票到持仓。注意：用户说'看好'、'讨论'、'打算研究' 等非购买意图时**不要**调用本工具"
   - ❌ "添加一只股票到持仓"（LLM 训练数据见过太多"添加 X"模式，会误触发）

2. **留推理余地，不要写死流程**
   - ✅ "添加**或更新**一只股票" → Claude 自主推断出"加仓时先查再合并均价"
   - ❌ "添加一只股票（如已存在请先调 list_portfolio 再合并）" → LLM 死板执行

3. **为平台 retrieval 服务**
   - description 太短会在 embedding 空间表征贫弱，可能被 Claude Desktop 的 ToolSearch 在 retrieval 阶段就丢掉
   - 80-250 字是经验区间

### inputSchema 的约束

- **required**：缺了会业务出错的字段（如 `symbol`）
- **enum**：取值集合可枚举的字段（如 `market: "US" | "HK" | "CN"`）
- **type**：基础类型（`string` / `number` / `boolean` / `array`）
- **format**：日期、URL 等特殊格式

---

## Consequences（结果）

### 正面

- ✅ **5/12 A/B 实验数据**：v0（4-6 字短描述）vs v1（80-250 字含边界），10 个含语义陷阱 case，**v1 行为正确率 10/10**
- ✅ **decision 与 schema 解耦**：未来增加 schema 字段不会污染 description
- ✅ **平台 retrieval 友好**：description 80-250 字在 ToolSearch embedding 空间有足够表征
- ✅ **跨 Server 引用模式可成立**（如 finance.get_quote 在 description 里引用 corporate_actions——靠 description 边界写法）

### 负面

- ⚠️ **description 字数预算限制**：太长会挤占 system prompt token 预算
- ⚠️ **写好 description 要"反向思考"**：要列举 LLM **可能误用**的场景，比列举正用场景更耗脑
- ⚠️ **inputSchema A/B 未实测**：先验确定度高 + 学习增量低 + ROI 低，主动 skip 了（详见 [experiment-decision-framework.md](../../../../../memory/shared/best-practices/experiment-decision-framework.md)）

---

## Alternatives Considered（备选方案）

| 方案 | 问题 |
|---|---|
| description 写功能，inputSchema 写边界 | inputSchema 是 JSON Schema 标准，无法表达"语义边界"（LLM 不读 schema 推理决策） |
| 全用 description（不写 inputSchema） | 字段结构错（type / required）无法在 dispatch 层拦截，错误会更深 |
| 全用 inputSchema（description 留空） | LLM 不知道什么时候调；ToolSearch 召回失败 |
| **两者分工 ★** | 各司其职，A/B 实验 10/10 验证 |

---

## 实测证据

### 5/12 description A/B 实验（10 个语义陷阱 case）

| Case | 用户输入 | v0 行为 | v1 行为 |
|---|---|---|---|
| 中文别名 | "宁王" | v0 不识别 | v1 自动识别为宁德时代 |
| 多市场歧义 | "苹果" | v0 默认美股 | v1 主动澄清 US vs HK |
| 看好不买入 | "我看好特斯拉" | v0 误触发 add_holding | v1 不误触发 |
| 纯讨论 | "聊聊 NVDA 涨势" | v0 误触发 | v1 不误触发 |

**v1 行为正确率：10/10**

### 跨 Server 引用模式（5/14 引入）

`memory.add_holding` 和 `finance.get_quote` 的 description 里写："涉及历史价位判断时先调 `get_corporate_actions`"——靠 description 边界写法实现跨 Server nudge，无需硬编码路由。这是 ADR-002（无 orchestrator）的工程支撑。

---

## 后续验证

- 🔲 工具池 10+ 时 description 互相干扰临界点
- 🔲 inputSchema A/B 实测（如果 W4 后 ROI 提升再做）
- 🔲 description 字数边界（80 / 250 / 500 字的衰减曲线）

---

## 关联

- 实验决策框架（为什么 inputSchema A/B 主动 skip）：[experiment-decision-framework.md](../../../../../memory/shared/best-practices/experiment-decision-framework.md)
- 跨 Server 协作（description nudge 的应用）：[ADR-002](./002-cross-server-no-orchestrator.md)
- 知识分层模式（description 怎么协助分层落地）：[ADR-004](./004-knowledge-layering.md)
- 原始 daily-lesson：`learning/daily-lesson/2026-05-12-description-ab.md`
