"""Record blocked payment attempts into AgentEval Failure Memory when available."""

from __future__ import annotations

import sys
from pathlib import Path

from paydesk.paths import AGENTEVAL, RESULTS


class FailureSink:
    def __init__(self) -> None:
        self.enabled = False
        self.path = RESULTS / "failure-memory.db"
        self._recorder = None
        self._ensure()

    def _ensure(self) -> None:
        if not AGENTEVAL.is_dir():
            return
        root = str(AGENTEVAL.parent)
        if root not in sys.path:
            sys.path.insert(0, root)
        try:
            from agenteval.failure_memory.recorder import FailureMemoryRecorder

            RESULTS.mkdir(parents=True, exist_ok=True)
            self._recorder = FailureMemoryRecorder(
                database_path=self.path,
                capture_content=True,
                jsonl_path=RESULTS / "traces.jsonl",
            )
            self.enabled = True
        except Exception:
            self.enabled = False
            self._recorder = None

    def record_block(self, *, invoice_id: str, reason: str, tools: list[str], output: str) -> dict:
        if not self.enabled or self._recorder is None:
            return {"recorded": False, "reason": "failure_memory_unavailable"}
        try:
            with self._recorder.trace(
                agent_name="pay-desk",
                prompt=f"Release {invoice_id}",
                attributes={
                    "invoice_id": invoice_id,
                    "failure_category": reason,
                    "correctness_pass": False,
                    "tools_called": list(tools),
                },
                source="local-desk",
                trace_id=f"paydesk-{invoice_id}-{reason}",
            ) as tr:
                for tool in tools:
                    tr.add_tool_call(tool, arguments={})
                tr.set_output(output)
                tr.set_status("failed")
            return {"recorded": True, "db": str(self.path), "invoice_id": invoice_id, "reason": reason}
        except Exception as exc:  # noqa: BLE001 — sink must not break the desk
            return {"recorded": False, "reason": str(exc)}
