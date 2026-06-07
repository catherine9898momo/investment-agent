"""Deterministic investment memo renderer for research runs."""

from __future__ import annotations

from dataclasses import dataclass

from src.research.models import Claim, Evidence, Fact, ResearchRunState, Source


MEMO_SECTIONS = [
    "先说结论",
    "发生了什么",
    "关键依据",
    "风险与不确定性",
    "还需要确认",
    "数据来源与时效",
]


@dataclass
class EvidenceRow:
    claim_id: str
    claim_type: str
    claim_text: str
    fact_id: str
    fact_metric: str
    fact_text: str
    source_id: str
    source_name: str
    source_fetched_at: str
    fact_observed_at: str


def render_investment_memo(run: ResearchRunState) -> str:
    """/**
     * 渲染真正面向用户的投资研究报告。
     *
     * @param run - 已绑定 claims/evidence，且可能带有入口契约的 research run。
     * @returns Markdown 研究报告，优先呈现结论、原因、证据、风险和下一步确认点。
     *
     * @remarks 内部路由、fact_id/source_id、证据表和 guardrail 明细不进入主报告；
     * 这些内容留在 trace 和 debug 输出里，避免报告变成工程日志。
     */
    """

    symbol, company = display_entity(run)
    title_name = f"{company}（{symbol}）" if company and company != symbol else symbol
    sections = [
        f"# {title_name} 研究简报",
        "",
        "## 先说结论",
        *executive_summary_lines(run),
        "",
        "## 发生了什么",
        *what_happened_lines(run),
        "",
        "## 关键依据",
        *key_evidence_lines(run),
        "",
        "## 风险与不确定性",
        *risk_and_uncertainty_lines(run),
        "",
        "## 还需要确认",
        *confirmation_lines(run),
        "",
        "## 数据来源与时效",
        *source_summary_lines(run),
    ]
    return "\n".join(sections)


def display_entity(run: ResearchRunState) -> tuple[str, str | None]:
    """/** @returns 用户报告里使用的 symbol 和公司名/检索名。 */"""

    if run.resolved_entity:
        return run.resolved_entity.symbol, run.resolved_entity.company_query or run.resolved_entity.company_name
    symbol = next((fact.symbol for fact in run.facts if fact.symbol), "标的")
    return symbol, None


def executive_summary_lines(run: ResearchRunState) -> list[str]:
    """/** 生成用户最先看到的一句话结论和边界说明。 */"""

    symbol, _ = display_entity(run)
    lines: list[str] = []
    quote = _fact_by_metric(run, "latest_price")
    change_pct = _quote_change_pct(quote)

    if _query_mentions_drop(run.user_query) and change_pct is not None and change_pct >= 0:
        lines.append(
            f"- 当前可用数据并不能证明 {symbol} 正在“大跌”：最新价格快照显示涨跌幅约为 {change_pct:.2f}%。因此，这一轮更适合先核对实时行情，再解释下跌原因。"
        )
    elif _query_mentions_drop(run.user_query):
        lines.append(f"- 这轮问题可以按“{symbol} 为什么下跌”来研究，但当前证据仍不足以直接归因到单一原因。")
    else:
        lines.append(f"- 当前证据足以支持对 {symbol} 做一轮研究梳理，但不足以生成任何买卖、加减仓或持有建议。")

    if run.intake and run.intake.wants_direct_trading_advice:
        lines.append("- 你问法里包含交易动作，我会把它转成研究问题处理，不给直接交易指令。")
    else:
        lines.append("- 下面是基于现有来源的研究判断，不是交易建议。")
    return lines


def what_happened_lines(run: ResearchRunState) -> list[str]:
    """/** 用用户语言解释行情、新闻和公司行动目前各自说明了什么。 */"""

    lines = [
        _quote_line(run),
        _history_line(run),
        _news_line(run),
        _corporate_actions_line(run),
    ]
    return [line for line in lines if line]


def key_evidence_lines(run: ResearchRunState) -> list[str]:
    """/** 输出简洁证据摘要，不暴露 fact_id/source_id。 */"""

    lines: list[str] = []
    quote = _fact_by_metric(run, "latest_price")
    history = _fact_by_metric(run, "five_day_close_range")
    news = _fact_by_metric(run, "news_tone")

    if quote:
        lines.append(f"- 价格证据：{_quote_evidence_text(quote)}")
    if history:
        lines.append(f"- 历史行情证据：{_history_evidence_text(history)}")
    if news:
        titles = _news_titles(news)
        if titles:
            lines.append("- 新闻证据：" + "；".join(titles[:3]))
        else:
            lines.append(f"- 新闻证据：{_humanize_fact_text(news)}")
    if not lines:
        lines.append("- 暂无足够证据，需要先补齐价格、新闻和公司行动数据。")
    return lines


