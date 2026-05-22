"""Corporate Actions MCP Server — 拆股 / 股息历史的 ground truth 服务

设计动机：闭环修复 LLM 训练知识不稳定反例（2026-05-13 TSLA $1200 case，
同一持仓同一天两次给出不同复权答案——一次 15:1、一次 3:1）。

知识分层模式：
- 触发器（"价位看起来不对"）→ LLM 训练知识
- 具体事实（拆股年月 / 比例 / 因子）→ 本服务（外部 ground truth）
- 决策建议 → LLM 综合两者

数据流：
- 首选 SQLite 缓存（24h TTL）
- miss / 过期 → yfinance 刷新并落库
- yfinance 失败 → 退回 stale 缓存 + warning，不阻塞调用方
"""

import asyncio
import json
import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import yfinance as yf
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent


app = Server("investment-corporate-actions")

DB_PATH = Path(__file__).parent.parent.parent / "memory.db"
CACHE_TTL = timedelta(hours=24)


# ---------------------------------------------------------------------------
# SQLite 缓存
# ---------------------------------------------------------------------------

def _get_db() -> sqlite3.Connection:
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA journal_mode=WAL")
    return db


def _init_schema() -> None:
    db = _get_db()
    try:
        db.executescript("""
            CREATE TABLE IF NOT EXISTS corporate_actions (
                symbol TEXT NOT NULL,
                action_type TEXT NOT NULL,
                date TEXT NOT NULL,
                ratio TEXT,
                factor REAL NOT NULL,
                PRIMARY KEY (symbol, action_type, date)
            );

            CREATE TABLE IF NOT EXISTS corporate_actions_fetch_log (
                symbol TEXT PRIMARY KEY,
                fetched_at TEXT NOT NULL
            );
        """)
        db.commit()
    finally:
        db.close()


def _read_cache(symbol: str) -> tuple[list[dict], datetime | None]:
    """读缓存。返回 (actions, last_fetched_at)；last_fetched=None 表示从未拉过。"""
    db = _get_db()
    try:
        rows = db.execute(
            "SELECT action_type, date, ratio, factor FROM corporate_actions "
            "WHERE symbol = ? ORDER BY date",
            (symbol,),
        ).fetchall()
        log = db.execute(
            "SELECT fetched_at FROM corporate_actions_fetch_log WHERE symbol = ?",
            (symbol,),
        ).fetchone()
        last = datetime.fromisoformat(log["fetched_at"]) if log else None
        return [dict(r) for r in rows], last
    finally:
        db.close()


def _write_cache(symbol: str, actions: list[dict]) -> None:
    """全量覆盖该 symbol 的缓存。"""
    db = _get_db()
    try:
        db.execute("DELETE FROM corporate_actions WHERE symbol = ?", (symbol,))
        db.executemany(
            "INSERT INTO corporate_actions (symbol, action_type, date, ratio, factor) "
            "VALUES (?, ?, ?, ?, ?)",
            [
                (symbol, a["action_type"], a["date"], a.get("ratio"), a["factor"])
                for a in actions
            ],
        )
        db.execute(
            "INSERT OR REPLACE INTO corporate_actions_fetch_log (symbol, fetched_at) "
            "VALUES (?, ?)",
            (symbol, datetime.now().isoformat()),
        )
        db.commit()
    finally:
        db.close()


# ---------------------------------------------------------------------------
# yfinance 数据拉取
# ---------------------------------------------------------------------------

def normalize_symbol(symbol: str) -> str:
    """同 finance_server：港股 5 位前导零 → 4 位，yfinance 兼容性兜底。"""
    if not symbol:
        return symbol
    upper = symbol.upper()
    if upper.endswith(".HK"):
        code, suffix = symbol.rsplit(".", 1)
        if len(code) == 5 and code.startswith("0"):
            return f"{code[1:]}.{suffix}"
    return symbol


def _ratio_str(factor: float) -> str:
    """factor → 人类可读的拆股比例字符串。

    yfinance splits Series 约定：
    - 普通拆股 N:1 → factor = N（一变 N，如 5.0 = 5:1）
    - 反向拆股 1:N → factor = 1/N（如 0.2 = 1:5）
    """
    if factor >= 1:
        if abs(factor - round(factor)) < 1e-6:
            return f"{int(round(factor))}:1"
        return f"{factor:.2f}:1"
    inv = 1.0 / factor
    if abs(inv - round(inv)) < 1e-2:
        return f"1:{int(round(inv))}"
    return f"1:{inv:.2f}"


def _fetch_from_yfinance(symbol: str) -> list[dict]:
    """从 yfinance 拉拆股 + 股息，归一化输出。"""
    normalized = normalize_symbol(symbol)
    ticker = yf.Ticker(normalized)

    actions: list[dict] = []

    splits = ticker.splits
    for ts, factor in splits.items():
        f = float(factor)
        if f <= 0:
            continue
        actions.append({
            "action_type": "split",
            "date": ts.strftime("%Y-%m-%d"),
            "ratio": _ratio_str(f),
            "factor": f,
        })

    dividends = ticker.dividends
    for ts, amount in dividends.items():
        a = float(amount)
        if a <= 0:
            continue
        actions.append({
            "action_type": "dividend",
            "date": ts.strftime("%Y-%m-%d"),
            "ratio": None,
            "factor": a,  # factor 字段对 dividend 复用为每股金额
        })

    return sorted(actions, key=lambda x: x["date"])


