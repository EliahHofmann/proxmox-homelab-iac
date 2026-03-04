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