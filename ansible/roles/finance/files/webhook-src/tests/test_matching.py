from matching_job import find_match


def _tx(id, amount, date, tags):
    return {"id": id, "amount": amount, "date": date, "tags": tags}


def test_match_same_amount_within_window():
    bank = _tx("b1", "19.99", "2026-07-08", [])
    belege = [_tx("p1", "19.99", "2026-07-05", ["unverifiziert"])]
    assert find_match(bank, belege)["id"] == "p1"


def test_no_match_outside_window():
    bank = _tx("b1", "19.99", "2026-07-20", [])
    belege = [_tx("p1", "19.99", "2026-07-05", ["unverifiziert"])]
    assert find_match(bank, belege) is None


def test_no_match_different_amount():
    bank = _tx("b1", "20.00", "2026-07-06", [])
    belege = [_tx("p1", "19.99", "2026-07-05", ["unverifiziert"])]
    assert find_match(bank, belege) is None


def test_ambiguous_returns_none():
    bank = _tx("b1", "19.99", "2026-07-06", [])
    belege = [_tx("p1", "19.99", "2026-07-05", ["unverifiziert"]),
              _tx("p2", "19.99", "2026-07-07", ["unverifiziert"])]
    assert find_match(bank, belege) is None


def test_ignores_already_verified_beleg():
    bank = _tx("b1", "19.99", "2026-07-06", [])
    belege = [_tx("p1", "19.99", "2026-07-05", ["bar"])]
    assert find_match(bank, belege) is None


def test_match_exact_same_day():
    bank = _tx("b1", "50.00", "2026-07-05", [])
    belege = [_tx("p1", "50.00", "2026-07-05", ["unverifiziert"])]
    assert find_match(bank, belege)["id"] == "p1"
