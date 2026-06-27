#!/usr/bin/env bash
# Shared helpers for Engram fault-injection scripts.
# Each fault makes a REAL change to the running Containerlab FRR nodes.
set -euo pipefail

LAB="${ENGRAM_LAB:-engram-demo}"
PREFIX="clab-${LAB}"

# Run a vtysh command on an FRR node, e.g.:  rtr R3 "show ip bgp summary"
rtr() {
  local node="$1"; shift
  docker exec "${PREFIX}-${node}" vtysh -c "$*"
}

# Run multiple config lines on a node:  cfg R3 "router bgp 65002" "neighbor X shutdown"
cfg() {
  local node="$1"; shift
  local args=(-c "configure terminal")
  for line in "$@"; do args+=(-c "$line"); done
  docker exec "${PREFIX}-${node}" vtysh "${args[@]}"
  docker exec "${PREFIX}-${node}" vtysh -c "write memory" >/dev/null 2>&1 || true
}

# Run a shell command inside a node (for iptables / ip link MTU faults).
sh_in() {
  local node="$1"; shift
  docker exec "${PREFIX}-${node}" sh -c "$*"
}

banner() { echo; echo "==== $* ===="; }
