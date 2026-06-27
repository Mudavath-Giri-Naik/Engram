#!/usr/bin/env bash
# FAULT: MTU mismatch on the R1<->R2 OSPF link.
# Symptom: OSPF adjacency gets stuck in ExStart/Exchange (DD packets can't pass),
#          routes via that link disappear. Classic MTU-mismatch signature.
# Signature Engram will derive: MTU_MISMATCH
source "$(dirname "$0")/_common.sh"

banner "Injecting MTU mismatch: R2 eth1 -> 9000 (R1 eth1 stays 1500)"
sh_in R2 "ip link set dev eth1 mtu 9000"

echo "Observe with:"
echo "  docker exec ${PREFIX}-R1 vtysh -c 'show ip ospf neighbor'   # stuck ExStart/Exchange"
echo "  docker exec ${PREFIX}-R1 vtysh -c 'show interface eth1'      # mtu 1500"
echo "  docker exec ${PREFIX}-R2 vtysh -c 'show interface eth1'      # mtu 9000"
echo
echo "FIX (after capturing the incident): scripts/faults/heal.sh mtu_mismatch"
