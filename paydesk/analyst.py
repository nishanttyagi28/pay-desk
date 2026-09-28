"""Questions over the ledger, executed only through the analyst's SELECT guard."""

from __future__ import annotations

import sys

from sqlalchemy import text
from sqlalchemy.engine import Engine

from paydesk.books import INVOICES, SETTLED
from paydesk.paths import ANALYST, BOOKS_DB

_READY = False


def _ensure_analyst() -> None:
    global _READY
    if _READY:
        return
    if not ANALYST.is_dir():
        raise RuntimeError(f"Agentic Data Analyst is not at {ANALYST}. Run scripts/fetch_vendor.sh.")
    root = str(ANALYST)
    if root not in sys.path:
        sys.path.insert(0, root)
    _READY = True


def open_books(path=None) -> Engine:
    _ensure_analyst()
    from db.database import get_engine

    BOOKS_DB.parent.mkdir(parents=True, exist_ok=True)
    engine = get_engine(str(path or BOOKS_DB))
    with engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS invoices"))
        conn.execute(text("DROP TABLE IF EXISTS payments"))
        conn.execute(
            text(
                """
                CREATE TABLE invoices (
                    invoice_id TEXT PRIMARY KEY,
                    vendor TEXT,
                    po_id TEXT,
                    grn_id TEXT,
                    invoice_rupees INTEGER,
                    po_rupees INTEGER,
                    grn_rupees INTEGER,
                    kind TEXT
                )
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE TABLE payments (
                    payment_id TEXT PRIMARY KEY,
                    invoice_id TEXT,
                    vendor TEXT,
                    rupees INTEGER,
                    settled INTEGER
                )
                """
            )
        )
        for invoice in INVOICES:
            conn.execute(
                text(
                    """
                    INSERT INTO invoices (
                        invoice_id, vendor, po_id, grn_id,
                        invoice_rupees, po_rupees, grn_rupees, kind
                    ) VALUES (
                        :invoice_id, :vendor, :po_id, :grn_id,
                        :invoice_rupees, :po_rupees, :grn_rupees, :kind
                    )
                    """
                ),
                invoice,
            )
        for payment in SETTLED:
            conn.execute(
                text(
                    """
                    INSERT INTO payments (payment_id, invoice_id, vendor, rupees, settled)
                    VALUES (:payment_id, :invoice_id, :vendor, :rupees, :settled)
                    """
                ),
                payment,
            )
    return engine


def ask(engine: Engine, question: str) -> dict:
    """Turn a desk question into SQL, refuse writes, and run the SELECT."""
    _ensure_analyst()
    from agents.sql_agent import check_sql_covers_request, is_safe_select
    from db.database import execute_select_query

    sql, routed = _sql_for(question)
    if sql is None:
        from agents.sql_agent import generate_sql

        generated, err = generate_sql(question, engine)
        if err or not generated:
            return {
                "library": "agentic-data-analyst",
                "commit": "8fc22fa6e821507e8cc96d31d98f220c9f491054",
                "success": False,
                "error": err or "No SQL was produced.",
                "question": question,
            }
        sql, routed = generated, "generate_sql"
    safe, why = is_safe_select(sql)
    gaps = check_sql_covers_request(question, sql)
    if not safe:
        return {
            "library": "agentic-data-analyst",
            "commit": "8fc22fa6e821507e8cc96d31d98f220c9f491054",
            "success": False,
            "error": why,
            "sql": sql,
            "question": question,
            "guard": "is_safe_select",
        }
    frame = execute_select_query(engine, sql)
    rows = frame.to_dict(orient="records")
    return {
        "library": "agentic-data-analyst",
        "commit": "8fc22fa6e821507e8cc96d31d98f220c9f491054",
        "success": True,
        "question": question,
        "sql": sql,
        "route": routed,
        "rows": rows,
        "row_count": len(rows),
        "self_check": gaps,
        "guard": "is_safe_select",
    }


def paid_rupees(engine: Engine, invoice_id: str) -> int:
    _ensure_analyst()
    from agents.sql_agent import is_safe_select
    from db.database import execute_select_query

    sql = (
        "SELECT COALESCE(SUM(rupees), 0) AS paid_rupees "
        "FROM payments WHERE invoice_id = :invoice_id AND settled = 1"
    )
    safe, why = is_safe_select(sql)
    if not safe:
        raise RuntimeError(why)
    frame = execute_select_query(engine, sql, {"invoice_id": invoice_id})
    return int(frame.iloc[0]["paid_rupees"])


def _sql_for(question: str) -> tuple[str | None, str]:
    stripped = question.strip()
    lowered = stripped.lower()
    from agents.sql_agent import FORBIDDEN_KEYWORDS

    if (
        lowered.startswith("select")
        or lowered.startswith("with")
        or FORBIDDEN_KEYWORDS.search(stripped)
    ):
        return stripped, "clerk_sql"
    if "open" in lowered or "unpaid" in lowered:
        return (
            "SELECT i.invoice_id, i.vendor, i.invoice_rupees "
            "FROM invoices i "
            "WHERE NOT EXISTS ("
            "  SELECT 1 FROM payments p "
            "  WHERE p.invoice_id = i.invoice_id AND p.settled = 1"
            ") "
            "ORDER BY i.invoice_id",
            "open_invoices",
        )
    if "paid" in lowered or "payment" in lowered:
        return (
            "SELECT vendor, SUM(rupees) AS paid_rupees "
            "FROM payments WHERE settled = 1 "
            "GROUP BY vendor ORDER BY paid_rupees DESC",
            "paid_by_vendor",
        )
    return None, ""
