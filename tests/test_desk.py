from pathlib import Path

import pytest

from paydesk.books import by_id
from paydesk.desk import Desk
from paydesk.scoring import score


@pytest.fixture
def desk(tmp_path: Path) -> Desk:
    return Desk(tmp_path / "books.db")


def test_write_sql_never_reaches_the_ledger(desk: Desk) -> None:
    refused = desk.ask("DELETE FROM payments")
    assert refused["success"] is False
    assert "forbidden" in refused["error"].lower()
    paid = desk.ask("How much have we already paid each vendor?")
    assert paid["success"] is True
    assert paid["rows"] == [{"vendor": "PackWell", "paid_rupees": 94000}]


def test_open_invoices_skip_the_settled_bill(desk: Desk) -> None:
    opened = desk.ask("Which invoices are still open?")
    ids = {row["invoice_id"] for row in opened["rows"]}
    assert "INV-2411" not in ids
    assert {"INV-2408", "INV-2414", "INV-2419", "INV-2420", "INV-2423"} <= ids


def test_duplicate_invoice_is_blocked(desk: Desk) -> None:
    review = desk.review("INV-2411")
    assert review["truthgraph"]["decision"] == "BLOCK"
    assert review["releasable"] is False
    assert review["stage"] == "settled"
    assert review["summary"] == "already settled"
    assert review["already_paid_rupees"] == 94000
    payment = desk.release("INV-2411", confirmed=True)
    assert payment["ok"] is False
    assert desk.balance_rupees() == 1_000_000


def test_mismatched_and_partial_and_hold_are_blocked(desk: Desk) -> None:
    mismatch = desk.review("INV-2414")
    assert mismatch["stage"] == "blocked"
    assert mismatch["match"]["matched"] is False
    partial = desk.review("INV-2420")
    assert partial["stage"] == "blocked"
    assert "partial" in partial["summary"]
    hold = desk.review("INV-2423")
    assert hold["stage"] == "blocked"
    assert hold["vendor"]["status"] == "hold"


def test_injected_sentence_fails_and_the_purchase_order_amount_stands(desk: Desk) -> None:
    review = desk.review("INV-2419")
    assert review["promptgate_on_injected_amount"]["passed"] is False
    assert review["promptgate"]["passed"] is True
    assert review["truthgraph"]["decision"] == "ALLOW"
    assert "64000" in review["honest_sentence"]
    assert "INR 1" not in review["honest_sentence"]


def test_clean_invoice_needs_finance_then_pays_once(desk: Desk) -> None:
    review = desk.review("INV-2408")
    assert review["truthgraph"]["decision"] == "ALLOW"
    assert review["promptgate"]["passed"] is True
    assert review["needs_dual"] is True
    assert review["releasable"] is True
    assert review["match"]["matched"] is True

    refused = desk.release("INV-2408", confirmed=False)
    assert refused["error"] == "confirmation_required"
    assert desk.balance_rupees() == 1_000_000

    pending = desk.release("INV-2408", confirmed=True)
    assert pending.get("pending") is True
    assert pending["stage"] == "awaiting_finance"
    assert desk.balance_rupees() == 1_000_000

    desk.set_actor("finance.arjun")
    paid = desk.approve("INV-2408", approved=True)
    assert paid["ok"] is True
    assert paid["rupees"] == 186000
    assert paid["seal_verified"] is True
    assert paid["matched_expected"] is True
    assert paid["authorized_by"] == "finance.arjun"
    assert "Action Passport" in (paid.get("passport_markdown") or "") or paid.get(
        "passport_markdown", ""
    ).startswith("# Action Passport")
    assert desk.balance_rupees() == 1_000_000 - 186000

    again = desk.release("INV-2408", confirmed=True)
    assert again["ok"] is False
    assert again["error"] in {"already_settled", "not_releasable"}
    assert desk.balance_rupees() == 814000
    settled = desk.review("INV-2408")
    assert settled["summary"] == "already settled"
    assert settled["stage"] == "settled"
    assert settled["receipt"]["rupees"] == 186000

    forged = desk.rail.forge(by_id("INV-2408"), 1)
    assert forged["ok"] is False
    assert desk.balance_rupees() == 814000

    scored = score(
        "clean-release",
        "Release INV-2408",
        paid["summary"],
        paid["tools"],
        "committed and verified INR 186000",
        ["promptgate.check", "truthgraph.gate", "analyst.select", "karmasakshi.commit"],
    )
    assert scored["correctness_pass"] is True
    assert scored["tool_call_recall"] == 1.0


def test_dashboard_and_reset_shape(desk: Desk) -> None:
    dash = desk.dashboard()
    assert dash["company"] == "Aravali Traders"
    assert dash["balance_rupees"] == 1_000_000
    assert "dual_approval_rupees" in dash
    assert len(dash["vendors"]) == 4
