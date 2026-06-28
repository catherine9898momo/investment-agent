# Report Narrative Quality 技术方案

## 1. 背景

当前系统已经完成 `Bounded Evidence Repair Loop` 的第一版：当用户通过 CLI 输入研究问题时，系统可以生成 `run_0`，审计质量问题，按白名单补证据，合并到 `enhanced_bundle`，再重建 `run_1`，并输出 trace log。

从最近一次 live 运行看，系统的优势已经很清楚：

- 有结构化 facts、verified facts、missing facts。
- 有归因等级，例如“候选因素 / 较可能因素”。
- 有 sector / peer evidence。
- 有 guardrail。
- 有 trace path，可以回放数据链路。

但和直接请求 GPT 的回答相比，当前报告还有明显产品体验差距：

- 开头没有快速点出“哪一天、跌了多少、最核心发生了什么”。
- “研究结论”和“原因排序”可能不一致，例如结论说主因是板块/同行，原因排序第一条却是个股情绪。
- 新闻只以标题列表出现，没有被整理成可解释的事件类型。
- loop 没有执行补证据时，仍展示“本轮质量改进：已执行 0 次”，读起来像系统日志。
- 报告结构偏审计表，用户读起来不像一份投资解释。

本方案目标是：在不破坏现有证据闭环、trace、guardrail 的基础上，让报告正文更像“可读的研究解释”，同时每一步改动都能通过单测验证。

## 2. 方案目标

### 2.1 产品目标

- 让用户第一屏看到清晰结论：发生了什么、最可能原因、哪些证据支持、哪些还不能确定。
- 让原因排序与 attribution evaluator 输出一致，不出现“结论 A、排序 B”的错位。
- 把新闻标题归类为结构化事件，例如财报/指引、行业同行、AI 交易、宏观风险、分析师动作。
- 把 loop summary 从工程日志改成用户能理解的质量状态说明。
- 保留 trace、missing facts、guardrail 和归因等级，不为了可读性牺牲可审计性。

### 2.2 工程目标

- 所有新增能力先写 fixture 单测，再做实现。
- 不引入开放式 LLM 自由事实生成。
- 不让 LLM 自由决定工具调用或事实类型。
- 报告正文仍只使用 `run.final_output` 所依赖的结构化 facts / verified facts / attribution causes。
- 新增模块尽量是确定性纯函数，方便 regression。

## 3. 非目标

- 不新增外部数据源。
- 不做完整多轮对话。
- 不做开放式 autonomous research loop。
- 不替换 `Bounded Evidence Repair Loop` 的 `enhanced_bundle -> run_1` 架构。
- 不提供买入、卖出、加仓、减仓等直接交易建议。
- 不把 trace viewer 质量面板纳入本阶段实现；本阶段只保证报告和 trace payload 为后续面板提供结构化信号。

## 4. 总体架构

现有 loop 架构保持不变：

```text
base_bundle
  -> build_research_run_from_bundle(base_bundle)
  -> run_0
  -> quality_audit
  -> evidence_task_plan
  -> evidence_task_results
  -> enhanced_bundle
  -> build_research_run_from_bundle(enhanced_bundle)
  -> run_1
  -> final_report
```

这段流程的含义：

- `base_bundle`：provider 第一次拉到的原始工具结果集合。
- `run_0`：初稿研究状态，包含 facts、verified facts、missing facts、claims、attribution causes 和初版 memo。
- `quality_audit`：审计 `run_0` 的质量问题，不拉数据、不改报告。
- `evidence_task_plan`：把质量问题映射为白名单补证据任务。
- `evidence_task_results`：任务执行结果，成功或失败都结构化记录。
- `enhanced_bundle`：把成功任务结果合并回 `ToolResultBundle` 后的新数据包。
- `run_1`：必须由 `build_research_run_from_bundle(enhanced_bundle)` 重新生成。
- `final_report`：用户最终看到的报告正文，来自 `run_1`，再追加质量摘要。

