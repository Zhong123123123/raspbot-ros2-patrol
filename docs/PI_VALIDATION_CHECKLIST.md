# 树莓派回板验证清单

本清单覆盖 2026-08-12 代码加固后仍需在真实 Raspberry Pi / ROS 2 Jazzy 环境完成的验证。所有运动测试须抬空轮子或由人员在旁监护，并保留终端输出与日志。

## 1. 环境与构建

```bash
export RASPBOT_WS="$HOME/ros2_ws"
source /opt/ros/jazzy/setup.bash
cd "$RASPBOT_WS"
./build.sh
source install/setup.bash
python3 -m pytest src/raspbot_vision/test -q
```

确认 `requirements-runtime.txt` 的 Python 依赖和 `apt-deps.txt` 的系统依赖已按实际镜像安装；`rcl_interfaces` 为两个 ROS 包的运行依赖。

## 2. 基础硬件与底盘安全

- 确认 `/dev/i2c-1`、底盘地址 `0x16`、摄像头和 GPIO 权限可用。
- 分别发布有限数值的 `/cmd_vel` 与 `/safety_cmd_vel`，确认安全指令优先、普通指令超时后停车。
- 对 `/cmd_vel` 发布 `NaN`/`Inf`（仅抬空轮子环境），确认底盘节点拒绝命令并调用停车；该行为是本轮新增的输入兜底。
- 在受控距离下验证超声波、红外避障和人工停止不会被 Agent 或 Dashboard 绕过。

## 3. 路线巡逻与 Agent 网关

启动 `patrol_full.launch.py` 后检查：

```bash
ros2 topic info /patrol/active -v
ros2 topic info /patrol/alert -v
ros2 topic echo /agent/command_result
```

前两项必须是 `std_msgs/msg/Bool`。对 `run_route` 依次验证：

1. 没有有效 `/ultrasonic/front` 数据时被拒绝，原因应为 `ultrasonic_unavailable`。
2. 数据超过 `ultrasonic_timeout_sec`（默认 2 s）后被拒绝，原因应为 `ultrasonic_stale`。
3. 距离小于 `min_obstacle_distance_m`（默认 0.30 m）时被拒绝，原因应为 `obstacle_too_close`。
4. 发送新鲜、安全距离和 `require_confirmation: true` 后才可以启动。
5. 把 `max_route_duration_sec` 临时设短，确认超时后发布 `/route_patrol/stop` 并返回 `route_timeout`。

`route_name` 目前是网关准入白名单，不是动态路线选择器：`route_patrol_node` 执行的是其 YAML 中配置的固定路线。结果中的 `requested_route_name` 与 `executed_route_name` 应被记录和核对。

## 4. Dashboard 与通知

- 默认启动后仅访问 `http://127.0.0.1:8080`，确认遥测/相机可用且浏览器控制被禁用。
- 如确有受信任局域网遥控需求，设置 `DASHBOARD_HOST=0.0.0.0`、`DASHBOARD_ENABLE_CONTROL=1` 和随机强 `DASHBOARD_TOKEN`；分别验证无 token、错误 token 和正确 token 的控制行为。
- Dashboard token 只保护控制 WebSocket，不是把监控页面变为认证页面；远程监听时仍应使用防火墙或可信网络隔离。
- 远程通知保持默认关闭。配置 webhook 后，用测试告警验证异步发送、重试、冷却时间；如使用钉钉 secret，再验证签名请求。

## 5. 回归与留证

- 执行至少一轮低速默认路线和一次三角度巡检，保存 `/route_patrol/status`、`/patrol/final_result`、`/agent/command_result` 与 JSONL 审计日志。
- 再执行连续巡逻、障碍物矩阵和受控急停测试。不要把单次成功替代长期稳定性结论。
- 将日期、软件版本、配置副本、终端输出和异常现象写入新的实机报告；不要覆盖 `SYSTEM_TEST_REPORT.md` 中的历史记录。
