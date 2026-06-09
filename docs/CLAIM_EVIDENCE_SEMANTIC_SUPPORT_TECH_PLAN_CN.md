# Claim-Evidence Semantic Support 技术方案

## 1. 方案目标

本文档承接 `docs/CLAIM_EVIDENCE_SEMANTIC_SUPPORT_PRD_CN.md`，描述如何在当前项目中落地 claim 与 evidence 的第二层语义支撑验证。

当前 P1 已经完成 provenance verification：`CandidateClaim.fact_ids` 必须引用真实存在、有来源、有时间戳的事实。但 `fact_id` 合法不等于证据足以支撑结论。本方案要补齐 semantic support verification：

- 验证 claim kind 与 bound fact type 是否兼容。
- 验证 fact value 的方向是否与 claim 表述一致。
- 对不相关、不充分或相矛盾的证据绑定生成结构化 issue。
- 将可补证的问题交给 `retrieval_planner` 生成有限、可去重的补证任务。
- 保持 evidence-constrained 原则：验证器只能读取当前 run 的 claim 和 bound facts，不引入外部知识。

## 2. 当前代码落点

现有关键模块如下：

- `src/research/models.py`
  - `VerifiedFact`、`ResearchContext`、`ClaimVerificationIssue`、`RetrievalTask` 等核心数据结构。
- `src/research/fact_verifier.py`
  - `_METRIC_TO_FACT_TYPE` 当前只覆盖价格、新闻、corporate actions、用户偏好和 data-quality 类事实。
- `src/research/claim_verifier.py`
  - 当前负责 fact id 合法性、缺失 evidence、直接交易建议、missing fact 被当支持、price-only causal inference、低置信度过度表述。
- `src/research/retrieval_planner.py`
  - 当前把 `retrieval_needed=True` 的 verifier issue 转成 `RetrievalTask`。
- `src/research/synthesizer.py`
  - 当前真实和 mock synthesizer 的接口仍以 `ResearchRunState` 为输入，后续真实 LLM 路径需要收紧为只读取 `ResearchContext`。
- `src/research/evaluator.py`
  - memo 渲染后的 guardrail。它不承担 claim-fact 语义蕴含判断。

## 3. 总体架构

语义支撑验证发生在 synthesis 之后、memo rendering 之前：

```text
tool results
  -> Fact
  -> VerifiedFact / MissingFact
  -> ResearchContext
  -> CandidateClaim
  -> provenance verification
  -> semantic support verification
  -> filter_synthesis_to_verified_claims
  -> bind_claims_to_evidence
  -> render memo
  -> guardrail evaluator
```

其中 semantic support verification 包含三层：

1. Evidence schema check
   - 判断 claim kind 与 bound fact type 是否兼容。
2. Metric direction rules
   - 判断“改善/下降/合理/偏高”等方向性表述是否被结构化 value 支持。
3. Constrained entailment judge
   - 后续阶段可接入窄任务 LLM judge，但默认关闭，确定性规则始终作为 fallback。

## 4. 数据结构改动

### 4.1 新增 `EvidenceSupportResult`

建议放入 `src/research/models.py`，作为 claim-level semantic verifier 的标准输出。

```python
@dataclass
class EvidenceSupportResult:
    """/**
     * 单条 claim 与其绑定 facts 的语义支撑验证结果。
     *
     * @property claim_kind - 细粒度结论类型，例如 cash_flow_quality 表示现金流质量判断。
     * @property fact_types - 当前 claim 绑定到的事实类型集合。
     * @property schema_status - evidence schema 的类型兼容状态。
     * @property verdict - 最终语义支撑判断结果。
     * @property reason - 面向 trace 和调试的人类可读原因。
     * @property unsupported_terms - claim 中尚未被证据支持的关键术语。
     * @property required_missing_facts - 为支撑该 claim 仍需要补齐的事实类型。
     */
    """

    claim_kind: str
    fact_types: list[str]
    schema_status: Literal["compatible", "mismatch", "insufficient", "unknown"]
    verdict: Literal["supported", "contradicted", "neutral", "insufficient"]
    reason: str
    unsupported_terms: list[str] = field(default_factory=list)
    required_missing_facts: list[str] = field(default_factory=list)
```

### 4.2 扩展 `ClaimVerificationIssue`

保持向后兼容，新增字段全部为 optional 或有默认值。