本方案新增的是 `run_1` 内部 memo 渲染前的叙事结构层：

```text
run_1
  -> classify_news_events
  -> build_report_narrative
  -> align_cause_ranking_with_attribution
  -> render_investment_memo_v3
  -> append_quality_summary
```

这段流程的含义：

- `classify_news_events`：从已核验新闻 fact 中提取事件类别，不新增事实。
- `build_report_narrative`：把价格、新闻、板块/同行、缺口整理成报告叙事模型。
- `align_cause_ranking_with_attribution`：确保原因排序第一项与 attribution primary cause 一致。
- `render_investment_memo_v3`：用更适合用户阅读的结构输出报告。
- `append_quality_summary`：根据 loop 是否真的补证据，展示“质量审计结果”或“本轮质量改进”。

## 5. 新增/修改文件

```text
src/research/news_event_classifier.py
src/research/report_narrative.py
src/research/memo_renderer.py
src/research/loop_engine.py
src/research/test_news_event_classifier.py
src/research/test_report_narrative.py
src/research/test_memo_renderer_narrative.py
src/research/test_loop_summary_view.py
```

文件说明：

- `news_event_classifier.py`：确定性新闻事件分类器。输入 `ResearchRunState` 或新闻 fact，输出 `NewsEvent` 列表。
- `report_narrative.py`：把 run 转成面向渲染的 `ReportNarrative`，避免 renderer 里堆太多推理逻辑。
- `memo_renderer.py`：保留现有渲染入口，内部切到 narrative-driven 渲染。
- `loop_engine.py`：只修改 loop summary 文案分支，不改变 loop 控制流。
- `test_news_event_classifier.py`：验证新闻标题到事件类型的稳定映射。
- `test_report_narrative.py`：验证 primary cause、key move、remaining gaps 的组合逻辑。
- `test_memo_renderer_narrative.py`：验证最终报告更可读，且不泄漏 debug id。
- `test_loop_summary_view.py`：验证 0 次补证据时不再显示“本轮质量改进”。

## 6. 数据结构设计

### 6.1 NewsEvent

```python
@dataclass(frozen=True)
class NewsEvent:
    event_type: Literal[
        "earnings_or_guidance",
        "sector_peer",
        "ai_trade",
        "macro_risk",
        "analyst_action",
        "company_specific",
        "corporate_action",
        "valuation_or_positioning",
        "unknown",
    ]
    label: str
    summary: str
    supporting_fact_ids: list[str]
    source_titles: list[str]
    confidence: Literal["high", "medium", "low"] = "medium"
    is_primary: bool = False
```

字段说明：

- `event_type`：稳定事件类别，用于测试、trace、报告排序和后续 UI 筛选。
- `label`：用户可读短标签，例如“财报/指引超预期但预期已满”。
- `summary`：一句话解释该事件为什么可能影响股价。
- `supporting_fact_ids`：支撑该事件的 fact id，只放 trace 和测试，不直接暴露给用户正文。
- `source_titles`：触发该事件的新闻标题，报告里可以展示前 1-3 条。
- `confidence`：分类置信度，不等同于归因置信度。
- `is_primary`：是否被 narrative 选为主事件；同一报告最多一个主事件。

### 6.2 ReportNarrative

```python
@dataclass(frozen=True)
class ReportNarrative:
    title: str
    one_line_conclusion: str
    key_move: str | None
    primary_cause: NarrativeCause
    secondary_causes: list[NarrativeCause]
    fundamental_readthrough: str | None
    evidence_events: list[NewsEvent]
    remaining_gaps: list[str]
    quality_note: str
```

字段说明：

