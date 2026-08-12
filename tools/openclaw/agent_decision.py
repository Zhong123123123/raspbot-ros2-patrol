#!/usr/bin/env python3
"""Agent Decision Helper — maps patrol results to allowed next actions.

Phase 6: Agent can select the next step based on patrol results,
but ONLY from allowed_actions. Cannot generate arbitrary chassis speeds.

Usage:
  python3 tools/openclaw/agent_decision.py --result occupied
  python3 tools/openclaw/agent_decision.py --result empty
  python3 tools/openclaw/agent_decision.py --result uncertain
  python3 tools/openclaw/agent_decision.py --result obstacle
  python3 tools/openclaw/agent_decision.py --route-state paused
"""

from __future__ import annotations

import argparse
import json
import sys

# Allowed action sets
ALLOWED_ACTIONS = frozenset({
    'query_status',
    'query_latest_patrol',
    'generate_report',
    'trigger_patrol_once',
    'run_route',
    'stop_route',
    'pause_route',
    'get_dashboard_url',
    'systemd_status',
})

# Decision strategies based on patrol result
DECISION_STRATEGIES = {
    'occupied': {
        'recommended': ['stop_route', 'query_latest_patrol', 'generate_report'],
        'allowed': ['stop_route', 'pause_route', 'query_latest_patrol',
                     'generate_report', 'query_status', 'get_dashboard_url'],
        'forbidden': ['trigger_patrol_once', 'run_route'],
        'message': (
            'Person detected. Recommended: stop movement and generate report. '
            'Continue moving is not advised.'
        ),
    },
    'empty': {
        'recommended': ['trigger_patrol_once', 'run_route'],
        'allowed': ['trigger_patrol_once', 'run_route', 'stop_route',
                     'pause_route', 'query_latest_patrol', 'generate_report',
                     'query_status', 'get_dashboard_url'],
        'forbidden': [],
        'message': (
            'Area is clear. Safe to continue patrol or execute next route step.'
        ),
    },
    'uncertain': {
        'recommended': ['trigger_patrol_once'],
        'allowed': ['trigger_patrol_once', 'stop_route', 'pause_route',
                     'query_latest_patrol', 'generate_report',
                     'query_status', 'get_dashboard_url'],
        'forbidden': ['run_route'],
        'message': (
            'Detection uncertain. Recommended: retry patrol scan once before '
            'continuing movement. Do not start new routes.'
        ),
    },
    'obstacle': {
        'recommended': ['pause_route'],
        'allowed': ['pause_route', 'stop_route', 'query_status',
                     'get_dashboard_url', 'query_latest_patrol'],
        'forbidden': ['trigger_patrol_once', 'run_route'],
        'message': (
            'Obstacle detected. Movement blocked. Wait or stop route.'
        ),
    },
    'route_completed': {
        'recommended': ['generate_report', 'trigger_patrol_once'],
        'allowed': ['generate_report', 'trigger_patrol_once', 'run_route',
                     'query_status', 'get_dashboard_url', 'query_latest_patrol'],
        'forbidden': ['pause_route'],
        'message': (
            'Route completed successfully. Ready for next task.'
        ),
    },
    'stopped': {
        'recommended': ['query_status'],
        'allowed': ['query_status', 'trigger_patrol_once', 'run_route',
                     'get_dashboard_url', 'query_latest_patrol',
                     'generate_report'],
        'forbidden': ['pause_route'],
        'message': (
            'Robot is stopped. Safe to issue new commands.'
        ),
    },
    'paused': {
        'recommended': ['stop_route'],
        'allowed': ['stop_route', 'pause_route',
                     'query_status', 'get_dashboard_url'],
        'forbidden': ['trigger_patrol_once', 'run_route'],
        'message': (
            'Route is paused. Either stop completely or wait for obstacle to clear.'
        ),
    },
}


def get_decision(result_type: str, current_route: str = '') -> dict:
    """Return decision guidance for a given patrol result type.

    Args:
        result_type: One of occupied, empty, uncertain, obstacle,
                     route_completed, stopped, paused.
        current_route: Optional current route name for context.

    Returns:
        Dict with recommended, allowed, forbidden actions and message.
    """
    strategy = DECISION_STRATEGIES.get(result_type)
    if strategy is None:
        return {
            'result_type': result_type,
            'error': f'Unknown result type: {result_type!r}. '
                     f'Valid types: {sorted(DECISION_STRATEGIES.keys())!r}',
            'recommended': ['query_status'],
            'allowed': ['query_status', 'get_dashboard_url'],
            'forbidden': list(ALLOWED_ACTIONS - {'query_status', 'get_dashboard_url'}),
            'message': 'Unknown result type. Only safe read-only actions allowed.',
        }

    decision = dict(strategy)
    decision['result_type'] = result_type
    if current_route:
        decision['current_route'] = current_route

    # Enforce: all recommended/allowed MUST be in ALLOWED_ACTIONS
    decision['recommended'] = [
        a for a in decision['recommended'] if a in ALLOWED_ACTIONS
    ]
    decision['allowed'] = [
        a for a in decision['allowed'] if a in ALLOWED_ACTIONS
    ]

    return decision


def map_to_script(action: str) -> str:
    """Map an action name to its script path."""
    mapping = {
        'query_status': 'tools/openclaw/robot_status.sh',
        'query_latest_patrol': 'tools/openclaw/query_latest_patrol.sh',
        'generate_report': 'tools/openclaw/generate_report.sh',
        'trigger_patrol_once': 'tools/openclaw/trigger_patrol_once.sh',
        'run_route': 'tools/openclaw/run_route.sh',
        'stop_route': 'tools/openclaw/stop_route.sh',
        'pause_route': 'tools/openclaw/pause_route.sh',
        'get_dashboard_url': 'tools/openclaw/robot_status.sh',
        'systemd_status': 'tools/openclaw/systemd_status.sh',
    }
    return mapping.get(action, '')


def main():
    parser = argparse.ArgumentParser(
        description='Agent Decision Helper — map patrol results to allowed next actions'
    )
    parser.add_argument(
        '--result', '-r',
        required=True,
        choices=sorted(DECISION_STRATEGIES.keys()),
        help='Patrol result type',
    )
    parser.add_argument(
        '--route', default='',
        help='Current route name for context (optional)',
    )
    parser.add_argument(
        '--json', action='store_true',
        help='Output as JSON',
    )
    parser.add_argument(
        '--scripts', action='store_true',
        help='Show script paths for recommended actions',
    )
    args = parser.parse_args()

    decision = get_decision(args.result, args.route)

    if args.json:
        if args.scripts:
            decision['script_paths'] = {
                a: map_to_script(a)
                for a in decision.get('recommended', [])
            }
        print(json.dumps(decision, indent=2, ensure_ascii=False))
    else:
        print(f"Result: {decision['result_type']}")
        print(f"Message: {decision.get('message', '')}")
        print()
        print(f"Recommended: {', '.join(decision.get('recommended', []))}")
        print(f"Allowed:     {', '.join(decision.get('allowed', []))}")
        print(f"Forbidden:   {', '.join(decision.get('forbidden', []))}")
        if args.scripts:
            print()
            print("Script paths for recommended actions:")
            for a in decision.get('recommended', []):
                print(f"  {a}: {map_to_script(a)}")

    # Exit code: 0 if any movement action is allowed, 1 if only read-only
    has_movement = any(
        a in ('trigger_patrol_once', 'run_route')
        for a in decision.get('allowed', [])
    )
    return 0 if has_movement else 1


if __name__ == '__main__':
    raise SystemExit(main())
