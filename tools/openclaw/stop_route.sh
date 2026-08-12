#!/usr/bin/env bash
# ============================================================================
# stop_route.sh — Stop current route task via agent gateway
# ============================================================================
# Purpose: Send stop_route command. Always allowed, no confirmation needed.
#
# Safety:  Stop must ALWAYS be possible — no preconditions, no safety checks
#          that could block it. The gateway accepts stop_route even when
#          the robot is idle (idempotent, no harm).
#
# Usage:   ./stop_route.sh
# ============================================================================

set -euo pipefail

COMMAND_TOPIC="/agent/command"
RESULT_TOPIC="/agent/command_result"

CMD_ID="cmd_$(date -u +%Y%m%dT%H%M%S)_$(shuf -i 100000-999999 -n 1 2>/dev/null || echo "000000")"

COMMAND_JSON=$(cat <<EOF
{
  "command_id": "${CMD_ID}",
  "source": "openclaw",
  "action": "stop_route",
  "params": {},
  "require_confirmation": false,
  "timestamp": "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
}
EOF
)

echo "{\"status\": \"sending_stop_route\", \"command_id\": \"${CMD_ID}\"}"

if [ -d "/opt/ros/jazzy" ]; then
    export PATH="/opt/ros/jazzy/bin:$PATH"
elif [ -d "/opt/ros/humble" ]; then
    export PATH="/opt/ros/humble/bin:$PATH"
else
    echo "{\"error\": \"ROS2 not found\"}" >&2
    exit 1
fi

ros2 topic pub --once "${COMMAND_TOPIC}" std_msgs/msg/String "{\"data\": $(echo "${COMMAND_JSON}" | jq -c .)}" 2>&1 || {
    echo "{\"error\": \"failed to publish command\", \"command_id\": \"${CMD_ID}\"}" >&2
    exit 1
}

# Brief wait for acknowledgment
sleep 0.5

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
            sys.exit(0 if data.get('result') == 'route_stopped' else 1)
" 2>/dev/null || {
    echo "{\"warning\": \"could not confirm stop result. Check /agent/command_result for cmd_id=${CMD_ID}\"}"
    exit 1
}
