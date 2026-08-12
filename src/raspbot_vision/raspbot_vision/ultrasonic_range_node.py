import math
import time
from collections import deque

import lgpio
import rclpy
from rcl_interfaces.msg import SetParametersResult
from rclpy.node import Node
from sensor_msgs.msg import Range


class UltrasonicRangeNode(Node):
    def __init__(self):
        super().__init__('raspbot_ultrasonic')
        self.declare_parameter('topic_name', 'ultrasonic/front')
        self.declare_parameter('frame_id', 'ultrasonic_link')
        self.declare_parameter('gpiochip', 0)
        self.declare_parameter('trig_pin', 23)
        self.declare_parameter('echo_pin', 24)
        self.declare_parameter('sample_rate', 8.0)
        self.declare_parameter('timeout_sec', 0.03)
        self.declare_parameter('settle_time_sec', 0.05)
        self.declare_parameter('min_range', 0.02)
        self.declare_parameter('max_range', 2.50)
        self.declare_parameter('field_of_view', 0.26)
        self.declare_parameter('temperature_c', 20.0)
        self.declare_parameter('median_window', 3)
        self.declare_parameter('publish_infinity_on_timeout', True)

        self.topic_name = self.get_parameter('topic_name').value
        self.frame_id = self.get_parameter('frame_id').value
        self.gpiochip = int(self.get_parameter('gpiochip').value)
        self.trig_pin = int(self.get_parameter('trig_pin').value)
        self.echo_pin = int(self.get_parameter('echo_pin').value)
        self.sample_rate = float(self.get_parameter('sample_rate').value)
        self.timeout_sec = float(self.get_parameter('timeout_sec').value)
        self.settle_time_sec = float(self.get_parameter('settle_time_sec').value)
        self.min_range = float(self.get_parameter('min_range').value)
        self.max_range = float(self.get_parameter('max_range').value)
        self.field_of_view = float(self.get_parameter('field_of_view').value)
        self.temperature_c = float(self.get_parameter('temperature_c').value)
        self.median_window = max(1, int(self.get_parameter('median_window').value))
        self.publish_infinity_on_timeout = bool(self.get_parameter('publish_infinity_on_timeout').value)

        self.history = deque(maxlen=self.median_window)
        self.gpio_handle = None
        self.publisher = self.create_publisher(Range, self.topic_name, 10)
        self.add_on_set_parameters_callback(self.on_set_parameters)
        self.setup_gpio()
        self.timer = self.create_timer(max(0.02, 1.0 / max(self.sample_rate, 0.1)), self.publish_measurement)
        self.get_logger().info(
            f'ultrasonic node started on gpiochip={self.gpiochip}, trig_gpio={self.trig_pin}, echo_gpio={self.echo_pin}'
        )

    def setup_gpio(self):
        self.cleanup_gpio()
        self.gpio_handle = lgpio.gpiochip_open(self.gpiochip)
        lgpio.gpio_claim_output(self.gpio_handle, self.trig_pin, 0)
        lgpio.gpio_claim_input(self.gpio_handle, self.echo_pin)
        lgpio.gpio_write(self.gpio_handle, self.trig_pin, 0)
        time.sleep(self.settle_time_sec)

    def cleanup_gpio(self):
        if self.gpio_handle is None:
            return
        try:
            lgpio.gpio_write(self.gpio_handle, self.trig_pin, 0)
        except Exception:
            pass
        for pin in (self.trig_pin, self.echo_pin):
            try:
                lgpio.gpio_free(self.gpio_handle, pin)
            except Exception:
                pass
        try:
            lgpio.gpiochip_close(self.gpio_handle)
        except Exception:
            pass
        self.gpio_handle = None

    def on_set_parameters(self, params):
        reset_timer = False
        reinit_gpio = False
        for param in params:
            if param.name == 'sample_rate':
                self.sample_rate = max(0.1, float(param.value))
                reset_timer = True
            elif param.name == 'timeout_sec':
                self.timeout_sec = max(0.005, float(param.value))
            elif param.name == 'settle_time_sec':
                self.settle_time_sec = max(0.0, float(param.value))
            elif param.name == 'min_range':
                self.min_range = max(0.0, float(param.value))
            elif param.name == 'max_range':
                self.max_range = max(self.min_range, float(param.value))
            elif param.name == 'field_of_view':
                self.field_of_view = max(0.01, float(param.value))
            elif param.name == 'temperature_c':
                self.temperature_c = float(param.value)
            elif param.name == 'median_window':
                self.median_window = max(1, int(param.value))
                self.history = deque(list(self.history), maxlen=self.median_window)
            elif param.name == 'publish_infinity_on_timeout':
                self.publish_infinity_on_timeout = bool(param.value)
            elif param.name == 'frame_id':
                self.frame_id = str(param.value)
            elif param.name == 'gpiochip':
                self.gpiochip = int(param.value)
                reinit_gpio = True
            elif param.name == 'trig_pin':
                self.trig_pin = int(param.value)
                reinit_gpio = True
            elif param.name == 'echo_pin':
                self.echo_pin = int(param.value)
                reinit_gpio = True
        if reinit_gpio:
            try:
                self.setup_gpio()
            except Exception as exc:
                return SetParametersResult(successful=False, reason=str(exc))
        if reset_timer:
            self.timer.cancel()
            self.timer = self.create_timer(max(0.02, 1.0 / self.sample_rate), self.publish_measurement)
        return SetParametersResult(successful=True)

    def speed_of_sound(self):
        return 331.3 + 0.606 * self.temperature_c

    def measure_once(self):
        if self.gpio_handle is None:
            raise RuntimeError('GPIO not initialized')

        lgpio.gpio_write(self.gpio_handle, self.trig_pin, 0)
        time.sleep(0.000002)
        lgpio.gpio_write(self.gpio_handle, self.trig_pin, 1)
        time.sleep(0.00001)
        lgpio.gpio_write(self.gpio_handle, self.trig_pin, 0)

        deadline = time.monotonic() + self.timeout_sec
        while lgpio.gpio_read(self.gpio_handle, self.echo_pin) == 0:
            if time.monotonic() >= deadline:
                return None

        pulse_start = time.monotonic_ns()
        deadline = time.monotonic() + self.timeout_sec
        while lgpio.gpio_read(self.gpio_handle, self.echo_pin) == 1:
            if time.monotonic() >= deadline:
                return None
        pulse_end = time.monotonic_ns()

        pulse_width = (pulse_end - pulse_start) / 1e9
        distance = pulse_width * self.speed_of_sound() / 2.0
        return distance

    def publish_measurement(self):
        try:
            distance = self.measure_once()
        except Exception as exc:
            self.get_logger().error(f'ultrasonic read failed: {exc}')
            return

        if distance is not None and self.min_range <= distance <= self.max_range:
            self.history.append(distance)
            value = sorted(self.history)[len(self.history) // 2]
        elif distance is None and self.publish_infinity_on_timeout:
            self.history.clear()
            value = math.inf
        else:
            self.history.clear()
            value = max(self.min_range, min(self.max_range, distance or 0.0))

        msg = Range()
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.header.frame_id = self.frame_id
        msg.radiation_type = Range.ULTRASOUND
        msg.field_of_view = float(self.field_of_view)
        msg.min_range = float(self.min_range)
        msg.max_range = float(self.max_range)
        msg.range = float(value)
        self.publisher.publish(msg)

    def destroy_node(self):
        self.cleanup_gpio()
        return super().destroy_node()


def main(args=None):
    rclpy.init(args=args)
    node = None
    try:
        node = UltrasonicRangeNode()
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    except RuntimeError as exc:
        if rclpy.ok():
            raise
        if node is not None:
            node.get_logger().debug(f'ignoring shutdown race in ultrasonic node: {exc}')
    finally:
        if node is not None:
            node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
