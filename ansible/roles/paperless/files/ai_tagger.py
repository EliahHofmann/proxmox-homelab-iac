#!/usr/bin/env python3
import os, json, urllib.request, sys

# --- KONFIGURATION ---
PAPERLESS_URL = "http://localhost:8000"
PAPERLESS_TOKEN = os.environ.get("AI_TAGGER_TOKEN")
OLLAMA_URL = "http://192.168.178.85:11434/api/generate"
# Modell fuer Titel/Absender/Typ. Ueber die Umgebung ueberschreibbar,
# damit ein Wechsel keinen neuen Deploy des Skripts braucht.
OLLAMA_MODEL = os.environ.get("AI_TAGGER_MODEL", "qwen3.6-14b-a3b")
DOCUMENT_ID = os.environ.get("DOCUMENT_ID")

ERLAUBTE_TYPEN = [
    "Rechnung", "Bescheid", "Vertrag", "Versicherung",
    "Gehaltsabrechnung", "Bankbeleg", "Quittung", "Brief",
    "Urkunde", "Gutachten", "Einladung"
]

def api_call(endpoint, method="GET", data=None):
    if "?" in endpoint:
        base, query = endpoint.split("?", 1)
        if not base.endswith("/"):
            base += "/"
        endpoint = f"{base}?{query}"

    url = f"{PAPERLESS_URL}/api/{endpoint}"
    if not url.endswith("/") and "?" not in url:
        url += "/"

    req = urllib.request.Request(url, method=method)
    req.add_header("Authorization", f"Token {PAPERLESS_TOKEN}")
    req.add_header("Content-Type", "application/json")
    body = json.dumps(data).encode("utf-8") if data else None
    with urllib.request.urlopen(req, data=body) as res:
        return json.loads(res.read().decode())

def get_or_create(endpoint, name):
    if not name or not name.strip():
        return None
    name = name.strip()[:64]

    items = api_call(f"{endpoint}?page_size=100").get("results", [])
    for item in items:
        if item.get("name").lower() == name.lower():
            return item.get("id")

    try:
        return api_call(endpoint, method="POST", data={"name": name}).get("id")
    except Exception as e:
        print(f"WARNUNG: Konnte '{name}' nicht anlegen ({e}), wird uebersprungen.")
        return None

def sanitize_typ(typ: str) -> str:
    for erlaubt in ERLAUBTE_TYPEN:
        if erlaubt.lower() == typ.strip().lower():
            return erlaubt
    return "Brief"

def extract_titel_aus_text(ocr_text: str, typ: str, absender: str) -> str:
    """Verbesserter Fallback: Filtert nun auch Kassenbon-Müll und Tabellen-Header heraus."""
    zeilen = [z.strip() for z in ocr_text.split("  ") if len(z.strip()) > 5]

    if typ in ["Rechnung", "Quittung"]:
        # NEU: Tabellen-Überschriften hinzugefügt
        skip_woerter = [
            "rechnung", "lieferschein", "bestellung", "bestellnummer",
            "rechnungsnummer", "datum", "zahlung", "menge", "preis",
            "versand", "gesamt", "stueck", "amazon", absender.lower(),
            "ust-id", "ust-idnr", "steuernummer", "seite", "page",
            "zahlungsreferenznummer", "lieferdatum", "zwischensumme",
            "straße", "strasse", "zahlbetrag", "€", "eur", "mwst", "steuer",
            "postleitzahl", "plz", "deutschland", "de",
            "bestellbestätigung", "kassen-id", "tse-", "str.", "str ",
            "bestellinformationen", "rechnungsdetails", "beschreibung",
            "rechnungsadresse", "lieferadresse", "verkauft von", "artikel"
        ]
        for zeile in zeilen:
            z = zeile.lower()
            if not any(s in z for s in skip_woerter) and 8 < len(zeile) < 80:
                if "€" not in zeile and "strasse" not in z and "straße" not in z:
                    return zeile[:60]

    betreff_marker = ["betreff:", "betrifft:", "re:", "betr.:"]
    for zeile in zeilen:
        for marker in betreff_marker:
            if marker in zeile.lower():
                return zeile.replace(marker, "").strip()[:60]

    return f"{typ} von {absender}"

