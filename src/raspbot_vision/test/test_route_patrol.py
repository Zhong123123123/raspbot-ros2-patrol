"""Unit tests for route_patrol_node pure functions."""

import pytest

# ---------------------------------------------------------------------------
#  validate_action
# ---------------------------------------------------------------------------

class TestValidateAction:
    def test_valid_move(self):
        from raspbot_vision.route_logic import validate_action
        a = validate_action({'action': 'move', 'linear_x': 0.06, 'duration_sec': 1.5}, 0)
        assert a['action'] == 'move'
        assert a['linear_x'] == 0.06
        assert a['duration_sec'] == 1.5

    def test_valid_turn(self):
        from raspbot_vision.route_logic import validate_action
        a = validate_action({'action': 'turn', 'angular_z': -0.3, 'duration_sec': 0.9}, 0)
        assert a['action'] == 'turn'
        assert a['angular_z'] == -0.3

    def test_valid_patrol(self):
        from raspbot_vision.route_logic import validate_action
        a = validate_action({'action': 'patrol', 'name': 'scan1'}, 0)
        assert a['action'] == 'patrol'
        assert a['name'] == 'scan1'

    def test_valid_stop(self):
        from raspbot_vision.route_logic import validate_action
        a = validate_action({'action': 'stop'}, 0)
        assert a['action'] == 'stop'

    def test_valid_wait(self):
        from raspbot_vision.route_logic import validate_action
        a = validate_action({'action': 'wait', 'duration_sec': 2.0}, 0)
        assert a['action'] == 'wait'
        assert a['duration_sec'] == 2.0

    def test_missing_action_key(self):
        from raspbot_vision.route_logic import RouteConfigError, validate_action
        with pytest.raises(RouteConfigError):
            validate_action({'name': 'bad'}, 0)

    def test_invalid_action_type(self):
        from raspbot_vision.route_logic import RouteConfigError, validate_action
        with pytest.raises(RouteConfigError):
            validate_action({'action': 'fly'}, 3)

    def test_empty_action_string(self):
        from raspbot_vision.route_logic import RouteConfigError, validate_action
        with pytest.raises(RouteConfigError):
            validate_action({'action': ''}, 0)

    def test_not_a_dict(self):
        from raspbot_vision.route_logic import RouteConfigError, validate_action
        with pytest.raises(RouteConfigError, match='dict'):
            validate_action('not a dict', 0)  # type: ignore

    def test_auto_generated_name(self):
        from raspbot_vision.route_logic import validate_action
        a = validate_action({'action': 'move'}, 5)
        assert a['name'] == 'move_5'  # fallback name from index

    def test_move_defaults(self):
        from raspbot_vision.route_logic import validate_action
        a = validate_action({'action': 'move'}, 0)
        assert a['linear_x'] == 0.06
        assert a['duration_sec'] == 1.0

    def test_turn_defaults(self):
        from raspbot_vision.route_logic import validate_action
        a = validate_action({'action': 'turn'}, 0)
        assert a['angular_z'] == 0.30
        assert a['duration_sec'] == 0.5

    def test_index_field_present(self):
        from raspbot_vision.route_logic import validate_action
        a = validate_action({'action': 'patrol'}, 42)
        assert a['index'] == 42


# ---------------------------------------------------------------------------
#  parse_route
# ---------------------------------------------------------------------------

class TestParseRoute:
    def test_valid_full_route(self):
        from raspbot_vision.route_logic import parse_route
        raw = [
            {'action': 'patrol', 'name': 'start'},
            {'action': 'move', 'linear_x': 0.06, 'duration_sec': 1.5},
            {'action': 'turn', 'angular_z': -0.3, 'duration_sec': 0.9},
            {'action': 'patrol', 'name': 'scan1'},
            {'action': 'wait', 'duration_sec': 1.0},
            {'action': 'stop'},
        ]
        route = parse_route(raw)
        assert len(route) == 6
        assert [a['action'] for a in route] == [
            'patrol', 'move', 'turn', 'patrol', 'wait', 'stop',
        ]

    def test_empty_list_raises(self):
        from raspbot_vision.route_logic import RouteConfigError, parse_route
        with pytest.raises(RouteConfigError, match='empty'):
            parse_route([])

    def test_not_a_list_raises(self):
        from raspbot_vision.route_logic import RouteConfigError, parse_route
        with pytest.raises(RouteConfigError, match='list'):
            parse_route({'action': 'move'})  # type: ignore

    def test_single_action_ok(self):
        from raspbot_vision.route_logic import parse_route
        route = parse_route([{'action': 'stop'}])
        assert len(route) == 1

    def test_invalid_action_in_list_raises(self):
        from raspbot_vision.route_logic import RouteConfigError, parse_route
        with pytest.raises(RouteConfigError):
            parse_route([{'action': 'move'}, {'action': 'bad'}])

    def test_all_valid_actions_accepted(self):
        from raspbot_vision.route_logic import parse_route
        for act in ['move', 'turn', 'wait', 'stop', 'patrol']:
            route = parse_route([{'action': act}])
            assert route[0]['action'] == act


