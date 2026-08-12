import lgpio
import rclpy
from rcl_interfaces.msg import SetParametersResult
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from std_msgs.msg import Bool, Int32MultiArray


class IrObstacleNode(Node):
    def __init__(self):
        super().__init__('raspbot_ir_obstacle')
        self.declare_parameter('gpiochip', 0)
        self.declare_parameter('left_pin', 9)
        self.declare_parameter('right_pin', 10)
        self.declare_parameter('enable_pin', 25)
        self.declare_parameter('sensor_active_low', True)
        self.declare_parameter('enable_active_high', True)
        self.declare_parameter('enable_on_start', True)
        self.declare_parameter('publish_rate', 20.0)

        self.gpiochip = int(self.get_parameter('gpiochip').value)
        self.left_pin = int(self.get_parameter('left_pin').value)
        self.right_pin = int(self.get_parameter('right_pin').value)
        self.enable_pin = int(self.get_parameter('enable_pin').value)
        self.sensor_active_low = bool(self.get_parameter('sensor_active_low').value)
        self.enable_active_high = bool(self.get_parameter('enable_active_high').value)
        self.enable_on_start = bool(self.get_parameter('enable_on_start').value)
        self.publish_rate = max(1.0, float(self.get_parameter('publish_rate').value))

        self.gpio_handle = None
        self.publisher = self.create_publisher(Int32MultiArray, 'ir_obstacle', 10)
        self.left_pub = self.create_publisher(Bool, 'ir_obstacle/left', 10)
        self.right_pub = self.create_publisher(Bool, 'ir_obstacle/right', 10)
        self.setup_gpio()
        self.timer = self.create_timer(1.0 / self.publish_rate, self.timer_callback)
        self.add_on_set_parameters_callback(self.on_set_parameters)
        self.get_logger().info(
            f'IR obstacle node started: left_gpio={self.left_pin}, right_gpio={self.right_pin}, enable_gpio={self.enable_pin}'
        )

    def setup_gpio(self):
        self.cleanup_gpio()
        self.gpio_handle = lgpio.gpiochip_open(self.gpiochip)
        lgpio.gpio_claim_input(self.gpio_handle, self.left_pin)
        lgpio.gpio_claim_input(self.gpio_handle, self.right_pin)
        lgpio.gpio_claim_output(self.gpio_handle, self.enable_pin, 0)
        self.set_enable(self.enable_on_start)

    def cleanup_gpio(self):
        if self.gpio_handle is None:
            return
        for pin in (self.left_pin, self.right_pin, self.enable_pin):
            try:
                if pin == self.enable_pin:
                    lgpio.gpio_write(self.gpio_handle, pin, 0)
            except Exception:
                pass
            try:
                lgpio.gpio_free(self.gpio_handle, pin)
            except Exception:
                pass
        try:
            lgpio.gpiochip_close(self.gpio_handle)
        except Exception:
            pass
        self.gpio_handle = None

    def set_enable(self, enabled: bool):
        if self.gpio_handle is None:
            return
        level = 1 if (enabled == self.enable_active_high) else 0
        lgpio.gpio_write(self.gpio_handle, self.enable_pin, level)

    def read_detected(self, pin: int) -> int:
        raw = int(lgpio.gpio_read(self.gpio_handle, pin))
        return 1 if ((raw == 0) if self.sensor_active_low else (raw == 1)) else 0

    def publish_state(self):
        left = self.read_detected(self.left_pin)
        right = self.read_detected(self.right_pin)

        packed = Int32MultiArray()
        packed.data = [left, right]
        self.publisher.publish(packed)

        left_msg = Bool()
        left_msg.data = bool(left)
        self.left_pub.publish(left_msg)

        right_msg = Bool()
        right_msg.data = bool(right)
        self.right_pub.publish(right_msg)

    def timer_callback(self):
        self.publish_state()

    def on_set_parameters(self, params):
        reinit_gpio = False
        reset_timer = False
        for param in params:
            if param.name == 'gpiochip':
                self.gpiochip = int(param.value)
                reinit_gpio = True
            elif param.name == 'left_pin':
                self.left_pin = int(param.value)
                reinit_gpio = True
            elif param.name == 'right_pin':
                self.right_pin = int(param.value)
                reinit_gpio = True
            elif param.name == 'enable_pin':
                self.enable_pin = int(param.value)
                reinit_gpio = True
            elif param.name == 'sensor_active_low':
                self.sensor_active_low = bool(param.value)
            elif param.name == 'enable_active_high':
                self.enable_active_high = bool(param.value)
            elif param.name == 'enable_on_start':
                self.enable_on_start = bool(param.value)
                if self.gpio_handle is not None:
                    self.set_enable(self.enable_on_start)
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
    node = IrObstacleNode()
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