```python
claim_kind: str | None = None
# 中文说明：细粒度 claim 类型，例如 cash_flow_quality、valuation_reasonableness。

fact_types: list[str] = field(default_factory=list)
# 中文说明：当前 issue 涉及的 bound fact type 集合。

required_missing_facts: list[str] = field(default_factory=list)
# 中文说明：为了支持该 claim 仍需补齐的 fact type。

verdict: str | None = None
# 中文说明：semantic support 判断结果，例如 supported、contradicted、insufficient。
```

`issue_type` 需要新增：

- `evidence_type_mismatch`
- `evidence_not_relevant`
- `evidence_insufficient`
- `evidence_contradicts_claim`

## 5. 新增模块：`evidence_schema.py`

新增文件：

```text
src/research/evidence_schema.py
```

核心接口：

```python
def classify_claim_kind(claim_text: str, coarse_claim_type: str) -> str:
    """/** 根据 claim 文本和粗粒度 claim_type 推导细粒度 claim_kind。 */"""

def required_fact_types_for_claim(claim_kind: str) -> set[str]:
    """/** 返回支撑该 claim_kind 的核心必需 fact type。 */"""

def compatible_fact_types_for_claim(claim_kind: str) -> set[str]:
    """/** 返回可以支撑该 claim_kind 的 fact type 集合。 */"""

def insufficient_fact_types_for_claim(claim_kind: str) -> set[str]:
    """/** 返回对该 claim_kind 明显不足或不相关的 fact type 集合。 */"""

def check_fact_type_compatibility(claim_kind: str, fact_types: set[str]) -> EvidenceSchemaResult:
    """/** 检查 claim_kind 与 bound fact types 的类型兼容性。 */"""
```

MVP 首批 claim kind：

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

分类原则：

- 中英关键词都要覆盖。
- 不确定时回退到 `generic_fact_summary`。
- `generic_fact_summary` 不触发误杀，只进入弱约束或跳过 semantic check。

## 6. Fact Taxonomy 扩展

在 `src/research/fact_verifier.py` 的 `_METRIC_TO_FACT_TYPE` 增加高频投资研究指标。

首批建议：

```python
_METRIC_TO_FACT_TYPE = {
    "latest_price": "price_move",
    "five_day_close_range": "price_move",
    "news_tone": "news_events",
    "unknown_news": "news_events",
    "corporate_actions": "corporate_actions",
    "investment_preferences": "user_preferences",
    "operating_cash_flow": "operating_cash_flow",
    "free_cash_flow": "free_cash_flow",
    "cash_conversion_ratio": "cash_conversion_ratio",
    "working_capital_trend": "working_capital_trend",
    "pe_ratio": "pe_ratio",
    "ev_ebitda": "ev_ebitda",
    "p_fcf": "p_fcf",
    "peer_valuation_range": "peer_valuation_range",
    "historical_valuation_range": "historical_valuation_range",
    "buyback_history": "buyback_history",
    "dividend_policy": "dividend_policy",
    "share_count_change": "share_count_change",
    "mna_history": "mna_history",
    "roic": "roic",
    "debt_usage": "debt_usage",
    "revenue_growth": "revenue_growth",
    "gross_margin_trend": "gross_margin_trend",
    "operating_margin_trend": "operating_margin_trend",
    "debt_level": "debt_level",
    "net_cash_or_debt": "net_cash_or_debt",
    "interest_coverage": "interest_coverage",
    "management_commentary": "management_commentary",
    "earnings_or_guidance": "earnings_or_guidance",
    "product_news": "product_news",
    "sector_move": "sector_move",
    "peer_moves": "peer_moves",
    "analyst_actions": "analyst_actions",
}
```

注意事项：

- 本阶段只扩展 mapping 和验证能力，不要求所有上游 tool/provider 立即产出这些 metric。
- data-quality 类 metric 继续保留 partial/low-confidence 行为。
- 新增 metric 名和 fact type 都要在代码注释里加中文说明。

## 7. Claim Verifier 集成

在 `src/research/claim_verifier.py` 中扩展 `_verify_single_claim()`。

建议流程：

```python
for claim in synthesis.claims:
    provenance_issues = existing_checks(...)
    if has_blocking_provenance_error:
        continue

    claim_kind = classify_claim_kind(claim.text, claim.claim_type)
    cited_facts = facts_by_id(claim.fact_ids)
    fact_types = {fact.fact_type for fact in cited_facts}

    schema_result = check_fact_type_compatibility(claim_kind, fact_types)
    direction_result = check_metric_direction(claim.text, cited_facts)
    support_result = merge_support_results(schema_result, direction_result)

    issues.extend(issues_from_support_result(support_result))
```

