"""Cross-Stream-Dedup (Strom 1 vs. Strom 2): Bank gewinnt, Beleg reichert an.

Laeuft per Cron nach dem Bank-Import. Matcht neue Bankbuchungen gegen
unverifizierte Paperless-Belege (gleicher Betrag, Datum +/-7 Tage) und merged sie.
Unverifizierte Belege aelter als 30 Tage gelten als Barzahlung.
"""
import os
import datetime
from firefly import FireflyClient

WINDOW_DAYS = 7
CASH_AFTER_DAYS = 30


def find_match(bank_tx, beleg_txs):
    """Genau ein passender unverifizierter Beleg, sonst None (bei Mehrdeutigkeit None)."""
    bd = datetime.date.fromisoformat(bank_tx["date"][:10])
    ba = round(float(bank_tx["amount"]), 2)
    hits = []
    for p in beleg_txs:
        if "unverifiziert" not in p["tags"]:
            continue
        if round(float(p["amount"]), 2) != ba:
            continue
        pd = datetime.date.fromisoformat(p["date"][:10])
        if abs((bd - pd).days) <= WINDOW_DAYS:
            hits.append(p)
    return hits[0] if len(hits) == 1 else None


def run():
    fc = FireflyClient(os.environ["FIREFLY_URL"], os.environ["FIREFLY_PAT"])
    belege = fc.list_unverified()
    bank = fc.list_bank_unmatched()

    for b in bank:
        m = find_match(b, belege)
        if m:
            fc.merge_beleg_into_bank(b, m)
            fc.delete_transaction(m["id"])
            belege = [x for x in belege if x["id"] != m["id"]]
            print(f"Gematcht: Bank {b['id']} <- Beleg {m['id']} ({b['amount']}EUR)")

    cutoff = datetime.date.today() - datetime.timedelta(days=CASH_AFTER_DAYS)
    for p in belege:
        if datetime.date.fromisoformat(p["date"][:10]) < cutoff:
            fc.move_to_cash(p)
            print(f"Als Barzahlung markiert: Beleg {p['id']} ({p['amount']}EUR)")


if __name__ == "__main__":
    run()
