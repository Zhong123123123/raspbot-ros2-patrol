from typing import Optional

import rclpy
from geometry_msgs.msg import Twist
from rcl_interfaces.msg import SetParametersResult
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from std_msgs.msg import Int32MultiArray


class IrLineFollowNode(Node):
    def __init__(self):
        super().__init__('raspbot_ir_line_follow')
        self.declare_parameter('line_topic', 'line_tracker')
        self.declare_parameter('forward_speed', 0.12)
        self.declare_parameter('turn_angular', 0.7)
        self.declare_parameter('sharp_turn_angular', 1.1)
        self.declare_parameter('search_angular', 0.5)
        self.declare_parameter('lost_timeout', 0.5)
        self.declare_parameter('loop_hz', 20.0)
        self.declare_parameter('enabled', True)

        self.forward_speed = float(self.get_parameter('forward_speed').value)
        self.turn_angular = float(self.get_parameter('turn_angular').value)
        self.sharp_turn_angular = float(self.get_parameter('sharp_turn_angular').value)
        self.search_angular = float(self.get_parameter('search_angular').value)
        self.lost_timeout = float(self.get_parameter('lost_timeout').value)
        self.enabled = bool(self.get_parameter('enabled').value)
        loop_hz = max(2.0, float(self.get_parameter('loop_hz').value))

        self.cmd_pub = self.create_publisher(Twist, 'cmd_vel', 10)
        self.create_subscription(Int32MultiArray, self.get_parameter('line_topic').value, self.line_callback, 10)
        self.timer = self.create_timer(1.0 / loop_hz, self.timer_callback)
        self.add_on_set_parameters_callback(self.on_set_parameters)

        self.last_line = [0, 0, 0, 0]
        self.last_line_time: Optional[float] = None
        self.last_turn_sign = 1.0
        self.get_logger().info('IR line follow node started')

    def now_sec(self) -> float:
        return self.get_clock().now().nanoseconds / 1e9

    def on_set_parameters(self, params):
        for param in params:
            if param.name == 'forward_speed':
                self.forward_speed = float(param.value)
            elif param.name == 'turn_angular':
                self.turn_angular = float(param.value)
            elif param.name == 'sharp_turn_angular':
                self.sharp_turn_angular = float(param.value)
            elif param.name == 'search_angular':
                self.search_angular = float(param.value)
            elif param.name == 'lost_timeout':
                self.lost_timeout = float(param.value)
            elif param.name == 'enabled':
                self.enabled = bool(param.value)
        return SetParametersResult(successful=True)

    def make_twist(self, linear_x=0.0, angular_z=0.0):
        msg = Twist()
        msg.linear.x = float(linear_x)
        msg.angular.z = float(angular_z)
        return msg

    def line_callback(self, msg: Int32MultiArray):
        data = list(msg.data)
        if len(data) >= 4:
            self.last_line = [1 if int(v) else 0 for v in data[:4]]
            self.last_line_time = self.now_sec()

    def classify_command(self):
        x1, x2, x3, x4 = self.last_line
        total = x1 + x2 + x3 + x4
        if total == 0:
            return self.make_twist(0.0, self.search_angular * self.last_turn_sign)

        weights = [-3.0, -1.0, 1.0, 3.0]
        error = (x1 * weights[0] + x2 * weights[1] + x3 * weights[2] + x4 * weights[3]) / total

        if error <= -2.0:
            self.last_turn_sign = 1.0
            return self.make_twist(0.04, self.sharp_turn_angular)
        if error < -0.3:
            self.last_turn_sign = 1.0
            return self.make_twist(self.forward_speed * 0.6, self.turn_angular)
        if error >= 2.0:
            self.last_turn_sign = -1.0
            return self.make_twist(0.04, -self.sharp_turn_angular)
        if error > 0.3:
            self.last_turn_sign = -1.0
            return self.make_twist(self.forward_speed * 0.6, -self.turn_angular)
        return self.make_twist(self.forward_speed, 0.0)

    def timer_callback(self):
        if not self.enabled:
            return
        now = self.now_sec()
        if self.last_line_time is None or now - self.last_line_time > self.lost_timeout:
            self.cmd_pub.publish(self.make_twist(0.0, 0.0))
            return
        self.cmd_pub.publish(self.classify_command())


def main(args=None):
    rclpy.init(args=args)
    node = IrLineFollowNode()
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
