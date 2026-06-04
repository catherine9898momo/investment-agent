# P1 Final Narrative: Production Research Loop

Last updated: 2026-06-04

This document is the learning and interview entry point for P1. It explains what
was built, why each boundary exists, how to talk about it in interviews, and what
P2 should add next.

## One-Sentence Summary

`investment-agent` P1 turns an investment research question into a traceable,
guardrailed memo by converting tool outputs into `Source` and `Fact`, asking the
LLM to produce only evidence-bound `Claim` objects, checking the result with
guardrails, writing a replayable trace, and regression-testing the full loop.

中文口述版：

> P1 的核心不是让模型预测股票涨跌，而是把一个投资研究问题变成可追踪、可审计、可回归测试的 research memo：信息从工具来，先变成 Source 和 Fact，模型只能基于这些事实生成 Claim，每个 Claim 必须绑定 Evidence，最后经过 Guardrail、Trace 和 Case Runner 验证。

## What P1 Built

The current production research loop is:

```text
User Query
 -> Live Tool Provider
 -> Tool Result Normalizer
 -> Source / Fact
 -> LLMResearchSynthesizer
 -> Claim / Evidence Binder
 -> Guardrail Evaluator
 -> Investment Memo Renderer
 -> Trace JSONL
 -> Case Runner / Regression Report
```

P1 delivered these concrete pieces:

- Live and fixture tool providers for quote, history, news, corporate actions,
  and preferences.
- Normalizers that convert tool-shaped dictionaries into stable `Source` and
  `Fact` objects.
- Mock and Anthropic structured synthesizers.
- Evidence binding from `Claim` back to `Fact` and `Source`.
- Guardrails for no direct trading advice, evidence requirements, timestamps,
  risks, unknowns, and human confirmation points.
- Trace JSONL files for replay and audit.
- A case runner with 10 direct-advice boundary cases and 3 frozen data-quality
  cases.
- A deterministic investment memo renderer with canonical sections, evidence
  table, freshness notes, unknowns, and trace reference.

## Why This Is A Production Loop

The important design choice is that P1 treats the LLM as one step in a controlled
research pipeline, not as the whole system.

Raw tool outputs are not pasted directly into a prompt as unstructured context.
They are normalized into typed evidence first. The LLM is then asked to synthesize
claims, but those claims must reference known fact ids. The binder rejects or
limits claims that cannot be tied back to the run state. The guardrail checks the
rendered answer before the user sees it. The trace records each stage so a bad
answer can become a regression case.

In interview language:

> I designed it as a closed production research loop. Each run leaves behind
> enough structured state to debug the answer, explain where claims came from,
> and add a regression case when the system fails.

## Architecture Explanation

### Source

`Source` answers: where did this information come from?

Examples:

- a quote tool result,
- a Google News RSS result,
- a corporate actions lookup,
- a local fixture,
- future RAG documents or external URLs.

Important fields include `id`, `kind`, `name`, `fetched_at`, `tool_name`, `url`,
and `reliability`.

Interview explanation:

> Source is provenance. It lets me separate "the model said this" from "this
> came from a specific tool or document at a specific time."

Failure mode it prevents:

- The model invents a source.
- A stale source is treated as fresh.
- A later reviewer cannot tell where a claim came from.

### Fact

`Fact` answers: what usable evidence did we extract from the source?

Examples:

- latest price,
- five-day close range,
- news tone,
- corporate actions summary,
- stale quote warning,
- missing news warning,
- conflicting signal warning.

Important fields include `id`, `text`, `source_ids`, `observed_at`, `metric`,
`symbol`, and optional structured `value`.

Interview explanation:

> Fact is the normalized evidence unit. It is smaller and more stable than raw
> tool output, and it gives the synthesizer a controlled vocabulary to reason
> over.

Failure mode it prevents:

- Every tool returns a different shape.
- The prompt becomes a pile of raw JSON.
- The model over-reads noisy tool output.

### Claim

