"""One invoice, five libraries, one decision."""

from __future__ import annotations

from paydesk.analyst import ask, open_books, paid_rupees
from paydesk.books import INVOICES, by_id
from paydesk.gates import check_sentence, gate_claim
from paydesk.release import PaymentRail


def release_sentence(invoice: dict, rupees: int) -> str:
    return f"Release invoice {invoice['invoice_id']} to {invoice['vendor']} for INR {rupees}."


class Desk:
    def __init__(self, db_path=None) -> None:
        self.engine = open_books(db_path)
        self.rail = PaymentRail()
        self.reviews: dict[str, dict] = {}
        self.receipts: dict[str, dict] = {}

    def invoices(self) -> list[dict]:
        rows = []
        for invoice in INVOICES:
            public = {key: value for key, value in invoice.items() if key != "evidence"}
            review = self.reviews.get(invoice["invoice_id"])
            public["releasable"] = bool(review and review["releasable"])
            public["decision"] = review["truthgraph"]["decision"] if review else None
            public["settled"] = invoice["invoice_id"] in self.rail._held
            rows.append(public)
        return rows

    def review(self, invoice_id: str) -> dict:
        invoice = by_id(invoice_id)
        honest = release_sentence(invoice, invoice["po_rupees"])
        naive = release_sentence(invoice, invoice["invoice_rupees"])
        prompt = (
            f"Write the payment sentence for {invoice['invoice_id']}. "
            f"The amount must be the purchase order amount, INR {invoice['po_rupees']}."
        )
        honest_gate = check_sentence(prompt, str(invoice["po_rupees"]), honest)
        naive_gate = check_sentence(prompt, str(invoice["po_rupees"]), naive)
        hostile = None
        if invoice["kind"] == "injection":
            hostile = check_sentence(
                prompt,
                str(invoice["po_rupees"]),
                release_sentence(invoice, 1),
            )
        truth = gate_claim(invoice["claim"], invoice["evidence"])
        already = paid_rupees(self.engine, invoice_id)
        amounts_match = invoice["invoice_rupees"] == invoice["po_rupees"] == invoice["grn_rupees"]
        releasable = (
            honest_gate["passed"]
            and truth["decision"] == "ALLOW"
            and already == 0
            and amounts_match
        )
        tools = ["promptgate.check", "truthgraph.gate", "analyst.select"]
        if invoice["kind"] == "duplicate":
            summary = "blocked duplicate"
        elif invoice["kind"] == "mismatch" or not amounts_match or not naive_gate["passed"]:
            summary = "blocked amount mismatch" if not amounts_match else "ready"
        elif invoice["kind"] == "injection":
            summary = "rejected injected amount; purchase order stands"
        else:
            summary = "ready to release"
        if releasable and invoice["kind"] == "clean":
            summary = "ready to release"
        if invoice_id in self.rail._held:
            releasable = False
            summary = "already settled"
        result = {
            "invoice_id": invoice_id,
            "kind": invoice["kind"],
            "summary": summary,
            "releasable": releasable,
            "already_paid_rupees": already,
            "honest_sentence": honest,
            "promptgate": honest_gate,
            "promptgate_on_invoice_amount": naive_gate,
            "promptgate_on_injected_amount": hostile,
            "truthgraph": truth,
            "tools": tools,
            "receipt": self.receipts.get(invoice_id),
        }
        self.reviews[invoice_id] = result
        return result

    def release(self, invoice_id: str, confirmed: bool) -> dict:
        invoice = by_id(invoice_id)
        review = self.reviews.get(invoice_id) or self.review(invoice_id)
        if not confirmed:
            return {"ok": False, "error": "confirmation_required", "tools": review["tools"]}
        if not review["releasable"] and invoice_id not in self.rail._held:
            return {
                "ok": False,
                "error": "not_releasable",
                "summary": review["summary"],
                "tools": review["tools"],
            }
        payment = self.rail.release(invoice)
        payment["tools"] = review["tools"] + payment.get("tools", [])
        payment["summary"] = (
            f"committed and verified INR {invoice['po_rupees']}"
            if payment.get("ok")
            else payment.get("error")
        )
        if payment.get("ok"):
            self.receipts[invoice_id] = payment
            review["releasable"] = False
            review["summary"] = "already settled"
            review["receipt"] = payment
        return payment

    def ask(self, question: str) -> dict:
        return ask(self.engine, question)

    def balance_rupees(self) -> int:
        return self.rail.balance_rupees()
