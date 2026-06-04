# P1 Final Narrative：Production Research Loop 中文版

最后更新：2026-06-04

这份文档是 P1 的中文学习和面试入口。它的用途不是替代代码文档，而是帮你把项目讲清楚：P1 做成了什么、为什么要这样设计、每个边界解决什么失败模式，以及下一阶段 P2 RAG 应该怎么接上来。

以后类似这种给人读、给自己复盘、用于面试或简历的总结性文档，默认都应该有英文版和中文版。

## 一句话总结

`investment-agent` P1 把一个投资研究问题变成可追踪、可审计、可回归测试的 research memo：工具输出先变成 `Source` 和 `Fact`，LLM 只能生成绑定证据的 `Claim`，每个 `Claim` 必须通过 `Evidence` 追溯回事实和来源，最后经过 `Guardrail`、`Trace` 和 `Case Runner` 验证。

更口语一点：

> P1 的核心不是让模型预测股票涨跌，而是做一条 production research loop。信息从工具来，先结构化成证据；模型只负责在证据范围内做 synthesis；输出前有 guardrail；每次运行都有 trace；失败后能沉淀成 regression case。

## P1 做成了什么

当前主链路是：

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

P1 已经落地的具体能力：

- fixture 和 live 两种工具数据路径。
- quote、history、news、corporate actions、preferences 的工具结果归一化。
- `Source` / `Fact` / `Claim` / `Evidence` 数据模型。
- Mock synthesizer 和 Anthropic structured-output synthesizer。
- Claim 到 Fact / Source 的 evidence binding。
- Guardrail：不直接给买卖建议、关键 claim 要有证据、source 要有 timestamp、输出要包含风险/未知项/人工确认点。
- JSONL trace：记录每次 run 的关键事件。
- Case runner：10 条 direct-advice boundary cases + 3 条 frozen data-quality cases。
- Deterministic investment memo renderer：固定 memo 章节、证据表、freshness notes、unknowns/conflicts、trace reference。

## 为什么这是 Production Loop

P1 最重要的设计是：LLM 不是整套系统本身，它只是受控 pipeline 中的一步。

工具返回的原始结果不会被直接糊进 prompt。它们先被 normalizer 变成结构化的 `Source` 和 `Fact`。LLM 负责生成 `Claim`，但每个关键 claim 必须绑定到已知 fact id。然后 guardrail 检查输出边界，trace 记录运行过程，case runner 把重要失败模式变成回归测试。

面试时可以这样说：

> 我把它设计成闭环的 production research system。每次运行都会留下结构化状态：信息来源、提取出的事实、模型生成的 claim、claim 绑定的 evidence、guardrail 结果和 trace。这样一个坏输出不是一句“模型答错了”，而是可以定位到具体 pipeline 环节，并转成 regression case。

## 架构解释

### Source

`Source` 回答的问题是：信息从哪里来？

例子：

- quote tool result，
- Google News RSS，
- corporate actions lookup，
- local fixture，
- 未来的 filing document 或 external URL。

重要字段包括：

- `id`
- `kind`
- `name`
- `fetched_at`
- `tool_name`
- `url`
- `reliability`

面试解释：

> Source 是 provenance，也就是来源和出处。它把“模型说了什么”和“信息来自哪个工具/文档/时间点”分开。

它解决的失败模式：

- 模型编造来源。
- 过期来源被当成新鲜数据。
- 后续 review 时无法判断 claim 从哪里来。

### Fact

`Fact` 回答的问题是：从 source 里抽出了什么可用证据？

例子：

- latest price，
- five-day close range，
- news tone，
- corporate actions summary，
- stale quote warning，
- missing news warning，
- conflicting signal warning。

重要字段包括：

- `id`
- `text`
- `source_ids`
- `observed_at`
- `metric`
- `symbol`
- optional `value`

面试解释：

> Fact 是归一化后的证据单元。它比原始工具 JSON 更小、更稳定，也让 synthesizer 有一组受控的事实可以推理。

它解决的失败模式：

- 每个工具输出 shape 都不同，后面处理复杂。
- prompt 里堆满 raw JSON。
- 模型过度解读噪声数据。

### Claim

`Claim` 回答的问题是：系统基于事实提出了什么研究判断？

当前 claim type 包括：

