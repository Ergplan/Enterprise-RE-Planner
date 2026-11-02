# The billx engine image (build prompt 5.0, Stage 2.5; developer guide section 12).
#
# One CPU image for linux/amd64 and linux/arm64 with the local OCR readers built in: PaddleOCR
# with its models downloaded at build time, and RapidOCR with the models its wheel ships. The
# code picks PaddleOCR where it initialises and RapidOCR otherwise (billx/reader/ocr), so one
# Dockerfile serves both platforms. It runs `billx serve` on port 8080 as a non-root user, needs
# no network at run time, and writes only under /data (BILLX_DATA_DIR): the root filesystem can
# be mounted read-only with a tmpfs on /tmp (docker/compose.yaml).
#
#   docker buildx build --platform linux/arm64 --load -f docker/engine.Dockerfile -t billx:local .
#   docker run --rm billx:local --help
#   docker run --rm --network none --read-only --tmpfs /tmp --entrypoint python billx:local \
#       docker/ocr_warmup.py          # which engine this platform picks; proves no download runs
#
# Secrets never enter this file: BILLX_TOKEN and the model keys come from the environment at run
# time. Image sizes and build times per platform are recorded in the Stage 2 report.
FROM python:3.12-slim

# Build metadata CI passes in (--build-arg); the default keeps a local build honest.
ARG VCS_REF=unknown
LABEL org.opencontainers.image.title="billx engine" \
      org.opencontainers.image.source="https://gitlab.com/icac1/ocr-bill-extraction" \
      org.opencontainers.image.revision="${VCS_REF}"

# Python writes no .pyc at run time (the root filesystem is read-only in production), prints
# unbuffered so the JSON logs reach docker as they happen, and pip keeps no cache (image size).
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# The system libraries the OCR runtimes load: libgl1 and libglib2.0-0 for OpenCV (the image code
# of PaddleOCR and RapidOCR), libgomp1 for Paddle's OpenMP threads. No recommends, no apt lists.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# The service user (uid 10001, as the build prompt fixes it) and the one writable path, /data.
RUN useradd --create-home --uid 10001 --user-group billx \
    && mkdir -p /data && chown billx:billx /data

WORKDIR /app

# The package and what it reads beside itself: config/ (settings.py), profiles/ (the label rule,
# the gate and the field map resolve `profiles/` relative to the package, with no env override)
# and the contract text. docs/, tests/ and tools/ stay out (.dockerignore).
COPY --chown=billx:billx pyproject.toml ./
COPY --chown=billx:billx billx ./billx
COPY --chown=billx:billx config ./config
COPY --chown=billx:billx profiles ./profiles
COPY --chown=billx:billx contract ./contract
COPY --chown=billx:billx docker/ocr_warmup.py ./docker/ocr_warmup.py

# paddlepaddle first, from Paddle's own index: PyPI carries no linux/arm64 wheel past 3.2.2, while
# the `ocr` extra needs >=3.3 (the version the Mac verified in Stage 0, decisions.md). Pinned so
# both platforms run the same release; --no-deps and --index-url (not --extra-index-url) mean this
# is the only package that index may supply. Then an editable install keeps the package at /app,
# so config/ and profiles/ resolve next to it, and the `ocr` extra brings paddleocr, rapidocr and
# onnxruntime (and paddlepaddle's own dependencies) from PyPI on both platforms.
ARG PADDLEPADDLE_VERSION=3.3.1
RUN pip install --no-deps --index-url https://www.paddlepaddle.org.cn/packages/stable/cpu/ \
        "paddlepaddle==${PADDLEPADDLE_VERSION}" \
    && pip install --editable '.[ocr]'

# Where things live at run time. PADDLE_PDX_CACHE_HOME is where PaddleOCR (PaddleX) keeps its
# models: inside the image, under the service user's home, filled by the warm-up below.
# BILLX_OCR_CACHE keeps the OCR word cache under /data, the only writable path.
# BILLX_MAX_JOBS=2: measured peaks of 2061 MiB with four workers and 1850 MiB with two, with the
# same throughput (OCR is serialised inside the container); four jobs are still accepted and
# queued. Set 4 where memory allows (docs/release-notes/0.1.md).
# PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK stops PaddleX probing the model hosts before it uses the
# local models (the warm-up log shows that probe); without it a container with no network waits.
ENV HOME=/home/billx \
    PADDLE_PDX_CACHE_HOME=/home/billx/.paddlex \
    PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK=True \
    BILLX_DATA_DIR=/data \
    BILLX_MAX_JOBS=2 \
    BILLX_OCR_CACHE=/data/cache/ocr \
    BILLX_CONFIG_DIR=/app/config \
    BILLX_PROFILES_DIR=/app/profiles

USER billx

# The warm-up: read a tiny synthetic page through the engine's own OCR path, which makes
# PaddleOCR download its detection and recognition models into the image (owned by the service
# user) and proves that one engine reads on this platform. The word cache is off so nothing is
# written under /data at build time.
RUN BILLX_OCR_CACHE=off python docker/ocr_warmup.py

# The API (contract 1.0 section 3): port 8080, the bearer token from BILLX_TOKEN. The health
# check reads the token from the environment and calls GET /v1/health with Python's standard
# library, so no curl is installed and no token is written here.
EXPOSE 8080
VOLUME ["/data"]
HEALTHCHECK --interval=30s --timeout=5s --start-period=90s --retries=3 \
    CMD python -c "import os, sys, urllib.request as u; r = u.Request('http://127.0.0.1:8080/v1/health', headers={'Authorization': 'Bearer ' + os.environ.get('BILLX_TOKEN', '')}); sys.exit(0 if u.urlopen(r, timeout=4).status == 200 else 1)"

ENTRYPOINT ["billx"]
CMD ["serve"]
