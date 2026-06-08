"""Minimal data model for traceable investment research runs.

These dataclasses are deliberately small. P0 only needs enough structure to
bind claims back to tool-produced facts and source timestamps.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:12]}"


@dataclass
class Source:
    id: str
    kind: Literal["tool_result", "user_memory", "local_fixture", "external_url"]
    name: str
    fetched_at: str
    url: str | None = None
    tool_name: str | None = None
    raw_ref: str | None = None
    reliability: Literal["high", "medium", "low"] = "medium"


@dataclass
class Fact:
    id: str
    text: str
    source_ids: list[str]
    observed_at: str
    value: Any | None = None
    metric: str | None = None
    symbol: str | None = None


@dataclass
class Evidence:
    fact_id: str
    source_id: str
    quote: str | None = None


@dataclass
class Claim:
    id: str
    text: str
    evidence: list[Evidence]
    is_key: bool = True
    claim_type: Literal["fact_summary", "supporting_factor", "risk_factor", "unknown", "fit_assessment"] = "fact_summary"


@dataclass
class PolicyCheck:
    name: str
    passed: bool
    message: str
    severity: Literal["info", "warning", "error"] = "error"


@dataclass
class GuardrailResult:
    passed: bool
    checks: list[PolicyCheck]


@dataclass
class QueryIntake:
    """/**
     * 记录对用户原始问题的归一化理解。
     *
     * @property raw_query - 保留下来的用户原始文本，用于报告渲染。
     * @property normalized_query - 归一化空白后的问题，用于确定性匹配。
     * @property language - 粗粒度语言类型，用于用户体验和调试上下文。
     * @property requested_output - 进入策略路由前，用户看起来想要的输出目标。
     * @property wants_direct_trading_advice - 检测到买入/卖出/加仓/减仓等语言时为 True。
     *
     * @remarks 这个对象只记录意图，不代表允许提供交易建议。guardrail 和路由选择仍然会强制执行只做研究的边界。
     */
    """

    raw_query: str
    normalized_query: str
    language: Literal["zh", "en", "mixed", "unknown"]
    requested_output: Literal["research_memo", "news_explanation", "valuation_review", "portfolio_review", "trade_advice", "unknown"]
    wants_direct_trading_advice: bool = False


@dataclass
class IntentRoute:
    """/**
     * 描述应该由哪条研究工作流处理当前问题。
     *
     * @property route - planner 和 renderer 使用的稳定路由 id。
     * @property rationale - 给 trace 和报告审计使用的人类可读理由。
     *
     * @remarks 路由值会刻意把直接交易请求和普通研究路径分开，让系统用边界声明和澄清问题来回答，而不是给建议。
     */
    """

    route: Literal[
        "company_research_memo",
        "news_explanation",
        "valuation_review",
        "portfolio_review",
        "direct_trade_advice_boundary",
        "unknown_research",
    ]
    rationale: str


@dataclass
class ResolvedEntity:
    """/**
     * 下游数据工具使用的归一化公司/ticker 标识。
     *
     * @property raw_mention - 触发解析的文本片段或覆盖值。
     * @property symbol - 传给 finance 和 corporate-action 工具的 ticker。
     * @property company_query - 传给 news/local research 工具的公司检索字符串。
     * @property company_name - 面向用户报告中可展示的可选正式公司名。
     * @property confidence - 本次标的解析的启发式置信度。
     */
    """

    raw_mention: str
    symbol: str
    company_query: str
    company_name: str | None = None
    confidence: Literal["high", "medium", "low"] = "medium"


@dataclass
class FactNeed:
    """/**
     * 研究计划中的一个证据需求槽位。
     *
     * @property key - trace/report 载荷 中使用的稳定 事实 key。
     * @property tool_name - 预期填充该事实的工具或未来 provider。
     * @property reason - 为什么 综合/渲染 前需要这个事实。
     * @property required - 对已规划但尚未接线的增强项为 False。
     */
    """

    key: str
    tool_name: str
    reason: str
    required: bool = True


@dataclass
class TimeWindow:
    """/**
     * 用户问题对应的研究时间窗口。
     *
     * @property label - 用户可读的窗口名称，例如“最近 5 个交易日”。
     * @property start_date - ISO 日期字符串，表示窗口开始。
     * @property end_date - ISO 日期字符串，表示窗口结束。
     * @property confidence - 规则解析置信度。
     * @property rationale - 为什么这样解释时间窗口。
     */
    """

    label: str
    start_date: str
    end_date: str
    confidence: Literal["high", "medium", "low"] = "medium"
    rationale: str = ""


@dataclass
class AttributionNeed:
    """/**
     * 归因分析需要核验的一类证据。
     *
     * @property key - 归因证据类型，例如 price_move、sector_move。
     * @property description - 用户可读说明。
     * @property required - 是否为回答该问题的必需证据。
     */
    """

    key: str
    description: str
    required: bool = True


@dataclass
class AttributionPlan:
    """/**
     * “为什么涨/跌”类问题的归因证据计划。
     *
     * @property question_type - price_drop、price_rise 或 general。
     * @property needs - 需要核验的归因证据集合。
     * @property peer_symbols - 用于同行/板块比较的 ticker。
     * @property index_symbols - 用于指数/ETF 背景比较的 ticker。
     */
    """

    question_type: Literal["price_drop", "price_rise", "general"]
    needs: list[AttributionNeed]
    peer_symbols: list[str] = field(default_factory=list)
    index_symbols: list[str] = field(default_factory=list)


@dataclass
class VerifiedFact:
    """/**
     * 已核验或可追踪的事实。
     *
     * @property id - verified fact id。
     * @property fact_type - price_move、news_events 等研究事实类型。
     * @property text - 用户可读事实文本。
     * @property source_ids - 支撑该事实的 source id。
     * @property observed_at - 事实观测时间。
     * @property confidence - 核验置信度。
     * @property verification_status - verified 或 partial。
     * @property raw_fact_id - 对应原始 Fact id。
     */
    """

    id: str
    fact_type: str
    text: str
    source_ids: list[str]
    observed_at: str
    confidence: Literal["high", "medium", "low"] = "medium"
    verification_status: Literal["verified", "partial"] = "verified"
    raw_fact_id: str | None = None
    value: Any | None = None


@dataclass
class MissingFact:
    """/**
     * 为避免幻觉而显式记录的缺失证据。
     *
     * @property fact_type - 缺失的事实类型。
     * @property reason - 为什么它对当前问题重要。
     * @property required - 是否是必需缺口。
     */
    """

    fact_type: str
    reason: str
    required: bool = True


@dataclass
class ContextFact:
    """/** LLM context 中允许被引用的一条事实。 */"""

    fact_id: str
    fact_type: str
    text: str
    source_ids: list[str]
    observed_at: str
    confidence: Literal["high", "medium", "low"]
    verification_status: Literal["verified", "partial"]
    value: Any | None = None


@dataclass
class ContextMissingFact:
    """/** LLM context 中显式暴露的证据缺口。 */"""

    fact_type: str
    reason: str
    required: bool


@dataclass
class ResearchContext:
    """/**
     * 给 evidence-constrained LLM 使用的最小研究上下文。
     *
     * @remarks 这个对象刻意比 ResearchRunState 小：它只暴露问题理解、可引用事实、证据缺口和输出约束，
     * 避免 synthesis 层从整个 run state 中随意引入未经核验的信息。
     */
    """

    user_query: str
    entity: ResolvedEntity | None
    intent_route: IntentRoute | None
    time_window: TimeWindow | None
    attribution_plan: AttributionPlan | None
    facts: list[ContextFact]
    missing_facts: list[ContextMissingFact]
    source_ids: list[str]
    user_preferences: list[ContextFact] = field(default_factory=list)
    unsupported_claim_constraints: list[str] = field(default_factory=list)


@dataclass
class ClaimVerificationIssue:
    """/** Claim verifier 发现的模型输出问题。 */"""

    claim_text: str
    issue_type: Literal[
        "unsupported_fact_id",
        "missing_evidence",
        "direct_trading_advice",
        "missing_fact_used_as_support",
        "price_only_causal_inference",
        "low_confidence_overstated",
    ]
    message: str
    severity: Literal["info", "warning", "error"] = "warning"
    fact_ids: list[str] = field(default_factory=list)
    retrieval_needed: bool = False


@dataclass
class ClaimVerificationResult:
    """/** 对一批 candidate claims 的核验结果。 */"""

    passed: bool
    issues: list[ClaimVerificationIssue]
    accepted_claim_indexes: list[int] = field(default_factory=list)


@dataclass
class ResearchPlan:
    """/**
     * 针对当前用户问题的证据收集和报告形态清单。
     *
     * @property fact_needs - 需要收集的必需和可选事实。
     * @property output_sections - 用户报告 renderer 预期输出的报告章节。
     * @property boundary_notes - 下游需要展示或执行的策略/用户体验边界。
     */
    """

    fact_needs: list[FactNeed]
    output_sections: list[str]
    boundary_notes: list[str] = field(default_factory=list)


@dataclass
class ResearchRunState:
    run_id: str
    user_query: str
    started_at: str
    status: Literal["started", "completed", "blocked"] = "started"
    sources: list[Source] = field(default_factory=list)
    facts: list[Fact] = field(default_factory=list)
    claims: list[Claim] = field(default_factory=list)
    human_confirmation_points: list[str] = field(default_factory=list)
    guardrail: GuardrailResult | None = None
    trace_path: str | None = None
    final_output: str | None = None
    raw_synthesis: str | None = None
    # /** 工具结果归一化前挂到 run 上的用户入口、路由、标的和计划契约。 */
    intake: QueryIntake | None = None
    intent_route: IntentRoute | None = None
    resolved_entity: ResolvedEntity | None = None
    research_plan: ResearchPlan | None = None
    time_window: TimeWindow | None = None
    attribution_plan: AttributionPlan | None = None
    verified_facts: list[VerifiedFact] = field(default_factory=list)
    missing_facts: list[MissingFact] = field(default_factory=list)
    research_context: ResearchContext | None = None
    claim_verification: ClaimVerificationResult | None = None

    @classmethod
    def start(cls, user_query: str) -> "ResearchRunState":
        return cls(
            run_id=new_id("rrun"),
            user_query=user_query,
            started_at=utc_now_iso(),
        )

    def source_by_id(self, source_id: str) -> Source | None:
        return next((source for source in self.sources if source.id == source_id), None)

    def fact_by_id(self, fact_id: str) -> Fact | None:
        return next((fact for fact in self.facts if fact.id == fact_id), None)


def to_jsonable(value: Any) -> Any:
    if hasattr(value, "__dataclass_fields__"):
        return asdict(value)
    if isinstance(value, list):
        return [to_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {key: to_jsonable(item) for key, item in value.items()}
    return value


def to_json(value: Any) -> str:
    return json.dumps(to_jsonable(value), ensure_ascii=False, indent=2)