# ---------------------------------------------------------------------------
# 业务逻辑
# ---------------------------------------------------------------------------

def get_corporate_actions(symbol: str, include_dividends: bool = False) -> dict[str, Any]:
    """获取股票历史 corporate actions。缓存优先，过期则刷新。"""
    normalized = normalize_symbol(symbol)
    cached, last_fetched = _read_cache(normalized)

    needs_refresh = last_fetched is None or (datetime.now() - last_fetched) > CACHE_TTL

    actions = cached
    source = "cache"
    warning: str | None = None

    if needs_refresh:
        try:
            actions = _fetch_from_yfinance(normalized)
            _write_cache(normalized, actions)
            source = "yfinance"
            last_fetched = datetime.now()
        except Exception as e:
            warning = f"yfinance refresh failed: {type(e).__name__}: {e}"
            if cached:
                source = "stale_cache"
            else:
                return {
                    "symbol": normalized,
                    "actions": [],
                    "splits_count": 0,
                    "cumulative_split_factor": 1.0,
                    "source": "error",
                    "error": warning,
                }

    splits = [a for a in actions if a["action_type"] == "split"]
    cumulative = 1.0
    for s in splits:
        cumulative *= s["factor"]

    visible = actions if include_dividends else splits

    out: dict[str, Any] = {
        "symbol": normalized,
        "actions": visible,
        "splits_count": len(splits),
        "cumulative_split_factor": round(cumulative, 4),
        "source": source,
        "last_fetched": last_fetched.isoformat() if last_fetched else None,
    }
    if warning:
        out["warning"] = warning
    return out


# ---------------------------------------------------------------------------
# MCP 接口
# ---------------------------------------------------------------------------

DESCRIPTION_GET = (
    "获取股票的历史 corporate actions（公司行动）——主要是拆股，可选包含股息。\n\n"
    "**这是 ground truth 工具，提供结构化历史事实，用来替代 LLM 训练知识里"
    "对拆股事件的模糊记忆。**\n\n"
    "**强烈建议在以下场景调用**（涉及历史价位 / 复权判断时）：\n"
    "- 用户给的 avg_cost 看起来与当前价差距很大（可能是拆股前的成本价）\n"
    "- 浮盈 / 浮亏计算\n"
    "- 历史价位讨论（如'当年我 $1200 买的'）\n"
    "- 主动给出拆股提醒前先核对（避免漏识别多次拆股）\n\n"
    "**为什么不要直接用训练知识里的拆股事实**：在长 session / 复杂任务下，"
    "LLM 可能漏掉早期拆股事件（如 TSLA 2020-08 那次），输出的复权倍数会不稳定，"
    "用户无法判断答案对错。本工具返回的是 yfinance 历史数据 + SQLite 缓存，"
    "对同一 symbol 任何时刻调用结果一致。\n\n"
    "返回字段：\n"
    "- actions: 列表，每项 {action_type, date, ratio, factor}，按日期升序\n"
    "  - action_type='split'：factor>1 普通拆股（5.0 = 5:1），factor<1 反向拆股\n"
    "  - action_type='dividend'：factor 是每股分红金额\n"
    "- splits_count: 拆股次数\n"
    "- cumulative_split_factor: 累计拆股因子（用于全期复权：原价 / 该因子 = 复权后价）\n"
    "- source: 'yfinance' / 'cache' / 'stale_cache' / 'error'\n\n"
    "参数 symbol 规则：美股直接写代码（TSLA / NVDA），A 股加后缀（600519.SS），"
    "港股 4 位 + .HK（0700.HK，不加前导零）。"
)


@app.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="get_corporate_actions",
            description=DESCRIPTION_GET,
            inputSchema={
                "type": "object",
                "properties": {
                    "symbol": {
                        "type": "string",
                        "description": "规范股票代码，如 TSLA / 600519.SS / 0700.HK",
                    },
                    "include_dividends": {
                        "type": "boolean",
                        "description": (
                            "是否包含历史股息。默认 False（股息列表通常很长，"
                            "且与拆股复权判断不直接相关）"
                        ),
                    },
                },
                "required": ["symbol"],
            },
        ),
    ]


@app.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    if name == "get_corporate_actions":
        result = get_corporate_actions(
            symbol=arguments["symbol"],
            include_dividends=bool(arguments.get("include_dividends", False)),
        )
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
    _init_schema()
    print(
        "[corporate_actions_server] starting (yfinance + SQLite cache, TTL=24h)",
        file=sys.stderr,
        flush=True,
    )
    async with stdio_server() as (read_stream, write_stream):
        await app.run(
            read_stream,
            write_stream,
            app.create_initialization_options(),
        )


if __name__ == "__main__":
    asyncio.run(main())
