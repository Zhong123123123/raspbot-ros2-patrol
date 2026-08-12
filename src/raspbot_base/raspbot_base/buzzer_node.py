import time

import lgpio
import rclpy
from rcl_interfaces.msg import SetParametersResult
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from std_msgs.msg import Bool, UInt16


class BuzzerNode(Node):
    def __init__(self):
        super().__init__('raspbot_buzzer')
        self.declare_parameter('gpiochip', 0)
        self.declare_parameter('gpio_pin', 12)
        self.declare_parameter('active_high', True)
        self.declare_parameter('enabled', False)
        self.declare_parameter('default_beep_ms', 80)

        self.gpiochip = int(self.get_parameter('gpiochip').value)
        self.gpio_pin = int(self.get_parameter('gpio_pin').value)
        self.active_high = bool(self.get_parameter('active_high').value)
        self.enabled = bool(self.get_parameter('enabled').value)
        self.default_beep_ms = max(1, int(self.get_parameter('default_beep_ms').value))

        self.gpio_handle = None
        self.beep_deadline = None
        self.setup_gpio()

        self.create_subscription(Bool, 'buzzer_cmd', self.bool_callback, 10)
        self.create_subscription(UInt16, 'buzzer_beep_ms', self.beep_callback, 10)
        self.timer = self.create_timer(0.02, self.timer_callback)
        self.add_on_set_parameters_callback(self.on_set_parameters)
        self.write_state(False)
        self.get_logger().info('buzzer node started (default silent)')

    def now_sec(self):
        return time.monotonic()

    def setup_gpio(self):
        self.cleanup_gpio()
        self.gpio_handle = lgpio.gpiochip_open(self.gpiochip)
        lgpio.gpio_claim_output(self.gpio_handle, self.gpio_pin, 0)

    def cleanup_gpio(self):
        if self.gpio_handle is None:
            return
        try:
            lgpio.gpio_write(self.gpio_handle, self.gpio_pin, 0)
        except Exception:
            pass
        try:
            lgpio.gpio_free(self.gpio_handle, self.gpio_pin)
        except Exception:
            pass
        try:
            lgpio.gpiochip_close(self.gpio_handle)
        except Exception:
            pass
        self.gpio_handle = None

    def write_state(self, on: bool):
        if self.gpio_handle is None:
            return
        level = 1 if (on == self.active_high) else 0
        lgpio.gpio_write(self.gpio_handle, self.gpio_pin, level)

    def bool_callback(self, msg: Bool):
        if not self.enabled:
            self.write_state(False)
            return
        self.beep_deadline = None
        self.write_state(bool(msg.data))

    def beep_callback(self, msg: UInt16):
        if not self.enabled:
            self.write_state(False)
            return
        duration_ms = int(msg.data) if int(msg.data) > 0 else self.default_beep_ms
        self.write_state(True)
        self.beep_deadline = self.now_sec() + duration_ms / 1000.0

    def timer_callback(self):
        if self.beep_deadline is None:
            return
        if self.now_sec() >= self.beep_deadline:
            self.write_state(False)
            self.beep_deadline = None

    def on_set_parameters(self, params):
        reinit_gpio = False
        for param in params:
            if param.name == 'gpiochip':
                self.gpiochip = int(param.value)
                reinit_gpio = True
            elif param.name == 'gpio_pin':
                self.gpio_pin = int(param.value)
                reinit_gpio = True
            elif param.name == 'active_high':
                self.active_high = bool(param.value)
            elif param.name == 'enabled':
                self.enabled = bool(param.value)
                if not self.enabled:
                    self.write_state(False)
            elif param.name == 'default_beep_ms':
                self.default_beep_ms = max(1, int(param.value))
        if reinit_gpio:
            try:
                self.setup_gpio()
                self.write_state(False)
            except Exception as exc:
                return SetParametersResult(successful=False, reason=str(exc))
        return SetParametersResult(successful=True)

    def destroy_node(self):
        try:
            self.write_state(False)
        finally:
            self.cleanup_gpio()
        return super().destroy_node()


def main(args=None):
    rclpy.init(args=args)
    node = BuzzerNode()
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
