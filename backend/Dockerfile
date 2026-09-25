# syntax=docker/dockerfile:1.7
# Multi-arch (linux/amd64, linux/arm64) backend image. The arm64 variant runs
# on AWS Graviton. opencv-python-headless 5.0.0.93 ships manylinux wheels
# for both x86_64 and aarch64, so nothing is compiled here.
ARG BASE_IMAGE=public.ecr.aws/docker/library/python:3.11-slim-bookworm
FROM ${BASE_IMAGE} AS runtime

ARG TARGETPLATFORM
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONPATH=/app

WORKDIR /app

COPY requirements.txt ./
# Optional build secret "ca": a corporate/proxy CA bundle for pip (never baked in).
RUN --mount=type=secret,id=ca,required=false \
    if [ -f /run/secrets/ca ]; then export PIP_CERT=/run/secrets/ca; fi; \
    pip install -r requirements.txt \
    && python -c "import cv2, sys; v = cv2.__version__; print('opencv', v, '${TARGETPLATFORM}'); sys.exit(0 if v.startswith('5') else 1)"

COPY . .
RUN useradd --create-home --uid 10001 app && mkdir -p /app/models && chown -R app /app/models
USER app

# One worker: the CV work runs in threads (OpenCV releases the GIL) and the live
# agent-progress registry is in-process.
ENV RUN_MIGRATIONS=true
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=5s --retries=5 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8000/health', timeout=4).status == 200 else 1)"
ENTRYPOINT ["/app/docker-entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
