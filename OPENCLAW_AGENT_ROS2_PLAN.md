下面这份可以直接保存成：

```text
docs/OPENCLAW_AGENT_ROS2_PLAN.md
```

---

# OpenClaw Agent + ROS2 巡检机器人自然语言控制计划文档

版本：V1.0
项目基础：Raspberry Pi 4B 8GB + Ubuntu 24.04 + ROS2 Jazzy + Raspbot 小车
目标方向：将现有 ROS2 巡检机器人升级为“自然语言 Agent 控制 ROS2 任务”的智能巡检系统。

> 状态说明：本文同时包含现状与规划。
> [已实现] = 已在当前树莓派仓库验证完成
> [计划中] = 设计方向，尚未落地实现
> [待实现] = 计划已明确，但当前还没有代码或运行验证

## 当前实现状态摘要

| 已实现 | 已集成 | 待接入 |
|------|------|------|
| `agent_command_gateway_node`、`tools/openclaw/`、`skills/raspbot_ros2_patrol/`、`openclaw_agent_entry`、`openclaw_agent.sh`、`openclaw_bind.sh`、`OPENCLAW_SKILL.md`、单元测试、JSONL 审计、`config/agent_command_gateway.yaml` | `patrol_full.launch.py` 与 `patrol_full_*.launch.py` 已自动拉起 gateway，`setup.py` 已纳入配置安装与入口 | OpenClaw UI 可直接导入本仓库 skill（可选） |

---

# 一、项目定位

## 1.1 项目名称

```text
基于 OpenClaw Agent 与 ROS2 的自然语言巡检机器人控制系统
```

## 1.2 一句话描述

```text
在现有 Raspberry Pi 4B + ROS2 巡检机器人基础上接入 OpenClaw Agent，使用户可以通过自然语言查询巡检状态、生成日报、触发定点巡检、执行白名单巡逻路线；Agent 负责理解意图和调用工具，ROS2 负责安全执行、状态反馈和日志追溯。
```

## 1.3 核心原则

```text
Agent 负责理解和规划
ROS2 负责执行和安全
底盘不接受 Agent 直接速度控制
所有移动任务必须经过安全网关
所有动作必须可追溯、可拒绝、可停止
```

## 1.4 项目边界

当前项目已经具备巡检闭环、人体检测、多轮确认、SQLite 日志、Web Dashboard、一键启动等基础能力；原项目计划也明确当前不依赖 SLAM、Nav2 和复杂路径规划，重点是做稳定、可演示、可面试讲清的 ROS2 工程闭环。

因此本阶段不做：

```text
不做 SLAM
不做 Nav2
不做地图导航
不做 Agent 直接发 /cmd_vel
不做 Agent 任意 shell 执行
不做多机器人协同
不做真正自主导航
不让 LLM 绕过 ROS2 安全节点
```

本阶段计划做：

```text
自然语言任务入口
Agent 工具调用
ROS2 安全命令网关
白名单路线执行
巡检日志查询
日报生成
状态查询
单次巡检触发
任务停止 / 暂停
完整测试与文档
```

---

# 二、目标系统架构 [计划中]

## 2.1 总体架构

```text
用户自然语言
  ↓
OpenClaw Agent
  ↓
OpenClaw Tools / Scripts
  ↓
agent_command_gateway_node
  ↓
ROS2 安全执行层
  ├── patrol_behavior_node
  ├── route_patrol_node
  ├── patrol_logger_node
  ├── obstacle_avoid_node
  └── base_driver_node
  ↓
小车硬件执行
```

## 2.2 分层说明

```text
自然语言层：
用户通过 OpenClaw 输入自然语言指令。

Agent 层：
Agent 理解用户意图，并选择合适工具。

工具层：
tools/openclaw/ 下的脚本负责把 Agent 意图转换为受限 ROS2 请求。

安全网关层：
agent_command_gateway_node 校验命令是否合法、安全、是否在白名单内。

ROS2 执行层：
现有 patrol_behavior_node / route_patrol_node 执行巡检或路线任务。

硬件层：
底盘、云台、摄像头、超声波、LED、蜂鸣器执行实际动作。
```

## 2.3 关键安全边界

Agent 永远不允许直接做这些事情：

```text
直接发布 /cmd_vel
直接控制电机
关闭 obstacle_avoid_node
关闭安全接管
执行任意 shell
修改 SQLite 原始数据
修改 systemd 服务
删除日志
修改模型文件
修改巡检主状态机
```

Agent 只允许通过白名单工具做这些事情：

