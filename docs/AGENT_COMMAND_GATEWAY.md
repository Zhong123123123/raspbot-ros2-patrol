# Agent Command Gateway — 安全命令网关文档

## 概述

`agent_command_gateway_node` 是 AI Agent 与 ROS2 执行层之间的安全网关。
所有来自 Agent 的命令必须经过它的校验才能到达机器人执行层。

## Topic 定义

### 输入：/agent/command

类型：`std_msgs/msg/String`，内容是 JSON。

```json
{
  "command_id": "cmd_20260705_001",
  "source": "openclaw",
  "action": "trigger_patrol_once",
  "params": {},
  "require_confirmation": false,
  "timestamp": "2026-07-05T12:00:00Z"
}
```

### 输出：/agent/command_result

类型：`std_msgs/msg/String`，内容是 JSON。

成功：
```json
{
  "command_id": "cmd_20260705_001",
  "accepted": true,
  "executed": true,
  "result": "patrol_completed",
  "data": {"final_decision": "empty", "max_confidence": 0.0},
  "reason": "",
  "timestamp": "2026-07-05T12:00:20Z"
}
```

拒绝：
```json
{
  "command_id": "cmd_20260705_002",
  "accepted": false,
  "executed": false,
  "result": "rejected",
  "data": {},
  "reason": "action_not_allowed",
  "timestamp": "2026-07-05T12:03:00Z"
}
```

## 支持的动作

### 只读动作（永久允许）

| 动作 | 说明 |
|------|------|
| `query_status` | 查询机器人状态 |
| `query_latest_patrol` | 查询最近巡检记录 |
| `generate_report` | 生成 Markdown 日报 |
| `get_dashboard_url` | 返回 Dashboard 地址 |
| `systemd_status` | 查询 systemd 服务状态 |

### 受控动作（有安全前置检查）

| 动作 | 说明 | 前置条件 |
|------|------|----------|
| `trigger_patrol_once` | 触发一次巡检 | patrol 未在运行 |
| `run_route` | 执行白名单路线 | route_name 在白名单; 无活动路线; 无障碍物 |
| `stop_route` | 停止当前路线 | 无（随时允许） |
| `pause_route` | 暂停当前路线 | 无（随时允许） |

### 永久拒绝的动作

- `direct_cmd_vel` — 直接速度控制
- `shell` — 任意 shell
- `disable_safety` — 关闭安全机制
- `modify_database` — 修改原始数据
- `stop_obstacle_avoid` — 关闭避障
- `delete_logs` — 删除日志

## 拒绝规则

1. JSON 不合法 → `invalid_json`
2. action 不在 allowed_actions 中 → `action_not_allowed`
3. source 不是 openclaw/trusted_tool/test → `untrusted_source`
4. forbidden_actions 中的动作 → `{action}_not_allowed`
5. 路线名不在 whitelist_routes → `route_not_whitelisted`
6. patrol 已激活时重复触发 → `patrol_already_active`
7. route 已激活时重复启动 → `route_already_active`
8. 障碍物距离 < min_obstacle_distance_m → `obstacle_too_close`

## 配置

参见 `config/agent_command_gateway.yaml`。

关键参数：
- `allowed_actions`: 允许的动作列表
- `whitelist_routes`: 白名单路线列表
- `min_obstacle_distance_m`: 最小障碍距离 (0.30m)
- `patrol_timeout_sec`: 巡检超时 (30s)
- `reject_if_obstacle_too_close`: true
- `reject_if_patrol_active`: true
- `reject_if_route_active`: true

## 日志审计

所有命令记录到 `$RASPBOT_WS/data/agent/agent_commands.jsonl`（未设置时回退到 `~/ros2_ws`）：

```json
{
  "timestamp": "2026-07-05T12:00:00Z",
  "command_id": "cmd_001",
  "source": "openclaw",
  "action": "run_route",
  "params": {"route_name": "door_check_route"},
  "accepted": true,
  "executed": true,
  "result": "route_started",
  "reason": ""
}
```

## 启动方式

主启动方式：

```bash
source /opt/ros/jazzy/setup.bash
source ~/ros2_ws/install/setup.bash
ros2 launch raspbot_bringup patrol_full.launch.py
```

单独调试方式：

```bash
ros2 run raspbot_vision agent_command_gateway_node --ros-args \
  --params-file ~/ros2_ws/config/agent_command_gateway.yaml
```

## 测试命令

```bash
# 合法查询
ros2 topic pub --once /agent/command std_msgs/msg/String \
  "data: '{\"command_id\":\"test_001\",\"source\":\"openclaw\",\"action\":\"query_status\",\"params\":{}}'"

# 非法命令（应被拒绝）
ros2 topic pub --once /agent/command std_msgs/msg/String \
  "data: '{\"command_id\":\"test_002\",\"source\":\"openclaw\",\"action\":\"direct_cmd_vel\",\"params\":{\"linear_x\":1.0}}'"

# 观察结果
ros2 topic echo /agent/command_result
```

## 当前实现补充（2026-08-12）

`/patrol/active` 和 `/patrol/alert` 均按 `std_msgs/msg/Bool` 订阅。网关的路线启动现在采用失效即拒绝策略：`/ultrasonic/front` 必须为正且有限的新鲜数据；缺失、非有限/非正值、超过 `ultrasonic_timeout_sec`（默认 2 s）或小于 `min_obstacle_distance_m`（默认 0.30 m）都会拒绝 `run_route`，相应原因为 `ultrasonic_unavailable`、`ultrasonic_stale` 或 `obstacle_too_close`。

当配置 `require_confirmation_for_routes: true`（默认）时，`run_route` 命令还必须带 `require_confirmation: true`。运行期间由 `max_route_duration_sec`（默认 120 s）监督；超时会发布 `/route_patrol/stop`、写入 JSONL 审计并返回 `route_timeout`。

`whitelist_routes` 目前只表达 Agent 的准入范围。底层 `route_patrol_node` 仍执行 YAML 中的固定路线，不能根据 `route_name` 动态切换文件。结果会同时给出 `requested_route_name` 和 `executed_route_name`，调用方不得把前者误读为已经选择了不同物理路线。

审计日志的默认路径为 `$RASPBOT_WS/data/agent/agent_commands.jsonl`；未设置 `RASPBOT_WS` 时才回退到 `~/ros2_ws`。树莓派验证步骤见 [PI_VALIDATION_CHECKLIST.md](PI_VALIDATION_CHECKLIST.md)。
