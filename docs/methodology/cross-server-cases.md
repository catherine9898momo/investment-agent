---
tags: [investment-agent, mcp, cross-server, domain-intelligence, stock-split, claude-desktop, news-server, knowledge-stability]
domain: ai-engineering
type: project-cases
project: investment-agent
updated: 2026-05-13
---

# 跨 MCP Server 协作 + 金融常识介入精度 — 实测案例集

> 实验日期：2026-05-13（W1 D3）
> 环境：Claude Desktop（含 ToolSearch 平台层）
> 接入 Server：investment-memory（持仓/关注/偏好）+ investment-finance（实时报价/历史 K 线）
> 实验目的：验证两个 Server 同时挂载下，Claude 是否能自动选择正确工具顺序 + 金融领域常识是否能精确介入

---

## 工程结论先行

1. **跨 Server 协作不需要 orchestrator**：每个 Server description 各自写清楚就足够，Claude 自动选择正确调用顺序（2 Server → 3 Server 都成立）
2. **Claude 的金融常识介入不是"价位异常检测"，是"金融事件识别"**——会区分"真有拆股"和"真实下跌"两种价格变化
3. **判别力数据**：4 个拆股相关 case，**4/4 精确判断**（该提的提、不该提的不提）
4. **⚠️ 但 LLM 训练知识不稳定**——同一持仓 / 同一拆股事件，不同 session 可能给出不同精度（TSLA Case 5 早识别 15:1 + Case 4 晚漏 5:1 只给 3:1）。详见 `llm-knowledge-stability.md`
5. **简历叙事锚点**：从"工具拼接器"升级到"领域常识 × 实时数据 × 持久化记忆"三层融合的业务智能，**并主动识别并修复 LLM 知识不稳定性**

---

## 实验 Case 集（4 个）

### Case 3：基线跨 Server — "我的 NVDA 浮盈多少？"

**持仓数据**：NVDA 100 股 @$850（在 NVDA 10:1 拆股之前的价位）

**Claude 行为**：
- 工具序列：`ToolSearch → memory.list_portfolio → finance.get_quote(NVDA)`
- 数学结果：100 × $850 = $85,000 成本，100 × $219.44 = $21,944 市值，浮亏 -$63,056（-74.18%）
- **拆股提醒**：主动提醒 NVDA 2024-06 做过 10:1 拆股，给出修正方案"实际持仓应为 1000 股、成本 $85、浮盈 +$134,440"

**判定**：✅✅✅
- 跨 Server 调用顺序正确（先查持仓，再拉现价）
- 拆股识别精确（年月 + 比例 + 复权计算 + 修正判定方向）

---

### Case 4：判别力 — "我的 AAPL 浮盈多少？"

**持仓数据**：AAPL 100 股 @$150（**AAPL 2020-08 拆股后的正常价位**）

**Claude 行为**：
- 工具序列：`ToolSearch → memory.list_portfolio → finance.get_quote(AAPL)`
- 数学结果：100 × $150 = $15,000 成本，100 × $292.68 = $29,268 市值，浮盈 +$14,268（+95.12%）
- **不提拆股**——AAPL 历史拆股是 2020-08（4:1），但 $150 是 post-split 完全正常的价位，本来就不该触发

**判定**：✅
- Claude 没被"AAPL 历史上有过拆股"这件事干扰
- 关键能力：**结合具体成本数字判断是否处于异常区间**，不是"看到拆股过的股票就提"

---

### Case 5：金融知识深度巅峰 — "我的 TSLA 浮盈多少？"

**持仓数据**：TSLA 50 股 @$1200（**两次拆股前的价格**，对应实际复权成本 $80）

