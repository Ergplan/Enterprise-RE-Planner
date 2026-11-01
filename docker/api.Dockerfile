# ergPLAN API: FastAPI engines. Built from the repository root: docker build -f docker/api.Dockerfile .
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app/apps/api
# tesseract: OCR for scanned regulation pages (documents/ocr.py), e.g. the UPERC CRE Regulations 2024
RUN apt-get update && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-eng \
    && rm -rf /var/lib/apt/lists/*
# Dependencies before the code, so a code change rebuilds only the last layers (an empty package lets
# the editable install resolve; the real package is copied over it below)
COPY apps/api/pyproject.toml ./
RUN mkdir -p ergplan && touch ergplan/__init__.py && pip install --upgrade pip && pip install -e .
# Chromium for printing the live plan to PDF (report/pdf.py, Stage 7)
RUN python -m playwright install --with-deps chromium
COPY apps/api/ergplan ./ergplan
COPY apps/api/alembic ./alembic
COPY apps/api/alembic.ini ./
COPY packages /app/packages
ENV ERGPLAN_DATA_DIR=/data
EXPOSE 8000
CMD ["sh", "-c", "alembic upgrade head && uvicorn ergplan.platform.app:app --host 0.0.0.0 --port 8000"]
