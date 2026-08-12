# Raspbot ROS2 Final Delivery Summary

> Scope: project closeout for the current feature set on Raspberry Pi 4B / Ubuntu 24.04 / ROS 2 Jazzy.
> Stability runs were intentionally excluded from this pass.

## 1. What Is Done

- Person detection backend selection is explicit and no longer silently falls back to HOG.
- YOLOv8 ONNX is the default person detector backend.
- `frame_rotate_deg=270` is documented and used for the installed camera orientation.
- TF-SSD remains available as the comparison / fallback backend.
- HOG remains available as a fallback only, with stricter filtering and lower trust.
- Dashboard now exposes backend, fallback, and decision reason.
- SQLite logging, patrol result querying, and daily report generation are working.
- `route_patrol_node` has been fixed and smoke-tested end-to-end.
- Multi-round patrol confirmation now drives the alert chain end-to-end.
- `systemd` install/start/stop/disable flow is working with the correct workspace path.
- IR obstacle startup misfire has been mitigated with a startup grace period so it does not seize the base immediately on boot.

## 2. Verified Results

- `./build.sh`: PASS
- `python3 -m pytest src/raspbot_vision/test -q`: PASS (`101 passed`)
- `patrol_delivery_check.sh`: PASS
- `generate_patrol_report.py`: PASS after SQLite-row fix
- `route_patrol_node` smoke test: PASS (`patrol -> move -> stop -> done`)
- Integrated alert-chain smoke test: PASS (multi-round confirmation, LED/Buzzer GPIO, webhook, and TTS)
- Live motion observation: PASS (wheel movement was observed once the IR startup false trigger was understood and mitigated)

## 3. Completed Items

- YOLOv8 ONNX backend load / decode / threshold issues were debugged and fixed.
- Dashboard backend visibility was added.
- HOG fallback reliability was constrained.
- Patrol data persistence and report tooling were validated.
- Route patrol state progression bug was fixed.
- Launch / packaging issues that blocked runtime verification were fixed.
- Multi-round confirmation now publishes alert and confirmation outputs that downstream nodes consume correctly.

## 4. Partial Items

No remaining functional partial items were identified in this closeout pass.

- The only intentionally excluded work was long stability validation.
- The earlier no-motion report was traced to the IR safety node grabbing the base during startup, and this was mitigated with the startup grace period parameter.

## 5. Not Run

The following stability-oriented checks were intentionally left out:

- 10 minute continuous run
- 20 patrol rounds
- 30 minute endurance run

## 6. Final Assessment

The project is in a shippable closeout state for the currently implemented feature set.

The core patrol chain is complete and demonstrable:

- sensing
- person detection
- patrol decisioning
- logging and report output
- dashboard visibility
- route patrol motion sequence

What remains is validation depth, not core functionality: endurance testing.

## 7. 后续代码加固与验证边界（2026-08-12）

本摘要的“Verified Results”是既有树莓派交付记录。之后的代码加固包括：底盘拒绝非有限速度输入、Agent 路线的新鲜超声波/人工确认/最大时长保护、Dashboard 默认本机监听并默认关闭控制、远程通知后台发送与钉钉签名支持，以及 `RASPBOT_WS` 运行时路径支持。

当前 Windows 离线回归为 `117 passed, 2 skipped`，没有复跑 ROS 2、GPIO、相机、Dashboard 或实车运动。因此本节不能将新保护描述为已完成实机验收；验证步骤见 [PI_VALIDATION_CHECKLIST.md](PI_VALIDATION_CHECKLIST.md)。
