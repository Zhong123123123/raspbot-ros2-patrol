import select
import sys
import termios
import tty

import rclpy
from geometry_msgs.msg import Twist
from rclpy.node import Node

MSG = """
Controls:
  w: forward
  s: back
  a: left turn
  d: right turn
  x: stop
  q: quit
"""


class TeleopKeyboardNode(Node):
    def __init__(self):
        super().__init__('raspbot_teleop_keyboard')
        self.declare_parameter('linear_speed', 0.20)
        self.declare_parameter('angular_speed', 0.80)
        self.linear_speed = float(self.get_parameter('linear_speed').value)
        self.angular_speed = float(self.get_parameter('angular_speed').value)
        self.publisher = self.create_publisher(Twist, 'cmd_vel', 10)
        self.get_logger().info(MSG)

    def publish_twist(self, linear_x: float, angular_z: float):
        msg = Twist()
        msg.linear.x = linear_x
        msg.angular.z = angular_z
        self.publisher.publish(msg)


def get_key(settings):
    tty.setraw(sys.stdin.fileno())
    rlist, _, _ = select.select([sys.stdin], [], [], 0.1)
    key = sys.stdin.read(1) if rlist else ''
    termios.tcsetattr(sys.stdin, termios.TCSADRAIN, settings)
    return key


def main(args=None):
    settings = termios.tcgetattr(sys.stdin)
    rclpy.init(args=args)
    node = TeleopKeyboardNode()
    try:
        while rclpy.ok():
            key = get_key(settings)
            if key == 'w':
                node.publish_twist(node.linear_speed, 0.0)
            elif key == 's':
                node.publish_twist(-node.linear_speed, 0.0)
            elif key == 'a':
                node.publish_twist(0.0, node.angular_speed)
            elif key == 'd':
                node.publish_twist(0.0, -node.angular_speed)
            elif key == 'x':
                node.publish_twist(0.0, 0.0)
            elif key == 'q':
                break
    finally:
        node.publish_twist(0.0, 0.0)
        termios.tcsetattr(sys.stdin, termios.TCSADRAIN, settings)
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