- `title`：报告标题，例如 `Micron（MU）研究简报`。
- `one_line_conclusion`：用户最先读到的一句话结论。
- `key_move`：本轮要解释的价格动作，例如“6 月 23 日单日下跌 13.2%”；若数据不足则写 `None`。
- `primary_cause`：原因排序第一项，必须和 attribution primary cause 对齐。
- `secondary_causes`：次要原因，只能来自已核验 facts、新闻事件或明确标注的候选解释。
- `fundamental_readthrough`：基本面解读，例如“财报强但市场担心预期过满”；证据不足时必须写成不确定表达。
- `evidence_events`：新闻事件列表，按重要性排序。
- `remaining_gaps`：还缺哪些证据，用中文表达。
- `quality_note`：本报告质量状态摘要，例如“已通过 normal 质量审计”。

### 6.3 NarrativeCause

```python
@dataclass(frozen=True)
class NarrativeCause:
    label: str
    explanation: str
    attribution_level: str
    confidence: str
    supporting_event_types: list[str]
    supporting_fact_types: list[str]
```

字段说明：

- `label`：原因标题，例如“板块/同行同步下跌”。
- `explanation`：面向用户的一句话原因解释。
- `attribution_level`：沿用 evaluator 的等级，例如 `likely_factor`。
- `confidence`：沿用 evaluator 或 narrative 聚合后的置信度。
- `supporting_event_types`：支撑该原因的新闻事件类别。
- `supporting_fact_types`：支撑该原因的事实类型，例如 `price_move`、`peer_moves`。

### 6.4 QualitySummaryView

```python
@dataclass(frozen=True)
class QualitySummaryView:
    heading: Literal["质量审计结果", "本轮质量改进"]
    status_line: str
    added_evidence: list[str]
    remaining_gaps: list[str]
    attribution_level_change: str
    stop_reason: str
    trace_path: str | None
```

字段说明：

- `heading`：用户看到的二级标题。未补证据时用“质量审计结果”，补过证据时用“本轮质量改进”。
- `status_line`：一句话说明 loop 状态，例如“normal 标准已通过，未触发补证据”。
- `added_evidence`：新增证据类型。没有新增时显示“无”。
- `remaining_gaps`：仍缺证据类型，用中文展示。
- `attribution_level_change`：归因等级变化，例如 `candidate_factor -> likely_factor`。
- `stop_reason`：稳定停止原因，保留机器可读值，便于 trace 对齐。
- `trace_path`：trace jsonl 文件路径。

## 7. 新闻事件分类规则

V1 使用确定性 keyword/rule classifier，不调用 LLM。

```text
earnings_or_guidance:
  earnings, revenue, EPS, guidance, outlook, forecast, results, profit, margin,
  财报, 指引, 营收, EPS, 利润率, 业绩

sector_peer:
  peers, rivals, SK Hynix, Samsung, semiconductor, chip, memory, KOSPI,
  同行, 竞争对手, 半导体, 芯片, 存储, 板块

ai_trade:
  AI, Nvidia, data center, HBM, accelerator,
  人工智能, 英伟达, 数据中心, HBM

macro_risk:
  Nasdaq, rates, yield, Fed, inflation, risk-off,
  纳指, 利率, 美联储, 通胀, 风险偏好

analyst_action:
  upgrade, downgrade, price target, rating, analyst,
  上调, 下调, 目标价, 评级, 分析师

corporate_action:
  split, dividend, buyback, merger, offering,
  拆股, 分红, 回购, 并购, 增发
```

规则说明：

- 一条新闻可以命中多个类别，但 V1 只取优先级最高的一个主类别。
- 优先级建议：`earnings_or_guidance > analyst_action > sector_peer > ai_trade > macro_risk > corporate_action > company_specific > unknown`。
- 分类只解释新闻标题，不创造新 fact。
- 如果所有新闻都只能归为 `unknown`，报告必须保守，不写成确定原因。

## 8. 报告结构调整

新报告建议结构：

```text
# Micron（MU）研究简报

## 一句话结论
## 发生了什么
## 最可能的原因
## 基本面是否变坏
## 归因证据矩阵
## 还不能确定的部分
## 数据来源与时效
## 质量审计结果 / 本轮质量改进
```

每个 section 含义：

