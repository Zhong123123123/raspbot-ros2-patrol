#!/usr/bin/env python3
"""Agent Command Gateway Node — safety gateway between AI Agent and ROS2.

Validates incoming /agent/command messages against allowed_actions and
whitelist_routes, checks obstacle distance and task state, then forwards
valid commands to patrol/route topics.

Safety principles:
  - All actions must be in allowed_actions
  - All route names must be in whitelist_routes
  - direct_cmd_vel, shell, disable_safety are always rejected
  - Obstacle checks before movement
  - Concurrent patrol/route checks prevent double-trigger
  - All commands logged to JSONL
"""

from __future__ import annotations

import json
import math
import os
import time
from pathlib import Path
from typing import Optional

import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Range
from std_msgs.msg import Bool, String

from .agent_protocol import (
    ALL_VALID_ACTIONS,
    FORBIDDEN_ALWAYS,
    READ_ONLY_ACTIONS,
    build_result,
    format_log_entry,
    range_safety_reason,
    validate_command,
)
from .workspace import resolve_workspace_path


# ---------------------------------------------------------------------------
# ROS2 Node
# ---------------------------------------------------------------------------

class AgentCommandGatewayNode(Node):
    """Safety gateway between AI Agent commands and ROS2 execution layer."""

    def __init__(self):
        super().__init__('agent_command_gateway')

        # --- Parameters ---
        self.declare_parameter('agent_command_topic', '/agent/command')
        self.declare_parameter('agent_result_topic', '/agent/command_result')
        self.declare_parameter('patrol_trigger_topic', '/patrol/trigger')
        self.declare_parameter('patrol_result_topic', '/patrol/final_result')
        self.declare_parameter('patrol_status_topic', '/patrol/confirmed_status')
        self.declare_parameter('patrol_alert_topic', '/patrol/alert')
        self.declare_parameter('patrol_active_topic', '/patrol/active')
        self.declare_parameter('route_start_topic', '/route_patrol/start')
        self.declare_parameter('route_stop_topic', '/route_patrol/stop')
        self.declare_parameter('route_status_topic', 'route_patrol/status')
        self.declare_parameter('ultrasonic_topic', '/ultrasonic/front')
        self.declare_parameter('allowed_actions', list(ALL_VALID_ACTIONS))
        self.declare_parameter('forbidden_actions', list(FORBIDDEN_ALWAYS))
        self.declare_parameter('whitelist_routes', ['short_test_route', 'door_check_route',
                                                      'desk_check_route', 'office_demo_route'])
        self.declare_parameter('require_confirmation_for_routes', True)
        self.declare_parameter('max_route_duration_sec', 120.0)
        self.declare_parameter('min_obstacle_distance_m', 0.30)
        self.declare_parameter('ultrasonic_timeout_sec', 2.0)
        self.declare_parameter('patrol_timeout_sec', 30.0)
        self.declare_parameter('configured_route_name', 'short_test_route')
        self.declare_parameter('reject_if_obstacle_too_close', True)
        self.declare_parameter('reject_if_patrol_active', True)
        self.declare_parameter('reject_if_route_active', True)
        self.declare_parameter('dashboard_url', 'http://raspberrypi.local:8080')
        self.declare_parameter('log_agent_commands', True)
        self.declare_parameter('agent_log_path', '$RASPBOT_WS/data/agent/agent_commands.jsonl')

        # --- Load parameters ---
        self.allowed_actions = frozenset(
            self.get_parameter('allowed_actions').get_parameter_value().string_array_value
        )
        self.whitelist_routes = frozenset(
            self.get_parameter('whitelist_routes').get_parameter_value().string_array_value
        )
        self.min_obstacle_distance_m = float(
            self.get_parameter('min_obstacle_distance_m').get_parameter_value().double_value
        )
        self.ultrasonic_timeout_sec = max(
            0.1, float(self.get_parameter('ultrasonic_timeout_sec').get_parameter_value().double_value)
        )
        self.max_route_duration_sec = max(
            1.0, float(self.get_parameter('max_route_duration_sec').get_parameter_value().double_value)
        )
        self.require_confirmation_for_routes = bool(
            self.get_parameter('require_confirmation_for_routes').get_parameter_value().bool_value
        )
        self.configured_route_name = str(
            self.get_parameter('configured_route_name').get_parameter_value().string_value
        ).strip()
        self.reject_if_obstacle_too_close = bool(
            self.get_parameter('reject_if_obstacle_too_close').get_parameter_value().bool_value
        )
        self.reject_if_patrol_active = bool(
            self.get_parameter('reject_if_patrol_active').get_parameter_value().bool_value
        )
        self.reject_if_route_active = bool(
            self.get_parameter('reject_if_route_active').get_parameter_value().bool_value
        )
        self.patrol_timeout_sec = float(
            self.get_parameter('patrol_timeout_sec').get_parameter_value().double_value
        )
        self.dashboard_url = str(
            self.get_parameter('dashboard_url').get_parameter_value().string_value
        )
        self.log_enabled = bool(
            self.get_parameter('log_agent_commands').get_parameter_value().bool_value
        )
        self.log_path = str(resolve_workspace_path(
            str(self.get_parameter('agent_log_path').get_parameter_value().string_value)
        ))

        # --- State ---
        self._patrol_active = False
        self._route_active = False
        self._front_distance_m: Optional[float] = None
        self._pending_patrol_cmd: Optional[dict] = None
        self._pending_patrol_deadline: float = 0.0
        self._last_ultrasonic_time: float = 0.0
        self._route_started_at: float = 0.0
        self._active_route_cmd: Optional[dict] = None

        # --- Publishers ---
        # NOTE: patrol_behavior_node subscribes to /patrol/trigger as Bool
        # NOTE: route_patrol_node subscribes to route_patrol/start, route_patrol/stop as Bool
        self._result_pub = self.create_publisher(
            String, self.get_parameter('agent_result_topic').value, 10
        )
        self._patrol_trigger_pub = self.create_publisher(
            Bool, self.get_parameter('patrol_trigger_topic').value, 10
        )
        self._route_start_pub = self.create_publisher(
            Bool, self.get_parameter('route_start_topic').value, 10
        )
        self._route_stop_pub = self.create_publisher(
            Bool, self.get_parameter('route_stop_topic').value, 10
        )
        # route_patrol_node does NOT support pause natively;
        # pause_route action is mapped to stop for safety

        # --- Subscribers ---
        self._cmd_sub = self.create_subscription(
            String, self.get_parameter('agent_command_topic').value,
            self._on_command, 10
        )
        self._patrol_result_sub = self.create_subscription(
            String, self.get_parameter('patrol_result_topic').value,
            self._on_patrol_result, 10
        )
        self._patrol_status_sub = self.create_subscription(
            String, self.get_parameter('patrol_status_topic').value,
            self._on_patrol_status, 10
        )
        self._patrol_alert_sub = self.create_subscription(
            Bool, self.get_parameter('patrol_alert_topic').value,
            self._on_patrol_alert, 10
        )
        self._route_status_sub = self.create_subscription(
            String, self.get_parameter('route_status_topic').value,
            self._on_route_status, 10
        )
        self._ultrasonic_sub = self.create_subscription(
            Range, self.get_parameter('ultrasonic_topic').value,
            self._on_ultrasonic, 10
        )

        # Patrol active state
        self._patrol_active_sub = self.create_subscription(
            Bool, self.get_parameter('patrol_active_topic').value,
            self._on_patrol_active, 10
        )

        # --- Ensure log directory ---
        if self.log_enabled:
            Path(self.log_path).parent.mkdir(parents=True, exist_ok=True)

        # --- Timer for pending command timeout ---
        self._timer = self.create_timer(0.5, self._check_timeouts)

        self.get_logger().info(
            f'Agent Command Gateway started '
            f'(allowed_actions={len(self.allowed_actions)}, '
            f'whitelist_routes={len(self.whitelist_routes)})'
        )

    # ------------------------------------------------------------------
    # Subscriber callbacks
    # ------------------------------------------------------------------

    def _on_command(self, msg: String) -> None:
        """Handle incoming agent command."""
        self.get_logger().debug(f'Received command: {msg.data[:200]}')

        valid, cmd, reason = validate_command(
            msg.data, self.allowed_actions, self.whitelist_routes
        )

        if not valid:
            result = build_result(
                cmd or {}, accepted=False, executed=False,
                result='rejected', reason=reason or 'validation_failed'
            )
            self._publish_result(result)
            self._write_log(cmd or {}, accepted=False, executed=False,
                            result='rejected', reason=reason or 'validation_failed')
            self.get_logger().warn(f'Command rejected: {reason}')
            return

        action = cmd['action']
        params = cmd.get('params', {})

        # --- Read-only actions: execute immediately ---
        if action in READ_ONLY_ACTIONS:
            self._handle_readonly(cmd)
            return

        # --- Mutating actions: safety checks first ---
        if not self._safety_checks(cmd, action):
            return  # Safety check failed; result already published

        # --- Route execution ---
        if action == 'run_route':
            self._handle_run_route(cmd, params)
        elif action == 'stop_route':
            self._handle_stop_route(cmd)
        elif action == 'pause_route':
            self._handle_pause_route(cmd)
        elif action == 'trigger_patrol_once':
            self._handle_trigger_patrol(cmd)

    def _on_patrol_result(self, msg: String) -> None:
        """Receive patrol final result, forward to pending command."""
        if not self._pending_patrol_cmd:
            return
        try:
            data = json.loads(msg.data) if msg.data else {}
        except json.JSONDecodeError:
            data = {'raw': msg.data}

        cmd = self._pending_patrol_cmd
        self._pending_patrol_cmd = None

        result = build_result(
            cmd, accepted=True, executed=True,
            result='patrol_completed', data=data,
        )
        self._publish_result(result)
        self._write_log(cmd, accepted=True, executed=True,
                        result='patrol_completed')
        self.get_logger().info(
            f'Patrol completed for cmd={cmd.get("command_id")}: '
            f'decision={data.get("final_decision", "unknown")}'
        )

    def _on_patrol_status(self, msg: String) -> None:
        """Track confirmed patrol status."""
        self.get_logger().debug(f'Patrol status: {msg.data}')

    def _on_patrol_alert(self, msg: Bool) -> None:
        """Log patrol alerts."""
        self.get_logger().info(f'Patrol alert: {msg.data}')

    def _on_route_status(self, msg: String) -> None:
        """Track route execution status."""
        try:
            data = json.loads(msg.data) if msg.data else {}
        except json.JSONDecodeError:
            return

        state = data.get('state', '')
        if state == 'done':
            self._route_active = False
            self._active_route_cmd = None
        elif state == 'error':
            self._route_active = False
            self._active_route_cmd = None
        elif state in ('idle', ''):
            self._route_active = False
            self._active_route_cmd = None
        else:
            self._route_active = True

    def _on_ultrasonic(self, msg: Range) -> None:
        """Track front ultrasonic distance."""
        distance_m = float(msg.range)
        if math.isfinite(distance_m) and distance_m > 0.0:
            self._front_distance_m = distance_m
            self._last_ultrasonic_time = time.time()
        else:
            self._front_distance_m = None
            self._last_ultrasonic_time = 0.0

    def _on_patrol_active(self, msg: Bool) -> None:
        """Track patrol active state from /patrol/active topic."""
        self._patrol_active = bool(msg.data)

    # ------------------------------------------------------------------
    # Timer
    # ------------------------------------------------------------------

    def _check_timeouts(self) -> None:
        """Timeout check for pending patrol commands."""
        if self._pending_patrol_cmd and time.time() > self._pending_patrol_deadline:
            cmd = self._pending_patrol_cmd
            self._pending_patrol_cmd = None
            result = build_result(
                cmd, accepted=True, executed=False,
                result='timeout', reason=f'patrol did not complete within {self.patrol_timeout_sec}s',
            )
            self._publish_result(result)
            self._write_log(cmd, accepted=True, executed=False,
                            result='timeout')
            self.get_logger().warn(
                f'Patrol timeout for cmd={cmd.get("command_id")}'
            )
        if self._route_active and self._route_started_at:
            if time.time() - self._route_started_at > self.max_route_duration_sec:
                self._route_stop_pub.publish(Bool(data=True))
                self._route_active = False
                cmd = self._active_route_cmd or {}
                self._active_route_cmd = None
                result = build_result(
                    cmd, accepted=True, executed=True,
                    result='route_timeout', reason='max_route_duration_exceeded',
                )
                self._publish_result(result)
                self._write_log(cmd, accepted=True, executed=True,
                                result='route_timeout', reason='max_route_duration_exceeded')
                self.get_logger().error(
                    f'Route exceeded {self.max_route_duration_sec:.1f}s; stop command published'
                )

    # ------------------------------------------------------------------
    # Action handlers
    # ------------------------------------------------------------------

    def _handle_readonly(self, cmd: dict) -> None:
        """Handle read-only query commands."""
        action = cmd['action']
        if action == 'query_status':
            data = {
                'hostname': os.uname().nodename,
                'patrol_active': self._patrol_active,
                'route_active': self._route_active,
                'front_distance_m': self._front_distance_m,
            }
        elif action == 'get_dashboard_url':
            data = {'dashboard_url': self.dashboard_url}
        elif action == 'systemd_status':
            data = {'note': 'systemd_status requires shell script execution'}
        elif action == 'query_latest_patrol':
            data = {'note': 'query_latest_patrol requires shell script execution'}
        elif action == 'generate_report':
            data = {'note': 'generate_report requires shell script execution'}
        else:
            data = {}

        result = build_result(
            cmd, accepted=True, executed=True,
            result='ok', data=data,
        )
        self._publish_result(result)
        self._write_log(cmd, accepted=True, executed=True, result='ok')
        self.get_logger().info(f'Read-only action: {action}')

    def _handle_trigger_patrol(self, cmd: dict) -> None:
        """Trigger a single patrol scan.

        The existing patrol_behavior_node subscribes to /patrol/trigger as
        std_msgs/Bool — a True value triggers one scan cycle.
        """
        self._patrol_trigger_pub.publish(Bool(data=True))
        self._pending_patrol_cmd = cmd
        self._pending_patrol_deadline = time.time() + self.patrol_timeout_sec

        # Acknowledge immediately
        ack = build_result(
            cmd, accepted=True, executed=True,
            result='patrol_triggered', data={'status': 'waiting_for_result'},
        )
        self._publish_result(ack)
        self._write_log(cmd, accepted=True, executed=True, result='patrol_triggered')
        self.get_logger().info(
            f'Patrol triggered by cmd={cmd.get("command_id")}'
        )

    def _handle_run_route(self, cmd: dict, params: dict) -> None:
        """Execute a whitelisted route.

        The existing route_patrol_node subscribes to route_patrol/start as
        std_msgs/Bool — a True value starts the pre-configured route.
        NOTE: route_patrol_node uses its own hardcoded route from config;
        the route_name parameter is validated but the actual route executed
        depends on route_patrol_node's configuration.
        """
        route_name = params.get('route_name', '')
        self._route_start_pub.publish(Bool(data=True))
        self._route_active = True
        self._route_started_at = time.time()
        self._active_route_cmd = cmd

        result = build_result(
            cmd, accepted=True, executed=True,
            result='route_started', data={
                'requested_route_name': route_name,
                'executed_route_name': self.configured_route_name or 'route_patrol_configured_route',
            },
        )
        self._publish_result(result)
        self._write_log(cmd, accepted=True, executed=True,
                        result='route_started')
        self.get_logger().info(
            f'Route started: {route_name} (cmd={cmd.get("command_id")})'
        )

    def _handle_stop_route(self, cmd: dict) -> None:
        """Stop current route.

        The existing route_patrol_node subscribes to route_patrol/stop as
        std_msgs/Bool — a True value triggers immediate stop.
        """
        self._route_stop_pub.publish(Bool(data=True))
        self._route_active = False
        self._active_route_cmd = None

        result = build_result(
            cmd, accepted=True, executed=True, result='route_stopped',
        )
        self._publish_result(result)
        self._write_log(cmd, accepted=True, executed=True, result='route_stopped')
        self.get_logger().info(f'Route stopped by cmd={cmd.get("command_id")}')

    def _handle_pause_route(self, cmd: dict) -> None:
        """Pause current route.

        NOTE: route_patrol_node does not natively support pause — we stop the
        route for safety. The route state is NOT preserved.
        """
        self._route_stop_pub.publish(Bool(data=True))
        self._route_active = False
        self._active_route_cmd = None

        result = build_result(
            cmd, accepted=True, executed=True,
            result='route_stopped',
            data={'note': 'pause mapped to stop (route_patrol_node lacks native pause)'},
        )
        self._publish_result(result)
        self._write_log(cmd, accepted=True, executed=True, result='route_stopped')
        self.get_logger().info(
            f'Route stopped (pause requested) by cmd={cmd.get("command_id")}'
        )

    # ------------------------------------------------------------------
    # Safety checks
    # ------------------------------------------------------------------

    def _safety_checks(self, cmd: dict, action: str) -> bool:
        """Run all safety checks. Returns True if safe to proceed."""
        # Check: patrol already active
        if (self.reject_if_patrol_active and self._patrol_active
                and action == 'trigger_patrol_once'):
            result = build_result(
                cmd, accepted=False, executed=False,
                result='rejected', reason='patrol_already_active',
            )
            self._publish_result(result)
            self._write_log(cmd, accepted=False, executed=False,
                            result='rejected', reason='patrol_already_active')
            self.get_logger().warn('Rejected trigger_patrol_once: patrol already active')
            return False

        # Check: route already active
        if (self.reject_if_route_active and self._route_active
                and action == 'run_route'):
            result = build_result(
                cmd, accepted=False, executed=False,
                result='rejected', reason='route_already_active',
            )
            self._publish_result(result)
            self._write_log(cmd, accepted=False, executed=False,
                            result='rejected', reason='route_already_active')
            self.get_logger().warn('Rejected run_route: route already active')
            return False

        if action == 'run_route' and self.require_confirmation_for_routes:
            if cmd.get('require_confirmation') is not True:
                result = build_result(
                    cmd, accepted=False, executed=False,
                    result='rejected', reason='route_confirmation_required',
                )
                self._publish_result(result)
                self._write_log(cmd, accepted=False, executed=False,
                                result='rejected', reason='route_confirmation_required')
                return False

        # A movement command must have a fresh, valid ultrasonic sample.  This
        # intentionally fails closed when the sensor node is unavailable.
        if self.reject_if_obstacle_too_close and action == 'run_route':
            reason = range_safety_reason(
                self._front_distance_m, self._last_ultrasonic_time,
                self.min_obstacle_distance_m, self.ultrasonic_timeout_sec,
            )
            if reason:
                data = {
                    'front_distance_m': self._front_distance_m,
                    'min_distance_m': self.min_obstacle_distance_m,
                    'ultrasonic_timeout_sec': self.ultrasonic_timeout_sec,
                }
                result = build_result(cmd, accepted=False, executed=False,
                                      result='rejected', reason=reason, data=data)
                self._publish_result(result)
                self._write_log(cmd, accepted=False, executed=False,
                                result='rejected', reason=reason)
                self.get_logger().warn(f'Rejected route command: {reason}')
                return False

        return True

    # ------------------------------------------------------------------
    # Output helpers
    # ------------------------------------------------------------------

    def _publish_result(self, result: dict) -> None:
        """Publish command result to /agent/command_result."""
        msg = String()
        msg.data = json.dumps(result)
        self._result_pub.publish(msg)

    def _write_log(self, cmd: dict, accepted: bool, executed: bool,
                   result: str, reason: str = '') -> None:
        """Write command to JSONL audit log."""
        if not self.log_enabled:
            return
        entry = format_log_entry(cmd, accepted, executed, result, reason)
        try:
            with open(self.log_path, 'a') as f:
                f.write(json.dumps(entry, ensure_ascii=False) + '\n')
        except OSError as exc:
            self.get_logger().error(f'Failed to write agent log: {exc}')


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main(args=None):
    rclpy.init(args=args)
    node = AgentCommandGatewayNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
