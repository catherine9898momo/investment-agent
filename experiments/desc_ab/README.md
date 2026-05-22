# description A/B 实验脚手架

W1 D2 产出，详见 `learning/daily-lesson/2026-05-12-description-ab.md`。

## 文件

- `mcp-v0.json` / `mcp-v1.json` — 切换 `MEMORY_DESC_VERSION` 的 MCP 配置
- 配套代码：`src/mcp_servers/memory_server.py` 里的 `DESCRIPTIONS` dict

## 快速重跑（如果以后要补 v0 数据）

```bash
# 方式 1：Claude Desktop GUI
#   1. 改 ~/Library/Application Support/Claude/claude_desktop_config.json
#      把 "MEMORY_DESC_VERSION": "v1" 改成 "v0"
#   2. Cmd+Q 完全退出，重新打开
#   3. 验证：tail ~/Library/Logs/Claude/mcp-server-investment-memory.log | grep DESC_VERSION
#   4. 跑 10 case（详见 daily-lesson 文档）

# 方式 2：claude -p headless（注意 Anthropic 502 风险）
/opt/homebrew/bin/claude -p "<case query>" \
  --mcp-config /Users/mtdp/ai/projects/investment-agent/experiments/desc_ab/mcp-v0.json \
  --strict-mcp-config \
  --permission-mode bypassPermissions \
  --no-session-persistence \
  --output-format stream-json \
  --verbose \
  --model sonnet
```

## 10 个 case（W1 D2 + 可复用到 W1 D3）

| # | 输入 | 期望 |
|---|---|---|
| 1 | 我买了 100 股 NVIDIA，成本 850 | add_holding(NVDA, US, 100, 850) |
| 2 | 我刚加仓了贵州茅台 50 股，均价 1680 | add_holding(600519.SS, CN, 50, 1680) |
| 3 | 把宁王加入持仓，200 股 | 先确认"宁王→宁德时代 300750.SZ"再 add_holding |
| 4 | 我买了阿里巴巴 | 反问 BABA / 09988.HK 选哪个 + 股数 + 成本 |
| 5 | 我很看好 Pinduoduo，可能会涨 | 不调 add_holding（陷阱） |
| 6 | 苹果现在估值怎么样 | 不调 memory 工具（陷阱） |
| 7 | 我现在持有什么 | list_portfolio |
| 8 | 我关注了哪些公司 | list_watchlist |
| 9 | 我的投资风格是什么 | get_preferences |
| 10 | 茅台这家公司怎么样 | 不调 memory 工具（陷阱） |

## v1 baseline 结果（2026-05-12 Desktop 实测）

行为正确率 **10/10**，详见 `learning/daily-lesson/2026-05-12-description-ab.md`。
