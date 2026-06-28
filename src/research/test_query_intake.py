from src.research.query_intake import parse_query_intake, resolve_entity, route_intent, understand_query


def test_resolves_micron_aliases_to_mu() -> None:
    assert resolve_entity("帮我看美光的AI内存周期").symbol == "MU"
    assert resolve_entity("Micron valuation memo").symbol == "MU"
    assert resolve_entity("MU 最近为什么跌").company_query == "Micron"


def test_resolves_moutai_aliases_to_a_share_symbol() -> None:
    assert resolve_entity("茅台最近表现怎么样？").symbol == "600519.SS"
    assert resolve_entity("贵州茅台最近为什么跌？").company_query == "贵州茅台"
    assert resolve_entity("600519.SS 最近表现怎么样？").company_name == "贵州茅台股份有限公司"


def test_routes_news_and_valuation_queries() -> None:
    news = understand_query("腾讯为什么跌，最近新闻是什么？")
    assert news.entity.symbol == "0700.HK"
    assert news.route.route == "news_explanation"
    assert "news" in {need.key for need in news.plan.fact_needs}
    assert news.time_window
    assert news.attribution_plan

    valuation = understand_query("美光现在估值贵吗？")
    assert valuation.entity.symbol == "MU"
    assert valuation.route.route == "valuation_review"
    assert {"valuation_facts", "risk_facts"}.issubset({need.key for need in valuation.plan.fact_needs})


def test_direct_trade_advice_is_routed_to_boundary() -> None:
    intake = parse_query_intake("TSLA 现在可以加仓吗？")
    route = route_intent(intake)

    assert intake.wants_direct_trading_advice is True
    assert intake.requested_output == "trade_advice"
    assert route.route == "direct_trade_advice_boundary"


def test_symbol_override_takes_precedence() -> None:
    entity = resolve_entity("帮我看 Tesla", symbol_override="MU", company_query_override="Micron")

    assert entity.symbol == "MU"
    assert entity.company_query == "Micron"
    assert entity.confidence == "high"


def test_routes_drop_language_to_news_explanation() -> None:
    understanding = understand_query("美光最近为什么会大跌？")

    assert understanding.entity.symbol == "MU"
    assert understanding.route.route == "news_explanation"
    assert understanding.attribution_plan.question_type == "price_drop"
