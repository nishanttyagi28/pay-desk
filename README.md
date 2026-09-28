# Pay Desk

Local accounts-payable console for **Aravali Traders, Okhla**. Not a multi-tenant SaaS. One company, one operating account, one process. You run it on localhost and record it yourself.

A vendor payment leaves the simulator only after:

1. **Three-way match** — invoice, purchase order, goods receipt (line-level)
2. **PromptGate** — the release sentence contains the purchase-order amount
3. **TruthGraph** — the claim is `ALLOW` against PO / GRN / ledger evidence
4. **Policy** — vendor not on hold; dual approval when amount ≥ ₹1,00,000
5. **KarmaSakshi** — seal → authorize → commit → verify → Action Passport
6. **AgentEval** — golden cases + Failure Memory on blocks

## Demo video (LinkedIn)

Recording of the local console (~50s, with voiceover):

- [`docs/demo/paydesk_linkedin_demo.mp4`](docs/demo/paydesk_linkedin_demo.mp4)
- Caption draft: [`docs/demo/LINKEDIN_POST.md`](docs/demo/LINKEDIN_POST.md)

Open the mp4, sound on. Flow: open invoices → DELETE refused → mismatch blocked → dual approval → sealed once.

## What you get on the screen

- Work queue with stage filters (`ready` / `blocked` / `awaiting_finance`)
- Actor switcher: clerk Meera, finance Arjun, auditor Neha (local roles, not login SaaS)
- Three-way match panel + line table
- Control plane: PromptGate, TruthGraph, match score, release / finance approve
- KarmaSakshi Action Passport markdown after settle
- Timeline (desk events + protocol audit)
- Ops view: cash, open exposure, blocked count, finance queue, library pins
- Audit feed
- Ledger ask (read-only SQL via Agentic Data Analyst guard)
- **Reset demo** for a clean recording take

## Seeded bills

| Invoice | Kind | What happens |
| --- | --- | --- |
| INV-2408 Shree Metals ₹1,86,000 | clean | Dual approval → sealed payment |
| INV-2411 PackWell ₹94,000 | duplicate | Already settled; TruthGraph `BLOCK` |
| INV-2414 Himalaya ₹2,10,000 | mismatch | PO/GRN ₹1,50,000 → blocked |
| INV-2419 Shree Metals ₹64,000 | injection | Note says ₹1; PromptGate fails that sentence |
| INV-2420 Shree Metals ₹1,20,000 | partial | GRN short → blocked |
| INV-2423 Orient Freight ₹42,000 | hold | Vendor status `hold` → blocked |

## Measured

```bash
PYTHONPATH=. python -m pytest -q
PYTHONPATH=. python eval/run_eval.py
```

Last local run: **7 pytest passed**. Eval **8/8** correctness, tool recall 1.0. Opening ₹10,00,000 → one dual-approved debit ₹1,86,000 → closing ₹8,14,000. Replay refused.

## Run on your machine

```bash
git clone https://github.com/nishanttyagi28/pay-desk.git
cd pay-desk
bash scripts/fetch_vendor.sh
python3 -m venv .venv && source .venv/bin/activate
pip install fastapi uvicorn sqlalchemy pandas pydantic httpx pyyaml

# KarmaSakshi Protocol must import as `karmasakshi`
# Option A: pip install karmasakshi-protocol
# Option B: export PYTHONPATH="/path/to/karmasakshi-protocol/src:$PYTHONPATH"

PYTHONPATH=. python -m uvicorn paydesk.api:app --host 127.0.0.1 --port 8771
```

Open **http://127.0.0.1:8771**.

### Recording script (about 90 seconds)

1. Click **Reset demo** so cash shows ₹10,00,000.
2. Open **INV-2411** → already settled / blocked duplicate.
3. Open **INV-2414** → mismatch score, Release blocked.
4. Click **Try write** → DELETE refused by SELECT guard.
5. Open **INV-2408** → match 100, ALLOW, **Confirm for finance**.
6. Switch actor to **Arjun Kapoor · finance** → **Finance approve & seal**.
7. Show passport + balance ₹8,14,000. Re-open INV-2408 → already settled.
8. Optional: Ops tab and Audit tab.

## Limits

Single company fixture. Simulator payments only. TruthGraph scores the evidence text you give it. PromptGate is a contains-check, not a live LLM. No cloud deploy, no tenants, no billing.
