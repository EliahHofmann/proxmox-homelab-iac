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


def test_abhebung_ist_keine_kategorie_mehr():
    # Seit der Umstellung ist eine Abhebung kein Konsum, sondern eine Umbuchung
    # ins Portemonnaie - kategorisiert wird erst die einzelne Barausgabe.
    assert match_category("GA NR00001111 BLZ12345678 0") is None


def test_abhebung_wird_erkannt():
    from categorize import ist_abhebung
    assert ist_abhebung("GA NR00001111 BLZ12345678 0")
    assert not ist_abhebung("AMAZON PAYMENTS EUROPE S.C.A.")
    assert not ist_abhebung(None)


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


# ---- neue Kategorien ----
def test_gaming():
    assert match_category("Tebex Limited") == "Gaming"
    assert match_category("STEAM GAMES") == "Gaming"
    assert match_category("Nintendo of Europe") == "Gaming"


def test_bildung():
    assert match_category("Westfaelische Hochschule") == "Bildung"
    assert match_category("Westfälische Hochschule") == "Bildung"


def test_abos_und_software():
    assert match_category("OPENAI *CHATGPT") == "Abos & Software"
    assert match_category("ANTHROPIC* CLAUDE SUB") == "Abos & Software"
    assert match_category("Proton AG") == "Abos & Software"
    assert match_category("netcup GmbH") == "Abos & Software"


def test_jugendfreizeit_kroatien():
    assert match_category("INA BACVA-SJEVER VISNJAN") == "Jugendfreizeit"
    assert match_category("NYX*INABavasjever Prsurici") == "Jugendfreizeit"
    assert match_category("PTO SEKA") == "Jugendfreizeit"
    assert match_category("TOBACCO ROVINJ") == "Jugendfreizeit"
    assert match_category("MLINAR PEKARSKA INDUST") == "Jugendfreizeit"
    assert match_category("LIDL HRVATSKA 0200") == "Jugendfreizeit"
    assert match_category("1160-20103 Irschenberg") == "Jugendfreizeit"


def test_konzum_faengt_die_vorgestreckte_buchung_nicht_ein():
    """Unter KONZUM laeuft auch die 170-EUR-Vorstreckung - die bleibt ohne Kategorie."""
    assert match_category("KONZUM Filiale") is None


def test_mensa_ist_restaurant_nicht_bildung():
    assert match_category("AKADEMISCHES FOERDERUNGSWERK") == "Restaurant"


def test_haendler_hinter_acquirern():
    assert match_category("Burger King Dorsten 13627") == "Restaurant"
    assert match_category("BurgerKing 27788 SOT") == "Restaurant"
    assert match_category("SUBWAY Gelsenkirchen-Bue") == "Restaurant"
    assert match_category("Tains - mein-asiamarkt GmbH") == "Lebensmittel"
    assert match_category("GASOMETER BOOKSHOP") == "Freizeit"
    assert match_category("ANTHROPIC. CLAUDE SUB") == "Abos & Software"
    assert match_category("DIGIPHILE") == "Abos & Software"


def test_gaming_schlaegt_online_shopping():
    """Tebex laeuft ueber PayPal - Gaming muss vor dem Auffangnetz greifen."""
    assert match_category("PayPal Europe - Tebex Limited") == "Gaming"


def test_abo_schlaegt_online_shopping():
    assert match_category("PayPal Europe - Proton AG") == "Abos & Software"


def test_acquirer_im_zeitraum_wird_jugendfreizeit():
    # Bei Kartenzahlungen bleibt nur der Acquirer uebrig - dann entscheidet das Datum.
    assert match_category("Landesbank Hessen-Thuringen", "2026-07-20") == "Jugendfreizeit"


def test_spaet_gebuchte_kartenzahlung_zaehlt_zum_zahlungstag():
    # Am 03.08. gebucht, gezahlt aber am 30.07. - das Fenster endet am 31.07.
    from categorize import zahlungsdatum
    assert zahlungsdatum("2026-07-30T12:42   Debitk.0", "2026-08-03") == "2026-07-30"
    assert match_category("Landesbank Hessen-Thuringen", "2026-08-03",
                          "2026-07-30T12:42   Debitk.0") == "Jugendfreizeit"


def test_zahlung_nach_der_rueckkehr_bleibt_offen():
    assert match_category("Landesbank Hessen-Thuringen", "2026-08-14",
                          "2026-08-11T09:45   Debitk.0") is None


def test_ohne_zahlungsdatum_gilt_das_buchungsdatum():
    from categorize import zahlungsdatum
    assert zahlungsdatum("ohne Datum", "2026-08-03") == "2026-08-03"


def test_acquirer_ausserhalb_des_zeitraums_bleibt_offen():
    assert match_category("Landesbank Hessen-Thuringen", "2026-08-15") is None
    assert match_category("Landesbank Hessen-Thuringen", "2026-06-01") is None


def test_acquirer_ohne_datum_bleibt_offen():
    assert match_category("Landesbank Hessen-Thuringen") is None


def test_haendlername_schlaegt_den_zeitraum():
    # Steht der Haendler drin, zaehlt er - auch mitten im Zeitfenster.
    assert match_category("Netto Marken-Discount", "2026-08-03") == "Lebensmittel"


def test_sammelkartenmarkt_ist_online_shopping():
    assert match_category("Sammelkartenmarkt GmbH + Co. KG") == "Online-Shopping"
