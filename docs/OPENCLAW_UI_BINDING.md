# OpenClaw UI Binding Guide

This repo now contains a workspace skill that OpenClaw can load directly.

## Local skill location

- `~/ros2_ws/skills/raspbot_ros2_patrol/SKILL.md`（默认 Linux 工作区）

## Recommended binding flow

1. Make sure the OpenClaw CLI is installed.
2. Bind the local skill directory.
3. Verify the skill appears in the list.
4. Use the skill prompt or the wrapper script for natural-language requests.

## One-command binding

```bash
cd ~/ros2_ws
./tools/openclaw/openclaw_bind.sh
```

Optional global install:

```bash
cd ~/ros2_ws
./tools/openclaw/openclaw_bind.sh --global
```

## Manual OpenClaw CLI commands

```bash
openclaw skills install ~/ros2_ws/skills/raspbot_ros2_patrol --as raspbot-ros2-patrol
openclaw skills list --eligible
openclaw skills info raspbot-ros2-patrol
```

## What the skill exposes

- Read-only status queries
- Patrol history and report generation
- Safe patrol triggers
- Whitelisted route execution
- Route stop and pause

## What it does not expose

- Direct `/cmd_vel`
- Arbitrary shell execution
- Safety bypass commands
- Non-whitelisted routes

## 工作区与安全说明

此绑定文档中的 shell 命令目前按 `~/ros2_ws` 设计；若工作区迁移到其他目录，先检查 `tools/openclaw/` 中的脚本路径，再将实际 skill 目录传给 `openclaw skills install`。`RASPBOT_WS` 支持主要 Python 节点的数据、模型和审计路径，但不自动重写这些 shell 工具。

绑定 skill 不会赋予直接底盘控制能力。`run_route` 仍经网关的白名单、人工确认、超声波新鲜度和时长限制；路线名称当前不是动态选路。参见 [AGENT_SAFETY.md](AGENT_SAFETY.md)。
