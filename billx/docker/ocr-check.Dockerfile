# Stage 0 local-OCR check image (section 3.1); not shipped. Mirrors the engine's base.
FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 libgomp1 fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir paddlepaddle paddleocr rapidocr onnxruntime pillow
COPY tools/mac/ocr_check.py /ocr_check.py
ENTRYPOINT ["python", "/ocr_check.py"]