```text
查询机器人状态
查询最近巡检记录
生成 Markdown 日报
触发一次定点巡检
执行白名单路线
暂停路线
停止当前任务
查看 systemd 状态
获取 Dashboard 地址
```

---

# 三、目标功能清单

## 3.1 V1：只读 Agent 运维能力

目标：先让 Agent 能“看懂系统状态”，不控制机器人运动。

功能：

```text
1. 查询机器人当前状态
2. 查询 ROS2 节点
3. 查询 ROS2 核心 topic
4. 查询最近巡检记录
5. 查询最近 occupied 记录
6. 生成 Markdown 日报
7. 查询 systemd 服务状态
8. 返回 Dashboard 地址
```

自然语言示例：

```text
“最近有没有检测到人？”
“帮我看一下小车现在运行状态。”
“生成今天的巡检日报。”
“Dashboard 地址是什么？”
“巡检服务是不是还在运行？”
```

## 3.2 V2：低风险巡检触发能力

目标：允许 Agent 触发一次已有的定点巡检流程。

功能：

```text
1. Agent 调用 trigger_patrol_once
2. 网关检查 patrol_full 是否运行
3. 网关检查 /patrol/trigger 是否存在
4. 网关发布一次巡检触发
5. 等待 /patrol/final_result
6. 返回巡检结果
```

自然语言示例：

```text
“现在巡检一次。”
“帮我检查一下办公室有没有人。”
“触发一次云台扫描。”
```

## 3.3 V3：白名单路线巡逻

目标：允许 Agent 执行提前配置好的固定路线，但不能自由控制底盘。

功能：

```text
1. 支持 run_route action
2. route_name 必须在 whitelist_routes 内
3. 路线由 route_patrol_node 执行
4. 移动采用 stop-and-scan 策略
5. 遇障碍物暂停
6. 结束后返回路线执行结果
```

自然语言示例：

```text
“去门口巡检一下。”
“执行办公室短路线。”
“巡检门口和桌子附近。”
```

## 3.4 V4：Agent 根据结果选择下一步

目标：Agent 可以根据巡检结果，在允许动作集合内选择下一步。

示例逻辑：

```text
如果 door_check_route 检测到 occupied：
  停止继续移动
  发送告警
  返回 occupied 结果

如果结果 empty：
  继续执行 desk_check_route

如果结果 uncertain：
  原地重试一次
```

限制：

```text
Agent 只能从 allowed_actions 里选择
不能生成任意底盘速度
不能绕过安全网关
不能无限重试
```

## 3.5 V5：路线草案生成

目标：Agent 可以根据自然语言生成路线 YAML 草案，但默认不直接执行。

示例：

用户：

```text
“帮我规划一个从起点到门口，再到桌子旁边的巡检路线。”
```

Agent 生成：

```yaml
route:
  - name: start_scan
    action: patrol
  - name: move_to_door
    action: move
    linear_x: 0.06
    duration_sec: 1.5
  - name: door_scan
    action: patrol
  - name: turn_to_desk
    action: turn
    angular_z: -0.30
    duration_sec: 0.9
  - name: desk_scan
    action: patrol
```

保存为：

```text
routes/generated_route_preview.yaml
```

必须人工确认后才能加入白名单。

---

# 四、计划新增模块设计 [待实现]

## 4.1 agent_command_gateway_node

节点名：

```text
agent_command_gateway_node
```

建议包位置：

```text
raspbot_vision
```

原因：

```text
它属于决策层 / 行为编排层，不是底层驱动。
```

订阅：

```text
/agent/command
/patrol/final_result
/patrol/confirmed_status
/patrol/alert
/route_patrol/status
/ultrasonic/front
```

发布：

```text
/agent/command_result
/patrol/trigger
/route_patrol/start
/route_patrol/stop
/route_patrol/pause
```

消息类型：

```text
std_msgs/String
```

内容使用 JSON。

## 4.2 /agent/command 格式

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

运行白名单路线：

```json
{
  "command_id": "cmd_20260705_002",
  "source": "openclaw",
  "action": "run_route",
  "params": {
    "route_name": "door_check_route"
  },
  "require_confirmation": true,
  "timestamp": "2026-07-05T12:01:00Z"
}
```

查询状态：

```json
{
  "command_id": "cmd_20260705_003",
  "source": "openclaw",
  "action": "query_status",
  "params": {},
  "require_confirmation": false
}
```

## 4.3 /agent/command_result 格式

成功：

