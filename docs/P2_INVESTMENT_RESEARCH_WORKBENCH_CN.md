# P2 投资研究工作台建设方案

最后更新：2026-06-04

## 背景

当前 `investment-agent` 已经有 P1 research loop：live tools -> Source / Fact -> Claim / Evidence -> Guardrail -> Memo -> Trace / Eval。这个骨架解决的是“研究输出必须可追踪、不能直接给交易指令、关键结论要有证据”的生产边界问题。

下一步要补的是投资研究本身的厚度：公司事实、行业周期、估值、市场反馈、投资命题、反方证据和用户投资原则之间的稳定连接。

目标不是让系统直接回答“买不买”，而是让它帮助用户形成、维护和检验一个长期投资判断：

```text
我为什么研究这家公司？
它的企业价值如何产生？
当前价格隐含了什么预期？
哪些事实支持我的 thesis？
哪些事实会推翻我的 thesis？
新财报或市场波动到底加强还是削弱了原判断？
```

## 当前完成度判断

```text
研究安全边界 / 证据链 / trace / guardrail：60%-70%
真实投资研究能力：20%-30%
产品化研究工作台：10%-20%
```

已经具备：

- Source / Fact / Claim / Evidence / Guardrail / Trace 的主链路。
- memo renderer、evidence table、freshness notes、unknown/conflict sections。
- finance / news / corporate actions / memory 的基础 MCP tools。
- watchlist / portfolio / preferences 的配置雏形。
- boundary 与 data-quality regression case。

主要缺口：

- 估值层：PE、EV/EBITDA、FCF yield、ROIC、正常化利润、周期顶部/底部利润。
- 行业周期层：供需、库存、价格、capex、产能释放节奏。
- 产业链资金流层：hyperscaler capex 到 GPU、HBM、电力、冷却、光模块、EPC 的传导。
- 公司深研层：护城河、客户集中度、资本开支强度、管理层、再投资质量。
- 市场反馈层：财报后涨跌、预期差、估值压缩、资金拥挤度、分析师预期修正。
- thesis / anti-thesis 记忆：原始判断、支持证据、反方证据、证伪条件和后续验证。
- monitor / alert：财报、价格异动、估值进入区间、订单变化、capex 下修、库存反转。
- 组合风险层：行业集中度、同一 AI capex 暴露、相关性、回撤压力测试。

## 投资研究模板

每个公司研究先固定生成一个 `Investment Research Pack`，避免价格波动后“怎么解释都合理”。

### 1. 投资命题

模板：

```text
我研究 {company}，不是因为 {short_term_price_move}，而是因为 {long_term_business_thesis}。
市场当前可能低估/高估的是 {valuation_gap_or_expectation_gap}。
这条 thesis 如果成立，企业价值会通过 {value_realization_path} 兑现。
```

### 2. 企业质量表

| 维度 | 核心问题 | 目标输出 |
|---|---|---|
| 业务结构 | 它赚什么钱？ | revenue / segment facts |
| 利润质量 | 哪些业务贡献利润？ | margin / operating income facts |
| 护城河 | 5 年后优势还在吗？ | moat claims with evidence |
| 定价权 | 成本上升能否转嫁？ | pricing power facts |
| 客户集中度 | 是否依赖少数客户？ | customer concentration facts |
| 资本强度 | 增长是否必须持续高 capex？ | capex intensity facts |
| 管理层 | 资本配置是否理性？ | buyback / M&A / debt / capex facts |

### 3. 行业周期表

| 维度 | 核心问题 | 目标输出 |
|---|---|---|
| 需求 | 需求来自 AI、手机、PC、汽车还是云？ | demand driver facts |
| 供给 | 新产能多久释放？ | capacity / lead time facts |
| 价格 | 当前处于涨价初期、中期、顶部还是回落？ | pricing cycle facts |
| 库存 | 客户和厂商库存健康吗？ | inventory facts |
| capex | 竞争对手是否正在扩产？ | peer capex facts |
| 瓶颈 | 最硬的瓶颈是什么？ | bottleneck facts |

### 4. 估值表

