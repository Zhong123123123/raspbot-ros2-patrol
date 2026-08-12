import math

import rclpy
from geometry_msgs.msg import Twist
from rcl_interfaces.msg import SetParametersResult
from rclpy.node import Node
from sensor_msgs.msg import Range
from std_msgs.msg import Bool


class ObstacleAvoidNode(Node):
    def __init__(self):
        super().__init__('raspbot_obstacle_avoid')
        self.declare_parameter('range_topic', 'ultrasonic/front')
        self.declare_parameter('stop_distance', 0.18)
        self.declare_parameter('clear_distance', 0.26)
        self.declare_parameter('reverse_speed', -0.10)
        self.declare_parameter('reverse_time', 0.35)
        self.declare_parameter('turn_angular', 1.1)
        self.declare_parameter('turn_time', 0.55)
        self.declare_parameter('hold_stop', True)
        self.declare_parameter('clear_confirm_count', 3)
        self.declare_parameter('turn_direction_mode', 'alternate')
        self.declare_parameter('enabled', True)
        self.declare_parameter('patrol_active_topic', 'patrol/active')

        self.stop_distance = float(self.get_parameter('stop_distance').value)
        self.clear_distance = float(self.get_parameter('clear_distance').value)
        self.reverse_speed = float(self.get_parameter('reverse_speed').value)
        self.reverse_time = float(self.get_parameter('reverse_time').value)
        self.turn_angular = float(self.get_parameter('turn_angular').value)
        self.turn_time = float(self.get_parameter('turn_time').value)
        self.hold_stop = bool(self.get_parameter('hold_stop').value)
        self.clear_confirm_count = max(1, int(self.get_parameter('clear_confirm_count').value))
        self.turn_direction_mode = str(self.get_parameter('turn_direction_mode').value)
        self.enabled = bool(self.get_parameter('enabled').value)

        self.safety_pub = self.create_publisher(Twist, 'safety_cmd_vel', 10)
        self.override_state_pub = self.create_publisher(Bool, 'safety_override_active', 10)
        self.range_sub = self.create_subscription(
            Range,
            self.get_parameter('range_topic').value,
            self.range_callback,
            10,
        )
        self.create_subscription(
            Bool,
            self.get_parameter('patrol_active_topic').value,
            self.patrol_active_callback,
            10,
        )
        self.timer = self.create_timer(0.05, self.timer_callback)
        self.add_on_set_parameters_callback(self.on_set_parameters)

        self.override_active = False
        self.patrol_active = False
        self.state = 'idle'
        self.state_deadline = None
        self.last_range = math.inf
        self.clear_counter = 0
        self.last_turn_sign = -1.0
        self.active_turn_sign = 1.0
        self.publish_override_state(False)
        self.get_logger().info('obstacle avoid node started')

    def now_sec(self):
        return self.get_clock().now().nanoseconds / 1e9

    def normalize_turn_mode(self, value: str) -> str:
        value = str(value).strip().lower()
        if value not in ('alternate', 'left', 'right'):
            raise ValueError('turn_direction_mode must be alternate, left, or right')
        return value

    def on_set_parameters(self, params):
        try:
            for param in params:
                if param.name == 'stop_distance':
                    self.stop_distance = float(param.value)
                elif param.name == 'clear_distance':
                    self.clear_distance = float(param.value)
                elif param.name == 'reverse_speed':
                    self.reverse_speed = float(param.value)
                elif param.name == 'reverse_time':
                    self.reverse_time = float(param.value)
                elif param.name == 'turn_angular':
                    self.turn_angular = float(param.value)
                elif param.name == 'turn_time':
                    self.turn_time = float(param.value)
                elif param.name == 'hold_stop':
                    self.hold_stop = bool(param.value)
                elif param.name == 'clear_confirm_count':
                    self.clear_confirm_count = max(1, int(param.value))
                elif param.name == 'turn_direction_mode':
                    self.turn_direction_mode = self.normalize_turn_mode(param.value)
                elif param.name == 'enabled':
                    self.enabled = bool(param.value)
        except ValueError as exc:
            return SetParametersResult(successful=False, reason=str(exc))
        return SetParametersResult(successful=True)

    def make_twist(self, linear_x=0.0, angular_z=0.0):
        msg = Twist()
        msg.linear.x = linear_x
        msg.angular.z = angular_z
        return msg

    def publish_override_state(self, active: bool):
        msg = Bool()
        msg.data = bool(active)
        self.override_state_pub.publish(msg)

    def select_turn_sign(self) -> float:
        mode = self.normalize_turn_mode(self.turn_direction_mode)
        if mode == 'left':
            sign = 1.0
        elif mode == 'right':
            sign = -1.0
        else:
            sign = -self.last_turn_sign
            self.last_turn_sign = sign
        return sign

    def start_override(self, distance: float):
        now = self.now_sec()
        self.override_active = True
        self.publish_override_state(True)
        self.state = 'reverse'
        self.state_deadline = now + self.reverse_time
        self.clear_counter = 0
        self.active_turn_sign = self.select_turn_sign()
        direction = 'left' if self.active_turn_sign > 0.0 else 'right'
        self.get_logger().warn(
            f'obstacle detected at {distance:.2f} m, safety takeover active, turning {direction}'
        )

    def release_override(self, reason: str = 'path clear'):
        self.override_active = False
        self.publish_override_state(False)
        self.state = 'idle'
        self.state_deadline = None
        self.clear_counter = 0
        self.safety_pub.publish(self.make_twist(0.0, 0.0))
        self.get_logger().info(f'{reason}, returning control to cmd_vel')

    def patrol_active_callback(self, msg: Bool):
        self.patrol_active = bool(msg.data)
        if self.patrol_active and self.override_active:
            self.release_override('patrol active')

    def range_callback(self, msg: Range):
        if not self.enabled or self.patrol_active:
            return

        distance = float(msg.range)
        if math.isfinite(distance) and distance > 0.0:
            self.last_range = distance
        else:
            self.last_range = math.inf

        if not self.override_active:
            if self.last_range <= self.stop_distance:
                self.start_override(self.last_range)
            return

        if self.last_range >= self.clear_distance:
            self.clear_counter += 1
        else:
            self.clear_counter = 0

    def timer_callback(self):
        if self.patrol_active:
            if self.override_active:
                self.release_override('patrol active')
            return

        if not self.enabled or not self.override_active:
            return

        now = self.now_sec()
        if self.state == 'reverse':
            self.safety_pub.publish(self.make_twist(self.reverse_speed, 0.0))
            if self.state_deadline is not None and now >= self.state_deadline:
                self.state = 'turn'
                self.state_deadline = now + self.turn_time
            return

        if self.state == 'turn':
            self.safety_pub.publish(self.make_twist(0.0, self.turn_angular * self.active_turn_sign))
            if self.state_deadline is not None and now >= self.state_deadline:
                self.state = 'hold' if self.hold_stop else 'idle'
                self.state_deadline = None
                if not self.hold_stop:
                    self.release_override()
            return

        if self.state == 'hold':
            self.safety_pub.publish(self.make_twist(0.0, 0.0))
            if self.clear_counter >= self.clear_confirm_count:
                self.release_override()


def main(args=None):
    rclpy.init(args=args)
    node = ObstacleAvoidNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    except RuntimeError as exc:
        if rclpy.ok():
            raise
        node.get_logger().debug(f'ignoring shutdown race in obstacle avoid node: {exc}')
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
