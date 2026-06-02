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
        record = {
            "event_type": event_type,
            "timestamp": utc_now_iso(),
            "payload": to_jsonable(payload),
        }
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    def snapshot(self, run: ResearchRunState) -> None:
        self.append("run_snapshot", asdict(run))