- `fact_summary`
- `supporting_factor`
- `risk_factor`
- `unknown`
- `fit_assessment`

面试解释：

> Claim 是 LLM 可以发挥 synthesis 能力的地方，但它不能自由漂浮。一个 claim 必须能绑定回已知 facts。

它解决的失败模式：

- LLM 写出流畅但没有证据的投资结论。
- 风险提示没有依据。
- 缺失信息和未知项从最终答案里消失。

### Evidence

`Evidence` 回答的问题是：哪个 fact 和 source 支撑了这个 claim？

关系是：

```text
Claim -> Evidence -> Fact -> Source
```

面试解释：

> Evidence 是模型语言和可追踪来源之间的连接层。它把自然语言答案变成可检查、可回放、可评估的结构。

它解决的失败模式：

- 答案里看起来有引用，但没有机器可检查的绑定关系。
- case runner 无法验证 evidence integrity。
- 未来 RAG 检索结果绕过证据模型，直接进入输出。

### Guardrail

`Guardrail` 回答的问题是：这个输出能不能展示给用户？

当前检查包括：

- 不能直接建议买入、卖出、加仓、减仓、持有、做空或清仓。
- 每个关键 claim 必须有 evidence。
- 每个 evidence source 必须有 timestamp。
- 输出必须包含风险或不确定性。
- 输出必须包含 human confirmation points。

面试解释：

> Guardrail 是 post-generation 的安全和质量闸门。我不只靠 prompt 让模型自觉遵守金融建议边界，而是在输出前再做规则检查。

它解决的失败模式：

- prompt drift 让 research output 变成 trading advice。
- 没证据的 claim 被展示给用户。
- missing data / stale data 被模型包装成确定结论。

### Trace

`Trace` 回答的问题是：这次 run 到底发生了什么？

JSONL trace 会记录：

- `tool_result`
- `fact_added`
- `synthesis_result`
- `claim_added`
- `memo_rendered`
- `guardrail_result`

面试解释：

> Trace 让 agent 可调试、可审计、可回归。如果 live run 出错，我可以检查工具输出、归一化 facts、模型 claims、memo render 和 guardrail 结果，然后把失败沉淀成 regression case。

它解决的失败模式：

- “线上错了一次，但不知道为什么。”
- eval 只看最终文本，不看 pipeline。
- production incident 没法反哺工程系统。

## Memo Output Shape

Day 6 加的 memo renderer 是 deterministic renderer，不是再让 LLM 自由生成一遍。

它把已经生成并审计过的 `Source`、`Fact`、`Claim`、`Evidence` 渲染成固定章节：

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

关键点：

> Memo 是 audited research state 的 deterministic projection，不是新的自由生成步骤。

这点很重要，因为如果最后的 memo 又让 LLM 任意重写，就可能绕过前面的 evidence binding 和 guardrail 设计。

## Eval Story

当前 eval 不验证“TSLA 后来会不会涨”。它验证的是 research agent 的工程正确性。

Case runner 检查：

- buy / sell / add / trim / hold / short / liquidation 等 direct-advice 边界。
- 输出是否包含预期 memo sections。
- guardrail 是否通过。
- trace 文件是否存在。
- trace 里是否有 `memo_rendered` event。
- frozen data-quality cases 是否出现预期 metrics 和 output terms。

Day 6 验证快照：

```text
ruff: all checks passed
pytest: 18 passed
fixture + mock all suite: 13/13 PASS
live + mock boundary suite: 10/10 PASS
```

面试时可以强调：

> 我评估的不是投资收益预测，而是一个 research system 是否遵守证据、边界、trace 和 regression 的工程契约。

## 3 分钟 Pitch

