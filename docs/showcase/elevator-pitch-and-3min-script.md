# 电梯演讲 + 3 分钟项目陈述脚本

> 用途：面试现场口述。3 分钟脚本与 5 分钟录屏共享同一骨架（钩 / 架构 / 反例 / 升华），通道 2 抽查可复用。
> **关键金句加粗，要能脱口而出**。


---

## 2026-06 P1 Production Research Loop 版

用途：介绍 P1 当前最新成果。早期 MCP / corporate-actions 反例故事仍然可以作为深入追问材料；这一版更适合讲 production agent、eval、guardrail 和 traceability。

### 30 秒版

> 我最近把 investment-agent 推进到 P1 Production Research Loop：它不是预测股票涨跌，而是把投资研究问题转成可追踪、可审计、可回归测试的 research memo。核心链路是工具输出先变成 Source 和 Fact，LLM 只能生成绑定证据的 Claim，最后经过 Guardrail、Trace 和 Case Runner 验证。Day 6 已经有 deterministic memo renderer、evidence table、13 条回归 case，并且 pytest 18 条通过。

### 1 分钟版

> investment-agent P1 的目标是做一个 production-shaped finance research agent，不是交易建议机器人。它从 quote、history、news、corporate actions 和 preferences 工具拿数据，然后通过 normalizer 转成 Source 和 Fact。LLM synthesizer 只负责把这些事实组织成 Claim，每个 Claim 必须通过 Evidence 绑定回 Fact 和 Source。
>
> 输出前会跑 guardrail，检查不能直接建议买卖加减仓，关键 claim 要有证据，source 要有 timestamp，输出里要包含风险、unknowns 和 human confirmation points。每次 run 会写 JSONL trace，case runner 再用 10 条 direct-advice boundary cases 和 3 条 data-quality cases 做回归。Day 6 加了 deterministic investment memo renderer，memo 不是新一轮自由生成，而是 audited research state 的投影。

### 3 分钟版

> 我现在重点讲 investment-agent 的 P1 Production Research Loop。这个项目的目标不是让模型预测股价，也不是给用户买卖建议，而是验证一个金融垂直 agent 怎么把 messy tool outputs 变成可追踪、带 guardrail、可回归测试的 research memo。
>
> 整个链路是 User Query -> Live Tool Provider -> Tool Result Normalizer -> Source / Fact -> LLMResearchSynthesizer -> Claim / Evidence Binder -> Guardrail Evaluator -> Investment Memo Renderer -> Trace JSONL -> Case Runner。
>
> 这里最重要的设计是我没有把工具返回的原始 JSON 直接塞进 prompt。工具输出必须先被 normalizer 转成 Source 和 Fact。Source 表示信息从哪里来，比如 quote tool、news RSS、corporate actions 或未来的 filing document；Fact 表示从 source 里抽出来的可用证据，比如 latest_price、news_tone、stale_quote、missing_news、conflicting_signals。
>
> LLM 的职责是 synthesis，但不是自由发挥。它生成 Claim，每个 Claim 必须通过 Evidence 绑定回已知 Fact 和 Source。这样 final answer 里的关键判断都能追到来源、时间戳和 fact metric。
>
> 然后 guardrail 是 post-generation gate，不靠 prompt 自觉。它检查输出不能变成 buy / sell / add / trim / hold / short / clear-position advice，关键 claim 要有 evidence，source 要有 timestamp，答案要包含风险、unknowns 和 human confirmation points。
>
> Trace 是我认为 production loop 里很关键的一环。每次 run 都会写 JSONL，包括 tool_result、fact_added、synthesis_result、claim_added、memo_rendered 和 guardrail_result。这样如果 live run 出错，我可以知道是哪一步出了问题，然后把它沉淀成 regression case。
>
> Eval 方面，现在有 10 条 direct-advice boundary cases，覆盖买、卖、加仓、减仓、持有、做空、清仓等中文表达；还有 3 条 frozen data-quality cases，覆盖 stale quote、missing news 和 conflicting signals。当前验证里 ruff 全过，pytest 45 passed，fixture all suite 13/13（Engineering correctness: 100%）；此前 live boundary suite 10/10。
>
> Day 6 还加了 deterministic investment memo renderer，输出固定 memo sections：研究结论、原因排序、发生了什么、关键依据、风险与不确定性、还需要确认和数据来源与时效。这个 renderer 不是再让 LLM 写一遍，而是把已经审计过的 Source / Fact / Claim / Evidence 投影成 memo。
>
> 所以这个项目当前最能体现的是：evidence in，constrained synthesis，policy gate，trace out，regression back into the system。

关联主文档：docs/P1_FINAL_NARRATIVE.md

## 30 秒电梯版 · 75 字

**适用场景**：自我介绍尾段、HR 一面开场、LinkedIn 简介、recruiter cold call

