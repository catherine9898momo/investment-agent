"""
weekly_analyst.py — W3 单 Agent 投资周报生成器

【最终目标】
cron 每周一早 8 点触发，自动跑一遍持仓 → 输出 reports/YYYY-Www.md 周报。
解决「每周手动打开 Claude Desktop 跑 Case D' 那套」的痛点。

【与 Case D' 的对应关系】
Case D' 在 Claude Desktop 里一句话触发 7 次工具调用。
本脚本把同样的 prompt 改写成「无人值守 + Python 消费 message stream」的形态。

【cron 配置（每周一 08:00）】
  0 8 * * 1 cd /Users/mtdp/ai/projects/investment-agent && venv/bin/python -m src.agents.weekly_analyst >> logs/weekly_analyst.log 2>&1
"""

import asyncio
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from claude_agent_sdk import query, ClaudeAgentOptions
from claude_agent_sdk.types import (
    AssistantMessage,
    TextBlock,
    ResultMessage,
    PreToolUseHookInput,
    PostToolUseHookInput,
    HookContext,
    HookMatcher,
    PreToolUseHookSpecificOutput,
    PostToolUseHookSpecificOutput,
)

# ============================================================
# 配置区
# ============================================================

TARGET_SYMBOL = "TSLA"

PROJECT_ROOT = Path(__file__).parent.parent.parent
REPORTS_DIR = PROJECT_ROOT / "reports"
LOGS_DIR = PROJECT_ROOT / "logs"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("weekly_analyst")


# ============================================================
# Hook 系统 — 解耦于主循环，主循环零改动
# ============================================================

# 每次 query() 跑完后用来统计的容器，hook 只写这里，主循环只读这里
_tool_log: list[dict] = []


async def pre_tool_hook(
    input: PreToolUseHookInput, session_id: str | None, ctx: HookContext
) -> PreToolUseHookSpecificOutput | None:
    """工具调用前：记录工具名和入参，打印进度。"""
    log.info("→ tool_use  %s  %s", input["tool_name"], json.dumps(input["tool_input"], ensure_ascii=False))
    _tool_log.append({"tool": input["tool_name"], "input": input["tool_input"]})
    return PreToolUseHookSpecificOutput(hookEventName="PreToolUse")


async def post_tool_hook(
    input: PostToolUseHookInput, session_id: str | None, ctx: HookContext
) -> PostToolUseHookSpecificOutput:
    """工具调用后：记录响应摘要（只取前 120 字符，避免日志爆炸）。"""
    resp_preview = str(input.get("tool_response", ""))[:120]
    log.info("← tool_result %s  %s…", input["tool_name"], resp_preview)
    return PostToolUseHookSpecificOutput(hookEventName="PostToolUse")


# ============================================================
# 主逻辑
# ============================================================

async def main() -> None:
    # --- 1) 配置 --------------------------------------------------
    options = ClaudeAgentOptions(
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
        # hook 系统挂在循环外部，主循环不感知
        # 每个事件对应 list[HookMatcher]，matcher=None 表示匹配所有工具
        hooks={
            "PreToolUse": [HookMatcher(hooks=[pre_tool_hook])],
            "PostToolUse": [HookMatcher(hooks=[post_tool_hook])],
        },
    )

    # --- 2) Prompt ------------------------------------------------
    prompt = f"""你是一个投资周报助手。请为我持仓中的 {TARGET_SYMBOL} 生成一份本周周报。

请按以下步骤工作：
1. 从持仓库查出 {TARGET_SYMBOL} 的当前持有数量和成本价
2. 查询 {TARGET_SYMBOL} 的最新价格和最近一周价格走势
3. 拉取 {TARGET_SYMBOL} 最近一周的相关新闻（最多 5 条）
4. 综合以上信息，输出一份结构化周报，包含：
   - 持仓概览（数量 / 成本 / 当前价 / 浮盈浮亏）
   - 一周价格走势（高低点 / 波动幅度）
   - 关键新闻摘要（利好 / 利空各列）
   - 综合建议（持有 / 加仓 / 减仓 / 观望，并说明理由）

注意：如果涉及历史价位判断（例如成本价远高于当前价），请先核对是否存在拆股、合并等公司行动事件。
"""

    # --- 3) 消费 stream -------------------------------------------
    log.info("=== weekly_analyst: analyzing %s ===", TARGET_SYMBOL)
    text_buffer: list[str] = []

    async for message in query(prompt=prompt, options=options):
        if isinstance(message, AssistantMessage):
            for block in message.content:
                if isinstance(block, TextBlock):
                    text_buffer.append(block.text)
        elif isinstance(message, ResultMessage):
            log.info(
                "done  turns=%d  cost=$%.4f  tools=%d",
                message.num_turns,
                message.total_cost_usd or 0,
                len(_tool_log),
            )

    # --- 4) 写文件 -----------------------------------------------
    report_text = "".join(text_buffer)
    if not report_text:
        log.error("no text collected — aborting file write")
        return

    now = datetime.now(timezone.utc)
    # ISO week: 2026-W21
    week_label = f"{now.year}-W{now.isocalendar().week:02d}"
    REPORTS_DIR.mkdir(exist_ok=True)
    report_path = REPORTS_DIR / f"{week_label}.md"

    report_path.write_text(report_text, encoding="utf-8")
    log.info("report written → %s", report_path)


if __name__ == "__main__":
    asyncio.run(main())
