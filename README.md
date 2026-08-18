# Proxmox Homelab: Infrastructure-as-Code & CI/CD Automation

[![CI/CD Pipeline](https://github.com/EliahHofmann/proxmox-homelab-iac/actions/workflows/devops-qa.yml/badge.svg)](https://github.com/EliahHofmann/proxmox-homelab-iac/actions)

Dieses Repository enthält die Infrastruktur- und Konfigurationsverwaltung für mein privates Proxmox Homelab. Das Projekt demonstriert einen vollständigen, professionellen **Infrastructure-as-Code (IaC)** Ansatz in Kombination mit einer modernen **CI/CD-Pipeline** und **zentraler Secret-Verwaltung**.

Das primäre Ziel dieses Projekts ist es, die Bereitstellung von Servern und Diensten zu 100% reproduzierbar, automatisiert und sicher zu gestalten – von der physischen Hardware-Ressource bis zum fertig konfigurierten Reverse-Proxy.

---

## Kern-Features

* **100% Infrastructure as Code:** Die komplette Infrastruktur (LXC & QEMU VMs) wird via **Terraform (OpenTofu)** provisioniert.
* **Dynamisches Inventory:** Anstelle von statischen IP-Listen nutzt **Ansible** die Proxmox API und Tags (z.B. `tag_adguard`), um Server dynamisch zu finden und zu konfigurieren.
* **Automatisierte CI/CD Pipeline:** Eine **GitHub Actions** Pipeline validiert Änderungen in Pull Requests (`--check`) und rollt diese nach dem Merge in den Main-Branch automatisch aus.
* **Zero-Trust Secrets Management:** Passwörter, API-Tokens und SSH-Keys werden nicht im Quellcode versioniert. Sie werden zur Laufzeit dynamisch von einem selbst gehosteten **HashiCorp Vault** in die Pipeline integriert.

---

## Tech Stack & Architektur

### Infrastruktur & Provisioning
* **Hypervisor:** Proxmox VE
* **Provisioning:** OpenTofu / Terraform (mit Proxmox Provider)
* **Configuration Management:** Ansible (mit `community.proxmox` Dynamic Inventory)

### Security & CI/CD
* **Secrets Management:** HashiCorp Vault
* **Automation:** GitHub Actions (Runner wird lokal gehostet)
* **Netzwerk:** Netbird (Wireguard VPN), Cloudflare Tunnels

### Gehostete Core-Services
* **Traefik:** Zentraler Reverse Proxy & Zertifikatsverwaltung
* **AdGuard Home:** DNS-Server und Split-DNS für internes Routing
* **Vaultwarden:** Selbst gehosteter Passwort-Manager
* **Nextcloud:** Cloud-Speicher und Kollaboration
* **Monitoring:** Prometheus, Grafana, Loki (inkl. automatischem Node-Exporter & Docker-Log Deployment via Ansible)
* **Weitere Services:** Consul, Immich, Collabora, Qwen3 (AI)

---

## Repository Struktur

Die Codebase ist modular aufgebaut und trennt Hardware-Provisionierung strikt von der Software-Konfiguration:

```text
proxmox-homelab-iac/
├── .github/workflows/
│   └── devops-qa.yml           # CI/CD Pipeline Definition
├── ansible/
│   ├── roles/                  # Modulare Ansible Rollen für jeden Service
│   │   ├── common/             # Basis-Setup (Docker, APT, Loki-Plugin, Node-Exporter)
│   │   ├── traefik/
│   │   ├── vaultwarden/
│   │   └── ...                 # (adguard, immich, consul, etc.)
│   ├── ansible.cfg             # Globale Ansible Konfiguration (z.B. auto_silent)
│   ├── proxmox.yml             # Konfiguration für das dynamische Proxmox Inventory
│   └── site.yml                # Haupt-Playbook zur Orchestrierung
├── terraform/
│   ├── main.tf                 # Terraform Ressourcen (Proxmox LXC/QEMU)
│   └── variables.tf            # Terraform Variablen
└── README.md
```

---

## Architektur & Workflow

1. **Infrastruktur erstellen (Terraform):** 
   Terraform kommuniziert mit der Proxmox API, erstellt neue Container/VMs, weist Ressourcen (CPU, RAM, Disk) zu und vergibt spezifische **Tags** (z.B. `monitoring`).
2. **Dynamic Inventory (Ansible):** 
   Das Ansible-Plugin greift auf Proxmox zu, sucht nach diesen Tags und ermittelt vollautomatisch die korrekten IP-Adressen der frisch erstellten Hosts (unabhängig davon, ob es sich um LXC Container oder QEMU VMs handelt).
3. **Pipeline Deployment (GitHub Actions):** 
   Der GitHub Runner authentifiziert sich via AppRole bei **HashiCorp Vault**, ruft den privaten SSH-Schlüssel sowie alle benötigten Service-Secrets ab und startet den Ansible-Lauf.
4. **Software Rollout (Ansible):** 
   Ansible installiert Docker, richtet ein zentrales Logging ein und deployt die jeweiligen Services über Jinja2-getemplatete Docker-Compose Dateien.

---

## Projektziele und Ergebnisse

Dieses Homelab dient als Portfolio-Projekt zur Vertiefung von DevOps Best Practices und moderner Systemadministration.
Wesentliche technische Meilensteine umfassen:
* Die erfolgreiche Integration von **HashiCorp Vault** in GitHub Actions für eine passwortfreie und sichere Pipeline.
* Die Entwicklung dynamischer **Jinja2-Expressions**, um in Ansible IP-Adressen über verschiedene Proxmox-Netzwerktypen hinweg fehlerfrei aufzulösen.
* Die Orchestrierung einer komplexen Infrastruktur, die durch eine Tag-basierte Architektur eine sehr hohe Skalierbarkeit ermöglicht (neuer Server = neues Tag = automatische Konfiguration).

---
*Erstellt von Eliah Hofmann - [LinkedIn](https://www.linkedin.com/in/eliah-hofmann)*
