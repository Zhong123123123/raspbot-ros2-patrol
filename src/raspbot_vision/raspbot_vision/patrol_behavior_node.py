"""Patrol behavior node — orchestrates multi-angle gimbal scanning with
multi-round confirmation, timeout retry, and occupied hold alert.

=== State Machine (P3) ===

    IDLE
      ↓ patrol/trigger received
    STOP_ROBOT  (park the robot, short settle)
      ↓ stop_settle_sec
    WAIT_GIMBAL  (move to left / center / right)
      ↓ settle_time_sec
    WAIT_RESULT  (trigger person_detect, wait for result)   ← retries on timeout
      ↓ result received  OR  timeout & retries exhausted
    advance_after_result()
      ├─ more angles left  →  WAIT_GIMBAL  (loop)
      └─ all 3 done  →  publish round result → FEEDBACK
                          ↓ feedback_duration_sec
                          evaluate round history
                          ├─ confirmed occupied  →  OCCUPIED_HOLD  (long alert)
                          │                         ↓ occupied_hold_sec
                          │                         → IDLE
                          └─ not yet confirmed    → IDLE

=== Multi-round confirmation ===

Each patrol cycle (= one full left/center/right scan) produces a round result.
Round results are stored in a rolling history deque.

- When the last `confirm_occupied_rounds` consecutive rounds are "occupied",
  the node publishes confirmed_decision="occupied" and enters OCCUPIED_HOLD.
- When the last `confirm_empty_rounds` consecutive rounds are "empty",
  the node publishes confirmed_decision="empty".
- Otherwise confirmed_decision="none".

This prevents false positives from a single weak detection and false negatives
from a single camera glitch.

=== Timeout retry ===

If WAIT_RESULT times out, the node retries the same scan position up to
`uncertain_retry_count` times before recording a timeout result and moving on.
"""

from __future__ import annotations

import json
import time
from collections import deque
from datetime import datetime, timezone
from typing import Any, Deque, Dict, List, Optional, Tuple

import rclpy
from geometry_msgs.msg import Twist, Vector3
from rcl_interfaces.msg import SetParametersResult
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from std_msgs.msg import Bool, ColorRGBA, String, UInt16

from .patrol_logic import evaluate_round_history


