# Claim-Evidence Semantic Support Verification PRD

## 1. 背景

当前 P1 research loop 已经完成第一层 evidence binding：工具输出先归一化为 `Source` / `Fact`，再生成 `VerifiedFact` / `ResearchContext`，LLM 输出的 `CandidateClaim` 必须引用存在的 `fact_id`，`claim_verifier` 会拦截不存在的 fact、缺失 evidence、直接交易建议、低置信度过度表述、以及仅用价格变动做因果归因等问题。

但这里仍有一个关键漏洞：`fact_id` 真实存在，不代表这个 fact 足以支持这个 claim。

典型失败：

```text
Claim: 公司现金流质量改善。
Bound Fact: 公司最近股价上涨 8%。
```

该 fact 真实、有来源、可追踪，绑定关系也合法，但它不能支持“现金流质量改善”。这类问题定义为：

- `evidence_relevance_failure`：证据真实但与结论无关。
- `evidence_adequacy_failure`：证据方向或信息量不足，不能支撑结论强度。

本功能目标是在 P1 provenance verification 之上，建设第二层 semantic support verification：确认 claim 与 bound facts 在类型、方向和语义上确实存在支持关系。

## 2. 目标

### 2.1 产品目标

- 识别“真实但无关”的 evidence binding，避免 memo 输出被无效证据包装成可信结论。
- 将现金流、估值、资本配置、管理层、增长、利润率、资产负债表等复杂投资判断纳入更细粒度证据约束。
- 对不可支持的 claim 生成结构化 issue，并驱动 `retrieval_planner` 产出补证任务。
- 保持 P1 设计原则：LLM 不是 source of truth；所有验证必须只读取当前 run 的 claim 与 bound facts，不引入外部知识。

### 2.2 非目标

- 不在本阶段做联网补证 executor。
- 不生成新的投资结论。
- 不把 LLM judge 作为最终事实来源。
- 不要求一次性覆盖所有财务指标；先覆盖高频、可规则化的 claim/fact 类型。

## 3. 用户与场景

### 3.1 目标用户

- 使用 investment-agent 生成公司研究 memo 的投资研究者。
- 维护 regression case、评估 agent 输出质量的开发者。

### 3.2 核心场景

1. 用户要求解释某公司近期表现或生成研究 memo。
2. 系统收集 quote/news/corporate actions/preferences 等数据，形成 `Fact` 与 `VerifiedFact`。
3. LLM 生成带 `fact_ids` 的 `CandidateClaim`。
4. 新 verifier 检查 claim type 与 fact type 是否兼容，以及 evidence text 是否支持 claim text。
5. 不相关、不充分或矛盾的 claim 被标记 issue；error 级别 claim 被过滤，warning 级别 claim 可保留但必须触发补证或降级展示。

## 4. 当前项目基线

### 4.1 现有模块

- `src/research/fact_verifier.py`
  - 当前 `_METRIC_TO_FACT_TYPE` 只覆盖 `price_move`、`news_events`、`corporate_actions`、`user_preferences` 及 data-quality 类 metric。
- `src/research/context_builder.py`
  - 将 `VerifiedFact` 转成 LLM 可引用的 `ContextFact`。
  - 已有约束：“不要从价格变动单独推断原因”、“partial/stale/missing/conflicting 只能作为风险或不确定性”。
- `src/research/synthesizer.py`
  - schema 中 `claim_type` 仍是粗粒度：`fact_summary|supporting_factor|risk_factor|unknown|fit_assessment`。
- `src/research/claim_verifier.py`
  - 当前检查重点是 fact id 合法性、缺失 evidence、直接交易建议、缺失事实被当支持、价格单独因果推断、低置信度过度表述。
- `src/research/retrieval_planner.py`
  - 可把 `retrieval_needed=True` 的 verifier issue 转成结构化 `RetrievalTask`。

### 4.2 能力缺口

- `Claim.claim_type` 与 `CandidateClaim.claim_type` 不足以表达“现金流质量”“估值合理性”“资本配置”等投资判断类型。
- `VerifiedFact.fact_type` 粒度不足，无法区分自由现金流、经营现金流、估值倍数、同行估值区间、回购历史等证据类型。
- `claim_verifier` 没有 claim-to-fact compatibility matrix。
- 没有 metric direction rules，无法判断“改善/恶化/合理/过高/下降/增长”等方向性 claim 与 fact value 是否一致。
- 没有受约束的 entailment judge 输出结构。

## 5. 功能需求

### FR1. Claim Taxonomy

新增细粒度 claim kind，不直接替代现有 `claim_type`，而是增加一个派生字段或验证期分类结果，避免一次性打破 renderer/schema。

首批 claim kind：