| 维度 | 核心问题 | 目标输出 |
|---|---|---|
| 当前倍数 | 市场按多少倍当前利润定价？ | PE / EV/EBITDA / FCF yield facts |
| 正常化利润 | 当前利润是不是周期峰值？ | normalized EPS / FCF facts |
| 熊市情景 | 需求放缓和毛利率回落时值多少钱？ | bear case valuation facts |
| 基准情景 | 中性假设下企业值多少钱？ | base case valuation facts |
| 牛市情景 | thesis 成立时值多少钱？ | bull case valuation facts |
| 安全边际 | 保守内在价值和价格之间差多少？ | margin-of-safety interpretation |

### 5. 财报后分析问题

```text
1. thesis 被加强了吗？
2. thesis 被削弱了吗？
3. 市场反应是基本面变化、预期太满、资金拥挤，还是行业联动？
```

## 巴菲特 / 芒格评分框架

评分范围：1-5。分数不是买卖建议，只用于研究排序和可比性。

| 维度 | 5 分含义 | 1 分含义 |
|---|---|---|
| 可理解性 | 业务模式清晰，价值驱动因素少而明确 | 依赖太多难验证假设 |
| 护城河 | 5-10 年竞争优势大概率延续 | 优势脆弱或被快速替代 |
| 定价权 | 成本上升或供需紧张时能保利润 | 接近商品化，被客户压价 |
| 现金流质量 | 利润能稳定转成自由现金流 | 会计利润强但现金流弱 |
| 再投资能力 | 高 ROIC 且有长 runway | 增长需要低回报投入 |
| 资本配置 | 管理层理性、克制、股东友好 | 周期顶部扩产/并购/举债 |
| 周期风险 | 周期位置可判断且下行可承受 | 峰值利润风险高 |
| 估值安全边际 | 保守情景仍有吸引力 | 价格已吃进多年完美增长 |
| 证伪清晰度 | 清楚知道什么事实会说明自己错了 | thesis 模糊，不容易推翻 |

## 要新增的生产模块

所有模块都必须服从 P1 主链路：外部数据或人工输入先变成 `Source` / `Fact`，再进入 synthesis、evidence binding、guardrail、memo 和 trace。

### 1. Company Research Pack

建议文件：`src/research/company_pack.py`、`src/research/company_models.py`、`src/research/test_company_pack.py`。

输出 facts：`business_model`、`segment_revenue`、`segment_margin`、`customer_concentration`、`competitive_position`、`management_capital_allocation`、`moat_indicator`、`key_risk`。

验收标准：对 MU、AVGO、QCOM、INTC、ARM 至少生成可追踪 research pack；没有数据时生成 unknown facts。

### 2. Valuation Normalizer

建议文件：`src/research/valuation.py`、`src/research/test_valuation.py`。

输出 facts：`current_valuation_multiple`、`fcf_yield`、`gross_margin_trend`、`normalized_earnings`、`bear_case_value`、`base_case_value`、`bull_case_value`、`margin_of_safety_indicator`。

第一版先做确定性计算，不做复杂 DCF。

### 3. Industry Cycle Tracker

建议文件：`src/research/industry_cycle.py`、`src/research/test_industry_cycle.py`。

第一批行业：`dram_hbm`、`ai_accelerator`、`data_center_power`、`data_center_cooling`、`optical_networking`、`grid_epc`。

### 4. Thesis Memory

建议文件：`src/research/thesis.py`、`src/research/test_thesis.py`，并在 `src/memory/store.py` 增加 SQLite tables。

建议 schema：

```text
investment_thesis(id, ticker, created_at, updated_at, thesis_text, value_realization_path, time_horizon, status)
thesis_evidence(id, thesis_id, fact_id, source_id, evidence_type, note)
thesis_invalidator(id, thesis_id, condition_text, observed_status, last_checked_at)
```

### 5. Market Reaction Explainer

建议文件：`src/research/market_reaction.py`、`src/research/test_market_reaction.py`。

判断分类：`fundamental_improvement`、`fundamental_deterioration`、`expectation_too_high`、`sector_risk_off`、`positioning_unwind`、`unknown_or_mixed`。

### 6. Buffett-Munger Scorecard

建议文件：`src/research/scorecard.py`、`src/research/test_scorecard.py`。

输出 facts：`score_understandability`、`score_moat`、`score_pricing_power`、`score_cash_flow_quality`、`score_reinvestment_runway`、`score_capital_allocation`、`score_cyclicality_risk`、`score_margin_of_safety`、`score_falsifiability`、`research_priority`。

### 7. Portfolio / Exposure Risk

建议文件：`src/research/exposure.py`、`src/research/test_exposure.py`。

