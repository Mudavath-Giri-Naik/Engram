# Deploy Engram — real, online, professional

Architecture once deployed:

```
  Browser ──> Vercel (web/index.html, the dashboard)
                   │  calls over HTTPS
                   ▼
            Render (FastAPI backend, Docker)
              ├── Render Postgres  (incidents)
              ├── Qdrant Cloud     (vectors)
              └── Google Gemini    (reasoning)

  Real data in:  scripts/capture_devnet.py  ──SSH──>  Cisco DevNet sandbox (real IOS XE)
```

Everything below is free-tier friendly.

---

## 1 · Vector DB — Qdrant Cloud (free)
1. Sign up at https://cloud.qdrant.io and create a **free cluster**.
2. Copy the **cluster URL** (e.g. `https://xxxx.gcp.cloud.qdrant.io:6333`) and an **API key**.
   You'll paste these into Render as `QDRANT_URL` and `QDRANT_API_KEY`.

## 2 · Backend — Render (Docker + managed Postgres)
1. Push this repo to GitHub.
2. Render → **New +** → **Blueprint** → pick your repo. It reads `render.yaml`
   and creates the API service **+ a free Postgres**.
3. Fill the env vars marked "sync:false" in the Render dashboard:
   - `QDRANT_URL`, `QDRANT_API_KEY` — from step 1
   - `LLM_API_KEY` — your Gemini key (https://aistudio.google.com/apikey)
   - `ENGRAM_BOOTSTRAP_API_KEY` — pick any secret string (this is your dashboard login key)
   - `CORS_ORIGINS` — your Vercel URL (add it after step 3, e.g. `https://engram-xyz.vercel.app`)
4. Deploy. On boot the container runs migrations + bootstrap automatically.
   Check `https://<your-api>.onrender.com/health` → `{"status":"ok",...}`.

`DATABASE_URL`, `LLM_PROVIDER=gemini`, `LLM_MODEL=gemini-2.5-flash`,
`EMBEDDING_MODEL=hashing`, and `ENGRAM_BOOTSTRAP_NETWORK_ID` are set for you in `render.yaml`.

> Railway instead of Render? Create a project from the repo (it uses the `Dockerfile`),
> add a Postgres plugin, and set the same env vars. Same result.

## 3 · Frontend — Vercel (static, no build)
1. Vercel → **Add New** → **Project** → import the repo.
2. Set **Root Directory** to `web` (it's a single static `index.html`, no build step).
3. Deploy. Open the URL.
4. Click **⚙︎ Settings** in the app and set:
   - **API URL** = your Render API URL (`https://<your-api>.onrender.com`)
   - **API Key** = the `ENGRAM_BOOTSTRAP_API_KEY` you chose
   Then go back to Render and put this Vercel URL into `CORS_ORIGINS`, redeploy.

That's it — a live, professional dashboard on the internet talking to a real backend.

## 4 · Put REAL Cisco data in
With the backend running (local or Render), pull live output from a **real Cisco IOS XE**
device in Cisco's free DevNet sandbox and store it as an incident:

```bash
# point at your deployed API (or http://localhost:8000 locally)
python scripts/capture_devnet.py --api-url https://<your-api>.onrender.com --api-key <your-key>
```
It SSHes into the sandbox, runs real `show version / ip interface brief / ip route /
running-config | section router bgp`, prints the real output, and ingests it. If the
public credentials have rotated, grab current ones from your DevNet account and pass
`--host --user --password`.

Refresh the dashboard → **Incidents** → you'll see the real Cisco CLI in the timeline.

---

## Run it all locally first (recommended before deploying)
```powershell
# backend (Windows, Docker for pg+qdrant)
docker compose up -d
python -m alembic upgrade head
python -m engram.cli bootstrap
python -m engram.cli serve            # http://localhost:8000

# frontend — just open the file, or serve it:
#   double-click web/index.html, OR:
python -m http.server 5500 --directory web    # then http://localhost:5500
# In the dashboard Settings: API URL http://localhost:8000, key local-dev-key
```

## Security note
The static dashboard sends the API key from the browser — fine for a demo/personal
use. For a hardened public deployment, put the key in a small server-side proxy (or
a Next.js API route) instead of the browser, and lock `CORS_ORIGINS` to your domain.