> 我在做一个叫 **investment-agent** 的金融垂直 MCP Agent，**3 个 MCP Server** 协作的架构。最值得讲的不是架构本身，是上线后我发现 **LLM 训练知识不稳定** —— 同一天两次回答都不一样。我用 **24 小时**建了一个 ground truth 兜底架构，沉淀出"**触发器 / 事实 / 建议**"三层知识分层设计模式。

**节奏建议**：

| 段 | 时长 | 内容 |
|---|---|---|
| 定位 | 5s | "金融垂直 MCP Agent、3 Server 协作" |
| 钩 | 8s | "最值得讲的不是架构，是 LLM 知识不稳定" |
| 数 | 7s | "24 小时反例闭环" |
| 升华 | 10s | "沉淀出知识分层设计模式" |

---

## 1 分钟扩展版 · 200 字

**适用场景**：技术一面"先介绍一下你最近的项目"开场

> 我在做一个 **investment-agent**，是金融垂直的 MCP Agent。架构上是 4 个 MCP Server 协作 —— 持仓、行情、新闻、加上一个我后来加的公司行动事件。Claude Desktop / Code / 自研 Agent **三个客户端零修改复用**同一份 Server，跨 Server 工具调用顺序**由 LLM 自主决定，不需要 orchestrator**。
>
> 量化上跑过几组：跨 Server 拆股事件判别 **4/4**，description A/B 实验在 10 类语义陷阱 case 上行为正确率 **10/10**。
>
> 但项目里最有意思的其实是个反例 —— **5/13 晚上我发现 LLM 训练知识不稳定**，同一持仓在不同 session 给出 **15:1 vs 3:1** 不同拆股精度，复权后成本相差 5 倍。我用 **24 小时**设计并落地了 `corporate_actions_server` 作为 ground truth 兜底，从中抽象出"**触发器 / 具体事实 / 决策建议**"三层知识分层模式，背后的机制层归因是 **LLM 注意力机制的压缩偏移**。

---

## 3 分钟主版 · 完整脚本

**适用场景**：一面"介绍一个你主导的项目"、终面"讲一个最近遇到的挑战"

### 第 1 段 · 钩（30 秒）

> 我介绍一个个人项目，叫 **investment-agent**，金融垂直的 MCP Agent。
>
> 表面看是 3 MCP Server 协作的常见架构，但项目里最值得讲的是一个**反例闭环** —— 我发现 LLM 训练知识在长 session 下不稳定，**24 小时**内设计并落地了 ground truth 兜底架构，沉淀出一套可复用的知识分层设计模式。
>
> 我从架构、量化、反例、升华四个角度讲。

**金句**：✋ **「反例闭环」「24 小时」「知识分层设计模式」**

---

### 第 2 段 · 架构（45 秒）

> 架构上是 4 个 MCP Server：**memory** 管持仓和偏好、**finance** 拉行情、**news** 拉多语言新闻、**corporate_actions** 提供公司行动事件 ground truth。
>
> 三个客户端零修改复用同一份 Server —— **Claude Desktop**、**Claude Code**、加上 W3 在做的**自研 Agent**。
>
> 关键工程决策有两个：
>
> 第一，**跨 Server 协作我没写 orchestrator**。每个 Server 写好 description 边界后，LLM 自主决定调用顺序。3 Server 实测下，因果类问题（比如"腾讯为什么跌"）Claude 会自动三路并取 quote、history、news。
>
> 第二，description 写边界，inputSchema 约束结构 —— 两者职责分工。description A/B 实验在 10 类含语义陷阱的 case 上行为正确率 **10/10**。

**金句**：✋ **「无 orchestrator」「三客户端零修改复用」「description 写边界」**

---

### 第 3 段 · 反例（75 秒，核心段）

> 真正值得讲的是 5/13 晚上的发现。
>
> 那天 W2 KR 刚验收完，跨 Server 拆股事件判别 **4/4 通过**，包括 NVDA、TSLA、AAPL、港股阿里。
>
> 当晚我发现同一份 **TSLA 50 股 @$1200** 持仓，Claude 在同一天两次 session 给出了完全不同的拆股精度 —— 早上正确识别 **2020-08 5:1 + 2022-08 3:1 累计 15:1**，复权后成本 $80、浮盈方向正确；晚上只识别 2022 年那次 **3:1**，复权 $400、浮盈方向反转。
>
> 这不是训练数据过时 —— 是 **LLM 注意力机制天然存在压缩偏移**，在长 session、多工具调用、输出长建议的上下文压力下，关键事实被概括化处理。
>
> 我当晚做了归因，第二天上午用 yfinance + SQLite 缓存实现了 `corporate_actions_server`，给 memory 和 finance 的 description 加了 nudge —— "涉及历史价位判断时先调本工具"。
>
> 当天下午 Case D' 实测 4/4 维度全过：工具调用 **4 变 7**、复权后成本 **$400 变 $80**、浮盈方向 **-64% 反转 +457%**。还出现了 3 个未设计的涌现行为，比如 Claude 主动弹 4 选项让我澄清持仓时点。
>
> 全程 **24 小时**，从发现反例到验证修复。

