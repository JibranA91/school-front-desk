# Deploying to Railway

This app is a three-service system. On Railway that maps to three services in one
project, all wired over Railway's **private network** so only the web tier is
public:

```
browser ──HTTPS──▶  web  (Next.js, PUBLIC)
                     │  private network (IPv6)
                     ▼
                    api  (FastAPI, PRIVATE — no public domain)
                     │
                     ▼
                 Postgres (pgvector, PRIVATE)
```

The browser only ever talks to the web tier; every FastAPI call is proxied
server-side through Next route handlers (`app/api/*`) and `auth.ts`. So **api and
Postgres stay private** and never get a public domain.

## What's already prepared in the repo

- **`api/Dockerfile`** honors Railway's injected `$PORT` (default `8000`) and
  binds `::` on Railway (its private network is IPv6-only) — auto-detected via
  the Railway-provided `RAILWAY_PRIVATE_DOMAIN`, and overridable with
  `UVICORN_HOST`. Locally it binds `0.0.0.0` so compose keeps working.
- **`Dockerfile`** (web) already reads `$PORT` and sets `HOSTNAME=0.0.0.0` (Next
  standalone).
- **`config.py`** normalizes a `postgres://` / `postgresql://` `DATABASE_URL`
  (what managed Postgres hands out) to the `postgresql+psycopg://` driver form.
- **`SEED_ON_START`** (opt-in) seeds the DB on first boot, but only when it has
  no users — so it never overwrites live data.
- **`railway.json`** sets the Dockerfile builder + a restart policy for both
  repo services.

## Prerequisites

- A Railway account.
- This repo on GitHub (`JibranA91/school-front-desk`), connected to Railway.
- Credentials for one LLM provider (Anthropic API key **or** AWS Bedrock keys).
  Without either, the API runs the offline mock (canned answers) — fine to prove
  the deploy, not the real behavior.

## Step 1 — Create the project + Postgres

1. **New Project → Deploy from GitHub repo →** select `school-front-desk`.
2. **New → Database → Add PostgreSQL.** Railway's Postgres ships the `vector`
   extension; the app runs `CREATE EXTENSION IF NOT EXISTS vector` on boot.
   - pgvector is **required even in FTS-only mode** — the entity table has a
     `vector` column.
   - If `CREATE EXTENSION vector` ever errors (an older PG image), delete it and
     instead **New → Empty Service → Deploy from Docker image** `pgvector/pgvector:pg16`,
     add a volume mounted at `/var/lib/postgresql/data`, and set `POSTGRES_USER`,
     `POSTGRES_PASSWORD`, `POSTGRES_DB`; then build `DATABASE_URL` from those.

## Step 2 — The `api` service (private)

Turn the service Railway created from the repo into the API (or add a new one
from the same repo):

- **Settings → Root Directory:** `api` — Railway auto-detects `api/Dockerfile`.
- **Settings → Networking:** do **not** generate a public domain (keep it private).
- **Variables:**

  | Variable | Value |
  |---|---|
  | `DATABASE_URL` | `${{Postgres.DATABASE_URL}}` |
  | `AUTH_SHARED_SECRET` | a long random string (must match `web`) |
  | `EMBEDDINGS_ENABLED` | `false` (FTS-only — recommended; no embedding provider needed) |
  | `SEED_ON_START` | `demo` (first-boot seed) — or omit and seed manually (Step 5) |

  Then pick **one** LLM provider:

  - **Anthropic (simplest):** `LLM_PROVIDER=anthropic`, `ANTHROPIC_API_KEY=<key>`
  - **Bedrock:** `AWS_REGION=us-east-1`, `AWS_ACCESS_KEY_ID=<…>`, `AWS_SECRET_ACCESS_KEY=<…>` (leave `LLM_PROVIDER=auto`)
  - **Neither:** the mock agent runs.

  > Enter secrets directly in Railway's Variables UI — never commit them. Railway
  > injects `PORT` automatically; the container binds it.

## Step 3 — The `web` service (public)

Add another service from the same GitHub repo:

- **Settings → Root Directory:** `/` (repo root) — auto-detects the root `Dockerfile`.
- **Settings → Networking → Generate Domain.** Note the URL, e.g.
  `https://school-front-desk-production.up.railway.app`.
- **Variables:**

  | Variable | Value |
  |---|---|
  | `API_BASE_URL` | `http://${{api.RAILWAY_PRIVATE_DOMAIN}}:${{api.PORT}}` |
  | `AUTH_SECRET` | a long random string (`openssl rand -base64 32`) |
  | `AUTH_SHARED_SECRET` | **same** value as the api service |
  | `AUTH_URL` | `https://${{RAILWAY_PUBLIC_DOMAIN}}` (the web domain from above) |
  | `AUTH_TRUST_HOST` | `true` |

  > `API_BASE_URL` references the **api** service by name — name that service
  > `api` or adjust the reference. `AUTH_URL` must be the public web URL, or
  > NextAuth's callback/redirect resolution breaks behind Railway's proxy.
  > Optionally set `WEB_ORIGIN` on the **api** service to this same URL (CORS);
  > not strictly required, since the browser never calls the api directly.

## Step 4 — Deploy

Deploy order: **Postgres → api → web.** If you added variables after a build,
trigger a redeploy so they take effect. Watch each service's **Deploy Logs**;
the api should log `Uvicorn running on http://[::]:<PORT>` and (if
`SEED_ON_START`) `seed_on_start=…: empty database, seeding…`.

## Step 5 — Seed the database

**Option A — automatic (recommended for a demo).** With `SEED_ON_START=demo`
on the api service, the first boot against an empty DB seeds the full demo. It
won't re-run once users exist. Use `fresh` instead of `demo` for a real school
(empty knowledge graph + inbox).

**Option B — manual.** In the api service, open a shell (`railway ssh --service api`,
or the dashboard shell) and run:

```bash
uv run python -m app.seed          # full demo
uv run python -m app.seed --fresh  # scaffold only (empty KG + inbox)
```

For a real school, seed `--fresh`, then upload the handbook via **Operator →
upload handbook** to build the knowledge graph.

## Step 6 — Verify

Open the web public URL (it redirects to `/login`) and sign in:

| Role | Email | Password |
|---|---|---|
| Operator | `maria@sunnyside.example` | `demo1234` |
| Parent | `ava.parent@example.com` | `demo1234` |

## Troubleshooting

| Symptom | Likely cause |
|---|---|
| Login always fails | `AUTH_SHARED_SECRET` differs between web and api, or the api service is down. |
| Web 502 / "failed to fetch" on questions | `API_BASE_URL` wrong, or the api isn't reachable on the private net. Confirm it resolves to `http://api.railway.internal:<PORT>`; if the api log shows it bound `0.0.0.0` instead of `[::]`, set `UVICORN_HOST=::` on the api service. |
| Redirects to the wrong host after login | `AUTH_URL` not set to the public web domain (with `AUTH_TRUST_HOST=true`). |
| Startup error `type "vector" does not exist` | Postgres image lacks pgvector — use the `pgvector/pgvector:pg16` image (Step 1). |
| Answers are canned / `provider: mock` | No LLM credentials set on the api service. |

Health of the (private) api can be seen in its Deploy Logs, or temporarily
generate a domain and hit `/health` (returns provider + retrieval mode), then
remove the domain.
