"""Score desk decisions with AgentEval."""

from __future__ import annotations

import sys

from paydesk.paths import AGENTEVAL

_READY = False


def _ensure() -> None:
    global _READY
    if _READY:
        return
    if not AGENTEVAL.is_dir():
        raise RuntimeError(f"AgentEval is not at {AGENTEVAL}. Run scripts/fetch_vendor.sh.")
    root = str(AGENTEVAL.parent)
    if root not in sys.path:
        sys.path.insert(0, root)
    _READY = True


def score(case_id: str, prompt: str, output: str, tools: list[str], ground_truth: str, required: list[str]) -> dict:
    _ensure()
    from agenteval.core.metrics import score_case
    from agenteval.core.schema import CaseResult, CorrectnessType, Expects, TestCase

    case = TestCase(
        id=case_id,
        prompt=prompt,
        expects=Expects(
            correctness_type=CorrectnessType.contains,
            ground_truth=ground_truth,
            must_call_tools=required,
            must_not_hallucinate=False,
        ),
    )
    result = CaseResult(
        case_id=case_id,
        prompt=prompt,
        final_answer=output,
        tools_called=list(tools),
        latency_ms=0.0,
    )
    scored = score_case(case, result, use_llm_judge=False)
    return {
        "library": "agenteval",
        "commit": "5a8e1cfcfbab41dda282d4db21813fae09dba196",
        "case_id": case_id,
        "correctness_pass": scored.correctness_pass,
        "tool_call_precision": scored.tool_call_precision,
        "tool_call_recall": scored.tool_call_recall,
        "output": output,
        "tools": list(tools),
    }
