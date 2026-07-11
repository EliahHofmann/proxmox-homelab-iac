import time
from prometheus_client import Histogram, CollectorRegistry

import metrics


def test_jobmetrics_roundtrip_und_akkumulation(tmp_path):
    d = str(tmp_path)
    m = metrics.JobMetrics("dedupe", state_dir=d)
    m.inc("finance_dedupe_matches_total", 2)
    m.set_gauge("finance_dedupe_unmatched_receipts", 5)
    m.save()
    # Zweiter Lauf: Counter akkumuliert ueber read-modify-write.
    m2 = metrics.JobMetrics("dedupe", state_dir=d)
    m2.inc("finance_dedupe_matches_total", 3)
    m2.save()

    col = metrics.StateFileCollector(state_dir=d)
    samples = {}
    for fam in col.collect():
        for s in fam.samples:
            samples[s.name] = s.value
    assert samples["finance_dedupe_matches_total"] == 5
    assert samples["finance_dedupe_unmatched_receipts"] == 5


def test_record_success_setzt_counter_dauer_und_zeitstempel(tmp_path):
    d = str(tmp_path)
    before = time.time()
    m = metrics.JobMetrics("bank_import", state_dir=d)
    m.record_success(12.34)
    m.save()

    col = metrics.StateFileCollector(state_dir=d)
    samples = {s.name: s.value for fam in col.collect() for s in fam.samples}
    assert samples["finance_bank_import_success_total"] == 1
    assert samples["finance_bank_import_duration_seconds"] == 12.34
    assert samples["finance_last_successful_bank_import_timestamp"] >= before


def test_record_failure_zaehlt_fehler(tmp_path):
    d = str(tmp_path)
    m = metrics.JobMetrics("advisor", state_dir=d)
    m.record_failure()
    m.save()
    col = metrics.StateFileCollector(state_dir=d)
    samples = {s.name: s.value for fam in col.collect() for s in fam.samples}
    assert samples["finance_advisor_run_failed_total"] == 1
    assert "finance_last_successful_advisor_run_timestamp" not in samples


def test_kaputte_state_datei_wird_ignoriert(tmp_path):
    (tmp_path / "dedupe.json").write_text("kein json {{{", encoding="utf-8")
    col = metrics.StateFileCollector(state_dir=str(tmp_path))
    # darf nicht werfen, liefert einfach nichts aus dieser Datei
    assert list(col.collect()) == []


def test_counter_name_bekommt_kein_doppeltes_total(tmp_path):
    d = str(tmp_path)
    m = metrics.JobMetrics("bank_import", state_dir=d)
    m.inc("finance_bank_import_success_total", 1)
    m.save()
    names = [s.name for fam in metrics.StateFileCollector(state_dir=d).collect() for s in fam.samples]
    assert "finance_bank_import_success_total" in names
    assert "finance_bank_import_success_total_total" not in names


def test_timer_misst_in_histogram():
    reg = CollectorRegistry()
    h = Histogram("t_sec", "test", registry=reg)
    with metrics.timer(h):
        time.sleep(0.001)
    assert reg.get_sample_value("t_sec_count") == 1.0
    assert reg.get_sample_value("t_sec_sum") > 0.0


def test_render_liefert_prometheus_format():
    metrics.webhook_received.inc()
    body, ctype = metrics.render()
    text = body.decode("utf-8")
    assert "finance_paperless_webhook_received_total" in text
    assert "text/plain" in ctype


def test_in_process_metriken_haben_keine_labels():
    # Datenschutz: keine dynamischen Labels (Haendler/Betrag/Titel) an Metriken.
    for m in (metrics.webhook_received, metrics.extraction_failed,
              metrics.firefly_create_success, metrics.ollama_duration):
        assert m._labelnames == ()
