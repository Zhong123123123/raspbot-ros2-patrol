#!/usr/bin/env bash
# ============================================================================
# run_route.sh — Execute a whitelisted patrol route via agent gateway
# ============================================================================
# Purpose: Send a run_route command through the agent command gateway.
#
# Safety:  route_name is validated at 2 levels:
#            1. Script checks for shell metacharacters
#            2. agent_command_gateway_node checks whitelist_routes
#          Direct chassis control is NOT exposed.
#          All commands are JSONL-logged.
#
# Usage:   ./run_route.sh door_check_route
#          ./run_route.sh desk_check_route
# ============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMMAND_TOPIC="/agent/command"
RESULT_TOPIC="/agent/command_result"

usage() {
    cat <<EOF
Usage: $(basename "$0") ROUTE_NAME

Available whitelist routes:
  short_test_route
  door_check_route
  desk_check_route
  office_demo_route

Example:
  $(basename "$0") door_check_route
EOF
}

if [ $# -eq 0 ]; then
    echo "{\"error\": \"missing route_name argument\"}" >&2
    usage
    exit 2
fi

ROUTE_NAME="$1"

# --- Script-level validation ---
# Reject shell metacharacters
if echo "$ROUTE_NAME" | grep -qE '[;&|$`(){}!<>]'; then
    echo "{\"error\": \"route_name contains invalid characters\", \"route_name\": \"${ROUTE_NAME}\"}" >&2
    exit 2
fi

# Only allow alphanumeric, underscore, hyphen
if ! echo "$ROUTE_NAME" | grep -qE '^[a-zA-Z0-9_-]+$'; then
    echo "{\"error\": \"route_name must be alphanumeric with underscores/hyphens only\", \"route_name\": \"${ROUTE_NAME}\"}" >&2
    exit 2
fi

CMD_ID="cmd_$(date -u +%Y%m%dT%H%M%S)_$(shuf -i 100000-999999 -n 1 2>/dev/null || echo "000000")"

COMMAND_JSON=$(cat <<EOF
{
  "command_id": "${CMD_ID}",
  "source": "openclaw",
  "action": "run_route",
  "params": {
    "route_name": "${ROUTE_NAME}"
  },
  "require_confirmation": true,
  "timestamp": "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
}
EOF
)

echo "{\"status\": \"sending_run_route\", \"command_id\": \"${CMD_ID}\", \"route_name\": \"${ROUTE_NAME}\"}"

# Check ROS2
if [ -d "/opt/ros/jazzy" ]; then
    export PATH="/opt/ros/jazzy/bin:$PATH"
elif [ -d "/opt/ros/humble" ]; then
    export PATH="/opt/ros/humble/bin:$PATH"
else
    echo "{\"error\": \"ROS2 not found\"}" >&2
    exit 1
fi

# Publish command
ros2 topic pub --once "${COMMAND_TOPIC}" std_msgs/msg/String "{\"data\": $(echo "${COMMAND_JSON}" | jq -c .)}" 2>&1 || {
    echo "{\"error\": \"failed to publish command\", \"command_id\": \"${CMD_ID}\"}" >&2
    exit 1
}

# Wait briefly for acknowledgment
sleep 1

# Try to get result
timeout 5 ros2 topic echo --once "${RESULT_TOPIC}" std_msgs/msg/String 2>/dev/null | \
    python3 -c "
import sys, json
for line in sys.stdin:
    line = line.strip()
    if line.startswith('data: '):
        data = json.loads(line[6:])
        if data.get('command_id') == '${CMD_ID}':
            print(json.dumps(data))
            if data.get('result') == 'route_started':
                sys.exit(0)
            elif data.get('accepted') == False:
                sys.exit(1)
" 2>/dev/null || {
    echo "{\"warning\": \"could not confirm route result. Check /agent/command_result for cmd_id=${CMD_ID}\"}"
}
