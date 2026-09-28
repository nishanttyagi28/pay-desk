from pathlib import Path

import pytest

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
    assert ids == {"INV-2408", "INV-2414", "INV-2419"}


def test_duplicate_invoice_is_blocked(desk: Desk) -> None:
    review = desk.review("INV-2411")
    assert review["truthgraph"]["decision"] == "BLOCK"
    assert review["releasable"] is False
    assert review["already_paid_rupees"] == 94000
    payment = desk.release("INV-2411", confirmed=True)
    assert payment["ok"] is False
    assert desk.balance_rupees() == 1_000_000


def test_mismatched_amount_is_blocked(desk: Desk) -> None:
    review = desk.review("INV-2414")
    assert review["truthgraph"]["decision"] == "BLOCK"
    assert review["promptgate_on_invoice_amount"]["passed"] is False
    assert review["releasable"] is False


def test_injected_sentence_fails_and_the_purchase_order_amount_stands(desk: Desk) -> None:
    review = desk.review("INV-2419")
    assert review["promptgate_on_injected_amount"]["passed"] is False
    assert review["promptgate"]["passed"] is True
    assert review["truthgraph"]["decision"] == "ALLOW"
    assert "64000" in review["honest_sentence"]
    assert "INR 1" not in review["honest_sentence"]


def test_clean_invoice_pays_once_and_a_forged_amount_does_not(desk: Desk) -> None:
    review = desk.review("INV-2408")
    assert review["truthgraph"]["decision"] == "ALLOW"
    assert review["promptgate"]["passed"] is True
    assert review["releasable"] is True
    refused = desk.release("INV-2408", confirmed=False)
    assert refused["error"] == "confirmation_required"
    assert desk.balance_rupees() == 1_000_000

    paid = desk.release("INV-2408", confirmed=True)
    assert paid["ok"] is True
    assert paid["rupees"] == 186000
    assert paid["seal_verified"] is True
    assert paid["matched_expected"] is True
    assert desk.balance_rupees() == 1_000_000 - 186000

    again = desk.release("INV-2408", confirmed=True)
    assert again["ok"] is False
    assert again["error"] == "already_settled"
    assert desk.balance_rupees() == 814000
    settled = desk.review("INV-2408")
    assert settled["summary"] == "already settled"
    assert settled["releasable"] is False
    assert settled["receipt"]["rupees"] == 186000

    forged = desk.rail.forge(desk_invoice(desk, "INV-2408"), 1)
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


def desk_invoice(desk: Desk, invoice_id: str) -> dict:
    from paydesk.books import by_id

    return by_id(invoice_id)
