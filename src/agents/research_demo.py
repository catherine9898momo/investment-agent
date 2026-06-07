"""基于证据的研究 demo，用于验证 P0 投资研究边界。

默认模式优先使用 live 数据源，尽量复用真实 MCP server 后端函数获取 quote/history/news/corporate-actions 结果。
fixture 只作为离线测试模式；如果 live 依赖或网络不可用，系统会生成可追踪的缺失证据，而不是伪装成真实结论。
"""

from __future__ import annotations

import argparse
from dataclasses import asdict

from src.research.evaluator import evaluate_research_output
from src.research.fact_verifier import build_verified_fact_table
from src.research.memo_renderer import memo_trace_payload, render_investment_memo
from src.research.models import ResearchRunState, to_json
from src.research.normalizers import normalize_tool_result_bundle
from src.research.query_intake import QueryUnderstanding, understand_query
from src.research.synthesizer import bind_claims_to_evidence, make_synthesizer
from src.research.tool_provider import ToolResultBundle, make_tool_provider
from src.research.trace import TraceLogger


DEFAULT_QUERY = "帮我看 TSLA 最近是否还值得继续关注。"
DEFAULT_SYMBOL = "TSLA"
DEFAULT_COMPANY_QUERY = "Tesla"

EXIT_COMMANDS = {"/exit", "/quit", "exit", "quit"}
HELP_COMMANDS = {"/help", "help", "?"}
CONFIG_COMMANDS = {"/config", "config"}
JSON_COMMANDS = {"/json", "json"}
DEBUG_COMMANDS = {"/debug", "debug"}


def build_research_run(
    user_query: str,
    synthesizer_name: str = "mock",
    data_source: str = "live",
    symbol: str | None = None,
    company_query: str | None = None,
    history_days: int = 5,
    news_days: int = 7,
) -> ResearchRunState:
    """/**
     * 基于用户问题和指定数据源构建完整研究 run。
     *
     * @param user_query - 用户原始问题。
     * @param synthesizer_name - mock 用于确定性的离线运行；anthropic 用于真实 LLM 综合。
     * @param data_source - fixture 用于离线验证；live 使用 MCP 后端数据提供器。
     * @param symbol - 可选 ticker 覆盖值，会绕过自动标的识别。
     * @param company_query - 可选新闻/公司检索覆盖值。
     * @param history_days - 价格历史事实的回看窗口。
     * @param news_days - 新闻事实的回看窗口。
     * @returns 带有 入口解析、路由、标的、计划、事实、结论、memo 和 guardrail 的 ResearchRunState。
     *
     * @remarks 这是 CLI/demo 使用的面向用户入口。它会在拉取工具数据前调用 understand_query，让解析出的标的决定 symbol 和 company query。
     */
    """

    understanding = understand_query(user_query, symbol_override=symbol, company_query_override=company_query)
    provider = make_tool_provider(data_source)
    bundle = provider.fetch(understanding.entity.symbol, understanding.entity.company_query, history_days, news_days)
    return build_research_run_from_bundle(
        user_query,
        bundle,
        synthesizer_name=synthesizer_name,
        symbol=understanding.entity.symbol,
        understanding=understanding,
    )


