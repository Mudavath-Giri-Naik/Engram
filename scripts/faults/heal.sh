#!/usr/bin/env bash
# Undo a previously injected fault. Usage: scripts/faults/heal.sh <scenario>
# Scenarios: mtu_mismatch | bgp_neighbor_down | ospf_cost_blackhole | acl_block | bgp_aspath_variant
source "$(dirname "$0")/_common.sh"

scenario="${1:-}"
case "$scenario" in
  mtu_mismatch)
    banner "Healing MTU mismatch: R2 eth1 -> 1500"
    sh_in R2 "ip link set dev eth1 mtu 1500"
    ;;
  bgp_neighbor_down)
    banner "Healing BGP neighbor down: R2 remote-as -> 65002"
    cfg R2 "router bgp 65001" "neighbor 10.0.23.3 remote-as 65002"
    rtr R2 "clear ip bgp *" >/dev/null 2>&1 || true
    ;;
  ospf_cost_blackhole)
    banner "Healing OSPF cost blackhole: R3 eth1 cost -> default (10)"
    cfg R3 "interface eth1" "no ip ospf cost"
    ;;
  acl_block)
    banner "Healing ACL block: removing FORWARD drop on R4"
    sh_in R4 "iptables -D FORWARD -p tcp --dport 5432 -d 10.4.4.10 -j DROP || true"
    ;;
  bgp_aspath_variant)
    banner "Healing BGP as-path variant: removing route-map on R3"
    cfg R3 \
      "router bgp 65002" \
      "address-family ipv4 unicast" \
      "no neighbor 10.0.23.2 route-map DENY-SITEA in"
    rtr R3 "clear ip bgp * soft in" >/dev/null 2>&1 || true
    ;;
  *)
    echo "Unknown scenario: '$scenario'"
    echo "Usage: $0 {mtu_mismatch|bgp_neighbor_down|ospf_cost_blackhole|acl_block|bgp_aspath_variant}"
    exit 1
    ;;
esac
echo "Done. Re-verify the relevant show commands."
