#!/usr/bin/env bash
# ============================================================================
# robot_status.sh — Read-only robot system status query
# ============================================================================

set -euo pipefail

TIMEOUT="${TIMEOUT:-5}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKSPACE_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
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

timestamp() { date -u +%Y-%m-%dT%H:%M:%SZ; }

value_or_unset() {
  local value="${1:-}"
  if [ -n "$value" ]; then
    printf '%s' "$value"
  else
    printf '<unset>'
  fi
}

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

render_cmd() {
  local label="$1"
  shift
  local output rc
  if run_capture output "$@"; then
    printf '%s\n' "$label"
    if [ -n "$output" ]; then
      printf '%s\n' "$output"
    else
      printf 'none\n'
    fi
  else
    rc=$?
    printf '%s\n' "$label"
    printf 'ERROR: failed (exit_code=%s)\n' "$rc"
    [ -n "$output" ] && printf '%s\n' "$output" | sed 's/^/  /'
  fi
}

service_scope() {
  case "$1" in
    openclaw-gateway.service) printf 'user' ;;
    *) printf 'system' ;;
  esac
}

inspect_service() {
  local service="$1"
  local scope cmd output rc load_state active_state unit_file_state sub_state fragment_path status
  scope="$(service_scope "$service")"
  cmd=(systemctl)
  [ "$scope" = "user" ] && cmd+=(--user)

  if run_capture output "${cmd[@]}" show "$service" -p LoadState -p ActiveState -p UnitFileState -p SubState -p FragmentPath; then
    while IFS='=' read -r key value; do
      case "$key" in
        LoadState) load_state="$value" ;;
        ActiveState) active_state="$value" ;;
        UnitFileState) unit_file_state="$value" ;;
        SubState) sub_state="$value" ;;
        FragmentPath) fragment_path="$value" ;;
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
    fragment_path="unknown"
  fi

  printf 'service: %s\n' "$service"
  printf 'scope: %s\n' "$scope"
  printf 'status: %s\n' "$status"
  printf 'load_state: %s\n' "${load_state:-unknown}"
  printf 'active_state: %s\n' "${active_state:-unknown}"
  printf 'unit_file_state: %s\n' "${unit_file_state:-unknown}"
  printf 'sub_state: %s\n' "${sub_state:-unknown}"
  printf 'fragment_path: %s\n' "${fragment_path:-unknown}"
  if [ "${status}" = "permission_error" ] || [ "${status}" = "error" ]; then
    printf 'error_exit_code: %s\n' "${rc:-0}"
    [ -n "${output:-}" ] && printf 'error_output:\n%s\n' "$output" | sed 's/^/  /'
  fi
}

echo "=== ROBOT STATUS ==="
echo "generated_at: $(timestamp)"
echo "hostname: $(hostname)"
echo "whoami: $(whoami)"
echo "HOME: ${HOME:-<unset>}"
echo "workspace_root: $WORKSPACE_ROOT"
echo "ROS_DOMAIN_ID: $(value_or_unset "${ROS_DOMAIN_ID:-}")"
echo "RMW_IMPLEMENTATION: $(value_or_unset "${RMW_IMPLEMENTATION:-}")"
echo "ROS_SETUP: $([ -f "$ROS_SETUP" ] && printf 'sourced' || printf 'missing')"
echo "INSTALL_SETUP: $([ -f "$INSTALL_SETUP" ] && printf 'sourced' || printf 'missing')"
echo "ROS_DISTRO: $(value_or_unset "${ROS_DISTRO:-}")"

echo
echo "--- Memory ---"
free -h 2>/dev/null || echo "ERROR: free not available"

echo
echo "--- Disk ---"
df -h / 2>/dev/null | tail -1 || echo "ERROR: df not available"

echo
echo "--- ROS2 Nodes ---"
render_cmd "ros2 node list:" ros2 node list

echo
echo "--- ROS2 Topics ---"
render_cmd "ros2 topic list -t:" ros2 topic list -t

echo
echo "--- Systemd Patrol Services ---"
for svc in \
  raspbot-patrol.service \
  patrol-full.service \
  patrol-detection.service \
  raspbot-base.service \
  web-dashboard.service \
  openclaw-gateway.service; do
  inspect_service "$svc"
  echo
done

echo "--- Dashboard ---"
echo "dashboard_url: http://raspberrypi.local:8080"

echo
echo "--- SQLite Database ---"
DB_PATH="$WORKSPACE_ROOT/data/patrol/patrol_events.db"
if [ -f "$DB_PATH" ]; then
  size=$(stat --format=%s "$DB_PATH" 2>/dev/null || echo unknown)
  echo "db_path: $DB_PATH"
  echo "db_size_bytes: $size"
else
  echo "db_path: $DB_PATH (not found)"
fi

echo
echo "status: ok"
