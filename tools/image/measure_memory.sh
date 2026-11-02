#!/usr/bin/env bash
# The memory figure each release states (developer guide section 12; build prompt Stage 2.5):
# the peak memory of the engine container while it reads 4 bills at once.
#
# Starts the image with BILLX_MAX_JOBS=4 (read-only root filesystem, tmpfs /tmp, a throwaway
# volume on /data, a random token that is never printed), writes the synthetic set with the
# image's own `billx synth`, submits 4 digital electricity PDFs to POST /v1/jobs at the same
# moment, and samples `docker stats` once a second until every job is done or failed. It prints
# one line with the baseline and the peak in MiB, and optionally the same as JSON.
#
#   tools/image/measure_memory.sh [IMAGE] [--jobs N] [--timeout SECONDS] [--synth DIR] [--json FILE]
#
# IMAGE defaults to $BILLX_IMAGE, else billx:local. Runs on this Mac (arm64, bash 3.2) and on a
# Linux CI runner with docker and curl. Exit 0 when every job finished, 1 on a timeout, 2 when
# the API never became healthy (for example before `billx serve` exists in the image: the script
# still reports what it sampled). The integrator records the peak in the release notes.
set -euo pipefail

IMAGE="${BILLX_IMAGE:-billx:local}"
JOBS=4
TIMEOUT=900          # seconds to wait for the jobs
HEALTH_WAIT=120      # seconds to wait for GET /v1/health
PORT="${BILLX_MEASURE_PORT:-18080}"
SYNTH=""
JSON_OUT=""

while [ $# -gt 0 ]; do
  case "$1" in
    --jobs) JOBS="$2"; shift 2 ;;
    --timeout) TIMEOUT="$2"; shift 2 ;;
    --synth) SYNTH="$2"; shift 2 ;;
    --json) JSON_OUT="$2"; shift 2 ;;
    -h|--help) sed -n '2,17p' "$0"; exit 0 ;;
    *) IMAGE="$1"; shift ;;
  esac
done

RUN_ID="measure-$$-$(date +%s)"
NAME="billx-$RUN_ID"
VOLUME="billx-$RUN_ID-data"
WORK="$(mktemp -d)"
URL="http://127.0.0.1:$PORT"

cleanup() {
  docker rm -f "$NAME" >/dev/null 2>&1 || true
  docker volume rm "$VOLUME" >/dev/null 2>&1 || true
  rm -rf "$WORK"
}
trap cleanup EXIT

# --- the synthetic set: written by the image itself, so no host venv is needed -----------------
if [ -z "$SYNTH" ]; then
  SYNTH="$WORK/synth"
  mkdir -p "$SYNTH" && chmod 777 "$SYNTH"   # the container writes as uid 10001
  docker run --rm -v "$SYNTH:/out" "$IMAGE" synth --out /out --seed 1 --no-planted >/dev/null
