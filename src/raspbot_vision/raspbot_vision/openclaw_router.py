#!/usr/bin/env python3
"""OpenClaw natural-language router for Raspbot ROS2.

This module turns a human-facing request into one of the existing safe
OpenClaw actions. It does not publish ROS2 topics directly. The selected
script handles the ROS2 side and gateway validation.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List

from .workspace import workspace_path

TOOLS_DIR = workspace_path('tools', 'openclaw')
DEFAULT_ROUTE = 'short_test_route'

QUERY_PATROL_FILTERS = {
    'occupied': {'occupied', '有人', '检测到人', '有人吗', '有没有人', 'person'},
    'empty': {'empty', '无人', '没人', '没有人', 'clear'},
    'uncertain': {'uncertain', '不确定', '模糊', '疑似'},
}

ROUTE_HINTS = [
    ('door_check_route', {'门口', 'door', '出入口', '入口'}),
    ('desk_check_route', {'桌', 'desk', '工位'}),
    ('office_demo_route', {'办公室', 'office', '演示', 'demo'}),
    ('short_test_route', {'短路线', 'short', 'test', '测试', '轻量'}),
]

INTENT_TO_SCRIPT = {
    'query_status': ('robot_status.sh', []),
    'query_latest_patrol': ('query_latest_patrol.sh', []),
    'generate_report': ('generate_report.sh', []),
    'systemd_status': ('systemd_status.sh', []),
    'trigger_patrol_once': ('trigger_patrol_once.sh', []),
    'run_route': ('run_route.sh', []),
    'stop_route': ('stop_route.sh', []),
    'pause_route': ('pause_route.sh', []),
    'get_dashboard_url': ('robot_status.sh', []),
}

SAFETY_HINTS = [
    'Do not suggest direct /cmd_vel control.',
    'Do not bypass the gateway or safety nodes.',
    'Use only the scripts and actions listed below.',
]


@dataclass(frozen=True)
class RoutedIntent:
    input_text: str
    normalized_text: str
    intent: str
    script: str
    script_args: List[str]
    route_name: str = ''
    patrol_filter: str = ''
    reason: str = ''

    def as_dict(self) -> Dict[str, Any]:
        return {
            'input_text': self.input_text,
            'normalized_text': self.normalized_text,
            'intent': self.intent,
            'script': self.script,
            'script_args': self.script_args,
            'route_name': self.route_name,
            'patrol_filter': self.patrol_filter,
            'reason': self.reason,
        }


def normalize_text(text: str) -> str:
    text = (text or '').strip().lower()
    text = re.sub(r'\s+', ' ', text)
    return text


def _contains_any(text: str, keywords: set[str]) -> bool:
    return any(keyword in text for keyword in keywords)


def detect_route_name(text: str) -> str:
    for route_name, keywords in ROUTE_HINTS:
        if _contains_any(text, keywords):
            return route_name
    return DEFAULT_ROUTE


def detect_patrol_filter(text: str) -> str:
    for filter_name, keywords in QUERY_PATROL_FILTERS.items():
        if _contains_any(text, keywords):
            return filter_name
    return ''


def detect_intent(text: str) -> RoutedIntent:
    raw = text or ''
    normalized = normalize_text(raw)

    if _contains_any(normalized, {'停止', 'stop', '停下', '结束', '终止', 'cancel'}):
        script, args = INTENT_TO_SCRIPT['stop_route']
        return RoutedIntent(raw, normalized, 'stop_route', script, args, reason='stop request')

    if _contains_any(normalized, {'暂停', 'pause', '等一下', '先停', '稍等'}):
        script, args = INTENT_TO_SCRIPT['pause_route']
        return RoutedIntent(raw, normalized, 'pause_route', script, args, reason='pause request')

    if _contains_any(normalized, {'systemd', '服务', '自启', '开机', '运行中', '还在运行'}):
        script, args = INTENT_TO_SCRIPT['systemd_status']
        return RoutedIntent(raw, normalized, 'systemd_status', script, args, reason='system status request')

    if _contains_any(normalized, {'dashboard', '面板', '网页', '地址'}):
        script, args = INTENT_TO_SCRIPT['get_dashboard_url']
        return RoutedIntent(raw, normalized, 'get_dashboard_url', script, args, reason='dashboard url request')

    if _contains_any(normalized, {'日报', '报告', '巡检情况', '今天巡检', '生成报告'}):
        script, args = INTENT_TO_SCRIPT['generate_report']
        return RoutedIntent(raw, normalized, 'generate_report', script, args, reason='daily report request')

    if _contains_any(normalized, {'最近有没有检测到人', '最近有没有人', '有没有检测到人', '有没有人', 'occupied', '检测到人'}):
        script, args = INTENT_TO_SCRIPT['query_latest_patrol']
        patrol_filter = detect_patrol_filter(normalized)
        if patrol_filter == 'occupied':
            args = ['--occupied']
        elif patrol_filter in ('empty', 'uncertain'):
            args = [f'--{patrol_filter}']
        return RoutedIntent(raw, normalized, 'query_latest_patrol', script, args, patrol_filter=patrol_filter, reason='latest patrol query')

    if _contains_any(normalized, {'门口', 'desk', '桌', '办公室', '路线', '巡逻', 'route', '去'}):
        route_name = detect_route_name(normalized)
        script, args = INTENT_TO_SCRIPT['run_route']
        return RoutedIntent(raw, normalized, 'run_route', script, [route_name, *args], route_name=route_name, reason='route request')

    if _contains_any(normalized, {'巡检一次', '巡检一下', '检查一次', '扫描一次', '触发巡检', 'patrol once'}):
        script, args = INTENT_TO_SCRIPT['trigger_patrol_once']
        return RoutedIntent(raw, normalized, 'trigger_patrol_once', script, args, reason='single patrol trigger')

    if _contains_any(normalized, {'状态', '运行状态', '现在状态', '小车现在', '机器人状态'}):
        script, args = INTENT_TO_SCRIPT['query_status']
        return RoutedIntent(raw, normalized, 'query_status', script, args, reason='status query')

    script, args = INTENT_TO_SCRIPT['query_status']
    return RoutedIntent(raw, normalized, 'query_status', script, args, reason='fallback to status query')


def build_skill_prompt() -> str:
    tools = [
        ('query_status', 'robot_status.sh', 'Read-only system status, dashboard URL, node/topic summary'),
        ('query_latest_patrol', 'query_latest_patrol.sh', 'Latest patrol evidence, occupied/empty/uncertain filters'),
        ('generate_report', 'generate_report.sh', 'Markdown daily report'),
        ('systemd_status', 'systemd_status.sh', 'Service state'),
        ('trigger_patrol_once', 'trigger_patrol_once.sh', 'Trigger one safe patrol scan'),
        ('run_route', 'run_route.sh <route_name>', 'Run a whitelisted route only'),
        ('stop_route', 'stop_route.sh', 'Stop current route safely'),
        ('pause_route', 'pause_route.sh', 'Pause route by stopping safely'),
        ('get_dashboard_url', 'robot_status.sh', 'Return dashboard URL'),
    ]

    lines = [
        'You are the OpenClaw assistant for the Raspbot ROS2 patrol robot.',
        'Follow the safety rules below and only call the approved local tools.',
        '',
        'Safety rules:',
        *[f'- {hint}' for hint in SAFETY_HINTS],
        '',
        'Available tools:',
    ]
    for action, tool, desc in tools:
        lines.append(f'- {action}: {tool} — {desc}')
    lines.extend([
        '',
        'Instruction flow:',
        '1. Classify the user request into one of the listed actions.',
        '2. If the request is a route request, only choose a whitelisted route name.',
        '3. If the request is ambiguous, fall back to query_status rather than inventing motion.',
        '4. Never output direct chassis speeds or bypass safety.',
    ])
    return '\n'.join(lines)


def script_path_for(intent: RoutedIntent) -> Path:
    return TOOLS_DIR / intent.script


def command_preview(intent: RoutedIntent) -> Dict[str, Any]:
    return {
        'action': intent.intent,
        'script': str(script_path_for(intent)),
        'script_args': intent.script_args,
        'route_name': intent.route_name,
        'patrol_filter': intent.patrol_filter,
        'reason': intent.reason,
    }
