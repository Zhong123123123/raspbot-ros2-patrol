"""Tests for the OpenClaw natural-language router."""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure package import works from source tree.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from raspbot_vision.openclaw_router import build_skill_prompt, detect_intent


def test_detect_route_request_to_door_check_route():
    routed = detect_intent('去门口巡检一下')
    assert routed.intent == 'run_route'
    assert routed.route_name == 'door_check_route'
    assert routed.script == 'run_route.sh'


def test_detect_report_request():
    routed = detect_intent('今天巡检情况怎么样，生成日报')
    assert routed.intent == 'generate_report'
    assert routed.script == 'generate_report.sh'


def test_detect_stop_request():
    routed = detect_intent('停止当前任务')
    assert routed.intent == 'stop_route'
    assert routed.script == 'stop_route.sh'


def test_detect_system_status_request():
    routed = detect_intent('巡检服务是不是还在运行？')
    assert routed.intent == 'systemd_status'
    assert routed.script == 'systemd_status.sh'


def test_prompt_contains_safety_rules():
    prompt = build_skill_prompt()
    assert 'Do not suggest direct /cmd_vel control.' in prompt
    assert 'run_route.sh <route_name>' in prompt
