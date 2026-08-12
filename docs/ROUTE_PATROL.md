# 移动巡逻指南

## 概述

轻量级固定路线移动巡逻功能。不依赖 SLAM / Nav2 / 地图导航 / 复杂路径规划。

**核心设计**：按 YAML 配置的时间片动作控制小车低速移动，到达预设巡检点后停车并触发现有 patrol/trigger，由 patrol_behavior_node 完成云台扫描、人体检测、日志和告警。

## 架构

```
route_patrol_node (NEW)             patrol_behavior_node (EXISTING)
┌──────────────────────┐            ┌─────────────────────────┐
│ 解析 YAML 路线       │   Bool    │ 云台左/中/右扫描         │
│ 按时间片执行动作     │ ────────→ │ 触发人体检测             │
│ move/turn/wait/stop  │  patrol/  │ 多轮确认 / 超时重试      │
│ patrol → 触发巡检    │  trigger  │ 结果联动 (LED/蜂鸣器)    │
│                      │ ←───────  │                          │
│ 订阅障碍距离 / 暂停  │  patrol/  │                          │
│ 发布状态 topic       │ final_res │                          │
└──────────────────────┘            └─────────────────────────┘
```

**状态机**：

```
IDLE  →  LOAD_ROUTE  →  [EXECUTING  ↔  STOP_AND_SETTLE]  →  TRIGGER_PATROL  →  WAIT_PATROL_RESULT  →  ...  →  DONE
                              ↕
                      OBSTACLE_PAUSED
```

## 快速开始

### 安全警告

> ⚠️ **首次测试请架空轮子或抬起小车！** 确认 /cmd_vel 正常后再落地低速测试。

### 编译

```bash
cd ~/ros2_ws
./build.sh
source install/setup.bash
```

### 启动完整移动巡逻系统

```bash
ros2 launch raspbot_bringup route_patrol.launch.py
```

这会启动：底盘硬件 + 超声波 + 避障 + 人体检测 + 巡逻行为 + 语音播报 + 远程通知 + **路线巡逻**

### 在已有系统中叠加路线巡逻

如果 patrol_full.launch.py 已在运行：

```bash
ros2 launch raspbot_bringup route_patrol_only.launch.py
```

### 手动触发巡逻

```bash
# 开始移动巡逻
ros2 topic pub --once route_patrol/start std_msgs/Bool "data: True"

# 停止
ros2 topic pub --once route_patrol/stop std_msgs/Bool "data: True"
```

## 路线配置

编辑 `config/route_patrol.yaml`：

```yaml
route_patrol:
  ros__parameters:
    route:
      - name: start_scan
        action: patrol             # 当前位置触发一轮巡检扫描

      - name: move_to_point_1
        action: move               # 前进
        linear_x: 0.06             # 速度 m/s (默认 0.06)
        duration_sec: 1.5          # 持续 1.5 秒

      - name: turn_right
        action: turn               # 转向
        angular_z: -0.30           # 角速度 rad/s (默认 0.30)
        duration_sec: 0.9

      - name: wait_demo
        action: wait               # 原地等待
        duration_sec: 1.0

      - name: point_2_scan
        action: patrol

      - name: final_stop
        action: stop               # 停机（自动发布零速度）
```

### 动作类型

| action | 参数 | 说明 |
|--------|------|------|
| `move` | `linear_x`, `duration_sec` | 前进 |
| `turn` | `angular_z`, `duration_sec` | 转向（正值左转，负值右转） |
| `wait` | `duration_sec` | 原地等待 |
| `stop` | 无 | 发布零速度 |
| `patrol` | 无 | 触发一轮云台巡检 |

### 路线参数

| 参数 | 默认 | 说明 |
|------|------|------|
| `auto_start` | false | 设为 true 则节点启动后自动开始 |
| `loop_route` | false | 设为 true 则完成后循环 |
| `obstacle_check_enabled` | true | 超声波障碍检测 |
| `obstacle_stop_distance_m` | 0.25 | 低于此距离 (m) 立即停车暂停 |
| `obstacle_resume_distance_m` | 0.35 | 高于此距离 (m) 恢复移动 |
| `patrol_timeout_sec` | 15.0 | 单轮巡检最长等待时间 |
| `stop_settle_sec` | 0.8 | 停车稳停时间 |
| `stop_repeat_count` | 5 | 停车后连发多少次零速度 |

## 运行时监控

```bash
# 观察当前状态
ros2 topic echo route_patrol/status

# 观察速度指令
ros2 topic echo cmd_vel

# 观察巡检触发
ros2 topic echo patrol/trigger     # Bool, True = 触发了
ros2 topic echo patrol/final_result # JSON 巡检结果
```

## 状态消息格式

`route_patrol/status` (std_msgs/String, JSON):

```json
{
  "state": "EXECUTING",
  "action_index": 2,
  "action_name": "move_to_point_1",
  "action": "move",
  "route_done": false,
  "blocked": false,
  "last_patrol_result": {
    "final_decision": "empty",
    "detected": false,
    "max_confidence": 0.0
  },
  "last_final_decision": "empty",
  "error_msg": ""
}
```

## 障碍处理

- **正常行驶中**：超声波距离 < 0.25m → 立即停车，进入 OBSTACLE_PAUSED
- **暂停中**：持续发零速度，等待障碍清除
- **障碍清除**：距离 > 0.35m → 自动恢复移动
- **底层兜底**：obstacle_avoid_node 始终通过 safety_cmd_vel 做即时避障（后退+转向），与路线级暂停互补

## 安全停止

以下情况自动发布零速度：
- 每个移动动作完成后（STOP_AND_SETTLE）
- 障碍检测时
- 路线完成时（DONE）
- 收到 route_patrol/stop 命令
- 节点销毁 / Ctrl+C

## Agent 网关启动路线的约定

`agent_command_gateway_node` 在发布 `/route_patrol/start` 前额外检查路线白名单、人工确认、路线互斥和超声波数据。它要求 `/ultrasonic/front` 的值为正数、有限且未超过 `ultrasonic_timeout_sec`（默认 2 s）；缺失、陈旧或小于 0.30 m 都会拒绝启动。运行开始后，网关的 `max_route_duration_sec`（默认 120 s）达到时会发布 `/route_patrol/stop`。

此处的 0.30 m 是 Agent 的启动准入距离，不会替换本节点运行中原有的 0.25/0.35 m 暂停/恢复阈值。`route_name` 也只用于网关白名单：当前节点执行的是 `route_patrol.yaml` 内的固定动作序列，而非按该名称选择不同路线。见 [AGENT_COMMAND_GATEWAY.md](AGENT_COMMAND_GATEWAY.md)。
