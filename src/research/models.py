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