- `cash_flow_quality`
- `valuation_reasonableness`
- `capital_allocation`
- `management_quality`
- `revenue_growth`
- `margin_trend`
- `balance_sheet_risk`
- `news_attribution`
- `price_movement`
- `sector_comparison`
- `user_preference_fit`
- `data_quality_limitation`
- `unknown_or_insufficient`
- `generic_fact_summary`

验收：

- 系统能对 `CandidateClaim.text` 和粗粒度 `claim_type` 生成 `claim_kind`。
- 分类结果写入 verifier trace payload 或 `ClaimVerificationIssue` 诊断信息。
- 不确定分类时回落到 `generic_fact_summary`，不产生误杀。

### FR2. Fact Taxonomy 扩展

扩展 `_METRIC_TO_FACT_TYPE` 与 verified fact 类型，优先覆盖投资研究常用指标。

首批新增 fact type：

- 现金流：`operating_cash_flow`、`free_cash_flow`、`cash_conversion_ratio`、`working_capital_trend`
- 估值：`pe_ratio`、`ev_ebitda`、`p_fcf`、`peer_valuation_range`、`historical_valuation_range`
- 资本配置：`buyback_history`、`dividend_policy`、`share_count_change`、`mna_history`、`roic`、`debt_usage`
- 增长与利润率：`revenue_growth`、`gross_margin_trend`、`operating_margin_trend`
- 资产负债表：`debt_level`、`net_cash_or_debt`、`interest_coverage`
- 管理层/事件：`management_commentary`、`earnings_or_guidance`、`product_news`
- 市场：`price_move`、`sector_move`、`peer_moves`、`analyst_actions`

验收：

- `build_verified_fact_table()` 能把新增 metric 稳定映射成 fact type。
- `retrieval_planner` 对新增 fact type 有 tool hints、source requirements 和 query focus fallback。
- data-quality facts 继续保持 partial/low-confidence 行为。

### FR3. Evidence Schema 兼容矩阵

新增确定性 evidence schema，描述每类 claim kind 可接受、必需、明显不足的 fact type。

建议新增模块：

```text
src/research/evidence_schema.py
```

核心接口：

```python
def classify_claim_kind(claim_text: str, coarse_claim_type: str) -> str: ...
def required_fact_types_for_claim(claim_kind: str) -> set[str]: ...
def compatible_fact_types_for_claim(claim_kind: str) -> set[str]: ...
def insufficient_fact_types_for_claim(claim_kind: str) -> set[str]: ...
def check_fact_type_compatibility(claim_kind: str, fact_types: set[str]) -> EvidenceSchemaResult: ...
```

首批规则示例：

```text
cash_flow_quality
  compatible:
    operating_cash_flow
    free_cash_flow
    cash_conversion_ratio
    working_capital_trend
  insufficient:
    price_move
    news_events
    product_news
    user_preferences

valuation_reasonableness
  compatible:
    pe_ratio
    ev_ebitda
    p_fcf
    peer_valuation_range
    historical_valuation_range
  insufficient:
    latest_price
    price_move
    positive_news
    user_preferences

capital_allocation
  compatible:
    buyback_history
    dividend_policy
    share_count_change
    mna_history
    roic
    debt_usage
  insufficient:
    price_move
    product_news
    generic management quote
```

验收：

- claim kind 与所有 bound fact types 不兼容时产生 `evidence_type_mismatch`。
- bound facts 只命中 insufficient types 时产生 `evidence_not_relevant`，`retrieval_needed=True`。
- 至少一个 compatible fact 存在时进入方向与蕴含判断。

### FR4. Metric Direction Rules

为结构化 `Fact.value` 增加方向性规则判断，先覆盖可确定的财务与市场指标。

首批规则：

- claim 包含“改善/提升/增长/扩大/improve/increase/grow”：
  - 对 `free_cash_flow`、`operating_cash_flow`、`revenue_growth`、`margin_trend` 等需要正向趋势。
- claim 包含“恶化/下降/收缩/deteriorate/decline/compress”：
  - 对上述指标需要负向趋势。
- claim 包含“估值合理/reasonable/fair”：
  - 需要当前 multiple 与 peer/historical range，或明确 benchmark。
- claim 包含“估值偏高/expensive/rich”：
  - 当前 multiple 高于 benchmark 或 range 中位/上沿。
- claim 包含“资产负债表风险/balance sheet risk/leverage risk”：
  - 需要 `debt_level`、`net_cash_or_debt`、`interest_coverage`、`debt_usage` 等证据。

验收：

- fact type 兼容但方向相反时产生 `evidence_contradicts_claim`，severity=`error`。
- fact type 兼容但缺少必要 value/benchmark 时产生 `evidence_insufficient`，`retrieval_needed=True`。
- 规则无法判断时不误杀，交给 entailment judge 或返回 neutral。

