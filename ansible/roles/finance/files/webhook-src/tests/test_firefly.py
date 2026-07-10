from firefly import FireflyClient


def test_map_category_aliases():
    c = FireflyClient("http://x", "t")
    assert c.map_category("supermarkt") == "Lebensmittel"
    assert c.map_category("REWE") == "Lebensmittel"
    assert c.map_category("völlig unbekannt") == "Sonstiges"
    assert c.map_category("") == "Sonstiges"
    assert c.map_category(None) == "Sonstiges"


def test_map_category_substring():
    c = FireflyClient("http://x", "t")
    assert c.map_category("Kauf im Supermarkt XY") == "Lebensmittel"


def test_build_withdrawal_payload():
    c = FireflyClient("http://x", "t")
    p = c.build_withdrawal(haendler="Amazon", betrag=19.99, datum="2026-07-05",
                           kategorie="Elektronik", doc_id=123)
    tx = p["transactions"][0]
    assert tx["type"] == "withdrawal"
    assert tx["amount"] == "19.99"
    assert tx["source_name"] == "Sparkasse Giro"
    assert tx["destination_name"] == "Amazon"
    assert tx["external_id"] == "paperless_123"
    assert "unverifiziert" in tx["tags"] and "paperless" in tx["tags"]
    assert tx["category_name"] == "Elektronik"


def test_build_withdrawal_amount_formatting():
    c = FireflyClient("http://x", "t")
    tx = c.build_withdrawal("X", 5, "2026-01-01", "y", 1)["transactions"][0]
    assert tx["amount"] == "5.00"
