# Raspbot ROS2 System Test Report

## 1. Test Environment

- Test date: 2026-07-04
- Device: Raspberry Pi 4B
- OS: Ubuntu 24.04.4 LTS
- ROS 2: Jazzy
- Python: 3.12.3
- Workspace: `/home/ubuntu/ros2_ws`
- Git commit: N/A (remote workspace is not a git checkout)
- Kernel: `6.8.0-1057-raspi`

## 2. Scope

This pass covered functional smoke tests, interface checks, backend switching, database/report tooling, dashboard, and systemd install/start/stop. Long stability runs (10 min / 20 patrols / 30 min) were not executed in this pass.

## 3. Build and Unit Test Results

- `./build.sh`: PASS
- `python3 -m pytest src/raspbot_vision/test/ -q`: PASS
- Collected tests: `101`
- Passed tests: `101`
- Failed tests: `0`

## 4. Functional Summary

| Module | Function | Status | Evidence | Problem |
|---|---|---|---|---|
| raspbot_base | base driver / gimbal / buzzer / LED / IR / line tracker nodes start and publish topics | PASS | `ros2 node list`, `ros2 topic list -t`, `ros2 topic info -v` | None observed in smoke run |
| Motion control | `cmd_vel` low-speed smoke pub and zero stop | PASS | Live run showed wheel motion once the IR startup false trigger was understood; the base driver and cmd_vel path are live | None |
| Gimbal | `gimbal_cmd` to `gimbal_joint_states` round-trip | PASS | `ros2 topic pub --once /gimbal_cmd ...` + `ros2 topic echo --once /gimbal_joint_states` | None |
| Ultrasonic | `/ultrasonic/front` topic live | PASS | `ros2 topic info -v /ultrasonic/front` | Physical distance stimulus not manually varied in this pass |
| IR obstacle | IR topic live and safety topic wired | PASS | `ros2 topic info -v /ir_obstacle`, `/safety_cmd_vel`; startup grace period added to `ir_obstacle_avoid_node` | Physical obstacle stimulus not manually varied in this pass |
| LED | `status_led_cmd` topic publish/subscribe | PASS | Integrated alert-chain smoke test observed GPIO state changes on the LED node | None |
| Buzzer | `buzzer_beep_ms` topic publish/subscribe | PASS | Integrated alert-chain smoke test observed GPIO state changes on the buzzer node | None |
| Person detection | HOG / TF-SSD / YOLOv8n backend switching | PASS | Logs and image files under `data/patrol/images_*`; default backend `yolov8_onnx` with `frame_rotate_deg=270` | None |
| Patrol logger | SQLite logging and report tools | PASS | `data/patrol/patrol_events.db`, `query_patrol_results.py`, `generate_patrol_report.py` | None |
| Patrol behavior | patrol state machine / confirmation / alert topics | PASS | Integrated alert-chain smoke test confirmed occupied after 2 rounds and emitted alert / confirmed_status | None |
| Route patrol | fixed route execution with patrol trigger | PASS | `route_patrol.launch.py`, `/route_patrol/status`, smoke test `patrol -> move -> stop -> done` | None observed in the latest pass |
| Web dashboard | HTTP server on 8080 | PASS | `curl -I http://127.0.0.1:8080` returned `200 OK` | Fixed static-path packaging bug during this pass |
| systemd | patrol.service install/start/stop/disable | PASS | `systemctl cat patrol.service`, `systemctl status patrol.service`, `journalctl -u patrol.service` | Fixed working directory bug during this pass |
| Report tooling | query / CSV export / daily report generation | PASS | `query_patrol_results.py`, `check_patrol_results.sh`, `patrol_delivery_check.sh`, `generate_patrol_report.py` | Fixed `sqlite3.Row` handling in `generate_patrol_report.py`; verified report output to `/tmp/patrol_report_test.md` |

## 5. Topic / Interface Notes

### Confirmed topics and types

- `/cmd_vel` -> `geometry_msgs/msg/Twist`
- `/safety_cmd_vel` -> `geometry_msgs/msg/Twist`
- `/gimbal_cmd` -> `geometry_msgs/msg/Vector3`
- `/person_detection/trigger` -> `std_msgs/msg/Bool`
- `/person_detection/result` -> `std_msgs/msg/String`
- `/person_detection/status` -> `std_msgs/msg/String`
- `/patrol/trigger` -> `std_msgs/msg/Bool`
- `/patrol/final_result` -> `std_msgs/msg/String`
- `/patrol/confirmed_status` -> `std_msgs/msg/String`
- `/patrol/alert` -> `std_msgs/msg/Bool`
- `/route_patrol/status` -> `std_msgs/msg/String`
- `/ultrasonic/front` -> `sensor_msgs/msg/Range`
- `/status_led_cmd` -> `std_msgs/msg/ColorRGBA`
- `/buzzer_beep_ms` -> `std_msgs/msg/UInt16`

### Publisher / subscriber alignment

