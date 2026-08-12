#!/usr/bin/env bash
set -euo pipefail

if [ -f /opt/ros/jazzy/setup.bash ]; then
  set +u
  # shellcheck disable=SC1091
  source /opt/ros/jazzy/setup.bash
  set -u
fi
if [ -f ~/ros2_ws/install/setup.bash ]; then
  set +u
  # shellcheck disable=SC1091
  source ~/ros2_ws/install/setup.bash
  set -u
fi

exec ros2 run raspbot_vision openclaw_agent_entry -- "$@"