### FR5. Constrained Entailment Judge

新增受约束的窄任务 judge。judge 只能读取：

- `claim_text`
- bound facts 的 `fact_id`、`fact_type`、`text`、`value`、`observed_at`
- compatibility/rule check 的中间结果

不得读取外部知识，不得访问全量 run state，不得生成新 claim。

固定输出：

```json
{
  "verdict": "supported|contradicted|neutral|insufficient",
  "reason": "...",
  "unsupported_terms": ["现金流质量改善"],
  "required_missing_facts": ["free_cash_flow_trend", "operating_cash_flow_to_net_income"]
}
```

建议实现阶段：

- P2A：先用 deterministic/rule judge，占位相同接口。
- P2B：接入 LLM judge，但默认 off，可通过配置或测试 fixture 开启。

验收：

- judge 输出必须通过 JSON schema 校验。
- verdict 为 `contradicted` 时产生 error issue。
- verdict 为 `neutral|insufficient` 时产生 retrieval-needed issue。
- judge reason 进入 trace，但 memo 默认不展示内部裁判文本。

### FR6. Claim Verifier 集成

扩展 `verify_synthesis_claims()` 流程：

```python
for claim in synthesis.claims:
    provenance_issues = existing_checks(...)
    claim_kind = classify_claim_kind(claim.text, claim.claim_type)
    cited_facts = facts_by_id(claim.fact_ids)
    schema_result = check_fact_type_compatibility(claim_kind, cited_fact_types)
    direction_result = check_metric_direction(claim.text, cited_facts)
    entailment_result = judge_entailment(claim.text, cited_facts)
    merge_issues(...)
```

新增 issue type：

- `evidence_type_mismatch`
- `evidence_not_relevant`
- `evidence_insufficient`
- `evidence_contradicts_claim`

建议扩展 `ClaimVerificationIssue`：

```python
claim_kind: str | None = None
fact_types: list[str] = field(default_factory=list)
required_missing_facts: list[str] = field(default_factory=list)
verdict: str | None = None
```

验收：

- 现有 `test_claim_verifier.py` 全部保持通过。
- 新增测试覆盖 type mismatch、insufficient、contradicted、supported 四类 verdict。
- error 级 issue 继续通过 `filter_synthesis_to_verified_claims()` 过滤。

### FR7. Retrieval Planner 集成

`retrieval_planner` 需要识别新 issue：

- `evidence_type_mismatch`
- `evidence_not_relevant`
- `evidence_insufficient`
- `evidence_contradicts_claim`

任务生成原则：

- mismatch/not relevant：根据 claim kind 的 required/compatible fact types 生成补证任务。
- insufficient：优先根据 `required_missing_facts` 生成补证任务。
- contradicted：默认不补证为支持 claim，而是生成反证/冲突确认任务，或要求 claim 降级为 risk/unknown。

验收：

- “现金流改善 + price_move fact” 生成 `free_cash_flow` / `operating_cash_flow` 等补证任务。
- “估值合理 + latest price only” 生成 valuation multiple 与 peer/historical range 任务。
- “现金流改善 + FCF 下降” 不生成支持性补证作为默认修复；该 claim 被过滤或进入 conflict/unknown。

### FR8. Trace、Memo 与 Eval

Trace 新增事件或 payload：

- `claim_evidence_relevance_checked`
- 字段：`claim_text`、`claim_kind`、`fact_ids`、`fact_types`、`schema_status`、`entailment_verdict`、`issue_types`

Memo 行为：

- 被 error 过滤的 claim 不进入 memo。
- warning claim 若保留，必须在 unknowns/conflicts/freshness notes 或 human confirmation points 中体现证据不足。
- Evidence table 可在后续版本增加 `claim_kind` 与 `semantic_verdict`，本阶段可只进入 trace。

Eval：

- 新增 frozen data-quality case：
  - 真实但无关证据。
  - 方向相反证据。
  - 只有单一价格证据支撑复杂基本面判断。
  - 估值判断缺少 benchmark。

## 6. 端到端验收用例

### Case A: 真实但无关

输入 claim：

```text
公司现金流质量改善。
```

bound fact：

```text
fact_price: 股价最近上涨 8%。 fact_type=price_move
```

预期：

- `claim_kind=cash_flow_quality`
- issue=`evidence_type_mismatch` 或 `evidence_not_relevant`
- `retrieval_needed=True`
- retrieval tasks 包含 `operating_cash_flow`、`free_cash_flow`、`cash_conversion_ratio`

### Case B: 类型正确但方向相反

输入 claim：

```text
自由现金流正在改善。
```

bound fact：

```text
fact_fcf: 自由现金流同比下降 20%。 fact_type=free_cash_flow
```

