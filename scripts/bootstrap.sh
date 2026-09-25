#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

command -v uv >/dev/null || { echo "uv is required"; exit 1; }
command -v npm >/dev/null || { echo "npm is required"; exit 1; }

(cd backend && uv sync)
(cd frontend && npm install)

echo "Bootstrap complete. Start 'make backend' and 'make frontend'."