**Claude 行为**：
- 工具序列：`ToolSearch → memory.list_portfolio → finance.get_quote(TSLA)`
- 数学结果：50 × $1200 = $60,000 成本，50 × $445 = $22,250 市值，浮亏 -$37,750（-62.9%）
- **拆股提醒原文**：

  > ⚠️ 提醒：1,200 的成本价远高于 TSLA 历史最高(拆股后),很可能是拆股前的成本未做复权调整。
  > TSLA 在 **2020-08(5:1)** 和 **2022-08(3:1)** 做过两次拆股,如果你的买入早于 2022-08,
  > 实际复权后成本应为 **1200 ÷ 15 = 80 USD**,那样反而是浮盈。
  > 要不要我帮你核对一下买入日期再修正？

**判定**：✅✅✅（满分）

这条提醒完整命中 6 个金融常识点：
1. 识别 $1200 远高于 TSLA post-split 历史最高
2. 推断"拆股前成本未复权"作为最可能解释
3. **精确列出两次拆股的年月**（2020-08、2022-08）
4. **精确列出每次拆股比例**（5:1、3:1）
5. **正确做复权计算**（1200 ÷ 15 = 80）
6. **推断判定方向反转**："反而是浮盈"——因为 $80 < $445

**这是真正的"垂直 Agent vs 通用 Agent"的本质分水岭**。

---

### Case 6：误触发陷阱 — "我的 09988.HK 浮盈多少？"

**持仓数据**：09988.HK（阿里巴巴港股）50 股 @HK$280（高点买入，但**阿里并无拆股事件**）

**Claude 行为**：
- 工具序列：`ToolSearch → memory.list_portfolio → finance.get_quote(09988.HK)`
- finance_server 内部 normalize：09988.HK → 9988.HK（前导零修复）
- 数学结果：50 × HK$280 = HK$14,000 成本，50 × HK$133.30 = HK$6,665 市值，浮亏 -HK$7,335（-52.39%）
- **不提拆股**——阿里没有拆股事件，价位下跌是真实的市场下跌（从 2020 高点 $300+ 跌到 $130 区间）

**判定**：✅（关键判别力 case）

这个 case 是整个实验的判别力测试最关键的一题：
- 阿里 -52% 的下跌幅度足够触发"价位异常检测"
- 如果 Claude 是"看到大幅价差就乱提拆股"的浅规则，这里会暴露
- Claude **没有误触发**，证明它真的有"阿里没拆股"这个具体知识

**附加观察**：
- Claude 也没有主动说"看起来你在高点买入"——这是个**没加分但也没扣分**的中性表现，从"恰到好处"角度可以接受
- 后续可考虑实验：是否需要在 description 里引导"对显著浮亏给出市场背景"

---

## 判别力矩阵汇总

| 股票 | 成本价 | 实际事件 | 期望 Claude | 实际 | 判定 |
|---|---|---|---|---|---|
| NVDA $850 | 拆股前价位 | 2024-06 10:1 拆股 | 提 | ✅ 提，精确 | ✅ |
| TSLA $1200 | 两次拆股前 | 2020-08 5:1 + 2022-08 3:1（总 15:1） | 提，比例 15 | ✅ 提，列出两次具体日期+比例+复权计算 | ✅✅ |
| AAPL $150 | post-split 正常 | 2020-08 4:1 拆股（但当前价位正常） | 不提 | ✅ 不提 | ✅ |
| 09988.HK HK$280 | 高点买入 | **无拆股**，真实市场下跌 | 不提 | ✅ 不提 | ✅ |

**结论：4/4 全部精确判别**。Claude 不是"看到价差就乱提"，是真的内化了"哪些股票什么时候拆过股"的具体金融历史知识。

---

## 工程视角的工程结论

### 跨 Server 协作

| 现象 | 工程含义 |
|---|---|
| Claude 自动选择正确顺序（持仓 → 现价） | description 写好就足够，**不需要 orchestrator** |
| 两个 Server 同时挂载下，工具调用没有互相干扰 | description 隔离 + 命名空间（investment-memory / investment-finance）足够清晰 |
| ToolSearch 出现在每个 case | 平台层 retrieval 是常态，工具池 8+ 后必然 |
| finance_server 的 normalize_symbol 在 09988.HK 自动生效 | LLM 不需要知道前导零陷阱，应用层兜底 |