# ---------------------------------------------------------------------------
#  should_pause_for_obstacle
# ---------------------------------------------------------------------------

class TestShouldPause:
    def test_no_distance_not_paused_returns_false(self):
        from raspbot_vision.route_logic import should_pause_for_obstacle
        assert should_pause_for_obstacle(None, False, 0.25, 0.35) is False

    def test_no_distance_while_paused_returns_true(self):
        from raspbot_vision.route_logic import should_pause_for_obstacle
        # Stays paused until we get a reading above resume threshold
        assert should_pause_for_obstacle(None, True, 0.25, 0.35) is True

    def test_below_stop_threshold_triggers_pause(self):
        from raspbot_vision.route_logic import should_pause_for_obstacle
        assert should_pause_for_obstacle(0.10, False, 0.25, 0.35) is True

    def test_above_stop_threshold_no_pause(self):
        from raspbot_vision.route_logic import should_pause_for_obstacle
        assert should_pause_for_obstacle(0.30, False, 0.25, 0.35) is False

    def test_below_resume_threshold_while_paused(self):
        from raspbot_vision.route_logic import should_pause_for_obstacle
        assert should_pause_for_obstacle(0.20, True, 0.25, 0.35) is True

    def test_above_resume_threshold_while_paused_clears(self):
        from raspbot_vision.route_logic import should_pause_for_obstacle
        assert should_pause_for_obstacle(0.50, True, 0.25, 0.35) is False

    def test_exactly_at_stop_threshold(self):
        from raspbot_vision.route_logic import should_pause_for_obstacle
        # 0.25 is NOT less than 0.25 — so no pause
        assert should_pause_for_obstacle(0.25, False, 0.25, 0.35) is False

    def test_exactly_at_resume_threshold(self):
        from raspbot_vision.route_logic import should_pause_for_obstacle
        # 0.35 is NOT less than 0.35 — so resume
        assert should_pause_for_obstacle(0.35, True, 0.25, 0.35) is False


# ---------------------------------------------------------------------------
#  build_status_json
# ---------------------------------------------------------------------------

class TestBuildStatusJson:
    def test_minimal_fields(self):
        import json

        from raspbot_vision.route_logic import build_status_json
        s = build_status_json('IDLE', 0, '', '', False, False)
        d = json.loads(s)
        assert d['state'] == 'IDLE'
        assert d['route_done'] is False
        assert d['last_patrol_result'] is None

    def test_with_patrol_result(self):
        import json

        from raspbot_vision.route_logic import build_status_json
        result = {'final_decision': 'occupied', 'detected': True}
        s = build_status_json('WAIT_PATROL_RESULT', 2, 'scan1', 'patrol',
                              False, False, last_patrol_result=result)
        d = json.loads(s)
        assert d['last_patrol_result']['detected'] is True
        assert d['last_final_decision'] == 'occupied'

    def test_error_state(self):
        import json

        from raspbot_vision.route_logic import build_status_json
        s = build_status_json('ERROR', 0, '', '', False, False,
                              error_msg='something broke')
        d = json.loads(s)
        assert d['error_msg'] == 'something broke'

    def test_done_state(self):
        import json

        from raspbot_vision.route_logic import build_status_json
        s = build_status_json('DONE', 6, '', '', True, False)
        d = json.loads(s)
        assert d['route_done'] is True

    def test_blocked_state(self):
        import json

        from raspbot_vision.route_logic import build_status_json
        s = build_status_json('OBSTACLE_PAUSED', 2, 'move_1', 'move',
                              False, True)
        d = json.loads(s)
        assert d['blocked'] is True
