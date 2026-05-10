variable "proxmox_api_url" {
    description = "URL zur Proxmox API"
    type = string
}

variable "proxmox_api_token_id" {
  description = "ID des Proxmox API Tokens"
  type        = string
}

variable "proxmox_api_token_secret" {
  description = "Passwort des Tokens mit sensitive true damit dieses nicht in den Logs erscheint"
  type        = string
  sensitive   = true
}


variable "ssh_public_key" {
  description = "Standard SSH-Key für alle Container"
  type        = string
  sensitive   = true
}

variable "lxc_configs" {
  description = "Map für alle LXC-Konfigurationen"
  type = map(object({
    vmid       = number
    target_node = string
    hostname   = string
    template   = string
    ip         = string
    cpu        = number
    memory     = number
    gw         = string
    storage    = string
    size       = string
    nameserver = string
    tags       = string
  }))
}

variable "vm_configs" {
  description = "Konfiguration für die virtuelle Maschine"
  type = map(object({
    vmid      = number
    target_node = string
    name      = string
    clone     = string
    ip        = string
    gw        = string
    cores     = number
    memory    = number
    disk_size = string
    storage   = string
    tags      = string
  }))
}