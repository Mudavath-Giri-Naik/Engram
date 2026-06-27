#!/usr/bin/env bash
# FAULT: BGP neighbor down on the R2<->R3 eBGP session (Incident "#47").
# Root cause modelled: remote-as typo. We change R2's view of R3's AS to a wrong
# value so the session never establishes (stuck Active/Connect).
# Signature Engram will derive: BGP_NEIGHBOR_DOWN
source "$(dirname "$0")/_common.sh"

banner "Injecting BGP neighbor down: R2 remote-as 65002 -> 65999 (typo)"
cfg R2 "router bgp 65001" "neighbor 10.0.23.3 remote-as 65999"
# Clear so the change takes effect immediately.
rtr R2 "clear ip bgp *" >/dev/null 2>&1 || true

echo "Observe with:"
echo "  docker exec ${PREFIX}-R2 vtysh -c 'show ip bgp summary'              # 10.0.23.3 Active/Idle"
echo "  docker exec ${PREFIX}-R2 vtysh -c 'show ip bgp neighbors 10.0.23.3'  # remote AS 65999"
echo
echo "FIX (after capturing the incident): scripts/faults/heal.sh bgp_neighbor_down"
