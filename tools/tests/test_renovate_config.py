"""Prueft, dass Renovate jede fest eingetragene Version im Repo findet.

Faellt ein neues image:-Feld oder eine *_version-Variable durchs Raster,
wuerde sie nie aktualisiert - ohne dass es jemand merkt.
"""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CONFIG = json.loads((ROOT / "renovate.json").read_text(encoding="utf-8"))

# Lokal gebaute Images, keine Registry
IGNORED_IMAGES = ("paperless-proton-bridge:local", "halcyon")
IGNORED_VERSIONS = ("halcyon_version",)
UNUSED_ROLE = "ansible/roles/nextcloud/"


def managers():
    for m in CONFIG["customManagers"]:
        files = [re.compile(p.strip("/")) for p in m["managerFilePatterns"]]
        rx = [re.compile(s.replace("(?<", "(?P<")) for s in m["matchStrings"]]
        yield files, rx


def repo_files():
    # Ausnahme fest im Test, nicht aus der geprueften Konfiguration gelesen
    for p in ROOT.rglob("*"):
        if p.is_file() and ".git" not in p.parts:
            rel = p.relative_to(ROOT).as_posix()
            if not rel.startswith(UNUSED_ROLE):
                yield rel


def matches():
    """Alle Treffer als (datei, match)."""
    found = []
    all_files = list(repo_files())
    for files, rx in managers():
        for rel in all_files:
            if any(f.search(rel) for f in files):
                text = (ROOT / rel).read_text(encoding="utf-8")
                for r in rx:
                    found += [(rel, m) for m in r.finditer(text)]
    return found


def matched_spans():
    spans = {}
    for rel, m in matches():
        spans.setdefault(rel, []).append(m.span())
    return spans


def line_is_matched(rel, offset, spans):
    return any(a <= offset < b for a, b in spans.get(rel, []))


def line_offsets(rel, pattern):
    text = (ROOT / rel).read_text(encoding="utf-8")
    pos = 0
    for n, line in enumerate(text.splitlines(keepends=True), 1):
        m = re.match(pattern, line)
        if m:
            yield n, line.strip(), pos + m.start(1)
        pos += len(line)


def test_every_image_line_is_detected_or_ignored():
    spans = matched_spans()
    missed = []
    for rel in repo_files():
        if not re.search(r"^ansible/roles/[^/]+/templates/[^/]*compose[^/]*\.j2$", rel):
            continue
        if rel.startswith(UNUSED_ROLE):
            continue
        for n, line, off in line_offsets(rel, r"^\s*(image:)"):
            if "{{" in line or any(i in line for i in IGNORED_IMAGES):
                continue
            if not line_is_matched(rel, off, spans):
                missed.append(f"{rel}:{n}: {line}")
    assert not missed, "Renovate findet diese Images nicht:\n" + "\n".join(missed)


def test_every_version_default_has_renovate_comment():
    spans = matched_spans()
    missed = []
    for rel in repo_files():
        if not re.search(r"^ansible/roles/[^/]+/defaults/main\.yml$", rel):
            continue
        for n, line, off in line_offsets(rel, r"^([a-z_]+_version):"):
            if line.split(":")[0] in IGNORED_VERSIONS:
                continue
            if not line_is_matched(rel, off, spans):
                missed.append(f"{rel}:{n}: {line}")
    assert not missed, "Ohne '# renovate:'-Kommentar:\n" + "\n".join(missed)


EXPECTED = {
    ("grafana/loki", "3.7.9"),
    ("prom/prometheus", "v3.15.1"),
    ("prom/alertmanager", "v0.34.1"),
    ("prom/node-exporter", "v1.12.1"),
    ("prompve/prometheus-pve-exporter", "3.10.1"),
    ("grafana/grafana", "13.2.4"),
    ("traefik", "v3.7.16"),
    ("favonia/cloudflare-ddns", "1.17.1"),
    ("mariadb", "11.8.9"),
    ("fireflyiii/core", "version-6.7.9"),
    ("fireflyiii/data-importer", "version-2.3.5"),
    ("binwiederhier/ntfy", "v2.32.0"),
    ("docker.io/library/redis", "8.10.2"),
    ("docker.io/library/postgres", "15.19"),
    ("docker.io/valkey/valkey", "9"),
    ("ghcr.io/immich-app/postgres", "14-vectorchord0.4.3-pgvectors0.2.0"),
    ("collabora/code", "26.04.5.1.1"),
    ("vaultwarden/server", "1.37.4"),
    ("cloudflare/cloudflared", "2026.10.3"),
    ("adguard/adguardhome", "v0.107.79"),
    ("ghcr.io/immich-app/immich-server", "v3.3.5"),
    ("ghcr.io/paperless-ngx/paperless-ngx", "3.3.3"),
    ("jellyfin/jellyfin", "12.2"),
}


def test_expected_dependencies():
    disabled = {n for r in CONFIG["packageRules"] if r.get("enabled") is False
                for n in r.get("matchPackageNames", [])}
    found = {(m["depName"], m["currentValue"]) for rel, m in matches()
             if not rel.startswith(UNUSED_ROLE) and m["depName"] not in disabled}
    assert found == EXPECTED
    assert "paperless-proton-bridge" in disabled
    digests = {m["depName"] for rel, m in matches() if m.groupdict().get("currentDigest")}
    assert {"docker.io/valkey/valkey", "ghcr.io/immich-app/postgres"} <= digests


def test_patch_automerge_minor_major_never():
    rules = CONFIG["packageRules"]
    auto = [r for r in rules if r.get("automerge") is True]
    assert auto, "keine Automerge-Regel"
    for r in auto:
        assert set(r.get("matchUpdateTypes", [])) <= {"patch", "digest"}, r
        assert r.get("matchUpdateTypes"), "Automerge ohne matchUpdateTypes gilt fuer alles"
    assert CONFIG.get("automerge") is not True
    assert CONFIG["schedule"] == ["after 1am and before 5am"]
    assert CONFIG["timezone"] == "Europe/Berlin" or ":timezone(Europe/Berlin)" in CONFIG["extends"]


def regex_werte(obj, schluessel=""):
    """Alle Werte, die Renovate als Regex liest: matchStrings und /.../-Muster."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield from regex_werte(v, k)
    elif isinstance(obj, list):
        for v in obj:
            yield from regex_werte(v, schluessel)
    elif isinstance(obj, str):
        if schluessel == "matchStrings" or (len(obj) > 2 and obj.startswith("/") and obj.endswith("/")):
            yield schluessel, obj


def test_keine_lookarounds_fuer_re2():
    # Renovate prueft Muster mit RE2: Lookaheads/-behinds und Rueckverweise machen
    # die ganze Konfiguration ungueltig, Renovate stellt dann alle PRs ein.
    verboten = ("(?!", "(?=", "(?<!", "(?<=", "\\1")
    werte = list(regex_werte(CONFIG))
    assert werte, "keine Regex-Werte gefunden"
    for k, muster in werte:
        assert not any(v in muster for v in verboten), f"{k}: {muster}"


def test_ignorepaths_ist_bewusst_gesetzt():
    # Jede Erweiterung von ignorePaths muss hier bewusst eingetragen werden.
    assert set(CONFIG.get("ignorePaths", [])) == {UNUSED_ROLE + "**"}