```json
{
  "command_id": "cmd_20260705_001",
  "accepted": true,
  "executed": true,
  "result": "patrol_completed",
  "data": {
    "final_decision": "empty",
    "max_confidence": 0.0
  },
  "reason": "",
  "timestamp": "2026-07-05T12:00:20Z"
}
```

拒绝：

```json
{
  "command_id": "cmd_20260705_004",
  "accepted": false,
  "executed": false,
  "result": "rejected",
  "data": {},
  "reason": "action_not_allowed",
  "timestamp": "2026-07-05T12:03:00Z"
}
```

危险命令拒绝：

```json
{
  "command_id": "cmd_20260705_005",
  "accepted": false,
  "executed": false,
  "result": "rejected",
  "reason": "direct_cmd_vel_not_allowed"
}
```

---

# 五、配置文件设计

新增：

```text
config/agent_command_gateway.yaml
```

示例：

```yaml
agent_command_gateway:
  ros__parameters:
    agent_command_topic: "/agent/command"
    agent_result_topic: "/agent/command_result"

    patrol_trigger_topic: "/patrol/trigger"
    patrol_result_topic: "/patrol/final_result"
    patrol_status_topic: "/patrol/confirmed_status"
    patrol_alert_topic: "/patrol/alert"

    route_start_topic: "/route_patrol/start"
    route_stop_topic: "/route_patrol/stop"
    route_pause_topic: "/route_patrol/pause"
    route_status_topic: "/route_patrol/status"

    ultrasonic_topic: "/ultrasonic/front"

    allowed_actions:
      - query_status
      - query_latest_patrol
      - generate_report
      - trigger_patrol_once
      - run_route
      - stop_route
      - pause_route
      - get_dashboard_url
      - systemd_status

    forbidden_actions:
      - direct_cmd_vel
      - shell
      - disable_safety
      - modify_database
      - stop_obstacle_avoid
      - delete_logs

    whitelist_routes:
      - short_test_route
      - door_check_route
      - desk_check_route
      - office_demo_route

    require_confirmation_for_routes: true
    max_route_duration_sec: 120.0
    min_obstacle_distance_m: 0.30
    patrol_timeout_sec: 30.0
    command_timeout_sec: 60.0

    reject_if_obstacle_too_close: true
    reject_if_patrol_active: true
    reject_if_route_active: true

    dashboard_url: "http://raspberrypi.local:8080"

    log_agent_commands: true
    agent_log_path: "/home/ubuntu/ros2_ws/data/agent/agent_commands.jsonl"
```

---

# 六、计划中的 OpenClaw 工具脚本设计 [待实现]

新增目录：

```text
tools/openclaw/
```

## 6.1 robot_status.sh

用途：

```text
查询机器人状态
```

输出：

```text
hostname
uptime
memory
disk
ROS2 node list
ROS2 topic list
patrol service status
dashboard url
```

要求：

```text
只读
有 timeout
失败返回非 0
不执行危险命令
```

## 6.2 query_latest_patrol.sh

用途：

```text
查询最近巡检记录
```

调用：

```bash
python3 tools/query_patrol_results.py --latest 5
```

支持参数：

```bash
./query_latest_patrol.sh --latest 5
./query_latest_patrol.sh --occupied
```

## 6.3 generate_report.sh

用途：

```text
生成 Markdown 日报
```

调用：

```bash
python3 tools/generate_patrol_report.py
```

输出：

```text
日报路径
occupied 次数
empty 次数
uncertain 次数
```

## 6.4 trigger_patrol_once.sh

用途：

```text
触发一次安全巡检
```

流程：

```text
1. source ROS2 环境
2. 检查 /patrol/trigger 是否存在
3. 发布 /agent/command action=trigger_patrol_once
4. 等待 /agent/command_result
5. 输出结果
```

注意：

```text
不直接控制底盘
不直接操作 person_detect_node
只走 agent_command_gateway_node
```

## 6.5 run_route.sh

用途：

```text
执行白名单路线
```

示例：

```bash
./run_route.sh door_check_route
```

内部发送：

```json
{
  "action": "run_route",
  "params": {
    "route_name": "door_check_route"
  }
}
```

要求：

```text
route_name 不允许包含 shell 特殊字符
route_name 必须由 gateway 再校验
脚本层也做一次基本校验
```

## 6.6 stop_route.sh

用途：

```text
停止当前路线任务
```

发送：

```json
{
  "action": "stop_route"
}
```

要求：

```text
必须安全
必须可随时调用
不能依赖 Agent 二次确认
```