`Claim` answers: what conclusion or research statement is the system making?

Claim types include:

- `fact_summary`,
- `supporting_factor`,
- `risk_factor`,
- `unknown`,
- `fit_assessment`.

Interview explanation:

> Claim is where the LLM is allowed to synthesize, but it is not allowed to float
> freely. A claim must be grounded back to known facts.

Failure mode it prevents:

- The LLM writes fluent but unsupported investment conclusions.
- A risk is presented without evidence.
- Unknowns disappear from the final answer.

### Evidence

`Evidence` answers: which fact and source support this claim?

It links:

```text
Claim -> Evidence -> Fact -> Source
```

Interview explanation:

> Evidence is the join table between model language and provenance. It is what
> turns a generated answer into something inspectable.

Failure mode it prevents:

- The answer has citations in prose but no machine-checkable binding.
- Case runner cannot verify evidence integrity.
- Future RAG chunks get pasted into output without becoming auditable evidence.

### Guardrail

`Guardrail` answers: is this output allowed to be shown?

Current checks cover:

- no direct buy/sell/add/trim/hold/short/clear-position advice,
- every key claim has evidence,
- every evidence source has timestamps,
- output includes risk or uncertainty,
- output includes human confirmation points.

Interview explanation:

> Guardrail is the post-generation quality and safety gate. I do not rely on the
> prompt alone to keep financial advice boundaries intact.

Failure mode it prevents:

- Prompt drift turns research into trading advice.
- A model output bypasses evidence rules.
- A missing-data case becomes a confident conclusion.

### Trace

`Trace` answers: what exactly happened during this run?

The JSONL trace records events such as:

- `tool_result`,
- `fact_added`,
- `synthesis_result`,
- `claim_added`,
- `memo_rendered`,
- `guardrail_result`.

Interview explanation:

> Trace makes the agent debuggable. If a live run fails, I can inspect the exact
> tool outputs, normalized facts, claims, guardrail result, and memo-render event,
> then turn that failure into a regression case.

Failure mode it prevents:

- "It failed once, but we cannot reproduce why."
- Evals only check the final text, not the pipeline.
- Production incidents do not become engineering improvements.

## Memo Output Shape

The Day 6 renderer is deterministic. It does not let raw LLM prose bypass the
evidence model. It renders the existing `Source`, `Fact`, `Claim`, and `Evidence`
objects into canonical memo sections:

- Boundary Statement
- Executive Summary
- Evidence Table
- What We Know
- Risks
- Unknowns / Conflicts
- Freshness Notes
- User Preference Fit
- Human Confirmation Points
- Trace Reference

The key point:

> The memo is not another LLM generation step. It is a deterministic projection
> of the audited research state.

## Evaluation Story

Current verification is not "did TSLA go up later?" It is engineering
correctness for a research system.

The case runner checks:

- boundary behavior for buy, sell, add, trim, hold, short, and liquidation
  language,
- expected memo sections,
- guardrail pass/fail,
- trace file existence,
- `memo_rendered` trace event,
- expected data-quality metrics and output terms for frozen stale/missing/conflict
  cases.

Current Day 6 verification snapshot:

```text
ruff: all checks passed
pytest: 18 passed
fixture + mock all suite: 13/13 PASS
live + mock boundary suite: 10/10 PASS
```

## Three-Minute Pitch

