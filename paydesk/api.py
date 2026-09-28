"""HTTP desk for Aravali Traders."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from paydesk import __version__
from paydesk.desk import Desk

WEB = Path(__file__).resolve().parents[1] / "web"
desk = Desk()
app = FastAPI(title="Pay Desk", version=__version__)
app.mount("/static", StaticFiles(directory=WEB), name="static")


class QuestionIn(BaseModel):
    question: str = Field(min_length=1, max_length=2000)


class ReleaseIn(BaseModel):
    confirmed: bool = False


@app.get("/")
def index() -> FileResponse:
    return FileResponse(WEB / "index.html")


@app.get("/api/health")
def health() -> dict:
    return {
        "status": "ok",
        "company": "Aravali Traders",
        "balance_rupees": desk.balance_rupees(),
        "version": __version__,
    }


@app.get("/api/invoices")
def invoices() -> dict:
    return {"invoices": desk.invoices(), "balance_rupees": desk.balance_rupees()}


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
def release(invoice_id: str, body: ReleaseIn) -> dict:
    try:
        return desk.release(invoice_id, body.confirmed)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Unknown invoice") from exc
