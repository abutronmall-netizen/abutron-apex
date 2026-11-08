# Deploying APEX to a managed host

Target: **Render** (primary), with an equivalent **fly.io** config. Both run the same
container, keep a persistent disk, and are told to never scale a trading loop to zero.

The point of a server is not that APEX runs faster. Three things are blocked here that a
hosted box unblocks:

| Blocked in the build sandbox | Unblocked on a managed host |
|---|---|
| `ws.derivws.com` returns HTTP 520 (the five synthetics were never tested live) | normal egress → Deriv demo feed works |
| Yahoo throttles the IP → no hourly equities | 5× the samples for the next backtest |
| Nothing survives between turns — no 24/7 loop | weeks of continuous paper trading |

---

## 1. Architecture: one service, one disk, three roles

Managed hosts attach a volume to a *single* service, so the collector and the trader
cannot share a disk from separate services. Everything therefore runs in one container
under supervisord, with roles selected by `APEX_ROLES`:

| Role | Process | Writes to the volume |
|---|---|---|
| `web` | `scripts/run_server.py` — dashboard + API + paper loop | `state/`, `results/` |
| `collector` | `scripts/collect.py --every 60` — bars, ticks, MANIFEST | `data_cache/` |
| `trader` | `scripts/run_deriv.py --live-demo` — Deriv demo orders | `state/`, `logs/` |

`trader` refuses to start without `DERIV_API_TOKEN`, and `DerivClient` hard-refuses any
account where `is_virtual == 0`. **Demo only, by construction.**

```
$APEX_DATA_DIR (/var/data)   ← the only thing that must persist
  state/       memory.json, decisions.jsonl
  results/     reports, sweeps
  data_cache/  OHLCV CSVs + ticks/ + MANIFEST.json
  logs/
```

The image itself is disposable; `/var/data` is the asset.

---

## 2. Secrets — the host holds exactly one token

The container is given a **bootstrap** token and nothing else. At boot `apex/secrets.py`
pulls the rest from your secrets manager into the process environment:

```bash
APEX_SECRETS=doppler                 # or: infisical | file | env
DOPPLER_TOKEN=dp.st.prd.xxxxx        # the only value typed into the host dashboard
DOPPLER_PROJECT=apex
DOPPLER_CONFIG=prd
```

Infisical: `APEX_SECRETS=infisical`, `INFISICAL_TOKEN`, `INFISICAL_PROJECT_ID`,
optional `INFISICAL_ENV` / `INFISICAL_HOST`.
File: `APEX_SECRETS=file`, `APEX_SECRETS_FILE=/run/secrets/apex.json` (chmod 600).

Put these in the manager, never in the repo:

| Name | Needed for | Notes |
|---|---|---|
| `DERIV_API_TOKEN` | `trader` role | **demo account token only** (`app.deriv.com → Settings → API token`, scope *Read + Trade*, virtual account) |
| `APEX_LLM_API_KEY` | optional advisor | leave unset → heuristic advisor |

Guarantees, all tested:

* a host-level env var **always wins** over the manager (nothing is silently overwritten);
* values are never logged — `secrets.status()` reports provider, names, and a redacted
  fingerprint (`abc*****efgh`);
* an unknown provider or an unreachable manager **fails loudly** (`SecretsError`);
* a secret load failure does **not** crash the app — it drops to paper mode and says so.

---

## 3. Deploy on Render

```bash
# once, locally
git push origin main

# in the Render dashboard: New → Blueprint → point at this repo
# render.yaml provisions the service, disk and health check
```

Then set, in *Environment*: `APEX_SECRETS` and `DOPPLER_TOKEN`. Nothing else.

