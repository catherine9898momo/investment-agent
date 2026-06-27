"""Deterministic investment memo renderer for research runs."""

from __future__ import annotations

from dataclasses import dataclass

from src.research.data_quality import classify_history_points, finite_closes
from src.research.models import Claim, Evidence, Fact, ResearchRunState, Source


MEMO_SECTIONS = [
    "研究结论",
    "原因排序",
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
        "## 研究结论",
        *executive_summary_lines(run),
        "",
        "## 原因排序",
        *cause_ranking_lines(run),
        "",
        "## 归因证据矩阵",
        *attribution_matrix_lines(run),
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
    """/** 生成用户最先看到的研究结论，而不是事实罗列。 */"""

    symbol, _ = display_entity(run)
    lines: list[str] = []
    if run.time_window:
        lines.append(f"- 研究窗口：{run.time_window.label}（{run.time_window.start_date} 至 {run.time_window.end_date}）。")

    change_pct = _quote_change_pct(_fact_by_metric(run, "latest_price"))
    news_titles = _all_news_titles(run)
    causes = _infer_cause_candidates(run)
    confidence = _attribution_confidence(run, causes)

    if _query_mentions_drop(run.user_query):
        if change_pct is not None and change_pct >= 0:
            lines.append(
                f"- 结论：当前可核验价格并不支持“{symbol} 最近大跌”这个前提；最新价格快照显示约上涨 {change_pct:.2f}%。应先核对你所指的具体日期或交易时段。"
            )
        elif run.attribution_causes:
            primary = run.attribution_causes[0]
            move_text = f"，价格快照显示跌幅约 {abs(change_pct):.2f}%" if change_pct is not None else ""
            lines.append(
                f"- 结论：当前最重要的候选解释是“{primary.label}”{move_text}，归因等级为“{_attribution_level_label(primary.level)}”。"
            )
            lines.append(f"- 置信度：{_confidence_label(primary.confidence)}。{_humanize_attribution_rationale(primary.rationale)}")
        elif causes:
            primary = causes[0]
            move_text = f"，价格快照显示跌幅约 {abs(change_pct):.2f}%" if change_pct is not None else ""
            lines.append(
                f"- 结论：这次更像是“{primary['label']}”相关的回撤{move_text}，但仍需 sector/peer 证据确认。"
            )
            lines.append(f"- 置信度：{confidence}。原因是已有价格/新闻线索，但板块 ETF、同行涨跌和宏观背景仍未完全核验。")
        else:
            lines.append(f"- 结论：可以按“{symbol} 为什么下跌”来研究，但当前缺少足够证据，不能负责任地给出确定归因。")
    elif causes:
        lines.append(f"- 结论：当前最主要的研究线索是“{causes[0]['label']}”，但仍需要更多实时市场背景确认。")
    else:
        lines.append(f"- 结论：当前证据足以支持对 {symbol} 做一轮研究梳理，但不足以形成明确归因或交易建议。")

    if news_titles:
        lines.append(f"- 已核验新闻线索：{news_titles[0]}")
    if run.intake and run.intake.wants_direct_trading_advice:
        lines.append("- 你问法里包含交易动作，我会把它转成研究问题处理，不给直接交易指令。")
    else:
        lines.append("- 这不是交易建议；它只是基于已核验证据和缺失证据的研究判断。")
    return lines


def cause_ranking_lines(run: ResearchRunState) -> list[str]:
    """/** 把可核验线索压成主因/次因/排除项。 */"""

    causes = _infer_cause_candidates(run)
    lines: list[str] = []
    change_pct = _quote_change_pct(_fact_by_metric(run, "latest_price"))
    if _query_mentions_drop(run.user_query) and change_pct is not None and change_pct >= 0:
        lines.append("1. **暂不做下跌归因**：当前可核验价格没有确认下跌，先需要确认你指的是哪一天、哪个交易时段或哪个价格口径。")
        return lines
    if causes:
        for idx, cause in enumerate(causes, start=1):
            lines.append(f"{idx}. **{cause['label']}**：{cause['reason']}")
    else:
        lines.append("1. **暂不能排序**：当前缺少足够的价格、新闻或板块证据，不能把原因写成确定结论。")

    if _has_corporate_actions_fact(run):
        lines.append("- **已排除/低优先级因素**：当前公司行动数据没有显示本轮涨跌可直接归因于拆股或股息；它更像是需要排除的背景项。")
    for missing in _important_missing_facts(run):
        if missing.fact_type in {"sector_move", "peer_moves"}:
            lines.append(f"- **仍需核验**：{missing.reason}")
    return lines



def attribution_matrix_lines(run: ResearchRunState) -> list[str]:
    if not run.attribution_causes:
        return ["- 暂无结构化归因等级；需要补齐价格、新闻、板块和同行事实。"]
    lines: list[str] = []
    for cause in run.attribution_causes:
        lines.append(f"- **{cause.label}**：{_attribution_level_label(cause.level)}；置信度：{_confidence_label(cause.confidence)}。")
        if cause.rationale:
            lines.append(f"  - 降级/升级理由：{_humanize_attribution_rationale(cause.rationale)}")
        if cause.missing_fact_types:
            lines.append(f"  - 证据缺口：{', '.join(_fact_type_label(item) for item in cause.missing_fact_types)}")
        if cause.next_checks:
            lines.append(f"  - 下一步核验：{'；'.join(cause.next_checks)}")
    return lines


def _attribution_level_label(level: str) -> str:
    return {
        "confirmed_cause": "已确认原因",
        "likely_factor": "较可能因素",
        "candidate_factor": "候选因素",
        "background_context": "背景信息",
        "unsupported": "证据不支持",
    }.get(level, level)


def _confidence_label(confidence: str) -> str:
    return {"high": "高", "medium": "中", "low": "低"}.get(confidence, confidence)


def _fact_type_label(fact_type: str) -> str:
    return {
        "sector_move": "板块/指数对照",
        "peer_moves": "同行对照",
        "news_events": "新闻事件",
        "price_move": "价格变化",
    }.get(fact_type, fact_type)


def _humanize_attribution_rationale(rationale: str) -> str:
    mapping = {
        "Sector and peer coverage supports a likely factor.": "板块和同行覆盖足以支持较可能因素。",
        "Sector and peer coverage supports a likely factor. Partial symbol failures remain.": "板块和同行覆盖足以支持较可能因素，但仍有部分 symbol 拉取失败。",
        "Comparison coverage is insufficient for a likely factor.": "板块/同行覆盖不足，不能升级为较可能因素。",
        "Price/news evidence is present but sector/peer confirmation is incomplete.": "已有价格/新闻线索，但板块和同行确认不完整。",
    }
    return mapping.get(rationale, rationale)

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
    if run.time_window:
        lines.append(f"- 研究窗口：{run.time_window.label}（{run.time_window.start_date} 至 {run.time_window.end_date}）。")
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
    for missing in _important_missing_facts(run):
        prefix = "关键缺口" if missing.required else "可选缺口"
        lines.append(f"- {prefix}：{missing.reason}")
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
    if run.verified_facts or run.missing_facts:
        lines.append(f"- 事实核验：已形成 {len(run.verified_facts)} 条可追踪事实，另有 {len(run.missing_facts)} 项证据缺口。")
    if run.trace_path:
        lines.append(f"- Trace 日志：{run.trace_path}")
    return lines


def _infer_cause_candidates(run: ResearchRunState) -> list[dict[str, str]]:
    titles = _all_news_titles(run)
    title_blob = " ".join(titles).lower()
    causes: list[dict[str, str]] = []

    if any(keyword in title_blob for keyword in ("chip sector", "semiconductor", "sector suffers", "worst day", "芯片", "半导体")):
        causes.append({
            "label": "半导体板块风险偏好回落",
            "reason": "已核验新闻标题直接提到芯片/半导体板块承压；这说明下跌可能不只是美光单一事件，但仍需用 SOXX/SMH 和同行涨跌进一步确认。",
        })
    if any(keyword in title_blob for keyword in ("stock falls", "shares tumble", "falls again", "大跌", "下跌")):
        causes.append({
            "label": "个股交易情绪转弱",
            "reason": "新闻线索显示 MU 股价连续走弱或 shares tumble，说明市场短期情绪承压；但这不是完整基本面归因。",
        })
    if any(keyword in title_blob for keyword in ("demand", "margin", "competition", "需求", "利润率", "竞争")):
        causes.append({
            "label": "需求、利润率或竞争预期被重新定价",
            "reason": "已核验新闻线索集中在需求、利润率或竞争压力，这更像预期层面的重新定价，而不是单一公司行动。",
        })
    if any(keyword in title_blob for keyword in ("ceo", "sold", "insider", "出售")):
        causes.append({
            "label": "管理层减持/获利了结引发的情绪压力",
            "reason": "已核验新闻标题提到 CEO 出售股票，这类信息通常会放大短期获利了结或情绪压力，但需要核验交易规模、计划性质和公告时间。",
        })
    if any(keyword in title_blob for keyword in ("approval", "nvidia", "memory-chip", "surged")):
        causes.append({
            "label": "利好兑现后的预期回撤",
            "reason": "新闻线索显示此前存在 Nvidia 相关存储芯片认可或股价大涨背景；如果利好后仍下跌，更像预期兑现后的回撤，需要结合涨幅和估值核验。",
        })
    change_pct = _quote_change_pct(_fact_by_metric(run, "latest_price"))
    if not causes and change_pct is not None and change_pct < 0:
        causes.append({
            "label": "价格层面的短期回撤",
            "reason": "价格快照显示短期下跌，但当前新闻、板块和同行证据不足，不能进一步确定具体原因。",
        })
    return causes


def _attribution_confidence(run: ResearchRunState, causes: list[dict[str, str]]) -> str:
    missing_required = {missing.fact_type for missing in run.missing_facts if missing.required}
    if not causes:
        return "低"
    if {"sector_move", "peer_moves"}.intersection(missing_required):
        return "中低"
    if missing_required:
        return "中"
    return "中高"


def _all_news_titles(run: ResearchRunState) -> list[str]:
    titles: list[str] = []
    for metric in ("news_tone", "unknown_news"):
        fact = _fact_by_metric(run, metric)
        if fact:
            titles.extend(_news_titles(fact))
    return titles


def _has_corporate_actions_fact(run: ResearchRunState) -> bool:
    return _fact_by_metric(run, "corporate_actions") is not None


def _important_missing_facts(run: ResearchRunState) -> list:
    if not run.missing_facts:
        return []
    priority = {"sector_move", "peer_moves", "earnings_or_guidance", "macro_context", "analyst_actions"}
    return [missing for missing in run.missing_facts if missing.fact_type in priority]


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
    insufficient = _fact_by_metric(run, "data_quality_history_insufficient")
    if insufficient:
        return "- 历史行情：历史行情数据不足，本轮不能使用历史走势作为归因证据。"
    fact = _fact_by_metric(run, "five_day_close_range")
    if not fact or not isinstance(fact.value, dict):
        return "- 历史行情：当前没有足够的历史价格数据。"
    bars = fact.value.get("bars") or []
    closes = _finite_closes(bars)
    classification = classify_history_points(closes)
    if not closes:
        return "- 历史行情：有历史数据返回，但缺少收盘价。"
    suffix = ""
    if not classification.window_complete:
        suffix = "；但历史窗口不完整，趋势判断需要降级。"
    return f"- 历史行情：近 {len(closes)} 个有效交易日收盘价区间约为 {min(closes)} 到 {max(closes)}，最新收盘价为 {closes[-1]}{suffix}"


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


def _finite_closes(bars: list) -> list[float]:
    return finite_closes(bars)


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
        closes = _finite_closes(bars)
        if closes:
            classification = classify_history_points(closes)
            suffix = "；历史窗口不完整，不能单独支撑趋势判断" if not classification.window_complete else ""
            return f"近 {len(closes)} 个有效交易日收盘价区间约为 {min(closes)} 到 {max(closes)}，最新收盘价为 {closes[-1]}{suffix}。"
    return _humanize_fact_text(fact)


def _reliability_label(reliability: str) -> str:
    return {"high": "高", "medium": "中", "low": "低"}.get(reliability, reliability)


def _humanize_fact_text(fact: Fact) -> str:
    if fact.metric and fact.metric.startswith("failure_"):
        return _humanize_failure_fact(fact)
    if fact.metric and fact.metric.startswith("missing_news"):
        return "新闻结果缺失，暂时不能支持新近新闻归因。"
    if fact.metric == "data_quality_history_insufficient":
        return "历史行情数据不足，不能支持区间或趋势判断。"
    if fact.metric == "data_quality_history_window_incomplete":
        return "历史行情窗口不完整，趋势判断需要降级。"
    if fact.metric == "data_quality_corporate_action_adjustment_uncertain":
        return "研究窗口内存在公司行动，但 quote/history 复权口径不明。"
    if fact.metric == "price_provenance_uncertain":
        return "价格与历史行情偏离较大，需要复核 provenance 后再做强归因。"
    return fact.text.replace(" quote snapshot", " 价格快照").replace("Recent news snapshot", "近期新闻快照")


def _humanize_failure_fact(fact: Fact) -> str:
    tool_label = {
        "failure_latest_price": "价格工具",
        "failure_five_day_close_range": "历史行情工具",
        "failure_news_tone": "新闻工具",
        "failure_corporate_actions": "公司行动工具",
    }.get(fact.metric or "", "数据工具")
    return f"{tool_label}本轮未能返回可核验结果；相关结论需要等待实时数据补齐。"


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
    return metric.startswith(("stale_", "missing_", "failure_", "unknown_", "conflicting_", "data_quality_", "price_provenance_"))


def _cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")