严重程度建议：

- `evidence_contradicts_claim`
  - `severity="error"`
  - claim 被过滤。
- `evidence_type_mismatch`
  - 对复杂基本面 claim 默认 `severity="error"`。
  - 对不确定分类或泛事实摘要降为 `warning` 或跳过。
- `evidence_not_relevant`
  - `severity="warning"` 或核心失败样例中升为 `error`。
  - `retrieval_needed=True`。
- `evidence_insufficient`
  - `severity="warning"`
  - `retrieval_needed=True`。

## 8. Metric Direction Rules

新增文件：

```text
src/research/metric_direction.py
```

核心接口：

```python
def check_metric_direction(claim_text: str, facts: list[ContextFact]) -> EvidenceSupportResult | None:
    """/**
     * 基于结构化 fact.value 判断 claim 的方向性表述是否被证据支持。
     *
     * @remarks 只使用当前 bound facts，不读取外部知识；无法判断时返回 None 或 neutral。
     */
    """
```

MVP 规则：

- claim 包含“改善/提升/增长/扩大/improve/increase/grow”
  - `free_cash_flow`、`operating_cash_flow`、`revenue_growth`、`gross_margin_trend`、`operating_margin_trend` 需要正向趋势。
- claim 包含“恶化/下降/收缩/deteriorate/decline/compress”
  - 上述指标需要负向趋势。
- claim 包含“估值合理/reasonable/fair”
  - 需要当前 multiple 与 peer/historical benchmark。
- claim 包含“估值偏高/expensive/rich”
  - 需要当前 multiple 高于 benchmark 或区间上沿。
- claim 包含“资产负债表风险/balance sheet risk/leverage risk”
  - 需要 `debt_level`、`net_cash_or_debt`、`interest_coverage` 或 `debt_usage`。

无法从 `value` 判断时不要误杀，返回 `insufficient` 或 `neutral`。

## 9. Retrieval Planner 集成

在 `src/research/retrieval_planner.py` 扩展：

- `_FACT_TYPE_TOOL_HINTS`
- `_FACT_TYPE_SOURCE_REQUIREMENTS`
- `_tasks_for_issue()`
- `_query_focus()`

新 issue 处理原则：

- `evidence_type_mismatch` / `evidence_not_relevant`
  - 根据 `claim_kind` 的 required/compatible fact types 生成补证任务。
- `evidence_insufficient`
  - 优先使用 `issue.required_missing_facts`。
- `evidence_contradicts_claim`
  - 默认不生成“支持原 claim”的补证任务。
  - 可生成 conflict confirmation 任务，或让 claim 降级为 risk/unknown。

示例：

```text
claim: 公司现金流质量改善。
fact_types: price_move
issue: evidence_not_relevant
retrieval tasks:
  - operating_cash_flow
  - free_cash_flow
  - cash_conversion_ratio
```

## 10. Synthesizer 输入边界收紧

真实 LLM synthesizer 应只读取 `ResearchContext`。

目标接口：

```python
class LLMResearchSynthesizer(Protocol):
    def synthesize(self, context: ResearchContext) -> SynthesisResult:
        """/**
         * 根据最小研究上下文生成候选 claims。
         *
         * @param context - 真实 LLM 的唯一输入，只包含可引用 facts、missing_facts、source_ids、用户问题、实体、时间窗口和输出约束。
         */
        """
```

迁移策略：

- Phase 1 中可以保留 mock adapter，避免一次性打破 demo fixture。
- `AnthropicJSONResearchSynthesizer` 优先迁移到 `ResearchContext`。
- `build_synthesis_prompt()` 改为接收 `ResearchContext`，不在内部读取完整 `ResearchRunState`。
- 编排层负责在 synthesizer 前调用 `build_research_context(run)`。

## 11. Missing Facts 与有限补证闭环

`MissingFact` 表示当前任务需要但本轮工具没有覆盖的事实类型，不是“系统已知但未填入”的事实。

未来自动补证 executor 必须有限循环：

```python
MAX_RETRIEVAL_ROUNDS = 2
MAX_TASKS_PER_ROUND = 5
```

停止条件：

- 达到最大补证轮次。
- 当前 verification 没有 error 或 retrieval-needed issue。
- retrieval plan 没有新任务。
- 新一轮检索没有产生新的 verified facts。
- 同一个 issue/fact_type/symbol 组合重复出现，进入 human confirmation，而不是继续空转。

