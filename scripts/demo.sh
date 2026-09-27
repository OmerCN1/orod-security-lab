#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# The backend creates this file (mode 0600) on first start; OROD_API_TOKEN overrides it.
token="${OROD_API_TOKEN:-$(cat "$repo_root/data/api-token")}"

# Read the header from stdin so the token never appears in the process list.
printf 'Authorization: Bearer %s\n' "$token" | curl -sS -X POST http://127.0.0.1:8000/api/v1/runs \
  -H @- \
  -H 'content-type: application/json' \
  -d '{"repository_url":"demo://vulnerable-python","trusted":true}'