> 我做的 `investment-agent` 是一个 finance domain 的 production-shaped research agent。它的目标不是预测股票涨跌，也不是给用户直接买卖建议，而是验证一个垂直 agent 怎么把混乱的市场工具输出变成可追踪、带 guardrail、可回归测试的 research memo。
>
> 核心链路是：User Query -> Live Tool Provider -> Tool Result Normalizer -> Source / Fact -> LLMResearchSynthesizer -> Claim / Evidence Binder -> Guardrail Evaluator -> Investment Memo Renderer -> Trace JSONL -> Case Runner。
>
> 关键工程决策是：LLM 不是 source of truth。工具输出必须先变成带来源和时间戳的 typed facts。LLM 可以做 synthesis，但每个重要 claim 必须通过 evidence 绑定回 fact 和 source。如果不能被证据支撑，它应该变成 unknown，或者被 guardrail block。
>
> 我还围绕真实失败模式搭了 eval loop。现在有 10 条 direct-advice boundary cases，覆盖买、卖、加仓、减仓、持有、做空、清仓等中文表达；还有 3 条 frozen data-quality cases，覆盖 stale quote、missing news 和 conflicting signals。Case runner 不只检查最终文本，还检查 guardrail、memo sections、trace 是否存在，以及 trace 里有没有 memo_rendered event。
>
> Day 6 输出层加了 deterministic investment memo renderer。它固定输出 Boundary Statement、Executive Summary、Evidence Table、Risks、Unknowns、Freshness Notes、Human Confirmation Points 和 Trace Reference。这个 memo 不是新的自由生成，而是把已审计的 research state 投影成人能读的格式。
>
> 所以这个项目当前最核心的价值是：evidence in，constrained synthesis，policy gate，trace out，regression back into the system。

## 简历 Bullet

短版：

- Built a production-shaped investment research agent that converts live market
  tool outputs into traceable `Source` / `Fact` / `Claim` / `Evidence` objects,
  then renders guardrailed investment memos with deterministic evidence tables.
- Implemented structured LLM synthesis, evidence binding, guardrail checks, JSONL
  tracing, and a regression case runner covering 10 direct-advice boundary cases
  plus 3 frozen data-quality cases.
- Added stale-data, missing-data, and conflicting-signal handling so the agent
  surfaces uncertainty instead of converting incomplete evidence into confident
  investment conclusions.

中文解释版：

- 设计并实现一个 production-shaped investment research agent，把 live market tools 输出归一化为可追踪的 `Source` / `Fact` / `Claim` / `Evidence`，再渲染成带 guardrail 的 investment memo。
- 实现 structured LLM synthesis、evidence binding、guardrail checks、JSONL trace 和 case runner，覆盖 10 条 direct-advice boundary cases 与 3 条 frozen data-quality cases。
- 增加 stale data、missing data、conflicting signals 处理，让系统暴露不确定性，而不是把不完整证据包装成确定投资结论。

长版：

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

P2 的核心原则：

> Retrieval output 必须先变成 `Source` 和 `Fact`，再影响 `Claim`。RAG 应该扩展证据模型，而不是绕过证据模型。

计划组件：

1. Document ingestion
   - filings
   - annual reports
   - earnings transcripts
   - research notes
   - company profiles

2. Document metadata
   - company / ticker
   - document type
   - period
   - publication date
   - source URL
   - provider reliability
   - ingestion timestamp

3. Chunking and embeddings
   - stable chunk ids
   - text spans
   - embeddings
   - optional BM25 / hybrid search
   - future pgvector storage

4. Retrieval-to-evidence bridge
   - retrieved chunk becomes `Source`
   - extracted statement becomes `Fact`
   - fact links to chunk/source metadata
   - claim cites that fact through `Evidence`

5. Memo-grade citation surface
   - document title
   - publication date
   - source URL
   - quoted span or summarized fact
   - freshness and reliability notes

6. Eval additions
   - citation integrity cases
   - stale filing cases
   - conflicting provider cases
   - retrieval miss cases
   - invalid fact-id cases from LLM synthesis

## 建议学习顺序

第一遍：先理解整条 loop，以及六个核心名词：

- Source
- Fact
- Claim
- Evidence
- Guardrail
- Trace

第二遍：挑你不清楚的边界问我，比如：

- 为什么 Fact 和 Claim 要分开？
- 为什么 memo renderer 要 deterministic？
- Guardrail 和 Case Runner 有什么区别？
- Trace 到底在生产系统里有什么价值？
- P2 RAG 为什么不能直接把 retrieved chunks 塞进 prompt？

第三遍：等你觉得理解了，我来反问你，顺序可以是：

1. 60 秒讲完整条 production research loop。
2. 分别解释 Source / Fact / Claim / Evidence。
3. 解释 Guardrail 解决什么问题。
4. 解释 Trace 和 Case Runner 的关系。
5. 解释 P2 RAG 怎么接到 Source / Fact。

目标不是背稿，而是让你能用自己的话讲清楚每个设计为什么存在。
