"""One company desk: review → match → dual approve → seal → passport."""

from __future__ import annotations

from paydesk.analyst import ask, open_books, paid_rupees, record_payment
from paydesk.auditlog import AuditLog
from paydesk.books import FINANCE_ID, INVOICES, VENDORS, by_id, vendor_by_id
from paydesk.gates import check_sentence, gate_claim
from paydesk.match import three_way
from paydesk.memory import FailureSink
from paydesk.policy import POLICY, dual_required
from paydesk.release import PaymentRail


def release_sentence(invoice: dict, rupees: int) -> str:
    return f"Release invoice {invoice['invoice_id']} to {invoice['vendor']} for INR {rupees}."


STAGES = (
    "unread",
    "blocked",
    "ready",
    "awaiting_finance",
    "settled",
)


class Desk:
    def __init__(self, db_path=None) -> None:
        self.db_path = db_path
        self.engine = open_books(db_path)
        self.rail = PaymentRail()
        self.audit = AuditLog()
        self.memory = FailureSink()
        self.reviews: dict[str, dict] = {}
        self.receipts: dict[str, dict] = {}
        self.stages: dict[str, str] = {inv["invoice_id"]: "unread" for inv in INVOICES}
        self.clerk_confirmed: set[str] = set()
        self.finance_approved: set[str] = set()
        self.actor = "clerk.meera"
        for payment in __import__("paydesk.books", fromlist=["SETTLED"]).SETTLED:
            self.stages[payment["invoice_id"]] = "settled"
        self.audit.record("desk.boot", actor="system", opening_rupees=POLICY["opening_rupees"])

    def set_actor(self, actor_id: str) -> dict:
        if actor_id not in POLICY["roles"]:
            raise KeyError(actor_id)
        self.actor = actor_id
        self.audit.record("actor.switch", actor=actor_id, role=POLICY["roles"][actor_id]["role"])
        return {"actor": actor_id, **POLICY["roles"][actor_id]}

    def invoices(self) -> list[dict]:
        rows = []
        for invoice in INVOICES:
            public = {
                key: value
                for key, value in invoice.items()
                if key not in {"evidence", "lines"}
            }
            review = self.reviews.get(invoice["invoice_id"])
            public["releasable"] = bool(review and review["releasable"])
            public["decision"] = review["truthgraph"]["decision"] if review else None
            public["stage"] = self.stages.get(invoice["invoice_id"], "unread")
            public["settled"] = public["stage"] == "settled"
            public["match_score"] = review["match"]["score"] if review else None
            public["vendor_status"] = vendor_by_id(invoice["vendor_id"])["status"]
            public["dual_required"] = dual_required(invoice["po_rupees"])
            rows.append(public)
        return rows

    def review(self, invoice_id: str) -> dict:
        invoice = by_id(invoice_id)
        vendor = vendor_by_id(invoice["vendor_id"])
        match = three_way(invoice)
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
        amounts_match = match["matched"]
        needs_dual = dual_required(invoice["po_rupees"])
        tools = ["promptgate.check", "truthgraph.gate", "analyst.select", "match.three_way"]

        gate_ok = (
            honest_gate["passed"]
            and truth["decision"] == "ALLOW"
            and already == 0
            and amounts_match
            and vendor["status"] not in POLICY["block_vendor_status"]
        )

        if invoice_id in self.rail._held or self.stages.get(invoice_id) == "settled":
            summary = "already settled"
            stage = "settled"
            releasable = False
        elif invoice["kind"] == "duplicate" or already > 0:
            summary = "blocked duplicate"
            stage = "blocked"
            releasable = False
        elif invoice["kind"] == "hold" or vendor["status"] in POLICY["block_vendor_status"]:
            summary = "blocked vendor hold"
            stage = "blocked"
            releasable = False
        elif invoice["kind"] == "partial" or not amounts_match:
            summary = "blocked amount mismatch" if not amounts_match else "blocked partial receipt"
            if invoice["kind"] == "partial":
                summary = "blocked partial receipt"
            stage = "blocked"
            releasable = False
        elif invoice["kind"] == "mismatch":
            summary = "blocked amount mismatch"
            stage = "blocked"
            releasable = False
        elif invoice["kind"] == "injection" and hostile and not hostile["passed"]:
            # Injection note fails PromptGate; PO sentence can still stand.
            if gate_ok:
                summary = "rejected injected amount; purchase order stands"
                stage = "ready"
                releasable = True
            else:
                summary = "rejected injected amount"
                stage = "blocked"
                releasable = False
        elif gate_ok:
            if needs_dual and invoice_id not in self.finance_approved:
                if invoice_id in self.clerk_confirmed:
                    summary = "awaiting finance approval"
                    stage = "awaiting_finance"
                    releasable = False
                else:
                    summary = "ready — dual approval required"
                    stage = "ready"
                    releasable = True  # clerk can confirm
            else:
                summary = "ready to release"
                stage = "ready"
                releasable = True
        else:
            summary = "blocked by gates"
            stage = "blocked"
            releasable = False

        if stage == "blocked":
            self.memory.record_block(
                invoice_id=invoice_id,
                reason=summary,
                tools=tools,
                output=summary,
            )

        self.stages[invoice_id] = stage
        result = {
            "invoice_id": invoice_id,
            "kind": invoice["kind"],
            "summary": summary,
            "stage": stage,
            "releasable": releasable,
            "needs_dual": needs_dual,
            "clerk_confirmed": invoice_id in self.clerk_confirmed,
            "finance_approved": invoice_id in self.finance_approved,
            "already_paid_rupees": already,
            "honest_sentence": honest,
            "promptgate": honest_gate,
            "promptgate_on_invoice_amount": naive_gate,
            "promptgate_on_injected_amount": hostile,
            "truthgraph": truth,
            "match": match,
            "vendor": vendor,
            "lines": invoice.get("lines") or [],
            "tools": tools,
            "receipt": self.receipts.get(invoice_id),
            "policy": {
                "dual_approval_rupees": POLICY["dual_approval_rupees"],
                "actor": self.actor,
            },
            "timeline": self.timeline(invoice_id),
        }
        self.reviews[invoice_id] = result
        self.audit.record(
            "invoice.reviewed",
            actor=self.actor,
            invoice_id=invoice_id,
            summary=summary,
            stage=stage,
            truthgraph=truth["decision"],
            match_score=match["score"],
        )
        return result

    def confirm(self, invoice_id: str, confirmed: bool) -> dict:
        """Clerk confirms release. High amounts wait for finance."""
        role = POLICY["roles"][self.actor]["role"]
        if role == "auditor":
            return {"ok": False, "error": "auditor_cannot_release"}
        review = self.reviews.get(invoice_id) or self.review(invoice_id)
        if not confirmed:
            return {"ok": False, "error": "confirmation_required", "tools": review["tools"]}
        if review["stage"] == "settled":
            return {"ok": False, "error": "already_settled"}
        if not review["releasable"] and review["stage"] not in {"ready", "awaiting_finance"}:
            return {"ok": False, "error": "not_releasable", "summary": review["summary"]}

        if review["needs_dual"] and invoice_id not in self.finance_approved:
            self.clerk_confirmed.add(invoice_id)
            self.stages[invoice_id] = "awaiting_finance"
            self.audit.record(
                "invoice.awaiting_finance",
                actor=self.actor,
                invoice_id=invoice_id,
                rupees=by_id(invoice_id)["po_rupees"],
            )
            review = self.review(invoice_id)
            return {
                "ok": True,
                "pending": True,
                "stage": "awaiting_finance",
                "summary": "awaiting finance approval",
                "review": review,
            }

        return self._commit(invoice_id, approver=self.actor)

    def approve(self, invoice_id: str, approved: bool) -> dict:
        role = POLICY["roles"][self.actor]["role"]
        if role != "finance":
            return {"ok": False, "error": "finance_role_required"}
        if not approved:
            self.audit.record("invoice.rejected", actor=self.actor, invoice_id=invoice_id)
            self.stages[invoice_id] = "blocked"
            return {"ok": False, "error": "rejected_by_finance"}
        if invoice_id not in self.clerk_confirmed and self.stages.get(invoice_id) != "awaiting_finance":
            # allow finance to approve after review if clerk already queued
            review = self.reviews.get(invoice_id) or self.review(invoice_id)
            if review["stage"] != "awaiting_finance":
                return {"ok": False, "error": "not_awaiting_finance", "stage": review["stage"]}
        self.finance_approved.add(invoice_id)
        self.audit.record("invoice.finance_approved", actor=self.actor, invoice_id=invoice_id)
        return self._commit(invoice_id, approver=FINANCE_ID)

    def _commit(self, invoice_id: str, *, approver: str) -> dict:
        invoice = by_id(invoice_id)
        review = self.reviews.get(invoice_id) or self.review(invoice_id)
        payment = self.rail.release(invoice, approver=approver)
        payment["tools"] = review["tools"] + payment.get("tools", [])
        payment["summary"] = (
            f"committed and verified INR {invoice['po_rupees']}"
            if payment.get("ok")
            else payment.get("error")
        )
        if payment.get("ok"):
            record_payment(
                self.engine,
                payment_id=f"PAY-{invoice_id.split('-')[-1]}",
                invoice_id=invoice_id,
                vendor=invoice["vendor"],
                rupees=invoice["po_rupees"],
            )
            self.receipts[invoice_id] = payment
            self.stages[invoice_id] = "settled"
            review["releasable"] = False
            review["summary"] = "already settled"
            review["stage"] = "settled"
            review["receipt"] = payment
            self.audit.record(
                "invoice.settled",
                actor=approver,
                invoice_id=invoice_id,
                rupees=invoice["po_rupees"],
                grant_id=payment.get("grant_id"),
                manifest_hash=payment.get("manifest_hash"),
            )
        else:
            self.audit.record(
                "invoice.release_failed",
                actor=approver,
                invoice_id=invoice_id,
                error=payment.get("error"),
            )
        return payment

    def release(self, invoice_id: str, confirmed: bool) -> dict:
        """Back-compat path used by tests and the simple API."""
        return self.confirm(invoice_id, confirmed)

    def ask(self, question: str) -> dict:
        result = ask(self.engine, question)
        self.audit.record(
            "ledger.asked",
            actor=self.actor,
            question=question[:200],
            success=bool(result.get("success")),
        )
        return result

    def balance_rupees(self) -> int:
        return self.rail.balance_rupees()

    def dashboard(self) -> dict:
        invoices = self.invoices()
        by_stage: dict[str, int] = {}
        for row in invoices:
            by_stage[row["stage"]] = by_stage.get(row["stage"], 0) + 1
        blocked = [row for row in invoices if row["stage"] == "blocked"]
        awaiting = [row for row in invoices if row["stage"] == "awaiting_finance"]
        open_exposure = sum(
            row["po_rupees"]
            for row in invoices
            if row["stage"] in {"unread", "ready", "awaiting_finance"}
        )
        return {
            "company": POLICY["company"],
            "site": POLICY["site"],
            "balance_rupees": self.balance_rupees(),
            "opening_rupees": POLICY["opening_rupees"],
            "by_stage": by_stage,
            "blocked_count": len(blocked),
            "awaiting_finance": awaiting,
            "open_exposure_rupees": open_exposure,
            "vendors": VENDORS,
            "dual_approval_rupees": POLICY["dual_approval_rupees"],
            "actor": self.actor,
            "roles": POLICY["roles"],
            "libraries": POLICY["libraries"],
            "failure_memory": {
                "enabled": self.memory.enabled,
                "path": str(self.memory.path) if self.memory.enabled else None,
            },
        }

    def timeline(self, invoice_id: str | None = None) -> list[dict]:
        desk_events = self.audit.list(invoice_id)
        protocol = self.rail.protocol_events(invoice_id)
        merged = []
        for event in desk_events:
            merged.append({"source": "desk", **event})
        for event in protocol:
            merged.append(
                {
                    "source": "karmasakshi",
                    "kind": event["event_type"],
                    "at": event["at"],
                    "actor": event.get("actor_id"),
                    "invoice_id": invoice_id,
                    "detail": event,
                }
            )
        merged.sort(key=lambda item: item.get("at") or "", reverse=True)
        return merged

    def passport(self, invoice_id: str) -> dict:
        found = self.rail.passport(invoice_id) or self.receipts.get(invoice_id)
        if not found:
            raise KeyError(invoice_id)
        return found

    def dossier(self, invoice_id: str) -> dict:
        review = self.reviews.get(invoice_id) or self.review(invoice_id)
        passport = self.rail.passport(invoice_id)
        return {
            "invoice": by_id(invoice_id),
            "vendor": vendor_by_id(by_id(invoice_id)["vendor_id"]),
            "review": review,
            "passport": passport,
            "timeline": self.timeline(invoice_id),
            "policy": POLICY,
        }
