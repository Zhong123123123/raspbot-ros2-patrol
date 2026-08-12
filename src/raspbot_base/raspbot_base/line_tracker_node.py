import lgpio
import rclpy
from rcl_interfaces.msg import SetParametersResult
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from std_msgs.msg import Int32MultiArray


class LineTrackerNode(Node):
    def __init__(self):
        super().__init__('raspbot_line_tracker')
        self.declare_parameter('gpiochip', 0)
        self.declare_parameter('sensor_pins', [17, 4, 27, 22])
        self.declare_parameter('active_low', True)
        self.declare_parameter('publish_rate', 20.0)

        self.gpiochip = int(self.get_parameter('gpiochip').value)
        self.sensor_pins = [int(pin) for pin in self.get_parameter('sensor_pins').value]
        self.active_low = bool(self.get_parameter('active_low').value)
        self.publish_rate = max(1.0, float(self.get_parameter('publish_rate').value))

        self.gpio_handle = None
        self.publisher = self.create_publisher(Int32MultiArray, 'line_tracker', 10)
        self.setup_gpio()
        self.timer = self.create_timer(1.0 / self.publish_rate, self.timer_callback)
        self.add_on_set_parameters_callback(self.on_set_parameters)
        self.get_logger().info(f'line tracker node started on pins {self.sensor_pins}')

    def setup_gpio(self):
        self.cleanup_gpio()
        self.gpio_handle = lgpio.gpiochip_open(self.gpiochip)
        for pin in self.sensor_pins:
            lgpio.gpio_claim_input(self.gpio_handle, pin)

    def cleanup_gpio(self):
        if self.gpio_handle is None:
            return
        for pin in self.sensor_pins:
            try:
                lgpio.gpio_free(self.gpio_handle, pin)
            except Exception:
                pass
        try:
            lgpio.gpiochip_close(self.gpio_handle)
        except Exception:
            pass
        self.gpio_handle = None

    def read_sensors(self):
        values = []
        for pin in self.sensor_pins:
            raw = int(lgpio.gpio_read(self.gpio_handle, pin))
            detected = 1 if ((raw == 0) if self.active_low else (raw == 1)) else 0
            values.append(detected)
        return values

    def timer_callback(self):
        msg = Int32MultiArray()
        msg.data = self.read_sensors()
        self.publisher.publish(msg)

    def on_set_parameters(self, params):
        reinit_gpio = False
        reset_timer = False
        for param in params:
            if param.name == 'gpiochip':
                self.gpiochip = int(param.value)
                reinit_gpio = True
            elif param.name == 'sensor_pins':
                self.sensor_pins = [int(pin) for pin in param.value]
                reinit_gpio = True
            elif param.name == 'active_low':
                self.active_low = bool(param.value)
            elif param.name == 'publish_rate':
                self.publish_rate = max(1.0, float(param.value))
                reset_timer = True
        if reinit_gpio:
            try:
                self.setup_gpio()
            except Exception as exc:
                return SetParametersResult(successful=False, reason=str(exc))
        if reset_timer:
            self.timer.cancel()
            self.timer = self.create_timer(1.0 / self.publish_rate, self.timer_callback)
        return SetParametersResult(successful=True)

    def destroy_node(self):
        self.cleanup_gpio()
        return super().destroy_node()


def main(args=None):
    rclpy.init(args=args)
    node = LineTrackerNode()
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
