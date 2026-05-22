"""Memory MCP Server — 暴露 SQLite 存储层为 MCP Tools

供 Claude Desktop / Claude Code / 自研 Agent 复用同一份持仓 / 关注列表 / 偏好数据。
传输：stdio（本地开发场景）

description 版本切换：
    MEMORY_DESC_VERSION=v0  使用粗糙描述（仅一句话），用于 A/B 实验对照组
    MEMORY_DESC_VERSION=v1  使用精细描述（含调用边界 / 参数规范 / 示例），默认值
"""

import asyncio
import json
import os
import sys
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

from src.memory import store


# MCP Server 实例，名字会出现在 Claude Desktop 的工具来源标识里
app = Server("investment-memory")


# A/B 实验：description 版本
# v0 = 粗糙描述（对照组），v1 = 精细描述（实验组，含调用边界）
DESC_VERSION = os.environ.get("MEMORY_DESC_VERSION", "v1").lower()

# 在 stderr 打一行版本标识，方便在 ~/Library/Logs/Claude/mcp-server-investment-memory.log
# 里确认实际生效的 description 版本（防止 Desktop 缓存或环境变量未生效翻车）
print(f"[memory_server] DESC_VERSION={DESC_VERSION} loaded", file=sys.stderr, flush=True)


DESCRIPTIONS: dict[str, dict[str, str]] = {
    "v0": {
        "list_portfolio": "查持仓",
        "add_holding": "添加持仓",
        "list_watchlist": "查关注列表",
        "get_preferences": "查偏好",
        # 参数描述也保持极简
        "param_symbol": "股票代码",
        "param_name": "名字",
        "param_market": "市场",
        "param_shares": "数量",
        "param_avg_cost": "成本",
    },
    "v1": {
        "list_portfolio": (
            "读取用户当前所有持仓股票的完整列表。"
            "返回每只股票的代码、名称、市场、持仓数量、平均成本和最后更新时间。"
            "用户问'我的持仓'、'我现在持有什么'、'持仓情况'等问题时调用。"
        ),
        "add_holding": (
            "向用户的持仓表添加或更新一只股票。\n\n"
            "仅在用户明确表达'我买入了'、'我现在持有'、'加入持仓'等真实交易意图时调用。"
            "不要在用户只是询问、讨论或评论某只股票时调用。\n\n"
            "参数 symbol 必须是规范的股票代码：\n"
            "- 美股直接写代码，如 AAPL、NVDA、TSLA\n"
            "- A 股加后缀，如 600519.SS（上交所）、000001.SZ（深交所）\n"
            "- 港股 4 位代码加 .HK，如 0700.HK、9988.HK（注意：不加前导零，"
            "00700.HK 在 yfinance 等数据源会失败）\n\n"
            "如果用户只说公司中文名（如'贵州茅台'），先在回复中给出对应代码（600519.SS）"
            "并请用户确认后再调用本工具。\n\n"
            "**拆股提醒（重要）**：如果用户给的 avg_cost 与该股票当前价差距明显（如"
            " TSLA $1200、NVDA $500+），可能是拆股前的历史成本价。"
            "**先调用 get_corporate_actions 工具核对历史拆股事实**，再向用户复权确认；"
            "不要直接用训练知识里的拆股记忆做判断（可能漏识别多次拆股事件）。"
        ),
        "list_watchlist": (
            "读取用户的关注列表（非持仓但持续追踪的公司）。"
            "返回每只股票的代码、名称、市场、关注原因和加入时间。"
            "用户问'我关注了哪些公司'、'关注列表'等问题时调用。"
        ),
        "get_preferences": (
            "读取用户的投资偏好配置（欣赏的投资者、投资风格、风险偏好、关注行业、分析语言）。"
            "在生成分析报告或回答与投资判断相关的问题前应先调用，"
            "以保证分析风格匹配用户偏好。不需要参数。"
        ),
        "param_symbol": "规范股票代码，如 AAPL / 600519.SS / 00700.HK",
        "param_name": "公司中文或英文名",
        "param_market": "市场：US 美股 / CN A 股 / HK 港股",
        "param_shares": "持仓数量（股），默认 0 表示只记录不入持仓数",
        "param_avg_cost": "平均成本价（按对应市场的本币），默认 0",
    },
}

if DESC_VERSION not in DESCRIPTIONS:
    raise ValueError(
        f"Invalid MEMORY_DESC_VERSION={DESC_VERSION}, must be one of {list(DESCRIPTIONS)}"
    )

D = DESCRIPTIONS[DESC_VERSION]


@app.list_tools()
async def list_tools() -> list[Tool]:
    """声明这个 Server 能干什么。Agent 在调用前先拿这份清单。

    注意：只有 description 随 MEMORY_DESC_VERSION 切换，inputSchema（required/enum/type）
    保持不变——本实验隔离的是 description 的语义约束力，schema 的结构约束力是 D3 的实验。
    """
    return [
        Tool(
            name="list_portfolio",
            description=D["list_portfolio"],
            inputSchema={
                "type": "object",
                "properties": {},
                "required": [],
            },
        ),
        Tool(
            name="add_holding",
            description=D["add_holding"],
            inputSchema={
                "type": "object",
                "properties": {
                    "symbol": {
                        "type": "string",
                        "description": D["param_symbol"],
                    },
                    "name": {
                        "type": "string",
                        "description": D["param_name"],
                    },
                    "market": {
                        "type": "string",
                        "enum": ["US", "CN", "HK"],
                        "description": D["param_market"],
                    },
                    "shares": {
                        "type": "number",
                        "description": D["param_shares"],
                    },
                    "avg_cost": {
                        "type": "number",
                        "description": D["param_avg_cost"],
                    },
                },
                "required": ["symbol", "name", "market"],
            },
        ),
        Tool(
            name="list_watchlist",
            description=D["list_watchlist"],
            inputSchema={
                "type": "object",
                "properties": {},
                "required": [],
            },
        ),
        Tool(
            name="get_preferences",
            description=D["get_preferences"],
            inputSchema={
                "type": "object",
                "properties": {},
                "required": [],
            },
        ),
    ]


@app.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    """收到工具调用请求时的派发逻辑。"""
    if name == "list_portfolio":
        data = store.get_portfolio()
        return [TextContent(
            type="text",
            text=json.dumps(data, ensure_ascii=False, indent=2),
        )]

    if name == "add_holding":
        store.add_holding(
            symbol=arguments["symbol"],
            name=arguments["name"],
            market=arguments["market"],
            shares=arguments.get("shares", 0),
            avg_cost=arguments.get("avg_cost", 0),
        )
        return [TextContent(
            type="text",
            text=f"已记录持仓 {arguments['symbol']} ({arguments['name']})",
        )]

    if name == "list_watchlist":
        data = store.get_watchlist()
        return [TextContent(
            type="text",
            text=json.dumps(data, ensure_ascii=False, indent=2),
        )]

    if name == "get_preferences":
        data = store.get_all_preferences()
        return [TextContent(
            type="text",
            text=json.dumps(data, ensure_ascii=False, indent=2),
        )]

    raise ValueError(f"Unknown tool: {name}")


async def main() -> None:
    """通过 stdio 启动 MCP Server。父进程（Claude Desktop / Claude Code）通过 pipe 通信。"""
    async with stdio_server() as (read_stream, write_stream):
        await app.run(
            read_stream,
            write_stream,
            app.create_initialization_options(),
        )


if __name__ == "__main__":
    asyncio.run(main())
