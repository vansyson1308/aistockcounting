setup:
	python -m venv .venv && . .venv/bin/activate && pip install -r backend/requirements.txt
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

dataset-split:
	python tools/labeling/split_dataset.py --in datasets/vj_items/images/all --seed $${SEED:-42}
	@echo "Images and labels split into train/val/test"
	@echo "Next: make dataset-validate"

dataset-validate:
	python tools/labeling/validate_dataset.py --root datasets/vj_items

cvat-create-task:
	python tools/labeling/cvat_tasks.py create-task --folder $${FOLDER:?Set FOLDER=} --name $${NAME:?Set NAME=}

cvat-export-yolo:
	python tools/labeling/cvat_tasks.py export-yolo --task-id $${TASK_ID:?Set TASK_ID=} --out-zip $${OUT_ZIP:-datasets/vj_items/cvat_export.zip}

train-venv:
	python -m venv .venv-train && . .venv-train/bin/activate && pip install -r training/requirements-train.txt
	@echo "Activate via: source .venv-train/bin/activate"

train-yolo:
	python training/scripts/train.py --config training/configs/yolo_v1.yaml
	@echo "Next: make eval-yolo RUN_DIR=outputs/vj_items/<run>"

eval-yolo:
	python training/scripts/eval.py --run-dir $${RUN_DIR:?Set RUN_DIR=outputs/vj_items/<run_dir>}
	python training/scripts/count_accuracy.py --run-dir $${RUN_DIR:?Set RUN_DIR=outputs/vj_items/<run_dir>}
	@echo "Next: make export-model VERSION=v0001 RUN_DIR=$${RUN_DIR}"

export-model:
	python training/scripts/export.py --version $${VERSION:?Set VERSION=v0001} --run-dir $${RUN_DIR:?Set RUN_DIR=outputs/vj_items/<run_dir>}
	@echo "Set MODEL_PT_PATH/MODEL_ONNX_PATH and run make model-smoke IMAGE=scripts/generated_sample.jpg"

train-pipeline:
	python training/scripts/train_pipeline.py --config training/configs/yolo_v1.yaml --version $${VERSION:?Set VERSION=v0001}

train-all:
	$(MAKE) dataset-split
	$(MAKE) dataset-validate
	$(MAKE) train-pipeline VERSION=$${VERSION:?Set VERSION=v0001}

model-smoke:
	python backend/tools/model_smoke_test.py --image $${IMAGE:?Set IMAGE=path/to/generated_sample.jpg}

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
	cd backend && ruff check app tests
	cd frontend && npm run lint

test:
	cd backend && pytest -q
	cd frontend && npm run test

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