### 领域智能介入

| 现象 | 工程含义 |
|---|---|
| Claude 内化了 NVDA / TSLA / AAPL 的拆股历史精确日期 | LLM 训练数据里的金融事件是"免费的领域知识"——不需要外挂知识库 |
| Claude 不在 AAPL / 09988.HK 上误触发 | 领域知识是"精确触发"而不是"看到关键词就触发" |
| Claude 主动给出修正方案（NVDA 修正为 1000 股、TSLA 复权计算） | LLM 不止给数据，给**决策建议**——这是 P6+ 工程师面试讲"业务智能"的硬证据 |

### 反向风险（未来需要观察）

- **金融知识可能过期**：如果未来 NVDA 又拆股一次而 LLM 训练数据没更新，会给出错误的复权计算
- **金融知识可能错误**：对小盘股、A 股、港股的具体事件，LLM 知识深度未知，需要更多 case 验证
- **应该有"知识截止时间"提示**：未来 description 里可以加"如果对最近 6 个月的拆股/合并事件不确定，明确说出不确定"

---

## 简历叙事最终版（基于 4/4 数据）

> investment-agent 在跨 MCP Server 协作场景下展现"金融垂直领域智能"：
> 用户问任何持仓的浮盈，Agent 自动串调 portfolio + finance 两个 Server，完成市值计算。
> **进一步，Agent 能在 4 个边界 case 上精确触发拆股提醒**：
> - NVDA（2024-06 10:1 拆股）→ ✅ 提
> - TSLA（2020-08 5:1 + 2022-08 3:1）→ ✅ 提，**列出两次精确日期+比例+复权计算**
> - AAPL（无近期拆股）→ ✅ 不提
> - 09988.HK（无拆股但 -52% 真实下跌）→ ✅ 不提
>
> 证明 Agent 能区分"价位异常"和"公司行动事件"两类信号，是**真正的垂直智能而非通用对话**。
> 工程上仅靠两个 Server 各自写好 description，没有额外的 orchestrator 或 prompt 工程。

---

---

## D4 增加：news_server 上线 + 三 Server 协作（2026-05-13 晚）

### Case A: NVIDIA 最近一周新闻 → ✅ 单 Server 基线

**Claude 行为**：
- 工具：`ToolSearch → news.get_news("NVIDIA", 7, "en")`
- 把 20 条新闻按 5 大主题归类：财报前预热 / 股价市值 / 中美关系 / 业务合作 / 其他
- 主线判断："Q1 财报前华尔街集体看多 + 黄仁勋被排除访华团"
- 一线媒体覆盖：Bloomberg / Forbes / Barron's / Reuters / NYT / NVIDIA Newsroom / MarketWatch / Seeking Alpha

**判定**：✅✅ 不只是给数据，是有逻辑的归类 + 主线判断。

### Case B: 贵州茅台最近新闻 → ✅ 中文召回质量超预期

**Claude 行为**：
- 工具：`ToolSearch → news.get_news("贵州茅台", 7, "zh")`（自动选 zh）
- 抓到的关键词都是深度财经术语：
  - "合同负债骤降 65%"
  - "存货周转天数拉长（与汾酒同样情况）"
  - "5/12 主力资金净卖出 11.23 亿元"
  - "细分食品指数估值低于近十年 88% 时间"
  - "总工程师王莉现身说明会"
  - "2026 年不设经营目标 / 全面向 C 改革"

**判定**：✅✅✅ Google News 中文召回比预期好得多，配合 Claude 整理能力，输出接近"专业研报摘要"。

### Case C: "腾讯最近为什么跌？" → ✅✅✅ Claude 主动多源编排