def main():
    if not DOCUMENT_ID: sys.exit(0)

    doc = api_call(f"documents/{DOCUMENT_ID}")
    ocr_text = doc.get("content", "")[:6000].replace("\n", "  ")

    # 2. KI Analyse (Spezialregeln für Restaurants/Kassenbons hinzugefügt)
    prompt = (
        "Du bist ein intelligenter Assistent für Dokumentenmanagement. Analysiere den Text und antworte AUSSCHLIESSLICH im gültigen JSON-Format.\n\n"
        "Verwende exakt diese Schlüssel: Titel, Absender, Typ, Tags.\n\n"
        "- Titel: MAXIMAL 3 bis 6 Wörter! Kurz und prägnant. Bei Rechnungen nenne das Hauptprodukt (z.B. 'PCIe WLAN Karte' oder 'Whopper Menü'). Suche im Text gezielt unterhalb von 'Beschreibung' oder 'Artikel'.\n"
        "  !!! WICHTIG: Verwende NIEMALS Adressen, 'Bestellbestätigung', Kassen-IDs, Beträge, 'Rechnung' oder 'Bestellinformationen' als Titel! !!!\n"
        "- Absender: Der reine Firmenname (z.B. 'BURGER KING', 'VISIONDE LTD' oder 'AOK').\n"
        f"- Typ: ZWINGEND exakt EINEN Typ aus dieser Liste kopieren: {ERLAUBTE_TYPEN}. Erfinde keine eigenen Typen! (Hinweis: Kassenbons = 'Quittung', Ämter/Krankenkassen = 'Bescheid').\n"
        "- Tags: Ein Array mit 3 kurzen Schlagwörtern.\n\n"
        "Beispielausgabe:\n"
        "{\n"
        '  "Titel": "PCIe WLAN Karte",\n'
        '  "Absender": "VISIONDE LTD",\n'
        '  "Typ": "Rechnung",\n'
        '  "Tags": ["Computer", "Hardware", "Netzwerk"]\n'
        "}\n\n"
        f"Dokumententext:\n{ocr_text}"
    )
    
    payload = {
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "stream": False,
        "format": "json",
        "options": {
            "num_predict": 300,
            "temperature": 0.1
        }
    }

    req_ai = urllib.request.Request(OLLAMA_URL, data=json.dumps(payload).encode("utf-8"))
    with urllib.request.urlopen(req_ai) as res:
        raw = res.read().decode()

    try:
        ai_res = json.loads(json.loads(raw).get("response", "{}"))
        print(f"DEBUG KI-Antwort: {ai_res}")
    except json.JSONDecodeError as e:
        print(f"WARNUNG: KI-Antwort ungueltig ({e}), nutze Fallbacks.")
        ai_res = {}

    # 4. Typ absichern und Kassenbon-Zwang
    typ_roh = ai_res.get("Typ") or ai_res.get("Dokumenttyp", "Brief")
    absender_roh = ai_res.get("Absender", "Unbekannt")

    # --- NEU: Post-Processing Zwang für Kassenbons ---
    bon_indikatoren = ["tse-transaktion", "tse-start", "kassen-id", "barzahlung", "rückgeld"]
    bekannte_gastro = ["burger king", "mcdonald", "kfc", "subway", "bäcker"]

    if (any(ind in ocr_text.lower() for ind in bon_indikatoren) or 
        any(bg in absender_roh.lower() for bg in bekannte_gastro)):
        print(f"INFO: Kassenbon-Muster erkannt. Überschreibe KI-Typ '{typ_roh}' auf 'Quittung'.")
        typ_roh = "Quittung"
    # -------------------------------------------------

    typ_bereinigt = sanitize_typ(typ_roh)

    tag_ids = [tid for tid in
               [get_or_create("tags", t) for t in ai_res.get("Tags", [])]
               if tid is not None]
    corr_id = get_or_create("correspondents", ai_res.get("Absender", "Unbekannt"))
    type_id = get_or_create("document_types", typ_bereinigt)

    # Erweiterte Liste generischer Wörter, um Kassenbon-Überschriften abzufangen
    generische_woerter = [
        "rechnung", "brief", "bescheid", "quittung", "dokument",
        "bestellung", "lieferschein", "kassenbon", "beleg",
        "vertrag", "urkunde", "versicherung", "gutachten", "einladung",
        "zahlbetrag", "gesamtpreis", "adresse", "lieferadresse",
        "bestellbestätigung", "bestellnummer", "kassen-id", "tse-transaktion",
        "bestellinformationen", "rechnungsdetails", "beschreibung", "artikel"
    ]
    
    ai_title = ai_res.get("Titel", "").strip()

    # Check auf Müll im Titel
    if (not ai_title or
        ai_title.lower() in generische_woerter or
        "ust-id" in ai_title.lower() or
        "steuernummer" in ai_title.lower() or
        "strasse" in ai_title.lower() or
        "straße" in ai_title.lower() or
        "kassen-id" in ai_title.lower() or
        "€" in ai_title or
        "zahlbetrag" in ai_title.lower()):

        finaler_titel = extract_titel_aus_text(ocr_text, typ_bereinigt, ai_res.get("Absender", "Unbekannt"))
        print(f"Titel-Fallback aktiv: '{finaler_titel}'")
    else:
        finaler_titel = ai_title

    patch_data = {
        "title": finaler_titel,
        "correspondent": corr_id,
        "document_type": type_id,
        "tags": tag_ids
    }
    api_call(f"documents/{DOCUMENT_ID}", method="PATCH", data=patch_data)
    print(f"Update abgeschlossen fuer ID {DOCUMENT_ID} - Titel: {finaler_titel} | Typ: {typ_bereinigt}")

    # Finance-Webhook nur bei Rechnung/Quittung anstossen (Datenstrom 1)
    if typ_bereinigt in ("Rechnung", "Quittung"):
        try:
            req = urllib.request.Request(
                "http://192.168.178.87:9000/webhook",
                data=json.dumps({"document_id": int(DOCUMENT_ID), "event": "document_consumed"}).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST")
            urllib.request.urlopen(req, timeout=10)
            print(f"Finance-Webhook getriggert fuer Dok {DOCUMENT_ID}")
        except Exception as e:
            print(f"Finance-Webhook-Trigger fehlgeschlagen (nicht kritisch): {e}")

if __name__ == "__main__":
    main()