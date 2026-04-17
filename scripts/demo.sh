#!/usr/bin/env bash
# Quick end-to-end demo for a grader: health -> refresh -> museums -> regression
# with jq-pretty output. Run this once the docker stack is up:
#
#     wsl docker compose -f docker/docker-compose.yml up -d
#     ./scripts/demo.sh
#
# Requires curl + jq on PATH. Uses $MUSEUMS_API_URL or localhost:8000.

set -euo pipefail

API="${MUSEUMS_API_URL:-http://localhost:8000}"
HEADERS=()
if [[ -n "${MUSEUMS_REFRESH_API_KEY:-}" ]]; then
    HEADERS=(-H "X-API-Key: ${MUSEUMS_REFRESH_API_KEY}")
fi

section() {
    echo
    echo "=== $1 ==="
}

section "1. Health check"
curl -fsS "${API}/health" | jq .

section "2. Refresh data (first run: 30-120s; subsequent: 429 within 24h)"
if curl -fsS -X POST "${API}/refresh" "${HEADERS[@]}" | jq . 2>/dev/null; then
    echo "(refresh complete)"
else
    echo "(likely cooldown — that's fine; try ?force=true to bypass)"
fi

section "3. Top 5 museums by visitor count"
curl -fsS "${API}/museums?limit=50" \
    | jq '.items | sort_by(-(.visitor_records | map(.visitors) | max // 0)) | .[0:5] | map({name, city_name, latest: (.visitor_records | max_by(.year) | .visitors)})'

section "4. Data coverage snapshot"
curl -fsS "${API}/cities/populations?limit=200" \
    | jq '.items | {total_cities: length, cities_with_pop: [.[] | select(.population_history | length > 0)] | length, densest: [.[] | {city: .name, n_years: (.population_history | length)}] | sort_by(-.n_years) | .[0:5]}'

section "5. Regression result"
curl -fsS "${API}/regression" \
    | jq '{coefficient, intercept, r_squared, n_samples, top_residuals: (.points | sort_by(-(.residual | fabs)) | .[0:3] | map({museum: .museum_name, city: .city_name, residual}))}'

echo
echo "Done. Open http://localhost:8888 for the Jupyter notebook, or http://localhost:8000/docs for the OpenAPI page."
