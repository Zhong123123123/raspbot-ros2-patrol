import rclpy
from rcl_interfaces.msg import SetParametersResult
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from std_msgs.msg import Bool, ColorRGBA, UInt16


class HardwareAlertNode(Node):
    def __init__(self):
        super().__init__('raspbot_hardware_alert')
        self.declare_parameter('idle_red', 0.0)
        self.declare_parameter('idle_green', 0.0)
        self.declare_parameter('idle_blue', 1.0)
        self.declare_parameter('alert_red', 1.0)
        self.declare_parameter('alert_green', 0.0)
        self.declare_parameter('alert_blue', 0.0)
        self.declare_parameter('beep_on_alert', False)
        self.declare_parameter('beep_ms', 60)

        self.idle_color = self.read_color('idle')
        self.alert_color = self.read_color('alert')
        self.beep_on_alert = bool(self.get_parameter('beep_on_alert').value)
        self.beep_ms = max(1, int(self.get_parameter('beep_ms').value))
        self.last_state = None

        self.led_pub = self.create_publisher(ColorRGBA, 'status_led_cmd', 10)
        self.beep_pub = self.create_publisher(UInt16, 'buzzer_beep_ms', 10)
        self.create_subscription(Bool, 'safety_override_active', self.override_callback, 10)
        self.add_on_set_parameters_callback(self.on_set_parameters)
        self.publish_color(self.idle_color)
        self.get_logger().info('hardware alert node started')

    def read_color(self, prefix: str):
        return (
            float(self.get_parameter(f'{prefix}_red').value),
            float(self.get_parameter(f'{prefix}_green').value),
            float(self.get_parameter(f'{prefix}_blue').value),
        )

    def publish_color(self, rgb):
        msg = ColorRGBA()
        msg.r, msg.g, msg.b = rgb
        msg.a = 1.0
        self.led_pub.publish(msg)

    def override_callback(self, msg: Bool):
        active = bool(msg.data)
        if active == self.last_state:
            return
        self.last_state = active
        self.publish_color(self.alert_color if active else self.idle_color)
        if active and self.beep_on_alert:
            beep = UInt16()
            beep.data = self.beep_ms
            self.beep_pub.publish(beep)

    def on_set_parameters(self, params):
        for param in params:
            if param.name in {'idle_red', 'idle_green', 'idle_blue', 'alert_red', 'alert_green', 'alert_blue'}:
                self.idle_color = self.read_color('idle')
                self.alert_color = self.read_color('alert')
            elif param.name == 'beep_on_alert':
                self.beep_on_alert = bool(param.value)
            elif param.name == 'beep_ms':
                self.beep_ms = max(1, int(param.value))
        return SetParametersResult(successful=True)


def main(args=None):
    rclpy.init(args=args)
    node = HardwareAlertNode()
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
