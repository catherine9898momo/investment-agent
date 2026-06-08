"""LLM research synthesizer with an offline mock implementation.

The synthesizer is the only layer allowed to turn sourced facts into candidate
research claims. It must return structured data with fact references; the
binder below rejects claims that cannot be tied back to known facts.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any, Protocol
try:
    from dotenv import load_dotenv
except ModuleNotFoundError:
    def load_dotenv() -> None:
        """/**
         * 离线 fixture/mock 运行使用的 空操作兜底函数。
         *
         * @remarks 查询入口和 mock 综合 路径应该能在最小环境里运行；只有 Anthropic/live 路径需要 python-dotenv 提供环境文件支持。
         */
        """

        return None

from src.research.context_builder import build_research_context, research_context_to_prompt_payload
from src.research.models import Claim, Evidence, ResearchRunState, new_id

load_dotenv()

RESEARCH_SYNTHESIS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "claims": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "A complete, standalone research sentence. Do not end mid-phrase."},
                    "claim_type": {
                        "type": "string",
                        "enum": [
                            "supporting_factor",
                            "risk_factor",
                            "fit_assessment",
                            "unknown",
                            "fact_summary",
                        ],
                    },
                    "fact_ids": {"type": "array", "items": {"type": "string"}},
                    "is_key": {"type": "boolean"},
                },
                "required": ["text", "claim_type", "fact_ids", "is_key"],
                "additionalProperties": False,
            },
        },
        "human_confirmation_points": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["claims", "human_confirmation_points"],
    "additionalProperties": False,
}

@dataclass
class CandidateClaim:
    text: str
    claim_type: str
    fact_ids: list[str]
    is_key: bool = True


@dataclass
class SynthesisResult:
    claims: list[CandidateClaim]
    human_confirmation_points: list[str] = field(default_factory=list)
    raw_model_output: str | None = None


class LLMResearchSynthesizer(Protocol):
    def synthesize(self, run: ResearchRunState) -> SynthesisResult:
        """Generate candidate claims from the existing run facts."""


class MockLLMResearchSynthesizer:
    """Deterministic stand-in for the LLM.

    This keeps the P0 demo runnable without network/API dependencies while
    preserving the same input/output contract a real LLM must follow.
    """

    def synthesize(self, run: ResearchRunState) -> SynthesisResult:
        fact_by_metric = {fact.metric: fact for fact in run.facts if fact.metric}
        entity_symbol = run.resolved_entity.symbol if run.resolved_entity else (run.facts[0].symbol or "the company")
        entity_name = run.resolved_entity.company_query if run.resolved_entity else entity_symbol
        price_fact = fact_by_metric.get("latest_price") or run.facts[0]
        news_fact = fact_by_metric.get("news_tone")
        pref_fact = fact_by_metric.get("investment_preferences") or run.facts[0]
        history_fact = fact_by_metric.get("five_day_close_range") or run.facts[0]

        claims = [
            CandidateClaim(
                text=(
                    f"当前可追踪证据足以把 {entity_symbol} 留在研究流程中，"
                    "但不足以生成任何交易指令。"
                ),
                claim_type="supporting_factor",
                fact_ids=[price_fact.id],
            ),
            CandidateClaim(
                text=(
                    f"关于 {entity_name} 的问题目前只匹配到用户的价值投资研究偏好；"
                    "业务质量、利润率、估值和管理层证据仍需要进一步确认。"
                ),
                claim_type="fit_assessment",
                fact_ids=[pref_fact.id],
            ),
            CandidateClaim(
                text="短期价格波动本身不足以支持投资决策。",
                claim_type="unknown",
                fact_ids=[history_fact.id],
            ),
        ]
        if news_fact is not None:
            claims.insert(
                1,
                CandidateClaim(
                    text=(
                        "近期新闻证据偏混合，回答应保留不确定性，"
                        "而不是强行给出看多或看空结论。"
                    ),
                    claim_type="risk_factor",
                    fact_ids=[news_fact.id],
                ),
            )

        data_quality_facts = _data_quality_facts(run)
        for fact in data_quality_facts:
            claims.append(
                CandidateClaim(
                    text=_data_quality_claim_text(fact.metric or "data_quality", fact.text),
                    claim_type=_data_quality_claim_type(fact.metric),
                    fact_ids=[fact.id],
                )
            )

        human_confirmation_points = [
            f"你关注 {entity_symbol} 的核心投资论点是什么？例如产品周期、行业景气、财务质量、管理层，还是估值修复？",
            "是否有目标估值纪律和最大回撤承受边界？",
            "是否允许补齐实时数据依赖和网络访问，再生成正式研究报告？",
        ]
        if data_quality_facts:
            human_confirmation_points.append("请人工确认 stale、missing 或 conflicting 数据质量限制后，再决定是否生成正式 memo。")

        return SynthesisResult(
            claims=claims,
            human_confirmation_points=human_confirmation_points,
            raw_model_output="mock_llm_synthesis_v1",
        )


class AnthropicJSONResearchSynthesizer:
    """Optional real LLM implementation.

    This path is intentionally not used by default. It requires ANTHROPIC_API_KEY
    and network access. The demo can be validated through MockLLMResearchSynthesizer
    first, then this implementation can be enabled for qualitative testing.
    """

    def __init__(self, model: str = "claude-sonnet-4-6") -> None:
        self.model = model

    def synthesize(self, run: ResearchRunState) -> SynthesisResult:
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise RuntimeError("ANTHROPIC_API_KEY is required for --synthesizer anthropic")

        from anthropic import Anthropic

        base_url = os.environ.get("ANTHROPIC_BASE_URL") or None
        client = Anthropic(api_key=api_key, base_url=base_url)
        prompt = build_synthesis_prompt(run)
        response = client.messages.create(
            model=self.model,
            max_tokens=2000,
            temperature=0,
            messages=[{"role": "user", "content": prompt}],
            output_config={
                "format": {
                    "type": "json_schema",
                    "schema": RESEARCH_SYNTHESIS_SCHEMA,
                }
            },
        )
        raw = "".join(block.text for block in response.content if getattr(block, "type", None) == "text")
        data = _parse_structured_json(raw)
        return synthesis_result_from_data(data, raw)


def synthesis_result_from_data(data: dict[str, Any], raw: str | None = None) -> SynthesisResult:
    claims = [
        CandidateClaim(
            text=item["text"],
            claim_type=item["claim_type"],
            fact_ids=item.get("fact_ids", []),
            is_key=item.get("is_key", True),
        )
        for item in data.get("claims", [])
        if _is_complete_claim_text(item.get("text", ""))
    ]
    return SynthesisResult(
        claims=claims,
        human_confirmation_points=data.get("human_confirmation_points", []),
        raw_model_output=raw,
    )


def _is_complete_claim_text(text: str) -> bool:
    stripped = text.strip()
    if not stripped:
        return False
    dangling_endings = ("添加了", "加入", "在", "对", "的", "和", "与", "及", "了")
    if stripped.endswith(dangling_endings):
        return False
    return stripped.endswith((".", "。", "!", "！", "?", "？", ")", "）"))


def _parse_structured_json(raw: str) -> dict[str, Any]:
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return _parse_json_object(raw)


def build_synthesis_prompt(run: ResearchRunState) -> str:
    context = run.research_context or build_research_context(run)
    payload = research_context_to_prompt_payload(context)
    return (
        "You are an investment research synthesizer, not a trading advisor.\n"
        "Use only context.facts. Do not introduce new factual claims.\n"
        "Every claim text must be a complete standalone sentence and must not end mid-phrase.\n"
        "Every claim must cite fact_ids that appear in context.facts.\n"
        "Missing facts are evidence gaps, not facts to convert into conclusions.\n"
        "Follow every unsupported_claim_constraints item in the context.\n"
        "Return a single JSON object with this schema:\n"
        "{\n"
        '  "claims": [\n'
        '    {"text": "...", "claim_type": "supporting_factor|risk_factor|fit_assessment|unknown|fact_summary", "fact_ids": ["fact_id"], "is_key": true}\n'
        "  ],\n"
        '  "human_confirmation_points": ["..."]\n'
        "}\n\n"
        f"Context: {json.dumps(payload, ensure_ascii=False)}\n"
    )


def bind_claims_to_evidence(run: ResearchRunState, synthesis: SynthesisResult) -> list[Claim]:
    """Convert candidate claims into validated Claim objects.

    A candidate claim is accepted only if every referenced fact exists and each
    referenced fact has at least one source id.
    """
    claims: list[Claim] = []
    for candidate in synthesis.claims:
        evidence: list[Evidence] = []
        for fact_id in candidate.fact_ids:
            fact = run.fact_by_id(fact_id)
            if fact is None or not fact.source_ids:
                continue
            source_id = fact.source_ids[0]
            if run.source_by_id(source_id) is None:
                continue
            evidence.append(Evidence(fact_id=fact.id, source_id=source_id, quote=fact.text))

        claims.append(
            Claim(
                id=new_id("claim"),
                text=candidate.text,
                evidence=evidence,
                is_key=candidate.is_key,
                claim_type=candidate.claim_type,  # type: ignore[arg-type]
            )
        )
    return claims


def _data_quality_facts(run: ResearchRunState) -> list[Any]:
    return [fact for fact in run.facts if _is_data_quality_metric(fact.metric)]


def _is_data_quality_metric(metric: str | None) -> bool:
    if not metric:
        return False
    return metric.startswith(("stale_", "missing_", "failure_", "unknown_", "conflicting_"))


def _data_quality_claim_type(metric: str | None) -> str:
    if metric and metric.startswith(("stale_", "failure_", "conflicting_")):
        return "risk_factor"
    return "unknown"


def _data_quality_claim_text(metric: str, fact_text: str) -> str:
    return f"Data quality limitation ({metric}): {fact_text}"


def make_synthesizer(name: str) -> LLMResearchSynthesizer:
    if name == "mock":
        return MockLLMResearchSynthesizer()
    if name == "anthropic":
        return AnthropicJSONResearchSynthesizer()
    raise ValueError(f"Unknown synthesizer: {name}")


def _parse_json_object(raw: str) -> dict[str, Any]:
    start = raw.find("{")
    end = raw.rfind("}")
    if start < 0 or end < start:
        raise ValueError(f"Model output did not contain a JSON object: {raw[:200]}")
    return json.loads(raw[start : end + 1])
