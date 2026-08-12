#!/usr/bin/env bash
set -euo pipefail

echo "[cleanup_gpio] stopping ROS launch and GPIO-related nodes..."

patterns=(
  "/opt/ros/jazzy/bin/ros2 launch raspbot_bringup"
  "/home/ubuntu/ros2_ws/install/raspbot_base/lib/raspbot_base/base_driver_node"
  "/home/ubuntu/ros2_ws/install/raspbot_base/lib/raspbot_base/gimbal_servo_node"
  "/home/ubuntu/ros2_ws/install/raspbot_base/lib/raspbot_base/buzzer_node"
  "/home/ubuntu/ros2_ws/install/raspbot_base/lib/raspbot_base/status_led_node"
  "/home/ubuntu/ros2_ws/install/raspbot_base/lib/raspbot_base/hardware_alert_node"
  "/home/ubuntu/ros2_ws/install/raspbot_base/lib/raspbot_base/line_tracker_node"
  "/home/ubuntu/ros2_ws/install/raspbot_base/lib/raspbot_base/ir_obstacle_node"
  "/home/ubuntu/ros2_ws/install/raspbot_vision/lib/raspbot_vision/ultrasonic_range_node"
  "/home/ubuntu/ros2_ws/install/raspbot_vision/lib/raspbot_vision/obstacle_avoid_node"
  "/home/ubuntu/ros2_ws/install/raspbot_vision/lib/raspbot_vision/ir_obstacle_avoid_node"
  "/home/ubuntu/ros2_ws/install/raspbot_vision/lib/raspbot_vision/patrol_behavior_node"
  "/home/ubuntu/ros2_ws/install/raspbot_vision/lib/raspbot_vision/patrol_scheduler_node"
  "/home/ubuntu/ros2_ws/install/raspbot_vision/lib/raspbot_vision/patrol_logger_node"
  "/home/ubuntu/ros2_ws/install/raspbot_vision/lib/raspbot_vision/person_detect_node"
)

for pattern in "${patterns[@]}"; do
  pkill -f "$pattern" 2>/dev/null || true
done

sleep 2

holder_pids="$(lsof -t /dev/gpiochip0 2>/dev/null | sort -u || true)"
if [[ -n "$holder_pids" ]]; then
  echo "[cleanup_gpio] forcing remaining /dev/gpiochip0 holders to exit: $holder_pids"
  kill $holder_pids 2>/dev/null || true
  sleep 1
fi

holder_pids="$(lsof -t /dev/gpiochip0 2>/dev/null | sort -u || true)"
if [[ -n "$holder_pids" ]]; then
  echo "[cleanup_gpio] killing stubborn /dev/gpiochip0 holders: $holder_pids"
  kill -9 $holder_pids 2>/dev/null || true
  sleep 1
fi

echo "[cleanup_gpio] current /dev/gpiochip0 holders:"
lsof /dev/gpiochip0 2>/dev/null || true

echo "[cleanup_gpio] done"
