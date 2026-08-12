# OpenClaw Agent Test Report

Date: 2026-07-05

## Summary

This round focused on closing the OpenClaw read-only operations loop:

- `tools/openclaw/generate_report.sh` was failing because it invoked `python3 -m raspbot_vision.generate_patrol_report` without sourcing the workspace, so `raspbot_vision` was not importable.
- `tools/openclaw/robot_status.sh` and `tools/openclaw/systemd_status.sh` previously hid failures and could mislead the agent with empty-list or `not_configured` output.
- Both issues were fixed and re-tested on the Raspberry Pi.

## Agent Command

```bash
openclaw agent --agent main --message "请只使用只读工具完成以下任务：1) 查询机器人实时状态；2) 查询最近巡检记录；3) 查询 systemd 服务状态；4) 生成巡检日报；5) 明确区分哪些信息是实时读取，哪些信息来自历史日志。不要执行任何移动或写入操作。" --verbose on --json
```

## Model

- Provider: `deepseek`
- Model: `deepseek-v4-pro`

## Tool Calls

The agent executed these read-only tools:

1. `robot_status.sh`
2. `query_latest_patrol.sh`
3. `systemd_status.sh`
4. `generate_report.sh`

It then read the generated Markdown report.

## Root Cause: `generate_report.sh`

Original failure:

- `python3 -m raspbot_vision.generate_patrol_report`
- `ModuleNotFoundError: No module named 'raspbot_vision'`

Root cause:

- The wrapper did not source `/opt/ros/jazzy/setup.bash`
- The wrapper did not source `~/ros2_ws/install/setup.bash`
- The wrapper relied on module import resolution instead of invoking the script file directly

Fix:

- Source ROS setup scripts when present
- Resolve paths relative to the script location so the wrapper works from any cwd
- Run `python3 /home/ubuntu/ros2_ws/src/raspbot_vision/raspbot_vision/generate_patrol_report.py`
- Add timeout and explicit error handling
- Keep report generation as a readable Markdown file under `data/patrol/exports/`

Current verified result:

- Exit code: `0`
- Report path: `/home/ubuntu/ros2_ws/data/patrol/exports/report_20260705_074011.md`
- Report file exists and is non-empty

## Root Cause: Read-only Status Inconsistency

The older tool output was misleading for two reasons:

- `robot_status.sh` did not source the ROS workspace and therefore could treat CLI issues as empty status.
- `systemd_status.sh` used `not_configured` for missing units, which blurred the distinction between:
  - unit not installed
  - unit installed but inactive
  - permission issue
- The repo uses `ros2 launch` as the primary node orchestration path, while `patrol.service` is only an optional systemd wrapper around `ros2 launch raspbot_bringup patrol_full.launch.py`.

Current behavior:

- `ros2 node list` is reported as `none` only when the command succeeds and returns no nodes
- command failures are reported as `ERROR`
- systemd services now return:
  - `active`
  - `inactive`
  - `service_not_found`
  - `permission_error`

## Direct vs Tool vs Agent

| Item | Direct command | OpenClaw tool result | Agent summary | Consistent |
|---|---|---|---|---|
| `ros2 node list` | empty | `none` | empty | yes |
| `ros2 topic list -t` | `/parameter_events`, `/rosout` | same | same | yes |
| `patrol.service` | inactive | `inactive` | inactive/dead | yes |
| `openclaw-gateway.service` | active | `active` | active/running | yes |
| Latest patrol count | 5 | 5 | 5 | yes |
| Latest `patrol_id` | `patrol_20260704T113632_380870` | same | same | yes |
| Report path | `report_20260705_073925.md` | `report_20260705_073925.md` | `report_20260705_074011.md` | yes, timestamped per run |

## Verified Tool Results

- `robot_status.sh`
  - reports `generated_at`, `hostname`, `whoami`, `HOME`, `ROS_DOMAIN_ID`, `RMW_IMPLEMENTATION`
  - sources ROS setup scripts
  - reports `ros2 node list: none`
  - reports only the default ROS topics
  - reports missing patrol systemd units as `service_not_found`
- `query_latest_patrol.sh`
  - returns the latest 5 patrol records from SQLite
  - latest record is `patrol_20260704T113632_380870`
- `systemd_status.sh`
  - reports `patrol.service` as `inactive`
  - reports `openclaw-gateway.service` as `active`
- `generate_report.sh`
  - runs successfully from any directory
  - exits `0`
  - writes a non-empty Markdown report

## Remaining Issues

- ROS2 application nodes are not currently running, so `ros2 node list` is empty.
- `patrol.service` exists as a wrapper but is currently inactive, so the launch stack is not running at the moment.
- `generate_patrol_report.py` still uses `jinja2`, which is installed on this machine; if this workspace is moved to a fresh host, the dependency should be recorded explicitly.

## Current Trusted Conclusion

The OpenClaw read-only operational chain is now trustworthy:

- direct command output matches tool output
- tool output matches the agent summary
- report generation is successful
- empty ROS2 node lists are no longer being misreported as failures
- missing systemd units are no longer disguised as generic `not_configured`

## Minimal Post-Start Acceptance

After starting `patrol.service`, the following was verified on the Raspberry Pi:

- `patrol.service` entered `active (running)`
- `ros2 launch raspbot_bringup patrol_full.launch.py` was the live process tree
- ROS2 nodes appeared, including:
  - `raspbot_base_driver`
  - `raspbot_person_detect`
  - `raspbot_patrol_scheduler`
  - `raspbot_patrol_behavior`
  - `raspbot_agent_command_gateway`
  - `raspbot_remote_notify`
- ROS2 topics appeared, including:
  - `/cmd_vel`
  - `/safety_cmd_vel`
  - `/person_detection/result`
  - `/patrol/final_result`
  - `/route_patrol/status`
- `person_detect_node` reported:
  - `detector_backend=yolov8_onnx`
  - `frame_rotate_deg=270`
- The launch stack produced live safety/obstacle logs, showing the control pipeline was active rather than idle

Per user request, `patrol.service` was then stopped to avoid leaving the robot in a running state.

## 2026-08-12 Windows 离线补充

本次未复跑上述 Raspberry Pi / OpenClaw 联调记录。Windows 上仅执行了不需要 ROS 的测试：`117 passed, 2 skipped`；跳过项缺少 OpenCV。代码层新增的路线准入逻辑要求人工确认和新鲜超声波值，并明确区分请求的路线名与固定 YAML 实际路线。实际 OpenClaw 调用和 ROS topic 行为仍需按 [PI_VALIDATION_CHECKLIST.md](PI_VALIDATION_CHECKLIST.md) 回板确认。