## 12. Trace、Memo、Guardrail 分工

Trace 建议新增事件：

```text
claim_evidence_relevance_checked
```

payload 字段：

- `claim_text`
- `claim_kind`
- `fact_ids`
- `fact_types`
- `schema_status`
- `entailment_verdict`
- `issue_types`

Memo 行为：

- `severity="error"` 的 semantic issue 对应 claim 不进入 memo。
- warning claim 若保留，必须进入 unknowns/conflicts/freshness notes 或 human confirmation points。
- Evidence table 可后续显示 `claim_kind` 与 `semantic_verdict`，MVP 可只进 trace。

Guardrail 分工：

- semantic verifier 发生在 memo 渲染前，负责 claim 与 bound facts 的语义支撑判断。
- evaluator/guardrail 发生在 memo 渲染后，负责检查最终输出是否有直接交易建议、证据、时间、风险和人工确认点。
- guardrail 不做 claim-fact 语义蕴含判断。

## 13. 验证 Trace 合同

每次执行 claim verification 或后续 semantic support verification 时，必须写入完整 JSONL trace，方便人工复盘一次关键验证到底发生了什么。

Trace 事件要求：

- 使用 `event_type="function_io"` 记录函数输入输出。
- payload 必须包含 `tag`，格式为 `模块路径.函数名`，例如 `src.research.claim_verifier.verify_synthesis_claims`。
- payload 必须包含 `module`、`function`、`inputs`、`output`。
- `inputs` 必须保留 claim、fact ids、fact types、missing types、quality/status 等复盘验证必需字段。
- `output` 必须保留完整 verifier result、issue list 或过滤后的 synthesis result。
- JSON 类输出不能截断；trace writer 只能做 JSON 序列化，不做字段裁剪。
- 如果函数没有传入 `TraceLogger`，必须保持旧行为不变，方便单测直接调用。

当前已接入的关键函数：

- `src.research.claim_verifier._context_fact_types_by_id`
- `src.research.claim_verifier._context_quality_by_id`
- `src.research.claim_verifier._verify_single_claim`
- `src.research.claim_verifier.verify_synthesis_claims`
- `src.research.claim_verifier.filter_synthesis_to_verified_claims`
- `src.agents.research_demo.build_research_run_from_bundle`

后续新增 `evidence_schema.py`、`metric_direction.py`、LLM judge 或 retrieval planner semantic issue 映射时，也必须沿用同一合同。

人工验证时重点查看本轮 `run.trace_path` 指向的 JSONL 文件，确认至少能看到：

```text
function_io -> src.research.claim_verifier._verify_single_claim
function_io -> src.research.claim_verifier.verify_synthesis_claims
function_io -> src.research.claim_verifier.filter_synthesis_to_verified_claims
```

## 14. 测试计划

### 14.1 `test_evidence_schema.py`

新增测试：

- `公司现金流质量改善。` -> `cash_flow_quality`
- `当前估值合理。` -> `valuation_reasonableness`
- `收入增长仍然强劲。` -> `revenue_growth`
- `短期价格波动本身不足以支持投资决策。` -> `price_movement` 或 `unknown_or_insufficient`
- 不明确 claim -> `generic_fact_summary`
- `cash_flow_quality + price_move` -> mismatch 或 insufficient
- `valuation_reasonableness + price_move` -> insufficient
- `revenue_growth + revenue_growth` -> compatible

### 14.2 `test_claim_verifier.py`

新增端到端 verifier 用例：

Case A：真实但无关

```text
claim: 公司现金流质量改善。
bound fact: 股价最近上涨 8%。 fact_type=price_move
expected:
  claim_kind=cash_flow_quality
  issue=evidence_type_mismatch 或 evidence_not_relevant
  retrieval_needed=True
  required_missing_facts 包含 operating_cash_flow、free_cash_flow、cash_conversion_ratio
```

Case B：类型正确但方向相反

```text
claim: 自由现金流正在改善。
bound fact: 自由现金流同比下降 20%。 fact_type=free_cash_flow
expected:
  issue=evidence_contradicts_claim
  severity=error
  claim 被 filter_synthesis_to_verified_claims 过滤
```

Case C：估值判断缺 benchmark

```text
claim: 当前估值合理。
bound fact: 最新股价为 120 美元。 fact_type=price_move
expected:
  issue=evidence_insufficient
  required_missing_facts 包含 pe_ratio、p_fcf、peer_valuation_range 或 historical_valuation_range
```

