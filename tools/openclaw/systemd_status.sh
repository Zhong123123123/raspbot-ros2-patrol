#!/usr/bin/env bash
# ============================================================================
# systemd_status.sh — Query systemd service status for patrol robot
# ============================================================================

set -euo pipefail

TIMEOUT="${TIMEOUT:-5}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKSPACE_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

usage() {
  cat <<EOF
Usage: $(basename "$0") [OPTIONS]

Options:
  --service NAME   Check specific service only
  --all            Show all robot-related services (default)
  --json           Output as JSON
  --help           Show this help
EOF
}

SERVICES=(
  "patrol.service"
  "openclaw-gateway.service"
)

OUTPUT_JSON=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --service)
      SERVICES=("$2")
      shift 2
      ;;
    --json)
      OUTPUT_JSON=true
      shift
      ;;
    --all)
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

timestamp() { date -u +%Y-%m-%dT%H:%M:%SZ; }

run_capture() {
  local __outvar="$1"
  shift
  local out rc
  set +e
  out="$(timeout "$TIMEOUT" "$@" 2>&1)"
  rc=$?
  set -e
  printf -v "$__outvar" '%s' "$out"
  return "$rc"
}

inspect_service() {
  local service="$1"
  local scope cmd output rc load_state active_state unit_file_state sub_state status
  scope="system"
  [ "$service" = "openclaw-gateway.service" ] && scope="user"
  cmd=(systemctl)
  [ "$scope" = "user" ] && cmd+=(--user)

  if run_capture output "${cmd[@]}" show "$service" -p LoadState -p ActiveState -p UnitFileState -p SubState; then
    while IFS='=' read -r key value; do
      case "$key" in
        LoadState) load_state="$value" ;;
        ActiveState) active_state="$value" ;;
        UnitFileState) unit_file_state="$value" ;;
        SubState) sub_state="$value" ;;
      esac
    done <<EOF
$output
EOF
    case "${load_state:-}" in
      not-found|masked) status="service_not_found" ;;
      *)
        case "${active_state:-}" in
          active) status="active" ;;
          *) status="inactive" ;;
        esac
        ;;
    esac
  else
    rc=$?
    if printf '%s' "$output" | grep -qiE 'Access denied|Permission denied'; then
      status="permission_error"
    elif printf '%s' "$output" | grep -qiE 'could not be found|not found|LoadState=not-found'; then
      status="service_not_found"
    else
      status="error"
    fi
    load_state="unknown"
    active_state="unknown"
    unit_file_state="unknown"
    sub_state="unknown"
  fi

  cat <<EOF
service: $service
scope: $scope
status: $status
load_state: ${load_state:-unknown}
active_state: ${active_state:-unknown}
unit_file_state: ${unit_file_state:-unknown}
sub_state: ${sub_state:-unknown}
EOF
  if [ "${status}" = "permission_error" ] || [ "${status}" = "error" ]; then
    echo "error_exit_code: ${rc:-0}"
    [ -n "${output:-}" ] && printf 'error_output:\n%s\n' "$output" | sed 's/^/  /'
  fi
}

if $OUTPUT_JSON; then
  echo "{"
  echo "  \"generated_at\": \"$(timestamp)\","
  echo "  \"hostname\": \"$(hostname)\","
  echo "  \"whoami\": \"$(whoami)\","
  echo "  \"home\": \"${HOME:-}\","
  echo "  \"workspace_root\": \"${WORKSPACE_ROOT}\","
  echo "  \"services\": {"
  first=true
  for svc in "${SERVICES[@]}"; do
    if [ "$first" = true ]; then
      first=false
    else
      echo ","
    fi
    blob="$(inspect_service "$svc")"
    json_blob="$(printf '%s' "$blob" | python3 -c 'import json,sys; print(json.dumps(sys.stdin.read()))')"
    printf '    "%s": {"details": %s}' "$svc" "$json_blob"
  done
  echo
  echo "  }"
  echo "}"
else
  echo "=== SYSTEMD SERVICE STATUS ==="
  echo "generated_at: $(timestamp)"
  echo "hostname: $(hostname)"
  echo "whoami: $(whoami)"
  echo "HOME: ${HOME:-<unset>}"
  echo "workspace_root: $WORKSPACE_ROOT"
  echo
  for svc in "${SERVICES[@]}"; do
    inspect_service "$svc"
    echo
  done
fi
