#!/usr/bin/env bash
# FAULT: the "85% like Incident #47" demo.
# Same VISIBLE symptom as bgp_neighbor_down (Site B stops learning Site A routes),
# but a DIFFERENT root cause: an AS-path access-list on R3 silently filters routes
# whose AS-path is "65001" inbound. The BGP session stays UP — so the Feb fix
# (correcting a remote-as typo) would NOT work here; the fix must adapt.
# Signature Engram will derive: BGP_ASPATH_ISSUE
source "$(dirname "$0")/_common.sh"

banner "Injecting BGP AS-path filter variant on R3 (session stays UP, routes filtered)"
cfg R3 \
  "bgp as-path access-list FILTER-SITEA seq 5 deny ^65001\$" \
  "bgp as-path access-list FILTER-SITEA seq 10 permit .*" \
  "route-map DENY-SITEA permit 10" \
  "  match as-path FILTER-SITEA" \
  "router bgp 65002" \
  "address-family ipv4 unicast" \
  "neighbor 10.0.23.2 route-map DENY-SITEA in"
rtr R3 "clear ip bgp * soft in" >/dev/null 2>&1 || true

echo "Observe with:"
echo "  docker exec ${PREFIX}-R3 vtysh -c 'show ip bgp summary'                 # neighbor is UP (Established!)"
echo "  docker exec ${PREFIX}-R3 vtysh -c 'show ip bgp neighbors 10.0.23.2 routes'  # Site A routes missing/filtered"
echo "  docker exec ${PREFIX}-R3 vtysh -c 'show bgp as-path-access-list'         # the filter"
echo
echo "Compare to Incident #47 (bgp_neighbor_down): SAME symptom, DIFFERENT as-path root cause."
echo "FIX (after capturing the incident): scripts/faults/heal.sh bgp_aspath_variant"