> I built `investment-agent` as a production-shaped research agent for finance.
> The goal is not to give trading advice. The goal is to show how a vertical
> agent can turn messy market tools into traceable, guardrailed research output.
>
> The core loop is: user query, live tool provider, normalizer, Source and Fact,
> structured LLM synthesis, Claim and Evidence binding, guardrail evaluation,
> deterministic memo rendering, trace logging, and regression testing.
>
> The main engineering decision is that the LLM is not the source of truth. Tool
> outputs first become typed facts with provenance and timestamps. The LLM can
> synthesize claims, but every important claim must bind back to a fact and a
> source. If it cannot be grounded, it should become an unknown or be blocked by
> the guardrail.
>
> I also built the eval loop around real failure modes. There are 10 boundary
> cases for direct advice like buy, sell, add, trim, hold, short, and liquidation,
> plus 3 frozen data-quality cases for stale quote data, missing news, and
> conflicting signals. The case runner checks not just final text, but guardrail
> results, expected memo sections, trace existence, and the memo-rendered trace
> event.
>
> The Day 6 output is an investment memo with canonical sections: boundary
> statement, executive summary, evidence table, risks, unknowns, freshness notes,
> human confirmation points, and trace reference. The renderer is deterministic,
> so the final memo is a projection of audited research state rather than another
> free-form generation step.
>
> What this demonstrates is a production research loop: evidence in, constrained
> synthesis, policy gate, trace out, regression back into the system.

## Resume Bullets

Short version:

- Built a production-shaped investment research agent that converts live market
  tool outputs into traceable `Source` / `Fact` / `Claim` / `Evidence` objects,
  then renders guardrailed investment memos with deterministic evidence tables.
- Implemented structured LLM synthesis, evidence binding, guardrail checks, JSONL
  tracing, and a regression case runner covering 10 direct-advice boundary cases
  plus 3 frozen data-quality cases.
- Added stale-data, missing-data, and conflicting-signal handling so the agent
  surfaces uncertainty instead of converting incomplete evidence into confident
  investment conclusions.

Longer version:

- Designed and implemented `investment-agent`, a finance-domain research agent
  whose core loop normalizes live quote/history/news/corporate-action outputs
  into typed evidence, constrains LLM claims to known facts, applies financial
  advice guardrails, and writes replayable JSONL traces.
- Built a regression harness for production research behavior, including
  10 Chinese direct-advice boundary cases and 3 frozen data-quality cases; Day 6
  validation passed `ruff`, `pytest` with 18 tests, fixture all-suite 13/13, and
  live boundary suite 10/10.
- Shipped a deterministic investment memo renderer with canonical sections,
  evidence table, freshness notes, unknowns/conflicts, human confirmation points,
  and a `memo_rendered` trace event for auditability.

## P2 RAG Plan

P2 should deepen research quality without breaking the P1 provenance contract.

Principle:

> Retrieval output must become `Source` and `Fact` before it influences a claim.
> RAG should extend the evidence model, not bypass it.

Planned components:

1. Document ingestion
   - filings,
   - annual reports,
   - earnings transcripts,
   - research notes,
   - company profiles.

2. Document metadata
   - company / ticker,
   - document type,
   - period,
   - publication date,
   - source URL,
   - provider reliability,
   - ingestion timestamp.

3. Chunking and embeddings
   - stable chunk ids,
   - text spans,
   - embeddings,
   - optional BM25 / hybrid search,
   - future pgvector storage.

4. Retrieval-to-evidence bridge
   - retrieved chunk becomes `Source`,
   - extracted statement becomes `Fact`,
   - fact links to chunk/source metadata,
   - claim can cite that fact through `Evidence`.

5. Memo-grade citation surface
   - show document title,
   - publication date,
   - source URL,
   - quoted span or summarized fact,
   - freshness and reliability notes.

6. Eval additions
   - citation integrity cases,
   - stale filing cases,
   - conflicting provider cases,
   - retrieval miss cases,
   - invalid fact-id cases from LLM synthesis.

## Suggested Learning Flow

Use this document in three passes:

1. First pass: understand the loop and the six nouns: Source, Fact, Claim,
   Evidence, Guardrail, Trace.
2. Second pass: ask questions about any boundary that feels unclear.
3. Third pass: practice explaining the project from memory, then answer mock
   interview questions.

When you are ready, I can quiz you in this order:

1. explain the loop in 60 seconds,
2. define each core noun,
3. explain why the renderer is deterministic,
4. explain what the case runner proves and does not prove,
5. explain how P2 RAG should connect to Source/Fact.
