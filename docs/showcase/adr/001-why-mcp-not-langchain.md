# ADR-001：选 MCP 协议而不是 LangChain 工具集

- **状态**：Accepted
- **日期**：2026-05-11
- **决策者**：项目作者（个人项目）

---

## Context（背景）

investment-agent 需要把"持仓记忆 / 行情 / 新闻 / 公司行动事件"封装成可被 LLM 调用的工具。市面上有几种主流方式：

- **LangChain Tools**：把工具写成 `@tool` 函数，绑定到 LangChain Agent
- **OpenAI Function Calling**：直接走 OpenAI API 的 `functions` 字段
- **MCP（Model Context Protocol）**：Anthropic 主导的协议，stdio/HTTP 传输，独立进程
- **自己写 HTTP API + Prompt 注入**：完全自研

需求约束：

1. 同一份工具要能被 **Claude Desktop**（GUI）+ **Claude Code**（CLI）+ **自研 Agent（Python sdk）** 三种客户端复用
2. 工具要能独立部署、独立迭代（不和 Agent 主代码耦合）
3. 工具数量会从 4 个 → 10+，需要协议层面的可扩展性

---

## Decision（决策）

**选 MCP 协议**，把每类工具实现为独立的 MCP Server（`memory_server` / `finance_server` / `news_server` / `corporate_actions_server`）。

---

## Consequences（结果）

### 正面

- ✅ **三客户端零修改复用**：同一份 `memory_server.py` 同时被 Claude Desktop、Claude Code、自研 Agent 调用，无任何分支代码
- ✅ **工具独立进程**：每个 Server stdio 通信，崩了不会拖垮 Agent 主进程
- ✅ **协议级标准化**：`list_tools` + `call_tool` 是统一契约，dispatch 处可加审计 / auth / 限流
- ✅ **跨语言友好**：协议是 JSON-RPC 2.0，后续若有 Java/Go 工具实现，无需改 Client

### 负面

- ⚠️ **多进程开销**：每个 Client 启动时会 fork 多个 Server 进程（4 Server × 3 Client = 12 进程峰值）
- ⚠️ **协议学习曲线**：三段式握手（initialize → result → notifications/initialized）比直接函数调用复杂
- ⚠️ **调试不便**：工具调用要看 stderr 日志而不是直接 print，Desktop 上 Server 崩溃只显示 "MCP server failed to load"
- ⚠️ **HTTP+SSE 未实操**：本项目只用 stdio，远程跨主机场景的协议表现未验证

---

## Alternatives Considered（备选方案）

| 方案 | 优 | 劣 | 为什么没选 |
|---|---|---|---|
| LangChain Tools | 生态成熟、文档多 | 工具和 LangChain Agent **强耦合** | 无法被 Claude Desktop / Code 直接消费 |
| OpenAI Function Calling | 简单、直接 | 绑定 OpenAI SDK，**只能在 OpenAI 客户端使用** | 跨客户端零修改复用做不到 |
| 自研 HTTP API + Prompt 注入 | 完全可控 | 没有协议标准，**每个客户端要写 adapter** | 工程量大、不可扩展 |
| MCP ★ | 跨客户端复用、独立进程、协议标准 | 多进程开销、学习曲线 | 唯一同时满足三客户端复用 + 工具独立部署的方案 |

---

## 后续验证

- ✅ 2026-05-11 memory_server 上线 + Claude Desktop + Claude Code 双客户端零修改复用验证通过
- ✅ 2026-05-13 finance + news 加入后，3 Server 协作在 Claude Desktop 跑通 "腾讯为什么跌" 一句话多工具调用
- 🔲 W3 自研 Agent（claude-agent-sdk）作为第三客户端接入（保留三客户端验证完整性）
- 🔲 HTTP+SSE 远程传输模式实操（W4 之后）

---

## 关联

- 协议详解：[mcp-protocol.md](../../../../../memory/shared/best-practices/mcp-protocol.md)
- 总览架构图：[diagrams/01-overview.md](../diagrams/01-overview.md)
- 下游决策 ADR-002：[002-cross-server-no-orchestrator.md](./002-cross-server-no-orchestrator.md)
