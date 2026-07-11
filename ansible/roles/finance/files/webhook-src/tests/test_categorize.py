from categorize import match_category


def test_lebensmittel():
    assert match_category("Netto Marken-Discoun") == "Lebensmittel"
    assert match_category("0502 EDEKA KIRSCH") == "Lebensmittel"
    assert match_category("KAUFLAND") == "Lebensmittel"
    assert match_category("Penny Mehrhoog") == "Lebensmittel"
    assert match_category("ALDI GmbH + Co. KG HERTEN") == "Lebensmittel"


def test_restaurant():
    assert match_category("WH-Gelsenkirchen 372 GE Cafe Neu") == "Restaurant"
    assert match_category("00925 MCDONALDS") == "Restaurant"
    assert match_category("SCHLOSS BURGER GmbH") == "Restaurant"
    assert match_category("SEPPELS SCHNELLIMBISS") == "Restaurant"


def test_freizeit():
    assert match_category("XXL Bowling Duisburg GmbH") == "Freizeit"
    assert match_category("28 Sued Erlebnisgastronomie GmbH") == "Freizeit"


def test_drogerie():
    assert match_category("ROSSMANN 3647 HUENXE") == "Drogerie"


def test_kleidung():
    assert match_category("H+M 098 SAGT VIELEN DANK") == "Kleidung"
    assert match_category("JEANS FRITZ") == "Kleidung"


def test_tanken():
    assert match_category("ARAL AG") == "Tanken"


def test_fixkosten():
    assert match_category("E-Plus Service GmbH") == "Fixkosten"


def test_bargeld():
    assert match_category("GA NR00002284 BLZ35650000 0") == "Bargeld"


def test_online_shopping():
    assert match_category("AMAZON PAYMENTS EUROPE S.C.A.") == "Online-Shopping"
    assert match_category("AMAZON EU S.A R.L., NIEDERLASSUNG DEUTSCHLAND") == "Online-Shopping"
    # PayPal-Einkaeufe (Games, Brettspiele, Lego) -> Online-Shopping (User-Wunsch).
    # Der konkrete Artikel ist auf dem Kontoauszug nicht sichtbar, die Kategorie passt trotzdem.
    assert match_category("PayPal Europe S.a.r.l. et Cie S.C.A") == "Online-Shopping"


def test_no_match_bleibt_offen():
    # Zahlungsdienstleister/Privatpersonen: bewusst KEIN Automatch
    assert match_category("Landesbank Hessen-Thuringen") is None
    assert match_category("JANA YVES HOFMANN") is None
    assert match_category("SG-VR Payment GmbH") is None
    assert match_category(None) is None
    assert match_category("") is None
