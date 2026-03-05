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

variable "test_password" {
  description = "Das Passwort vom test-lxc"
  type        = string
  sensitive   = true

}

variable "test_ip_adresse" {
  description = "Die IP-Adresse des test-lxc"
  type        = string
}

variable "gateway" {
  description = "Die IP-Adresse des Gateways des Netzwerks"
  type        = string
}