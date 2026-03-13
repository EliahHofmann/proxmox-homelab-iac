# Proxmox Homelab IaC

In diesem Repository verwalte ich die Infrastruktur und Konfiguration für mein privates Proxmox Homelab. Das gesamte Setup basiert auf einem Infrastructure as Code (IaC) Ansatz, um die Serverumgebung reproduzierbar und automatisiert aufbauen zu können.

**Hinweis: Aktuell fehlen noch einige Kommentare im Code. Diese werden aber demnächst ergänzt und überarbeitet.**

Die Bereitstellung der Infrastruktur ist strikt von der Software-Konfiguration getrennt. OpenTofu (Terraform) übernimmt das Erstellen der virtuellen Maschinen und LXC-Container über die Proxmox API. Ansible kümmert sich anschließend um die Installation und Konfiguration der Dienste.

## Tech Stack
* **Hypervisor:** Proxmox VE
* **Infrastructure Provisioning:** OpenTofu / Terraform
* **Configuration Management:** Ansible
* **Core Services:** Docker, Traefik (Reverse Proxy), Vaultwarden, Nextcloud
* **Netzwerk:** Netbird (Wireguard VPN), AdGuard Home (Split-DNS)

## Repository Struktur

Das Projekt nutzt Ansible-Rollen und Jinja2-Templates für die dynamische Konfiguration der Dienste. Um sensible Daten (Passwörter, IPs, API-Keys) aus dem Versionsverlauf herauszuhalten, liegen im gesamten Projekt `example`-Dateien bei.

```text
proxmox-homelab-iac/
├── ansible/
│   ├── roles/
│   │   ├── common/             # Basis-Setup für alle Hosts (Updates, Docker etc.)
│   │   ├── traefik/            # Reverse Proxy Setup & Zertifikatsverwaltung
│   │   │   ├── defaults/       # Standardvariablen (z.B. main_example.yml)
│   │   │   ├── tasks/          # Playbooks für Traefik
│   │   │   └── templates/      # Jinja2 Templates (traefik, nextcloud, vaultwarden etc.)
│   │   └── vaultwarden/        # Passwort-Manager Deployment inkl. Backups
│   │       ├── defaults/       
│   │       ├── tasks/          
│   │       └── templates/      # Jinja2 Templates (docker-compose, backup-script etc.)
│   ├── ansible.cfg             # Globale Ansible Konfiguration
│   ├── inventory.example.ini   # Beispiel für das Host-Inventory
│   ├── site.yml                # Haupt-Playbook
│   └── vars_example.yml        # Globale Variablen
└── terraform/
    ├── main.tf                 # Definition der Proxmox Ressourcen (LXC/VMs)
    ├── variables.tf            # Terraform Variablen
    └── .gitignore
```

** Setup und Verwendung **

Bevor die Skripte ausgeführt werden können, müssen die lokalen Variablen gesetzt werden.

    Alle *example* Dateien (z.B. inventory.example.ini, vars_example.yml, main_example.yml) kopieren und umbenennen (das "example" aus dem Dateinamen entfernen).

    Die eigenen Werte (IP-Adressen, Passwörter, Tokens) in die neuen Dateien eintragen. Die .gitignore sorgt dafür, dass diese Dateien nicht versehentlich ins Repository gepusht werden.

Infrastruktur ausrollen (OpenTofu)

Wechsel in das Terraform-Verzeichnis, um die Container und VMs auf dem Proxmox-Server zu erstellen:

bash
cd terraform
tofu init
tofu plan
tofu apply


** Server konfigurieren (Ansible) **

Sobald die Maschinen laufen, übernimmt Ansible die Installation und Konfiguration der Dienste:

```text
cd ../ansible
ansible-playbook -i inventory.ini site.yml
```

** Projektziele und Learnings **

Dieses Projekt dient mir als praktische Umgebung, um tiefere Erfahrungen im Bereich DevOps und Systemadministration zu sammeln. Schwerpunkte waren dabei der Umgang mit der Proxmox API über Terraform-Provider, das Schreiben idempotenter Ansible Playbooks, das Templating mit Jinja2 sowie die Absicherung der Dienste durch Traefik und Split-DNS.

Erstellt von Eliah Hofmann - LinkedIn (www.linkedin.com/in/eliah-hofmann)
