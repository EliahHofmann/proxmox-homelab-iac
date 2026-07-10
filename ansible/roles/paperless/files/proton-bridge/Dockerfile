# Basis: shenxn/protonmail-bridge (debian:sid-slim). Neuere Bridge-Versionen
# (>=3.20, per Auto-Update gezogen) laden libfido2 dynamisch fuer Security-Key-
# Support. Das Basis-Image bringt sie nicht mit -> "libfido2.so.1: cannot open
# shared object file" und die Bridge crasht beim Start. Bibliothek nachruesten.
FROM shenxn/protonmail-bridge:latest
RUN apt-get update \
    && apt-get install -y --no-install-recommends libfido2-1 \
    && rm -rf /var/lib/apt/lists/*
