from typing import Optional

import rclpy
from geometry_msgs.msg import Twist
from rcl_interfaces.msg import SetParametersResult
from rclpy.node import Node
from std_msgs.msg import Bool, Int32MultiArray


class IrObstacleAvoidNode(Node):
    def __init__(self):
        super().__init__('raspbot_ir_obstacle_avoid')
        self.declare_parameter('obstacle_topic', 'ir_obstacle')
        self.declare_parameter('ultrasonic_override_topic', 'safety_override_active')
        self.declare_parameter('enabled', True)
        self.declare_parameter('left_enabled', False)
        self.declare_parameter('right_enabled', True)
        self.declare_parameter('left_detect_value', 1)
        self.declare_parameter('right_detect_value', 1)
        self.declare_parameter('reverse_speed', -0.08)
        self.declare_parameter('reverse_time', 0.20)
        self.declare_parameter('turn_angular', 1.0)
        self.declare_parameter('turn_time', 0.35)
        self.declare_parameter('forward_speed', 0.08)
        self.declare_parameter('forward_time', 0.18)
        self.declare_parameter('hold_stop', True)
        self.declare_parameter('clear_confirm_count', 3)
        self.declare_parameter('publish_rate', 20.0)
        self.declare_parameter('prefer_turn', 'alternate')
        self.declare_parameter('patrol_active_topic', 'patrol/active')
        self.declare_parameter('startup_grace_sec', 1.5)

        self.enabled = bool(self.get_parameter('enabled').value)
        self.left_enabled = bool(self.get_parameter('left_enabled').value)
        self.right_enabled = bool(self.get_parameter('right_enabled').value)
        self.left_detect_value = int(self.get_parameter('left_detect_value').value)
        self.right_detect_value = int(self.get_parameter('right_detect_value').value)
        self.reverse_speed = float(self.get_parameter('reverse_speed').value)
        self.reverse_time = float(self.get_parameter('reverse_time').value)
        self.turn_angular = float(self.get_parameter('turn_angular').value)
        self.turn_time = float(self.get_parameter('turn_time').value)
        self.forward_speed = float(self.get_parameter('forward_speed').value)
        self.forward_time = float(self.get_parameter('forward_time').value)
        self.hold_stop = bool(self.get_parameter('hold_stop').value)
        self.clear_confirm_count = max(1, int(self.get_parameter('clear_confirm_count').value))
        self.publish_rate = max(1.0, float(self.get_parameter('publish_rate').value))
        self.prefer_turn = self.normalize_turn_mode(self.get_parameter('prefer_turn').value)

        self.safety_pub = self.create_publisher(Twist, 'safety_cmd_vel', 10)
        self.override_pub = self.create_publisher(Bool, 'ir_safety_override_active', 10)
        self.create_subscription(
            Int32MultiArray,
            self.get_parameter('obstacle_topic').value,
            self.obstacle_callback,
            10,
        )
        self.create_subscription(
            Bool,
            self.get_parameter('ultrasonic_override_topic').value,
            self.ultrasonic_override_callback,
            10,
        )
        self.create_subscription(
            Bool,
            self.get_parameter('patrol_active_topic').value,
            self.patrol_active_callback,
            10,
        )
        self.timer = self.create_timer(1.0 / self.publish_rate, self.timer_callback)
        self.add_on_set_parameters_callback(self.on_set_parameters)

        self.ultrasonic_override_active = False
        self.patrol_active = False
        self.override_active = False
        self.state = 'idle'
        self.state_deadline: Optional[float] = None
        self.clear_counter = 0
        self.left_blocked = False
        self.right_blocked = False
        self.pending_turn_sign = 1.0
        self.last_turn_sign = -1.0
        self.startup_grace_sec = max(0.0, float(self.get_parameter('startup_grace_sec').value))
        self.startup_started_at = self.now_sec()

        self.publish_override(False)
        self.get_logger().info(
            f'ir obstacle avoid node started (left_enabled={self.left_enabled}, right_enabled={self.right_enabled}, startup_grace_sec={self.startup_grace_sec})'
        )

    def now_sec(self) -> float:
        return self.get_clock().now().nanoseconds / 1e9

    def normalize_turn_mode(self, value: str) -> str:
        value = str(value).strip().lower()
        if value not in ('alternate', 'left', 'right'):
            raise ValueError('prefer_turn must be alternate, left, or right')
        return value

    def on_set_parameters(self, params):
        try:
            for param in params:
                if param.name == 'enabled':
                    self.enabled = bool(param.value)
                elif param.name == 'left_enabled':
                    self.left_enabled = bool(param.value)
                elif param.name == 'right_enabled':
                    self.right_enabled = bool(param.value)
                elif param.name == 'left_detect_value':
                    self.left_detect_value = int(param.value)
                elif param.name == 'right_detect_value':
                    self.right_detect_value = int(param.value)
                elif param.name == 'reverse_speed':
                    self.reverse_speed = float(param.value)
                elif param.name == 'reverse_time':
                    self.reverse_time = float(param.value)
                elif param.name == 'turn_angular':
                    self.turn_angular = float(param.value)
                elif param.name == 'turn_time':
                    self.turn_time = float(param.value)
                elif param.name == 'forward_speed':
                    self.forward_speed = float(param.value)
                elif param.name == 'forward_time':
                    self.forward_time = float(param.value)
                elif param.name == 'hold_stop':
                    self.hold_stop = bool(param.value)
                elif param.name == 'clear_confirm_count':
                    self.clear_confirm_count = max(1, int(param.value))
                elif param.name == 'publish_rate':
                    self.publish_rate = max(1.0, float(param.value))
                elif param.name == 'prefer_turn':
                    self.prefer_turn = self.normalize_turn_mode(param.value)
                elif param.name == 'startup_grace_sec':
                    self.startup_grace_sec = max(0.0, float(param.value))
                    self.startup_started_at = self.now_sec()
        except ValueError as exc:
            return SetParametersResult(successful=False, reason=str(exc))
        return SetParametersResult(successful=True)

    def make_twist(self, linear_x=0.0, angular_z=0.0):
        msg = Twist()
        msg.linear.x = linear_x
        msg.angular.z = angular_z
        return msg

    def publish_override(self, active: bool):
        msg = Bool()
        msg.data = bool(active)
        self.override_pub.publish(msg)

    def ultrasonic_override_callback(self, msg: Bool):
        self.ultrasonic_override_active = bool(msg.data)
        if self.ultrasonic_override_active and self.override_active:
            self.release_override('ultrasonic override active')

    def patrol_active_callback(self, msg: Bool):
        self.patrol_active = bool(msg.data)
        if self.patrol_active and self.override_active:
            self.release_override('patrol active')

    def obstacle_callback(self, msg: Int32MultiArray):
        data = list(msg.data)
        if len(data) < 2:
            return

        raw_left_blocked = int(data[0]) == self.left_detect_value
        raw_right_blocked = int(data[1]) == self.right_detect_value
        self.left_blocked = raw_left_blocked if self.left_enabled else False
        self.right_blocked = raw_right_blocked if self.right_enabled else False

        if self.now_sec() - self.startup_started_at < self.startup_grace_sec:
            return

        if not self.enabled or self.ultrasonic_override_active or self.patrol_active:
            return

        if self.override_active:
            if self.left_blocked or self.right_blocked:
                self.clear_counter = 0
            else:
                self.clear_counter += 1
            return

        if self.left_blocked or self.right_blocked:
            self.start_override()

    def choose_turn_sign(self) -> float:
        if self.left_blocked and not self.right_blocked:
            return -1.0
        if self.right_blocked and not self.left_blocked:
            return 1.0
        if self.prefer_turn == 'left':
            return 1.0
        if self.prefer_turn == 'right':
            return -1.0
        sign = -self.last_turn_sign
        self.last_turn_sign = sign
        return sign

    def start_override(self):
        self.override_active = True
        self.publish_override(True)
        self.clear_counter = 0
        self.pending_turn_sign = self.choose_turn_sign()
        now = self.now_sec()

        if self.left_blocked and self.right_blocked:
            self.state = 'reverse'
            self.state_deadline = now + self.reverse_time
            action = 'reverse then turn'
        elif self.left_blocked:
            self.state = 'turn'
            self.state_deadline = now + self.turn_time
            action = 'turn right'
        elif self.right_blocked:
            self.state = 'turn'
            self.state_deadline = now + self.turn_time
            action = 'turn left'
        else:
            self.state = 'idle'
            self.state_deadline = None
            action = 'idle'

        self.get_logger().warn(
            f'IR obstacle detected: left={self.left_blocked} right={self.right_blocked}, action={action}'
        )

    def release_override(self, reason: str = 'clear'):
        self.override_active = False
        self.publish_override(False)
        self.state = 'idle'
        self.state_deadline = None
        self.clear_counter = 0
        self.safety_pub.publish(self.make_twist(0.0, 0.0))
        self.get_logger().info(f'ir safety released: {reason}')

    def timer_callback(self):
        if not self.enabled:
            if self.override_active:
                self.release_override('disabled')
            return

        if self.now_sec() - self.startup_started_at < self.startup_grace_sec:
            return

        if self.ultrasonic_override_active or self.patrol_active:
            if self.override_active:
                self.release_override('patrol active' if self.patrol_active else 'ultrasonic override active')
            return

        if not self.override_active:
            return

        now = self.now_sec()
        if self.state == 'reverse':
            self.safety_pub.publish(self.make_twist(self.reverse_speed, 0.0))
            if self.state_deadline is not None and now >= self.state_deadline:
                self.state = 'turn'
                self.state_deadline = now + self.turn_time
            return

        if self.state == 'turn':
            self.safety_pub.publish(self.make_twist(0.0, self.turn_angular * self.pending_turn_sign))
            if self.state_deadline is not None and now >= self.state_deadline:
                if self.forward_time > 0.0:
                    self.state = 'forward'
                    self.state_deadline = now + self.forward_time
                elif self.hold_stop:
                    self.state = 'hold'
                    self.state_deadline = None
                else:
                    self.release_override('maneuver complete')
            return

        if self.state == 'forward':
            self.safety_pub.publish(self.make_twist(self.forward_speed, 0.0))
            if self.state_deadline is not None and now >= self.state_deadline:
                if self.hold_stop:
                    self.state = 'hold'
                    self.state_deadline = None
                else:
                    self.release_override('maneuver complete')
            return

        if self.state == 'hold':
            self.safety_pub.publish(self.make_twist(0.0, 0.0))
            if self.clear_counter >= self.clear_confirm_count:
                self.release_override('path clear')


def main(args=None):
    rclpy.init(args=args)
    node = IrObstacleAvoidNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    except RuntimeError as exc:
        if rclpy.ok():
            raise
        node.get_logger().debug(f'ignoring shutdown race in ir obstacle avoid node: {exc}')
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
