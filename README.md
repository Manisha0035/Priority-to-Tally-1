# tally-bridge-api

Job queue that sits on Railway between the Priority-to-Tally middleware app
and the local agent running next to Tally. It lets the middleware app live
on a cloud server (Railway) while Tally stays on a local desktop, with no
inbound ports opened on the local machine.

## How it works

```
Middleware app (Railway)          bridge_api (Railway)          bridge_agent (local, next to Tally)
──────────────────────             ─────────────────              ──────────────────────────────
1. Builds XML voucher
2. POST /jobs            ───────►  3. Stores job (pending)
                                    4. GET /jobs/pending      ◄──── 5. Agent polls every few seconds
                                    6. Job marked "picked"    ────►
                                                                    7. Agent sends XML to
                                                                       localhost:9000 (Tally)
                                    9. POST /jobs/{id}/result ◄──── 8. Agent posts Tally's response
10. GET /jobs/{id}        ◄──────  (status: done)
11. Shows result in UI
```

The local machine only ever makes **outbound** HTTPS calls to this service.
Nothing needs to be exposed on your router or firewall.

## Endpoints

| Method | Path                  | Called by         | Purpose                              |
|--------|-----------------------|--------------------|---------------------------------------|
| POST   | `/jobs`                | middleware app     | Enqueue a new XML job                 |
| GET    | `/jobs/pending`         | bridge_agent       | Poll for jobs waiting for this client |
| POST   | `/jobs/{job_id}/result` | bridge_agent       | Report Tally's response or an error   |
| GET    | `/jobs/{job_id}`        | middleware app     | Poll for the result                   |
| GET    | `/health`               | anyone             | Health check                          |

All endpoints except `/health` require an `X-Api-Key` header.

## Environment variables

| Variable          | Required | Description                                      |
|--------------------|----------|---------------------------------------------------|
| `BRIDGE_API_KEY`   | yes      | Shared secret — must match on the middleware app and the local agent |
| `BRIDGE_DB_PATH`   | no       | SQLite file path (default: `bridge.db`)           |

## Deploy to Railway

1. Push this folder to its own GitHub repo (e.g. `tally-bridge-api`)
2. Railway → New Project → Deploy from GitHub repo → select it
3. Railway auto-detects Python + reads `Procfile`
4. Set `BRIDGE_API_KEY` under Variables (generate a long random string — this is your shared secret)
5. Settings → Networking → Generate Domain
6. Confirm it's live: open `https://<your-domain>/health` in a browser, should return `{"ok": true}`

## Local development

```bash
pip install -r requirements.txt
uvicorn bridge_api:app --reload --port 8000
```

## Notes

- Jobs older than 30 minutes (`JOB_TTL_SECONDS`) are ignored by the agent poll, so stale/abandoned jobs don't get processed after a long delay.
- Uses SQLite for simplicity. Fine for a single middleware instance + single agent. If you scale to many concurrent clients/agents, consider swapping in Postgres (Railway offers this as an add-on) — the queries would need minimal changes.
- `client_id` lets one bridge_api serve multiple Tally installations later (e.g. multiple dealership branches), by giving each agent a different `BRIDGE_CLIENT_ID`.