## 6.7 pause_route.sh

用途：

```text
暂停当前路线任务
```

发送：

```json
{
  "action": "pause_route"
}
```

---

# 七、自然语言到工具映射 [计划中]

## 7.1 查询类

用户说：

```text
“最近有没有检测到人？”
```

Agent 应调用：

```bash
tools/openclaw/query_latest_patrol.sh --occupied --latest 5
```

用户说：

```text
“今天巡检情况怎么样？”
```

Agent 应调用：

```bash
tools/openclaw/generate_report.sh
```

用户说：

```text
“小车现在状态正常吗？”
```

Agent 应调用：

```bash
tools/openclaw/robot_status.sh
```

## 7.2 巡检类

用户说：

```text
“现在巡检一次。”
```

Agent 应调用：

```bash
tools/openclaw/trigger_patrol_once.sh
```

用户说：

```text
“去门口检查一下。”
```

Agent 应调用：

```bash
tools/openclaw/run_route.sh door_check_route
```

用户说：

```text
“停止当前任务。”
```

Agent 应调用：

```bash
tools/openclaw/stop_route.sh
```

## 7.3 拒绝类

用户说：

```text
“往前开 10 秒。”
```

第一版应拒绝，或者转换成白名单路线，不能直接发速度。

回复：

```text
当前不支持直接底盘速度控制。可以执行已配置的白名单路线，例如 short_test_route 或 door_check_route。
```

用户说：

```text
“关闭避障继续走。”
```

必须拒绝：

```text
该操作会绕过安全机制，已拒绝。
```

---

# 八、运行流程设计 [计划中]

## 8.1 触发一次巡检

```text
用户：
“巡检一次”

OpenClaw Agent：
识别 action=trigger_patrol_once

tools/openclaw/trigger_patrol_once.sh：
发送 /agent/command

agent_command_gateway_node：
检查 action 白名单
检查当前不是 route_active
检查 patrol_full 正常
发布 /patrol/trigger
等待 /patrol/final_result

patrol_behavior_node：
云台左/中/右扫描
触发人体检测
合并结果
发布 final_result

patrol_logger_node：
写入 SQLite 和截图路径

agent_command_gateway_node：
返回 command_result

OpenClaw Agent：
用自然语言总结结果
```

## 8.2 执行门口巡逻路线

```text
用户：
“去门口巡检一下”

OpenClaw Agent：
识别 route_name=door_check_route

tools/openclaw/run_route.sh：
发送 /agent/command action=run_route

agent_command_gateway_node：
检查 route_name 是否在 whitelist_routes
检查障碍距离
检查当前任务状态
发布 /route_patrol/start

route_patrol_node：
低速移动
停车
触发 /patrol/trigger
等待结果
路线完成

agent_command_gateway_node：
返回 route_completed 或 rejected

OpenClaw Agent：
总结执行结果
```

---

# 九、安全策略

## 9.1 指令白名单

所有 Agent 请求必须满足：

```text
action 在 allowed_actions 内
route_name 在 whitelist_routes 内
source 是 openclaw 或 trusted_tool
JSON 格式合法
命令没有过期
机器人状态允许执行
```

## 9.2 移动限制

移动相关能力只允许：

```text
执行预定义 route
暂停 route
停止 route
```

禁止：

```text
任意速度
任意转向
任意时长
绕过避障
动态高速路径
```

## 9.3 障碍物检查

执行路线前检查：

```text
front_distance >= min_obstacle_distance_m
```

执行中由 `route_patrol_node` 和 `obstacle_avoid_node` 继续负责安全暂停。

## 9.4 状态冲突检查

如果当前正在执行路线：

```text
拒绝新的 run_route
允许 stop_route
允许 query_status
```

如果当前正在巡检：

```text
拒绝新的 trigger_patrol_once
允许 query_status
允许 stop_route
```

## 9.5 日志审计

所有 Agent 命令记录到：

```text
~/ros2_ws/data/agent/agent_commands.jsonl
```

每行 JSON：

```json
{
  "timestamp": "2026-07-05T12:00:00Z",
  "command_id": "cmd_001",
  "source": "openclaw",
  "action": "run_route",
  "params": {"route_name": "door_check_route"},
  "accepted": true,
  "executed": true,
  "result": "route_completed",
  "reason": ""
}
```

---

# 十、开发阶段计划

## 阶段 0：基线冻结

目标：

```text
确认当前 ROS2 巡检系统稳定可运行。
```

任务：

