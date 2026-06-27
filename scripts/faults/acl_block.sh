#!/usr/bin/env bash
# FAULT: an ACL that silently drops a needed flow.
# Implemented as a data-plane filter on R4 dropping TCP/5432 (Postgres) from h1
# to h2 — connectivity "works" (ping ok) but the application flow is dropped.
# Signature Engram will derive: ACL_BLOCK
source "$(dirname "$0")/_common.sh"

banner "Injecting ACL block: drop TCP 5432 to h2 (10.4.4.10) on R4"
sh_in R4 "iptables -A FORWARD -p tcp --dport 5432 -d 10.4.4.10 -j DROP"

echo "Observe with:"
echo "  docker exec ${PREFIX}-h1 ping -c2 10.4.4.10                       # OK (icmp passes)"
echo "  docker exec ${PREFIX}-h1 nc -vz -w3 10.4.4.10 5432                # TIMES OUT (silently dropped)"
echo "  docker exec ${PREFIX}-R4 iptables -L FORWARD -n -v               # see the deny rule"
echo
echo "FIX (after capturing the incident): scripts/faults/heal.sh acl_block"
