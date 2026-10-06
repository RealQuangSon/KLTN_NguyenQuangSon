# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

HomeMatch is a thesis project (KLTN): **"HomeMatch AI Agent"**, a rental platform (rooms, studios, apartments in **TP.HCM and Hà Nội**) with an AI assistant that recommends units by the renter's needs and financial capacity. **Each landlord (role `owner`, `Room.landlord_id`) approves their own rooms** in a shortlist before the renter (`renter`) sees them; `admin` runs the Admin Console. The old `manager` (sale) role still logs in but has no business permissions. The original topic was about buying apartments; the project narrowed it to rentals (decisions D-01..D-08 in `docs/ke-hoach-kltn-homematch.md`, confirmed by the user 05/10/2026). Most docs are in Vietnamese.

The code (schema v9) implements the AI assistant plus five platform modules added 05/10 (E1–E6):
- **Tenant portal:** filter search, quick view, Leaflet/OSM map, AI comparison advice, live chat with handover context, offline/online (Jitsi) viewings, handbook.
- **Automation:** in-app notifications with dedup keys; background jobs (viewing/payment/renewal reminders, lead re-engagement, chat retention); room status/price change sync.
- **Admin Console:** PII-masked AI transcripts (90 days, audited views), handover metrics, users, listing moderation, jobs.
- **Landlord PMS & CRM:** dashboard, room CRUD, versioned click-accept leases, meter readings, immutable invoices, payments/claims/receipts, maintenance, leads, analytics.
- **Landlord co-pilot:** channel-specific marketing posts, share links, public listing page `/tin/:id`, comparable-based price advice, rule-routed assistant with Web Speech voice input.

External integrations are substituted (D-07): no payment gateway, real email/SMS, social auto-posting, or legal e-signature (D-08).

