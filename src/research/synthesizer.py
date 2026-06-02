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
from dotenv import load_dotenv

from src.research.models import Claim, Evidence, Fact, ResearchRunState, new_id

load_dotenv()

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
        price_fact = fact_by_metric.get("latest_price") or run.facts[0]
        news_fact = fact_by_metric.get("news_tone") or run.facts[0]
        pref_fact = fact_by_metric.get("investment_preferences") or run.facts[0]
        history_fact = fact_by_metric.get("five_day_close_range") or run.facts[0]

        return SynthesisResult(
            claims=[
                CandidateClaim(
                    text=(
                        "Current sourced evidence is enough to keep TSLA in a research workflow, "
                        "but it is not enough to produce a trading instruction."
                    ),
                    claim_type="supporting_factor",
                    fact_ids=[price_fact.id],
                ),
                CandidateClaim(
                    text=(
                        "The recent news evidence is mixed, so the answer should preserve "
                        "uncertainty instead of forcing a bullish or bearish conclusion."
                    ),
                    claim_type="risk_factor",
                    fact_ids=[news_fact.id],
                ),
                CandidateClaim(
                    text=(
                        "The question matches the user's value-investing preference only at "
                        "the research stage; business quality, margins, valuation, and management "
                        "evidence still need confirmation."
                    ),
                    claim_type="fit_assessment",
                    fact_ids=[pref_fact.id],
                ),
                CandidateClaim(
                    text="Short-term price movement alone is insufficient evidence for an investment decision.",
                    claim_type="unknown",
                    fact_ids=[history_fact.id],
                ),
            ],
            human_confirmation_points=[
                "你关注 TSLA 的核心 thesis 是自动驾驶、能源、制造效率，还是纯 EV 销量？",
                "是否有目标估值纪律和最大回撤承受边界？",
                "是否允许把 local fixture 升级为 live MCP tool run 后再生成正式 memo？",
            ],
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
            max_tokens=1200,
            temperature=0,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = "".join(block.text for block in response.content if getattr(block, "type", None) == "text")
        data = _parse_json_object(raw)
        claims = [
            CandidateClaim(
                text=item["text"],
                claim_type=item["claim_type"],
                fact_ids=item.get("fact_ids", []),
                is_key=item.get("is_key", True),
            )
            for item in data.get("claims", [])
        ]
        return SynthesisResult(
            claims=claims,
            human_confirmation_points=data.get("human_confirmation_points", []),
            raw_model_output=raw,
        )


def build_synthesis_prompt(run: ResearchRunState) -> str:
    fact_rows = [
        {
            "fact_id": fact.id,
            "text": fact.text,
            "metric": fact.metric,
            "source_ids": fact.source_ids,
            "observed_at": fact.observed_at,
        }
        for fact in run.facts
    ]
    return (
        "You are an investment research synthesizer, not a trading advisor.\n"
        "Use only the facts below. Do not introduce new factual claims.\n"
        "Do not recommend buying, selling, adding, trimming, holding, shorting, or clearing a position.\n"
        "Return a single JSON object with this schema:\n"
        "{\n"
        '  "claims": [\n'
        '    {"text": "...", "claim_type": "supporting_factor|risk_factor|fit_assessment|unknown|fact_summary", "fact_ids": ["fact_id"], "is_key": true}\n'
        "  ],\n"
        '  "human_confirmation_points": ["..."]\n'
        "}\n\n"
        f"User query: {run.user_query}\n"
        f"Facts: {json.dumps(fact_rows, ensure_ascii=False)}\n"
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
