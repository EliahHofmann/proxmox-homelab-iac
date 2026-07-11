import metrics
import record_run


def _samples(state_dir):
    col = metrics.StateFileCollector(state_dir=state_dir)
    return {s.name: s.value for fam in col.collect() for s in fam.samples}


def test_record_run_success(tmp_path, monkeypatch):
    monkeypatch.setattr(metrics, "STATE_DIR", str(tmp_path))
    assert record_run.main(["--job", "bank_import", "--status", "success", "--duration", "3.5"]) == 0
    s = _samples(str(tmp_path))
    assert s["finance_bank_import_success_total"] == 1
    assert s["finance_bank_import_duration_seconds"] == 3.5
    assert "finance_last_successful_bank_import_timestamp" in s


def test_record_run_failed(tmp_path, monkeypatch):
    monkeypatch.setattr(metrics, "STATE_DIR", str(tmp_path))
    assert record_run.main(["--job", "bank_import", "--status", "failed"]) == 0
    s = _samples(str(tmp_path))
    assert s["finance_bank_import_failed_total"] == 1
    assert "finance_last_successful_bank_import_timestamp" not in s


def test_record_run_akkumuliert_ueber_laeufe(tmp_path, monkeypatch):
    monkeypatch.setattr(metrics, "STATE_DIR", str(tmp_path))
    record_run.main(["--job", "bank_import", "--status", "success", "--duration", "1"])
    record_run.main(["--job", "bank_import", "--status", "success", "--duration", "2"])
    s = _samples(str(tmp_path))
    assert s["finance_bank_import_success_total"] == 2
    assert s["finance_bank_import_duration_seconds"] == 2.0
