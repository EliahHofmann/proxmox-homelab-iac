#!/usr/bin/env python3
import os
import json
import urllib.request
from fastapi import FastAPI, Request, BackgroundTasks

app = FastAPI()

PAPERLESS_URL = "[http://192.168.178.86:8000](http://192.168.178.86:8000)"
PAPERLESS_TOKEN = os.environ.get("PAPERLESS_TOKEN", "")
OLLAMA_URL = "[http://192.168.178.85:11434/api/generate](http://192.168.178.85:11434/api/generate)"
OLLAMA_MODEL = "paperlessKI"

ACTUAL_SERVER_URL = "http://actual-budget:5006"  
ACTUAL_TOKEN = os.environ.get("ACTUAL_TOKEN", "")

ACTUAL_ACCOUNT_ID = "PLATZHALTER_KONTO_ID" 

def api_call(url, method="GET", headers=None, data=None):
    req = urllib.request.Request(url, method=method)
    if headers:
        for k, v in headers.items():
            req.add_header(k, v)
    body = json.dumps(data).encode("utf-8") if data else None
    with urllib.request.urlopen(req, data=body, timeout=120) as res:
        return json.loads(res.read().decode())

def process_webhook(document_id: int):
    try:
        print(f"Starte Verarbeitung für Dokument ID: {document_id}")
        
        headers = {"Authorization": f"Token {PAPERLESS_TOKEN}", "Content-Type": "application/json"}
        doc = api_call(f"{PAPERLESS_URL}/api/documents/{document_id}/", headers=headers)
        ocr_text = doc.get("content", "")[:1200].replace("\n", " ").replace('"', "'")

        prompt = (
            "Extract finance data as JSON only. Do not talk. "
            "Format: {\"haendler\": \"...\", \"betrag_euro\": 0.00, \"datum\": \"YYYY-MM-DD\", \"kategorie\": \"...\"}. "
            f"Text: {ocr_text}"
        )
        
        payload = {
            "model": OLLAMA_MODEL,
            "prompt": prompt,
            "stream": False,
            "format": "json",
            "options": {"temperature": 0.1, "num_thread": 4}
        }
        
        ai_raw = api_call(OLLAMA_URL, method="POST", data=payload).get("response", "").strip()
        ai_res = json.loads(ai_raw)
        
        print(f"KI hat analysiert: {ai_res}")
        
        betrag_euro = float(ai_res.get("betrag_euro", 0))
        amount_cents = int(betrag_euro * -100)
        
        if ACTUAL_ACCOUNT_ID == "PLATZHALTER_KONTO_ID":
            print("WARNUNG: Actual Account ID ist noch nicht gesetzt. Abbruch des Uploads.")
            return

        actual_headers = {
            "X-Actual-Token": ACTUAL_TOKEN,
            "Content-Type": "application/json"
        }
        
        transaction_data = {
            "transactions": [{
                "account": ACTUAL_ACCOUNT_ID,
                "date": ai_res.get("datum"),
                "amount": amount_cents,
                "payee_name": ai_res.get("haendler", "Unbekannt"),
                "notes": f"KI-Import aus Paperless ID {document_id}",
                "imported_id": f"paperless_{document_id}"  # Wichtig für Deduplizierung!
            }]
        }
        
        api_call(f"{ACTUAL_SERVER_URL}/api/v1/transactions", method="POST", headers=actual_headers, data=transaction_data)
        print(f"Erfolgreich in Actual verbucht: {ai_res.get('haendler')} - {betrag_euro}€")
        
    except Exception as e:
        print(f"Fehler bei der Verarbeitung von ID {document_id}: {e}")

@app.post("/webhook")
async def paperless_webhook(request: Request, background_tasks: BackgroundTasks):
    data = await request.json()
    document_id = data.get("document_id")
    event = data.get("event")
    
    if event == "document_consumed" and document_id:
        background_tasks.add_task(process_webhook, document_id)
        return {"status": "processing started"}
    return {"status": "ignored event"}
