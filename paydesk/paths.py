from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VENDOR = ROOT / "vendor"
DATA = ROOT / "data"
RESULTS = ROOT / "eval" / "results"

TRUTHGRAPH = VENDOR / "truthgraph"
PROMPTGATE = VENDOR / "promptgate"
ANALYST = VENDOR / "agentic-data-analyst"
AGENTEVAL = VENDOR / "agenteval"
BOOKS_DB = DATA / "books.db"
