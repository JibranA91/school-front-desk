# AI Front Desk

A lightweight, mobile-friendly **AI Front Desk** prototype for early-education centers
(daycares / pre-Ks). It answers the routine questions that flood a school's phone, email,
and text every day — grounded in a specific center's policies and schedules — so administrators
save time and parents get fast, trustworthy answers.

Built as a proof of concept around two ideas: **trustworthy grounding** (every answer is tied to
the center's own source of truth, and the agent escalates instead of guessing when it's unsure or
the topic is sensitive) and a **self-improving loop** (operators watch what parents ask, see where
the system struggled, and teach it — by editing the knowledge graph or ingesting the handbook).

## The problem

School administrators spend hours daily answering the same questions:

- *"Are you open on Veterans Day?"*
- *"What is the tuition for infants?"*
- *"My child has a fever, can they come in?"*
- *"I forgot to pack lunch — can you provide one today, and what is it?"*
- *"How can I schedule a tour?"*

Parents want fast, accurate answers. Operators are busy and can't always respond in real time.
Handbooks are hard to search on a phone, and voicemail tag is frustrating.

## Two perspectives

### Parent experience (front desk)
Ask a question and get an answer specific to the center that feels trustworthy. Answers cite where
they came from. When a question is uncertain or sensitive (health, medication, allergy, safety,
billing, custody), the system hands off to staff rather than guessing. A durable **Updates** feed
lets a parent see when staff have followed up.

### Operator experience (control center)
Staff provide and edit the source of truth (policies, schedules), see what questions are being
asked and where the system struggled, and improve the system over time — inspect and edit any
knowledge entity, revert a change, or upload a handbook PDF and watch the knowledge graph populate.

## How it works

Answers are **grounded** in a small knowledge graph of a fictional center's policies and schedules
(tuition, hours, holidays, illness policy, tours, meals, and more) plus a few **live** data sources
(today's / this week's menu, program roster, center profile). No real personal data is used.

- A parent question is answered by a **LangGraph ReAct agent**. Before the agent runs, the relevant
  **subgraph is retrieved and injected** into its context; the agent can also call graph tools
  (`search_graph` / `get_entity` / `expand_neighbors`) and live-data tools (`get_todays_menu`,
  `get_week_menu`, `get_programs`, `get_center_info`) to look further.
- **Retrieval is hybrid**: pgvector cosine similarity + Postgres full-text search + a walk over
  knowledge-graph relationships. Semantic search can be switched off to rank on full-text alone.
- **Escalation is a code-level safety net**, not left to the model — sensitive categories always
  hand off, even when a matching policy exists.
- **Short-term memory**: the current chat session's recent turns are fed back so the agent resolves
  follow-ups like *"what about fever?"* or *"and tomorrow's lunch?"*.

## Architecture

| Service | Stack | Port |
|---|---|---|
| `web` | Next.js 16 (App Router) · React 19 · Tailwind v4 · Auth.js (NextAuth v5) | `3000` |
| `api` | FastAPI · SQLAlchemy 2.0 · LangGraph · LangChain (Bedrock / Anthropic) | `8001` → `8000` |
| `db`  | Postgres 16 + [pgvector](https://github.com/pgvector/pgvector) | `5432` |

The LLM provider is pluggable: **AWS Bedrock**, the **Anthropic Claude API**, or an offline
**mock** (no keys needed — retrieval + keyword heuristics, useful as a smoke test).

### Repository layout

```
app/            Next.js App Router — parent (/), operator (/operator), login, API proxy routes
components/     React UI (ParentView, OperatorView, InboxPanel, EntityInspector, KnowledgeGraph…)
lib/, auth.ts, middleware.ts   Front-end data layer, Auth.js config, route guarding
api/app/        FastAPI service
  main.py         endpoints (ask, entities, ingest, changelog, updates…)
  agent.py        the parent ReAct agent + live-data tools
  retrieval.py    hybrid retrieval (pgvector + FTS + graph walk)
  authoring.py    operator-authored knowledge (structured extraction)
  ingest.py       handbook PDF → knowledge graph
  seed.py         demo dataset + `--fresh` deploy mode
  models.py, db.py, config.py, llm.py, embeddings.py
evals/          Offline golden-set evals (see evals/README.md)
Dockerfile, api/Dockerfile, docker-compose.yml
```

## Running it

Everything runs with Docker Compose. From the repo root:

```bash
docker compose up -d --build
```

Then seed the demo center (one-time, resets the DB):

```bash
docker compose exec api uv run python -m app.seed          # full Sunnyside demo
# or, for a real school — everything except an empty knowledge graph + inbox:
docker compose exec api uv run python -m app.seed --fresh
```

Open **http://localhost:3000** and sign in:

| Role | Email | Password |
|---|---|---|
| Operator | `maria@sunnyside.example` | `demo1234` |
| Parent | `ava.parent@example.com` (or `noah.` / `liam.`) | `demo1234` |

### Fresh deploy for a new school

`--fresh` seeds only the always-present scaffold (center profile, programs, users, children, and
this week's menu) and leaves the **knowledge graph and operator inbox empty**. The operator then
builds the knowledge base from scratch — either by editing entities directly or by uploading the
center's handbook:

```bash
docker compose exec api uv run python -m app.ingest /path/to/handbook.pdf
```
(or, in the app, **Operator → upload handbook** — the same ingestion with live progress.)

### LLM provider

Copy `api/.env.example` to `api/.env` and fill in credentials. Without any, the API runs on the
mock agent. Every knob (provider, model ids, embeddings on/off, retrieval shape, chat memory) is
documented in [`api/.env.example`](api/.env.example).

### Phone / LAN access

The Next.js server needs the URL clients actually use for auth callbacks. To reach the app from a
phone on the same network, set `AUTH_URL` to this machine's LAN URL before starting `web`:

```bash
AUTH_URL=http://<your-lan-ip>:3000 docker compose up -d web
```

## Deploy

The repo is prepared for **Railway** (three services: public web, private api,
private Postgres+pgvector — dynamic `$PORT`, IPv6 private networking, managed
`DATABASE_URL`, optional first-boot seeding). Step-by-step in
[`DEPLOY.md`](DEPLOY.md).

## Evals

Two offline golden-set harnesses score the parent agent against the seeded graph + ingested
handbook. The headline metric is **safety**, not raw accuracy — a confident wrong answer is the
failure that sinks trust.

- **`evals/run_evals.py`** — escalation *decision* accuracy: answer vs. escalate vs. hand-off,
  grounding (every answer carries a citation), over-escalation, and the safety gate (zero confident
  answers to sensitive / unknown / out-of-scope questions).
- **`evals/menu_evals.py`** — menu *content* correctness across days (today, tomorrow, each
  weekday, the whole week, weekends): right day's dish, no cross-day leakage, and no fabricated
  menu when none is posted.

See [`evals/README.md`](evals/README.md) for how to run them and what each scores.

## Status

Proof of concept — optimized for demonstrating product vision, grounding/trust, and technical
judgment rather than production hardening. Invented data only; no real personal data.
