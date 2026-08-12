#!/usr/bin/env bash
# ============================================================================
# query_latest_patrol.sh — Query latest patrol records from SQLite
# ============================================================================

set -euo pipefail

TIMEOUT="${TIMEOUT:-30}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKSPACE_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
QUERY_SCRIPT="$WORKSPACE_ROOT/query_patrol_results.py"
DB_PATH="$WORKSPACE_ROOT/data/patrol/patrol_events.db"

LIMIT=5
DECISION=""
MODE="final"

usage() {
  cat <<EOF
Usage: $(basename "$0") [OPTIONS]

Options:
  --latest N       Show N latest patrol records (default: 5)
  --occupied       Show only occupied records
  --empty          Show only empty records
  --uncertain      Show only uncertain records
  --limit N        Max records to return
  --decision TYPE  Filter by final_decision (occupied/empty/uncertain)
  --observations   Show per-angle observations instead of final results
  --help           Show this help
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --latest|--limit)
      LIMIT="$2"
      shift 2
      ;;
    --occupied)
      DECISION="occupied"
      shift
      ;;
    --empty)
      DECISION="empty"
      shift
      ;;
    --uncertain)
      DECISION="uncertain"
      shift
      ;;
    --decision)
      DECISION="$2"
      shift 2
      ;;
    --observations)
      MODE="observations"
      shift
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

if [ ! -f "$QUERY_SCRIPT" ]; then
  echo "{\"error\": \"query script not found\", \"path\": \"$QUERY_SCRIPT\"}" >&2
  exit 1
fi

CMD_ARGS=(--db "$DB_PATH" --mode "$MODE" --limit "$LIMIT")
if [ -n "$DECISION" ]; then
  CMD_ARGS+=(--decision "$DECISION")
fi

echo "generated_at: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "hostname: $(hostname)"
echo "whoami: $(whoami)"
echo "HOME: ${HOME:-<unset>}"
echo "workspace_root: $WORKSPACE_ROOT"
echo "db_path: $DB_PATH"
echo "query_script: $QUERY_SCRIPT"
echo

set +e
OUTPUT="$(timeout "$TIMEOUT" python3 "$QUERY_SCRIPT" "${CMD_ARGS[@]}" 2>&1)"
QUERY_EXIT=$?
set -e
if [ $QUERY_EXIT -ne 0 ]; then
  echo "ERROR: query failed (exit_code=$QUERY_EXIT)" >&2
  [ -n "$OUTPUT" ] && printf '%s\n' "$OUTPUT" >&2
  exit 1
fi

printf '%s\n' "$OUTPUT"
echo
echo "status: ok"
