import lgpio
import rclpy
from rcl_interfaces.msg import SetParametersResult
from rclpy.node import Node
from std_msgs.msg import ColorRGBA


class StatusLedNode(Node):
    def __init__(self):
        super().__init__('raspbot_status_led')
        self.declare_parameter('enabled', False)
        self.declare_parameter('gpiochip', 0)
        self.declare_parameter('led1_gpio', 5)
        self.declare_parameter('led2_gpio', 6)
        self.declare_parameter('led1_active_high', True)
        self.declare_parameter('led2_active_high', True)
        self.declare_parameter('default_red', 0.0)
        self.declare_parameter('default_green', 0.0)
        self.declare_parameter('default_blue', 0.0)

        self.enabled = bool(self.get_parameter('enabled').value)
        self.gpiochip = int(self.get_parameter('gpiochip').value)
        self.led1_gpio = int(self.get_parameter('led1_gpio').value)
        self.led2_gpio = int(self.get_parameter('led2_gpio').value)
        self.led1_active_high = bool(self.get_parameter('led1_active_high').value)
        self.led2_active_high = bool(self.get_parameter('led2_active_high').value)
        self.gpio_handle = None
        if self.enabled:
            self.setup_gpio()

        self.create_subscription(ColorRGBA, 'status_led_cmd', self.color_callback, 10)
        self.add_on_set_parameters_callback(self.on_set_parameters)

        if self.enabled:
            self.apply_color(
                float(self.get_parameter('default_red').value),
                float(self.get_parameter('default_green').value),
                float(self.get_parameter('default_blue').value),
            )
        self.get_logger().info(
            f'status led node started (enabled={self.enabled}, led1_gpio={self.led1_gpio}, led2_gpio={self.led2_gpio})'
        )

    def setup_gpio(self):
        self.cleanup_gpio()
        self.gpio_handle = lgpio.gpiochip_open(self.gpiochip)
        lgpio.gpio_claim_output(self.gpio_handle, self.led1_gpio, 0)
        lgpio.gpio_claim_output(self.gpio_handle, self.led2_gpio, 0)

    def cleanup_gpio(self):
        if self.gpio_handle is None:
            return
        for pin in (self.led1_gpio, self.led2_gpio):
            try:
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

    def write_pin(self, pin: int, active_high: bool, on: bool):
        if self.gpio_handle is None:
            return
        level = 1 if (on == active_high) else 0
        lgpio.gpio_write(self.gpio_handle, pin, level)

    def apply_color(self, red: float, green: float, blue: float):
        if not self.enabled:
            return
        red_on = red > 0.5
        blue_on = blue > 0.5
        self.write_pin(self.led1_gpio, self.led1_active_high, red_on)
        self.write_pin(self.led2_gpio, self.led2_active_high, blue_on)
        if green > 0.5:
            self.get_logger().debug('green channel requested but old board likely exposes only two status LEDs')

    def color_callback(self, msg: ColorRGBA):
        self.apply_color(float(msg.r), float(msg.g), float(msg.b))

    def on_set_parameters(self, params):
        reinit_gpio = False
        enabled_changed = False
        for param in params:
            if param.name == 'enabled':
                self.enabled = bool(param.value)
                enabled_changed = True
            elif param.name == 'gpiochip':
                self.gpiochip = int(param.value)
                reinit_gpio = True
            elif param.name == 'led1_gpio':
                self.led1_gpio = int(param.value)
                reinit_gpio = True
            elif param.name == 'led2_gpio':
                self.led2_gpio = int(param.value)
                reinit_gpio = True
            elif param.name == 'led1_active_high':
                self.led1_active_high = bool(param.value)
            elif param.name == 'led2_active_high':
                self.led2_active_high = bool(param.value)
        if enabled_changed or reinit_gpio:
            try:
                self.cleanup_gpio()
                if self.enabled:
                    self.setup_gpio()
            except Exception as exc:
                return SetParametersResult(successful=False, reason=str(exc))
        return SetParametersResult(successful=True)

    def destroy_node(self):
        try:
            self.apply_color(0.0, 0.0, 0.0)
        finally:
            self.cleanup_gpio()
            return super().destroy_node()


def main(args=None):
    rclpy.init(args=args)
    node = StatusLedNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