```text
1. colcon build 通过
2. colcon test 通过
3. patrol_full.launch.py 能启动
4. /patrol/trigger 能触发巡检
5. SQLite 能写入结果
6. route_patrol_node 如已存在，确认可用
7. Web Dashboard 可访问
```

交付物：

```text
当前 git commit
当前节点列表
当前 topic 列表
一次完整巡检日志
```

---

## 阶段 1：OpenClaw 安装与隔离验证

目标：

```text
让 OpenClaw 在树莓派上运行，但不接入机器人控制。
```

任务：

```text
1. 检查系统环境
2. 安装 OpenClaw
3. 检查 gateway 状态
4. 检查资源占用
5. 确认 ROS2 巡检系统不受影响
```

验收：

```text
OpenClaw 能启动
ROS2 仍能启动
CPU/内存占用可接受
没有改动机器人主线
```

---

## 阶段 2：只读工具接入

目标：

```text
让 Agent 可以查询机器人状态和巡检日志。
```

新增：

```text
tools/openclaw/robot_status.sh
tools/openclaw/query_latest_patrol.sh
tools/openclaw/generate_report.sh
tools/openclaw/systemd_status.sh
```

验收：

```text
自然语言可以查询最近巡检结果
自然语言可以生成日报
自然语言可以查看机器人状态
无任何移动动作
```

---

## 阶段 3：agent_command_gateway_node

目标：

```text
建立 Agent 到 ROS2 的安全命令网关。
```

新增：

```text
agent_command_gateway_node
config/agent_command_gateway.yaml
/agent/command
/agent/command_result
```

验收：

```text
合法 action 被接受
非法 action 被拒绝
direct_cmd_vel 被拒绝
shell 被拒绝
非白名单 route 被拒绝
所有结果有 JSON 返回
所有命令有日志
```

---

## 阶段 4：单次巡检触发

目标：

```text
Agent 可以触发一次已有巡检流程。
```

新增：

```text
tools/openclaw/trigger_patrol_once.sh
```

验收：

```text
自然语言“巡检一次”能触发 /patrol/trigger
能等待 /patrol/final_result
能返回 occupied / empty / uncertain
能写入 SQLite
```

---

## 阶段 5：白名单路线执行

目标：

```text
Agent 可以执行提前定义好的安全路线。
```

新增：

```text
tools/openclaw/run_route.sh
tools/openclaw/stop_route.sh
tools/openclaw/pause_route.sh
```

配置：

```yaml
whitelist_routes:
  - short_test_route
  - door_check_route
  - desk_check_route
```

验收：

```text
自然语言“去门口巡检”能执行 door_check_route
非白名单路线被拒绝
遇障碍物暂停
任务可停止
结束后返回结果
```

---

## 阶段 6：Agent 决策下一步

目标：

```text
Agent 根据巡检结果，在 allowed_actions 内选择下一步。
```

示例策略：

```text
occupied -> stop_and_alert
empty -> continue_route
uncertain -> retry_once
obstacle -> pause_route
```

验收：

```text
Agent 能根据巡检结果选择下一步
但不能越权控制底盘
所有动作仍经过 gateway
```

---

## 阶段 7：路线草案生成

目标：

```text
Agent 能生成路线 YAML 草案，但默认不执行。
```

新增：

```text
tools/openclaw/generate_route_preview.sh
routes/generated_route_preview.yaml
```

验收：

```text
能根据自然语言生成 route YAML
生成后不自动执行
需要人工确认后加入 whitelist_routes
```

---

## 阶段 8：系统实测与演示

目标：

```text
完成完整演示闭环。
```

演示脚本：

```text
1. 用户通过自然语言问“最近有没有人”
2. Agent 查询 SQLite 日志并回答
3. 用户说“现在巡检一次”
4. Agent 调用 trigger_patrol_once
5. 小车云台扫描并检测
6. Agent 返回结果
7. 用户说“去门口巡检”
8. Agent 执行 door_check_route
9. 遇到人后告警
10. 生成 Markdown 日报
```

---

# 十一、测试计划

## 11.1 单元测试

覆盖：

```text
合法 JSON 解析
非法 JSON 拒绝
合法 action 接受
非法 action 拒绝
direct_cmd_vel 拒绝
shell 拒绝
白名单 route 接受
非白名单 route 拒绝
obstacle too close 拒绝
patrol active 时拒绝重复巡检
route active 时拒绝重复路线
command_result 格式正确
agent command 日志写入
```

## 11.2 集成测试

测试命令：

