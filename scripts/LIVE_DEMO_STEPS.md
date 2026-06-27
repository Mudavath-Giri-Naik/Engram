# Engram — manual live demo (real routers, real faults)

Do each step yourself and watch what happens. Real FRR routers, real Cisco-style
CLI (`show ip bgp summary`, etc.), real faults, real incidents.

Terminals you'll use:
- **WSL (Ubuntu)** — only for the `containerlab` commands (it needs Linux).
- **PowerShell** — `docker exec` into routers + Engram (`serve`, `capture`, dashboard).
  (Docker Desktop shares one engine, so containers started in WSL are visible to
  `docker` in PowerShell.)

Keep `python -m engram.cli serve` running in its own PowerShell window the whole time.

---

## PART 0 — one-time setup (WSL + containerlab)

1. Make sure **Docker Desktop** is running, and WSL integration is on
   (Docker Desktop → Settings → Resources → WSL Integration → enable your distro).
2. Open **WSL** (type `wsl` in PowerShell, or open "Ubuntu" from Start).
3. Install containerlab (one line):
   ```bash
   bash -c "$(curl -sL https://get.containerlab.dev)"
   containerlab version       # should print a version
   ```
4. Go to the project's topology folder *inside WSL*:
   ```bash
   cd /mnt/c/Users/Administrator/Desktop/Engram/topology
   ```

---

## PART 1 — start the real router network  (WSL)

```bash
sudo containerlab deploy -t engram-demo.clab.yml
```
**Watch for:** a table listing nodes `clab-engram-demo-R1 … R4`, `h1`, `h2` as running.

If bind-mounts complain on `/mnt/c`, copy the folder into WSL home and run there:
```bash
cp -r /mnt/c/Users/Administrator/Desktop/Engram/topology ~/engram-topo
cd ~/engram-topo && sudo containerlab deploy -t engram-demo.clab.yml
```

---

## PART 2 — confirm the network is healthy  (PowerShell)

```powershell
docker ps --filter "name=clab-engram-demo"
docker exec clab-engram-demo-R2 vtysh -c "show ip bgp summary"
```
**Watch for:** neighbor `10.0.23.3` with a number under `State/PfxRcd` (e.g. `3`) and an
uptime under `Up/Down` — that means BGP is UP (Established). This is your "before".

Prove end-to-end reachability (Site A host to Site B host):
```powershell
docker exec clab-engram-demo-h1 ping -c 3 10.4.4.10
```
**Watch for:** replies (0% loss).

---

## PART 3 — BREAK it (this is the real fault = "Incident #47")  (PowerShell)

Misconfigure R2's BGP neighbor AS (a real, common mistake — a typo in remote-as):
```powershell
docker exec clab-engram-demo-R2 vtysh -c "configure terminal" -c "router bgp 65001" -c "neighbor 10.0.23.3 remote-as 65999"
docker exec clab-engram-demo-R2 vtysh -c "clear ip bgp *"
```
Now look at the damage:
```powershell
docker exec clab-engram-demo-R2 vtysh -c "show ip bgp summary"
```
**Watch for:** neighbor `10.0.23.3` now shows `Active` or `Connect` (NOT a number) —
the session is down. Reachability now breaks:
```powershell
docker exec clab-engram-demo-h1 ping -c 3 10.4.4.10     # should fail / 100% loss
```

(Shortcut equivalent: `bash scripts/faults/bgp_neighbor_down.sh`.)

---

## PART 4 — CAPTURE the real broken output into a transcript  (PowerShell)

```powershell
cd C:\Users\Administrator\Desktop\Engram
"# device: R2"                          | Out-File inc47.txt -Encoding ascii
'$ show ip bgp summary'                 | Out-File inc47.txt -Append -Encoding ascii
docker exec clab-engram-demo-R2 vtysh -c "show ip bgp summary"          | Out-File inc47.txt -Append -Encoding ascii
'$ show ip bgp neighbors 10.0.23.3'     | Out-File inc47.txt -Append -Encoding ascii
docker exec clab-engram-demo-R2 vtysh -c "show ip bgp neighbors 10.0.23.3" | Out-File inc47.txt -Append -Encoding ascii
notepad inc47.txt          # look at the REAL captured output
```
**Watch for:** the file holds the actual broken `show` output from the router.

---

## PART 5 — FIX it for real, confirm recovery  (PowerShell)

```powershell
docker exec clab-engram-demo-R2 vtysh -c "configure terminal" -c "router bgp 65001" -c "neighbor 10.0.23.3 remote-as 65002"
docker exec clab-engram-demo-R2 vtysh -c "clear ip bgp *"
docker exec clab-engram-demo-R2 vtysh -c "show ip bgp summary"     # neighbor UP again
docker exec clab-engram-demo-h1 ping -c 3 10.4.4.10                # replies again
```
(Shortcut equivalent: `bash scripts/faults/heal.sh bgp_neighbor_down`.)

---

## PART 6 — SAVE it as a real incident in Engram  (PowerShell)

Make sure `serve` is running, then:
```powershell
python -m engram.cli capture --host clab-engram-demo-R2 --from-file inc47.txt
```
It will ask you a few questions — answer with what really happened:
- Title: `R2-R3 BGP neighbor down`
- Symptom: `BGP neighbor 10.0.23.3 stuck Active, Site B unreachable`
- Protocols: `BGP`
- Affected layer: `L3`   Scope: `LINK`   Severity: `SEV2`
- Topology hash: `topo-v1`
- Root cause: `remote-as typo (65999 instead of 65002)`
- Fix description: `corrected neighbor remote-as to 65002`
- Commands applied: `neighbor 10.0.23.3 remote-as 65002, clear ip bgp *`
- Outcome: `RESOLVED`   Verification: `ping h1->h2 restored`

**Watch for:** `Ingested incident id = ...`. That's a REAL incident now in Postgres + Qdrant.
Open the dashboard **Incidents** page — you'll see it, with the real captured output in its timeline.

---

## PART 7 — a NEW, similar fault (the "85% like #47" moment)  (PowerShell)

Inject a DIFFERENT root cause that looks the same on the surface (AS-path filter —
session stays UP but routes get filtered):
```powershell
bash scripts/faults/bgp_aspath_variant.sh
docker exec clab-engram-demo-R3 vtysh -c "show ip bgp summary"      # neighbor UP this time
```

Now ask Engram (dashboard **New Fault**, or the command below):
- Description: `Site B (R3) not learning Site A routes; BGP session is up; AS-path filtering suspected`
- Protocols: `BGP`, Layer: `L3`, Devices: `R3,R2`
- Tick **Run LLM comparative reasoning** → **Search memory**

**Watch for:** Engram retrieves your real #47 as the closest match, and Gemini explains
it's similar but the AS-path differs, so the old fix must be adapted — citing the incident.

Heal when done: `bash scripts/faults/heal.sh bgp_aspath_variant`

---

## PART 8 — tear down  (WSL)

```bash
cd /mnt/c/Users/Administrator/Desktop/Engram/topology   # or ~/engram-topo
sudo containerlab destroy -t engram-demo.clab.yml --cleanup
```

---

### The one-sentence pitch while you demo
"When a senior engineer leaves, their troubleshooting knowledge leaves with them.
Engram captures it from the real CLI, and the next time a similar fault hits, it
recalls the exact past incident and adapts the fix — and warns you if a past fix failed."
