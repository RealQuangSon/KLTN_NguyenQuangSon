# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

HomeMatch is a thesis project (KLTN): **"HomeMatch AI Agent"**, a rental platform (rooms, studios, apartments in **TP.HCM and Hà Nội**) with an AI assistant that recommends units by the renter's needs and financial capacity. Recommendations are **published to the renter immediately after ranking** (decision 05/11/2026 removed the landlord-approval step); landlords learn about demand through CRM leads (`touch_lead(source="recommended")` when one of their rooms lands in the top 5), never through a blocking review. `admin` runs the Admin Console. The old `manager` (sale) role still logs in but has no business permissions. The original topic was about buying apartments; the project narrowed it to rentals (decisions D-01..D-08 in `docs/ke-hoach-kltn-homematch.md`, confirmed by the user 05/10/2026). Most docs are in Vietnamese.

The code (schema v16) implements the AI assistant plus five platform modules added 05/10 (E1–E6), extended 08/10 with landlord self-signup + admin approval (v10), support-ticket lifecycle (v11), listing/maintenance photos (v12), landlord promotions (v13), landlord contact phone (v14), renter room saves (v15), recommendation auto-publish — the landlord-review step removed (v16, 05/11/2026) — plus the chat `simulate_finance` intent and VND cost metrics on `/admin/metrics`. Listing payloads (LF, 31/10/2026) carry the masked post body, posting time, poster kind, ward (old/new), street, move-in date, payment cycle, minimum lease and 19 amenity keys (`AMENITY_KEYS` in `models.py`); every new field is `null` when the post does not say:
- **Tenant portal:** filter search, quick view, Leaflet/OSM map, AI comparison advice, live chat with handover context, offline/online (Jitsi) viewings, handbook.
- **Automation:** in-app notifications with dedup keys; background jobs (viewing/payment/renewal reminders, lead re-engagement, chat retention); room status/price change sync.
- **Admin Console:** PII-masked AI transcripts (90 days, audited views), handover metrics, users, listing moderation, jobs.
- **Landlord PMS & CRM:** dashboard, room CRUD, versioned click-accept leases, meter readings, immutable invoices, payments/claims/receipts, maintenance, leads, analytics.
- **Landlord co-pilot:** channel-specific marketing posts, share links, public listing page `/tin/:id`, comparable-based price advice, rule-routed assistant with Web Speech voice input.

External integrations are substituted (D-07): no payment gateway, real email/SMS, social auto-posting, or legal e-signature (D-08). The project runs on localhost only (D-09, 28/10/2026): Railway deployment and the Docker build are out of scope, and their configuration files were removed from the repository on 28/10/2026.