```bash
ros2 topic pub --once /agent/command std_msgs/msg/String \
"{data: '{\"command_id\":\"test_001\",\"source\":\"openclaw\",\"action\":\"query_status\",\"params\":{}}'}"
```

观察：

```bash
ros2 topic echo /agent/command_result
```

测试触发巡检：

```bash
ros2 topic pub --once /agent/command std_msgs/msg/String \
"{data: '{\"command_id\":\"test_002\",\"source\":\"openclaw\",\"action\":\"trigger_patrol_once\",\"params\":{}}'}"
```

测试非法命令：

```bash
ros2 topic pub --once /agent/command std_msgs/msg/String \
"{data: '{\"command_id\":\"test_003\",\"source\":\"openclaw\",\"action\":\"direct_cmd_vel\",\"params\":{\"linear_x\":1.0}}'}"
```

预期：

```text
accepted=false
reason=direct_cmd_vel_not_allowed
```

## 11.3 硬件测试

顺序：

```text
1. 不启动底盘，只测 query_status
2. 启动 patrol_full，只测 trigger_patrol_once
3. 架空轮子，测 run_route
4. 落地低速，测 short_test_route
5. 测 stop_route
6. 测障碍物暂停
```

## 11.4 稳定性测试

```text
连续自然语言查询 20 次
连续触发巡检 10 次
连续执行短路线 5 次
Agent 命令日志无丢失
ROS2 主节点不崩溃
小车无危险运动
```

---

# 十二、文档交付物

新增文档：

```text
docs/OPENCLAW_AGENT_CONTROL.md
docs/AGENT_COMMAND_GATEWAY.md
docs/AGENT_SAFETY.md
docs/AGENT_TEST_REPORT.md
```

## 12.1 OPENCLAW_AGENT_CONTROL.md

内容：

```text
项目定位
安装 OpenClaw
自然语言示例
工具调用说明
ROS2 执行流程
安全边界
启动方式
```

## 12.2 AGENT_COMMAND_GATEWAY.md

内容：

```text
/agent/command 格式
/agent/command_result 格式
支持 action
拒绝规则
配置参数
日志格式
```

## 12.3 AGENT_SAFETY.md

内容：

```text
为什么不允许直接 /cmd_vel
白名单路线机制
障碍物检查机制
任务状态检查
人工确认机制
危险命令拒绝示例
```

## 12.4 AGENT_TEST_REPORT.md

内容：

```text
测试环境
测试命令
测试结果
功能通过表
失败问题
下一步优化
```

---

# 十三、简历与面试表述

## 13.1 简历 bullet

```text
- 在 ROS2 巡检机器人系统外接入 OpenClaw Agent，设计自然语言到机器人任务的受控执行链路，支持通过自然语言查询巡检日志、生成日报、触发单次巡检和执行白名单巡逻路线。
- 设计 agent_command_gateway_node 作为 AI Agent 与 ROS2 执行层之间的安全网关，对 Agent 请求进行 action 白名单、路线白名单、障碍距离、任务状态和超时校验，避免 LLM 直接控制底盘运动。
- 将 Agent 工具调用封装为只读查询、低风险巡检触发和受控路线执行三类能力，结合 SQLite 日志、Dashboard 和 systemd 服务实现机器人远程智能运维闭环。
```

## 13.2 面试 2 分钟讲法

```text
我的项目原本是一个基于 Raspberry Pi 4B 和 ROS2 Jazzy 的办公室巡检机器人，已经具备人体检测、云台扫描、超声波避障、SQLite 日志、Dashboard 和一键启动能力。

后续我在系统外接入 OpenClaw Agent，把它作为自然语言任务入口。用户可以说“巡检一次”“查最近有没有人”“去门口巡检一下”，Agent 会理解意图并调用受限工具。

我没有让 Agent 直接发布 /cmd_vel 控制底盘，而是设计了 agent_command_gateway_node 作为安全网关。所有来自 Agent 的命令都必须经过 action 白名单、route 白名单、障碍物距离、任务状态和超时检查。真正的运动仍然由 ROS2 的 route_patrol_node、obstacle_avoid_node 和 base_driver_node 执行。

这样系统既有 AI Agent 的自然语言交互能力，也保留了 ROS2 机器人系统的安全边界和可追溯性。
```

## 13.3 高频追问

### Q1：为什么不让 Agent 直接控制 `/cmd_vel`？

```text
因为 LLM 输出不可完全预测，直接控制底盘有安全风险。我把 Agent 限制在高级任务层，只能触发白名单任务，底盘控制仍由 ROS2 安全节点执行。
```

