"""ROS-independent validation and safety helpers for the Agent gateway."""

from __future__ import annotations

import json
import math
import time
import uuid
from datetime import datetime, timezone
from typing import Optional

FORBIDDEN_ALWAYS = frozenset({
    'direct_cmd_vel',
    'shell',
    'disable_safety',
    'modify_database',
    'stop_obstacle_avoid',
    'delete_logs',
})

READ_ONLY_ACTIONS = frozenset({
    'query_status',
    'query_latest_patrol',
    'generate_report',
    'get_dashboard_url',
    'systemd_status',
})

MUTATING_ACTIONS = frozenset({
    'trigger_patrol_once',
    'run_route',
    'stop_route',
    'pause_route',
})

ALL_VALID_ACTIONS = READ_ONLY_ACTIONS | MUTATING_ACTIONS


def validate_command(
    raw: str,
    allowed_actions: frozenset,
    whitelist_routes: frozenset,
) -> tuple[bool, Optional[dict], Optional[str]]:
    """Validate and parse a raw command JSON string."""
    try:
        cmd = json.loads(raw)
    except json.JSONDecodeError as exc:
        return False, None, f'invalid_json: {exc}'
    if not isinstance(cmd, dict):
        return False, None, 'not_a_dict'

    action = cmd.get('action', '')
    if not action or not isinstance(action, str):
        return False, None, 'missing_or_invalid_action'
    source = cmd.get('source', '')
    if source not in ('openclaw', 'trusted_tool', 'test'):
        return False, None, f'untrusted_source: {source!r}'
    if action in FORBIDDEN_ALWAYS:
        return False, None, f'{action}_not_allowed'
    if action not in allowed_actions:
        return False, None, f'action_not_allowed: {action!r}'

    if action == 'run_route':
        params = cmd.get('params', {})
        if not isinstance(params, dict):
            return False, None, 'params_must_be_dict'
        route_name = params.get('route_name', '')
        if not route_name or not isinstance(route_name, str):
            return False, None, 'missing_route_name'
        if route_name not in whitelist_routes:
            return False, None, f'route_not_whitelisted: {route_name!r}'

    if not cmd.get('command_id'):
        cmd['command_id'] = (
            f'cmd_{datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")}_{uuid.uuid4().hex[:6]}'
        )
    cmd['_received_at'] = datetime.now(timezone.utc).isoformat()
    return True, cmd, None


def build_result(
    cmd: dict,
    accepted: bool,
    executed: bool,
    result: str,
    data: Optional[dict] = None,
    reason: str = '',
) -> dict:
    """Build a command result response dict."""
    return {
        'command_id': cmd.get('command_id', 'unknown'),
        'accepted': accepted,
        'executed': executed,
        'result': result,
        'data': data or {},
        'reason': reason,
        'timestamp': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
    }


def format_log_entry(
    cmd: dict,
    accepted: bool,
    executed: bool,
    result: str,
    reason: str = '',
) -> dict:
    """Build a JSONL log entry for agent command audit trail."""
    return {
        'timestamp': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
        'command_id': cmd.get('command_id', 'unknown'),
        'source': cmd.get('source', 'unknown'),
        'action': cmd.get('action', 'unknown'),
        'params': cmd.get('params', {}),
        'accepted': accepted,
        'executed': executed,
        'result': result,
        'reason': reason,
    }


def range_safety_reason(
    distance_m: Optional[float],
    received_at: float,
    min_distance_m: float,
    max_age_sec: float,
    *,
    now: Optional[float] = None,
) -> Optional[str]:
    """Return a rejection reason unless a range sample is fresh and safe."""
    if distance_m is None or not math.isfinite(distance_m) or distance_m <= 0.0:
        return 'ultrasonic_unavailable'
    if received_at <= 0.0 or (time.time() if now is None else now) - received_at > max_age_sec:
        return 'ultrasonic_stale'
    if distance_m < min_distance_m:
        return 'obstacle_too_close'
    return None
