# Security Notes

## Threat model (MVP)
- Untrusted user uploads (malicious file payloads).
- API abuse (request flooding).
- Object storage path/key tampering.
- Sensitive internal error leakage.
- Missing auth in internal deployments.

## Mitigations implemented
- Strict upload validation:
  - Content-Type + extension allowlist (JPEG/PNG).
  - File-size cap (10MB).
  - Magic-byte check + Pillow decode verification.
- Safe object keys:
  - UUID-only generated object keys; no user-supplied paths.
- Rate limiting:
  - In-memory per-client/path limiter middleware.
- Inference concurrency control:
  - Semaphore to cap simultaneous inference workload.
- Error handling + request tracing:
  - User-facing safe error messages only.
  - Structured logging with request id (`X-Request-ID`).
- Optional auth gate:
  - `ENABLE_SIMPLE_AUTH=true` enables `X-STAFF-ID` or `X-API-TOKEN` requirement.

## Dependency and audit policy
- Backend dependencies are pinned in `backend/requirements.txt`.
- Run locally/CI:
  - `pip install pip-audit`
  - `pip-audit -r backend/requirements.txt`
- In restricted/offline environments, document that audit execution is deferred.

## Operational recommendations
- Rotate MinIO/Postgres credentials for non-local environments.
- Terminate TLS at edge/load balancer and preserve forwarded proto headers.
- Keep `MOCK_MODE=false` in production.
