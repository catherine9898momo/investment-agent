# P1 Production Research Loop Execution Plan

Last updated: 2026-06-03
Environment: VPS only, `/opt/agents/investment-agent`, deploy user, VS Code Remote SSH workflow.

## Operating Rules

- Do not develop or validate on the Mac local workspace; use the VPS project path only.
- Do not read, print, or commit `.env`, API keys, base URLs, or other secrets.
- Keep `.env` untracked.
- Commit and push from the VPS after verified increments.

## Target Loop

User Query -> Live Tool Provider -> Tool Result Normalizer -> Source / Fact -> LLMResearchSynthesizer -> Claim / Evidence Binder -> Guardrail Evaluator -> Research Output -> Trace JSONL -> Case Runner / Regression Report

## Day 1 Status

Completed before this update:

- Fixture provider with mock synthesizer passes.
- Live provider with mock synthesizer passes.
- Trace JSONL writes under `logs/research_traces/`.
- Guardrail evaluator returns PASS for the baseline research demo.
- Prior fixes landed for `feedparser`, memory DB init, corporate actions schema init, and Anthropic base URL support.

Baseline commands:

```bash
.venv/bin/python -m src.agents.research_demo --data-source fixture --synthesizer mock
.venv/bin/python -m src.agents.research_demo --data-source live --synthesizer mock
```

## Day 2 Status: Tool Result Normalizer

Completed on 2026-06-03:

- Added `src/research/normalizers.py` as the explicit boundary from raw tool-shaped dictionaries to `Source` and `Fact` objects.
- Moved quote/history/news/corporate_actions/preferences summary logic out of `src/agents/research_demo.py`.
- Kept `research_demo.py` focused on orchestration: provider fetch, trace, normalization, synthesis, evidence binding, guardrail, output.
- Added independent normalizer functions:
  - `normalize_preferences`
  - `normalize_quote`
  - `normalize_history`
  - `normalize_news`
  - `normalize_corporate_actions`
- Preserved stable success metrics used by the mock and future LLM synthesizers:
  - `investment_preferences`
  - `latest_price`
  - `five_day_close_range`
  - `news_tone`
  - `corporate_actions`
- Added failure/unknown behavior:
  - tool result dictionaries with `error` become `failure_*` facts instead of crashing normalization.
  - empty history/news responses become `unknown_history` / `unknown_news` facts.
  - live provider wraps each tool call independently and returns sanitized `{error: ...ExceptionType}` dictionaries on exceptions.
- Added `src/research/test_normalizers.py` covering metric stability and failure fact generation.

Verified on VPS:

```bash
.venv/bin/python -m pytest
.venv/bin/ruff check src/agents/research_demo.py src/research/normalizers.py src/research/tool_provider.py src/research/test_normalizers.py
.venv/bin/python -m src.agents.research_demo --data-source fixture --synthesizer mock
.venv/bin/python -m src.agents.research_demo --data-source live --synthesizer mock
```

Observed results:

- `pytest`: 10 passed.
- `ruff`: all checks passed for changed files.
- fixture + mock: Guardrail PASS, trace written.
- live + mock: Guardrail PASS, trace written.

## Next: Day 3 Live + Anthropic

Planned next increment:

- Run live provider with `LLMResearchSynthesizer` using Anthropic from the VPS environment.
- Do not print API key or base URL.
- Validate that real model JSON output binds to existing facts only.
- If model emits invalid JSON or invalid `fact_ids`, add minimal repair/rejection handling without weakening evidence constraints.
- Preserve guardrail PASS and trace completeness.

Candidate command shape, with secrets loaded only from the VPS environment:

```bash
.venv/bin/python -m src.agents.research_demo --data-source live --synthesizer anthropic
```


## Day 3 Status: Live + Anthropic

Completed on 2026-06-03:

- Ran `live + anthropic` from the VPS and reproduced a real JSON parsing failure from model text output.
- Root cause: the model emitted human-readable JSON-like text with an unescaped quote inside a string, causing `json.loads` to fail.
- Updated `AnthropicJSONResearchSynthesizer` to use Anthropic structured outputs via `output_config.format=json_schema`.
- Added `RESEARCH_SYNTHESIS_SCHEMA` for claims and human confirmation points.
- Added `synthesis_result_from_data` so structured model output can be converted into `SynthesisResult` without duplicating parsing logic.
- Kept `_parse_json_object` as a compatibility fallback for fenced or wrapped JSON text.
- Increased Anthropic `max_tokens` from `1200` to `2000`.
- Added a minimal incomplete-claim filter so obviously dangling claim text is dropped rather than rendered as a broken research claim.
- Added tests for the strict schema, structured data conversion, and incomplete claim filtering.

Verified on VPS:

```bash
.venv/bin/python -m pytest
.venv/bin/ruff check src/research/synthesizer.py src/research/test_synthesizer.py
.venv/bin/python -m src.agents.research_demo --data-source live --synthesizer anthropic
```

Observed results:

- `pytest`: 13 passed.
- `ruff`: all checks passed for changed files.
- live + anthropic: Guardrail PASS, trace written.
- Latest successful trace observed: `logs/research_traces/rrun_3001cf396ce6.jsonl`.

Remaining Day 3 notes:

- The model is now structurally constrained, but factual depth is still limited by the current five normalized facts.
- The output can still over-interpret news titles; Day 5 freshness/conflict/unknown rules should make headline-only evidence more explicit.
- Do not commit/push until the user reviews the diff.

## Remaining Week Plan

- Day 4: Expand Case Runner to 10 cases.
- Day 5: Add minimal freshness, conflict, and unknown rules.
- Day 6: Add investment memo output shape.
- Day 7: Write P1 summary docs and interview explanation material.