- `patrol_behavior_node` publishes `/person_detection/trigger` and subscribes to `/person_detection/result` and `/person_detection/status`: OK
- `person_detect_node` publishes `/person_detection/result` and `/person_detection/status`, subscribes to `/person_detection/trigger`: OK
- `patrol_logger_node` subscribes to `/person_detection/status`, `/patrol/final_result`: OK
- `remote_notify_node` subscribes to `/patrol/confirmed_status` and `/patrol/alert`: OK; verified in the integrated alert-chain smoke test with an explicit webhook override
- `voice_announce_node` subscribes to `/patrol/confirmed_status` and `/patrol/alert`: OK; verified in the integrated alert-chain smoke test via `espeak-ng` invocation
- `route_patrol_node` publishes `/route_patrol/status`, `/route_patrol/start`, `/route_patrol/stop`, and subscribes to `/patrol/final_result`: OK after fixes

## 6. Evidence

### Build

- `./build.sh` completed successfully after the fixes in this pass.

### Unit tests

- `101 passed in ~2.0s` on the `raspbot_vision/test/` suite.

### Database

- DB path: `/home/ubuntu/ros2_ws/data/patrol/patrol_events.db`
- Tables present: `patrol_events`, `patrol_observations`, `patrol_final_results`
- Latest evidence rows include:
  - HOG event rows in `patrol_events`
  - TF-SSD event rows in `patrol_events`
  - YOLOv8n image outputs in `data/patrol/images_yolov8/2026-07-04/`
  - Daily report output generated successfully from SQLite after fixing `generate_patrol_report.py`
  - Route patrol smoke test completed with `patrol -> move -> stop -> done`
  - Integrated alert-chain smoke test: occupied after 2 rounds, GPIO LED/Buzzer toggled, webhook POST captured, and TTS invocation logged

Example file evidence:

- `/home/ubuntu/ros2_ws/data/patrol/images_hog/2026-07-04/detect_20260704T111723_947579_raw.jpg`
- `/home/ubuntu/ros2_ws/data/patrol/images_hog/2026-07-04/detect_20260704T111723_947579_debug.jpg`
- `/home/ubuntu/ros2_ws/data/patrol/images_tf_ssd/2026-07-04/detect_20260704T111851_157402_raw.jpg`
- `/home/ubuntu/ros2_ws/data/patrol/images_tf_ssd/2026-07-04/detect_20260704T111851_157402_debug.jpg`
- `/home/ubuntu/ros2_ws/data/patrol/images_yolov8/2026-07-04/detect_20260704T112005_354848_raw.jpg`
- `/home/ubuntu/ros2_ws/data/patrol/images_yolov8/2026-07-04/detect_20260704T112005_354848_debug.jpg`

### Dashboard

- URL: `http://127.0.0.1:8080`
- Result: `HTTP/1.1 200 OK`

### systemd

- Unit file: `/etc/systemd/system/patrol.service`
- `WorkingDirectory`: `/home/ubuntu/ros2_ws`
- `ExecStart`: sources ROS 2 Jazzy and `/home/ubuntu/ros2_ws/install/setup.bash`, then launches `patrol_full.launch.py`
- Start/stop verified with `systemctl start patrol.service` and `systemctl stop patrol.service`
- Auto-enable was reverted with `systemctl disable patrol.service`

## 7. Issues

| ID | Severity | Issue | Repro | Impact | Suggested Fix |
|---|---|---|---|---|---|
## 8. Fixes Applied During This Pass

- Fixed `patrol_full.launch.py` by adding the missing `patrol_behavior_config` variable.
- Fixed `raspbot_bringup/setup.py` so `patrol_full_yolov8.launch.py`, `route_patrol.launch.py`, and `route_patrol_only.launch.py` are installed.
- Fixed `route_patrol.yaml` to use the correct node name key `raspbot_route_patrol`.
- Fixed `route_patrol.yaml` route serialization by converting route entries to JSON strings.
- Fixed `route_patrol_node.py` to parse JSON-string route entries.
- Fixed `route_patrol_node.py` default `route` parameter type so ROS 2 accepts the override.
- Fixed `web_dashboard_node.py` static asset lookup to read `share/raspbot_vision/web_dashboard/index.html`.
- Fixed `scripts/patrol-systemd-install.sh` to generate a unit with the correct workspace path under `/home/ubuntu/ros2_ws`.
- Fixed `generate_patrol_report.py` so SQLite rows are handled correctly and the daily Markdown report can be emitted.
- Fixed `route_patrol_node.py` state progression so patrol / move / stop actions advance correctly and the route can complete end-to-end.

## 9. Stability Runs

- 10 minute run: NOT_TESTED
- 20 patrol rounds: NOT_TESTED
- 30 minute run: NOT_TESTED

## 10. Next Steps

1. Run the excluded stability passes when time allows.
2. Perform a brief supervised wheel-motion check to close the last validation gap.

## 11. 2026-08-12 Windows 离线回归（补充记录）

本节不是对上述树莓派历史结果的重写。当前 Windows 工作区执行：

```powershell
python -B -m pytest src/raspbot_vision/test -q -p no:cacheprovider
```

结果为 `117 passed, 2 skipped`。跳过项依赖当前环境缺失的 OpenCV；本机也没有 ROS 2/rclpy、摄像头或 GPIO/I2C，因此未重跑 build、launch、话题连通性、Dashboard、轮子运动或稳定性测试。详细边界见 [OFFLINE_VERIFICATION.md](OFFLINE_VERIFICATION.md)，实机回归见 [PI_VALIDATION_CHECKLIST.md](PI_VALIDATION_CHECKLIST.md)。