def build_research_run_from_bundle(
    user_query: str,
    bundle: ToolResultBundle,
    synthesizer_name: str = "mock",
    symbol: str | None = None,
    understanding: QueryUnderstanding | None = None,
) -> ResearchRunState:
    """/**
     * 基于已经获取到的工具结果构建 research run。
     *
     * @param user_query - 用于 trace/report 上下文的用户原始问题。
     * @param bundle - 工具形态的结果包，通常来自 fixture 或 live provider。
     * @param synthesizer_name - synthesizer 实现名称。
     * @param symbol - 没有传入 QueryUnderstanding 时使用的可选 fallback symbol。
     * @param understanding - 可选的预计算 intake/router/entity/plan 包。
     * @returns 经过 guardrail 评估后的 completed 或 blocked ResearchRunState。
     *
     * @remarks eval fixture 可以直接传入 bundle，同时仍然获得同一套用户入口契约。query_understanding trace 事件是这一层的审计点。
     */
    """

    if understanding is None:
        understanding = understand_query(user_query, symbol_override=symbol)
    run = ResearchRunState.start(user_query=user_query)
    run.intake = understanding.intake
    run.intent_route = understanding.route
    run.resolved_entity = understanding.entity
    run.research_plan = understanding.plan
    run.time_window = understanding.time_window
    run.attribution_plan = understanding.attribution_plan

    trace = TraceLogger(run)
    trace.append("run_started", {"run_id": run.run_id, "query": user_query})
    trace.append("query_understanding", understanding)

    trace_tool_results(trace, bundle)

    normalized = normalize_tool_result_bundle(bundle, understanding.entity.symbol)
    run.sources.extend(normalized.sources)
    run.facts.extend(normalized.facts)

    for source in run.sources:
        trace.append("source_added", source)
    for fact in run.facts:
        trace.append("fact_added", fact)

    verified_facts, missing_facts = build_verified_fact_table(run.facts, run.attribution_plan)
    run.verified_facts = verified_facts
    run.missing_facts = missing_facts
    trace.append("verified_fact_table", {"verified_facts": verified_facts, "missing_facts": missing_facts})

    synthesizer = make_synthesizer(synthesizer_name)
    synthesis = synthesizer.synthesize(run)
    trace.append("synthesis_result", synthesis)

    run.claims.extend(bind_claims_to_evidence(run, synthesis))
    run.human_confirmation_points = synthesis.human_confirmation_points
    run.raw_synthesis = synthesis.raw_model_output
    for claim in run.claims:
        trace.append("claim_added", claim)

    output = render_research_output(run)
    trace.append("memo_rendered", memo_trace_payload(run))
    guardrail = evaluate_research_output(run, output)
    run.guardrail = guardrail
    run.final_output = output
    run.status = "completed" if guardrail.passed else "blocked"

    trace.append("final_output", {"text": output})
    trace.append("guardrail_result", guardrail)
    trace.append("run_completed", asdict(run))
    return run

def trace_tool_results(trace: TraceLogger, bundle: ToolResultBundle) -> None:
    trace.append("tool_result", {"tool": "memory.get_preferences", "result": bundle.preferences})
    trace.append("tool_result", {"tool": "finance.get_quote", "result": bundle.quote})
    trace.append("tool_result", {"tool": "finance.get_history", "result": bundle.history})
    trace.append("tool_result", {"tool": "news.get_news", "result": bundle.news})
    trace.append("tool_result", {"tool": "corporate_actions.get_corporate_actions", "result": bundle.corporate_actions})


def render_research_output(run: ResearchRunState) -> str:
    return render_investment_memo(run)


def print_interactive_help() -> None:
    """/**
     * 打印交互式 research demo 的会话命令。
     *
     * @remarks 这里模仿 Claude Code CLI 的基本体验：启动后持续输入问题，
     * 用 slash command 查看帮助、配置或退出。
     */
    """

    print(
        "可用命令:\n"
        "  /help      查看帮助\n"
        "  /config    查看当前数据源、synthesizer 和覆盖参数\n"
        "  /json      切换 JSON / Markdown 输出\n"
        "  /debug     切换是否显示 guardrail/debug 信息\n"
        "  /exit      退出会话\n"
    )


def print_run_result(run: ResearchRunState, as_json: bool = False, debug: bool = False) -> None:
    """/**
     * 打印单轮研究结果。
     *
     * @param run - 已完成或被 guardrail 阻断的研究 run。
     * @param as_json - 为 True 时打印完整 JSON；否则打印用户可读 memo。
     * @param debug - 为 True 时额外打印 guardrail 检查明细。
     */
    """

    if as_json:
        print(to_json(run))
        return

    print(run.final_output)
    if not debug:
        return

    print()
    print("Debug / Guardrail:", "PASS" if run.guardrail and run.guardrail.passed else "BLOCKED")
    if run.guardrail:
        for check in run.guardrail.checks:
            status = "PASS" if check.passed else "FAIL"
            print(f"- {status} {check.name}: {check.message}")