Still missing:
- live GPT-4o/pgvector runs on the local machine (`infra/live_run.sh`; needs the user's OpenAI key and budget);
- browser E2E demo on localhost (script in `docs/kich-ban-demo.md`, not yet recorded);
- social auto-posting (FR-47 is share-only);
- research evaluation: labelling and survey tools exist (`eval label-sheet|label-report|survey-report`), the labels and answers do not.

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
.venv/bin/python -m backend.manage seed-demo   # optional [DEMO]-tagged PMS data for owner-a/renter-a; idempotent, refuses HOMEMATCH_PUBLIC=true
.venv/bin/python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 --workers 1 --no-access-log --log-config backend/logging.json
npm --prefix frontend run dev           # http://127.0.0.1:5173; Vite proxies /api → :8000 (prefix stripped)
```

Seed logins: `renter-a`, `renter-b`; landlords `owner-a`, `owner-b` (TP.HCM), `owner-c`, `owner-d` (Hà Nội); `admin-a`. Each password is `local-<username>-password`. The catalog loads from JSON only into an empty DB, so use a fresh DB path after regenerating data.

Background jobs run inside the API process every `HOMEMATCH_JOBS_INTERVAL_SECONDS` (default 300; tests set 0). Run them once with `.venv/bin/python -m backend.manage jobs`.

**Day-to-day app DB is Neon (decision 31/10/2026).** `bash infra/run-neon.sh [port]` sources `.env` then `.local/neon.env` (`HOMEMATCH_DATABASE_URL` = Neon database `homematch`, `HOMEMATCH_CRAWL_DATABASE_URL` = `neondb` with the Chợ Tốt snapshots; project `kltn`, id `snowy-shadow-49494187`, aws-ap-southeast-1), restores the catalog snapshot from Neon if missing, runs `setup` and starts uvicorn. Use the direct (non-`-pooler`) URL. Neon suspends idle compute after 5 minutes, so `Database` reconnects a dead session outside a transaction and checkpoints use a checked `ConnectionPool`. Round trips are ~50–400 ms, so avoid per-row queries on list endpoints. With the Chợ Tốt catalog most rooms lack fees, so most listed totals are labelled estimates (D-12: they are shown at once, never held). Never commit `.local/neon.env`.

PostgreSQL is optional. `bash infra/local-pg.sh start` starts a cluster in `.local/` on 127.0.0.1:55432. PG tests are skipped unless `HOMEMATCH_TEST_DATABASE_URL` is set, for example `postgresql://homematch@127.0.0.1:55432/homematch_test`. When it is set, the `storage` fixture parametrizes the tests over both SQLite and PG, with one throwaway schema per test.

Eval CLI: `.venv/bin/python -m eval <validate|oracle|extraction|ranking --split dev|metrics|invariants --split dev|grounding|measure|report>`. Outputs go to `eval/runs/development/`. See `eval/README.md` and `eval/REPRODUCE.md`.

## Architecture

**Request path:** React SPA (`frontend/src`) → FastAPI (`backend/app/main.py`, `create_app`) → `HomeMatchService` (`backend/app/service.py`) → repository/`Database` → SQLite or PostgreSQL.

- `locations.py` canonicalizes city/area names and aliases ("Sài Gòn", "Q7", "Bình Thạnh", "Cầu Giấy"). The demo interpreter uses it to extract them, and the hard filter uses it to compare them. City is never defaulted: when the renter names a district, the interview node pins its single city via `locations.city_for_area` (deterministic alias resolution, marked `inferred`); `_questions` only asks what blocks the run (meaning of a mentioned amount, occupants, unpinned city, destination details) — room type stays a form field.
- `main.py` resolves the actor from a server-side bearer token (`auth.py`: scrypt password hashes, random tokens stored as SHA-256 hashes, revocable; no JWT). Response DTOs live in `schemas.py`, domain models in `models.py`.
- `database.py` is a thin SQL boundary for both backends. Write SQL with `?` placeholders; they are rewritten to `%s` for psycopg. `migrations.py` keeps a migration ledger (`hm_schema_migrations`). The `hm_*` tables are listed in `docs/kien-truc-trien-khai.md`.
- Storage is selected by `HOMEMATCH_DATABASE_URL` (PG) if set, otherwise `HOMEMATCH_DB_PATH` (SQLite). LangGraph checkpoints go to the same PG database, or to a sibling `*.checkpoints.sqlite` file.

**Two LangGraph graphs, both in `service.py`:**
1. **Chat graph** (`ChatState`): intent → extract → draft-profile update, or finance/support/handbook answers. Extraction is done by `interpreter.py`: a rule-based demo mode by default, or GPT structured output when `HOMEMATCH_LLM_MODE=openai` — through the OpenAI Responses API, or through any `/chat/completions`-only gateway such as OpenRouter when `HOMEMATCH_LLM_API=chat_completions` (gateways like OpenRouter serve no embeddings, so keep `HOMEMATCH_EMBEDDING_MODE=disabled` and B1 matching there). Money mentioned in chat is only a hint; the profile becomes authoritative only when the renter confirms it with `expected_draft_revision`.
2. **Recommendation graph** (`RecommendationState`): rank → save draft → publish. `repository.set_draft` writes `published` (with the top 5 rooms; `diagnostics.total_matches` keeps the real count, D-12) / `no_match` directly (`needs_verification` survives only on legacy runs); the `publish` node stamps `published_at`, notifies the renter once (`rooms_ready`) and touches a CRM lead for each landlord with a room in the top 5. There is no `interrupt()` and no resume path; `hm_run_reviews` stays read-only for legacy data.

LangGraph only orchestrates. Finance (`costs.py`), hard filters and ranking (`catalog.py`: B1 lexical/rule, optional P = B1 + pgvector semantic via `semantic.py`), permissions and publication are deterministic code, not model decisions. If P is unavailable the app falls back to B1 and records which algorithm it used. The eval never counts that fallback as P.

**Invariants that tests enforce:**
- Renters see only published recommendations for their *current* profile version and catalog version; results reach the renter in the same turn as the ranking. A new profile confirmation invalidates old results, compares and viewings; a catalog change does so only when re-ranking the run's profile gives a different list (D-11), and an unfinished `generating` run is never revalidated.
- Unknown costs stay `null`, never 0. A known subtotal is not a full total. D-12 (08/11/2026): listings missing fees or capacity are shown at once with labels (capacity "chưa rõ", monthly total "ước tính" from standard assumptions, kept apart from the known subtotal); there is no accept-estimates step, and `accept_estimated_data` is a legacy flag with no effect. A run keeps the top 5 and reports the real total (`total_matches`) plus a `/tim-kiem` link with the same filters. Move-in cost = deposit + prepaid rent + one-time fees + moving + furnishing; it does not add the first month again. Money is `Decimal` with VND rounding, and only `costs.py` handles it.
- Hard constraints are never relaxed automatically. The system only suggests soft relaxations, which the renter must confirm.
- The AI ranking never reads `posted_at` or `poster_kind` (F2); `eval invariants` mutates both and checks the ranking does not move. "Newest" sorting exists only in filter search (`GET /listings`), chosen by the user. The public projection may show `description` only in its PII-masked form, which the crawler applies before storing.
- Record-level permissions: landlords only see/edit their own rooms, viewings, conversations, leases, invoices, maintenance and leads; renters only their own. Role capabilities live in `agent_capability.py` and `capabilities.py`.
- Issued invoices are immutable; payments are append-only and cannot exceed the balance; a payment claim is not a payment until the landlord confirms it. Editing a sent lease bumps its version and requires re-acceptance.
- AI chat turns are stored PII-masked (`conversations.mask_pii`) and purged after `HOMEMATCH_CHAT_RETENTION_DAYS`; admin views are audited.
- Concurrency uses revisions, CAS and mutation keys. The frontend sends `mutationKey()` from `api.ts`.
- **Keep a single API worker** (`--workers 1`). The jobs thread lives in that process; there is no outbox or recovery worker.

Agent guardrails live in `agent_guard.py`, `agent_budget.py` (per-session **turn** budget `HOMEMATCH_SESSION_TURN_BUDGET`, default 60, plus cost cap `HOMEMATCH_SESSION_COST_CAP_USD`), `agent_capability.py`, `provider_breaker.py` (5 provider failures/60 s → skip 120 s) and `agent_provenance.py`.

**Frontend:** React 19 + Vite with no router or state libraries. `router.tsx` is a minimal custom history router. `pages/` holds the renter workspace, `SearchPage`, `Inbox`, `Handbook`, `LandlordWorkspace`, `Pms.tsx` (dashboard, leases, billing, maintenance, leads), `Copilot`, `AdminWorkspace`, `PublicListing` and auth pages; routes are in `App.tsx` (`/tim-kiem`, `/chu-nha/*`, `/quan-tri/*`, `/nguoi-thue/*`, `/tin/:id`). `api.ts` wraps fetch with `ApiError`. `VITE_API_BASE_URL` defaults to `/api`, and newer endpoints use `/api/v1`. The frontend never computes scores, permissions or publication. It keeps only the token and session ID in `sessionStorage`. Vitest tests and fixtures are in `src/tests/`.

**Finance and fairness rules:**
- `costs.py` holds `assess_affordability` and `estimate_loan` (annuity), specified in `docs/tai-chinh-thue.md`. Bands are computed on the housing ratio after rounding it HALF_UP to 4 places.
- In `catalog.py`, cash is a hard limit unless the profile has a `loan`. With a loan, the hard checks become `loan_principal` and `loan_burden`.
- `HomeMatchService._admin_projection` omits the profile entirely and nulls `housing_ratio`, because the ratio plus the burden would reveal income. Landlords see the band only (leads and handover context carry the band, never income). Income must never reach any landlord-facing DTO, handover context, LLM prompts or embeddings.
- Ranking must never use commercial attributes such as commission or time on market; `eval invariants` mutates both and checks the ranking does not move.
- `frontend/src/locations.ts` mirrors `locations.py`. A backend test keeps the two in sync.

**Agents and memory:**
- Chat graph nodes: `route` (supervisor), `interview` (needs agent), `finance`, `support`, `handbook`.
- In `openai` mode a turn runs the **agent loop** (`agent_loop.py`, AG-13 + harness HN-00…HN-13.2; the architecture chapter is `docs/thiet-ke-agent.md`): an **input analyst** (`input_analyst.py`, `HOMEMATCH_INPUT_ANALYST=jev|rules|off`, default rules, tests set off) first classifies the message with one Jev request (route needs|finance|ranking|other + clarity clear|reason; state carries only the redacted message + draft, phase and whether results exist — never money/income/loans; timeout 3 s; low probability or Jev failure → rules with `decided_by="fallback"`; quarantined text never reaches Jev; Jev `usage.cost` counts against the session cap), then routes to one **specialised agent role** (roster with per-role system prompt + tool set declared once in `agent_tools.py`): `needs` (interviewing), `finance` (cost/loan explanation; `simulate_loan` re-runs the graph's simulate branch on the user's own sentence and is `writes=True` so it runs on the main thread), `ranking` (read-only explanation via `compare_rooms` + `advisor.advise`, never reorders). The loop itself is HN-01…HN-12: the model reasons and calls tools itself (`find_place`, `update_needs`, `search_rooms`, `confirm_and_search`, `ask_user`, …) declared once in the registry (`agent_tools.py`, with `writes/timeout_s/view/phases`) — schema, allowlist, capability, per-phase specs and views are generated from it. Limits per turn: 6 tool steps (`MAX_AGENT_STEPS`), 4 LLM calls (`MAX_LLM_CALLS`), 45 s deadline; read-only tools run in parallel (the Database serializes statements), write tools run on the main thread; a tool over 8 s returns a structured `tool_timeout`. A deterministic **fast path** handles rule-understood sentences with zero LLM calls (`agent_mode="fast_path"`); only `human_support`, `landlord_handover`, `handbook` and messages with `cost_input` keep the deterministic explicit path — `simulate_finance`/`calculate_cost` without `cost_input` go to the finance agent when results exist, to the graph otherwise. When the turn publishes a fresh run, a **ranking handover** makes exactly one extra tool-less LLM call to explain the top rooms through `guard_output` + `check_numbers` (grounding = the exact JSON handed to the model); every failure keeps the `confirm_template`, never a 429 or `graph_fallback`, and the call is recorded separately (`handover` step, `provenance.handover_calls`) so `llm_calls`/fast-path metrics stay clean. `ask_user(field=…)` builds chips from the real catalog (`clarify.py`) — including `city`/`budget_cap`/`destination` (real landmarks; budget levels derived from the catalog's own distribution, labeled honestly "Tiền thuê dưới X" when fees are missing; never called total cost) — and Jev/rules decide (`decisions.py`); the fallback rules never auto-accept a radius (gold-calibrated thresholds 0.85/0.40/0.2), and the ask-only fields (city/budget_cap/destination) are never auto-accepted for the renter. The model's own question and one-line reason flow through `ask_user(question=…, reason=…)` after the output guards; a question written in the message without `ask_user` is kept chip-less and counted as `question_without_chip` in the trace. Engine assumptions go to `MessageResult.assumptions` as reader sentences (off mode keeps the old concatenation); pending-question state lives in-process only (clear on chip click, field write, new run, or an off-topic turn — losing it on restart is harmless). Money fields are read deterministically from the user's own sentence, never written by the model; tool results are stripped of income and wrapped as untrusted before they reach the model; numbers in the reply are checked against user text + tool results and replaced by a template on mismatch, and output guards block income mentions and unbacked claims ("đã đặt lịch/thanh toán"). Demo mode and provider failures fall back to the rule graph (`agent_mode="graph_fallback"`); `HOMEMATCH_AGENT_FALLBACK_MODEL`, one retry and a circuit breaker sit in between. Durable per-turn traces live in `hm_agent_turns`/`hm_agent_steps` (schema v20/v21, `GET /admin/agent-turns`), and `HOMEMATCH_AGENT_RECORD/REPLAY` cassettes record/replay live evidence offline; `MessageResult.agents` and `input_analysis` expose which role ran and how the turn was routed (no raw text, no money).
- The recommendation graph has no interrupt or resume; its `rank` node acts as the ranking agent.
- Every business call from a graph goes through `ToolBox.call(agent, tool, fn, ...)`, which enforces the per-agent allowlist and a 4-step limit. New tools must be added to `AGENT_TOOLS`.
- Memory never stores money, income, loans or destinations. It prefills drafts only as `inferred`, up to 6 preferences. Preferences accumulate across sessions (removed from the form = dropped and muted; absent from 2 confirmed sessions = decayed; amenities distinctive of saved rooms = suggested with no session evidence); location and room type keep the latest value. Withdrawing consent deletes it.
- `docs/api-san-pham-v1.md` lists what is left.

**Data:** the v2 catalog in `data/catalog/rooms.json` is fully synthetic. It has 220 units: TP.HCM 120, Hà Nội 100; types `room`/`studio`/`apartment`. Rooms are assigned to landlords owner-a..d by `landlord_for`. Gold has 45 profiles (dev 15, test 30) and the oracle has 22 cases. `python -m data.generate` regenerates everything deterministically and keeps the 80 v1 rooms identical. `data/` also holds the generator, splits, gold data, cost oracles and manifests, which `eval validate` checks by hash. Do not edit frozen data without regenerating the manifests. **Crawl (CA-01..07, crawler 2.4):** crawled rooms carry `source_images` (CDN Chợ Tốt URLs, display-only, never ranking/LLM/embedding), `toilets`, `project_name` and `poster_name` — the poster display name is returned ONLY in the listing `contact` block to signed-in users and never in any Room `model_dump` output; the full crawl snapshot lives in table `chotot_raw_ads` (every raw ad, pushed in batches; `chotot_listings.raw` stays NULL for new snapshots).

## Conventions

- Tests default to offline providers. `backend/tests/conftest.py` autouse-sets demo LLM, demo auth, B1 and no embeddings. Never call paid APIs in tests. Live GPT/embedding indexing needs `backend.manage index --allow-live`.
- Use `DomainError` for expected failures. Use Pydantic at boundaries. Python uses 4-space indentation and type hints.
- Do not claim something is verified (live model quality, PG, Docker/cloud, browser E2E) unless it was actually run. The docs distinguish historical evidence from current status.
- Never commit secrets, local DBs (`.local/`), checkpoints or raw chats.
