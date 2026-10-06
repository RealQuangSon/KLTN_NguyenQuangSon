#!/usr/bin/env bash
set -euo pipefail
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$ROOT"
PYTHON=${HOMEMATCH_PYTHON:-.venv/bin/python}
export HOMEMATCH_LLM_MODE=demo

"$PYTHON" -m pip check
"$PYTHON" -m eval validate
"$PYTHON" -m eval oracle
"$PYTHON" -m eval extraction --split dev
"$PYTHON" -m eval ranking --split dev
"$PYTHON" -m eval metrics
"$PYTHON" -m eval invariants --split dev
"$PYTHON" -m eval grounding
"$PYTHON" -m eval measure
"$PYTHON" -m eval report
"$PYTHON" -m pytest backend/tests eval/tests
npm --prefix frontend run test -- --run
npm --prefix frontend run build
"$PYTHON" -m backend.demo
"$PYTHON" -m infra.smoke_api --in-process
