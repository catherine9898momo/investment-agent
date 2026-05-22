# ADR — 架构决策记录

> 这里记录 investment-agent 项目里**值得被面试官追问"为什么这么做"的关键决策**，每篇按 Michael Nygard 的 ADR 模板写：Context / Decision / Consequences / Alternatives Considered。

---

## 索引

| # | 标题 | 决策日期 | 关键词 |
|---|---|---|---|
| [001](./001-why-mcp-not-langchain.md) | 为什么选 MCP 协议而不是 LangChain 工具集 | 2026-05-11 | 协议 vs 框架 / 跨客户端复用 |
| [002](./002-cross-server-no-orchestrator.md) | 跨 Server 协作不需要 orchestrator | 2026-05-13 | LLM 自主编排 / description 边界 |
| [003](./003-corporate-actions-data-source.md) | corporate_actions 选 yfinance+SQLite 不选 LLM 联网搜索 | 2026-05-14 | ground truth / LLM hop / 决策树 |
| [004](./004-knowledge-layering.md) | 三层知识分层设计模式 | 2026-05-13 | 触发器/事实/建议 / 注意力机制 |
| [005](./005-description-vs-inputschema.md) | description 写边界、inputSchema 约束结构 | 2026-05-12 | A/B 实验 10/10 / 语义 vs 结构 |
| [006](./006-showcase-html-only.md) | Showcase 资产走纯文本 + HTML 静态站点路线 | 2026-05-19 | 单一真理源 / 自动同步 / MkDocs Material |

---

## 阅读建议

| 受众 | 阅读顺序 |
|---|---|
| HR / 一面 | 003 → 004（看反例闭环） |
| 终面架构师 | 002 → 005 → 001（看协议选型与工具池扩展性思考） |
| 同行技术博客读者 | 004 → 003 → 002（先读模式，再读案例，再读协作） |

---

## 写作约定

- 每篇 200-400 字主体 + 备选方案表
- **Alternatives Considered 不能空**——证明思考过多个方案，不是拍脑袋
- **Consequences 要有"负面"项**——选了 A 一定会失去 B，诚实写出来
- 关联 case study / 架构图 / memory/ 知识库原文，方便面试官追问时下钻
