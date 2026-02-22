#!/usr/bin/env bash
set -euo pipefail

cd frontend
npm install --no-audit --no-fund
npm run lint
npm run typecheck
npm run build