def risk_and_uncertainty_lines(run: ResearchRunState) -> list[str]:
    """/** 汇总用户决策前应看到的风险和未知项。 */"""

    lines = [
        "- 风险：当前数据只能支持研究判断，不能支持直接交易动作。",
        "- 不确定性：最新财报、指引、估值区间、行业周期位置和管理层表述仍需要进一步核验。",
    ]
    if _uses_fixture_data(run):
        lines.append("- 数据限制：当前使用的是演示数据，不应当当作真实市场结论；正式研究需要切换到实时数据源。")
    quality_facts = [fact for fact in run.facts if _is_data_quality_metric(fact.metric)]
    for fact in quality_facts:
        lines.append(f"- 数据质量提示：{_humanize_fact_text(fact)}")
    return lines


def confirmation_lines(run: ResearchRunState) -> list[str]:
    """/** 输出下一步人工确认问题。 */"""

    if not run.human_confirmation_points:
        return ["- 请确认你的研究目标：解释短期下跌、评估中长期 thesis，还是决定是否继续跟踪？"]
    return [f"- {point}" for point in run.human_confirmation_points]


def source_summary_lines(run: ResearchRunState) -> list[str]:
    """/** 用用户可读方式展示来源和时间，不展示内部 source id。 */"""

    if not run.sources:
        return ["- 暂无来源；无法评估时效性。"]
    lines = []
    for source in run.sources:
        source_name = _source_display_name(source)
        lines.append(f"- 来源：{source_name}；获取时间：{source.fetched_at}；可靠性：{_reliability_label(source.reliability)}")
    return lines


def _fact_by_metric(run: ResearchRunState, metric: str) -> Fact | None:
    return next((fact for fact in run.facts if fact.metric == metric), None)


def _quote_change_pct(fact: Fact | None) -> float | None:
    value = fact.value if fact else None
    if isinstance(value, dict) and isinstance(value.get("change_pct"), (int, float)):
        return float(value["change_pct"])
    return None


def _quote_line(run: ResearchRunState) -> str:
    fact = _fact_by_metric(run, "latest_price")
    if not fact or not isinstance(fact.value, dict):
        return "- 价格：当前没有可用的最新价格快照。"
    value = fact.value
    price = value.get("price")
    currency = value.get("currency") or ""
    change = value.get("change_pct")
    if isinstance(change, (int, float)):
        direction = "上涨" if change > 0 else "下跌" if change < 0 else "持平"
        return f"- 价格：最新快照为 {price} {currency}，相对前收盘约{direction} {abs(change):.2f}%。"
    return f"- 价格：最新快照为 {price} {currency}。"


def _history_line(run: ResearchRunState) -> str:
    fact = _fact_by_metric(run, "five_day_close_range")
    if not fact or not isinstance(fact.value, dict):
        return "- 历史行情：当前没有足够的历史价格数据。"
    bars = fact.value.get("bars") or []
    closes = [bar.get("close") for bar in bars if isinstance(bar, dict) and bar.get("close") is not None]
    if not closes:
        return "- 历史行情：有历史数据返回，但缺少收盘价。"
    return f"- 历史行情：近 {len(closes)} 个交易日收盘价区间约为 {min(closes)} 到 {max(closes)}，最新收盘价为 {closes[-1]}。"


def _news_line(run: ResearchRunState) -> str:
    fact = _fact_by_metric(run, "news_tone") or _fact_by_metric(run, "unknown_news")
    if not fact:
        return "- 新闻：当前没有可用新闻摘要。"
    titles = _news_titles(fact)
    if not titles:
        return f"- 新闻：{_humanize_fact_text(fact)}"
    return f"- 新闻：当前召回 {len(titles)} 条相关新闻，主题集中在 {titles[0]} 等线索。"


def _corporate_actions_line(run: ResearchRunState) -> str:
    fact = _fact_by_metric(run, "corporate_actions")
    if not fact or not isinstance(fact.value, dict):
        return "- 公司行动：当前没有公司行动数据。"
    value = fact.value
    splits = value.get("splits_count")
    factor = value.get("cumulative_split_factor")
    return f"- 公司行动：当前来源显示拆股记录数量为 {splits}，累计拆股因子为 {factor}；解释涨跌前需要排除拆股/股息影响。"


def _news_titles(fact: Fact) -> list[str]:
    value = fact.value
    if not isinstance(value, dict):
        return []
    items = value.get("items") or []
    return [str(item.get("title")) for item in items if isinstance(item, dict) and item.get("title")]


