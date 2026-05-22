"""Finance MCP Server — 暴露 yfinance 行情数据为 MCP Tools

工具：
- get_quote(symbol)            当前价 + 涨跌幅 + 货币
- get_history(symbol, days)    最近 N 天 K 线（OHLCV）

传输：stdio（本地开发）。

设计要点：
- normalize_symbol：港股 5 位前导零（00700.HK）yfinance 不认，必须 4 位（0700.HK）。
  这是 yfinance 的兼容性坑，应用层提前 normalize 比把规范化责任丢给 LLM 更稳。
- 数据缺失保护：fast_info / history() 在 ticker 不存在时表现不一致：
    - fast_info 抛 AttributeError，错误明显
    - history() 静默返回空 DataFrame，需要应用层显式判 empty
  本 server 在两条路径都做了显式判断，向 LLM 返回明确的错误文本，避免"看起来成功但数据为空"。
- timeout：yfinance 首次请求冷启动可能 ~5s，MCP 客户端 timeout 配宽点。
"""

import asyncio
import json
import sys
from typing import Any

import yfinance as yf
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent


app = Server("investment-finance")


# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------

def normalize_symbol(symbol: str) -> str:
    """规范化 ticker。

    目前只处理港股 5 位前导零 → 4 位（yfinance 兼容性问题）：
        00700.HK → 0700.HK
        09988.HK → 9988.HK

    其他市场原样返回。
    """
    if not symbol:
        return symbol
    upper = symbol.upper()
    if upper.endswith(".HK"):
        code, suffix = symbol.rsplit(".", 1)
        # 5 位代码且以 0 开头 → 去掉前导零
        if len(code) == 5 and code.startswith("0"):
            return f"{code[1:]}.{suffix}"
    return symbol


def _safe_float(value: Any) -> float | None:
    """yfinance 偶尔返回 NaN / None / numpy 类型，统一转 float 或 None。"""
    if value is None:
        return None
    try:
        f = float(value)
        # NaN 检查
        if f != f:  # NaN != NaN
            return None
        return f
    except (TypeError, ValueError):
        return None


def _fetch_quote(symbol: str) -> dict[str, Any]:
    """拉当前价 + 前收 + 涨跌幅 + 货币。失败时返回 error 字段。"""
    normalized = normalize_symbol(symbol)
    try:
        ticker = yf.Ticker(normalized)
        info = ticker.fast_info
        price = _safe_float(info.last_price)
        prev_close = _safe_float(info.previous_close)
        currency = getattr(info, "currency", None)
    except Exception as e:
        return {
            "symbol": normalized,
            "error": f"fetch_failed: {type(e).__name__}: {e}",
        }

    if price is None:
        return {
            "symbol": normalized,
            "error": "no_price_data (ticker 可能不存在或市场休市)",
        }

    change_pct = None
    if prev_close is not None and prev_close > 0:
        change_pct = round((price / prev_close - 1) * 100, 2)

    return {
        "symbol": normalized,
        "price": round(price, 2),
        "previous_close": round(prev_close, 2) if prev_close is not None else None,
        "change_pct": change_pct,
        "currency": currency,
    }


def _fetch_history(symbol: str, days: int) -> dict[str, Any]:
    """拉最近 N 天 K 线。返回每日 OHLCV。"""
    normalized = normalize_symbol(symbol)
    # yfinance period 字符串需要后缀
    if days <= 0:
        return {"symbol": normalized, "error": "days must be > 0"}
    period = f"{days}d"

    try:
        hist = yf.Ticker(normalized).history(period=period)
    except Exception as e:
        return {
            "symbol": normalized,
            "error": f"fetch_failed: {type(e).__name__}: {e}",
        }

    if hist.empty:
        return {
            "symbol": normalized,
            "error": "no_history_data (ticker 可能不存在或市场休市)",
        }

    bars = []
    for ts, row in hist.iterrows():
        bars.append({
            "date": ts.strftime("%Y-%m-%d"),
            "open": round(float(row["Open"]), 2),
            "high": round(float(row["High"]), 2),
            "low": round(float(row["Low"]), 2),
            "close": round(float(row["Close"]), 2),
            "volume": int(row["Volume"]),
        })

    return {
        "symbol": normalized,
        "period": period,
        "bars": bars,
    }


# ---------------------------------------------------------------------------
# MCP 接口
# ---------------------------------------------------------------------------

@app.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="get_quote",
            description=(
                "获取股票的当前价格、前收盘价、涨跌幅和货币。\n\n"
                "用户问'XX 现在多少钱'、'当前股价'、'今天涨了吗'、'实时报价'等问题时调用。\n\n"
                "参数 symbol 必须是规范的股票代码：\n"
                "- 美股直接写代码，如 AAPL、NVDA、TSLA\n"
                "- A 股加后缀，如 600519.SS（上交所）、000001.SZ（深交所）\n"
                "- 港股 4 位代码加 .HK，如 0700.HK、9988.HK（不加前导零）\n\n"
                "如果用户只说公司中文名（如'贵州茅台'），先在回复中给出对应代码并请用户确认。\n\n"
                "**涉及历史价位 / 复权判断时**（如'我 $1200 买的 TSLA 现在浮盈多少'、"
                "'这价位是不是拆股前的'），**先调 get_corporate_actions 拿历史拆股事实**，"
                "再用本工具的当前价做复权计算，避免凭训练知识猜拆股次数。"
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "symbol": {
                        "type": "string",
                        "description": "规范股票代码，如 NVDA / 600519.SS / 0700.HK",
                    },
                },
                "required": ["symbol"],
            },
        ),
        Tool(
            name="get_history",
            description=(
                "获取股票最近 N 天的日 K 线（开盘价、最高、最低、收盘、成交量）。\n\n"
                "用户问'最近一周走势'、'最近 N 天涨跌情况'、'K 线'、'历史价格'等问题时调用。\n\n"
                "参数 days 是交易日天数（非自然日），建议范围 5-90。少于 5 天信息量不足，"
                "超过 90 天数据量大且通常不必要。\n\n"
                "symbol 规则同 get_quote。"
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "symbol": {
                        "type": "string",
                        "description": "规范股票代码，如 NVDA / 600519.SS / 0700.HK",
                    },
                    "days": {
                        "type": "integer",
                        "description": "回看交易日天数，建议 5-90",
                        "minimum": 1,
                        "maximum": 365,
                    },
                },
                "required": ["symbol", "days"],
            },
        ),
    ]


@app.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    if name == "get_quote":
        result = _fetch_quote(arguments["symbol"])
    elif name == "get_history":
        result = _fetch_history(arguments["symbol"], int(arguments["days"]))
    else:
        raise ValueError(f"Unknown tool: {name}")

    return [TextContent(
        type="text",
        text=json.dumps(result, ensure_ascii=False, indent=2),
    )]


# ---------------------------------------------------------------------------
# 启动入口
# ---------------------------------------------------------------------------

async def main() -> None:
    print("[finance_server] starting (yfinance backend)", file=sys.stderr, flush=True)
    async with stdio_server() as (read_stream, write_stream):
        await app.run(
            read_stream,
            write_stream,
            app.create_initialization_options(),
        )


if __name__ == "__main__":
    asyncio.run(main())