**Claude 行为**：
- 用户问"为什么跌"是**因果推理问题**，没指定要查行情还是新闻
- Claude 自己决定三路并取：
  - `finance.get_quote(0700.HK)` 确认跌幅
  - `finance.get_history(0700.HK)` 看趋势
  - `news.get_news("腾讯", zh)` 找原因
- 归纳 5 个原因：AI 叙事掉队 / 腾讯音乐 Q1 利润 -51% / 收购喜马拉雅附条件获批 / Prosus 持续套现 / 财报前观望
- 一句话总结："不是单一利空，而是 AI 竞争力被质疑 + 子公司业绩下滑 + 大股东持续套现 + 财报前避险几股力量叠加"

**判定**：✅✅✅ 真正的多 Server 工程价值证明——Server 各管一摊，**LLM 自己编排路径**。

### Case D（**W2 KR 终极验收**）: "持仓里的 TSLA：拉新闻 + 当前价 + 我的成本，给个建议"

**Claude 行为**：一句自然语言触发 **4 个工具调用**：
1. `memory.list_portfolio` 拿持仓数据
2. `finance.get_quote(TSLA)` 拿当前价
3. `finance.get_history(TSLA, 7)` 看一周走势
4. `news.get_news("Tesla", 7, "en")` 拉新闻

**输出结构**：
- TSLA 持仓快照表（50 股 / $1200 成本 / 当前 $431.08 / 浮亏 -$38,446 (-64.1%)）
- ⚠️ **拆股提醒触发**（但这里出现了知识不稳定问题，见下文）
- 一周走势 K 线（5/4-5/12，累计 +9.8%，5/11 触及 $445 一周高点）
- 新闻面归纳：利好 3 条 + 利空 4 条
- 建议："持有为主，不加仓"+ 3 条推理依据（不止损 / 不加仓 / 持有观察）

**判定**：✅✅✅✅ **W2 全部 KR 达成**——一句话覆盖了三 Server 协作 + 业务建议 + 推理透明度。

### ⚠️ Case D 的反例：LLM 拆股知识不稳定

| Case | 时间 | Claude 拆股说明 | 复权 |
|---|---|---|---|
| **Case 5 上午** | 2026-05-13 早 | "2020-08 (5:1) + 2022-08 (3:1)，**共 15:1**" | 1200 ÷ 15 = **80 USD** |
| **Case D 晚上** | 2026-05-13 晚 | "2022 年 8 月 **1:3 拆股**" | 1200 ÷ 3 ≈ **400 USD** |

历史事实：TSLA 真实拆股两次（2020-08 5:1 + 2022-08 3:1，共 15:1）。**Case 5 对、Case D 漏**。

**这个反例修正了昨天"LLM 训练知识可白嫖"的结论**：

> LLM 训练知识是垂直 Agent 的"高质量提示信号"，但**不是 ground truth**。
> 同一事件在不同 session、不同上下文压力下可能输出不同精度的答案。
> 修复方向：建 `corporate_actions_server` 提供结构化拆股数据，LLM 只做"触发器"，权威数字走工具。

详见 `llm-knowledge-stability.md`。

---

### Case D' (post-fix) — 2026-05-14 闭环验证

**前置条件**：corporate_actions_server 已上线并注册到 Claude Desktop（4 Server 工具池）。

**同一 prompt（一字不改）**："持仓里的 TSLA：拉新闻 + 当前价 + 我的成本，给个建议"

**Claude 行为**：一句自然语言触发 **7 个工具调用**（5 + 2 分两批）：
1. `memory.list_portfolio` 拿持仓
2. `finance.get_quote(TSLA)` 拿当前价（发现 $1200 vs $445 异常）
3. `finance.get_history(TSLA, 7)` 看走势
4. `news.get_news("Tesla", ...)` 拉新闻
5. **`get_corporate_actions(TSLA)`** ← 新增的关键调用
6-7. 用户选了"2020-08 拆股前"后，又调用了 list_portfolio + get_quote 重算

