#!/bin/bash
# Prueft ein Compose-Projekt nach dem Deploy: jeder Container healthy (bzw.
# running ohne Healthcheck), kein Neustart in einem 20-s-Fenster, und die
# laufenden Images sind genau die aus der Compose-Datei.
# Aufruf: container-health.sh <compose-dir> <max-wartezeit-s>
set -u
dir=$1; wait_max=${2:-360}
cd "$dir" || { echo "FAIL: $dir fehlt"; exit 1; }
fail=0
state() { docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$1" 2>/dev/null; }
ok() { [ "$1" = healthy ] || [ "$1" = running ]; }

ids=$(docker compose ps -aq)
[ -n "$ids" ] || { echo "FAIL: keine Container in $dir"; exit 1; }
names=$(for i in $ids; do docker inspect -f '{{.Name}}' "$i" | tr -d /; done)

for c in $names; do
  t=0; s=$(state "$c")
  while ! ok "$s" && [ "$t" -lt "$wait_max" ]; do sleep 5; t=$((t + 5)); s=$(state "$c"); done
  ok "$s" || { echo "FAIL: $c ist $s nach ${t}s"; fail=1; }
done

declare -A before
for c in $names; do before[$c]=$(docker inspect -f '{{.RestartCount}}' "$c"); done
sleep 20
for c in $names; do
  now=$(docker inspect -f '{{.RestartCount}}' "$c"); s=$(state "$c")
  if [ "$now" != "${before[$c]}" ] || ! ok "$s"; then echo "FAIL: $c startet neu oder kippt ($s, restarts ${before[$c]} -> $now)"; fail=1; fi
done

want=$(docker compose config --images | sort -u)
have=$(for c in $names; do docker inspect -f '{{.Config.Image}}' "$c"; done | sort -u)
missing=$(comm -23 <(echo "$want") <(echo "$have"))
extra=$(comm -13 <(echo "$want") <(echo "$have"))
if [ -n "$missing$extra" ]; then
  echo "FAIL: Soll/Ist-Images weichen ab (fehlt: ${missing:-nichts} / unerwartet: ${extra:-nichts})"; fail=1
fi

[ "$fail" = 0 ] && echo "OK: $(echo $names | wc -w) Container in $dir"
exit $fail
