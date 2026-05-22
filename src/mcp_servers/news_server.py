"""News MCP Server — Google News RSS 拉取公司/股票相关新闻

工具：
- get_news(query, days=7, lang="en")  按关键词拉新闻，过滤近 N 天

数据源：Google News Search RSS
    https://news.google.com/rss/search?q=<query>&hl=<lang-region>&gl=<region>&ceid=<region>:<lang>

设计要点：
- 用 query（关键词）而不是 symbol（代码）作为参数——Google News 是自然语言搜索引擎，传公司名召回比传 ticker 高
- 双语支持：lang=en 拉英文新闻、lang=zh 拉中文新闻
- 去重：按 link
- 时间过滤：按 entry.published_parsed，过滤 cutoff 之前的
- 截断：最多 20 条，防止 LLM 上下文爆炸

依赖：feedparser
"""

import asyncio
import json
import sys
import time
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import quote

import feedparser

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent


app = Server("investment-news")


# 语言 → (hl, gl, ceid_lang) 三元组
LANG_TABLE: dict[str, tuple[str, str, str]] = {
    "en": ("en-US", "US", "en"),
    "zh": ("zh-CN", "CN", "zh-Hans"),
}


def _build_rss_url(query: str, lang: str) -> str:
    """构造 Google News Search RSS URL。"""
    hl, gl, ceid_lang = LANG_TABLE.get(lang, LANG_TABLE["en"])
    q = quote(query)
    return f"https://news.google.com/rss/search?q={q}&hl={hl}&gl={gl}&ceid={gl}:{ceid_lang}"


def _extract_source(entry: Any) -> str:
    """Google News 把发布媒体名放在 entry.source.title。"""
    src = getattr(entry, "source", None)
    if src is None:
        return ""
    return getattr(src, "title", "") or ""


def _fetch_news(query: str, days: int, lang: str) -> dict[str, Any]:
    """拉新闻并按时间/去重过滤。失败返回 error 字段。"""
    if not query.strip():
        return {"query": query, "error": "empty_query"}
    if days <= 0:
        return {"query": query, "error": "days must be > 0"}

    url = _build_rss_url(query, lang)

    try:
        feed = feedparser.parse(url)
    except Exception as e:
        return {
            "query": query,
            "lang": lang,
            "error": f"fetch_failed: {type(e).__name__}: {e}",
        }

    # feedparser 在网络错误 / 解析失败时也不抛异常，要看 bozo 标志
    if feed.bozo and not feed.entries:
        return {
            "query": query,
            "lang": lang,
            "error": f"parse_failed: {feed.bozo_exception}",
        }

    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    items: list[dict[str, Any]] = []
    seen_links: set[str] = set()

    for entry in feed.entries:
        link = entry.get("link", "")
        if not link or link in seen_links:
            continue
        seen_links.add(link)

        # 时间过滤
        pub_struct = entry.get("published_parsed")
        if pub_struct is None:
            # 没有时间字段的条目不要——可能是 feed 结构异常
            continue
        pub_dt = datetime.fromtimestamp(time.mktime(pub_struct), tz=timezone.utc)
        if pub_dt < cutoff:
            # entries 按时间倒序，遇到第一条过期即可中断
            break

        items.append({
            "title": entry.get("title", "").strip(),
            "link": link,
            "published": pub_dt.isoformat(),
            "source": _extract_source(entry),
        })

        if len(items) >= 20:
            break

    return {
        "query": query,
        "lang": lang,
        "days": days,
        "count": len(items),
        "items": items,
    }


# ---------------------------------------------------------------------------
# MCP 接口
# ---------------------------------------------------------------------------

@app.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="get_news",
            description=(
                "通过 Google News 拉取关于公司/股票/关键词的最新新闻。\n\n"
                "用户问'XX 最近有什么新闻'、'XX 最新动态'、'XX 涨/跌的原因'、"
                "'最近发生了什么'等问题时调用。\n\n"
                "参数 query 是**自然语言关键词**，不是股票代码：\n"
                "- 美股建议传公司英文名，如 'NVIDIA'、'Apple'、'Tesla'（召回比 'NVDA' 更准）\n"
                "- A 股传中文公司名，如 '贵州茅台'、'宁德时代'\n"
                "- 港股可以中英文都行，如 '腾讯' 或 'Tencent'\n\n"
                "参数 lang 选择新闻语言：\n"
                "- 英文公司 / 美股 → 传 'en'\n"
                "- 中文公司 / A 股 / 港股中文报道 → 传 'zh'\n\n"
                "默认 7 天回看，建议 1-30 天。返回最多 20 条按时间倒序。"
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "公司名或关键词，如 NVIDIA / 贵州茅台 / Tencent",
                    },
                    "days": {
                        "type": "integer",
                        "description": "回看天数（自然日），建议 1-30",
                        "minimum": 1,
                        "maximum": 30,
                    },
                    "lang": {
                        "type": "string",
                        "enum": ["en", "zh"],
                        "description": "新闻语言：en=英文新闻，zh=中文新闻",
                    },
                },
                "required": ["query"],
            },
        ),
    ]


@app.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    if name == "get_news":
        result = _fetch_news(
            query=arguments["query"],
            days=int(arguments.get("days", 7)),
            lang=arguments.get("lang", "en"),
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
    print("[news_server] starting (Google News RSS backend)", file=sys.stderr, flush=True)
    async with stdio_server() as (read_stream, write_stream):
        await app.run(
            read_stream,
            write_stream,
            app.create_initialization_options(),
        )


if __name__ == "__main__":
    asyncio.run(main())
