vm_configs = {
  "monitoring" = {
    vmid      = 400
    target_node = "dell-optiplex-melchior"
    name      = "monitoring"
    clone     = "debian-12-cloudinit"
    ip        = "192.168.178.60/24"
    gw        = "192.168.178.1"
    cores     = 4
    memory    = 4096
    disk_size = "100G"
    storage   = "local-lvm"
    tags      = "monitoring"
  }
}


lxc_configs = {
  "adguard" = {
    vmid       = 100
    target_node = "dell-optiplex-melchior"
    hostname   = "adguard-dns"
    ip         = "192.168.178.30/24"
    cpu        = 1
    memory     = 512
    gw         = "192.168.178.1"
    size       = "4G"
    storage    = "local-lvm"
    nameserver = "1.1.1.1"
    tags       = "adguard"
  },
  "traefik" = {
    vmid       = 101
    target_node = "dell-optiplex-melchior"
    hostname   = "traefik"
    ip         = "192.168.178.31/24"
    cpu        = 1
    memory     = 512
    gw         = "192.168.178.1"
    size       = "4G"
    storage    = "local-lvm"
    nameserver = "1.1.1.1"
    tags       = "traefik"
  },
  "cloudflare" = {
    vmid       = 102
    target_node = "dell-optiplex-melchior" 
    hostname   = "cloudflare-tunnel"
    ip         = "192.168.178.32/24"
    cpu        = 1
    memory     = 512
    gw         = "192.168.178.1"
    size       = "5G"
    storage    = "local-lvm"
    nameserver = "1.1.1.1"
    tags       = "cloudflared"
  },
  "collabora" = {
    vmid       = 201
    target_node = "hp-server-balthasar" 
    hostname   = "collabora"
    ip         = "192.168.178.81/24"
    cpu        = 4
    memory     = 8192
    gw         = "192.168.178.1"
    size       = "8G"
    storage    = "local-lvm"
    nameserver = "1.1.1.1"
    tags       = "collabora"
  },
  "vaultwarden" = {
    vmid       = 202
    target_node = "dell-optiplex-melchior"
    hostname   = "vaultwarden-server"
    ip         = "192.168.178.82/24"
    cpu        = 1
    memory     = 512
    gw         = "192.168.178.1"
    size       = "15G"
    storage    = "local-lvm"
    nameserver = "1.1.1.1"
    tags       = "vaultwarden"
  },
  "affine" = {
    vmid       = 203
    target_node = "hp-server-balthasar" 
    hostname   = "affine"
    ip         = "192.168.178.83/24"
    cpu        = 4
    memory     = 4096
    gw         = "192.168.178.1"
    size       = "25G"
    storage    = "local-lvm"
    nameserver = "1.1.1.1"
    tags       = "affine"
  },
  "immich" = {
    vmid       = 204
    target_node = "hp-server-balthasar" 
    hostname   = "immich"
    ip         = "192.168.178.84/24"
    cpu        = 4
    memory     = 4096
    gw         = "192.168.178.1"
    size       = "200G"
    storage    = "local-lvm"
    nameserver = "1.1.1.1"
    tags       = "immich"
  },
    "qwen3" = {
    vmid       = 205
    target_node = "hp-server-balthasar" 
    hostname   = "qwen3"
    ip         = "192.168.178.85/24"
    cpu        = 6
    memory     = 12288
    gw         = "192.168.178.1"
    size       = "100G"
    storage    = "local-lvm"
    nameserver = "1.1.1.1"
    tags       = "qwen3"
  },
  "paperless_ngx" = {
    vmid       = 206
    target_node = "hp-server-balthasar" 
    hostname   = "paperless-ngx"
    ip         = "192.168.178.86/24"
    cpu        = 2
    memory     = 4096
    gw         = "192.168.178.1"
    size       = "20G"
    storage    = "local-lvm"
    nameserver = "1.1.1.1"
    tags       = "paperless"
  },
    "finance_stack" = {
    vmid       = 207
    target_node = "hp-server-balthasar" 
    hostname   = "ActualBudget"
    ip         = "192.168.178.87/24"
    cpu        = 2
    memory     = 2048
    gw         = "192.168.178.1"
    size       = "10G"
    storage    = "local-lvm"
    nameserver = "1.1.1.1"
    tags       = "ActualBudget"
    }
}