- `一句话结论`：第一屏给用户答案，不超过 3 条 bullet。
- `发生了什么`：价格动作、日期窗口、新闻事件摘要。
- `最可能的原因`：原因排序，第一项必须对齐 attribution primary cause。
- `基本面是否变坏`：把财报/指引类新闻和股价反应分开解释，避免“跌了=基本面差”的误导。
- `归因证据矩阵`：保留现有归因等级、置信度、缺口、下一步核验。
- `还不能确定的部分`：展示 missing facts 和低置信度点。
- `数据来源与时效`：保留 sources 和 fetched_at。
- `质量审计结果 / 本轮质量改进`：展示 loop 状态。

## 9. 渲染约束

报告正文必须满足：

```text
不得出现 fact_ / source_ / claim_ debug id。
不得输出买入、卖出、加仓、减仓等直接交易动作。
不得把 candidate_factor 写成 confirmed_cause。
不得把 missing facts 写成已核验证据。
不得让原因排序第一项和 attribution primary cause 不一致。
```

这些约束的含义：

- `debug id`：工程可追踪信息只进 trace，不进用户正文。
- `直接交易动作`：研究报告只给证据判断，不给交易指令。
- `candidate_factor`：候选因素只能写成“可能 / 候选 / 需要继续核验”。
- `missing facts`：缺失事实只能写进“不确定性 / 还需确认”。
- `原因排序一致`：如果 attribution evaluator 判断主因是“板块/同行同步波动”，原因排序第一项也必须是它。

## 10. 分阶段实现与单测

### Phase 1：Loop Summary 文案分支

目标：修复“已执行 0 次补证据”读起来像异常的问题。

测试文件：

```text
src/research/test_loop_summary_view.py
```

单测：

```python
def test_quality_passed_without_iterations_renders_quality_audit_result_heading():
    result = LoopResult(
        initial_run=run,
        final_run=run,
        iterations=[],
        stop_reason="quality_passed",
        quality_delta={
            "added_fact_types": [],
            "remaining_missing_fact_types": ["analyst_actions"],
            "before_attribution_level": "likely_factor",
            "after_attribution_level": "likely_factor",
        },
    )

    output = append_loop_summary("# Report", result)

    assert "## 质量审计结果" in output
    assert "## 本轮质量改进" not in output
    assert "未触发补证据" in output
```

验收：

- `quality_passed + 0 iterations` 显示“质量审计结果”。
- `iterations >= 1` 仍显示“本轮质量改进”。
- 不改变 loop engine 的补证据控制流。

### Phase 2：新闻事件分类器

目标：把新闻标题从“标题列表”变成结构化事件。

测试文件：

```text
src/research/test_news_event_classifier.py
```

单测：

```python
def test_classifies_micron_earnings_and_ai_trade_news_events():
    facts = [
        Fact(
            id="fact_news",
            text="News items mention Micron earnings, AI memory demand, Nvidia, and guidance.",
            metric="news_tone",
            source_ids=["src_news"],
            observed_at="2026-06-28",
            value={
                "titles": [
                    "Micron Earnings Beat Estimates but Outlook Raises Questions",
                    "AI Memory Demand Linked to Nvidia Keeps Investors Focused",
                ]
            },
        )
    ]

    events = classify_news_events(facts)

    assert [event.event_type for event in events] == ["earnings_or_guidance", "ai_trade"]
    assert events[0].supporting_fact_ids == ["fact_news"]
```

验收：

- 财报/指引、同行/板块、AI 交易、宏观、分析师动作至少各有一个 fixture case。
- 分类器是纯函数。
- 分类器不调用 provider，不访问网络，不调用 LLM。

### Phase 3：ReportNarrative 构建

目标：把 run 转成稳定的叙事模型，供 renderer 使用。

测试文件：

```text
src/research/test_report_narrative.py
```

单测：