### Q2：Agent 怎么知道能执行哪些动作？

```text
我在 agent_command_gateway.yaml 里定义 allowed_actions 和 whitelist_routes，网关节点只接受白名单内动作，其他全部拒绝。
```

### Q3：如果 Agent 生成危险命令怎么办？

```text
网关会拒绝。例如 direct_cmd_vel、disable_safety、shell、modify_database 都在 forbidden_actions 中，即使 Agent 调用了也不会执行。
```

### Q4：这个算不算真正 AI Agent？

```text
算轻量级机器人 Agent 工具调用系统。Agent 负责自然语言理解、工具选择和任务规划，ROS2 负责安全执行和状态反馈。重点不是让 LLM 接管底盘，而是把 Agent 接入机器人任务闭环。
```

---

# 十四、最终验收标准

项目达到以下标准后，可以认为 OpenClaw Agent 集成阶段完成：

```text
1. OpenClaw 能正常运行
2. ROS2 巡检系统不受 OpenClaw 影响
3. Agent 能通过自然语言查询机器人状态
4. Agent 能查询最近巡检记录
5. Agent 能生成 Markdown 日报
6. Agent 能触发一次定点巡检
7. Agent 能执行白名单路线
8. Agent 不能直接控制 /cmd_vel
9. 非法 action 会被拒绝
10. 非白名单 route 会被拒绝
11. 所有 Agent 命令有日志记录
12. 支持 stop_route 紧急停止任务
13. 支持障碍物过近时拒绝或暂停路线
14. Dashboard 和 SQLite 能看到执行结果
15. 文档能讲清自然语言、工具调用、ROS2 执行和安全边界
```

---

# 十五、推荐实施顺序

```text
1. 先不要开放移动能力，只做 Agent 查询日志和状态
2. 再做 agent_command_gateway_node
3. 再开放 trigger_patrol_once
4. 再开放 run_route 白名单路线
5. 再做 Agent 根据结果选择下一步
6. 最后做路线草案生成
```

最小可演示版本：

```text
自然语言：“现在巡检一次”
OpenClaw Agent 调用 trigger_patrol_once
agent_command_gateway_node 校验并发布 /patrol/trigger
ROS2 完成云台扫描和人体检测
SQLite 写日志
Agent 返回“本次巡检结果：empty / occupied / uncertain”
```

完整增强版本：

```text
自然语言：“去门口巡检一下，如果有人就通知我”
OpenClaw Agent 调用 run_route door_check_route
ROS2 执行低速路线和 stop-and-scan 巡检
检测到 occupied 后发布告警
Agent 查询结果并总结
生成日报或远程通知
```

---

# 十六、结论

这个方向可以作为你项目的高级扩展：

```text
ROS2 巡检机器人
+
OpenClaw Agent 自然语言任务入口
+
受限工具调用
+
ROS2 安全命令网关
+
白名单路线执行
+
日志追溯与远程运维
```

它的亮点不是“让 AI 随便控制机器人”，而是：

```text
让 AI Agent 在明确安全边界内调用机器人能力。
```

这会比单纯加一个模型、加一个 Dashboard、加一个通知更有项目辨识度，也更适合面试讲系统设计。


---

# 十七、可执行版里程碑清单

> 说明：下面这版是“能落地执行”的版本。每个阶段都按输入、输出、验收、风险来写，方便排期和复盘。

## 17.1 里程碑 M0：现状冻结与边界确认 [已实现]

输入：

```text
当前 ROS2 巡检机器人主线代码
当前测试报告
当前已验证的巡检 / 日志 / Dashboard / 路线能力
```

输出：

```text
基线版本说明
能力边界说明
禁止项清单
```

验收：

```text
能明确区分“已实现能力”和“计划能力”
不会把 OpenClaw 相关能力误写成现状
```

风险：

```text
如果不冻结边界，后续文档会把规划和实现混写
```

## 17.2 里程碑 M1：只读接入 [待实现]

输入：

```text
OpenClaw 运行环境
只读脚本清单
ROS2 环境只读查询能力
```

输出：

```text
robot_status.sh
query_latest_patrol.sh
generate_report.sh
systemd_status.sh
```

验收：

```text
自然语言能转成只读查询
不产生任何移动控制
所有脚本有 timeout 和非 0 失败返回
```

风险：

```text
脚本可能读取到不完整环境变量
OpenClaw 与 ROS2 的启动顺序可能导致查询失败
```

## 17.3 里程碑 M2：安全网关 [待实现]

