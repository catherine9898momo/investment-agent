# 研究运行时序图（E）— 单次 Investment Research Run

> 用途：解释当前 P1 research loop 的真实执行顺序，澄清它是 single-agent pipeline / workflow orchestration，不是 multi-agent orchestrator。
> 箭头含义：一次用户研究请求中的执行顺序和数据转换方向；不表示代码 import 依赖、服务部署依赖或多 agent 调度关系。

---

## Mermaid 源码

```mermaid
sequenceDiagram
    autonumber

    actor User as 用户 / CLI / MCP Client
    participant Entry as research_demo<br/>Run Builder
    participant Intake as Query Intake<br/>Router / Entity / TimeWindow
    participant Provider as Tool Provider
    participant Tools as MCP Tools<br/>finance / news / memory / corporate_actions
    participant Data as 外部 / 本地数据源<br/>yfinance / Google News / SQLite / config
    participant Normalizer as Source / Fact Normalizer
    participant Verifier as Fact Verifier<br/>Verified / Missing Facts
    participant Context as Research Context Builder
    participant LLM as LLM Synthesizer
    participant ClaimCheck as Claim Verifier<br/>Evidence Binder
    participant Memo as Memo Renderer
    participant Guardrail as Guardrail / Evaluator
    participant Trace as Trace Logger / Eval

    User->>Entry: 1. 输入投资研究问题<br/>例如“TSLA 最近还值得关注吗？”
    Entry->>Intake: 2. 解析用户问题

    Intake-->>Entry: 3. 返回 QueryUnderstanding<br/>intent / ticker / company / time window / plan

    Entry->>Provider: 4. 根据解析结果请求工具数据<br/>symbol / company_query / history_days / news_days

    Provider->>Tools: 5. 调用工具<br/>quote / history / news / preferences / corporate actions
    Tools->>Data: 6. 读取外部或本地数据
    Data-->>Tools: 7. 返回原始行情、新闻、持仓、公司行动
    Tools-->>Provider: 8. 返回 tool-shaped results

    Provider-->>Entry: 9. 返回 ToolResultBundle

    Entry->>Trace: 10. 记录 run_started / tool_result

    Entry->>Normalizer: 11. 标准化工具结果
    Normalizer-->>Entry: 12. 返回 Sources + Facts<br/>来源、时间戳、价格、新闻、拆股、偏好、数据质量

    Entry->>Verifier: 13. 构建 verified fact table
    Verifier-->>Entry: 14. 返回 VerifiedFacts + MissingFacts<br/>已核验证据和显式缺口

    Entry->>Context: 15. 构建给 LLM 的最小上下文
    Context-->>Entry: 16. 返回 ResearchContext<br/>facts / missing facts / constraints

    Entry->>LLM: 17. 基于 ResearchContext 综合
    LLM-->>Entry: 18. 返回 candidate claims<br/>每条 claim 引用 fact_id

    Entry->>ClaimCheck: 19. 校验 claims 并绑定证据
    ClaimCheck-->>Entry: 20. 返回 evidence-bound Claims<br/>过滤无证据或越界 claims

    Entry->>Memo: 21. 渲染投资研究简报
    Memo-->>Entry: 22. 返回 Markdown Memo

    Entry->>Guardrail: 23. 输出前检查
    Guardrail-->>Entry: 24. 返回 GuardrailResult<br/>交易建议边界 / 证据 / 来源 / 时间戳 / 风险 / 人工确认

    Entry->>Trace: 25. 记录 memo / guardrail / final_output

    alt guardrail passed
        Entry-->>User: 26. 输出研究报告<br/>status = completed
    else guardrail blocked
        Entry-->>User: 26. 输出阻断或需修正结果<br/>status = blocked
    end
```

---

## 节点说明

| 节点 | 当前代码位置 | 作用 |
|---|---|---|
| `research_demo / Run Builder` | `src/agents/research_demo.py` | 串联一次 research run，创建并更新 `ResearchRunState`，记录 trace。 |
| `Query Intake` | `src/research/query_intake.py` | 解析用户问题、标的、意图、研究窗口和研究计划。 |
| `Tool Provider` | `src/research/tool_provider.py` | 在 `live` 和 `fixture` 模式下取工具形态结果，并隔离单工具失败。 |
| `MCP Tools` | `src/mcp_servers/` | 提供行情、新闻、记忆、公司行动等工具能力。 |
| `Source / Fact Normalizer` | `src/research/normalizers.py` | 把工具结果转成可追踪的 `Source` 和 `Fact`。 |
| `Fact Verifier` | `src/research/fact_verifier.py` | 构建已核验事实表，并显式记录缺失事实。 |
| `Research Context Builder` | `src/research/context_builder.py` | 把完整 run state 收敛成 LLM 可见的最小研究上下文。 |
| `LLM Synthesizer` | `src/research/synthesizer.py` | 基于 `ResearchContext` 生成结构化 candidate claims 和人工确认点。 |
| `Claim Verifier / Evidence Binder` | `src/research/claim_verifier.py`, `src/research/synthesizer.py` | 校验 claim 边界，把 claim 绑定回 `fact_id` / `source_id`。 |
| `Memo Renderer` | `src/research/memo_renderer.py` | 渲染用户可读的 Markdown 投资研究简报。 |
| `Guardrail / Evaluator` | `src/research/evaluator.py` | 检查交易建议边界、证据、来源、时间戳、风险和人工确认点。 |
| `Trace Logger / Eval` | `src/research/trace.py`, `src/eval/` | 保存可回放 trace，并支持 regression case 检查。 |

---

## 设计边界

- 当前项目是 **single-agent research pipeline**，不是 planner / researcher / critic / portfolio analyst 多角色 agent 系统。
- `ResearchRunState` 是贯穿流程的状态对象，不是独立服务或 agent。
- `LLM Synthesizer` 位于 `Source / Fact Normalizer` 和 `Research Context Builder` 之后，`Claim Verifier / Evidence Binder` 之前；它不能绕过 facts 直接生成事实结论。
- `Guardrail / Evaluator` 在 memo 渲染之后做最终输出检查，因此它检查的是用户实际会看到的文本和已绑定证据。
