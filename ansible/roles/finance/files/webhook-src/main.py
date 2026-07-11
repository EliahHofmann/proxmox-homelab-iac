"""FastAPI-Webhook: Paperless-Beleg -> Ollama-Extraktion -> Firefly-Transaktion (Strom 1)."""
import os
import time
import requests
from fastapi import FastAPI, Request, BackgroundTasks, Response

from firefly import FireflyClient
from extractor import extract_finance
import metrics
import slog

app = FastAPI()

PAPERLESS_URL = os.environ["PAPERLESS_URL"].rstrip("/")
PAPERLESS_TOKEN = os.environ["PAPERLESS_TOKEN"]
OLLAMA_URL = os.environ["OLLAMA_URL"]
OLLAMA_MODEL = os.environ["OLLAMA_MODEL"]
firefly = FireflyClient(os.environ["FIREFLY_URL"], os.environ["FIREFLY_PAT"])


def process(document_id):
    try:
        if firefly.search_external_id(f"paperless_{document_id}"):
            slog.log_event("document_already_booked", document_id=document_id)
            return

        with metrics.timer(metrics.paperless_duration):
            r = requests.get(
                f"{PAPERLESS_URL}/api/documents/{document_id}/",
                headers={"Authorization": f"Token {PAPERLESS_TOKEN}"}, timeout=60)
            r.raise_for_status()
            ocr = r.json().get("content", "")

        try:
            with metrics.timer(metrics.ollama_duration):
                data = extract_finance(ocr, OLLAMA_URL, OLLAMA_MODEL)
        except Exception:
            metrics.extraction_failed.inc()
            slog.log_event("invoice_extraction_failed", document_id=document_id, reason="ollama_error")
            raise

        if data["betrag_euro"] <= 0:
            metrics.extraction_failed.inc()
            slog.log_event("invoice_extraction_failed", document_id=document_id, reason="no_amount")
            return

        metrics.extraction_success.inc()
        slog.log_event("invoice_extraction_success", document_id=document_id,
                       merchant_hash=slog.merchant_hash(data["haendler"]), needs_review=False)

        payload = firefly.build_withdrawal(
            data["haendler"], data["betrag_euro"], data["datum"], data["kategorie"], document_id)
        try:
            with metrics.timer(metrics.firefly_duration):
                firefly.create_withdrawal(payload)
        except Exception:
            metrics.firefly_create_failed.inc()
            slog.log_event("firefly_create_failed", document_id=document_id, reason="api_error")
            raise

        metrics.firefly_create_success.inc()
        slog.log_event("firefly_create_success", document_id=document_id)
    except Exception as e:
        # Nur grobe Fehlerklasse ins Log, KEINE Rohdaten (OCR/Betrag/Haendler).
        slog.log_event("process_error", document_id=document_id, error_type=type(e).__name__)


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/metrics")
async def metrics_endpoint():
    body, content_type = metrics.render()
    return Response(content=body, media_type=content_type)


@app.post("/webhook")
async def webhook(request: Request, background_tasks: BackgroundTasks):
    body = await request.json()
    doc_id, event = body.get("document_id"), body.get("event")
    if event == "document_consumed" and doc_id:
        metrics.webhook_received.inc()
        metrics.last_webhook_ts.set(time.time())
        slog.log_event("webhook_received", document_id=doc_id)
        background_tasks.add_task(process, doc_id)
        return {"status": "processing"}
    metrics.webhook_invalid.inc()
    slog.log_event("webhook_invalid")
    return {"status": "ignored"}
