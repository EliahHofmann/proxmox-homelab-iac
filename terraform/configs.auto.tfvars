vm_configs = {
  "monitoring" = {
    vmid      = 400
    target_node = "dell-optiplex-melchior"
    name      = "monitoring"
    clone     = "debian-12-cloudinit"
    tags      = "monitoring"
    ip        = "192.168.178.60/24"
    gw        = "192.168.178.1"
    cores     = 4
    memory    = 4096
    disk_size = "100G"
    storage   = "local-lvm"
  }
}


lxc_configs = {
  "adguard" = {
    vmid       = 100
    target_node = "dell-optiplex-melchior"
    hostname   = "adguard-dns"
    template   = "local:vztmpl/debian-12-standard_12.12-1_amd64.tar.zst"
    tags      = "adguard"
    ip         = "192.168.178.30/24"
    cpu        = 1
    memory     = 512
    gw         = "192.168.178.1"
    size       = "4G"
    storage    = "local-lvm"
    nameserver = "1.1.1.1"
  },
  "traefik" = {
    vmid       = 101
    target_node = "dell-optiplex-melchior"
    hostname   = "traefik"
    template   = "local:vztmpl/debian-12-standard_12.12-1_amd64.tar.zst"
    tags      = "traefik"
    ip         = "192.168.178.31/24"
    cpu        = 1
    memory     = 512
    gw         = "192.168.178.1"
    size       = "4G"
    storage    = "local-lvm"
    nameserver = "1.1.1.1"
  },
  "cloudflare" = {
    vmid       = 102
    target_node = "dell-optiplex-melchior" 
    hostname   = "cloudflare-tunnel"
    template   = "local:vztmpl/debian-12-standard_12.12-1_amd64.tar.zst"
    tags      = "cloudflare"
    ip         = "192.168.178.32/24"
    cpu        = 1
    memory     = 512
    gw         = "192.168.178.1"
    size       = "2G"
    storage    = "local-lvm"
    nameserver = "1.1.1.1"
  },
  "collabora" = {
    vmid       = 201
    target_node = "hp-server-balthasar" 
    hostname   = "collabora"
    template   = "local:vztmpl/debian-12-standard_12.12-1_amd64.tar.zst"
    tags      = "collabora"
    ip         = "192.168.178.81/24"
    cpu        = 4
    memory     = 8192
    gw         = "192.168.178.1"
    size       = "8G"
    storage    = "local-lvm"
    nameserver = "1.1.1.1"
  },
  "vaultwarden" = {
    vmid       = 202
    target_node = "dell-optiplex-melchior"
    hostname   = "vaultwarden-server"
    template   = "local:vztmpl/debian-12-standard_12.12-1_amd64.tar.zst"
    tags      = "vaultwarden"
    ip         = "192.168.178.82/24"
    cpu        = 1
    memory     = 512
    gw         = "192.168.178.1"
    size       = "15G"
    storage    = "local-lvm"
    nameserver = "1.1.1.1"
  },
  "affine" = {
    vmid       = 203
    target_node = "hp-server-balthasar" 
    hostname   = "affine"
    template   = "local:vztmpl/debian-12-standard_12.12-1_amd64.tar.zst"
    tags      = "affine"
    ip         = "192.168.178.83/24"
    cpu        = 4
    memory     = 4096
    gw         = "192.168.178.1"
    size       = "25G"
    storage    = "local-lvm"
    nameserver = "1.1.1.1"
  },
  "immich" = {
    vmid       = 204
    target_node = "hp-server-balthasar" 
    hostname   = "immich"
    template   = "local:vztmpl/debian-12-standard_12.12-1_amd64.tar.zst"
    tags      = "immich"
    ip         = "192.168.178.84/24"
    cpu        = 4
    memory     = 4096
    gw         = "192.168.178.1"
    size       = "200G"
    storage    = "local-lvm"
    nameserver = "1.1.1.1"
  },
    "qwen3" = {
    vmid       = 205
    target_node = "hp-server-balthasar" 
    hostname   = "qwen3"
    template   = "local:vztmpl/debian-12-standard_12.12-1_amd64.tar.zst"
    tags      = "qwen3"
    ip         = "192.168.178.85/24"
    cpu        = 6
    memory     = 12288
    gw         = "192.168.178.1"
    size       = "100G"
    storage    = "local-lvm"
    nameserver = "1.1.1.1"
  },
  "consul" = {
    vmid       = 403
    target_node = "dell-optiplex-melchior" 
    hostname   = "consul"
    template   = "local:vztmpl/debian-12-standard_12.12-1_amd64.tar.zst"
    tags      = "consul"
    ip         = "192.168.178.63/24"
    cpu        = 1
    memory     = 512
    gw         = "192.168.178.1"
    size       = "2G"
    storage    = "local-lvm"
    nameserver = "1.1.1.1"
  }
}