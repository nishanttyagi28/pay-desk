"""HTTP console for Aravali Traders Pay Desk (local prototype, not SaaS)."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from paydesk import __version__
from paydesk.desk import Desk
from paydesk.policy import POLICY

WEB = Path(__file__).resolve().parents[1] / "web"
desk = Desk()
app = FastAPI(title="Pay Desk", version=__version__)
app.mount("/static", StaticFiles(directory=WEB), name="static")


class QuestionIn(BaseModel):
    question: str = Field(min_length=1, max_length=2000)


class ConfirmIn(BaseModel):
    confirmed: bool = False


class ApproveIn(BaseModel):
    approved: bool = False


class ActorIn(BaseModel):
    actor: str


@app.get("/")
def index() -> FileResponse:
    return FileResponse(WEB / "index.html")


@app.get("/api/health")
def health() -> dict:
    return {
        "status": "ok",
        "company": POLICY["company"],
        "balance_rupees": desk.balance_rupees(),
        "version": __version__,
        "mode": "local-prototype",
        "actor": desk.actor,
    }


@app.get("/api/dashboard")
def dashboard() -> dict:
    return desk.dashboard()


@app.get("/api/policy")
def policy() -> dict:
    return POLICY


@app.get("/api/invoices")
def invoices() -> dict:
    return {"invoices": desk.invoices(), "balance_rupees": desk.balance_rupees(), "actor": desk.actor}


@app.post("/api/actor")
def actor(body: ActorIn) -> dict:
    try:
        return desk.set_actor(body.actor)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Unknown actor") from exc


@app.post("/api/ask")
def ask(body: QuestionIn) -> dict:
    return desk.ask(body.question)


@app.post("/api/invoices/{invoice_id}/review")
def review(invoice_id: str) -> dict:
    try:
        return desk.review(invoice_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Unknown invoice") from exc


@app.post("/api/invoices/{invoice_id}/release")
def release(invoice_id: str, body: ConfirmIn) -> dict:
    try:
        return desk.release(invoice_id, body.confirmed)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Unknown invoice") from exc


@app.post("/api/invoices/{invoice_id}/approve")
def approve(invoice_id: str, body: ApproveIn) -> dict:
    try:
        return desk.approve(invoice_id, body.approved)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Unknown invoice") from exc


@app.get("/api/invoices/{invoice_id}/timeline")
def timeline(invoice_id: str) -> dict:
    return {"invoice_id": invoice_id, "events": desk.timeline(invoice_id)}


@app.get("/api/invoices/{invoice_id}/passport")
def passport(invoice_id: str) -> dict:
    try:
        return desk.passport(invoice_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="No passport yet") from exc


@app.get("/api/invoices/{invoice_id}/passport.md")
def passport_md(invoice_id: str) -> PlainTextResponse:
    try:
        found = desk.passport(invoice_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="No passport yet") from exc
    return PlainTextResponse(found.get("passport_markdown") or "", media_type="text/markdown")


@app.get("/api/invoices/{invoice_id}/dossier")
def dossier(invoice_id: str) -> dict:
    try:
        return desk.dossier(invoice_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Unknown invoice") from exc


@app.get("/api/audit")
def audit() -> dict:
    return {"events": desk.timeline()}


@app.post("/api/demo/reset")
def reset() -> dict:
    global desk
    desk = Desk()
    return {"ok": True, "balance_rupees": desk.balance_rupees(), "message": "Demo books reloaded."}
