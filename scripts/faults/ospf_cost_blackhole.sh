#!/usr/bin/env bash
# FAULT: OSPF cost misconfiguration that blackholes the path to Site B.
# We set an absurd OSPF cost on R3's link to R4 so the route is deprioritized /
# effectively unreachable from Site A's perspective via the normal path.
# Signature Engram will derive: OSPF_COST_BLACKHOLE
source "$(dirname "$0")/_common.sh"

banner "Injecting OSPF cost blackhole: R3 eth1 ospf cost -> 65535"
cfg R3 "interface eth1" "ip ospf cost 65535"

echo "Observe with:"
echo "  docker exec ${PREFIX}-R3 vtysh -c 'show ip ospf interface eth1'  # Cost: 65535"
echo "  docker exec ${PREFIX}-R3 vtysh -c 'show ip route 10.4.4.0/24'    # path cost inflated / withdrawn"
echo "  docker exec ${PREFIX}-h1 ping -c2 10.4.4.10                      # fails / blackholed"
echo
echo "FIX (after capturing the incident): scripts/faults/heal.sh ospf_cost_blackhole"
