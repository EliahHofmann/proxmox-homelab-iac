"""Filter fuer die Rolle ssh_access: Schluessel aus Vault lesen und pruefen."""
import re

KEY_RE = re.compile(r"((?:ssh|ecdsa|sk)-[A-Za-z0-9@.-]+)\s+([A-Za-z0-9+/]+=*)(?:\s+(.*))?$")


def parse_keys(raw):
    """Zeilen -> [{body: "typ base64", comment}], ohne Leer-/Kommentarzeilen und Doppelte.

    Optionen vor dem Schluessel (from=..., no-pty) werden verworfen; die Rolle setzt
    die Optionen selbst.
    """
    keys, seen = [], set()
    for line in (raw or "").replace("\r", "").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        m = KEY_RE.search(line)
        if not m:
            continue
        body = f"{m.group(1)} {m.group(2)}"
        if body not in seen:
            seen.add(body)
            keys.append({"body": body, "comment": (m.group(3) or "").strip()})
    return keys


def keys_safe(keys, own_body):
    """Nur schreiben, wenn niemand ausgesperrt wird: >= 2 Schluessel, der eigene dabei."""
    return bool(own_body) and len(keys) >= 2 and any(k["body"] == own_body for k in keys)


class FilterModule:
    def filters(self):
        return {"ssh_access_parse_keys": parse_keys, "ssh_access_keys_safe": keys_safe}
