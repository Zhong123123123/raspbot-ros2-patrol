#!/usr/bin/env python3
"""Route patrol node — lightweight fixed-route mobile patrol with stop-and-scan.

Drives the robot through a YAML-configured sequence of actions (move, turn,
wait, stop, patrol), triggering existing patrol scans at waypoints.

No SLAM, no Nav2, no map — pure timed motion on a pre-defined route.
"""

from __future__ import annotations

import json
import time
from typing import List, Optional

import rclpy
from geometry_msgs.msg import Twist
from rclpy.node import Node
from sensor_msgs.msg import Range
from std_msgs.msg import Bool, String

from .route_logic import (
    RouteConfigError,
    build_status_json,
    parse_route,
    should_pause_for_obstacle,
)

# ---------------------------------------------------------------------------
#  Node
# ---------------------------------------------------------------------------

class RoutePatrolNode(Node):
    def __init__(self):
        super().__init__('raspbot_route_patrol')

        # --- parameters ---
        self.declare_parameter('enabled', True)
        self.declare_parameter('auto_start', False)
        self.declare_parameter('loop_route', False)
        self.declare_parameter('cmd_vel_topic', 'cmd_vel')
        self.declare_parameter('patrol_trigger_topic', 'patrol/trigger')
        self.declare_parameter('patrol_result_topic', 'patrol/final_result')
        self.declare_parameter('patrol_active_topic', 'patrol/active')
        self.declare_parameter('ultrasonic_topic', 'ultrasonic/front')
        self.declare_parameter('status_topic', 'route_patrol/status')
        self.declare_parameter('publish_rate_hz', 10.0)
        self.declare_parameter('stop_repeat_count', 5)
        self.declare_parameter('stop_settle_sec', 0.8)
        self.declare_parameter('default_linear_x', 0.06)
        self.declare_parameter('default_angular_z', 0.30)
        self.declare_parameter('obstacle_check_enabled', True)
        self.declare_parameter('obstacle_stop_distance_m', 0.25)
        self.declare_parameter('obstacle_resume_distance_m', 0.35)
        self.declare_parameter('patrol_timeout_sec', 15.0)
        self.declare_parameter('route', ['{"action":"stop"}'])

        self._load_params()

        # --- publishers ---
        self.cmd_vel_pub = self.create_publisher(Twist, self.cmd_vel_topic, 10)
        self.trigger_pub = self.create_publisher(Bool, self.patrol_trigger_topic, 10)
        self.status_pub = self.create_publisher(String, self.status_topic, 10)

        # --- subscribers ---
        self.create_subscription(
            Range, self.ultrasonic_topic, self._on_range, 10,
        )
        self.create_subscription(
            String, self.patrol_result_topic, self._on_patrol_result, 10,
        )
        self.create_subscription(
            Bool, self.patrol_active_topic, self._on_patrol_active, 10,
        )
        self.create_subscription(
            Bool, 'route_patrol/start', self._on_start, 10,
        )
        self.create_subscription(
            Bool, 'route_patrol/stop', self._on_stop_cmd, 10,
        )

        # --- state ---
        self.state: str = 'IDLE'
        self.route: List[dict] = []
        self.action_index: int = 0
        self._action_elapsed: float = 0.0
        self._stop_counter: int = 0
        self._patrol_start_time: float = 0.0
        self._patrol_active_seen: bool = False
        self._patrol_result: Optional[dict] = None
        self._obstacle_distance: Optional[float] = None
        self._pre_pause_state: str = ''
        self._pre_pause_elapsed: float = 0.0

        # --- timer ---
        dt = 1.0 / max(self.publish_rate_hz, 1.0)
        self.timer = self.create_timer(dt, self._tick)

        self.get_logger().info(
            'route patrol node started '
            f'(enabled={self.enabled}, auto_start={self.auto_start}, '
            f'route_actions={len(self.route) if self.route else "unloaded"}, '
            f'obstacle_check={self.obstacle_enabled})'
        )

    # ------------------------------------------------------------------
    #  Parameter loading
    # ------------------------------------------------------------------

    def _load_params(self):
        self.enabled = bool(self.get_parameter('enabled').value)
        self.auto_start = bool(self.get_parameter('auto_start').value)
        self.loop_route = bool(self.get_parameter('loop_route').value)
        self.cmd_vel_topic = str(self.get_parameter('cmd_vel_topic').value)
        self.patrol_trigger_topic = str(self.get_parameter('patrol_trigger_topic').value)
        self.patrol_result_topic = str(self.get_parameter('patrol_result_topic').value)
        self.patrol_active_topic = str(self.get_parameter('patrol_active_topic').value)
        self.ultrasonic_topic = str(self.get_parameter('ultrasonic_topic').value)
        self.status_topic = str(self.get_parameter('status_topic').value)
        self.publish_rate_hz = max(1.0, float(self.get_parameter('publish_rate_hz').value))
        self.stop_repeat_count = max(1, int(self.get_parameter('stop_repeat_count').value))
        self.stop_settle_sec = max(0.0, float(self.get_parameter('stop_settle_sec').value))
        self.default_linear_x = float(self.get_parameter('default_linear_x').value)
        self.default_angular_z = float(self.get_parameter('default_angular_z').value)
        self.obstacle_enabled = bool(self.get_parameter('obstacle_check_enabled').value)
        self.obstacle_stop_m = float(self.get_parameter('obstacle_stop_distance_m').value)
        self.obstacle_resume_m = float(self.get_parameter('obstacle_resume_distance_m').value)
        self.patrol_timeout_sec = max(1.0, float(self.get_parameter('patrol_timeout_sec').value))

    # ------------------------------------------------------------------
    #  Subscriber callbacks
    # ------------------------------------------------------------------

    def _on_range(self, msg: Range):
        self._obstacle_distance = float(msg.range) if msg.range > 0 else None

    def _on_patrol_result(self, msg: String):
        try:
            self._patrol_result = json.loads(msg.data)
        except json.JSONDecodeError:
            self._patrol_result = {'final_decision': 'unknown', 'error': 'json_parse_failed'}

    def _on_patrol_active(self, msg: Bool):
        if msg.data:
            self._patrol_active_seen = True

    def _on_start(self, msg: Bool):
        if msg.data and self.state == 'IDLE':
            if not self.route:
                self._enter_state('LOAD_ROUTE')
            else:
                self._start_route()

    def _on_stop_cmd(self, msg: Bool):
        if msg.data and self.state not in ('IDLE', 'DONE', 'ERROR'):
            self.get_logger().info('stop command received')
            self._stop_robot()
            self._enter_state('DONE')

    # ------------------------------------------------------------------
    #  State machine tick
    # ------------------------------------------------------------------

    def _tick(self):
        if not self.enabled:
            return

        self._publish_status()

        # Obstacle check — only during movement states
        if self.obstacle_enabled and self.state in ('EXECUTING',):
            action = self._current_action()
            if action and action['action'] in ('move',):
                paused = should_pause_for_obstacle(
                    self._obstacle_distance,
                    False,  # not currently paused
                    self.obstacle_stop_m,
                    self.obstacle_resume_m,
                )
                if paused:
                    self.get_logger().warn(
                        f'obstacle detected at {self._obstacle_distance:.2f}m '
                        f'(threshold={self.obstacle_stop_m}m) — pausing'
                    )
                    self._pre_pause_state = self.state
                    self._pre_pause_elapsed = self._action_elapsed
                    self._stop_robot()
                    self._enter_state('OBSTACLE_PAUSED')
                    return
        elif self.state == 'OBSTACLE_PAUSED':
            if not should_pause_for_obstacle(
                self._obstacle_distance, True,
                self.obstacle_stop_m, self.obstacle_resume_m,
            ):
                self.get_logger().info(
                    f'obstacle cleared ({self._obstacle_distance:.2f}m) — resuming'
                )
                self._action_elapsed = self._pre_pause_elapsed
                self._enter_state(self._pre_pause_state)
                return

        # State handler
        handler = getattr(self, f'_handle_{self.state.lower()}', None)
        if handler:
            handler()

    def _enter_state(self, new_state: str):
        self.get_logger().debug(f'{self.state} → {new_state}')
        self.state = new_state

    def _current_action(self) -> Optional[dict]:
        if 0 <= self.action_index < len(self.route):
            return self.route[self.action_index]
        return None

    def _advance_or_done(self, dispatch_next: bool = False):
        self.action_index += 1
        if self.action_index >= len(self.route):
            if self.loop_route:
                self.action_index = 0
                self.get_logger().info('route loop — restarting from beginning')
            else:
                self._stop_robot()
                self._enter_state('DONE')
                self.get_logger().info('route complete')
                return
        self._action_elapsed = 0.0
        self._stop_counter = 0
        self._patrol_active_seen = False
        self._patrol_result = None
        self._patrol_start_time = 0.0
        if dispatch_next:
            next_action = self._current_action()
            if next_action:
                self.get_logger().info(
                    f'route advancing to {next_action["name"]} ({next_action["action"]})'
                )
                self._dispatch_action(next_action)

    # ------------------------------------------------------------------
    #  State handlers
    # ------------------------------------------------------------------

    def _handle_idle(self):
        if self.auto_start and self.route:
            self._start_route()
        # else: wait for /route_patrol/start

    def _handle_load_route(self):
        raw = self.get_parameter('route').value
        try:
            self.route = parse_route(raw)
        except RouteConfigError as exc:
            self.get_logger().error(f'invalid route: {exc}')
            self._enter_state('ERROR')
            return
        self.get_logger().info(f'route loaded: {len(self.route)} actions')
        self._start_route()

    def _start_route(self):
        self.action_index = 0
        self._action_elapsed = 0.0
        self._stop_counter = 0
        self._patrol_start_time = 0.0
        self._patrol_active_seen = False
        self._patrol_result = None
        self._pre_pause_state = ''
        action = self._current_action()
        if not action:
            self._enter_state('DONE')
            return
        self._dispatch_action(action)

    def _dispatch_action(self, action: dict):
        act = action['action']
        if act == 'stop':
            self._stop_robot()
            self._advance_or_done(dispatch_next=True)
        elif act in ('move', 'turn', 'wait'):
            self._enter_state('EXECUTING')
        elif act == 'patrol':
            self._enter_state('TRIGGER_PATROL')
        else:
            self.get_logger().error(f'unknown action: {act}')
            self._enter_state('ERROR')

    def _handle_executing(self):
        action = self._current_action()
        if not action:
            self._advance_or_done(dispatch_next=True)
            return

        dt = 1.0 / max(self.publish_rate_hz, 1.0)
        self._action_elapsed += dt

        act = action['action']
        duration = float(action.get('duration_sec', 1.0))

        if act == 'move':
            twist = Twist()
            twist.linear.x = float(action.get('linear_x', self.default_linear_x))
            self.cmd_vel_pub.publish(twist)
        elif act == 'turn':
            twist = Twist()
            twist.angular.z = float(action.get('angular_z', self.default_angular_z))
            self.cmd_vel_pub.publish(twist)
        # wait: do nothing, just let timer count

        if self._action_elapsed >= duration:
            # Action complete → force stop and settle
            if act in ('move', 'turn'):
                self._stop_counter = 0
                self._enter_state('STOP_AND_SETTLE')
            else:
                self._advance_or_done(dispatch_next=True)

    def _handle_stop_and_settle(self):
        self._stop_robot()
        self._stop_counter += 1
        if self._stop_counter >= self.stop_repeat_count:
            self._advance_or_done(dispatch_next=True)

    def _handle_trigger_patrol(self):
        """Send patrol trigger and wait for patrol result."""
        action = self._current_action()
        if not action:
            self._advance_or_done(dispatch_next=True)
            return

        if self._patrol_start_time <= 0.0:
            self.get_logger().info(
                f'triggering patrol at: {action["name"]}'
            )
            self._patrol_start_time = time.monotonic()
            self._patrol_result = None
            self.trigger_pub.publish(Bool(data=True))
            self._enter_state('WAIT_PATROL_RESULT')
            return

        self._enter_state('WAIT_PATROL_RESULT')

    def _handle_wait_patrol_result(self):
        elapsed = time.monotonic() - self._patrol_start_time

        if self._patrol_result is not None:
            decision = self._patrol_result.get('final_decision', '?')
            self.get_logger().info(
                f'patrol result received: {decision} '
                f'(waited {elapsed:.1f}s)'
            )
            self._advance_or_done(dispatch_next=True)
            return

        if elapsed > self.patrol_timeout_sec:
            self.get_logger().warn(
                f'patrol timeout after {self.patrol_timeout_sec}s — '
                f'skipping {self._current_action()["name"] if self._current_action() else "?"}'
            )
            self._patrol_result = {
                'final_decision': 'timeout',
                'error': 'patrol_timeout',
            }
            self._advance_or_done(dispatch_next=True)

    def _handle_obstacle_paused(self):
        # Just publish zeros and wait; _tick handles resume
        self._stop_robot()

    def _handle_done(self):
        self._stop_robot()
        if self.loop_route:
            self._start_route()

    def _handle_error(self):
        self._stop_robot()
        self.get_logger().error('route patrol in ERROR state')

    # ------------------------------------------------------------------
    #  Helpers
    # ------------------------------------------------------------------

    def _stop_robot(self):
        self.cmd_vel_pub.publish(Twist())

    def _publish_status(self):
        action = self._current_action()
        payload = build_status_json(
            state=self.state,
            action_index=self.action_index,
            action_name=action['name'] if action else '',
            action=action['action'] if action else '',
            route_done=(self.state == 'DONE'),
            blocked=(self.state == 'OBSTACLE_PAUSED'),
            last_patrol_result=self._patrol_result,
            error_msg='' if self.state != 'ERROR' else 'route error',
        )
        self.status_pub.publish(String(data=payload))

    # ------------------------------------------------------------------
    #  Lifecycle
    # ------------------------------------------------------------------

    def destroy_node(self):
        self._stop_robot()
        self.get_logger().info('route patrol node stopped — zero velocity sent')
        super().destroy_node()

    def __del__(self):
        try:
            self._stop_robot()
        except Exception:
            pass


def main(args=None):
    rclpy.init(args=args)
    node = RoutePatrolNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
