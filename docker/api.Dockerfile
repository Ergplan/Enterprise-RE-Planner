# ergPLAN API: FastAPI engines. Built from the repository root: docker build -f docker/api.Dockerfile .
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app/apps/api
# Chromium prints the live plan to PDF (report/pdf.py, Stage 7)
RUN apt-get update && apt-get install -y --no-install-recommends chromium fonts-noto-core \
    && rm -rf /var/lib/apt/lists/*
COPY apps/api/pyproject.toml ./
COPY apps/api/ergplan ./ergplan
RUN pip install --upgrade pip && pip install -e .
COPY apps/api/alembic ./alembic
COPY apps/api/alembic.ini ./
COPY packages /app/packages
ENV ERGPLAN_DATA_DIR=/data
EXPOSE 8000
CMD ["sh", "-c", "alembic upgrade head && uvicorn ergplan.platform.app:app --host 0.0.0.0 --port 8000"]
