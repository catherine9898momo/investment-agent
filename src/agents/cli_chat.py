"""Interactive CLI for the stateful investment assistant.

This is the usage-first entry point: keep one ClaudeSDKClient alive, let the
user ask real follow-up questions, and print context usage after each turn.
"""

import asyncio
import logging
from typing import Iterable

from claude_agent_sdk import ClaudeSDKClient
from claude_agent_sdk.types import (
    AssistantMessage,
    ResultMessage,
    TextBlock,
    ToolResultBlock,
    ToolUseBlock,
    UserMessage,
)

from src.agents.stateful_assistant import build_options, log_context_usage

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("cli_chat")

EXIT_COMMANDS = {"/exit", "/quit", "exit", "quit"}
CONTEXT_COMMANDS = {"/context", "context"}
HELP_COMMANDS = {"/help", "help"}


def print_help() -> None:
    print(
        "Commands:\n"
        "  /context  print current context usage\n"
        "  /help     show this help\n"
        "  /exit     quit\n"
    )


def iter_text_blocks(msg: AssistantMessage) -> Iterable[str]:
    for block in msg.content:
        if isinstance(block, TextBlock):
            yield block.text


def handle_message(msg, turn_idx: int) -> None:
    if isinstance(msg, AssistantMessage):
        text_parts = list(iter_text_blocks(msg))
        if text_parts:
            print("".join(text_parts), flush=True)
        for block in msg.content:
            if isinstance(block, ToolUseBlock):
                log.info("T%d tool_use: %s(%s)", turn_idx, block.name, str(block.input)[:120])
    elif isinstance(msg, UserMessage):
        content = msg.content if isinstance(msg.content, list) else []
        for block in content:
            if isinstance(block, ToolResultBlock):
                preview = str(block.content)[:160].replace("\n", " ")
                log.info("T%d tool_result: %s", turn_idx, preview)
    elif isinstance(msg, ResultMessage):
        log.info(
            "T%d done  turns=%d  cost=$%.4f",
            turn_idx,
            msg.num_turns,
            msg.total_cost_usd or 0,
        )


async def chat_loop() -> None:
    options = build_options()
    print("investment-agent CLI chat")
    print("Type /help for commands, /exit to quit.\n")

    async with ClaudeSDKClient(options=options) as client:
        turn_idx = 0
        while True:
            try:
                user_input = input("> ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\nbye.")
                return

            if not user_input:
                continue
            if user_input in EXIT_COMMANDS:
                print("bye.")
                return
            if user_input in HELP_COMMANDS:
                print_help()
                continue
            if user_input in CONTEXT_COMMANDS:
                await log_context_usage(client, turn_idx)
                continue

            turn_idx += 1
            await client.query(user_input)
            async for msg in client.receive_response():
                handle_message(msg, turn_idx)
            await log_context_usage(client, turn_idx)


if __name__ == "__main__":
    asyncio.run(chat_loop())