Still missing:
- Railway deployment and live GPT-4o/pgvector runs (need the user's accounts and keys);
- browser E2E demo; PostgreSQL run of schema v9;
- photo/media upload, landlord promotions, the chat `simulate_finance` intent, VND cost metrics;
- research evaluation (labels, user study).

Where to look in `docs/`:
- `README.md`: the doc index;
- `ke-hoach-kltn-homematch.md`: thesis outline;
- `yeu-cau-san-pham.md`: FR/NFR, each with current status;
- `trang-thai-trien-khai.md`: what exists, with evidence;
- `ke-hoach-trien-khai.md`: phases GĐ1–GĐ5.

`docs/luu-tru/` holds the archived 04/10 docs; current scope is defined by the files above. `CONTEXT.md` is the glossary. `AGENTS.md` holds repository guidelines, which also apply here.

## Commands

Run everything from the repo root. The Python venv lives in `.venv/`.

```bash
python3 -m venv .venv && .venv/bin/python -m pip install -r requirements.lock
npm --prefix frontend ci

# Tests (pytest.ini: testpaths = backend/tests eval/tests, pythonpath = .)
.venv/bin/python -m pytest
.venv/bin/python -m pytest backend/tests/test_workflow.py::test_name   # single test
npm --prefix frontend test                                              # vitest run
npm --prefix frontend test -- src/tests/renter-state.test.tsx           # single UI test file
npm --prefix frontend run typecheck
npm --prefix frontend run build
npm --prefix frontend run format        # Prettier; there is no Python formatter or linter

# Offline end-to-end checks
.venv/bin/python -m infra.smoke_api --in-process
.venv/bin/python -m backend.demo
bash infra/check-local.sh               # full offline suite: eval pipeline + pytest + UI tests + build + demo + smoke
```

Run locally. The backend does **not** load `.env`, so export the variables yourself:

```bash
export HOMEMATCH_DB_PATH=.local/homematch-v2.sqlite HOMEMATCH_CATALOG_PATH=data/catalog/rooms.json \
       HOMEMATCH_AUTH_MODE=seed HOMEMATCH_LLM_MODE=demo HOMEMATCH_MATCHING_METHOD=B1 HOMEMATCH_EMBEDDING_MODE=disabled
.venv/bin/python -m backend.manage setup && .venv/bin/python -m backend.manage seed-users
.venv/bin/python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 --workers 1 --no-access-log --log-config backend/logging.json
npm --prefix frontend run dev           # http://127.0.0.1:5173; Vite proxies /api → :8000 (prefix stripped)
```

Seed logins: `renter-a`, `renter-b`; landlords `owner-a`, `owner-b` (TP.HCM), `owner-c`, `owner-d` (Hà Nội); `admin-a`. Each password is `local-<username>-password`. The catalog loads from JSON only into an empty DB, so use a fresh DB path after regenerating data.

Background jobs run inside the API process every `HOMEMATCH_JOBS_INTERVAL_SECONDS` (default 300; tests set 0). Run them once with `.venv/bin/python -m backend.manage jobs`.

PostgreSQL is optional. `bash infra/local-pg.sh start` starts a cluster in `.local/` on 127.0.0.1:55432. PG tests are skipped unless `HOMEMATCH_TEST_DATABASE_URL` is set, for example `postgresql://homematch@127.0.0.1:55432/homematch_test`. When it is set, the `storage` fixture parametrizes the tests over both SQLite and PG, with one throwaway schema per test.

Eval CLI: `.venv/bin/python -m eval <validate|oracle|extraction|ranking --split dev|metrics|invariants --split dev|grounding|measure|report>`. Outputs go to `eval/runs/development/`. See `eval/README.md` and `eval/REPRODUCE.md`.

## Architecture

**Request path:** React SPA (`frontend/src`) → FastAPI (`backend/app/main.py`, `create_app`) → `HomeMatchService` (`backend/app/service.py`) → repository/`Database` → SQLite or PostgreSQL.

- `locations.py` canonicalizes city/area names and aliases ("Sài Gòn", "Q7", "Bình Thạnh", "Cầu Giấy"). The demo interpreter uses it to extract them, and the hard filter uses it to compare them. City is never defaulted.
- `main.py` resolves the actor from a server-side bearer token (`auth.py`: scrypt password hashes, random tokens stored as SHA-256 hashes, revocable; no JWT). Response DTOs live in `schemas.py`, domain models in `models.py`.
- `database.py` is a thin SQL boundary for both backends. Write SQL with `?` placeholders; they are rewritten to `%s` for psycopg. `migrations.py` keeps a migration ledger (`hm_schema_migrations`). The `hm_*` tables are listed in `docs/kien-truc-trien-khai.md`.
- Storage is selected by `HOMEMATCH_DATABASE_URL` (PG) if set, otherwise `HOMEMATCH_DB_PATH` (SQLite). LangGraph checkpoints go to the same PG database, or to a sibling `*.checkpoints.sqlite` file.

**Two LangGraph graphs, both in `service.py`:**
1. **Chat graph** (`ChatState`): intent → extract → draft-profile update, or finance/support/handbook answers. Extraction is done by `interpreter.py`: a rule-based demo mode by default, or GPT structured output when `HOMEMATCH_LLM_MODE=openai`. Money mentioned in chat is only a hint; the profile becomes authoritative only when the renter confirms it with `expected_draft_revision`.
2. **Recommendation graph** (`RecommendationState`): rank → save `pending_review` draft → `interrupt()` → **each landlord reviews their own rooms** (`hm_run_reviews`; subset/order within their own slots, version and idempotency key). After the first approval the run is `partially_published` and `repository.visible_items` shows approved rooms in agent order. When every landlord has decided, the final `decision` event is written and the graph resumes with the ledger `event_id` → finalize. Nodes before the interrupt must have **no write side effects**, because LangGraph reruns the node on resume.

LangGraph only orchestrates. Finance (`costs.py`), hard filters and ranking (`catalog.py`: B1 lexical/rule, optional P = B1 + pgvector semantic via `semantic.py`), permissions and publication are deterministic code, not model decisions. If P is unavailable the app falls back to B1 and records which algorithm it used. The eval never counts that fallback as P.

**Invariants that tests enforce:**
- Renters see only landlord-approved recommendations for their *current* profile version and catalog version. A pending run shows `results=[]`. A new profile confirmation or a catalog change invalidates old results, compares and viewings.
- Unknown costs stay `null`, never 0. A known subtotal is not a full total. Move-in cost = deposit + prepaid rent + one-time fees + moving + furnishing; it does not add the first month again. Money is `Decimal` with VND rounding, and only `costs.py` handles it.
- Hard constraints are never relaxed automatically. The system only suggests soft relaxations, which the renter must confirm.
- Record-level permissions: landlords only see/edit their own rooms, review slots, viewings, conversations, leases, invoices, maintenance and leads; renters only their own. Role capabilities live in `agent_capability.py` and `capabilities.py`.
- Issued invoices are immutable; payments are append-only and cannot exceed the balance; a payment claim is not a payment until the landlord confirms it. Editing a sent lease bumps its version and requires re-acceptance.
- AI chat turns are stored PII-masked (`conversations.mask_pii`) and purged after `HOMEMATCH_CHAT_RETENTION_DAYS`; admin views are audited.
- Concurrency uses revisions, CAS and mutation keys. The frontend sends `mutationKey()` from `api.ts`.
- **Keep a single API worker** (`--workers 1`). The jobs thread lives in that process; there is no outbox or recovery worker.

Agent guardrails live in `agent_guard.py`, `agent_budget.py` (per-session LLM budget, `HOMEMATCH_SESSION_LLM_BUDGET`), `agent_capability.py` and `agent_provenance.py`.

**Frontend:** React 19 + Vite with no router or state libraries. `router.tsx` is a minimal custom history router. `pages/` holds the renter workspace, `SearchPage`, `Inbox`, `Handbook`, `LandlordWorkspace`, `Pms.tsx` (dashboard, leases, billing, maintenance, leads), `Copilot`, `AdminWorkspace`, `PublicListing` and auth pages; routes are in `App.tsx` (`/tim-kiem`, `/chu-nha/*`, `/quan-tri/*`, `/nguoi-thue/*`, `/tin/:id`). `api.ts` wraps fetch with `ApiError`. `VITE_API_BASE_URL` defaults to `/api`, and newer endpoints use `/api/v1`. The frontend never computes scores, permissions or publication. It keeps only the token and session ID in `sessionStorage`. Vitest tests and fixtures are in `src/tests/`.

**Finance and fairness rules:**
- `costs.py` holds `assess_affordability` and `estimate_loan` (annuity), specified in `docs/tai-chinh-thue.md`. Bands are computed on the housing ratio after rounding it HALF_UP to 4 places.
- In `catalog.py`, cash is a hard limit unless the profile has a `loan`. With a loan, the hard checks become `loan_principal` and `loan_burden`.
- `HomeMatchService._landlord_projection` strips `monthly_income_vnd` and nulls `housing_ratio`, because the ratio plus the burden would reveal income. Landlords see the band only. Income must never reach the landlord DTO, handover context, LLM prompts or embeddings.
- Approving with a dropped or reordered list requires `override_reason`. Ranking must never use commercial attributes such as commission or time on market; `eval invariants` mutates both and checks the ranking does not move.
- `frontend/src/locations.ts` mirrors `locations.py`. A backend test keeps the two in sync.

**Agents and memory:**
- Chat graph nodes: `route` (supervisor), `interview` (needs agent), `finance`, `support`, `handbook`.
- The recommendation graph keeps its node names so pending checkpoints stay valid. Its `rank` node acts as the ranking agent.
- Every business call from a graph goes through `ToolBox.call(agent, tool, fn, ...)`, which enforces the per-agent allowlist and a 4-step limit. New tools must be added to `AGENT_TOOLS`.
- Memory never stores money, income, loans or destinations. It prefills drafts only as `inferred`. Withdrawing consent deletes it.
- `docs/api-san-pham-v1.md` lists what is left.

**Data:** the v2 catalog in `data/catalog/rooms.json` is fully synthetic. It has 220 units: TP.HCM 120, Hà Nội 100; types `room`/`studio`/`apartment`. Rooms are assigned to landlords owner-a..d by `landlord_for`. Gold has 45 profiles (dev 15, test 30) and the oracle has 22 cases. `python -m data.generate` regenerates everything deterministically and keeps the 80 v1 rooms identical. `data/` also holds the generator, splits, gold data, cost oracles and manifests, which `eval validate` checks by hash. Do not edit frozen data without regenerating the manifests.

## Conventions

- Tests default to offline providers. `backend/tests/conftest.py` autouse-sets demo LLM, demo auth, B1 and no embeddings. Never call paid APIs in tests. Live GPT/embedding indexing needs `backend.manage index --allow-live`.
- Use `DomainError` for expected failures. Use Pydantic at boundaries. Python uses 4-space indentation and type hints.
- Do not claim something is verified (live model quality, PG, Docker/cloud, browser E2E) unless it was actually run. The docs distinguish historical evidence from current status.
- Never commit secrets, local DBs (`.local/`), checkpoints or raw chats.
