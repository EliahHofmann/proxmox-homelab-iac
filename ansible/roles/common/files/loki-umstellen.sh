#!/bin/bash
# Erstellt laufende Container neu, deren Loki-Ziel nicht mehr dem aus
# /etc/docker/daemon.json entspricht. Log-Einstellungen gelten pro Container
# ab seiner Erstellung - ein Neustart von Docker allein reicht nicht.
# Gibt nie die URL aus (sie enthaelt das Passwort). Verwaltet von Ansible (common).
set -euo pipefail
daemon="${DAEMON_JSON:-/etc/docker/daemon.json}"
soll=$(sed -n 's/.*"loki-url": *"\([^"]*\)".*/\1/p' "$daemon")
[ -n "$soll" ] || { echo "kein loki-url in $daemon" >&2; exit 1; }

ordner=()
einzeln=()
for id in $(docker ps -q); do
    [ "$(docker inspect -f '{{.HostConfig.LogConfig.Type}}' "$id")" = "loki" ] || continue
    [ "$(docker inspect -f '{{index .HostConfig.LogConfig.Config "loki-url"}}' "$id")" = "$soll" ] && continue
    dir=$(docker inspect -f '{{index .Config.Labels "com.docker.compose.project.working_dir"}}' "$id")
    if [ -n "$dir" ]; then
        ordner+=("$dir")
    else
        einzeln+=("$(docker inspect -f '{{.Name}}' "$id" | sed 's#^/##')")
    fi
done

if [ ${#ordner[@]} -gt 0 ]; then
    while IFS= read -r dir; do
        (cd "$dir" && docker compose up -d --force-recreate --pull never)
        echo "neu erstellt: $dir"
    done < <(printf '%s\n' "${ordner[@]}" | sort -u)
fi
if [ ${#einzeln[@]} -gt 0 ]; then
    echo "ohne compose, von Hand neu erstellen: ${einzeln[*]}"
fi