**触发器表达**（精确命中"知识分层"模式）：
> "成本 $1200 vs 当前价 $445 异常——大概率是拆股前价格未复权。先查 TSLA 历史拆股事实再算。"

**关键输出修正**：

| 维度 | Case D (5/13) | Case D' (5/14) |
|---|---|---|
| 拆股识别 | 仅 2022-08 (1:3) | **2020-08-31 5:1 + 2022-08-25 3:1 累计 15:1** |
| 复权后成本 | $400 | **$80** |
| 浮盈方向 | -64%（浮亏） | **+457%（浮盈）** |
| UX 处理 | 自信一口判定 | **先弹 4 选项让用户确认持仓时点** |
| 工程协同 | 单向输出 | **主动提议更新 portfolio 口径** |

**判定**：✅✅✅✅ **反例闭环成功 + 涌现 3 个未设计行为**

1. 触发器表达逐字命中 llm-knowledge-stability.md 里的"知识分层"设计模式
2. 主动澄清持仓时点（4 选项 UX）—— LLM 提示要存在感、不要权威感的真实落地
3. 工具池间主动协同——提议改 portfolio 口径，是没人教过的涌现行为

**工程结论**：description 引导在 4 Server / ~10 工具池下足够稳定，无需 system prompt 干预。

详见 `learning/daily-lesson/2026-05-14-corporate-actions-loop-closure.md` 的"实测验收"节。

---

## D4 工程结论补充

| 现象 | 工程含义 |
|---|---|
| Case C 三路并取做因果推理 | LLM 在多 Server 场景下能自主选择"信息检索策略" |
| Case D 一句话 4 工具调用 | 自然语言 → 结构化任务编排，不需要 prompt 模板 |
| Case D 拆股提醒漏算 | LLM 训练知识在长输出 / 多焦点任务下精度下降 |
| Case B 中文召回质量 | Google News 多语言能力足够生产用 |
| 3 Server 同时挂载下无 description 干扰 | description 边界写好后，工具池规模可线性扩展 |

---

## 测试 fixture 状态

实验数据保留在 portfolio 中（用户决策）：
- AAPL 100 股 @$150
- TSLA 50 股 @$1200 ← **刻意保留拆股前价位**，用于回归测试
- 09988.HK 50 股 @HK$280
- NVDA 100 股 @$850（W1 D2 案例 1 残留，也是拆股前价位）
- 600519.SS 50 股 @¥1680（W1 D2 案例 2 残留）

将作为后续拆股提醒回归测试的复用基线。下次需要清理时直接 `store.remove_holding(symbol)` 即可。

### ⚠️ Fixture-preservation note（2026-05-14）

Case D'（5/14 实测）后 Claude 主动提议把 TSLA 改成 750 股 @ $80（复权后口径）。
**用户决策：保留拆股前口径不改**。

理由：portfolio 当前是测试 fixture，刻意保留拆股前价位是为了：
1. 后续修改 description / 新工具发布时复用此 case 做回归测试
2. 验证后续 LLM 模型 / Agent 框架升级时的拆股识别能力是否退化

改成 750@$80（复权后）会让 fixture 失去"触发拆股提醒"的能力，反例无法复现。

**任何 AI 不要自作主张去改这些 fixture。** 真实持仓数据另立 schema 字段或表区分。

---

## 关联资源

- 实验脚手架：`projects/investment-agent/experiments/desc_ab/`
- finance_server 实现：`src/mcp_servers/finance_server.py`（含 normalize_symbol 港股前导零修复）
- D2 description A/B 结果：`learning/daily-lesson/2026-05-12-description-ab.md`
- D3 当日学习记录：`learning/daily-lesson/2026-05-13-cross-server-day.md`
- 实验决策框架：`memory/shared/best-practices/experiment-decision-framework.md`