def build_parser() -> argparse.ArgumentParser:
    """/**
     * 构建 research demo CLI 参数。
     *
     * @returns argparse.ArgumentParser。
     *
     * @remarks 不传 --query 时进入交互式会话；传 --query 时保持旧的一次性
     * 执行模式，方便脚本、回归测试和 smoke test 继续使用。
     */
    """

    parser = argparse.ArgumentParser(description="投资研究 demo。默认进入交互式会话；传 --query 时执行单轮研究。")
    parser.add_argument("--query", default=None, help="单轮研究问题。不传时进入交互式会话。")
    parser.add_argument("--symbol", default=None, help=f"手动覆盖标的解析出的 symbol。默认先解析 query，未识别时回退到 {DEFAULT_SYMBOL}。")
    parser.add_argument("--company-query", default=None, help=f"手动覆盖新闻/公司检索 query。默认先解析 query，未识别时回退到 {DEFAULT_COMPANY_QUERY}。")
    parser.add_argument("--history-days", type=int, default=5, help="价格历史事实的回看天数。")
    parser.add_argument("--news-days", type=int, default=7, help="新闻事实的回看天数。")
    parser.add_argument(
        "--data-source",
        choices=["fixture", "live"],
        default="live",
        help="live 会复用真实 MCP server 后端函数；fixture 是确定性离线测试数据。",
    )
    parser.add_argument(
        "--synthesizer",
        choices=["mock", "anthropic"],
        default="mock",
        help="mock 是确定性离线路径；anthropic 需要 ANTHROPIC_API_KEY 和网络访问。",
    )
    parser.add_argument("--json", action="store_true", help="打印 run state JSON，而不是 markdown 输出。交互模式中可用 /json 切换。")
    parser.add_argument("--debug", action="store_true", help="额外打印 guardrail 检查明细。交互模式中可用 /debug 切换。")
    return parser


def run_one_query(args: argparse.Namespace, query: str, as_json: bool | None = None, debug: bool | None = None) -> ResearchRunState:
    """/**
     * 执行一轮研究问题。
     *
     * @param args - CLI 参数命名空间。
     * @param query - 本轮用户输入的问题。
     * @param as_json - 可选输出模式覆盖；None 时使用 args.json。
     * @param debug - 可选 debug 输出覆盖；None 时使用 args.debug。
     * @returns 本轮 ResearchRunState。
     */
    """

    run = build_research_run(
        query,
        synthesizer_name=args.synthesizer,
        data_source=args.data_source,
        symbol=args.symbol,
        company_query=args.company_query,
        history_days=args.history_days,
        news_days=args.news_days,
    )
    print_run_result(run, args.json if as_json is None else as_json, args.debug if debug is None else debug)
    return run


def print_config(args: argparse.Namespace, as_json: bool, debug: bool) -> None:
    """/** 打印当前会话配置，方便用户确认本轮会话是否在 fixture/live、mock/anthropic 等模式下运行。 */"""

    print(
        "当前配置:\n"
        f"  data_source: {args.data_source}\n"
        f"  synthesizer: {args.synthesizer}\n"
        f"  symbol_override: {args.symbol or '-'}\n"
        f"  company_query_override: {args.company_query or '-'}\n"
        f"  history_days: {args.history_days}\n"
        f"  news_days: {args.news_days}\n"
        f"  output: {'JSON' if as_json else 'Markdown'}\n"
        f"  debug: {'on' if debug else 'off'}"
    )


def interactive_loop(args: argparse.Namespace) -> None:
    """/**
     * 启动类似 Claude Code CLI 的交互式研究会话。
     *
     * @param args - CLI 参数命名空间，用作每一轮研究的默认配置。
     *
     * @remarks 当前会话是“多轮输入、逐轮研究”的本地 demo；每轮都会重新
     * 走 query intake、工具结果归一化、synthesis、guardrail 和 memo 渲染。
     */
    """

    as_json = args.json
    debug = args.debug
    print("investment-agent research CLI")
    print("直接输入研究问题开始。输入 /help 查看命令，/exit 退出。\n")

    while True:
        try:
            user_input = input("research> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n已退出。")
            return

        if not user_input:
            continue
        if user_input in EXIT_COMMANDS:
            print("已退出。")
            return
        if user_input in HELP_COMMANDS:
            print_interactive_help()
            continue
        if user_input in CONFIG_COMMANDS:
            print_config(args, as_json, debug)
            continue
        if user_input in JSON_COMMANDS:
            as_json = not as_json
            print(f"输出模式已切换为 {'JSON' if as_json else 'Markdown'}。")
            continue
        if user_input in DEBUG_COMMANDS:
            debug = not debug
            print(f"Debug 输出已{'开启' if debug else '关闭'}。")
            continue

        try:
            run_one_query(args, user_input, as_json=as_json, debug=debug)
        except Exception as exc:  # noqa: BLE001 - 交互会话里单轮失败不应直接退出。
            print(f"本轮研究失败: {exc.__class__.__name__}: {exc}")


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.query:
        run_one_query(args, args.query)
        return

    interactive_loop(args)


if __name__ == "__main__":
    main()
