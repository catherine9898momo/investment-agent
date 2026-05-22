# 博客 2 · 3 个 MCP Server 协作，为什么我没写 orchestrator

- **平台**：知乎（首发）· Medium · 掘金（同步）
- **预期字数**：3000-4000 字
- **预期阅读时长**：8-10 分钟
- **目标受众**：后端架构师、协议设计者、做过 Agent 多工具调用的工程师
- **SEO 关键词**：MCP 协议、Multi-Agent、Tool Use、LangGraph、Orchestrator、Function Calling
- **引流目标**：GitHub repo

---

## 钩子段（opener）

> 当我决定让 Agent 调 3 个 MCP Server 协作时，第一反应是写一个 orchestrator —— 一个判断"什么问题该调哪几个工具、按什么顺序调"的路由模块。
>
> 但我没写。
>
> 实测下来，**LLM 自主决定调用顺序的 3 Server 协作不仅跑通了，还出现了 3 个我没设计的涌现行为**。这让我重新思考一个问题：在 Agent 架构里，**orchestrator 是不是一个被需求过度高估的抽象层**？
>
> 这篇文章讲我怎么走到"不写 orchestrator"这个决策的，以及它背后那个不太显眼但很关键的工程原则：**Agent 不是一个程序，Agent 是 LLM 本身**。

---

## 大纲

### Part 1 · 直觉做法 vs 反直觉做法（约 500 字）

**核心论点**：写 orchestrator 是直觉、不写是反直觉。

要点：
- 典型多工具调用场景：用户问 "腾讯为什么跌"，需要 quote + history + news 三路并取
- 直觉做法：写一个 `Orchestrator` 模块，硬编码"因果类问题 → 并取这三个工具"路由逻辑
- 为什么直觉这么强：传统软件工程教育，"路由"、"调度"是上层抽象的标配
- 反直觉做法：让 LLM 看完每个工具的 `description` 后自主决定调用顺序
- 为什么反直觉成立：**LLM 本来就是个推理引擎**，不要再造一个推理层

### Part 2 · 实测 — 3 Server 自主协作的 3 个 case（约 800 字）

**核心论点**：实测数据支撑"不写 orchestrator"。

要点：
- **Case A · "腾讯为什么跌"**（5/13 实测）
  - LLM 自主三路并取 `finance.get_quote` + `finance.get_history` + `news.get_news`
  - 输出含因果推理（"股价下跌 X%，从新闻看主要是 Y 事件")
- **Case B · "持仓 TSLA + 新闻 + 建议"**（5/13 实测）
  - 一句话触发 4 次工具调用
  - 跨 2 Server（memory + finance）
- **Case D' · TSLA 反例修复后**（5/14 实测）
  - 一句话触发 7 次工具调用
  - 跨 4 Server（memory + finance + news + corporate_actions）
  - 关键："corporate_actions 是 5/14 才加的工具，LLM 看了 description 后就接住了" —— 无需改 orchestrator

**配图**：03-case-d-sequence 时序图

### Part 3 · 为什么这套思路成立 —— 3 个支撑条件（约 600 字）

**核心论点**：不写 orchestrator 不是任何场景都成立，有 3 个工程条件。

要点：
1. **description 边界要写好**
   - description A/B 实验 10/10 数据
   - 关键：写"什么时候**不**该调"比写"做什么"更重要
   - LLM 训练数据里见过太多"添加 X"模式，模糊描述会让它在"看好"、"讨论"等无意图场景误触发
2. **inputSchema 约束结构错误**
   - description 解决决策错，inputSchema 解决结构错
   - 两者职责分工 —— 详见 ADR-005
3. **工具数量在合理区间**
   - 实测到 4 Server 仍稳定
   - 10+ 工具的边界没测，可能 description 互相干扰
   - 这是 LangGraph 等框架真正的应用场景：**工具池足够大、需要显式 Supervisor 才能管控**

### Part 4 · 跨 Server 引用模式 —— description 充当 nudge（约 500 字）

**核心论点**：跨 Server 协作不靠 orchestrator，靠 description 之间的"软引用"。