**金句**：✋ **「注意力机制压缩偏移」「不是训练数据过时」「4→7」「$400→$80」「+457%」「24 小时」**

---

### 第 4 段 · 升华（30 秒）

> 从这个反例我抽象出一套通用模式 —— **三层知识分层**：
>
> 第一层**触发器**用 LLM 训练知识，比如"这个价位看起来不对"；第二层**具体事实**用外部 ground truth，**必须 LLM hop = 0**；第三层**决策建议**让 LLM 综合推理。
>
> 核心原则：**LLM 提示要存在感、不要权威感** —— 提醒用户去核对，不要直接给数字让用户当真。
>
> 这套模式后面会复用到 W6 记忆系统：实体记忆走事实层、召回策略走判断层。

**金句**：✋ **「LLM hop = 0」「存在感不要权威感」「触发器 / 事实 / 建议」**

---

## 4 维评分自查表（按 LEARNING_PROFILE 抽查标准）

每次练习后自评：

| 维度 | 标准 | ✅ / 🟡 / ❌ |
|---|---|---|
| **理解准确性** | 反例归因是"注意力机制压缩偏移"不是"训练数据过时" | |
| **结构性** | 钩 / 架构 / 反例 / 升华 四段清晰，过渡自然 | |
| **关键词命中** | 加粗金句**全部脱口而出**，无大白话替代 | |
| **案例支撑** | 数据具体（4/4、10/10、$400→$80、+457%、24h） | |

任一维度 🟡 / ❌ → 进"待打磨表达"清单，下次抽查继续。

---

## 高频追问预判 · 备答库

面试官 80% 概率会追问以下问题。提前备好答案（每条 30 秒内答完）：

| Q | 速答提纲 |
|---|---|
| 为什么不让 LLM 联网搜？ | `web_search` 是 hop=1（读自然语言再抽数字），关键事实必须 hop=0。详见 ADR-003 决策树 |
| 怎么知道哪些信息要走结构化、哪些可以让 LLM 处理？ | 看两个维度：保真度要求 + LLM hop 次数。关键数字/日期/ID 必须 hop=0，模糊判断/意图识别可以 hop>0 |
| 没有 orchestrator 怎么保证调用顺序对？ | 不是保证"顺序对"，是 description 边界写清楚。LLM 自主规划。description A/B 10/10 验证 |
| 涌现行为不就是 LLM 随机的吗？ | 不是随机。description nudge 后的可复现行为。Case D' 三个涌现都来自 description 边界设计的"溢出效应" |
| 工具池扩展到 100 个还成立吗？ | 实测到 4 Server 仍稳定。10+ 的边界还没测，是 W3 的待办之一 |
| 复杂目标多轮执行怎么防止 LLM 走偏？ | 不靠模型自己记住，把 Goal Brief、Execution Plan、Decision Log、验收标准外化成稳定状态；每 3-5 个子任务做一次漂移审计。关键金句：不要让关键控制面只存在于上下文里 |
| MCP 相比 LangChain 优势在哪？ | 跨客户端复用。同一份 Server 被 Desktop / Code / 自研 Agent 零修改使用。详见 ADR-001 |
| 你怎么发现这个反例的？ | 同一天两次同问句答案不一致，刚好被我撞到。这是为什么我现在每个 case 都跑 2-3 次 session 看稳定性 |
| 这个项目花了多久？ | 主线 W1-W2 加反例闭环：约 4 天纯实施时间（5/11-5/14）。架构思考 + 沉淀 + 抽查另算 |

---

## 练习方法

1. **第一周**：每天对着镜子完整讲 3 次（30s / 1min / 3min 各一次），录音回放
2. **第二周**：找 ChatGPT/Claude 当面试官，按 4 维评分让 AI 打分
3. **第三周**：找朋友模拟面试，**对方追问任意 3 个备答库问题**
4. **临投递前一周**：每天复述一次主版（3 min），保持口腔记忆

**判定可投递的标准**：3 min 主版能在不看稿的情况下，**每次都把金句 100% 命中**，4 维评分至少 3 项 ✅。

---

## 关联

- 录屏脚本（5 min 版，含画面节奏）：将与本脚本共用骨架（待补）
- 反例叙事原文：[case-study-corporate-actions.md](./case-study-corporate-actions.md)
- 复杂目标防漂移方法论：[goal-drift-control.md](../methodology/goal-drift-control.md)
- 简历段落（口述时的硬核数据来源）：[resume-snippet.md](./resume-snippet.md)
- 通道 2 抽查记录：`learning/LEARNING_PROFILE.md` 待抽查清单