```python
def test_primary_cause_matches_attribution_primary_cause():
    run = make_run(
        attribution_causes=[
            AttributionCause(
                label="板块/同行同步波动",
                level="likely_factor",
                confidence="medium",
                support_fact_ids=["vf_price", "vf_peer"],
            )
        ],
        verified_fact_types=["price_move", "peer_moves", "sector_move", "news_events"],
    )

    narrative = build_report_narrative(run)

    assert narrative.primary_cause.label == "板块/同行同步波动"
    assert narrative.primary_cause.attribution_level == "likely_factor"
```

验收：

- primary cause 必须来自 `run.attribution_causes[0]`。
- remaining gaps 必须来自 `run.missing_facts` 和 attribution missing fact types。
- key move 缺失时不编造具体日期或跌幅。

### Phase 4：Memo Renderer v3

目标：让用户报告更接近“解释型研究简报”，而不是审计输出。

测试文件：

```text
src/research/test_memo_renderer_narrative.py
```

单测：

```python
def test_memo_renders_user_facing_narrative_sections_without_debug_ids():
    output = render_investment_memo(run_with_micron_news_events())

    assert "## 一句话结论" in output
    assert "## 最可能的原因" in output
    assert "## 基本面是否变坏" in output
    assert "板块/同行同步波动" in output
    assert "fact_" not in output
    assert "source_" not in output
```

验收：

- 报告第一屏能回答“为什么跌”。
- 原因排序第一项与 attribution primary cause 一致。
- `candidate_factor` 使用“候选因素 / 可能 / 需要核验”等保守措辞。
- 保留“归因证据矩阵”和“数据来源与时效”。

### Phase 5：回归 fixture

目标：把 MU 这类真实问题沉淀成输出结构回归。

测试文件：

```text
src/research/test_report_ux_regression.py
```

单测：

```python
def test_mu_drop_report_prioritizes_key_move_and_aligned_cause():
    run = build_fixture_mu_drop_run_with_peer_and_sector_support()

    output = render_investment_memo(run)

    assert output.index("## 一句话结论") < output.index("## 归因证据矩阵")
    assert "板块/同行同步波动" in output.split("## 最可能的原因", 1)[1]
    assert "这不是交易建议" in output
```

验收：

- 防止未来 renderer 改动把报告退回“事实表罗列”。
- 防止主因错位。
- 防止 debug id 泄漏。
- 防止直接交易建议回归。

## 11. 推荐执行顺序

```text
1. Phase 1：Loop Summary 文案分支
2. Phase 2：NewsEvent 分类器
3. Phase 3：ReportNarrative 构建
4. Phase 4：Memo Renderer v3
5. Phase 5：MU 报告 UX regression
```

推荐理由：

- Phase 1 最小、收益高，能立刻修复当前 live 输出里的尴尬文案。
- Phase 2 给报告提供结构化新闻输入，避免 renderer 靠标题字符串临时判断。
- Phase 3 把“怎么组织答案”的逻辑从 renderer 拆出来，便于测试。
- Phase 4 再改用户可见报告，风险更可控。
- Phase 5 把这次 MU 真实观察固化，避免以后回退。

## 12. 验收标准

完成后应满足：

```text
pytest src/research/test_loop_summary_view.py -q
pytest src/research/test_news_event_classifier.py -q
pytest src/research/test_report_narrative.py -q
pytest src/research/test_memo_renderer_narrative.py -q
pytest src/research/test_report_ux_regression.py -q
pytest -q
```

验收含义：

- 单项测试证明每一层能力独立正确。
- 全量测试证明没有破坏现有 query intake、normalizer、attribution、loop、CLI 行为。
- `pytest -q` 仍应保持全绿。

## 13. 未来扩展

本阶段完成后，再进入下一阶段：

- trace viewer 质量面板：直接读取 `NewsEvent`、`ReportNarrative`、`QualitySummaryView` 的 trace payload。
- 多轮对话：用户围绕当前 `final_run` 追问时，复用 narrative 和 evidence graph。
- LLM synthesis 升级：可以让 LLM 只负责改写表达，但必须禁止新增事实，并用 claim verifier 复核。

