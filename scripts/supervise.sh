#!/bin/bash
# supervise.sh — auto-restart systrader on crash
# CYBOS COM (32-bit Python + pywin32) occasionally hits native access
# violations (BUY BlockRequest, PumpWaitingMessages under disclosure flood).
# We cannot prevent them in-process, so supervise externally.
#
# Usage:  nohup ./scripts/supervise.sh > /tmp/systrader_supervise.log 2>&1 &
# Stop:   touch /tmp/systrader_stop  (then kill supervise + python)

cd "$(dirname "$0")/.."
ROOT="$(pwd)"

STOP_FILE="/tmp/systrader_stop"
STDOUT_LOG="/tmp/systrader_stdout.log"
STDERR_LOG="/tmp/systrader_stderr.log"
MIN_UPTIME=5        # restart-loop detector: if process dies < MIN_UPTIME seconds, back off
BACKOFF_MAX=60

# Clear stale stop file
rm -f "$STOP_FILE"

backoff=2
while true; do
  if [ -f "$STOP_FILE" ]; then
    echo "[$(date '+%F %T')] stop file present, exiting supervise"
    break
  fi

  start_ts=$(date +%s)
  echo "[$(date '+%F %T')] starting systrader"
  "$ROOT/.venv/Scripts/python.exe" -u main.py >> "$STDOUT_LOG" 2>> "$STDERR_LOG"
  exit_code=$?
  elapsed=$(( $(date +%s) - start_ts ))

  echo "[$(date '+%F %T')] systrader exited code=$exit_code after ${elapsed}s"

  if [ -f "$STOP_FILE" ]; then
    echo "[$(date '+%F %T')] stop file present, exiting supervise"
    break
  fi

  if [ "$elapsed" -lt "$MIN_UPTIME" ]; then
    echo "[$(date '+%F %T')] fast exit detected; backing off ${backoff}s"
    sleep "$backoff"
    backoff=$(( backoff * 2 ))
    if [ "$backoff" -gt "$BACKOFF_MAX" ]; then backoff=$BACKOFF_MAX; fi
  else
    backoff=2
    sleep 2
  fi
done
