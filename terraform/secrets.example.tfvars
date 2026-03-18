# --- Proxmox API Zugangsdaten ---
# Ersetze die Werte durch deine eigenen Daten.
proxmox_api_url          = "https://192.1.1.2:8006/api2/json"
proxmox_api_token_id     = "terraform-user@pve!token-name"
proxmox_api_token_secret = "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"

# öffentlicher SSH-Key für den Zugriff auf alle Instanzen
ssh_public_key = "ssh-ed25519 AAAA... dein-benutzer@dein-pc"

vm_configs = {
  "monitoring" = {
    vmid      = 400
    name      = "monitoring"
    clone     = "debian-12-cloudinit"
    ip        = "192.1.1.10/24"
    gw        = "192.1.1.1"
    cores     = 4
    memory    = 4096
    disk_size = "100G"
    storage   = "local-lvm"
  }
}


#Alle Container in einer Liste
lxc_configs = {
  "service-1" = {
    vmid       = 100
    hostname   = "vault-server"
    template = "local:vztmpl/debian-12-standard_12.12-1_amd64.tar.zst"
    ip         = "192.1.1.11/24"
    cpu        = 1
    memory     = 512
    gw         = "192.1.1.1"
    size       = "15G"
    storage    = "local-lvm"
    nameserver = "1.1.1.1"
  },
  "service-2" = {
    vmid       = 101
    hostname   = "cloud-server"
    template = "local:vztmpl/debian-12-standard_12.12-1_amd64.tar.zst"
    ip         = "192.1.1.12/24"
    cpu        = 2
    memory     = 2048
    gw         = "192.1.1.1"
    size       = "15G"
    storage    = "local-lvm"
    nameserver = "1.1.1.1"
  },
    "service-3" = {
    vmid       = 102
    hostname   = "tunnel-server"
    template = "local:vztmpl/debian-12-standard_12.12-1_amd64.tar.zst"
    ip         = "192.1.1.13/24"
    cpu        = 1
    memory     = 512
    gw         = "192.1.1.1"
    size       = "2G"
    storage    = "local-lvm"
    nameserver = "1.1.1.1"
  },
  "service-4" = {
    vmid       = 103
    hostname   = "reverse-proxy"
    template = "local:vztmpl/debian-12-standard_12.12-1_amd64.tar.zst"
    ip         = "192.1.1.14/24"
    cpu        = 1
    memory     = 512
    gw         = "192.1.1.1"
    size       = "4G"
    storage    = "local-lvm"
    nameserver = "1.1.1.1"
    },
    "service-5" = {
    vmid       = 104
    hostname   = "cloud-service"
    template = "local:vztmpl/debian-12-standard_12.12-1_amd64.tar.zst"
    ip         = "192.1.1.15/24"
    cpu        = 4
    memory     = 8192
    gw         = "192.1.1.1"
    size       = "8G"
    storage    = "local-lvm"
    nameserver = "1.1.1.1"
    },
    "service-6" = {
    vmid       = 105
    hostname   = "adguard-service"
    template = "local:vztmpl/debian-12-standard_12.12-1_amd64.tar.zst"
    ip         = "192.1.1.16/24"
    cpu        = 1
    memory     = 512
    gw         = "1192.1.1.1"
    size       = "4G"
    storage    = "local-lvm"
    nameserver = "1.1.1.1"
    },
    "service-7" = {
    vmid       = 106
    hostname   = "creative-cloud-service"
    template = "local:vztmpl/debian-12-standard_12.12-1_amd64.tar.zst"
    ip         = "192.1.1.16/24"
    cpu        = 4
    memory     = 4096
    gw         = "192.1.1.1"
    size       = "25G"
    storage    = "local-lvm"
    nameserver = "1.1.1.1"
    }
}