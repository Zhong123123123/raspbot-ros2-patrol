"""ROS-independent route validation and status helpers."""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional


VALID_ACTIONS = frozenset({'move', 'turn', 'wait', 'stop', 'patrol'})


class RouteConfigError(ValueError):
    """Raised when a route entry is malformed."""


def validate_action(entry: dict, index: int) -> dict:
    """Validate one route entry and return a normalized copy."""
    if not isinstance(entry, dict):
        raise RouteConfigError(f'route[{index}] must be a dict, got {type(entry).__name__}')
    action = entry.get('action', '')
    if action not in VALID_ACTIONS:
        raise RouteConfigError(
            f'route[{index}].action must be one of {sorted(VALID_ACTIONS)}, got: {action!r}'
        )

    normalized: dict = {
        'name': str(entry.get('name', f'{action}_{index}')),
        'action': action,
        'index': index,
    }
    if action == 'move':
        normalized['linear_x'] = float(entry.get('linear_x', 0.06))
        normalized['duration_sec'] = float(entry.get('duration_sec', 1.0))
    elif action == 'turn':
        normalized['angular_z'] = float(entry.get('angular_z', 0.30))
        normalized['duration_sec'] = float(entry.get('duration_sec', 0.5))
    elif action == 'wait':
        normalized['duration_sec'] = float(entry.get('duration_sec', 0.5))
    return normalized


def parse_route(raw: list) -> List[dict]:
    """Parse and validate a raw YAML route list."""
    if not isinstance(raw, list):
        raise RouteConfigError(f'route must be a list, got {type(raw).__name__}')
    if not raw:
        raise RouteConfigError('route list is empty')

    parsed = []
    for index, entry in enumerate(raw):
        if isinstance(entry, str):
            try:
                entry = json.loads(entry)
            except json.JSONDecodeError as exc:
                raise RouteConfigError(f'route[{index}] is not valid JSON: {exc}') from exc
        parsed.append(validate_action(entry, index))
    return parsed


def should_pause_for_obstacle(
    distance_m: Optional[float],
    currently_paused: bool,
    stop_threshold_m: float,
    resume_threshold_m: float,
) -> bool:
    """Apply hysteresis to a route-level obstacle pause decision."""
    if distance_m is None:
        return currently_paused
    if not currently_paused:
        return distance_m < stop_threshold_m
    return distance_m < resume_threshold_m


def build_status_json(
    state: str,
    action_index: int,
    action_name: str,
    action: str,
    route_done: bool,
    blocked: bool,
    last_patrol_result: Optional[dict] = None,
    error_msg: str = '',
) -> str:
    """Build the ``route_patrol/status`` JSON payload."""
    payload: Dict[str, Any] = {
        'state': state,
        'action_index': action_index,
        'action_name': action_name,
        'action': action,
        'route_done': route_done,
        'blocked': blocked,
        'last_patrol_result': last_patrol_result,
        'last_final_decision': last_patrol_result.get('final_decision') if last_patrol_result else None,
        'error_msg': error_msg,
    }
    return json.dumps(payload, ensure_ascii=False)