要点：
- 案例：5/14 加 `corporate_actions_server` 后，怎么让 LLM 知道要调它？
- 不是改 orchestrator，是改 `memory.add_holding` 和 `finance.get_quote` 的 description
- 加一句："涉及历史价位判断时先调 `get_corporate_actions`"
- 这个模式叫 **跨 Server description nudge**，本质是把 routing 信息**就近写到 description 里**
- 优势：新工具加入只需自己写好 description + 旧工具补一句 nudge，无中心模块改动
- 局限：工具池大了 description 会互相干扰，nudge 上限未知

### Part 5 · 涌现行为 vs 设计行为（约 500 字）

**核心论点**：不写 orchestrator 才能让"涌现行为"发生。

要点：
- Case D' 出现 3 个涌现：金句命中 / 主动澄清 / 协同提议
- 这些行为 description 里没写、orchestrator 也写不出来
- 涌现的本质：**description nudge 的溢出效应**
- 如果写了 orchestrator 硬编码场景，这种涌现会被"覆盖"
- 涌现行为是 P6+ 加分项 —— 面试官问"你做的 Agent 有什么超预期的表现"，能答出来就过线

### Part 6 · 什么时候应该写 orchestrator（约 500 字，平衡视角）

**核心论点**：不是反 orchestrator，是反"默认写 orchestrator"。

要点：
- 应该写 orchestrator 的场景：
  - 工具池 > 20，description 互相干扰
  - 多 Agent 工作流（W7 LangGraph Supervisor-Worker）—— 这才是 LangGraph 真正的应用场景
  - 强约束业务（金融合规、医疗诊断）—— LLM 自由决策风险太大
  - Human-in-the-loop 卡点
- 不该写 orchestrator 的场景：
  - 工具池 ≤ 10 且 description 边界清晰
  - 探索期单 Agent 项目
  - 需要涌现行为 / 灵活组合的场景

### Part 7 · 一句话总结（约 200 字）

> **Agent 不是另一个程序，Agent 是 LLM 本身**。orchestrator 的本质是"在 LLM 之外再造一个推理层"，但 LLM 已经是推理引擎了。Description 写好边界，把"路由信息"就近写到工具描述里，让 LLM 自主规划 —— 这是单 Agent 阶段最简单也最可扩展的做法。

### 行动召唤（CTA）

- 项目实测代码：链 GitHub repo
- description A/B 实验数据：链 daily-lesson 截图
- 完整决策记录：链 ADR-002
- 关注我系列下一篇：《触发器 / 事实 / 建议 — Agent 知识分层设计模式》

---

## 写作 Checklist

- [ ] 钩子段强调"反直觉" —— 这是知乎读者最爱的钩子
- [ ] Part 2 三个 case 用结构化叙述 + 工具调用序列（替代截图）
- [ ] Part 3 三个支撑条件用编号清单（读者易扫描）
- [ ] Part 4 "跨 Server description nudge" 是原创术语，要解释清楚
- [ ] Part 6 平衡视角必须有 —— 不平衡会被同行喷"标题党"
- [ ] 全文避免攻击 LangGraph / LangChain，留余地

---

## 标题 A/B 候选

1. **3 个 MCP Server 协作，为什么我没写 orchestrator**（信息密度 + 反直觉）
2. **Agent 不是程序，Agent 是 LLM 本身 — 一个反 orchestrator 的工程实践**（升华版）
3. **重新审视 Agent 架构：当 description 就是 routing**（学术风）
4. **不写 orchestrator 的 3 Server 协作 — 4/4 拆股判别 + 3 个涌现行为**（数据钩子）

**推荐 1**：知乎读者吃"反直觉 + 具体场景"。

---

## 关联

- 决策记录：[ADR-002](../adr/002-cross-server-no-orchestrator.md)
- description A/B 实测：[ADR-005](../adr/005-description-vs-inputschema.md)
- 跨 Server case 全文：[cross-server-cases.md](../../../../../memory/projects/investment-agent/cross-server-cases.md)
- 时序图：[03-case-d-sequence.md](../diagrams/03-case-d-sequence.md)
