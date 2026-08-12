---
name: raspbot_ros2_patrol
description: Natural-language control for the Raspbot ROS2 patrol robot
version: 1.0.0
metadata:
  openclaw:
    requires:
      bins:
        - bash
        - jq
        - python3
    primaryEnv: ROS_DISTRO
---

# Raspbot ROS2 Patrol Skill

Use this skill for the Raspbot patrol robot workspace.

## What this skill does

- Queries robot status
- Queries patrol history
- Generates patrol reports
- Triggers a safe patrol scan
- Runs only whitelisted patrol routes
- Stops or pauses a route safely

## Safety rules

- Never generate or suggest direct `/cmd_vel` control
- Never bypass `agent_command_gateway_node`
- Never expose arbitrary shell execution
- Never invent route names outside the whitelist
- If the request is ambiguous, fall back to a status query

## Tool mapping

- `query_status` -> `tools/openclaw/robot_status.sh`
- `query_latest_patrol` -> `tools/openclaw/query_latest_patrol.sh`
- `generate_report` -> `tools/openclaw/generate_report.sh`
- `systemd_status` -> `tools/openclaw/systemd_status.sh`
- `trigger_patrol_once` -> `tools/openclaw/trigger_patrol_once.sh`
- `run_route` -> `tools/openclaw/run_route.sh <route_name>`
- `stop_route` -> `tools/openclaw/stop_route.sh`
- `pause_route` -> `tools/openclaw/pause_route.sh`
- `get_dashboard_url` -> `tools/openclaw/robot_status.sh`

## Supported route names

- `short_test_route`
- `door_check_route`
- `desk_check_route`
- `office_demo_route`

## Prompt guidance

When asked to act, choose the safest valid action first:

1. If the request is only about status, use a read-only tool.
2. If the request is about one patrol scan, use the trigger script.
3. If the request is about movement, only use a whitelisted route.
4. If the request asks for direct motion or safety bypass, refuse.

## Notes for OpenClaw UI import

This repository is already laid out as a workspace skill root.
The helper scripts source the ROS environment themselves.
The skill directory can be imported directly from:

`/home/ubuntu/ros2_ws/skills/raspbot_ros2_patrol`

