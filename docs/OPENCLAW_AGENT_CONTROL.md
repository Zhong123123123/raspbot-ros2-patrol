# OpenClaw Agent + ROS2 巡检机器人自然语言控制

## 项目定位

在现有 Raspberry Pi 4B + ROS2 Jazzy 巡检机器人基础上接入 OpenClaw Agent，
使用户可以通过自然语言查询巡检状态、生成日报、触发定点巡检、执行白名单巡逻路线。

Agent 负责理解和规划，ROS2 负责执行和安全。

## 状态总览

| 已实现 | 已集成 | 待接入 |
|------|------|------|
| `agent_command_gateway_node` 节点、`tools/openclaw/` 工具脚本、`skills/raspbot_ros2_patrol/`、`openclaw_agent_entry`、`OPENCLAW_SKILL.md`、单元测试、JSONL 审计、`config/agent_command_gateway.yaml` | `patrol_full.launch.py` 与 `patrol_full_*.launch.py` 已自动拉起 gateway，`setup.py` 已纳入配置安装与入口 | OpenClaw UI 可直接导入本仓库 skill（可选） |

## 安装

```bash
# Node.js 20+ required
npm install -g openclaw

# Verify
openclaw --version
```

## 自然语言示例

### 查询类
```
"最近有没有检测到人？"    → query_latest_patrol.sh --occupied
"今天巡检情况怎么样？"    → generate_report.sh
"小车现在状态正常吗？"    → robot_status.sh
"Dashboard 地址是什么？"  → robot_status.sh (读取 dashboard_url)
"巡检服务是不是还在运行？" → systemd_status.sh
```

### 巡检类
```
"现在巡检一次。"          → trigger_patrol_once.sh
"去门口检查一下。"        → run_route.sh door_check_route
"执行办公室短路线。"      → run_route.sh desk_check_route
"停止当前任务。"          → stop_route.sh
"暂停一下。"              → pause_route.sh
```

### 拒绝类
```
"往前开 10 秒。"          → 拒绝：不支持直接底盘速度控制
"关闭避障继续走。"        → 拒绝：绕过安全机制
```

## 工具脚本

所有脚本在 `tools/openclaw/` 下：

| 脚本 | 功能 | 类型 |
|------|------|------|
| `robot_status.sh` | 查询系统状态 | 只读 |
| `query_latest_patrol.sh` | 查询巡检记录 | 只读 |
| `generate_report.sh` | 生成日报 | 只读 |
| `systemd_status.sh` | 服务状态 | 只读 |
| `trigger_patrol_once.sh` | 触发单次巡检 | 受控 |
| `run_route.sh` | 执行白名单路线 | 受控 |
| `stop_route.sh` | 停止路线 | 受控 |
| `pause_route.sh` | 暂停路线 | 受控 |
| `generate_route_preview.sh` | 生成路线草案 | 草案 |
| `openclaw_agent.sh` | 自然语言入口一键封装 | 受控 |
| `openclaw_bind.sh` | OpenClaw skill 安装 / 绑定助手 | 受控 |
| `OPENCLAW_SKILL.md` | OpenClaw skill pack / prompt | 配置 |
| `agent_decision.py` | 结果→下一步决策 | 辅助 |

## ROS2 执行流程

### 触发一次巡检

```
用户："巡检一次"
  → OpenClaw Agent 识别 action=trigger_patrol_once
  → trigger_patrol_once.sh 发布 /agent/command
  → agent_command_gateway_node 校验:
      - action 在白名单 ✅
      - patrol 未运行 ✅
  → 发布 /patrol/trigger
  → patrol_behavior_node 执行云台扫描
  → 等待 /patrol/final_result
  → 返回结果给 Agent
  → Agent 用自然语言总结
```

### 请求门口路线（当前执行固定 YAML 路线）

```
用户："去门口巡检一下"
  → OpenClaw Agent 识别 route_name=door_check_route
  → run_route.sh door_check_route 发布 /agent/command
  → agent_command_gateway_node 校验:
      - route_name 在白名单 ✅
      - 无障碍物 ✅
      - 无活动路线 ✅
  → 发布 /route_patrol/start
  → route_patrol_node 执行 stop-and-scan
  → 返回执行结果
  → Agent 总结
```

## 安全边界

Agent 永远不允许：
- 直接发布 /cmd_vel
- 直接控制电机
- 关闭 obstacle_avoid_node
- 执行任意 shell
- 修改 SQLite 原始数据
- 删除日志
- 修改 systemd 服务

参见 [AGENT_SAFETY.md](AGENT_SAFETY.md)。

## 启动方式

```bash
# 1. 启动 ROS2 巡检基础系统（已包含 agent_command_gateway_node）
source /opt/ros/jazzy/setup.bash
source ~/ros2_ws/install/setup.bash
ros2 launch raspbot_bringup patrol_full.launch.py

# 2. 如需单独调试 gateway，可手动启动
ros2 run raspbot_vision agent_command_gateway_node --ros-args \
  --params-file ~/ros2_ws/config/agent_command_gateway.yaml

# 3. OpenClaw Agent 通过调用 tools/openclaw/ 下的脚本与 ROS2 交互
```

## 当前约束（2026-08-12）

自然语言中的 `door_check_route`、`desk_check_route` 等名称目前用于 Agent 网关白名单准入，不会让 `route_patrol_node` 动态选择同名路线文件；节点实际运行的是 `route_patrol.yaml` 中配置的固定路线。命令结果应同时读取 `requested_route_name` 与 `executed_route_name`。

`run_route` 默认必须带 `require_confirmation: true`，且只有 `/ultrasonic/front` 提供正数、有限、2 秒内的新鲜值并达到至少 0.30 m 时才可能启动。网关还会在默认 120 秒后请求停止路线。不要把这些应用层检查理解为 ROS graph 的访问控制；OpenClaw 与 ROS 2 应部署在受信任的网络和账户边界内。

当前 shell 工具仍以 Linux 默认 `~/ros2_ws` 布局为前提。`RASPBOT_WS` 已用于主要 Python 节点的运行时路径，但移动工作区后需先检查并修改这些工具脚本，再绑定到 OpenClaw。实机验收以 [PI_VALIDATION_CHECKLIST.md](PI_VALIDATION_CHECKLIST.md) 为准。
