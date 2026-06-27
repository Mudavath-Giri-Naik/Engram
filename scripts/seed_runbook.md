# Engram seed runbook — generate REAL incidents

Following these steps produces genuine incidents from a real (virtual) network.
No data is fabricated: every incident comes from a fault you actually inject and
troubleshoot on FRR routers running under Containerlab.

## Prerequisites
- Docker + [Containerlab](https://containerlab.dev/install/) installed (Linux, or
  WSL2/Docker Desktop on Windows/Mac).
- Engram running: `docker compose up -d && make migrate && make api`
  (API at http://localhost:8000). The dashboard is optional: `make dashboard`.
- Your `.env.local` has `ENGRAM_BOOTSTRAP_API_KEY` + `ENGRAM_BOOTSTRAP_NETWORK_ID`
  set (these seed the tenant the capture CLI posts to), and `DEVICE_SSH_*` only
  matter for live SSH capture — the fault scripts here use `docker exec`, and you
  can capture via transcript files without SSH.

## 1. Deploy the demo network
```bash
cd topology
sudo containerlab deploy -t engram-demo.clab.yml
# verify
docker exec clab-engram-demo-R2 vtysh -c "show ip bgp summary"   # neighbor Established
docker exec clab-engram-demo-h1 ping -c2 10.4.4.10               # Site A -> Site B works
```
Topology hash for this baseline: use `topo-v1` (any stable label). Re-use the SAME
hash on incidents recorded against this wiring so staleness detection is meaningful.

## 2. Record Incident #47 — BGP neighbor down (the anchor incident)
```bash
# inject
bash scripts/faults/bgp_neighbor_down.sh
# investigate (capture raw output to a transcript)
{
  echo "# device: R2"
  echo '$ show ip bgp summary';            docker exec clab-engram-demo-R2 vtysh -c "show ip bgp summary"
  echo '$ show ip bgp neighbors 10.0.23.3'; docker exec clab-engram-demo-R2 vtysh -c "show ip bgp neighbors 10.0.23.3"
  echo '$ show running-config bgpd';        docker exec clab-engram-demo-R2 vtysh -c "show running-config"
} > /tmp/inc47.txt

# fix it
bash scripts/faults/heal.sh bgp_neighbor_down
docker exec clab-engram-demo-R2 vtysh -c "show ip bgp summary"   # Established again

# ingest the incident (interactive prompts: title, symptom, protocols=BGP,
# layer=L3, scope=LINK, severity=SEV2, root cause="neighbor remote-as typo",
# fix="corrected remote-as to 65002", outcome=RESOLVED, topology hash=topo-v1)
engram capture --host clab-engram-demo-R2 --from-file /tmp/inc47.txt
```
Note the incident id printed — this is the "#47" you'll see matched later.

## 3. Record an MTU-mismatch incident
```bash
bash scripts/faults/mtu_mismatch.sh
{
  echo "# device: R1"
  echo '$ show ip ospf neighbor';  docker exec clab-engram-demo-R1 vtysh -c "show ip ospf neighbor"
  echo '$ show interface eth1';    docker exec clab-engram-demo-R1 vtysh -c "show interface eth1"
  echo "# device: R2"
  echo '$ show interface eth1';    docker exec clab-engram-demo-R2 vtysh -c "show interface eth1"
} > /tmp/mtu.txt
bash scripts/faults/heal.sh mtu_mismatch
engram capture --host clab-engram-demo-R1 --from-file /tmp/mtu.txt
# protocols=OSPF,MTU  layer=L3  signature auto -> MTU_MISMATCH  outcome=RESOLVED
```

## 4. Record a FAILED-then-SUCCEEDED incident (proves failure memory)
This is the important one. First fix FAILS, is recorded as FAILED, second fix works.
```bash
bash scripts/faults/ospf_cost_blackhole.sh           # blackhole Site B path
{
  echo "# device: R3"
  echo '$ show ip ospf interface eth1'; docker exec clab-engram-demo-R3 vtysh -c "show ip ospf interface eth1"
  echo '$ show ip route 10.4.4.0/24';   docker exec clab-engram-demo-R3 vtysh -c "show ip route 10.4.4.0/24"
} > /tmp/blackhole.txt

# Capture with a WRONG first hypothesis recorded as FAILED:
engram capture --host clab-engram-demo-R3 --from-file /tmp/blackhole.txt
#   title: "Site B unreachable - tried clearing OSPF"
#   root cause (wrong): "suspected stale LSDB"
#   fix: "cleared ip ospf process"   outcome=FAILED   verification=ping still fails
# -> records a FAILED fix into memory.

# Now the real fix and a SECOND incident recorded as RESOLVED:
bash scripts/faults/heal.sh ospf_cost_blackhole
docker exec clab-engram-demo-h1 ping -c2 10.4.4.10   # works now
engram capture --host clab-engram-demo-R3 --from-file /tmp/blackhole.txt
#   root cause: "OSPF cost 65535 on R3 eth1 blackholed path"
#   fix: "removed ip ospf cost override"  outcome=RESOLVED
```
You can also flip an existing incident to FAILED directly via the API:
```bash
curl -X PATCH localhost:8000/v1/incidents/<id>/outcome \
  -H "X-API-Key: $ENGRAM_BOOTSTRAP_API_KEY" -H 'Content-Type: application/json' \
  -d '{"status":"FAILED","verification_method":"ping still failed","verified":true}'
```

## 5. THE DEMO — trigger the AS-path variant ("85% like Incident #47")
```bash
bash scripts/faults/bgp_aspath_variant.sh
# Same symptom as #47 (Site B not learning Site A routes) but session stays UP.
```
Now ask Engram (this is what an AIOps system would call):
```bash
curl -s -X POST localhost:8000/v1/query \
  -H "X-API-Key: $ENGRAM_BOOTSTRAP_API_KEY" -H 'Content-Type: application/json' \
  -d '{
    "network_id":"ignored-from-auth",
    "description":"Site B (R3) suddenly not learning Site A routes; BGP session looks up though; AS-path filtering suspected",
    "protocols":["BGP"], "affected_layer":"L3", "devices":["R3","R2"],
    "current_topology_hash":"topo-v1"
  }' | python -m json.tool
```
Expect: Incident #47 retrieved as the closest match (shared signature/protocol/
device), with the LLM noting the **AS-path difference** and adapting the fix —
and a warning surfaced if a prior related fix was recorded FAILED. Open the
dashboard's **New Fault** page to see the same result visually.

Heal when done:
```bash
bash scripts/faults/heal.sh bgp_aspath_variant
```

## Tear down
```bash
cd topology && sudo containerlab destroy -t engram-demo.clab.yml --cleanup
```
