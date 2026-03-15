#!/usr/bin/env bash
set -euo pipefail

cd frontend
npm install --no-audit --no-fund --legacy-peer-deps
npm run lint
npm run typecheck
npm run test
npm run build
