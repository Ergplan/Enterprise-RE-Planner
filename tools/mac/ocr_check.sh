#!/bin/bash
# Runs the local-OCR check on macOS arm64 and in linux/arm64 and linux/amd64 images,
# and writes .status/ocr-check.json ({"macos-arm64": "paddleocr" | "rapidocr" | "none", ...}).
set -uo pipefail
REPO="$(cd "$(dirname "$0")/../.." && pwd)"; cd "$REPO"; mkdir -p .status
[ -x .venv-ocr/bin/python ] || { python3 -m uv venv -q --python 3.12 .venv-ocr && python3 -m uv pip install -q --python .venv-ocr/bin/python paddlepaddle paddleocr rapidocr onnxruntime pillow; }
linux() {
  docker buildx build -q --load --platform "linux/$1" -f docker/ocr-check.Dockerfile -t "billx-ocr-check:$1" . >/dev/null \
    && docker run --rm --platform "linux/$1" "billx-ocr-check:$1" 2>/dev/null | tail -1 \
    || echo '{"reader": "none", "errors": {"build_or_run": "failed"}}'
}
MAC=$(.venv-ocr/bin/python tools/mac/ocr_check.py 2>/dev/null | tail -1)
ARM=$(linux arm64)
AMD=$(linux amd64)
python3 - "$MAC" "$ARM" "$AMD" <<'PY'
import json, sys
names = ["macos-arm64", "linux-arm64", "linux-amd64"]
rows = {}
for name, raw in zip(names, sys.argv[1:]):
    try: rows[name] = json.loads(raw)
    except Exception: rows[name] = {"reader": "none", "errors": {"output": raw[-200:]}}
summary = {n: rows[n].get("reader", "none") for n in names}
json.dump({**summary, "detail": rows}, open(".status/ocr-check.json", "w"), indent=2)
print(json.dumps(summary))
PY