Defaults applied by `render.yaml`: starter plan, Frankfurt (closest to Deriv's edge),
5 GB disk at `/var/data`, health check `/healthz`, `autoDeploy: true`.

**fly.io** instead — same container, single machine, volume:

```bash
fly launch --no-deploy --copy-config --name apex-desk
fly volumes create apex_data --size 5 --region fra
fly secrets set APEX_SECRETS=doppler DOPPLER_TOKEN=dp.st.prd.xxxxx
fly deploy
```

`auto_stop_machines = "off"` and `min_machines_running = 1` are deliberate: a stopped
machine is a stopped trading loop.

---

## 4. Verifying a deploy in 60 seconds

```bash
curl -s https://<host>/healthz | python3 -m json.tool
```

```json
{
  "role": "web",
  "uptime_s": 138.4,
  "runner_started": true,
  "runner_running": true,
  "bars": 132,
  "memory_settled": 24400,
  "disk_free_gb": 4.812,
  "secrets": {"provider": "doppler", "loaded_count": 2, "has_deriv_token": true,
              "deriv_token": "abc*****efgh"},
  "data_dir": "/var/data",
  "ok": true
}
```

`/healthz` returns **503** when the loop is not stepping or the disk is nearly full, so
the platform restarts a wedged container instead of serving a dead dashboard. The
Dockerfile `HEALTHCHECK` uses the same endpoint.

Then watch the collector build the dataset:

```bash
curl -s https://<host>/api/state | head -c 400
# and on the box / via the Render shell:
cat /var/data/data_cache/MANIFEST.json | python3 -m json.tool
```

The manifest is the inventory: rows, first/last bar and last fetch per symbol. It is the
first thing to check when a measurement looks wrong.

---

## 5. What I'd do in the first 48 hours

1. **Prove the synthetics.** `APEX_ROLES=web,collector,trader` with the Deriv demo token;
   watch the signal→order tape for R_75/R_100/BOOM500/CRASH500/stpRNG. This is the first
   time those five are traded against a live feed.
2. **Bank the data.** Hourly equities + Deriv ticks piling up in `data_cache/`. Every day
   of uptime is +24 hourly bars per instrument that the sandbox could not fetch.
3. **Re-measure honestly.** When `MANIFEST.json` shows ~5,000 hourly equity bars, re-run
   `make real` + `make ablate` against a sample 3× larger than the 1,453 daily bars behind
   the current verdict (Sharpe 0.94 vs 1.20; PF 0.89 at the design frequency).
4. **Then attack the Sharpe gap** — ex-ante sizing instead of realised-vol scaling, and
   the regime detector. That is research; the server buys data, not alpha.

---

## 6. Cost and guardrails

Starter plan + 5 GB disk ≈ **$7–9/month** on Render; `shared-cpu-1x` + 5 GB volume is
roughly the same on fly.io. The loop is ~0.05 CPU and a few MB of RAM — the disk, not the
CPU, is the constraint.

Guardrails that are already in the code:

* demo-only enforcement in `DerivClient` (`require_demo=True`);
* `trader` role silently skipped when no token is present;
* per-instrument / per-class / gross / net caps and a 12% drawdown kill switch in the risk
  governor — a hosted loop cannot run away with the account;
* atomic file writes (`*.tmp` + `os.replace`) so a hard kill never corrupts state;
* restart-safe: memory, decisions and the data cache are all on the volume and re-read at
  boot.

**Docker note:** the image could not be built inside the build sandbox (no Docker daemon).
Everything the container does was exercised directly instead — `deploy/entrypoint.py`
secrets → layout → supervisord → web role → `GET /healthz` → `200 ok:true` — and that
path is covered by tests. Expect the first real `docker build` to be the moment anything
image-specific (base image, permissions) shows up.

---

## 7. Connecting this workspace to your deployment

The build sandbox can only reach domains on its egress allowlist — an arbitrary IP
returns a stub (test: `http://192.0.2.1/`, an unroutable documentation address, answers
**404** from the proxy). So a bare `http://<public-ip>:8000` cannot be reached from here
no matter what the firewall says. Three ways around it, cheapest first.

**A. Paste a report (zero exposure).** On the box:

```bash
python3 scripts/remote_report.py            # reads localhost:8000, prints JSON
```

The output is deliberately safe to paste: no tokens, no account ids, secrets stripped by
key name, and it never touches `/api/control`. Give me that and I can diagnose the desk,
the memory matrix, the fills and the data cache as if I were on the box.

**B. Quick tunnel (live polling).** `trycloudflare.com`, `ngrok-free.app` and
`localtunnel.me` are all reachable from here (verified). On the box:

```bash
cloudflared tunnel --url http://localhost:8000     # prints https://<name>.trycloudflare.com
```

Send me that URL and I can poll `/healthz` and `/api/state` each turn. Kill the tunnel
when you are done — it is a temporary hole. Put the tunnel in front of the *dashboard*,
never in front of `/api/control` with the door open.

**C. Git channel (async).** Enable the GitHub connector for this conversation and have
the box commit `state/`, `results/` and `data_cache/MANIFEST.json` on a timer. I read the
artefacts without needing any network path at all.

### Before you expose anything

`POST /api/control/{pause,resume,reset_risk,flatten}` changes state. It now requires
`APEX_API_TOKEN` (sent as `Authorization: Bearer …`); with no token configured it only
accepts loopback, so a public deployment **fails closed**. Verify from outside:

```bash
curl -s -o /dev/null -w '%{http_code}\n' -X POST https://<host>/api/control/pause
# 401/403 = secured.  200 = anyone with the URL can flatten your book.
```
