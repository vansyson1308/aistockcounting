setup:
	python -m venv .venv && . .venv/bin/activate && pip install -r backend/requirements-dev.txt
	cd frontend && npm install

dev:
	docker compose up --build

up:
	docker compose up --build -d

down:
	docker compose down -v

logs:
	docker compose logs -f --tail=200

bootstrap:
	docker compose up -d db
	docker compose exec -T db psql -U $${POSTGRES_USER:-postgres} -d $${POSTGRES_DB:-stockdb} -c "CREATE EXTENSION IF NOT EXISTS pgcrypto;"

# Staging / production-lite
staging-up:
	docker compose --env-file .env.staging.example -f docker-compose.staging.yml up -d

staging-down:
	docker compose --env-file .env.staging.example -f docker-compose.staging.yml down

staging-smoke:
	./ops/smoke_test.sh

backup-local:
	./ops/backup/backup_all.sh

restore-local:
	@echo "Usage: ./ops/backup/restore_postgres.sh <dump> [db] && ./ops/backup/restore_minio.sh <tar.gz>"

cvat-up:
	cd cvat && docker compose --env-file .env.cvat up -d
	@echo "CVAT UI: http://127.0.0.1:8081"

cvat-down:
	cd cvat && docker compose --env-file .env.cvat down

cvat-logs:
	cd cvat && docker compose --env-file .env.cvat logs -f --tail=200

label-export-images:
	python tools/labeling/export_images.py --out datasets/vj_items/images/all --limit $${LIMIT:-5}
	@echo "Next: make dataset-split"

dataset-split: data-split

dataset-validate:
	python tools/labeling/validate_dataset.py --root datasets/vj_items

cvat-create-task:
	python tools/labeling/cvat_tasks.py create-task --folder $${FOLDER:?Set FOLDER=} --name $${NAME:?Set NAME=}

cvat-export-yolo:
	python tools/labeling/cvat_tasks.py export-yolo --task-id $${TASK_ID:?Set TASK_ID=} --out-zip $${OUT_ZIP:-datasets/vj_items/cvat_export.zip}

train-venv:
	python3 -m venv .venv-train && .venv-train/bin/pip install -r training/requirements-yolox.txt
	.venv-train/bin/pip install --no-deps --no-build-isolation yolox==0.3.0

data-ingest:
	python tools/labeling/ingest_raw.py

data-prelabel:
	python tools/labeling/prelabel.py --backend $${BACKEND:-owlv2}

data-split:
	python tools/labeling/split_dataset.py --seed $${SEED:-42}

data-verify:
	python tools/labeling/split_dataset.py --verify

train-yolox:
	.venv-train/bin/python training/train_yolox.py all --config $${CONFIG:-training/configs/yolox_trayagent.yaml}

fetch-model:
	scripts/fetch_model.sh

eval-agent:
	python training/scripts/agent_eval.py --backend $${BACKEND:-onnx} --model $${MODEL:-models/trayagent_v1.onnx} --machine $${MACHINE:-local} --out reports/agentic

model-smoke:
	python backend/tools/model_smoke_test.py --image $${IMAGE:?Set IMAGE=path/to/image.jpg}

backend-dev:
	cd backend && uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

frontend-dev:
	cd frontend && npm run dev

frontend-build:
	cd frontend && npm run build

frontend-lint:
	cd frontend && npm run lint

frontend-typecheck:
	cd frontend && npm run typecheck

lint:
	cd backend && ruff check app tests && black --check -q app tests
	cd frontend && npm run lint
	python3 scripts/license_gate.py

test:
	cd backend && pytest -q
	cd frontend && npm run test

backend-venv:
	python3 -m venv .venv && .venv/bin/pip install -r backend/requirements-dev.txt

# Multi-arch backend image (amd64 + arm64/Graviton)
image-multiarch:
	docker buildx build --platform linux/amd64,linux/arm64 -t trayagent-backend:dev ./backend

# --- Football pivot: Phase 0a (ml core, camsim, licensing) ---
ml-venv:
	python3 -m venv .venv-ml && .venv-ml/bin/pip install -r ml/requirements-dev.txt

ml-lint:
	.venv-ml/bin/ruff check ml tools/camsim scripts/license_gate.py conftest.py

ml-test:
	.venv-ml/bin/python -m pytest ml/tests tools/camsim/tests -q

license-check:
	python3 scripts/license_gate.py

camsim:
	.venv-ml/bin/python -m tools.camsim.run --all --heights 8 12 15 20 25 --out outputs/camsim

# --- AWS (infra/aws, CDK v2 Python) ---
infra-venv:
	python3 -m venv infra/aws/.venv && infra/aws/.venv/bin/pip install -r infra/aws/requirements.txt -r infra/aws/requirements-dev.txt
	cd infra/aws && npm ci

infra-test:
	cd infra/aws && .venv/bin/python -m pytest -q

infra-synth:
	cd infra/aws && env -u AWS_ACCESS_KEY_ID -u AWS_SECRET_ACCESS_KEY -u AWS_SESSION_TOKEN ./node_modules/.bin/cdk synth --quiet

aws-deploy:
	scripts/aws/deploy.sh

aws-teardown:
	scripts/aws/teardown.sh