class PatrolBehaviorNode(Node):
    def __init__(self):
        super().__init__('raspbot_patrol_behavior')
        self.declare_parameter('trigger_topic', 'patrol/trigger')
        self.declare_parameter('detection_result_topic', 'person_detection/result')
        self.declare_parameter('detection_trigger_topic', 'person_detection/trigger')
        self.declare_parameter('gimbal_command_topic', 'gimbal_cmd')
        self.declare_parameter('final_result_topic', 'patrol/final_result')
        self.declare_parameter('confirmed_topic', 'patrol/confirmed_status')
        self.declare_parameter('cmd_vel_topic', 'cmd_vel')
        self.declare_parameter('status_led_topic', 'status_led_cmd')
        self.declare_parameter('buzzer_topic', 'buzzer_beep_ms')
        self.declare_parameter('patrol_active_topic', 'patrol/active')
        self.declare_parameter('alert_topic', 'patrol/alert')
        self.declare_parameter('left_angle', 45.0)
        self.declare_parameter('center_angle', 90.0)
        self.declare_parameter('right_angle', 135.0)
        self.declare_parameter('tilt_angle', 105.0)
        self.declare_parameter('stop_settle_sec', 0.2)
        self.declare_parameter('settle_time_sec', 0.8)
        self.declare_parameter('detection_timeout_sec', 8.0)
        self.declare_parameter('feedback_duration_sec', 1.2)
        self.declare_parameter('busy_reject_warn_sec', 2.0)
        self.declare_parameter('occupied_min_positive_positions', 2)
        self.declare_parameter('occupied_min_confidence', 0.60)
        # P3: multi-round confirmation
        self.declare_parameter('confirm_occupied_rounds', 2)
        self.declare_parameter('confirm_empty_rounds', 3)
        self.declare_parameter('round_history_size', 10)
        # P3: occupied hold
        self.declare_parameter('occupied_hold_sec', 15.0)
        self.declare_parameter('occupied_hold_beep_ms', 200)
        # P3: timeout retry
        self.declare_parameter('uncertain_retry_count', 1)

        self._load_parameters()

        # --- publishers ---
        self.gimbal_pub = self.create_publisher(Vector3, self.gimbal_command_topic, 10)
        self.detect_trigger_pub = self.create_publisher(Bool, self.detection_trigger_topic, 10)
        self.final_result_pub = self.create_publisher(String, self.final_result_topic, 10)
        self.confirmed_pub = self.create_publisher(String, self.confirmed_topic, 10)
        self.alert_pub = self.create_publisher(Bool, self.alert_topic, 10)
        self.cmd_vel_pub = self.create_publisher(Twist, self.cmd_vel_topic, 10)
        self.status_led_pub = self.create_publisher(ColorRGBA, self.status_led_topic, 10)
        self.buzzer_pub = self.create_publisher(UInt16, self.buzzer_topic, 10)
        self.patrol_active_pub = self.create_publisher(Bool, self.patrol_active_topic, 10)

        # --- subscriptions ---
        self.create_subscription(Bool, self.trigger_topic, self.trigger_callback, 10)
        self.create_subscription(String, self.detection_result_topic, self.detection_result_callback, 10)
        self.add_on_set_parameters_callback(self.on_set_parameters)

        # --- state machine ---
        self.timer = self.create_timer(0.05, self.timer_callback)
        self.state: str = 'IDLE'
        self.state_deadline: float = 0.0

        # Per-cycle state
        self.current_patrol_id: Optional[str] = None
        self.current_scan_index: int = 0
        self.current_scan_position: Optional[str] = None
        self.scan_results: Dict[str, Any] = {}
        self.uncertain_retries_left: int = 0
        self.started_at_utc: Optional[str] = None
        self.last_busy_warn_time: float = 0.0

        # Multi-round state (persists across cycles)
        self.round_history: Deque[Tuple[str, Optional[str]]] = deque(maxlen=self.round_history_size)
        self.confirmed_decision: str = 'none'          # 'none' | 'occupied' | 'empty'
        self.confirmed_at_utc: Optional[str] = None
        self.confirmed_patrol_id: Optional[str] = None
        self.last_published_confirmed: Optional[str] = None  # avoid spamming same msg

        self.publish_patrol_active(False)
        self.get_logger().info(
            'patrol behavior node started (P3) — '
            f'confirm_occupied={self.confirm_occupied_rounds}, '
            f'confirm_empty={self.confirm_empty_rounds}, '
            f'hold={self.occupied_hold_sec}s, '
            f'retry={self.uncertain_retry_count}'
        )

    # ------------------------------------------------------------------
    #  Parameters
    # ------------------------------------------------------------------

    def _load_parameters(self):
        self.trigger_topic = str(self.get_parameter('trigger_topic').value)
        self.detection_result_topic = str(self.get_parameter('detection_result_topic').value)
        self.detection_trigger_topic = str(self.get_parameter('detection_trigger_topic').value)
        self.gimbal_command_topic = str(self.get_parameter('gimbal_command_topic').value)
        self.final_result_topic = str(self.get_parameter('final_result_topic').value)
        self.confirmed_topic = str(self.get_parameter('confirmed_topic').value)
        self.cmd_vel_topic = str(self.get_parameter('cmd_vel_topic').value)
        self.status_led_topic = str(self.get_parameter('status_led_topic').value)
        self.buzzer_topic = str(self.get_parameter('buzzer_topic').value)
        self.patrol_active_topic = str(self.get_parameter('patrol_active_topic').value)
        self.alert_topic = str(self.get_parameter('alert_topic').value)
        self.left_angle = float(self.get_parameter('left_angle').value)
        self.center_angle = float(self.get_parameter('center_angle').value)
        self.right_angle = float(self.get_parameter('right_angle').value)
        self.tilt_angle = float(self.get_parameter('tilt_angle').value)
        self.stop_settle_sec = max(0.0, float(self.get_parameter('stop_settle_sec').value))
        self.settle_time_sec = max(0.0, float(self.get_parameter('settle_time_sec').value))
        self.detection_timeout_sec = max(0.1, float(self.get_parameter('detection_timeout_sec').value))
        self.feedback_duration_sec = max(0.1, float(self.get_parameter('feedback_duration_sec').value))
        self.busy_reject_warn_sec = max(0.5, float(self.get_parameter('busy_reject_warn_sec').value))
        self.occupied_min_positive_positions = max(1, int(self.get_parameter('occupied_min_positive_positions').value))
        self.occupied_min_confidence = max(0.0, float(self.get_parameter('occupied_min_confidence').value))

        # P3: multi-round
        self.confirm_occupied_rounds = max(1, int(self.get_parameter('confirm_occupied_rounds').value))
        self.confirm_empty_rounds = max(1, int(self.get_parameter('confirm_empty_rounds').value))
        self.round_history_size = max(1, int(self.get_parameter('round_history_size').value))
        # Resize deque if needed (preserve existing entries)
        if hasattr(self, 'round_history'):
            old = list(self.round_history)
            self.round_history = deque(old, maxlen=self.round_history_size)

        # P3: occupied hold
        self.occupied_hold_sec = max(0.0, float(self.get_parameter('occupied_hold_sec').value))
        self.occupied_hold_beep_ms = max(0, int(self.get_parameter('occupied_hold_beep_ms').value))

        # P3: retry
        self.uncertain_retry_count = max(0, int(self.get_parameter('uncertain_retry_count').value))

    def on_set_parameters(self, params):
        for param in params:
            name = param.name
            if name in {'stop_settle_sec', 'settle_time_sec', 'feedback_duration_sec',
                         'busy_reject_warn_sec', 'occupied_min_confidence',
                         'occupied_hold_sec'} and float(param.value) < 0.0:
                return SetParametersResult(successful=False, reason=f'{name} must be >= 0')
            if name in {'detection_timeout_sec'} and float(param.value) <= 0.0:
                return SetParametersResult(successful=False, reason='detection_timeout_sec must be > 0')
            if name in {'occupied_min_positive_positions', 'confirm_occupied_rounds',
                         'confirm_empty_rounds', 'round_history_size',
                         'uncertain_retry_count'} and int(param.value) <= 0:
                return SetParametersResult(successful=False, reason=f'{name} must be > 0')
        self._load_parameters()
        return SetParametersResult(successful=True)

    # ------------------------------------------------------------------
    #  Timing helpers
    # ------------------------------------------------------------------

    @staticmethod
    def now_sec() -> float:
        return time.monotonic()

    @staticmethod
    def utc_now() -> str:
        return datetime.now(timezone.utc).isoformat()

    # ------------------------------------------------------------------
    #  Trigger & detection result callbacks
    # ------------------------------------------------------------------

    def trigger_callback(self, msg: Bool):
        if not msg.data:
            return
        if self.state != 'IDLE':
            now = self.now_sec()
            if now - self.last_busy_warn_time >= self.busy_reject_warn_sec:
                self.get_logger().warning(
                    f'patrol trigger ignored while busy in state={self.state}'
                )
                self.last_busy_warn_time = now
            return
        self.start_patrol()

    def detection_result_callback(self, msg: String):
        if self.state != 'WAIT_RESULT' or self.current_scan_position is None:
            return
        try:
            payload = json.loads(msg.data)
        except json.JSONDecodeError:
            self.get_logger().warning('invalid JSON on person_detection/result')
            return
        payload['scan_position'] = self.current_scan_position
        payload['patrol_id'] = self.current_patrol_id
        self.scan_results[self.current_scan_position] = payload
        self.get_logger().info(
            f'patrol {self.current_patrol_id} {self.current_scan_position} result: '
            f"detected={payload.get('detected')} "
            f"count={payload.get('person_count', 0)} "
            f"confidence={float(payload.get('max_confidence', 0.0)):.2f} "
            f"error={payload.get('error_msg', '')}"
        )
        self.uncertain_retries_left = 0  # clear retry counter on success
        self.advance_after_result()

    # ------------------------------------------------------------------
    #  State transitions
    # ------------------------------------------------------------------

    def start_patrol(self):
        self.current_patrol_id = datetime.now(timezone.utc).strftime('patrol_%Y%m%dT%H%M%S_%f')
        self.started_at_utc = self.utc_now()
        self.current_scan_index = 0
        self.current_scan_position = None
        self.scan_results = {}
        self.uncertain_retries_left = 0
        self.publish_patrol_active(True)
        self.publish_stop()
        self.publish_led(0.0, 0.0, 1.0)   # blue = patrol starting
        self.set_state('STOP_ROBOT', self.stop_settle_sec)
        self.get_logger().info(f'patrol started: {self.current_patrol_id}')

    def set_state(self, state: str, delay_sec: float = 0.0):
        self.state = state
        self.state_deadline = self.now_sec() + max(0.0, delay_sec)

    def begin_scan(self, index: int):
        self.current_scan_index = index
        self.current_scan_position = self.scan_order[index]
        angle = {
            'left': self.left_angle,
            'center': self.center_angle,
            'right': self.right_angle,
        }[self.current_scan_position]
        # Reset retry counter for this scan position
        self.uncertain_retries_left = self.uncertain_retry_count
        self.publish_stop()
        self.publish_gimbal(angle, self.tilt_angle)
        self.set_state('WAIT_GIMBAL', self.settle_time_sec)
        self.get_logger().info(
            f'patrol {self.current_patrol_id} scanning {self.current_scan_position} '
            f'angle={angle} (retries={self.uncertain_retries_left})'
        )

    def timer_callback(self):
        now = self.now_sec()
        if self.state == 'IDLE':
            return

        # -- STOP_ROBOT -> begin first scan --
        if self.state == 'STOP_ROBOT' and now >= self.state_deadline:
            self.begin_scan(self.current_scan_index)

        # -- WAIT_GIMBAL -> trigger detection --
        elif self.state == 'WAIT_GIMBAL' and now >= self.state_deadline:
            self.publish_detection_trigger()
            self.set_state('WAIT_RESULT', self.detection_timeout_sec)

        # -- WAIT_RESULT timeout -> retry or record timeout --
        elif self.state == 'WAIT_RESULT' and now >= self.state_deadline:
            if self.uncertain_retries_left > 0:
                self.uncertain_retries_left -= 1
                self.get_logger().warning(
                    f'patrol {self.current_patrol_id} {self.current_scan_position} '
                    f'timeout, retrying ({self.uncertain_retries_left} left)'
                )
                self.publish_detection_trigger()
                self.set_state('WAIT_RESULT', self.detection_timeout_sec)
            else:
                self.record_timeout_result()
                self.advance_after_result()

        # -- FEEDBACK done -> check multi-round history --
        elif self.state == 'FEEDBACK' and now >= self.state_deadline:
            self._on_feedback_done()

        # -- OCCUPIED_HOLD done -> back to IDLE --
        elif self.state == 'OCCUPIED_HOLD' and now >= self.state_deadline:
            self._on_hold_done()

    def _on_feedback_done(self):
        """Called after the per-round FEEDBACK phase ends.

        Evaluates round history and decides whether to enter OCCUPIED_HOLD
        or return to IDLE.
        """
        # Clear brief feedback LED
        self.publish_led(0.0, 0.0, 0.0)
        self.publish_gimbal(self.center_angle, self.tilt_angle)

        # Evaluate multi-round history
        self._evaluate_round_history()

        if self.confirmed_decision == 'occupied' and self.occupied_hold_sec > 0.0:
            self.get_logger().info(
                f'patrol confirmed OCCUPIED after '
                f'{self.confirm_occupied_rounds} consecutive rounds, '
                f'holding alert for {self.occupied_hold_sec}s'
            )
            self.publish_alert(True)
            self.publish_led(1.0, 0.0, 0.0)   # red during hold
            if self.occupied_hold_beep_ms > 0:
                self.publish_beep(self.occupied_hold_beep_ms)
            self.set_state('OCCUPIED_HOLD', self.occupied_hold_sec)
        else:
            self._return_to_idle('round evaluated')

    def _on_hold_done(self):
        """Called after OCCUPIED_HOLD expires — return to IDLE."""
        self.get_logger().info(
            f'occupied hold finished, returning to IDLE '
            f'(confirmed_decision={self.confirmed_decision})'
        )
        self.publish_led(0.0, 0.0, 0.0)
        self.publish_alert(False)
        self._return_to_idle('occupied hold done')

    def _return_to_idle(self, reason: str = ''):
        """Clean transition back to IDLE."""
        self.publish_patrol_active(False)
        self.state = 'IDLE'

    def advance_after_result(self):
        """Move to next scan angle, or finish the round."""
        if self.current_scan_index + 1 < len(self.scan_order):
            self.begin_scan(self.current_scan_index + 1)
            return

        # All angles done — build and publish round result
        self.publish_stop()
        final_payload = self.build_final_payload()
        msg = String()
        msg.data = json.dumps(final_payload, ensure_ascii=True)
        self.final_result_pub.publish(msg)

        # Append to round history
        decision = final_payload['final_decision']
        pid = final_payload['patrol_id']
        self.round_history.append((decision, pid))

        # Brief per-round feedback
        self.publish_feedback(final_payload)
        self.set_state('FEEDBACK', self.feedback_duration_sec)

    def record_timeout_result(self):
        self.scan_results[self.current_scan_position] = {
            'timestamp_utc': self.utc_now(),
            'patrol_id': self.current_patrol_id,
            'scan_position': self.current_scan_position,
            'detected': False,
            'person_count': 0,
            'max_confidence': 0.0,
            'mode': 'triggered',
            'camera_backend': '',
            'detector_backend': '',
            'error_msg': 'detection_timeout',
            'scan_positive_frames': 0,
            'scan_total_frames': 0,
        }
        self.get_logger().warning(
            f'patrol {self.current_patrol_id} {self.current_scan_position} '
            f'detection timeout (retries exhausted)'
        )

    # ------------------------------------------------------------------
    #  Multi-round confirmation evaluation
    # ------------------------------------------------------------------

    def _evaluate_round_history(self):
        """Check the round history deque for a confirmed decision.

        Updates self.confirmed_decision and self.confirmed_at_utc.
        """
        previous = self.confirmed_decision
        self.confirmed_decision = evaluate_round_history(
            list(self.round_history),
            self.confirm_occupied_rounds,
            self.confirm_empty_rounds,
        )

        # Track when the decision changed
        if self.confirmed_decision != previous:
            self.confirmed_at_utc = self.utc_now()
            self.confirmed_patrol_id = self.current_patrol_id
            self.get_logger().info(
                f'confirmed_decision changed: {previous} -> {self.confirmed_decision} '
                f'(rounds in history: {len(self.round_history)})'
            )

        self._publish_confirmed_status()

    def _publish_confirmed_status(self):
        """Publish the current confirmation state on /patrol/confirmed_status."""
        history = list(self.round_history)
        latest_round = history[-1][0] if history else 'none'

        # Count consecutive from end
        occupied_streak = 0
        empty_streak = 0
        for decision, _ in reversed(history):
            if decision == 'occupied':
                occupied_streak += 1
            else:
                break
        for decision, _ in reversed(history):
            if decision == 'empty':
                empty_streak += 1
            else:
                break

        payload = {
            'timestamp_utc': self.utc_now(),
            'confirmed_decision': self.confirmed_decision,
            'is_confirmed': self.confirmed_decision != 'none',
            'confirmed_at_utc': self.confirmed_at_utc or '',
            'confirmed_patrol_id': str(self.confirmed_patrol_id or ''),
            'latest_round_decision': latest_round,
            'latest_patrol_id': str(self.current_patrol_id or ''),
            'occupied_consecutive_rounds': occupied_streak,
            'occupied_rounds_required': self.confirm_occupied_rounds,
            'empty_consecutive_rounds': empty_streak,
            'empty_rounds_required': self.confirm_empty_rounds,
            'total_rounds_recorded': len(history),
            'state': self.state,
        }

        payload_json = json.dumps(payload, ensure_ascii=True)
        # Only publish if changed (avoid spamming the same message)
        if payload_json != self.last_published_confirmed:
            msg = String()
            msg.data = payload_json
            self.confirmed_pub.publish(msg)
            self.last_published_confirmed = payload_json

    # ------------------------------------------------------------------
    #  Round-level decision logic (unchanged from P2, kept for clarity)
    # ------------------------------------------------------------------

    @property
    def scan_order(self) -> List[str]:
        return ['left', 'center', 'right']

    def build_final_payload(self) -> Dict[str, Any]:
        results = [self.scan_results[pos] for pos in self.scan_order if pos in self.scan_results]
        occupied_positions = [item['scan_position'] for item in results if bool(item.get('detected', False))]
        positive_observation_count = len(occupied_positions)
        total_observation_count = len(results)
        max_person_count = max((int(item.get('person_count', 0)) for item in results), default=0)
        max_confidence = max((float(item.get('max_confidence', 0.0)) for item in results), default=0.0)
        camera_backends = sorted({str(item.get('camera_backend', '')) for item in results if item.get('camera_backend')})
        detector_backends = sorted({str(item.get('detector_backend', '')) for item in results if item.get('detector_backend')})
        errors = [f"{item.get('scan_position')}:{item.get('error_msg')}" for item in results if item.get('error_msg')]

        decision_reason = ''
        if positive_observation_count == 0:
            if errors:
                final_decision = 'uncertain'
                detected = False
                decision_reason = 'errors_present_without_positive_detection'
            else:
                final_decision = 'empty'
                detected = False
                decision_reason = 'all_scans_clear'
        else:
            strong_signal = (
                positive_observation_count >= self.occupied_min_positive_positions
                or max_confidence >= self.occupied_min_confidence
                or max_person_count >= 2
            )
            if strong_signal:
                final_decision = 'occupied'
                detected = True
                if positive_observation_count >= self.occupied_min_positive_positions:
                    decision_reason = 'multiple_positive_positions'
                elif max_person_count >= 2:
                    decision_reason = 'multi_person_single_position'
                else:
                    decision_reason = 'single_positive_high_confidence'
            else:
                final_decision = 'uncertain'
                detected = False
                decision_reason = 'single_weak_positive'

        return {
            'patrol_id': self.current_patrol_id,
            'started_at_utc': self.started_at_utc,
            'finished_at_utc': self.utc_now(),
            'final_decision': final_decision,
            'detected': detected,
            'max_person_count': max_person_count,
            'max_confidence': max_confidence,
            'occupied_positions': occupied_positions,
            'positive_observation_count': positive_observation_count,
            'total_observation_count': total_observation_count,
            'decision_reason': decision_reason,
            'camera_backend': ','.join(camera_backends),
            'detector_backend': ','.join(detector_backends),
            'mode': 'triggered_scan',
            'error_msg': '; '.join(errors),
            'observations': results,
        }

    # ------------------------------------------------------------------
    #  Hardware feedback helpers
    # ------------------------------------------------------------------

    def publish_gimbal(self, pan: float, tilt: float):
        msg = Vector3()
        msg.x = float(pan)
        msg.y = float(tilt)
        msg.z = 0.0
        self.gimbal_pub.publish(msg)

    def publish_alert(self, active: bool):
        msg = Bool()
        msg.data = bool(active)
        self.alert_pub.publish(msg)

    def publish_patrol_active(self, active: bool):
        msg = Bool()
        msg.data = bool(active)
        self.patrol_active_pub.publish(msg)

    def publish_detection_trigger(self):
        msg = Bool()
        msg.data = True
        self.detect_trigger_pub.publish(msg)

    def publish_stop(self):
        msg = Twist()
        msg.linear.x = 0.0
        msg.angular.z = 0.0
        self.cmd_vel_pub.publish(msg)

    def publish_led(self, red: float, green: float, blue: float):
        msg = ColorRGBA()
        msg.r = float(red)
        msg.g = float(green)
        msg.b = float(blue)
        msg.a = 1.0
        self.status_led_pub.publish(msg)

    def publish_beep(self, duration_ms: int):
        msg = UInt16()
        msg.data = int(duration_ms)
        self.buzzer_pub.publish(msg)

    def publish_feedback(self, final_payload):
        decision = final_payload['final_decision']
        if decision == 'occupied':
            self.publish_led(1.0, 0.0, 0.0)
            self.publish_beep(160)
        elif decision == 'uncertain':
            self.publish_led(1.0, 0.0, 1.0)
            self.publish_beep(100)
        else:
            self.publish_led(0.0, 0.0, 1.0)

    # ------------------------------------------------------------------
    #  Lifecycle
    # ------------------------------------------------------------------

    def destroy_node(self):
        try:
            self.publish_led(0.0, 0.0, 0.0)
        finally:
            super().destroy_node()


def main(args=None):
    rclpy.init(args=args)
    node = PatrolBehaviorNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    except ExternalShutdownException:
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
