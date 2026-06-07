"""面向用户的查询入口、意图路由、标的识别和事实规划。

/**
 * 这个模块是研究链路里第一层面向用户的入口。
 *
 * 它把原始自然语言问题转换成四个显式契约：
 * - QueryIntake：用户看起来想问什么。
 * - IntentRoute：应该由哪条研究工作流来回答。
 * - ResolvedEntity：下游工具应该查询哪家公司/哪个 ticker。
 * - ResearchPlan：渲染 memo 前需要补齐哪些事实。
 *
 * 把这些契约放在 LLM 外面，可以让工作流可追踪、可测试；当用户提出直接交易建议时，也能保持保守边界。
 */
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from src.research.models import FactNeed, IntentRoute, QueryIntake, ResearchPlan, ResolvedEntity


DEFAULT_ENTITY = ResolvedEntity(
    raw_mention="TSLA",
    symbol="TSLA",
    company_query="Tesla",
    company_name="Tesla, Inc.",
    confidence="low",
)

_ALIAS_TO_ENTITY: dict[str, ResolvedEntity] = {
    "mu": ResolvedEntity("MU", "MU", "Micron", "Micron Technology, Inc.", "high"),
    "micron": ResolvedEntity("Micron", "MU", "Micron", "Micron Technology, Inc.", "high"),
    "美光": ResolvedEntity("美光", "MU", "Micron", "Micron Technology, Inc.", "high"),
    "美光科技": ResolvedEntity("美光科技", "MU", "Micron", "Micron Technology, Inc.", "high"),
    "tsla": ResolvedEntity("TSLA", "TSLA", "Tesla", "Tesla, Inc.", "high"),
    "tesla": ResolvedEntity("Tesla", "TSLA", "Tesla", "Tesla, Inc.", "high"),
    "特斯拉": ResolvedEntity("特斯拉", "TSLA", "Tesla", "Tesla, Inc.", "high"),
    "nvda": ResolvedEntity("NVDA", "NVDA", "Nvidia", "NVIDIA Corporation", "high"),
    "nvidia": ResolvedEntity("Nvidia", "NVDA", "Nvidia", "NVIDIA Corporation", "high"),
    "英伟达": ResolvedEntity("英伟达", "NVDA", "Nvidia", "NVIDIA Corporation", "high"),
    "aapl": ResolvedEntity("AAPL", "AAPL", "Apple", "Apple Inc.", "high"),
    "apple": ResolvedEntity("Apple", "AAPL", "Apple", "Apple Inc.", "high"),
    "苹果": ResolvedEntity("苹果", "AAPL", "Apple", "Apple Inc.", "high"),
    "msft": ResolvedEntity("MSFT", "MSFT", "Microsoft", "Microsoft Corporation", "high"),
    "microsoft": ResolvedEntity("Microsoft", "MSFT", "Microsoft", "Microsoft Corporation", "high"),
    "微软": ResolvedEntity("微软", "MSFT", "Microsoft", "Microsoft Corporation", "high"),
    "0700.hk": ResolvedEntity("0700.HK", "0700.HK", "Tencent", "Tencent Holdings Limited", "high"),
    "tencent": ResolvedEntity("Tencent", "0700.HK", "Tencent", "Tencent Holdings Limited", "high"),
    "腾讯": ResolvedEntity("腾讯", "0700.HK", "Tencent", "Tencent Holdings Limited", "high"),
    "09988.hk": ResolvedEntity("09988.HK", "09988.HK", "Alibaba", "Alibaba Group Holding Limited", "high"),
    "baba": ResolvedEntity("BABA", "BABA", "Alibaba", "Alibaba Group Holding Limited", "high"),
    "alibaba": ResolvedEntity("Alibaba", "BABA", "Alibaba", "Alibaba Group Holding Limited", "high"),
    "阿里": ResolvedEntity("阿里", "09988.HK", "Alibaba", "Alibaba Group Holding Limited", "high"),
    "阿里巴巴": ResolvedEntity("阿里巴巴", "09988.HK", "Alibaba", "Alibaba Group Holding Limited", "high"),
}

_OUTPUT_SECTIONS = [
    "用户问题",
    "边界声明",
    "核心结论",
    "证据摘要",
    "风险",
    "未知项",
    "下一步需要用户确认的问题",
    "trace/reference",
]

_DIRECT_TRADE_TERMS = ("买入", "卖出", "加仓", "减仓", "清仓", "满仓", "重仓", "做空", "持有", "buy", "sell", "add", "trim", "short", "hold")
_NEWS_TERMS = ("新闻", "消息", "为什么跌", "为什么涨", "为什么会跌", "为什么会涨", "大跌", "下跌", "暴跌", "回调", "下挫", "跌幅", "涨跌", "催化", "news", "headline", "headlines")
_VALUATION_TERMS = ("估值", "便宜", "贵", "pe", "p/e", "multiple", "valuation")
_PORTFOLIO_TERMS = ("持仓", "组合", "portfolio", "position", "仓位")
_RESEARCH_TERMS = ("研究", "memo", "报告", "分析", "thesis", "关注", "看一下", "看", "风险")


@dataclass(frozen=True)
class QueryUnderstanding:
    """/**
     * 打包用户入口层的完整输出。
     *
     * @property intake - 归一化后的问题形态和用户请求的输出类型。
     * @property route - 根据问题意图选择出的工作流路由。
     * @property entity - 下游工具要使用的 ticker/公司目标。
     * @property plan - 描述必需/可选证据的事实计划。
     */
    """

    intake: QueryIntake
    route: IntentRoute
    entity: ResolvedEntity
    plan: ResearchPlan


def understand_query(user_query: str, symbol_override: str | None = None, company_query_override: str | None = None) -> QueryUnderstanding:
    """/**
     * 对单个用户问题运行完整入口解析流程。
     *
     * @param user_query - 用户原始输入，例如 "帮我看美光/Micron/MU"。
     * @param symbol_override - CLI 或调用方传入的可选 ticker 覆盖值。
     * @param company_query_override - 可选的公司/新闻检索 检索词覆盖值。
     * @returns 可直接挂到 ResearchRunState 上的 QueryUnderstanding 对象。
     *
     * @remarks 手动覆盖会优先于自动标的识别；当自然语言提及不清晰时，调用方可以强制指定 symbol。
     */
    """

    intake = parse_query_intake(user_query)
    route = route_intent(intake)
    entity = resolve_entity(user_query, symbol_override=symbol_override, company_query_override=company_query_override)
    plan = plan_research(route, entity)
    return QueryUnderstanding(intake=intake, route=route, entity=entity, plan=plan)


def parse_query_intake(user_query: str) -> QueryIntake:
    """/**
     * 归一化原始问题，并分类用户想要的输出类型。
     *
     * @param user_query - 原始自然语言问题。
     * @returns 包含语言、请求输出类型和交易动作标记的 QueryIntake。
     *
     * @remarks 这里故意使用规则化、保守的判断。检测到直接交易动词不代表允许给建议，只表示下游路由必须强制执行研究边界。
     */
    """

    normalized = " ".join(user_query.strip().split())
    lower = normalized.lower()
    wants_trade = any(term in lower for term in _DIRECT_TRADE_TERMS)
    if any(term in lower for term in _NEWS_TERMS):
        requested = "news_explanation"
    elif any(term in lower for term in _VALUATION_TERMS):
        requested = "valuation_review"
    elif any(term in lower for term in _PORTFOLIO_TERMS):
        requested = "portfolio_review"
    elif wants_trade:
        requested = "trade_advice"
    elif any(term in lower for term in _RESEARCH_TERMS):
        requested = "research_memo"
    else:
        requested = "unknown"
    return QueryIntake(
        raw_query=user_query,
        normalized_query=normalized,
        language=_detect_language(normalized),
        requested_output=requested,  # type: ignore[arg-type]
        wants_direct_trading_advice=wants_trade,
    )


def route_intent(intake: QueryIntake) -> IntentRoute:
    """/**
     * 把归一化后的入口信息映射到研究工作流路由。
     *
     * @param intake - 已解析的用户问题契约。
     * @returns 描述所选工作流及其理由的 IntentRoute。
     *
     * @remarks 直接交易请求会优先进入边界工作流，再考虑新闻、估值或公司 memo 路由。这个优先级可以避免 "现在可以加仓吗" 这类问题被隐式处理成交易建议。
     */
    """

    if intake.wants_direct_trading_advice:
        return IntentRoute(
            route="direct_trade_advice_boundary",
            rationale="用户问题包含直接交易动作，转为研究边界内的证据 memo。",
        )
    if intake.requested_output == "news_explanation":
        return IntentRoute(route="news_explanation", rationale="用户主要在询问新闻、涨跌原因或催化。")
    if intake.requested_output == "valuation_review":
        return IntentRoute(route="valuation_review", rationale="用户主要在询问估值。")
    if intake.requested_output == "portfolio_review":
        return IntentRoute(route="portfolio_review", rationale="用户主要在询问持仓或组合语境。")
    if intake.requested_output == "research_memo":
        return IntentRoute(route="company_research_memo", rationale="用户需要公司研究 memo 或关注名单研究。")
    return IntentRoute(route="unknown_research", rationale="未识别到明确任务，默认生成保守研究 memo。")


def resolve_entity(user_query: str, symbol_override: str | None = None, company_query_override: str | None = None) -> ResolvedEntity:
    """/**
     * 把用户提到的公司名称解析成 ticker 和公司检索 query。
     *
     * @param user_query - 原始问题，可能包含 美光、Micron、MU 等别名。
     * @param symbol_override - 调用方提供的可选 ticker 覆盖值。
     * @param company_query_override - 调用方提供的可选公司/新闻 检索词覆盖值。
     * @returns finance、news、corporate actions 工具会使用的 ResolvedEntity。
     *
     * @remarks 别名匹配会先处理已知中英文名称，再回退到大写 ticker 提取。如果没有识别到标的，会用低置信度的 TSLA demo 兜底值，以保持既有 fixture 行为。
     */
    """

    if symbol_override:
        symbol = _normalize_symbol(symbol_override)
        company_query = company_query_override or _company_query_for_symbol(symbol) or symbol
        return ResolvedEntity(
            raw_mention=symbol_override,
            symbol=symbol,
            company_query=company_query,
            company_name=_company_name_for_symbol(symbol),
            confidence="high",
        )

    lower = user_query.lower()
    for alias in sorted(_ALIAS_TO_ENTITY, key=len, reverse=True):
        if _alias_in_query(alias, lower, user_query):
            return _ALIAS_TO_ENTITY[alias]

    ticker = _extract_ticker(user_query)
    if ticker:
        return ResolvedEntity(
            raw_mention=ticker,
            symbol=ticker,
            company_query=company_query_override or _company_query_for_symbol(ticker) or ticker,
            company_name=_company_name_for_symbol(ticker),
            confidence="medium",
        )

    if company_query_override:
        return ResolvedEntity(
            raw_mention=company_query_override,
            symbol=DEFAULT_ENTITY.symbol,
            company_query=company_query_override,
            company_name=None,
            confidence="low",
        )
    return DEFAULT_ENTITY


def plan_research(route: IntentRoute, entity: ResolvedEntity) -> ResearchPlan:
    """/**
     * 生成用户报告渲染前必须检查的事实清单。
     *
     * @param route - 为当前问题选择出的意图路由。
     * @param entity - 已解析出的公司/ticker 目标。
     * @returns 包含必需事实、可选增强项和输出边界说明的 ResearchPlan。
     *
     * @remarks 基础研究计划 总是要求 价格、历史行情、新闻、公司行动，避免新闻解释或研究 memo 只依赖单一且可能过期的数据源。估值/投资论点相关事实会先作为可选项，直到专门的数据 provider 接上。
     */
    """

    needs = [
        FactNeed("preferences", "memory.get_preferences", "识别用户偏好和风险边界。"),
        FactNeed("price", "finance.get_quote", f"获取 {entity.symbol} 最新价格快照。"),
        FactNeed("history", "finance.get_history", "判断短期价格背景，避免只看单点价格。"),
        FactNeed("news", "news.get_news", "召回近期新闻和可能催化。"),
        FactNeed(
            "corporate_actions",
            "corporate_actions.get_corporate_actions",
            "核验拆股/股息等公司行动，避免持仓和价格解释错误。",
        ),
    ]
    if route.route in {"company_research_memo", "valuation_review", "portfolio_review", "direct_trade_advice_boundary", "unknown_research"}:
        needs.extend([
            FactNeed("company_thesis", "company_research.local_thesis", "读取本地 company thesis。", required=False),
            FactNeed("monitoring_facts", "company_research.monitoring", "读取需要持续跟踪的 monitoring facts。", required=False),
        ])
    if route.route == "valuation_review":
        needs.extend([
            FactNeed("valuation_facts", "research.valuation_facts", "补齐估值倍数、财务质量和可比口径。", required=False),
            FactNeed("risk_facts", "research.risk_facts", "明确估值结论的反证和风险。", required=False),
        ])
    boundary_notes = ["输出必须是研究报告，不给直接交易建议。"]
    if route.route == "direct_trade_advice_boundary":
        boundary_notes.append("用户请求中的交易动作只作为需要澄清的目标，不作为系统建议。")
    return ResearchPlan(fact_needs=needs, output_sections=_OUTPUT_SECTIONS, boundary_notes=boundary_notes)


def _detect_language(text: str) -> str:
    """/** @returns 用于报告和调试上下文的粗粒度语言类型。 */"""

    has_zh = bool(re.search(r"[\u4e00-\u9fff]", text))
    has_en = bool(re.search(r"[A-Za-z]", text))
    if has_zh and has_en:
        return "mixed"
    if has_zh:
        return "zh"
    if has_en:
        return "en"
    return "unknown"


def _alias_in_query(alias: str, lower_query: str, raw_query: str) -> bool:
    """/** @returns 当别名以安全、独立的提及形式出现时返回 True。 */"""

    if any("\u4e00" <= char <= "\u9fff" for char in alias):
        return alias in raw_query
    if "." in alias:
        return alias in lower_query
    return bool(re.search(rf"(?<![a-z0-9]){re.escape(alias)}(?![a-z0-9])", lower_query))


def _extract_ticker(user_query: str) -> str | None:
    """/** @returns 第一个看起来合理的大写 ticker，并排除常见金融缩写。 */"""

    for match in re.finditer(r"\b[A-Z][A-Z0-9]{0,4}(?:\.[A-Z]{1,3})?\b", user_query):
        token = match.group(0)
        if token not in {"CEO", "CFO", "USD", "EPS", "PE"}:
            return _normalize_symbol(token)
    return None


def _normalize_symbol(symbol: str) -> str:
    return symbol.strip().upper()


def _company_query_for_symbol(symbol: str) -> str | None:
    for entity in _ALIAS_TO_ENTITY.values():
        if entity.symbol == symbol:
            return entity.company_query
    return None


def _company_name_for_symbol(symbol: str) -> str | None:
    for entity in _ALIAS_TO_ENTITY.values():
        if entity.symbol == symbol:
            return entity.company_name
    return None
