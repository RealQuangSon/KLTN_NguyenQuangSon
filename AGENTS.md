# Repository Guidelines

Thesis scope: an AI agent that recommends rental rooms, studios and apartments in TP.HCM and Hà Nội by needs and financial capacity. Recommendations are published to the renter right after ranking (decision 05/11/2026 removed landlord approval); landlords learn about a renter only when the renter messages them or requests a viewing (the lead pipeline was removed on 19/11/2026). The platform also has a tenant portal, automation jobs, an Admin Console, landlord PMS and a landlord co-pilot. Read `docs/README.md` first.

## Project Structure & Module Organization

- `frontend/src/`: React/TypeScript UI, components, workspaces and styles; `src/tests/` holds Vitest fixtures/tests.
- `backend/app/`: FastAPI, schemas, auth, deterministic finance/ranking, SQLite/PostgreSQL ledger and LangGraph workflows. Agent logic belongs here.
- `backend/tests/`: pytest; `backend/manage.py` supplies setup/import/seed/index commands; `backend/demo.py` runs offline.
- `data/`: synthetic catalog, generator, profiles/splits, independent cost oracles and manifests.
- `eval/`: CLI, metrics, protocol, tests and development outputs. Human relevance labels remain separate.
- `infra/`: local scripts (check, run, PostgreSQL, backup/restore, live run) and env inventory. The project runs on localhost only; there is no container or cloud deployment. `docs/` holds the specification, design and contracts.

## Build, Test, and Development Commands

Run from repository root:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.lock
npm --prefix frontend ci
.venv/bin/python -m pytest
npm --prefix frontend test
npm --prefix frontend run build
.venv/bin/python -m infra.smoke_api --in-process
.venv/bin/python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 --workers 1
npm --prefix frontend run dev
```

These install dependencies, test Python/UI, build assets, exercise an isolated API and run services. See README for seed credentials/env exports. `python -m eval validate` checks dataset hashes/schema; `bash infra/check-local.sh` combines offline checks. PostgreSQL tests require `HOMEMATCH_TEST_DATABASE_URL`.

## Coding Style & Naming Conventions

Use four-space Python indentation, `snake_case`, `PascalCase` classes, type hints and Pydantic boundaries. Use `DomainError` for expected failures. Money stays in `costs.py` with `Decimal` and existing VND rounding. Follow frontend Prettier formatting (`npm --prefix frontend run format`), PascalCase components and camelCase functions. No Python formatter/linter is configured.

## Testing Guidelines

Name pytest files `test_*.py` and UI tests `*.test.tsx`. Use temporary DBs, close connections and default to offline providers. Test changed behaviors: null/zero costs, hard filters, ownership, result visibility, stale replies/versions, CAS, keys and restart. No numerical coverage threshold exists. Fixture tests do not prove live model quality, browser integration or PG behavior.

## Commit & Pull Request Guidelines

Follow the existing history: focused conventional-style messages with a scope, written in Vietnamese, such as `feat(search): thêm bộ lọc tiện ích`. PRs describe behavior, report actual checks/limitations and include UI screenshots. Coordinate parallel agents by directory ownership and shared API contract.

## Security & Architecture Constraints

Never commit secrets, real financial data, local DBs or raw checkpoints/chats. Backend does not auto-load `.env`. Keep one API worker; finance, permissions and publication remain deterministic. Renters only see published recommendations for their current profile and catalog version. Landlords never see renter income; AI chat is stored PII-masked. Do not claim integrations (payments, e-signature, email, social posting) that are only substituted. Freeze research inputs before test runs and obtain independent human labels.
