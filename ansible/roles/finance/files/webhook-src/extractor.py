"""Ruft die lokale Ollama-KI und parst robust striktes Finanz-JSON."""
import json
import datetime
import re
import requests

SYSTEM_PROMPT = (
    "Du bist ein Finanz-Extraktor. Antworte AUSSCHLIESSLICH mit gueltigem JSON, kein Fliesstext. "
    "Lies das GESAMTE Dokument bis zum Ende, auch ueber mehrere Seiten hinweg. "
    "Schluessel exakt: haendler (string), gesamtbetrag (number oder null), "
    "positionen (array von number = Zeilen-Endpreise inkl. Versand), "
    "datum (YYYY-MM-DD), kategorie (string). "
    "Regeln fuer den Betrag: "
    "gesamtbetrag = die FINALE Gesamtsumme / der Endbetrag / Zahlbetrag der Rechnung, "
    "genau der Betrag der abgebucht wird. Nimm NIEMALS den Einzelpreis einer einzelnen "
    "Position als Gesamtbetrag. Steht keine Endsumme im Dokument, setze gesamtbetrag=null "
    "und liste in positionen die Zeilen-Endpreise ALLER Artikel (Menge x Einzelpreis) "
    "sowie Versandkosten als eigene Zahl. Positive Dezimalzahlen, Punkt als Trenner. "
    "Zahlungen ueber PayPal fuer Einkaeufe: kategorie=Online-Shopping. "
    "Enthaelt das Dokument MEHRERE Rechnungen (mehrere Verkaeufer oder mehrere Seiten mit "
    "je eigenem Gesamtpreis/Zahlbetrag), setze gesamtbetrag=null und liste JEDEN dieser "
    "Gesamtpreise als eigene Zahl in positionen - dann NICHT zusaetzlich die Einzelartikel "
    "auflisten. "
    "datum: Suche im Dokument das Feld Rechnungsdatum, Lieferdatum, Bestelldatum oder "
    "Belegdatum. Es steht dort meist als TT.MM.JJJJ - rechne es nach JJJJ-MM-TT um "
    "(Beispiel: 28.05.2026 wird zu 2026-05-28). Nimm nicht das heutige Datum. "
    "Wenn unklar: haendler=Unbekannt, gesamtbetrag=null, positionen=[], kategorie=Sonstiges. "
    "Erfinde niemals Betraege oder Daten. "
    'Beispiel: {"haendler":"Amazon","gesamtbetrag":24.63,"positionen":[12.99,8.49,3.15],'
    '"datum":"2026-07-05","kategorie":"Online-Shopping"}'
)


DATUM_RE = re.compile(r"\b(\d{1,2})\.(\d{1,2})\.(\d{4})\b")


def datum_aus_text(ocr_text):
    """Erstes plausibles TT.MM.JJJJ aus dem Beleg als ISO-Datum.

    Fallback, wenn das Modell gar kein oder ein unmoegliches Datum liefert
    (beobachtet: "2025-16-00"). Ohne ihn wuerde das heutige Datum gesetzt und
    das matching_job faende die zugehoerige Bankbuchung nicht mehr (+-7 Tage).
    """
    if not ocr_text:
        return None
    for tag, monat, jahr in DATUM_RE.findall(str(ocr_text)):
        try:
            return datetime.date(int(jahr), int(monat), int(tag)).isoformat()
        except ValueError:
            continue
    return None


def _to_euro(value):
    """Robustes Parsen eines einzelnen Betrags (Komma/Punkt/EUR/Euro-Zeichen)."""
    try:
        cleaned = str(value).replace(",", ".").replace("€", "").replace("EUR", "").strip()
        return round(abs(float(cleaned)), 2)
    except (ValueError, TypeError):
        return None


def _resolve_betrag(data):
    """Ermittelt den Rechnungsbetrag: gesamtbetrag wenn vorhanden, sonst Summe der
    Positionen (deterministisch in Python, nicht vom Modell rechnen lassen).
    Faellt auf den Alt-Key betrag_euro zurueck (Rueckwaertskompat)."""
    gesamt = _to_euro(data.get("gesamtbetrag"))
    if gesamt is not None and gesamt > 0:
        return gesamt
    positionen = data.get("positionen")
    if isinstance(positionen, list) and positionen:
        summe = 0.0
        gefunden = False
        for p in positionen:
            betrag = _to_euro(p)
            if betrag is not None:
                summe += betrag
                gefunden = True
        if gefunden and summe > 0:
            return round(summe, 2)
    legacy = _to_euro(data.get("betrag_euro"))
    if legacy is not None:
        return legacy
    return 0.0


def parse_ai_json(raw, ocr_text=None):
    fallback_datum = datum_aus_text(ocr_text) or datetime.date.today().isoformat()
    defaults = {"haendler": "Unbekannt", "betrag_euro": 0.0, "datum": fallback_datum, "kategorie": "Sonstiges"}
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return defaults
    if not isinstance(data, dict):
        return defaults
    out = dict(defaults)
    if data.get("haendler"):
        out["haendler"] = str(data["haendler"])[:100]
    if data.get("kategorie"):
        out["kategorie"] = str(data["kategorie"])
    if data.get("datum"):
        try:
            datetime.date.fromisoformat(str(data["datum"]))
            out["datum"] = str(data["datum"])
        except ValueError:
            pass
    out["betrag_euro"] = _resolve_betrag(data)
    return out


def fit_text(text, limit=8000):
    """Kuerzt langen OCR-Text auf head+tail (erste 2/3 + letztes 1/3), damit bei
    mehrseitigen Belegen die Endsumme unten NICHT verloren geht."""
    if not text or len(text) <= limit:
        return text or ""
    head = int(limit * 2 / 3)
    tail = limit - head
    return text[:head] + "\n...\n" + text[-tail:]


def extract_finance(ocr_text, ollama_url, model):
    prompt = f"{SYSTEM_PROMPT}\nText: {fit_text(ocr_text)}"
    payload = {
        "model": model, "prompt": prompt, "stream": False, "format": "json",
        "options": {"temperature": 0.1, "num_predict": 400, "num_ctx": 8192},
    }
    r = requests.post(ollama_url, json=payload, timeout=180)
    r.raise_for_status()
    return parse_ai_json(r.json().get("response", ""), ocr_text)
