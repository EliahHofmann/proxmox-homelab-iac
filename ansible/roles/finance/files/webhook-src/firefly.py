"""Firefly III API-Client: Belegimport (Strom 1) + Dedup-Hilfen (Strom 2/4)."""
import requests

# Freie KI-Kategorien -> festes Set (verhindert Kategorie-Wildwuchs)
CATEGORY_ALIASES = {
    "supermarkt": "Lebensmittel", "rewe": "Lebensmittel", "edeka": "Lebensmittel",
    "aldi": "Lebensmittel", "lidl": "Lebensmittel", "lebensmittel": "Lebensmittel",
    "baecker": "Lebensmittel", "bäcker": "Lebensmittel",
    "restaurant": "Restaurant", "gastronomie": "Restaurant", "essen": "Restaurant",
    "elektronik": "Elektronik", "hardware": "Elektronik", "computer": "Elektronik",
    "kleidung": "Kleidung", "drogerie": "Drogerie", "versicherung": "Versicherung",
    "strom": "Fixkosten", "miete": "Fixkosten", "abo": "Abos", "software": "Abos",
}
ALLOWED = set(CATEGORY_ALIASES.values()) | {"Sonstiges"}

ASSET_BANK = "Sparkasse Giro"
ASSET_CASH = "Bargeld"


class FireflyClient:
    def __init__(self, base_url, token):
        self.base = base_url.rstrip("/")
        self.h = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.api+json",
            "Content-Type": "application/json",
        }

    # ---------- reine Logik (unit-getestet) ----------
    def map_category(self, raw):
        if not raw:
            return "Sonstiges"
        key = raw.strip().lower()
        if key in CATEGORY_ALIASES:
            return CATEGORY_ALIASES[key]
        for alias, cat in CATEGORY_ALIASES.items():
            if alias in key:
                return cat
        return "Sonstiges"

    def build_withdrawal(self, haendler, betrag, datum, kategorie, doc_id):
        return {
            "error_if_duplicate_hash": True,
            "apply_rules": True,
            "transactions": [{
                "type": "withdrawal",
                "date": datum,
                "amount": f"{float(betrag):.2f}",
                "description": haendler or "Unbekannt",
                "source_name": ASSET_BANK,
                "destination_name": haendler or "Unbekannt",
                "category_name": self.map_category(kategorie),
                "external_id": f"paperless_{doc_id}",
                "tags": ["paperless", "unverifiziert"],
                "notes": f"KI-Import aus Paperless Dok {doc_id}",
            }],
        }

    # ---------- API (real gegen Firefly, Checkpoint-getestet) ----------
    def search_external_id(self, ext_id):
        r = requests.get(f"{self.base}/api/v1/search/transactions",
                         params={"query": f"external_id:{ext_id}"}, headers=self.h, timeout=30)
        r.raise_for_status()
        return len(r.json().get("data", [])) > 0

    def create_withdrawal(self, payload):
        r = requests.post(f"{self.base}/api/v1/transactions",
                          json=payload, headers=self.h, timeout=30)
        r.raise_for_status()
        return r.json()

    def _flatten(self, group):
        """Firefly-Transaktionsgruppe -> flache dicts pro Split."""
        gid = group["id"]
        out = []
        for split in group["attributes"]["transactions"]:
            out.append({
                "id": gid,
                "journal_id": split["transaction_journal_id"],
                "amount": split["amount"],
                "date": split["date"][:10],
                "tags": split.get("tags") or [],
                "category_name": split.get("category_name"),
                "description": split.get("description"),
                "notes": split.get("notes"),
                "source_name": split.get("source_name"),
            })
        return out

    def _search_transactions(self, query):
        out, page = [], 1
        while True:
            r = requests.get(f"{self.base}/api/v1/search/transactions",
                             params={"query": query, "page": page}, headers=self.h, timeout=60)
            r.raise_for_status()
            body = r.json()
            for g in body.get("data", []):
                out.extend(self._flatten(g))
            pag = body.get("meta", {}).get("pagination", {})
            if page >= pag.get("total_pages", 1):
                break
            page += 1
        return out

    def list_unverified(self):
        return self._search_transactions('tag_is:"unverifiziert"')

    def list_bank_unmatched(self):
        # withdrawals auf dem Bank-Konto, die noch nicht gematcht wurden
        return self._search_transactions(
            f'source_account_is:"{ASSET_BANK}" type:withdrawal -tag_is:"gematcht"')

    def update_transaction(self, group_id, journal_id, fields):
        body = {"apply_rules": False,
                "transactions": [{"transaction_journal_id": journal_id, **fields}]}
        r = requests.put(f"{self.base}/api/v1/transactions/{group_id}",
                         json=body, headers=self.h, timeout=30)
        r.raise_for_status()
        return r.json()

    def delete_transaction(self, group_id):
        r = requests.delete(f"{self.base}/api/v1/transactions/{group_id}",
                            headers=self.h, timeout=30)
        r.raise_for_status()

    def merge_beleg_into_bank(self, bank, beleg):
        """Kategorie/Notiz vom Beleg auf die Bank-Transaktion uebertragen + Tag 'gematcht'."""
        new_tags = [t for t in bank["tags"] if t not in ("unverifiziert",)]
        if "gematcht" not in new_tags:
            new_tags.append("gematcht")
        fields = {
            "category_name": beleg.get("category_name") or bank.get("category_name"),
            "notes": (beleg.get("notes") or "") + " | gematcht mit Paperless-Beleg",
            "tags": new_tags,
        }
        return self.update_transaction(bank["id"], bank["journal_id"], fields)

    def move_to_cash(self, beleg):
        """Unverifizierten Beleg als Barzahlung markieren (Konto -> Bargeld, Tag -> bar)."""
        new_tags = [t for t in beleg["tags"] if t != "unverifiziert"]
        if "bar" not in new_tags:
            new_tags.append("bar")
        fields = {"source_name": ASSET_CASH, "tags": new_tags}
        return self.update_transaction(beleg["id"], beleg["journal_id"], fields)
