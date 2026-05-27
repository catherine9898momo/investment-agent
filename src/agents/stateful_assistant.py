"""
stateful_assistant.py — W5 D1 ClaudeSDKClient stateful 长对话最小骨架

【目标】
跑通 3 轮 stateful 对话，验证 SDK 在 client 实例内跨 query 维护 messages。
对照 weekly_analyst.py 的 query() stateless 版，本文件是 stateful 版的最小对应物。

【今天 D1 边界】
不挂 hook、不挂压缩策略、3 轮 input 写死。骨架立住即停。
"""

import asyncio
import logging
from pathlib import Path

from claude_agent_sdk import ClaudeSDKClient, ClaudeAgentOptions
from claude_agent_sdk.types import (
    AssistantMessage,
    UserMessage,
    TextBlock,
    ToolUseBlock,
    ToolResultBlock,
    ResultMessage,
)

PROJECT_ROOT = Path(__file__).parent.parent.parent

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("stateful_assistant")

# 3 轮对话写死 —— 第 2/3 轮故意省略上下文，验证 SDK 是否"记得"前一轮
DIALOGUE_INPUTS = [
    "我持仓里有 TSLA 1000 股，成本价 $1200。帮我看下现在什么情况。",
    "那拆股事件呢？复权之后我到底是亏还是赚？",
    "如果还有 200 股 NVDA 成本 $40，整体浮盈浮亏算下来是多少？",
]


def build_options() -> ClaudeAgentOptions:
    return ClaudeAgentOptions(
        setting_sources=["project", "local"],
        cwd=str(PROJECT_ROOT),
        permission_mode="bypassPermissions",
        allowed_tools=[
            "mcp__investment-memory__list_portfolio",
            "mcp__investment-memory__get_preferences",
            "mcp__investment-finance__get_quote",
            "mcp__investment-finance__get_history",
            "mcp__investment-news__get_news",
            "mcp__investment-corporate-actions__get_corporate_actions",
        ],
        system_prompt=(
            "你是一个投资助手，会跨多轮对话累积持仓信息。"
            "涉及历史价位判断时务必先调 get_corporate_actions 拿拆股 ground truth。"
        ),
        # 5/25 锁 Sonnet 4.6 · 默认继承 CLI 全局 Opus 一天烧 $17,Sonnet ~5x 便宜
        # 且 4 策略对比只要求"同模型一致性"，不要求"用最强"
        model="claude-sonnet-4-6",
    )


def handle_message(msg, round_idx: int) -> None:
    """把一条 SDK message 打印成人可读摘要。"""
    if isinstance(msg, AssistantMessage):
        for block in msg.content:
            if isinstance(block, TextBlock):
                preview = block.text[:200].replace("\n", " ")
                log.info("R%d ← assistant.text: %s", round_idx, preview)
            elif isinstance(block, ToolUseBlock):
                log.info("R%d ← assistant.tool_use: %s(%s)", round_idx, block.name, str(block.input)[:80])
    elif isinstance(msg, UserMessage):
        content = msg.content if isinstance(msg.content, list) else []
        for block in content:
            if isinstance(block, ToolResultBlock):
                resp = str(block.content)[:120].replace("\n", " ")
                log.info("R%d ← tool_result: %s", round_idx, resp)
    elif isinstance(msg, ResultMessage):
        log.info(
            "R%d ── done  turns=%d  cost=$%.4f",
            round_idx,
            msg.num_turns,
            msg.total_cost_usd or 0,
        )


async def log_context_usage(client: ClaudeSDKClient, round_idx: int) -> None:
    """W5 策略 0 · 观测仪表盘：打印当前 context window 的 token 分布。

    `get_context_usage()` 等价于 CLI 里的 `/context` 命令——返回当前 messages
    数组（含 system prompt / tools / memory files / MCP / 对话历史）整体进入
    下一轮 LLM call 的 token 占用。messages 这一类是唯一会单调增长的桶，
    后续 W5 策略 A/B/C 都在压它。
    """
    usage = await client.get_context_usage()
    log.info(
        "R%d ── ctx  total=%d (%.1f%%)  max=%d  autoCompact=%s  threshold=%s",
        round_idx,
        usage["totalTokens"],
        usage["percentage"],
        usage["maxTokens"],
        usage["isAutoCompactEnabled"],
        usage.get("autoCompactThreshold"),
    )
    for cat in usage["categories"]:
        log.info(
            "R%d ── ctx.cat  %-20s = %6d tokens",
            round_idx,
            cat["name"],
            cat["tokens"],
        )


async def main() -> None:
    options = build_options()
    log.info("=== stateful_assistant: %d-round dialogue ===", len(DIALOGUE_INPUTS))

    async with ClaudeSDKClient(options=options) as client:
        for idx, user_input in enumerate(DIALOGUE_INPUTS, start=1):
            log.info("")
            log.info("R%d → user: %s", idx, user_input)

            await client.query(user_input)
            async for msg in client.receive_response():
                handle_message(msg, idx)

            # W5 策略 0 · 每轮收尾打印 context 使用情况
            await log_context_usage(client, idx)


if __name__ == "__main__":
    asyncio.run(main())
