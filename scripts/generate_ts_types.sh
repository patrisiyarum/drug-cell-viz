#!/usr/bin/env bash
# Regenerate frontend TS types from the FastAPI OpenAPI schema.
# Run after any change to apps/api/src/api/models/*.py.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OPENAPI_JSON="/tmp/drug-cell-viz-openapi.json"

cd "$ROOT/apps/api"
uv run python -c "from api.main import app; import json; print(json.dumps(app.openapi()))" > "$OPENAPI_JSON"

cd "$ROOT/apps/web"
pnpm exec openapi-typescript "$OPENAPI_JSON" -o lib/api-types.ts

echo "Generated apps/web/lib/api-types.ts"
