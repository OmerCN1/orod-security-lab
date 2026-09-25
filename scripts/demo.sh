#!/usr/bin/env bash
set -euo pipefail

curl -sS -X POST http://127.0.0.1:8000/api/v1/runs \
  -H 'content-type: application/json' \
  -d '{"repository_url":"demo://vulnerable-python","trusted":true}'
