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


resource "proxmox_vm_qemu" "vms" {
  for_each = var.vm_configs
  name        = each.value.name
  target_node = each.value.target_node
  vmid        = each.value.vmid
  clone       = each.value.clone

  agent   = 1
  os_type = "cloud-init"
  memory  = each.value.memory
  scsihw  = "virtio-scsi-pci"

  cpu {
    cores   = each.value.cores
    sockets = 1
    type    = "host"
  }

  disk {
    slot    = "scsi0"
    size    = each.value.disk_size
    type    = "disk"
    storage = each.value.storage
    discard = "1"
  }

  disk {
    slot    = "ide2"
    type    = "cloudinit"
    storage = each.value.storage
  }

  network {
    id     = 0
    model  = "virtio"
    bridge = "vmbr0"
  }

  serial {
    id   = 0
    type = "socket"
  }

  vga {
    type = "serial0"
  }

  timeouts {
    create = "5m"
  }

  boot = "order=scsi0"
  ipconfig0 = "ip=${each.value.ip},gw=${each.value.gw}"
  ciuser    = "root"
  sshkeys   = var.ssh_public_key
}


resource "proxmox_lxc" "containers" {
  for_each = var.lxc_configs

  target_node = each.value.target_node
  vmid        = each.value.vmid
  hostname    = each.value.hostname
  ostemplate  = each.value.template
  
  ssh_public_keys = var.ssh_public_key
  unprivileged    = true
  start           = true
  onboot          = true

  cores  = each.value.cpu
  memory = each.value.memory

  rootfs {
    storage = each.value.storage
    size    = each.value.size
  }

  nameserver = each.value.nameserver

  network {
    name     = "eth0"
    bridge   = "vmbr0"
    ip       = each.value.ip
    gw       = each.value.gw
    firewall = true
  }

  features {
    nesting = true
  }
}