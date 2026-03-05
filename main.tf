terraform {
  required_providers {
    proxmox = {
      source = "telmate/proxmox"
      version = "3.0.2-rc07"
    }
  }
}

provider "proxmox" {
  pm_api_url          = var.proxmox_api_url
  pm_api_token_id     = var.proxmox_api_token_id
  pm_api_token_secret = var.proxmox_api_token_secret
  pm_tls_insecure     = true
}

resource "proxmox_lxc" "vaultwarden" {
  target_node         = "pve"
  hostname            = "vaultwarden-server"
  ostemplate          = "local:vztmpl/debian-13-standard_13.1-2_amd64.tar.zst"
  ssh_public_keys     = var.ssh_public_key_vaultwarden
  unprivileged        = true
  cores               = 1
  memory              = 512

  rootfs {
    storage = "local-lvm"
    size    = "15G"
  }


  network {
    name             = "eth0"
    bridge           = "vmbr0"
    ip               = var.test_ip_adresse
    gw               = var.gateway
    firewall         = true
  }
}