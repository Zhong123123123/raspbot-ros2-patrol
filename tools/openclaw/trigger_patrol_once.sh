#!/usr/bin/env bash
# ============================================================================
# trigger_patrol_once.sh — Trigger a single patrol scan via agent gateway
# ============================================================================
# Purpose: Send a trigger_patrol_once command through the agent command gateway.
#
# Safety:  Does NOT directly control chassis or camera.
#          Goes through agent_command_gateway_node which validates:
#            - action in allowed_actions
#            - patrol not already active
#            - source is trusted
#          All commands are JSONL-logged.
#
# Usage:   ./trigger_patrol_once.sh
# ============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMMAND_TOPIC="/agent/command"
RESULT_TOPIC="/agent/command_result"
TIMEOUT_SEC=45

CMD_ID="cmd_$(date -u +%Y%m%dT%H%M%S)_$(shuf -i 100000-999999 -n 1 2>/dev/null || echo "000000")"

COMMAND_JSON=$(cat <<EOF
{
  "command_id": "${CMD_ID}",
  "source": "openclaw",
  "action": "trigger_patrol_once",
  "params": {},
  "require_confirmation": false,
  "timestamp": "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
}
EOF
)

echo "{\"status\": \"sending_trigger_patrol_once\", \"command_id\": \"${CMD_ID}\"}"

# Check if ROS2 is available
if [ -d "/opt/ros/jazzy" ]; then
    export PATH="/opt/ros/jazzy/bin:$PATH"
elif [ -d "/opt/ros/humble" ]; then
    export PATH="/opt/ros/humble/bin:$PATH"
else
    echo "{\"error\": \"ROS2 not found\"}" >&2
    exit 1
fi

# Check if the command topic exists
if ! timeout 5 ros2 topic list 2>/dev/null | grep -q "${COMMAND_TOPIC}"; then
    echo "{\"warning\": \"topic ${COMMAND_TOPIC} not found. Is agent_command_gateway_node running?\"}"
fi

# Publish the command
ros2 topic pub --once "${COMMAND_TOPIC}" std_msgs/msg/String "{\"data\": $(echo "${COMMAND_JSON}" | jq -c .)}" 2>&1 || {
    echo "{\"error\": \"failed to publish command\", \"command_id\": \"${CMD_ID}\"}" >&2
    exit 1
}

# Wait for result
echo "{\"status\": \"waiting_for_result\", \"command_id\": \"${CMD_ID}\", \"timeout_sec\": ${TIMEOUT_SEC}}"

START_TIME=$(date +%s)
while true; do
    # Try to get the latest result for our command
    RESULT=$(timeout 5 ros2 topic echo --once "${RESULT_TOPIC}" std_msgs/msg/String 2>/dev/null | python3 -c "
import sys, json
try:
    for line in sys.stdin:
        line = line.strip()
        if line.startswith('data: '):
            data = json.loads(line[6:])
            if data.get('command_id') == '${CMD_ID}':
                print(json.dumps(data))
                sys.exit(0)
except:
    pass
sys.exit(1)
" 2>/dev/null || true)

    if [ -n "$RESULT" ]; then
        echo "$RESULT"
        # Check if the result indicates patrol completed
        RESULT_TYPE=$(echo "$RESULT" | python3 -c "import sys,json; print(json.loads(sys.stdin.read()).get('result',''))" 2>/dev/null || echo "")
        if [ "$RESULT_TYPE" = "patrol_completed" ]; then
            exit 0
        elif [ "$RESULT_TYPE" = "rejected" ]; then
            exit 1
        fi
    fi

    ELAPSED=$(( $(date +%s) - START_TIME ))
    if [ "$ELAPSED" -ge "$TIMEOUT_SEC" ]; then
        echo "{\"error\": \"timeout waiting for patrol result\", \"command_id\": \"${CMD_ID}\"}" >&2
        exit 1
    fi

    sleep 1
done
