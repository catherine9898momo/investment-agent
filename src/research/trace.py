"""JSONL trace writer for research runs."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from src.research.models import ResearchRunState, to_jsonable, utc_now_iso


PROJECT_ROOT = Path(__file__).parent.parent.parent
TRACE_DIR = PROJECT_ROOT / "logs" / "research_traces"


class TraceLogger:
    def __init__(self, run: ResearchRunState, trace_dir: Path = TRACE_DIR) -> None:
        trace_dir.mkdir(parents=True, exist_ok=True)
        self.path = trace_dir / f"{run.run_id}.jsonl"
        run.trace_path = str(self.path)

    def append(self, event_type: str, payload: Any) -> None:
        """/**
         * 写入一条完整 JSONL trace 事件。
         *
         * @param event_type - 事件类型，例如 claim_verification 或 function_io。
         * @param payload - 任意可 JSON 序列化载荷，会完整写入，不做字段截断。
         *
         * @remarks 这里刻意不截断 JSON 内容，方便人工复盘关键验证链路的完整输入和输出。
         */
        """

        record = {
            "event_type": event_type,
            "timestamp": utc_now_iso(),
            "payload": to_jsonable(payload),
        }
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    def append_function_io(self, module: str, function: str, inputs: Any, output: Any) -> None:
        """/**
         * 写入标准化函数输入/输出 trace。
         *
         * @param module - Python 模块路径，例如 src.research.claim_verifier。
         * @param function - 函数名，例如 verify_synthesis_claims。
         * @param inputs - 本次函数调用的完整输入摘要或原始对象。
         * @param output - 本次函数调用的完整输出。
         *
         * @remarks payload.tag 使用 module.function，方便从 trace log 中定位具体模块和函数。
         */
        """

        self.append(
            "function_io",
            {
                "tag": f"{module}.{function}",
                "module": module,
                "function": function,
                "inputs": inputs,
                "output": output,
            },
        )

    def snapshot(self, run: ResearchRunState) -> None:
        self.append("run_snapshot", asdict(run))
