# 研究流水线架构图（F）— LLM Synthesizer 位置修正版

> 用途：用 flowchart 说明当前 Investment Agent 的 P1 research pipeline 总体架构。
> 箭头含义：单次研究任务中的执行顺序和数据转换方向；不表示代码 import 依赖、服务部署依赖或多 agent 调度。

---

## Mermaid 源码

```mermaid
flowchart TB
    U["User / CLI / MCP Client<br/>用户问题或命令入口"]

    E["research_demo / Run Builder<br/>创建并更新 ResearchRunState<br/>串联单次 research run"]

    Q["Query Intake / Router<br/>解析问题、ticker、公司名<br/>识别时间窗口和研究类型"]

    P["Tool Provider<br/>根据解析结果拉取数据<br/>支持 live / fixture<br/>隔离单工具失败"]

    subgraph TOOL_LAYER["MCP Tool 层"]
        M["memory_server<br/>持仓 / 偏好 / watchlist"]
        F["finance_server<br/>quote / history"]
        N["news_server<br/>新闻召回"]
        CA["corporate_actions_server<br/>拆股 / 股息 ground truth"]
    end

    subgraph DATA_LAYER["外部 / 本地数据源"]
        YF[("yfinance<br/>行情 / 历史价格 / 公司行动")]
        GN[("Google News RSS<br/>新闻")]
        DB[("SQLite / config<br/>持仓 / 偏好 / 缓存")]
    end

    SF["Source / Fact Normalizer<br/>工具结果标准化<br/>Source: 来源 / 时间戳 / 可靠性<br/>Fact: 价格 / 新闻 / 拆股 / 偏好 / 数据质量"]

    VF["Fact Verifier<br/>生成 VerifiedFacts<br/>显式记录 MissingFacts"]

    RC["Research Context Builder<br/>把完整 run state 收敛为 LLM 最小上下文<br/>facts / missing facts / constraints"]

    LLM["LLM Synthesizer<br/>输入: ResearchContext<br/>输出: candidate claims + human confirmation points<br/>每条 claim 必须引用 fact_id"]

    CB["Claim Verifier / Evidence Binder<br/>校验 fact_id 是否存在<br/>绑定 fact_id -> source_id<br/>过滤无证据或越界 claim"]

    MR["Memo Renderer<br/>输出用户可读 Markdown 投资研究简报"]

    G["Guardrail / Evaluator<br/>检查直接交易建议边界<br/>检查证据、来源、时间戳、风险、不确定性、人工确认点"]

    O["Final Output + Trace / Eval<br/>Investment Memo<br/>Trace JSONL<br/>Regression case"]

    U --> E --> Q --> P --> TOOL_LAYER --> DATA_LAYER --> TOOL_LAYER --> P --> SF --> VF --> RC --> LLM --> CB --> MR --> G --> O

    E -."记录 run_started / tool_result / final_output".-> O
    Q -."intake / route / entity / plan".-> E
    SF -."sources / facts".-> E
    VF -."verified_facts / missing_facts".-> E
    CB -."claims / evidence".-> E
    G -."guardrail status".-> E

    M --> DB
    F --> YF
    N --> GN
    CA --> YF
    CA --> DB

    classDef entry fill:#e3f2fd,stroke:#1976d2,stroke-width:1.5px
    classDef tool fill:#fff3e0,stroke:#f57c00,stroke-width:1.5px
    classDef data fill:#f5f5f5,stroke:#616161,stroke-width:1px,stroke-dasharray:3 3
    classDef evidence fill:#e8f5e9,stroke:#2e7d32,stroke-width:1.5px
    classDef llm fill:#ede7f6,stroke:#5e35b1,stroke-width:1.5px
    classDef guard fill:#ffebee,stroke:#c62828,stroke-width:1.5px

    class U,E,Q,P entry
    class M,F,N,CA tool
    class YF,GN,DB data
    class SF,VF,RC,CB evidence
    class LLM llm
    class G guard
```

---

## 读图说明

这张图强调当前项目的主链路是：

```text
用户问题
-> 问题解析
-> 工具取数
-> Source / Fact 标准化
-> Fact 核验与缺口记录
-> ResearchContext 最小上下文
-> LLM Synthesizer 生成 candidate claims
-> Claim / Evidence 绑定
-> Memo 渲染
-> Guardrail 检查
-> Final Memo + Trace / Eval
```

每个节点的作用如下：

- `User / CLI / MCP Client`：用户从本地 CLI、Claude Desktop、Claude Code 或其他 MCP client 发起研究问题。
- `research_demo / Run Builder`：当前单次研究任务的入口控制代码，创建并更新 `ResearchRunState`，串联各模块。
- `Query Intake / Router`：把自然语言问题转成可执行的标的、意图、时间窗口和研究计划。
- `Tool Provider`：根据解析结果拉取行情、新闻、偏好和公司行动数据。
- `MCP Tool 层`：封装实际工具能力，不承担最终研究判断。
- `外部 / 本地数据源`：提供原始事实来源，包括 yfinance、Google News RSS、SQLite 和 config。
- `Source / Fact Normalizer`：把原始工具结果转成带来源、时间戳和可靠性的结构化事实。
- `Fact Verifier`：区分已核验事实和缺失事实，避免把缺口当结论。
- `Research Context Builder`：把完整状态收敛成 LLM 可见的最小上下文，减少越权读取和幻觉空间。
- `LLM Synthesizer`：只基于 `ResearchContext` 生成候选研究结论，不直接给交易指令。
- `Claim Verifier / Evidence Binder`：检查候选结论是否能绑定回 `fact_id` 和 `source_id`。
- `Memo Renderer`：把已绑定证据的研究状态渲染成用户可读报告。
- `Guardrail / Evaluator`：对最终用户可见文本做交易建议边界、证据、风险和来源检查。
- `Final Output + Trace / Eval`：输出研究 memo，并留下可回放 trace 和回归测试入口。

---

## 关键修正

- `LLM Synthesizer` 不再画在 Tool Provider 的并列分支上；它必须位于 `Source / Fact Normalizer`、`Fact Verifier` 和 `Research Context Builder` 之后。
- `Claim / Evidence Binder` 必须位于 `LLM Synthesizer` 之后，因为它处理的是 LLM 生成的 candidate claims。
- 当前图表达的是 **single-agent research pipeline**，不是 multi-agent orchestrator；编排对象是研究步骤和工具调用，不是多个 agent 角色。
- `ResearchRunState` 是贯穿流程的状态容器，因此在图中作为 `research_demo / Run Builder` 的维护对象出现，而不是独立服务节点。
