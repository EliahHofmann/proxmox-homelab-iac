#!/usr/bin/env python3
import os, json, urllib.request, sys

# --- KONFIGURATION ---
PAPERLESS_URL = "http://localhost:8000"
PAPERLESS_TOKEN = os.environ.get("AI_TAGGER_TOKEN")
OLLAMA_URL = "http://192.168.178.85:11434/api/generate"
DOCUMENT_ID = os.environ.get("DOCUMENT_ID")

ERLAUBTE_TYPEN = [
    "Rechnung",
    "Bescheid",
    "Vertrag",
    "Versicherung",
    "Gehaltsabrechnung",
    "Bankbeleg",
    "Quittung",
    "Brief",
    "Urkunde",
    "Gutachten",
    "Einladung"
]

typen_beschreibung = (
    "Rechnung (Zahlungsaufforderung von Shops/Firmen wie Amazon, Strom, Internet), "
    "Bescheid (Behoerden/Krankenkasse/Steuern/offizielle Mitteilungen), "
    "Vertrag (Handy/Miete/Arbeit/Abonnements), "
    "Versicherung (Policen/Schadensmeldungen/Versicherungsthemen), "
    "Gehaltsabrechnung (Lohnzettel), "
    "Bankbeleg (Kontoauszug/Kreditkarte), "
    "Quittung (Kassenzettel), "
    "Brief (NUR private/persoenliche Post ohne andere Kategorie), "
    "Urkunde (Schulzeugnisse/Abschlusszeugnisse/Geburtsurkunden/Zertifikate/Berufsschule), "
    "Gutachten (Arztbriefe/Gutachten/TUeV), "
    "Einladung (Termine/Versammlungen)"
)

def api_call(endpoint, method="GET", data=None):
    url = f"{PAPERLESS_URL}/api/{endpoint}"
    if not url.endswith("/"): url += "/"
    req = urllib.request.Request(url, method=method)
    req.add_header("Authorization", f"Token {PAPERLESS_TOKEN}")
    req.add_header("Content-Type", "application/json")
    body = json.dumps(data).encode("utf-8") if data else None
    with urllib.request.urlopen(req, data=body) as res:
        return json.loads(res.read().decode())

def get_or_create(endpoint, name):
    items = api_call(endpoint).get("results", [])
    for item in items:
        if item.get("name").lower() == name.lower():
            return item.get("id")
    return api_call(endpoint, method="POST", data={"name": name}).get("id")

def sanitize_typ(typ: str) -> str:
    for erlaubt in ERLAUBTE_TYPEN:
        if erlaubt.lower() == typ.strip().lower():
            return erlaubt
    return "Brief"

def main():
    if not DOCUMENT_ID: sys.exit(0)

    # 1. OCR Text holen
    doc = api_call(f"documents/{DOCUMENT_ID}")
    ocr_text = doc.get("content", "")[:600].replace("\n", " ")

    # 2. KI Analyse
    prompt = (
        f"Analysiere das Dokument. Antworte NUR mit JSON ohne Erklaerungen. "
        f"Verwende exakt diese Schluessel: Titel, Absender, Typ, Tags. "
        f'Beispiel: {{\"Titel\": \"...\", \"Absender\": \"...\", \"Typ\": \"...\", \"Tags\": [\"...\"]}}. '
        f"Fuer 'Absender' trage NUR den Namen der ausstellenden Firma oder Behoerde ein, "
        f"niemals den Namen des Empfaengers oder eine Privatperson. "
        f"Bei Online-Shops (z.B. Amazon, Ebay) ist der Absender immer der Shop-Name. "
        f"Fuer 'Typ' waehle NUR einen passenden Wert aus: {typen_beschreibung}. "
        f"Krankenkassen-Schreiben sind immer 'Bescheid' oder 'Versicherung', niemals 'Brief'. "
        f"Zeugnisse und Abschlussdokumente von Schulen sind immer 'Urkunde', niemals 'Bescheid'. "
        f"Fuer 'Tags' gib genau 3 kurze allgemeine Schlagwoerter auf Deutsch an, "
        f"die den Inhalt beschreiben, nicht den Absender. "
        f"Text: {ocr_text}"
    )

    payload = {
        "model": "paperlessKI",
        "prompt": prompt,
        "stream": False,
        "format": "json",
        "options": {
            "num_predict": 1500,
            "temperature": 0.1
        }
    }

    req_ai = urllib.request.Request(OLLAMA_URL, data=json.dumps(payload).encode("utf-8"))
    with urllib.request.urlopen(req_ai) as res:
        raw = res.read().decode()

    # 3. JSON parsen mit Fallback
    try:
        ai_res = json.loads(json.loads(raw).get("response", "{}"))
        print(f"DEBUG KI-Antwort: {ai_res}")
    except json.JSONDecodeError as e:
        print(f"WARNUNG: KI-Antwort ungueltig ({e}), nutze Fallbacks.")
        ai_res = {}

    # 4. Typ absichern
    typ_roh = ai_res.get("Typ") or ai_res.get("Dokumenttyp", "Brief")
    typ_bereinigt = sanitize_typ(typ_roh)

    # 5. IDs aufloesen/erstellen
    tag_ids = [get_or_create("tags", t) for t in ai_res.get("Tags", [])]
    corr_id = get_or_create("correspondents", ai_res.get("Absender", "Unbekannt"))
    type_id = get_or_create("document_types", typ_bereinigt)

    # 6. Dokument aktualisieren
    patch_data = {
        "title": ai_res.get("Titel", "KI Dokument"),
        "correspondent": corr_id,
        "document_type": type_id,
        "tags": tag_ids
    }
    api_call(f"documents/{DOCUMENT_ID}", method="PATCH", data=patch_data)
    print(f"Update abgeschlossen fuer ID {DOCUMENT_ID} - Typ: {typ_bereinigt}")

if __name__ == "__main__":
    main()

