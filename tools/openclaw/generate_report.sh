#!/usr/bin/env bash
# ============================================================================
# generate_report.sh — Generate Markdown patrol daily report
# ============================================================================

set -euo pipefail

TIMEOUT="${TIMEOUT:-30}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKSPACE_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
REPORT_SCRIPT="$WORKSPACE_ROOT/src/raspbot_vision/raspbot_vision/generate_patrol_report.py"
DB_PATH="$WORKSPACE_ROOT/data/patrol/patrol_events.db"
DEFAULT_OUTPUT_DIR="$WORKSPACE_ROOT/data/patrol/exports"
ROS_SETUP="/opt/ros/jazzy/setup.bash"
INSTALL_SETUP="$WORKSPACE_ROOT/install/setup.bash"

source_if_exists() {
  local file="$1"
  if [ -f "$file" ]; then
    # shellcheck disable=SC1090
    set +u
    source "$file"
    set -u
  fi
}

source_if_exists "$ROS_SETUP"
source_if_exists "$INSTALL_SETUP"

usage() {
  cat <<EOF
Usage: $(basename "$0") [OPTIONS]

Options:
  --date YYYY-MM-DD   Report date (default: today)
  --days N            Date range in days (default: 1)
  --output FILE       Output file path (default: auto-generated under exports/)
  --help              Show this help
EOF
}

DATE_ARG=""
DAYS_ARG=""
OUTPUT_ARG=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --date)
      DATE_ARG="$2"
      shift 2
      ;;
    --days)
      DAYS_ARG="$2"
      shift 2
      ;;
    --output|-o)
      OUTPUT_ARG="$2"
      shift 2
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1"
      usage
      exit 2
      ;;
  esac
done

if [ ! -f "$DB_PATH" ]; then
  echo "{\"error\": \"database not found\", \"path\": \"$DB_PATH\"}" >&2
  exit 1
fi

if [ ! -f "$REPORT_SCRIPT" ]; then
  echo "{\"error\": \"report script not found\", \"path\": \"$REPORT_SCRIPT\"}" >&2
  exit 1
fi

if ! python3 - <<'PY' >/dev/null 2>&1
try:
    import jinja2  # noqa: F401
except Exception as exc:
    raise SystemExit(f'jinja2 import failed: {exc}')
PY
then
  echo "{\"error\": \"missing python dependency\", \"module\": \"jinja2\"}" >&2
  exit 1
fi

mkdir -p "$DEFAULT_OUTPUT_DIR"

if [ -z "$OUTPUT_ARG" ]; then
  TIMESTAMP=$(date -u +%Y%m%d_%H%M%S)
  OUTPUT_ARG="$DEFAULT_OUTPUT_DIR/report_${TIMESTAMP}.md"
fi

echo "generated_at: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "hostname: $(hostname)"
echo "whoami: $(whoami)"
echo "HOME: ${HOME:-<unset>}"
echo "workspace_root: $WORKSPACE_ROOT"
echo "db_path: $DB_PATH"
echo "report_script: $REPORT_SCRIPT"
echo "output_path: $OUTPUT_ARG"
echo

PY_ARGS=(--db "$DB_PATH" --output "$OUTPUT_ARG")
if [ -n "$DATE_ARG" ]; then
  PY_ARGS+=(--date "$DATE_ARG")
fi
if [ -n "$DAYS_ARG" ]; then
  PY_ARGS+=(--days "$DAYS_ARG")
fi

set +e
REPORT_OUTPUT="$(timeout "$TIMEOUT" python3 "$REPORT_SCRIPT" "${PY_ARGS[@]}" 2>&1)"
REPORT_EXIT=$?
set -e
if [ $REPORT_EXIT -ne 0 ]; then
  echo "ERROR: report generation failed (exit_code=$REPORT_EXIT)" >&2
  [ -n "$REPORT_OUTPUT" ] && printf '%s\n' "$REPORT_OUTPUT" >&2
  exit "$REPORT_EXIT"
fi

printf '%s\n' "$REPORT_OUTPUT"

if [ -f "$OUTPUT_ARG" ]; then
  echo "report_path: $OUTPUT_ARG"
  echo "report_size_bytes: $(stat --format=%s "$OUTPUT_ARG" 2>/dev/null || echo unknown)"
  exit 0
fi

echo "{\"error\": \"report file not created\", \"path\": \"$OUTPUT_ARG\"}" >&2
exit 1
