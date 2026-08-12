import math
from typing import Optional

import rclpy
from geometry_msgs.msg import Twist
from rclpy.node import Node

from .yb_pcb_car import YB_Pcb_Car


class BaseDriverNode(Node):
    def __init__(self):
        super().__init__('raspbot_base_driver')
        self.declare_parameter('i2c_address', 0x16)
        self.declare_parameter('i2c_bus', 1)
        # Legacy compatibility parameters kept for older launch/config paths.
        # They do not change the current cmd_vel -> PWM mapping unless explicitly set.
        self.declare_parameter('max_linear_speed', 0.0)
        self.declare_parameter('wheel_radius', 0.0)
        self.declare_parameter('max_pwm', 100.0)
        self.declare_parameter('linear_gain', 70.0)
        self.declare_parameter('angular_gain', 45.0)
        self.declare_parameter('cmd_timeout', 0.5)
        self.declare_parameter('safety_timeout', 0.3)

        address = self.get_parameter('i2c_address').value
        i2c_bus = self.get_parameter('i2c_bus').value
        self.max_linear_speed = float(self.get_parameter('max_linear_speed').value)
        self.wheel_radius = float(self.get_parameter('wheel_radius').value)
        self.max_pwm = float(self.get_parameter('max_pwm').value)
        self.linear_gain = float(self.get_parameter('linear_gain').value)
        self.angular_gain = float(self.get_parameter('angular_gain').value)
        self.cmd_timeout = float(self.get_parameter('cmd_timeout').value)
        self.safety_timeout = float(self.get_parameter('safety_timeout').value)

        self.driver = YB_Pcb_Car(address=address, i2c_bus=i2c_bus)
        self.last_cmd_time: Optional[float] = None
        self.last_safety_cmd_time: Optional[float] = None

        self.create_subscription(Twist, 'cmd_vel', self.cmd_vel_callback, 10)
        self.create_subscription(Twist, 'safety_cmd_vel', self.safety_cmd_callback, 10)
        self.timer = self.create_timer(0.05, self.watchdog_callback)
        self.get_logger().info(
            'raspbot base driver started '
            f'(max_linear_speed={self.max_linear_speed}, wheel_radius={self.wheel_radius}, '
            f'max_pwm={self.max_pwm}, linear_gain={self.linear_gain}, angular_gain={self.angular_gain})'
        )

    def now_sec(self) -> float:
        return self.get_clock().now().nanoseconds / 1e9

    def apply_twist(self, msg: Twist):
        linear = float(msg.linear.x)
        angular = float(msg.angular.z)

        # Never let malformed ROS messages turn into a motor command.  In
        # particular, Python's min/max would clamp NaN to a rail value.
        if not math.isfinite(linear) or not math.isfinite(angular):
            self.get_logger().error(
                f'rejected non-finite Twist command: linear_x={linear!r}, angular_z={angular!r}'
            )
            self.driver.car_stop()
            return False

        left = linear * self.linear_gain - angular * self.angular_gain
        right = linear * self.linear_gain + angular * self.angular_gain
        left = max(-self.max_pwm, min(self.max_pwm, left))
        right = max(-self.max_pwm, min(self.max_pwm, right))

        self.driver.control_car(left, right)
        return True

    def safety_active(self, now_sec: Optional[float] = None) -> bool:
        if self.last_safety_cmd_time is None:
            return False
        if now_sec is None:
            now_sec = self.now_sec()
        return now_sec - self.last_safety_cmd_time <= self.safety_timeout

    def cmd_vel_callback(self, msg: Twist):
        now_sec = self.now_sec()
        self.last_cmd_time = now_sec
        if self.safety_active(now_sec):
            return
        self.apply_twist(msg)

    def safety_cmd_callback(self, msg: Twist):
        self.apply_twist(msg)
        self.last_safety_cmd_time = self.now_sec()

    def watchdog_callback(self):
        now_sec = self.now_sec()
        if self.safety_active(now_sec):
            return
        if self.last_cmd_time is None:
            return
        if now_sec - self.last_cmd_time > self.cmd_timeout:
            self.driver.car_stop()
            self.last_cmd_time = None

    def destroy_node(self):
        try:
            self.driver.car_stop()
        finally:
            super().destroy_node()


def main(args=None):
    rclpy.init(args=args)
    node = BaseDriverNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
