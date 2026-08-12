# Agent Safety — 安全机制说明

## 为什么不直接控制 /cmd_vel

LLM 输出不可完全预测。如果 Agent 可以直接发布 `/cmd_vel`：

- 可能生成危险速度值
- 可能绕过避障节点
- 可能忽略当前机器人状态
- 无法做白名单校验

因此，所有移动必须通过 ROS2 安全节点执行，Agent 只能触发预定义任务。

## 安全层级

```
Layer 1: Agent 工具脚本
  └─ 脚本层面参数校验（如 route_name 不允许特殊字符）

Layer 2: agent_command_gateway_node
  └─ action 白名单
  └─ route 白名单
  └─ 障碍物距离检查
  └─ 任务冲突检查
  └─ 超时保护

Layer 3: ROS2 执行层
  └─ obstacle_avoid_node 持续监控
  └─ route_patrol_node 内置 stop-and-scan
  └─ base_driver_node 硬件层保护
```

## 白名单路线机制

只有 `config/agent_command_gateway.yaml` 中 `whitelist_routes` 列出的路线名称可以被 Agent 网关接受；当前底层仍执行固定 YAML 路线，不会按名称动态加载不同文件。

添加路线的流程：
1. 在 `config/route_patrol.yaml` 中定义路线步骤
2. 架空轮子测试（wheels elevated）
3. 低速地面测试
4. 将路线名加入 `whitelist_routes`
5. 重启 gateway 节点

## 障碍物检查机制

执行 `run_route` 前：
- 检查 `/ultrasonic/front` 距离
- 距离 < `min_obstacle_distance_m`（默认 0.30m）→ 拒绝

执行中：
- `route_patrol_node` 的 `should_pause_for_obstacle` 持续检查
- `obstacle_avoid_node` 独立运行，不被 Agent 关闭

## 任务状态检查

| 当前状态 | trigger_patrol_once | run_route | stop_route |
|---------|---------------------|-----------|------------|
| 空闲 | ✅ | ✅ | ✅（idempotent） |
| 巡检中 | ❌ | ✅ | ✅ |
| 路线执行中 | ✅ | ❌ | ✅ |

## 人工确认机制

- `run_route` 默认 `require_confirmation: true`
- 生成的路线草案默认不执行
- 路线必须人工确认后加入白名单

## 危险命令拒绝示例

```bash
# 拒绝：直接速度控制
{"action": "direct_cmd_vel", "params": {"linear_x": 1.0}}
→ {"accepted": false, "reason": "direct_cmd_vel_not_allowed"}

# 拒绝：任意 shell
{"action": "shell", "params": {"command": "rm -rf /"}}
→ {"accepted": false, "reason": "shell_not_allowed"}

# 拒绝：关闭安全
{"action": "disable_safety"}
→ {"accepted": false, "reason": "disable_safety_not_allowed"}

# 拒绝：非白名单路线
{"action": "run_route", "params": {"route_name": "secret_route"}}
→ {"accepted": false, "reason": "route_not_whitelisted"}
```

## 当前安全语义（2026-08-12）

网关在启动路线前要求有效的超声波值为“正数、有限且新鲜”。默认 2 秒未收到新值即视为陈旧并拒绝路线，不以旧测距值继续放行；距离低于 0.30 m 同样拒绝。路线还需要显式人工确认，并受 120 秒最大时长保护，超时会请求停止路线。

这层是应用级准入，不是 ROS 2 网络认证：能够直接访问 ROS graph 的主体仍可能绕过 `/agent/command`。生产使用应限制 ROS 网络、终端账户和物理急停权限。Dashboard 的 token 只约束浏览器控制消息，不保护监控页面本身；远程监听时需要可信网络和防火墙。

路线名白名单也不是动态路径选择机制。当前仅允许已审核名称发起固定 YAML 路线；在实现真正的多路线加载、参数校验和独立实机测试前，不能将它描述为按名称导航。
