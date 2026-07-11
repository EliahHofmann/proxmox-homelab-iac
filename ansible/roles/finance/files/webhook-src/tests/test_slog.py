import io
import json

import slog


def _emit(event, **fields):
    buf = io.StringIO()
    slog.log_event(event, _stream=buf, **fields)
    return json.loads(buf.getvalue())


def test_log_event_ist_valides_json_mit_event_und_ts():
    rec = _emit("invoice_extraction_success", document_id=123, needs_review=False)
    assert rec["event"] == "invoice_extraction_success"
    assert rec["document_id"] == 123
    assert rec["needs_review"] is False
    assert isinstance(rec["ts"], (int, float))


def test_sensible_felder_werden_verworfen():
    rec = _emit(
        "dedupe_match",
        paperless_document_id=1,
        firefly_transaction_id="456",
        date_delta_days=2,
        amount=349.99,          # verboten
        betrag=349.99,          # verboten
        haendler="Amazon",      # verboten
        iban="DE1234",          # verboten
        token="geheim",         # verboten
        ocr_text="langer text", # verboten
        description="Kopfkissen",  # verboten
    )
    assert rec["paperless_document_id"] == 1
    assert rec["firefly_transaction_id"] == "456"
    assert rec["date_delta_days"] == 2
    for verboten in ("amount", "betrag", "haendler", "iban", "token", "ocr_text", "description"):
        assert verboten not in rec


def test_sensible_felder_case_insensitive():
    rec = _emit("x", Amount=5, IBAN="DE", Haendler="X", ok=1)
    assert rec == {**rec, "ok": 1}
    assert "Amount" not in rec and "IBAN" not in rec and "Haendler" not in rec


def test_merchant_hash_deterministisch_und_gekuerzt():
    a = slog.merchant_hash("Amazon EU")
    b = slog.merchant_hash("amazon eu ")   # normalisiert (trim+lower)
    assert a == b
    assert len(a) == 12
    assert a.isalnum()


def test_merchant_hash_haengt_von_salt_ab(monkeypatch):
    monkeypatch.setattr(slog, "LOG_SALT", "salt-A")
    a = slog.merchant_hash("Amazon")
    monkeypatch.setattr(slog, "LOG_SALT", "salt-B")
    b = slog.merchant_hash("Amazon")
    assert a != b
