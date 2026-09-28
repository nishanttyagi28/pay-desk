"""Seal a vendor payment with KarmaSakshi and refuse a second debit."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from karmasakshi.adapters.payment_simulator import (
    PaymentRequest,
    PaymentSimulator,
    PaymentSimulatorAdapter,
)
from karmasakshi.adapters.registry import build_reference_registry
from karmasakshi.audit.journal import AuditJournal
from karmasakshi.crypto import Keyring, generate_signing_key
from karmasakshi.domain.common import MonetaryAmount, Principal
from karmasakshi.domain.enums import PrincipalType
from karmasakshi.engine.context import EngineContext
from karmasakshi.engine.core import KarmaSakshiEngine
from karmasakshi.errors import GrantExhaustedError, KarmaSakshiError
from karmasakshi.grants.model import ScopeConstraints
from karmasakshi.passports.generator import build_passport
from karmasakshi.passports.render import render_passport_markdown
from karmasakshi.stores.memory import InMemoryGrantStore

from paydesk.books import (
    AGENT_ID,
    AGENT_NAME,
    CLERK_ID,
    CLERK_NAME,
    FINANCE_ID,
    FINANCE_NAME,
    OPENING_RUPEES,
    OPERATING_ACCOUNT,
)


class PaymentRail:
    def __init__(self) -> None:
        self.simulator = PaymentSimulator()
        self.simulator.fund_account(OPERATING_ACCOUNT, OPENING_RUPEES * 100)
        self.adapter = PaymentSimulatorAdapter(self.simulator)
        self.key = generate_signing_key("aravali-finance")
        self.audit = AuditJournal()
        self.engine = KarmaSakshiEngine(
            EngineContext(
                keyring=Keyring([self.key.verification_key()]),
                grant_store=InMemoryGrantStore(),
                audit=self.audit,
                clock=self._clock(),
                adapter_registry=build_reference_registry(),
            )
        )
        self.clerk = Principal(
            principal_id=CLERK_ID, principal_type=PrincipalType.HUMAN, display_name=CLERK_NAME
        )
        self.finance = Principal(
            principal_id=FINANCE_ID, principal_type=PrincipalType.HUMAN, display_name=FINANCE_NAME
        )
        self.agent = Principal(
            principal_id=AGENT_ID, principal_type=PrincipalType.AGENT, display_name=AGENT_NAME
        )
        self._held: dict[str, tuple] = {}
        self._passports: dict[str, dict] = {}

    def balance_rupees(self) -> int:
        return self.simulator.get_balance(OPERATING_ACCOUNT) // 100

    def release(self, invoice: dict, *, approver: str = CLERK_ID) -> dict:
        """Prepare, seal, authorize, commit, and verify one exact amount."""
        held = self._held.get(invoice["invoice_id"])
        if held is not None:
            sealed, grant = held
            try:
                self.engine.commit(sealed, grant, self.adapter, context=None)
            except GrantExhaustedError as exc:
                return {
                    "ok": False,
                    "error": "already_settled",
                    "detail": str(exc),
                    "balance_rupees": self.balance_rupees(),
                    "tools": ["karmasakshi.commit"],
                }
            return {
                "ok": False,
                "error": "replay_unexpected",
                "balance_rupees": self.balance_rupees(),
                "tools": ["karmasakshi.commit"],
            }

        issuer = self.finance if approver == FINANCE_ID else self.clerk
        request = self._request(invoice, invoice["po_rupees"])
        tools = [
            "karmasakshi.prepare",
            "karmasakshi.seal",
            "karmasakshi.authorize",
            "karmasakshi.commit",
            "karmasakshi.verify",
            "karmasakshi.passport",
        ]
        manifest = self.engine.prepare(self.adapter, request, context=None)
        sealed = self.engine.seal(manifest, self.key)
        now = datetime.now(timezone.utc)
        grant = self.engine.authorize(
            sealed,
            issuer=issuer,
            subject=self.agent,
            audience=(self.adapter.adapter_id,),
            allowed_effect_types=(manifest.effect_type,),
            scope=ScopeConstraints(
                max_amount=MonetaryAmount(currency="INR", minor_units=invoice["po_rupees"] * 100),
                recipients=(invoice["vendor_account"],),
            ),
            not_before=now - timedelta(minutes=1),
            expires_at=now + timedelta(hours=2),
            signing_key=self.key,
        )
        commit = self.engine.commit(sealed, grant, self.adapter, context=None)
        proof = self.engine.verify(manifest, commit, self.adapter, context=None)
        passport = build_passport(
            sealed=sealed,
            keyring=self.engine.context.keyring,
            audit=self.audit,
            lifecycle_state="verified",
            grant=grant,
            grant_store=self.engine.context.grant_store,
            commit_result=commit,
            outcome_proof=proof,
        )
        markdown = render_passport_markdown(passport)
        payload = {
            "ok": bool(
                commit.success and proof.matched_expected and passport.verification.seal_verified
            ),
            "invoice_id": invoice["invoice_id"],
            "rupees": invoice["po_rupees"],
            "beneficiary": invoice["vendor_account"],
            "manifest_id": manifest.manifest_id,
            "manifest_hash": manifest.canonical_hash(),
            "grant_id": grant.grant_id,
            "authorized_by": issuer.principal_id,
            "seal_verified": passport.verification.seal_verified,
            "grant_verified": passport.verification.grant_verified,
            "matched_expected": proof.matched_expected,
            "lifecycle_state": passport.lifecycle_state,
            "passport_markdown": markdown,
            "balance_rupees": self.balance_rupees(),
            "tools": tools,
        }
        self._held[invoice["invoice_id"]] = (sealed, grant)
        self._passports[invoice["invoice_id"]] = payload
        return payload

    def passport(self, invoice_id: str) -> dict | None:
        return self._passports.get(invoice_id)

    def forge(self, invoice: dict, rupees: int) -> dict:
        """Try to commit a different amount with the grant that sealed the real one."""
        held = self._held.get(invoice["invoice_id"])
        if held is None:
            return {"ok": False, "error": "nothing_to_forge"}
        _sealed, grant = held
        request = self._request(invoice, rupees, idem=f"forge-{invoice['invoice_id']}-{rupees}")
        manifest = self.engine.prepare(self.adapter, request, context=None)
        forged = self.engine.seal(manifest, self.key)
        try:
            self.engine.commit(forged, grant, self.adapter, context=None)
        except KarmaSakshiError as exc:
            return {
                "ok": False,
                "error": "grant_does_not_cover_this_amount",
                "detail": exc.__class__.__name__,
                "balance_rupees": self.balance_rupees(),
            }
        return {"ok": True, "error": "forge_was_accepted", "balance_rupees": self.balance_rupees()}

    def protocol_events(self, invoice_id: str | None = None) -> list[dict]:
        events = []
        for event in self.audit.all_events():
            row = {
                "event_type": event.event_type,
                "decision": event.decision,
                "manifest_id": event.manifest_id,
                "grant_id": event.grant_id,
                "actor_id": event.actor_id,
                "at": event.timestamp.isoformat() if event.timestamp else None,
            }
            if invoice_id is None:
                events.append(row)
                continue
            held = self._held.get(invoice_id)
            if held and held[0].manifest.manifest_id == event.manifest_id:
                events.append(row)
        return list(reversed(events))

    def _request(self, invoice: dict, rupees: int, idem: str | None = None) -> PaymentRequest:
        return PaymentRequest(
            actor=self.agent,
            principal=self.clerk,
            source_account=OPERATING_ACCOUNT,
            beneficiary=invoice["vendor_account"],
            amount_minor_units=rupees * 100,
            currency="INR",
            reference=invoice["invoice_id"],
            idempotency_key=idem or f"pay-{invoice['invoice_id']}",
            ttl_seconds=3600,
        )

    @staticmethod
    def _clock():
        from karmasakshi.config.clock import SYSTEM_CLOCK

        return SYSTEM_CLOCK