fi
# Digital electricity PDFs only: the other synthetic documents are gas, water, telecom, an
# invoice, a receipt and a letter (named by their kind), which the measurement does not need.
FILES=()
for f in "$SYNTH"/*.digital.pdf; do
  case "$(basename "$f")" in
    gas-*|invoice-*|letter-*|receipt-*|telecom-*|water-*) ;;
    *) FILES+=("$f") ;;
  esac
done
[ ${#FILES[@]} -gt 0 ] || { echo "measure_memory: no digital electricity PDF in $SYNTH" >&2; exit 2; }

# --- the token: random, handed to the container through the environment and to curl through a
# header file (mode 600), so it is on no command line and in no output -------------------------
BILLX_TOKEN="$(head -c 32 /dev/urandom | od -An -tx1 | tr -d ' \n')"
export BILLX_TOKEN
umask 077
printf 'Authorization: Bearer %s\n' "$BILLX_TOKEN" > "$WORK/headers"
umask 022

# --- start the engine as compose does: read-only root, tmpfs /tmp, /data on a volume ------------
docker volume create "$VOLUME" >/dev/null
docker run -d --name "$NAME" \
  --read-only --tmpfs /tmp:size=256m \
  -v "$VOLUME:/data" \
  -e BILLX_TOKEN -e BILLX_API_MODE=esgos-1.1 -e "BILLX_MAX_JOBS=$JOBS" \
  -p "127.0.0.1:$PORT:8080" \
  "$IMAGE" serve >/dev/null

# One `docker stats` sample in MiB (the "used" part of "123.4MiB / 1.94GiB"); empty if the
# container is gone.
sample_mib() {
  docker stats --no-stream --format '{{.MemUsage}}' "$NAME" 2>/dev/null \
    | awk -F'/' '{ v=$1; gsub(/ /, "", v);
        if (v ~ /GiB$/) printf "%.1f\n", substr(v, 1, length(v)-3) * 1024;
        else if (v ~ /MiB$/) printf "%.1f\n", substr(v, 1, length(v)-3);
        else if (v ~ /KiB$/) printf "%.1f\n", substr(v, 1, length(v)-3) / 1024;
        else if (v ~ /B$/) printf "%.1f\n", substr(v, 1, length(v)-1) / 1048576; }'
}
running() { [ "$(docker inspect -f '{{.State.Running}}' "$NAME" 2>/dev/null)" = "true" ]; }
max_of() { awk -v a="$1" -v b="$2" 'BEGIN { print (a+0 > b+0) ? a : b }'; }

report() {
  # $1 status, $2 seconds, $3 finished, $4 failed
  echo "measure_memory: image=$IMAGE jobs=$JOBS submitted=${SUBMITTED:-0} finished=$3 failed=$4 seconds=$2 baseline_mib=${BASELINE:-0} peak_mib=${PEAK:-0} status=$1"
  if [ -n "$JSON_OUT" ]; then
    printf '{"image": "%s", "jobs": %s, "submitted": %s, "finished": %s, "failed": %s, "seconds": %s, "baseline_mib": %s, "peak_mib": %s, "status": "%s"}\n' \
      "$IMAGE" "$JOBS" "${SUBMITTED:-0}" "$3" "$4" "$2" "${BASELINE:-0}" "${PEAK:-0}" "$1" > "$JSON_OUT"
  fi
}

# --- wait for GET /v1/health ---------------------------------------------------------------------
PEAK=0; BASELINE=0; SUBMITTED=0
START=$(date +%s)
healthy=no
while [ $(( $(date +%s) - START )) -lt "$HEALTH_WAIT" ]; do
  if ! running; then break; fi
  if curl -fsS -H @"$WORK/headers" "$URL/v1/health" >/dev/null 2>&1; then healthy=yes; break; fi
  m="$(sample_mib)"; [ -n "$m" ] && PEAK="$(max_of "$PEAK" "$m")"
  sleep 1
done
if [ "$healthy" != yes ]; then
  echo "measure_memory: the API did not answer GET /v1/health within ${HEALTH_WAIT}s; container log tail:" >&2
  docker logs --tail 5 "$NAME" >&2 2>&1 || true
  report api_unavailable $(( $(date +%s) - START )) 0 0
  exit 2
fi
BASELINE="$(sample_mib)"; PEAK="$(max_of "$PEAK" "$BASELINE")"

# --- submit the jobs at the same moment (one curl per file, in the background) ------------------
i=0
for f in "${FILES[@]}"; do
  [ "$i" -lt "$JOBS" ] || break
  i=$((i + 1))
  curl -sS -o "$WORK/submit-$i.json" -H @"$WORK/headers" \
    -F "file=@$f" \
    -F "options={\"request_id\":\"$RUN_ID-$i\",\"product\":\"measure\",\"allow_cloud_model\":false};type=application/json" \
    "$URL/v1/jobs" >/dev/null 2>&1 &
done
wait
JOB_IDS=()
for n in $(seq 1 "$i"); do
  id="$(sed -n 's/.*"job_id" *: *"\([^"]*\)".*/\1/p' "$WORK/submit-$n.json" 2>/dev/null | head -1)"
  [ -n "$id" ] && JOB_IDS+=("$id")
done
SUBMITTED=${#JOB_IDS[@]}
if [ "$SUBMITTED" -eq 0 ]; then
  echo "measure_memory: no job was accepted by POST /v1/jobs" >&2
  report submit_failed $(( $(date +%s) - START )) 0 0
  exit 2
fi

# --- sample until every job is done or failed ----------------------------------------------------
T0=$(date +%s)
finished=0; failed=0
while [ $(( $(date +%s) - T0 )) -lt "$TIMEOUT" ]; do
  m="$(sample_mib)"; [ -n "$m" ] && PEAK="$(max_of "$PEAK" "$m")"
  finished=0; failed=0
  for id in "${JOB_IDS[@]}"; do
    st="$(curl -fsS -H @"$WORK/headers" "$URL/v1/jobs/$id" 2>/dev/null | sed -n 's/.*"status" *: *"\([^"]*\)".*/\1/p' | head -1)"
    case "$st" in
      done) finished=$((finished + 1)) ;;
      failed) finished=$((finished + 1)); failed=$((failed + 1)) ;;
    esac
  done
  [ "$finished" -ge "$SUBMITTED" ] && break
  running || break
  sleep 1
done
SECONDS_TAKEN=$(( $(date +%s) - T0 ))
if [ "$finished" -ge "$SUBMITTED" ]; then
  report ok "$SECONDS_TAKEN" "$finished" "$failed"
  exit 0
fi
report timeout "$SECONDS_TAKEN" "$finished" "$failed"
exit 1
