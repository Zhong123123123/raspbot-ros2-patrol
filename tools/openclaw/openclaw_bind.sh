#!/usr/bin/env bash
# ============================================================================
# openclaw_bind.sh — install the Raspbot skill into OpenClaw
# ============================================================================
# Purpose: Provide a one-command helper for binding the workspace skill into
#          a local OpenClaw installation.
#
# Safety:  Installs only the local skill directory. No robot control.
#
# Usage:   ./openclaw_bind.sh
#          ./openclaw_bind.sh --global
# ============================================================================

set -euo pipefail

export PATH="$HOME/.npm-global/bin:$PATH"

SKILL_DIR="/home/ubuntu/ros2_ws/skills/raspbot_ros2_patrol"
SKILL_NAME="raspbot-ros2-patrol"
GLOBAL_FLAG=""

if [ "${1:-}" = "--global" ]; then
  GLOBAL_FLAG="--global"
fi

if ! command -v openclaw >/dev/null 2>&1; then
  echo "{\"error\":\"openclaw_cli_not_found\"}" >&2
  exit 1
fi

if [ ! -d "$SKILL_DIR" ]; then
  echo "{\"error\":\"skill_dir_not_found\",\"path\":\"$SKILL_DIR\"}" >&2
  exit 1
fi

openclaw skills install "$SKILL_DIR" --as "$SKILL_NAME" $GLOBAL_FLAG

