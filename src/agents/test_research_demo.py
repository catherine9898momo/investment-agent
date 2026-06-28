from src.agents.research_demo import build_parser, build_research_run


def test_build_research_run_uses_query_understanding_for_entity_and_plan() -> None:
    run = build_research_run("帮我看美光 MU 最近是否还值得研究。", data_source="fixture")

    assert run.resolved_entity is not None
    assert run.resolved_entity.symbol == "MU"
    assert run.intent_route is not None
    assert run.intent_route.route == "company_research_memo"
    assert run.research_plan is not None
    assert run.time_window is not None
    assert run.attribution_plan is not None
    assert run.verified_facts
    assert {"price", "history", "news", "corporate_actions"}.issubset({need.key for need in run.research_plan.fact_needs})
    assert run.final_output is not None
    assert "MU" in run.final_output
    assert "## 一句话结论" in run.final_output
    assert "## 最可能的原因" in run.final_output
    assert "## 证据表" not in run.final_output
    assert "fact_" not in run.final_output


def test_research_demo_parser_defaults_to_interactive_mode() -> None:
    args = build_parser().parse_args([])

    assert args.query is None
    assert args.data_source == "live"
    assert args.synthesizer == "mock"
    assert args.debug is False
    assert args.json is False


def test_research_demo_parser_keeps_one_shot_query_mode() -> None:
    args = build_parser().parse_args(["--query", "帮我看 MU", "--symbol", "MU"])

    assert args.query == "帮我看 MU"
    assert args.symbol == "MU"


def test_research_demo_parser_supports_debug_mode() -> None:
    args = build_parser().parse_args(["--debug"])

    assert args.debug is True


def test_research_demo_parser_supports_loop_flags() -> None:
    args = build_parser().parse_args(["--loop", "--max-loops", "1", "--quality-threshold", "normal"])

    assert args.loop is True
    assert args.max_loops == 1
    assert args.quality_threshold == "normal"


def test_research_demo_parser_does_not_enable_loop_by_default() -> None:
    args = build_parser().parse_args([])

    assert args.loop is False
    assert args.max_loops == 1
    assert args.quality_threshold == "normal"


def test_research_demo_parser_supports_enhanced_loop_comparison_flags() -> None:
    args = build_parser().parse_args(["--loop", "--research-depth", "enhanced", "--compare-loop"])

    assert args.loop is True
    assert args.research_depth == "enhanced"
    assert args.compare_loop is True


def test_research_demo_parser_supports_fixture_loop_case() -> None:
    args = build_parser().parse_args(["--fixture-loop-case", "missing-peer-enhanced"])

    assert args.fixture_loop_case == "missing-peer-enhanced"


def test_research_demo_parser_supports_loop_eval_artifact_flags() -> None:
    args = build_parser().parse_args(["--save-loop-eval", "--loop-eval-dir", "artifacts/demo"] )

    assert args.save_loop_eval is True
    assert args.loop_eval_dir == "artifacts/demo"