输入：

```text
/agent/command 消息格式
allowed_actions 列表
whitelist_routes 列表
现有 patrol / route / alert topic
```

输出：

```text
agent_command_gateway_node
config/agent_command_gateway.yaml
/agent/command
/agent/command_result
```

验收：

```text
非法 action 被拒绝
direct_cmd_vel 被拒绝
非白名单 route 被拒绝
所有结果可回传且可追踪
```

风险：

```text
如果网关与现有巡检状态机耦合过深，容易引入死锁或重复触发
```

## 17.4 里程碑 M3：单次巡检触发 [待实现]

输入：

```text
现有 patrol_behavior_node
/patrol/trigger
/patrol/final_result
```

输出：

```text
trigger_patrol_once.sh
巡检触发结果回传
```

验收：

```text
“巡检一次” 能触发现有巡检链路
结果能返回 occupied / empty / uncertain
能写入 SQLite
```

风险：

```text
触发频率过高会和现有巡检调度冲突
```

## 17.5 里程碑 M4：白名单路线执行 [待实现]

输入：

```text
route_patrol_node
白名单路线配置
障碍物安全状态
```

输出：

```text
run_route.sh
stop_route.sh
pause_route.sh
白名单路线执行日志
```

验收：

```text
能执行 door_check_route / desk_check_route 等固定路线
非白名单路线被拒绝
遇障碍能暂停
任务能停止
```

风险：

```text
如果白名单路线和现场布置不一致，容易出现路线可执行但实地不可用
```

## 17.6 里程碑 M5：结果驱动下一步 [待实现]

输入：

```text
巡检结果 occupied / empty / uncertain
路线状态
告警状态
```

输出：

```text
Agent 下一步动作建议
停止 / 继续 / 重试 / 告警
```

验收：

```text
Agent 只能在 allowed_actions 内选下一步
不能越权生成底盘速度
不能绕过 gateway
```

风险：

```text
决策链过长会增加延迟，现场体验会变差
```

## 17.7 里程碑 M6：路线草案生成 [待实现]

输入：

```text
自然语言路线需求
现有 route 模板
```

输出：

```text
routes/generated_route_preview.yaml
人工确认后的白名单路线草案
```

验收：

```text
只能生成草案，不能直接执行
必须人工确认后才能加入白名单
```

风险：

```text
如果不做人工审核，路线草案可能带来安全风险
```

---

# 十八、需要改成状态标签的句子清单

> 下面这些不是要删，而是要把它们明确标成 [已实现] / [计划中] / [待实现]，避免读者误会。

## 18.1 建议标成 [已实现]

- “当前项目已经具备巡检闭环、人体检测、多轮确认、SQLite 日志、Web Dashboard、一键启动等基础能力”
- “不做 SLAM / 不做 Nav2 / 不做地图导航”
- “route_patrol_node 执行路线巡逻”
- “patrol_behavior_node / patrol_logger_node / web_dashboard” 这些现有能力描述
- “ROS2 安全执行层” 中已经落地的节点

## 18.2 建议标成 [计划中]

- “OpenClaw Agent” 作为自然语言入口
- “OpenClaw Tools / Scripts”
- “agent_command_gateway_node”
- “/agent/command”
- “/agent/command_result”
- “config/agent_command_gateway.yaml”
- “tools/openclaw/” 目录下所有脚本
- “白名单路线执行” 作为 Agent 集成能力
- “Agent 根据结果选择下一步”

## 18.3 建议标成 [待实现]

- “允许 Agent 触发一次已有的定点巡检流程”
- “允许 Agent 执行提前配置好的固定路线”
- “Agent 可以根据自然语言生成路线 YAML 草案”
- “自然语言可以查询机器人状态 / 生成日报 / 触发巡检 / 执行路线” 这些对外能力
- “OpenClaw 能正常运行”
- “合法 action 被接受、非法 action 被拒绝” 的网关验收

## 18.4 最容易混淆的原句，建议直接改写

- “最终系统架构” -> “目标系统架构”
- “本阶段重点做” -> “本阶段计划做”
- “核心新增模块设计” -> “计划新增模块设计”
- “工具层” -> “计划中的工具层”
- “ROS2 执行层” 如果描述现有节点，可以保留并标 [已实现]
- “完整增强版本” -> “目标增强版本”

## 18.5 推荐的统一写法

```text
[已实现] 当前仓库中已验证可运行
[计划中] 设计已确定，但代码尚未完成
[待实现] 已列入计划，但还没有开发或验证
```
