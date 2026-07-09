"""FastAPI-Webhook: Paperless-Beleg -> Ollama-Extraktion -> Firefly-Transaktion (Strom 1)."""
import os
import requests
from fastapi import FastAPI, Request, BackgroundTasks

from firefly import FireflyClient
from extractor import extract_finance

app = FastAPI()

PAPERLESS_URL = os.environ["PAPERLESS_URL"].rstrip("/")
PAPERLESS_TOKEN = os.environ["PAPERLESS_TOKEN"]
OLLAMA_URL = os.environ["OLLAMA_URL"]
OLLAMA_MODEL = os.environ["OLLAMA_MODEL"]
firefly = FireflyClient(os.environ["FIREFLY_URL"], os.environ["FIREFLY_PAT"])


def process(document_id):
    try:
        if firefly.search_external_id(f"paperless_{document_id}"):
            print(f"Dok {document_id} bereits verbucht, ueberspringe.")
            return
        r = requests.get(
            f"{PAPERLESS_URL}/api/documents/{document_id}/",
            headers={"Authorization": f"Token {PAPERLESS_TOKEN}"}, timeout=60)
        r.raise_for_status()
        ocr = r.json().get("content", "")
        data = extract_finance(ocr, OLLAMA_URL, OLLAMA_MODEL)
        if data["betrag_euro"] <= 0:
            print(f"Dok {document_id}: kein Betrag erkannt, ueberspringe.")
            return
        payload = firefly.build_withdrawal(
            data["haendler"], data["betrag_euro"], data["datum"], data["kategorie"], document_id)
        firefly.create_withdrawal(payload)
        print(f"Verbucht: {data['haendler']} {data['betrag_euro']}EUR (Dok {document_id})")
    except Exception as e:
        print(f"Fehler Dok {document_id}: {e}")


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/webhook")
async def webhook(request: Request, background_tasks: BackgroundTasks):
    body = await request.json()
    doc_id, event = body.get("document_id"), body.get("event")
    if event == "document_consumed" and doc_id:
        background_tasks.add_task(process, doc_id)
        return {"status": "processing"}
    return {"status": "ignored"}
