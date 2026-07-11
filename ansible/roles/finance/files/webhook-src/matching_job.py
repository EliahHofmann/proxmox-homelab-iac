"""Cross-Stream-Dedup (Strom 1 vs. Strom 2): Bank gewinnt, Beleg reichert an.

Laeuft per Cron nach dem Bank-Import. Matcht neue Bankbuchungen gegen
unverifizierte Paperless-Belege (gleicher Betrag, Datum +/-7 Tage) und merged sie.
Unverifizierte Belege aelter als 30 Tage gelten als Barzahlung.
"""
import os
import time
import datetime
from firefly import FireflyClient
from metrics import JobMetrics
import slog

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


def run(today=None):
    today = today or datetime.date.today()
    t0 = time.perf_counter()
    m = JobMetrics("dedupe")
    try:
        fc = FireflyClient(os.environ["FIREFLY_URL"], os.environ["FIREFLY_PAT"])
        belege = fc.list_unverified()
        bank = fc.list_bank_unmatched()

        matches = 0
        for b in bank:
            hit = find_match(b, belege)
            if hit:
                fc.merge_beleg_into_bank(b, hit)
                fc.delete_transaction(hit["id"])
                delta = abs((datetime.date.fromisoformat(b["date"][:10])
                             - datetime.date.fromisoformat(hit["date"][:10])).days)
                belege = [x for x in belege if x["id"] != hit["id"]]
                matches += 1
                m.inc("finance_dedupe_matches_total")
                slog.log_event("dedupe_match",
                               firefly_transaction_id=str(b["id"]),
                               paperless_transaction_id=str(hit["id"]),
                               date_delta_days=delta)

        cutoff = today - datetime.timedelta(days=CASH_AFTER_DAYS)
        moved = 0
        unmatched = 0        # junge, unverifizierte Belege ohne Match (noch offen)
        needs_review = 0     # davon: schon aus dem Match-Fenster raus -> Handarbeit
        for p in belege:
            pd = datetime.date.fromisoformat(p["date"][:10])
            if pd < cutoff:
                fc.move_to_cash(p)
                moved += 1
            else:
                unmatched += 1
                if (today - pd).days > WINDOW_DAYS:
                    needs_review += 1

        m.set_gauge("finance_dedupe_unmatched_receipts", unmatched)
        m.set_gauge("finance_receipts_needing_review", needs_review)
        m.mark_success_meta(time.perf_counter() - t0)
        m.save()
        slog.log_event("dedupe_run_success", matches=matches, moved_to_cash=moved,
                       unmatched=unmatched, needs_review=needs_review)
    except Exception as e:
        m.record_failure(time.perf_counter() - t0)
        m.save()
        slog.log_event("dedupe_run_failed", error_type=type(e).__name__)
        raise


if __name__ == "__main__":
    run()
