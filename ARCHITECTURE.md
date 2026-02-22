# MVP v0.1 Architecture & Task Breakdown

## Architecture (PRD-aligned)
- **Frontend (Next.js 14 PWA, Tailwind):** mobile-first scan flow (camera/upload), detection preview with box overlay, manual override form, save flow, history + filters/pagination, stats dashboard.
- **Backend (FastAPI, async SQLAlchemy, Alembic):** REST APIs `/api/v1/count-items`, `/api/v1/save`, `/api/v1/history`, `/api/v1/stats`; validation/security; inference service with ONNX fallback mock mode.
- **Data Layer:** PostgreSQL `counts` table + indexes per PRD.
- **Object Storage:** MinIO bucket for original and thumbnail images through S3 API.
- **Infra:** Docker Compose services (frontend, backend, db, minio, nginx) with health checks.

## Iterative Task Breakdown
1. **Scaffold monorepo**: backend/frontend/infra folders, lint+format+test tooling, env templates.
2. **Backend foundation**: config, DB models, migrations, API contract schemas, centralized error handling.
3. **Inference + storage**: upload validation, MinIO save + thumbnail generation, ONNX/mock inference.
4. **Frontend MVP flows**: scan/camera/upload, overlay render, manual override & save, history, stats.
5. **Deployment + QA**: compose stack, nginx reverse proxy, Makefile targets, smoke/integration tests, acceptance checklist verification.