预期：

- issue=`evidence_contradicts_claim`
- severity=`error`
- claim 被过滤

### Case C: 估值判断缺 benchmark

输入 claim：

```text
当前估值合理。
```

bound fact：

```text
fact_price: 最新股价为 120 美元。 fact_type=price_move
```

预期：

- issue=`evidence_insufficient`
- `required_missing_facts` 包含 `pe_ratio`、`p_fcf`、`peer_valuation_range` 或 `historical_valuation_range`

### Case D: 合法支持

输入 claim：

```text
收入增长仍然强劲。
```

bound fact：

```text
fact_revenue: 最近季度收入同比增长 42%。 fact_type=revenue_growth
```

预期：

- verdict=`supported`
- 无 semantic support issue
- claim 可进入 binding 与 memo renderer

## 7. 数据结构建议

### 7.1 新增结果对象

```python
@dataclass
class EvidenceSupportResult:
    claim_kind: str
    fact_types: list[str]
    schema_status: Literal["compatible", "mismatch", "insufficient", "unknown"]
    verdict: Literal["supported", "contradicted", "neutral", "insufficient"]
    reason: str
    unsupported_terms: list[str] = field(default_factory=list)
    required_missing_facts: list[str] = field(default_factory=list)
```

### 7.2 `ClaimVerificationIssue` 扩展

```python
claim_kind: str | None = None
fact_types: list[str] = field(default_factory=list)
required_missing_facts: list[str] = field(default_factory=list)
verdict: str | None = None
```

为了减少破坏，可先把这些字段设为 optional，并保持现有调用点无需修改。

## 8. 实施阶段

### Phase 1: Deterministic Schema MVP

- 新增 `evidence_schema.py`。
- 实现 claim kind 规则分类。
- 扩展 `_METRIC_TO_FACT_TYPE`。
- 在 `claim_verifier` 中接入 compatibility matrix。
- 新增 mismatch/not relevant/insufficient/contradicted issue type。
- 增加单元测试。

完成标准：

- 真实但无关证据能被拦截。
- 现有测试不回归。

### Phase 2: Direction Rules

- 新增 `evidence_entailment.py` 或 `metric_direction.py`。
- 基于 `Fact.value` / `ContextFact.value` 做趋势方向判断。
- 对缺少 value 或 benchmark 的 claim 产出 missing facts。
- 扩展 retrieval planner。

完成标准：

- 类型正确但方向相反能被 error 过滤。
- 估值合理性 claim 在缺少 benchmark 时被标为 insufficient。

### Phase 3: Constrained LLM Judge

- 抽象 judge interface。
- 默认 deterministic judge；LLM judge behind flag。
- 添加 JSON schema 校验与 trace。
- 建立 fixture 测试，确保 judge 不引入外部知识。

完成标准：

- LLM judge 输出稳定结构。
- judge 失败时系统降级到 deterministic verdict，不阻断主链路。

### Phase 4: Eval 与 Memo Surface

- 增加 research case runner 覆盖。
- trace 增加 semantic support payload。
- memo unknown/conflict/human confirmation points 消化 warning 级问题。

完成标准：

- 新增 frozen cases PASS。
- memo 不展示被 semantic verifier 判定为 error 的 claim。

## 9. 风险与约束

- 规则分类可能误判 claim kind；MVP 应偏保守，不确定时回落到 `generic_fact_summary`。
- fact taxonomy 过细会增加 normalizer 和 retrieval planner 维护成本；首批只覆盖高频投资判断。
- LLM judge 可能给出不稳定 verdict；必须 behind flag，并保留 deterministic fallback。
- 中英混合 claim 需要关键词规则同时覆盖中文与英文。
- 不能让 judge 访问外部信息，否则会破坏 P1 的 evidence-constrained 边界。

## 10. 成功指标

- 新增 semantic verifier 单测不少于 8 条。
- frozen eval 至少覆盖 4 类 evidence relevance failure。
- 现有 P1 单测与 research demo 不回归。
- 对“现金流改善 + 股价上涨”“估值合理 + 最新股价”“资本配置强 + 产品新闻”等样例均能产生 retrieval-needed issue。
- 对“FCF 同比下降 + 现金流改善”能产生 error 并过滤 claim。

## 11. 面试表述

可以这样概括：

```text
我们把 evidence verification 分成两层。
第一层是 provenance verification，确认每个 claim 都绑定到真实存在、有来源、有时间戳的 fact。
第二层是 semantic support verification，确认这个 fact 在类型、方向和语义上确实能支持 claim。
P1 已经完成第一层；下一步会用 claim taxonomy、fact taxonomy、required evidence schema、metric direction rules 和 constrained entailment judge 来识别“真实但无关”的证据绑定。
```