Case D：合法支持

```text
claim: 收入增长仍然强劲。
bound fact: 最近季度收入同比增长 42%。 fact_type=revenue_growth
expected:
  verdict=supported
  无 semantic support issue
  claim 可进入 binding 与 memo renderer
```

### 14.3 `test_retrieval_planner.py`

新增测试：

- `evidence_not_relevant` 能生成现金流补证任务。
- `evidence_insufficient` 能优先使用 `required_missing_facts`。
- 估值 insufficient 能生成 valuation multiple 与 peer/historical benchmark 任务。
- contradicted issue 不默认生成支持性补证任务。
- 重复 fact_type/symbol/issue 组合被去重。

### 14.4 Regression

建议回归命令：

```bash
pytest src/research/test_claim_verifier.py
pytest src/research/test_retrieval_planner.py
pytest src/research/test_synthesizer.py
pytest src/research
python3 -m src.agents.research_demo
```

## 15. 实施阶段

### Phase 1：Deterministic Schema MVP

- 新增 `evidence_schema.py`。
- 实现 claim kind 规则分类。
- 扩展 `_METRIC_TO_FACT_TYPE`。
- 扩展 `ClaimVerificationIssue`。
- 在 `claim_verifier` 中接入 compatibility matrix。
- 增加 schema 和 verifier 单测。

完成标准：

- “现金流改善 + 股价上涨”能被拦截。
- 现有 P1 单测不回归。

### Phase 2：Direction Rules

- 新增 `metric_direction.py`。
- 基于 `Fact.value` / `ContextFact.value` 判断方向一致性。
- 对缺少 value 或 benchmark 的 claim 产出 insufficient。
- 扩展 retrieval planner。

完成标准：

- “FCF 同比下降 + 现金流改善”产生 error 并过滤。
- “估值合理 + 最新股价”产生补证任务。

### Phase 3：Constrained LLM Judge

- 抽象 judge interface。
- 默认 deterministic judge。
- LLM judge behind flag。
- judge 输出通过 JSON schema 校验。
- judge 失败时降级到 deterministic verdict。

完成标准：

- judge 只能读取 claim text 和 bound facts。
- judge 不访问外部知识，不生成新 claim。

### Phase 4：Eval 与 Memo Surface

- 增加 frozen eval cases。
- trace 增加 semantic support payload。
- memo 消化 warning 级不足、冲突和人工确认点。

完成标准：

- error claim 不进入 memo。
- warning claim 的证据不足能在 unknown/conflict/human confirmation 中体现。

## 16. 中文注释规范

后续编码或修改代码时，只要涉及专业名词、字段、枚举、规则、接口边界，都必须增加中文注释。

具体要求：

- 新增 dataclass 必须说明每个字段的中文语义。
- 新增 enum/Literal 值必须说明业务含义。
- 新增 claim kind、fact type、issue type 必须有中文解释。
- 新增规则函数必须说明输入边界：只能读取当前 claim 和 bound facts，不能引入外部知识。
- 涉及 `ResearchContext` 与 `ResearchRunState` 的接口必须标明最小权限边界。
- 对金融术语使用中英并列，例如 `free_cash_flow` 注释为“自由现金流”。

推荐沿用当前项目中的 JSDoc-like 风格：

```python
@dataclass
class Example:
    """/**
     * 中文说明这个对象的业务含义。
     *
     * @property field_name - 中文说明字段用途和边界。
     *
     * @remarks 中文说明重要约束，例如是否允许 LLM 读取、是否可进入 memo。
     */
    """
```

## 17. 风险与关注点

- 规则分类可能误判，因此 MVP 要偏保守。
- fact taxonomy 过细会增加 normalizer、retrieval planner 和测试维护成本。
- direction rules 依赖 `value` 结构，必须在测试 fixture 中固定 value 形态。
- LLM judge 不能成为 source of truth，必须 behind flag。
- 中英混合 claim 要覆盖关键词。
- contradicted claim 默认过滤，不要用补证任务强行修复原 claim。
- 自动补证闭环必须有限轮次，避免无限循环。

## 18. 成功指标

- semantic verifier 单测不少于 8 条。
- frozen eval 至少覆盖 4 类 evidence relevance failure。
- 现有 P1 单测与 research demo 不回归。
- 对以下样例均能产生预期 issue：
  - “现金流改善 + 股价上涨”
  - “估值合理 + 最新股价”
  - “资本配置强 + 产品新闻”
  - “FCF 同比下降 + 现金流改善”

