"""Tests for agent_command_gateway_node — pure helpers and validation logic."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

# Ensure the package is importable
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from raspbot_vision.agent_protocol import (
    ALL_VALID_ACTIONS,
    FORBIDDEN_ALWAYS,
    READ_ONLY_ACTIONS,
    build_result,
    format_log_entry,
    range_safety_reason,
    validate_command,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SAMPLE_ALLOWED = frozenset({
    'query_status', 'query_latest_patrol', 'generate_report',
    'trigger_patrol_once', 'run_route', 'stop_route', 'pause_route',
    'get_dashboard_url', 'systemd_status',
})

SAMPLE_ROUTES = frozenset({
    'short_test_route', 'door_check_route', 'desk_check_route', 'office_demo_route',
})


def _cmd(action: str, params=None, source='openclaw', cmd_id='test_001') -> str:
    d = {'command_id': cmd_id, 'source': source, 'action': action, 'params': params or {}}
    return json.dumps(d)


# ---------------------------------------------------------------------------
# validate_command
# ---------------------------------------------------------------------------

class TestValidateCommand:
    """Validation of incoming command JSON."""

    # --- Success cases ---

    def test_valid_query_status(self):
        valid, cmd, reason = validate_command(
            _cmd('query_status'), SAMPLE_ALLOWED, SAMPLE_ROUTES
        )
        assert valid
        assert reason is None
        assert cmd['action'] == 'query_status'

    def test_valid_trigger_patrol(self):
        valid, cmd, reason = validate_command(
            _cmd('trigger_patrol_once'), SAMPLE_ALLOWED, SAMPLE_ROUTES
        )
        assert valid
        assert cmd['action'] == 'trigger_patrol_once'

    def test_valid_run_route(self):
        valid, cmd, reason = validate_command(
            _cmd('run_route', {'route_name': 'door_check_route'}),
            SAMPLE_ALLOWED, SAMPLE_ROUTES,
        )
        assert valid
        assert cmd['params']['route_name'] == 'door_check_route'

    def test_valid_stop_route(self):
        valid, cmd, reason = validate_command(
            _cmd('stop_route'), SAMPLE_ALLOWED, SAMPLE_ROUTES
        )
        assert valid

    def test_valid_pause_route(self):
        valid, cmd, reason = validate_command(
            _cmd('pause_route'), SAMPLE_ALLOWED, SAMPLE_ROUTES
        )
        assert valid

    def test_auto_generates_command_id(self):
        valid, cmd, reason = validate_command(
            json.dumps({'source': 'openclaw', 'action': 'query_status', 'params': {}}),
            SAMPLE_ALLOWED, SAMPLE_ROUTES,
        )
        assert valid
        assert 'command_id' in cmd
        assert cmd['command_id'].startswith('cmd_')

    def test_accepts_trusted_tool_source(self):
        valid, cmd, reason = validate_command(
            _cmd('query_status', source='trusted_tool'),
            SAMPLE_ALLOWED, SAMPLE_ROUTES,
        )
        assert valid

    def test_accepts_test_source(self):
        valid, cmd, reason = validate_command(
            _cmd('query_status', source='test'),
            SAMPLE_ALLOWED, SAMPLE_ROUTES,
        )
        assert valid

    # --- Rejection: JSON ---

    def test_invalid_json_rejected(self):
        valid, cmd, reason = validate_command('not json', SAMPLE_ALLOWED, SAMPLE_ROUTES)
        assert not valid
        assert 'invalid_json' in reason

    def test_not_a_dict_rejected(self):
        valid, cmd, reason = validate_command('[]', SAMPLE_ALLOWED, SAMPLE_ROUTES)
        assert not valid
        assert reason == 'not_a_dict'

    # --- Rejection: action ---

    def test_missing_action_rejected(self):
        valid, cmd, reason = validate_command(
            json.dumps({'source': 'openclaw'}), SAMPLE_ALLOWED, SAMPLE_ROUTES
        )
        assert not valid
        assert reason == 'missing_or_invalid_action'

    def test_empty_action_rejected(self):
        valid, cmd, reason = validate_command(
            _cmd('', source='openclaw'), SAMPLE_ALLOWED, SAMPLE_ROUTES
        )
        assert not valid
        assert reason == 'missing_or_invalid_action'

    def test_action_not_in_whitelist(self):
        valid, cmd, reason = validate_command(
            _cmd('launch_missiles'), SAMPLE_ALLOWED, SAMPLE_ROUTES
        )
        assert not valid
        assert 'action_not_allowed' in reason

    # --- Rejection: forbidden actions ---

    def test_direct_cmd_vel_rejected(self):
        valid, cmd, reason = validate_command(
            _cmd('direct_cmd_vel', {'linear_x': 1.0}),
            SAMPLE_ALLOWED, SAMPLE_ROUTES,
        )
        assert not valid
        assert reason == 'direct_cmd_vel_not_allowed'

    def test_shell_rejected(self):
        valid, cmd, reason = validate_command(
            _cmd('shell', {'command': 'ls'}),
            SAMPLE_ALLOWED, SAMPLE_ROUTES,
        )
        assert not valid
        assert reason == 'shell_not_allowed'

    def test_disable_safety_rejected(self):
        valid, cmd, reason = validate_command(
            _cmd('disable_safety'), SAMPLE_ALLOWED, SAMPLE_ROUTES
        )
        assert not valid
        assert reason == 'disable_safety_not_allowed'

    def test_modify_database_rejected(self):
        valid, cmd, reason = validate_command(
            _cmd('modify_database'), SAMPLE_ALLOWED, SAMPLE_ROUTES
        )
        assert not valid
        assert reason == 'modify_database_not_allowed'

    def test_stop_obstacle_avoid_rejected(self):
        valid, cmd, reason = validate_command(
            _cmd('stop_obstacle_avoid'), SAMPLE_ALLOWED, SAMPLE_ROUTES
        )
        assert not valid
        assert reason == 'stop_obstacle_avoid_not_allowed'

    def test_delete_logs_rejected(self):
        valid, cmd, reason = validate_command(
            _cmd('delete_logs'), SAMPLE_ALLOWED, SAMPLE_ROUTES
        )
        assert not valid
        assert reason == 'delete_logs_not_allowed'

    # --- Rejection: source ---

    def test_untrusted_source_rejected(self):
        valid, cmd, reason = validate_command(
            _cmd('query_status', source='hacker'),
            SAMPLE_ALLOWED, SAMPLE_ROUTES,
        )
        assert not valid
        assert 'untrusted_source' in reason

    # --- Rejection: route whitelist ---

    def test_non_whitelisted_route_rejected(self):
        valid, cmd, reason = validate_command(
            _cmd('run_route', {'route_name': 'secret_route'}),
            SAMPLE_ALLOWED, SAMPLE_ROUTES,
        )
        assert not valid
        assert 'route_not_whitelisted' in reason

    def test_missing_route_name_rejected(self):
        valid, cmd, reason = validate_command(
            _cmd('run_route', {}),
            SAMPLE_ALLOWED, SAMPLE_ROUTES,
        )
        assert not valid
        assert reason == 'missing_route_name'

    def test_route_params_not_dict_rejected(self):
        valid, cmd, reason = validate_command(
            _cmd('run_route', 'door_check_route'),
            SAMPLE_ALLOWED, SAMPLE_ROUTES,
        )
        assert not valid
        assert reason == 'params_must_be_dict'

    # --- All forbidden actions blocked regardless of whitelist ---

    @pytest.mark.parametrize('action', sorted(FORBIDDEN_ALWAYS))
    def test_every_forbidden_action_rejected(self, action):
        # Even if it were in allowed_actions, FORBIDDEN_ALWAYS takes priority
        big_allow = SAMPLE_ALLOWED | FORBIDDEN_ALWAYS
        valid, cmd, reason = validate_command(
            _cmd(action), big_allow, SAMPLE_ROUTES
        )
        assert not valid
        assert 'not_allowed' in reason


# ---------------------------------------------------------------------------
# build_result
# ---------------------------------------------------------------------------

class TestBuildResult:
    def test_accepted_result(self):
        cmd = {'command_id': 'test_001', 'action': 'query_status'}
        result = build_result(cmd, accepted=True, executed=True, result='ok')
        assert result['command_id'] == 'test_001'
        assert result['accepted'] is True
        assert result['executed'] is True
        assert result['result'] == 'ok'
        assert 'timestamp' in result

    def test_rejected_result_with_reason(self):
        cmd = {'command_id': 'test_002'}
        result = build_result(
            cmd, accepted=False, executed=False,
            result='rejected', reason='action_not_allowed',
        )
        assert result['accepted'] is False
        assert result['reason'] == 'action_not_allowed'

    def test_result_includes_data(self):
        cmd = {'command_id': 'test_003'}
        result = build_result(
            cmd, accepted=True, executed=True,
            result='ok', data={'key': 'value'},
        )
        assert result['data'] == {'key': 'value'}

    def test_missing_command_id_defaults_to_unknown(self):
        cmd = {}
        result = build_result(cmd, accepted=True, executed=True, result='ok')
        assert result['command_id'] == 'unknown'


class TestRangeSafety:
    def test_fresh_clear_range_is_accepted(self):
        assert range_safety_reason(0.8, 100.0, 0.3, 2.0, now=101.0) is None

    def test_missing_or_invalid_range_is_rejected(self):
        assert range_safety_reason(None, 0.0, 0.3, 2.0, now=101.0) == 'ultrasonic_unavailable'
        assert range_safety_reason(float('nan'), 100.0, 0.3, 2.0, now=101.0) == 'ultrasonic_unavailable'

    def test_stale_or_close_range_is_rejected(self):
        assert range_safety_reason(0.8, 90.0, 0.3, 2.0, now=101.0) == 'ultrasonic_stale'
        assert range_safety_reason(0.2, 100.0, 0.3, 2.0, now=101.0) == 'obstacle_too_close'


# ---------------------------------------------------------------------------
# format_log_entry
# ---------------------------------------------------------------------------

class TestFormatLogEntry:
    def test_log_entry_fields(self):
        cmd = {
            'command_id': 'test_001',
            'source': 'openclaw',
            'action': 'run_route',
            'params': {'route_name': 'door_check_route'},
        }
        entry = format_log_entry(cmd, accepted=True, executed=True, result='route_started')
        assert entry['command_id'] == 'test_001'
        assert entry['source'] == 'openclaw'
        assert entry['action'] == 'run_route'
        assert entry['params'] == {'route_name': 'door_check_route'}
        assert entry['accepted'] is True
        assert entry['executed'] is True
        assert entry['result'] == 'route_started'
        assert 'timestamp' in entry

    def test_log_entry_rejected(self):
        cmd = {'command_id': 'test_002', 'source': 'openclaw', 'action': 'shell', 'params': {}}
        entry = format_log_entry(cmd, accepted=False, executed=False,
                                 result='rejected', reason='shell_not_allowed')
        assert entry['accepted'] is False
        assert entry['result'] == 'rejected'
        assert entry['reason'] == 'shell_not_allowed'


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

class TestConstants:
    def test_forbidden_always_covers_plan_items(self):
        """Verify all 6 forbidden actions from the plan are present."""
        expected = {
            'direct_cmd_vel', 'shell', 'disable_safety',
            'modify_database', 'stop_obstacle_avoid', 'delete_logs',
        }
        assert expected == FORBIDDEN_ALWAYS

    def test_read_only_and_mutating_partition(self):
        """Read-only and mutating actions should be disjoint."""
        assert READ_ONLY_ACTIONS.isdisjoint(
            ALL_VALID_ACTIONS - READ_ONLY_ACTIONS
        )

    def test_no_forbidden_in_valid(self):
        """FORBIDDEN_ALWAYS should not be in ALL_VALID_ACTIONS."""
        assert FORBIDDEN_ALWAYS.isdisjoint(ALL_VALID_ACTIONS)


# ---------------------------------------------------------------------------
# Integration-style: JSON round-trip
# ---------------------------------------------------------------------------

class TestJsonRoundTrip:
    """Test that validated commands produce well-formed JSON results."""

    def test_full_round_trip_rejection(self):
        """Rejected command → valid JSON result."""
        raw = _cmd('direct_cmd_vel', {'linear_x': 1.0})
        valid, cmd, reason = validate_command(raw, SAMPLE_ALLOWED, SAMPLE_ROUTES)
        assert not valid
        result = build_result(
            cmd or {}, accepted=False, executed=False,
            result='rejected', reason=reason or 'unknown',
        )
        # Must serialize
        serialized = json.dumps(result)
        assert serialized
        # Round-trip
        parsed = json.loads(serialized)
        assert parsed['accepted'] is False
        assert 'direct_cmd_vel_not_allowed' in parsed['reason']

    def test_full_round_trip_accepted(self):
        """Accepted command → valid JSON result."""
        raw = _cmd('query_status')
        valid, cmd, reason = validate_command(raw, SAMPLE_ALLOWED, SAMPLE_ROUTES)
        assert valid
        result = build_result(cmd, accepted=True, executed=True, result='ok')
        serialized = json.dumps(result)
        parsed = json.loads(serialized)
        assert parsed['accepted'] is True
        assert parsed['command_id'] == 'test_001'