def _quote_evidence_text(fact: Fact) -> str:
    value = fact.value
    if isinstance(value, dict):
        price = value.get("price")
        currency = value.get("currency") or ""
        change = value.get("change_pct")
        if isinstance(change, (int, float)):
            direction = "上涨" if change > 0 else "下跌" if change < 0 else "持平"
            return f"最新价格 {price} {currency}，相对前收盘约{direction} {abs(change):.2f}%。"
        return f"最新价格 {price} {currency}。"
    return _humanize_fact_text(fact)


def _history_evidence_text(fact: Fact) -> str:
    value = fact.value
    if isinstance(value, dict):
        bars = value.get("bars") or []
        closes = [bar.get("close") for bar in bars if isinstance(bar, dict) and bar.get("close") is not None]
        if closes:
            return f"近 {len(closes)} 个交易日收盘价区间约为 {min(closes)} 到 {max(closes)}，最新收盘价为 {closes[-1]}。"
    return _humanize_fact_text(fact)


def _reliability_label(reliability: str) -> str:
    return {"high": "高", "medium": "中", "low": "低"}.get(reliability, reliability)


def _humanize_fact_text(fact: Fact) -> str:
    return fact.text.replace(" quote snapshot", " 价格快照").replace("Recent news snapshot", "近期新闻快照")


def _query_mentions_drop(query: str) -> bool:
    return any(term in query for term in ("跌", "大跌", "下跌", "暴跌", "回调", "下挫"))


def _uses_fixture_data(run: ResearchRunState) -> bool:
    return any(source.kind == "local_fixture" or source.name.startswith("fixture") for source in run.sources)


def _source_display_name(source: Source) -> str:
    mapping = {
        "memory.get_preferences": "用户偏好记忆",
        "finance.get_quote": "价格快照",
        "finance.get_history": "历史行情",
        "news.get_news": "新闻检索",
        "corporate_actions.get_corporate_actions": "公司行动",
        "research.data_quality_check": "数据质量检查",
    }
    return mapping.get(source.tool_name or "", source.name)


def user_question_lines(run: ResearchRunState) -> list[str]:
    """/**
     * 为报告格式化用户原始问题和入口分类结果。
     *
     * @param run - 包含可选 QueryIntake 的 research run。
     * @returns “用户问题”章节使用的 Markdown bullet 行。
     *
     * @remarks 如果检测到直接交易动词，这个章节会在证据讨论开始前先展示边界。
     */
    """

    lines = [f"- 用户问题: {run.user_query}"]
    if run.intake:
        lines.append(f"- 识别语言: {run.intake.language}; 请求类型: {run.intake.requested_output}")
        if run.intake.wants_direct_trading_advice:
            lines.append("- 入口边界: 检测到直接交易动作，后续只转化为研究问题和需要确认的条件。")
    return lines


def entity_and_intent_lines(run: ResearchRunState) -> list[str]:
    """/**
     * 格式化已解析公司/ticker 和选中的工作流路由。
     *
     * @param run - 包含 ResolvedEntity 和 IntentRoute 的 research run。
     * @returns “标的识别与意图”章节使用的 Markdown bullet 行。
     *
     * @remarks 这样可以审计别名处理；例如 美光、Micron、MU 都应该展示为解析到 MU/Micron。
     */
    """

    lines: list[str] = []
    if run.resolved_entity:
        entity = run.resolved_entity
        name = f"; company={entity.company_name}" if entity.company_name else ""
        lines.append(
            f"- 标的识别: {entity.raw_mention} -> {entity.symbol}; news/company query={entity.company_query}{name}; confidence={entity.confidence}"
        )
    else:
        lines.append("- 标的识别: 未识别，使用保守默认值。")
    if run.intent_route:
        lines.append(f"- 意图路由: {run.intent_route.route}; rationale={run.intent_route.rationale}")
    else:
        lines.append("- 意图路由: 未记录。")
    return lines


def research_plan_lines(run: ResearchRunState) -> list[str]:
    """/**
     * 格式化 research planner 选出的事实清单。
     *
     * @param run - 包含可选 ResearchPlan 的 research run。
     * @returns 列出必需/可选 事实需求 的 Markdown bullet 行。
     *
     * @remarks 即使可选 事实需求 的 数据提供器 还没实现，也会刻意展示出来；这样产品缺口是显性的，而不是藏在 综合步骤里。
     */
    """

    if not run.research_plan:
        return ["- 未生成显式研究计划。"]
    lines = ["- 必需事实 / 工具："]
    for need in run.research_plan.fact_needs:
        required_label = "必需" if need.required else "可选"
        lines.append(f"  - {need.key}: {need.tool_name} ({required_label}) - {need.reason}")
    if run.research_plan.boundary_notes:
        lines.append("- 边界说明：")
        lines.extend(f"  - {note}" for note in run.research_plan.boundary_notes)
    return lines