第一批 factor tags：`ai_capex`、`semiconductor_cycle`、`data_center_power`、`cloud_platform`、`memory_cycle`、`china_exposure`、`rate_sensitive`。

### 8. Monitor / Alert Trigger

建议文件：`src/research/alerts.py`、`src/research/test_alerts.py`。

触发类型：earnings released、price move exceeds threshold、valuation multiple enters range、backlog changes materially、capex guidance changes、HBM pricing / supply commentary changes、thesis invalidator observed。

## 建议实施顺序

### P2A：研究模板和 thesis 记忆

- 新增 `InvestmentResearchPack` 数据模型。
- 新增 thesis / invalidator schema。
- memo 增加 `Investment Thesis` 和 `Thesis Invalidators` section。
- 增加 MU fixture case。

验收：给定 MU thesis + fixture facts，memo 能说明支持证据、反方证据、证伪条件和人工确认问题。

### P2B：估值 normalizer

系统能解释“低 PE 可能来自峰值利润”，并把这句话绑定到 normalized earnings facts。

### P2C：行业周期 tracker

系统能把普通 DRAM 商品周期、HBM 供需瓶颈和扩产风险分成不同 facts。

### P2D：巴芒 scorecard

ARM 能被识别为好生意但安全边际弱；INTC 能被识别为 turnaround 不确定性高；QCOM 能被识别为现金流较强但 AI 主线相关性较弱。

### P3：市场反馈和组合风险

系统能解释 Broadcom 好财报大跌可能是 expectation gap，而不是直接归因基本面恶化。

### P4：文档/RAG 和自动监控

新财报或电话会进入后，系统自动生成 changed facts，并判断对应 thesis 是 strengthened / weakened / unchanged。

## 第一批研究 universe

| 层级 | 公司 | 研究重点 |
|---|---|---|
| GPU / AI accelerator | NVDA, AMD | 增长是否已被价格充分反映，软件生态和供给能力 |
| ASIC / networking | AVGO | AI ASIC、网络、软件现金流，预期是否过满 |
| CPU / foundry turnaround | INTC | foundry 亏损、18A、capex、外部客户验证 |
| IP licensing | ARM | 轻资产护城河与高估值安全边际 |
| Memory / HBM | MU, SK hynix, Samsung | HBM 是否改变传统 DRAM 周期 |
| Mobile / edge AI | QCOM | 现金流、专利、边缘 AI、汽车和 PC 可选项 |
| Foundry / equipment | TSMC, ASML | 护城河、地缘风险、capex 强度 |
| Data center power | ETN, Schneider, VRT, nVent | 订单能见度、电力瓶颈、利润释放 |
| Grid / EPC | PWR, GE Vernova | 大负载接入、电网升级、backlog |
| Optical networking | ANET, COHR, Fabrinet, GLW, MRVL | AI 集群连接密度、客户集中度、技术路线 |

## Memo 输出目标形态

```text
Boundary Statement
Investment Thesis
Thesis Status
Executive Summary
Business Quality
Industry Cycle
Valuation
Market Reaction
Buffett-Munger Scorecard
Evidence Table
Risks
Unknowns / Conflicts
Thesis Invalidators
User Preference Fit
Human Confirmation Points
Trace Reference
```

## Guardrail 增强

- scorecard 分数必须绑定至少一个 fact。
- valuation conclusion 必须包含 bear/base/bull 或 normalized earnings。
- cycle conclusion 必须包含 demand/supply/inventory/pricing 中至少两个维度。
- thesis update 必须说明 support / oppose / unchanged。
- market reaction conclusion 必须区分 fact 和 interpretation。
- alert output 不能包含买入、卖出、加仓、减仓、持有等直接动作建议。

## 最小可行切片

建议下一个工程切片只做一件事：`P2A-MU Thesis Pack`。

范围：fixture 数据，不依赖 live source；新增 thesis model；新增 MU research pack fixture；memo 增加 Investment Thesis / Thesis Invalidators；case runner 增加 `mu_hbm_thesis_pack`。

验收命令：

```bash
.venv/bin/python -m pytest
.venv/bin/python -m src.eval.research_case_runner --data-source fixture --synthesizer mock --suite all
```

成功标准：case PASS；memo 不给买卖建议；MU thesis、支持证据、反方证据、证伪条件、人工确认问题都出现；所有关键 claims 都绑定 evidence。
