"""PromptGate and TruthGraph, called as those projects shipped them."""

from __future__ import annotations

import json
import subprocess
import sys

from paydesk.paths import PROMPTGATE, TRUTHGRAPH

_TRUTH_READY = False


def _ensure_truthgraph() -> None:
    global _TRUTH_READY
    if _TRUTH_READY:
        return
    if not TRUTHGRAPH.is_dir():
        raise RuntimeError(f"TruthGraph is not at {TRUTHGRAPH}. Run scripts/fetch_vendor.sh.")
    root = str(TRUTHGRAPH)
    if root not in sys.path:
        sys.path.insert(0, root)
    _TRUTH_READY = True


def check_sentence(prompt: str, expect_contains: str, output: str) -> dict:
    """Score one release sentence with PromptGate's contains rule."""
    if not PROMPTGATE.is_dir():
        raise RuntimeError(f"PromptGate is not at {PROMPTGATE}. Run scripts/fetch_vendor.sh.")
    code = (
        "import json,sys\n"
        "from app.eval import run_case\n"
        "from app.models import PromptCase\n"
        "raw=json.loads(sys.stdin.read())\n"
        "case=PromptCase(id='desk', prompt=raw['prompt'], expect_contains=raw['expect'])\n"
        "print(json.dumps(run_case(case, raw['output'], 'contains')))\n"
    )
    completed = subprocess.run(
        [sys.executable, "-c", code],
        input=json.dumps(
            {"prompt": prompt, "expect": expect_contains, "output": output}
        ),
        text=True,
        capture_output=True,
        cwd=str(PROMPTGATE),
        env={**dict(**{k: v for k, v in __import__("os").environ.items()}), "PYTHONPATH": str(PROMPTGATE)},
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.strip() or "PromptGate failed")
    result = json.loads(completed.stdout)
    return {
        "library": "promptgate",
        "commit": "9f74eb567a71cf360ebc6d1ec079f77e88f871f3",
        "passed": bool(result.get("passed")),
        "expect_contains": expect_contains,
        "output": output,
        "prompt": prompt,
    }


def gate_claim(claim: str, evidence: list[tuple[str, str, float]]) -> dict:
    """ALLOW, REVIEW, or BLOCK from TruthGraph's agent_tool_gate."""
    _ensure_truthgraph()
    from app.models.evidence import Evidence
    from app.services.gate import gate

    items = [
        Evidence(text=text, source=source, reliability=reliability)
        for text, source, reliability in evidence
    ]
    result = gate(
        claim,
        items,
        policy_id="agent_tool_gate",
        decompose=False,
        use_registry=False,
    )
    return {
        "library": "truthgraph",
        "commit": "2ac10fbd8d50a444da9151bd23d45711d63f627f",
        "policy_id": result.policy_id,
        "decision": result.decision,
        "verdict": result.verdict,
        "confidence": round(float(result.confidence), 3),
        "reasons": list(result.reasons),
        "claim": claim,
    }