def build_evidence_rows(run: ResearchRunState) -> list[EvidenceRow]:
    rows: list[EvidenceRow] = []
    for claim in run.claims:
        for evidence in claim.evidence:
            fact = run.fact_by_id(evidence.fact_id)
            source = run.source_by_id(evidence.source_id)
            if fact is None or source is None:
                continue
            rows.append(_evidence_row(claim, evidence, fact, source))
    return rows


def memo_trace_payload(run: ResearchRunState) -> dict[str, object]:
    """/**
     * 为已渲染 memo 构建紧凑的 trace metadata。
     *
     * @param run - 用于渲染 memo 的 research run。
     * @returns 可 JSON 序列化的 payload，包含 memo 格式、证据数量、resolved symbol、intent route 和 fact-plan keys。
     */
    """

    rows = build_evidence_rows(run)
    return {
        "format": "investment_memo_v2",
        "sections": MEMO_SECTIONS,
        "evidence_row_count": len(rows),
        "resolved_symbol": run.resolved_entity.symbol if run.resolved_entity else None,
        "intent_route": run.intent_route.route if run.intent_route else None,
        "fact_need_keys": [need.key for need in run.research_plan.fact_needs] if run.research_plan else [],
        "claim_ids": [claim.id for claim in run.claims],
        "fact_ids": [fact.id for fact in run.facts],
        "source_ids": [source.id for source in run.sources],
    }


def claim_lines(claims: list[Claim]) -> list[str]:
    if not claims:
        return ["- 未生成对应 claim；需要更多可追踪事实或人工补充。"]
    lines = []
    for claim in claims:
        evidence_refs = [f"{e.fact_id}/{e.source_id}" for e in claim.evidence]
        lines.append(f"- {claim.text} 证据: {', '.join(evidence_refs)}")
    return lines


def fact_lines(facts: list[Fact]) -> list[str]:
    if not facts:
        return ["- 暂无可用 fact。"]
    return [
        (
            f"- {fact.text} 来源: {', '.join(fact.source_ids)}; "
            f"observed_at: {fact.observed_at}; metric: {fact.metric}"
        )
        for fact in facts
    ]


def evidence_table_lines(rows: list[EvidenceRow]) -> list[str]:
    if not rows:
        return ["- 暂无证据行；guardrail 应阻断缺少证据的关键 claim。"]
    lines = [
        "| Claim | Claim 类型 | Fact | Fact 指标 | Source | Source fetched_at | Fact observed_at |",
        "|---|---|---|---|---|---|---|",
    ]
    for row in rows:
        lines.append(
            "| "
            f"{_cell(row.claim_text)} ({row.claim_id}) | "
            f"{_cell(row.claim_type)} | "
            f"{_cell(row.fact_text)} ({row.fact_id}) | "
            f"{_cell(row.fact_metric)} | "
            f"{_cell(row.source_name)} ({row.source_id}) | "
            f"{_cell(row.source_fetched_at)} | "
            f"{_cell(row.fact_observed_at)} |"
        )
    return lines


def freshness_lines(run: ResearchRunState) -> list[str]:
    if not run.sources:
        return ["- 暂无来源；无法评估时效性。"]
    lines = [
        (
            f"- 来源 {source.id}: {source.name}; tool={source.tool_name}; "
            f"fetched_at={source.fetched_at}; reliability={source.reliability}"
        )
        for source in run.sources
    ]
    quality_facts = [fact for fact in run.facts if _is_data_quality_metric(fact.metric)]
    if quality_facts:
        lines.append("- 数据质量限制:")
        lines.extend(f"  - {fact.metric}: {fact.text}" for fact in quality_facts)
    return lines


def _evidence_row(claim: Claim, evidence: Evidence, fact: Fact, source: Source) -> EvidenceRow:
    return EvidenceRow(
        claim_id=claim.id,
        claim_type=claim.claim_type,
        claim_text=claim.text,
        fact_id=fact.id,
        fact_metric=fact.metric or "unknown_metric",
        fact_text=evidence.quote or fact.text,
        source_id=source.id,
        source_name=source.name,
        source_fetched_at=source.fetched_at,
        fact_observed_at=fact.observed_at,
    )


def _is_data_quality_metric(metric: str | None) -> bool:
    if not metric:
        return False
    return metric.startswith(("stale_", "missing_", "failure_", "unknown_", "conflicting_"))


def _cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")
