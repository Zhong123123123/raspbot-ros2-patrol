from datetime import datetime

import rclpy
from rcl_interfaces.msg import SetParametersResult
from rclpy.node import Node
from std_msgs.msg import Bool


class PatrolSchedulerNode(Node):
    def __init__(self):
        super().__init__('raspbot_patrol_scheduler')
        self.declare_parameter('enabled', True)
        self.declare_parameter('interval_sec', 10.0)
        self.declare_parameter('active_start', '00:00')
        self.declare_parameter('active_end', '23:59')
        self.declare_parameter('publish_enabled_heartbeat_sec', 5.0)
        self.declare_parameter('enabled_topic', 'person_detection/enabled')
        self.declare_parameter('trigger_topic', 'person_detection/trigger')

        self.enabled = bool(self.get_parameter('enabled').value)
        self.interval_sec = float(self.get_parameter('interval_sec').value)
        self.active_start = str(self.get_parameter('active_start').value)
        self.active_end = str(self.get_parameter('active_end').value)
        self.publish_enabled_heartbeat_sec = float(self.get_parameter('publish_enabled_heartbeat_sec').value)
        self.enabled_topic = str(self.get_parameter('enabled_topic').value)
        self.trigger_topic = str(self.get_parameter('trigger_topic').value)

        self.enabled_pub = self.create_publisher(Bool, self.enabled_topic, 10)
        self.trigger_pub = self.create_publisher(Bool, self.trigger_topic, 10)
        self.add_on_set_parameters_callback(self.on_set_parameters)
        self.trigger_timer = self.create_timer(max(self.interval_sec, 1.0), self.trigger_timer_callback)
        self.heartbeat_timer = self.create_timer(max(self.publish_enabled_heartbeat_sec, 1.0), self.heartbeat_callback)
        self.last_active = None
        self.get_logger().info(
            f'patrol scheduler node started (enabled={self.enabled}, interval_sec={self.interval_sec}, active_start={self.active_start}, active_end={self.active_end})'
        )

    def on_set_parameters(self, params):
        for param in params:
            if param.name == 'enabled':
                self.enabled = bool(param.value)
            elif param.name == 'interval_sec':
                if float(param.value) <= 0.0:
                    return SetParametersResult(successful=False, reason='interval_sec must be > 0')
                self.interval_sec = float(param.value)
                self.trigger_timer.timer_period_ns = int(self.interval_sec * 1e9)
            elif param.name == 'active_start':
                self.active_start = str(param.value)
            elif param.name == 'active_end':
                self.active_end = str(param.value)
            elif param.name == 'publish_enabled_heartbeat_sec':
                if float(param.value) <= 0.0:
                    return SetParametersResult(successful=False, reason='publish_enabled_heartbeat_sec must be > 0')
                self.publish_enabled_heartbeat_sec = float(param.value)
                self.heartbeat_timer.timer_period_ns = int(self.publish_enabled_heartbeat_sec * 1e9)
        return SetParametersResult(successful=True)

    def _parse_hhmm(self, value: str):
        hour_str, minute_str = value.split(':', 1)
        return int(hour_str), int(minute_str)

    def is_active_now(self):
        if not self.enabled:
            return False
        now = datetime.now()
        start_hour, start_minute = self._parse_hhmm(self.active_start)
        end_hour, end_minute = self._parse_hhmm(self.active_end)
        current_minutes = now.hour * 60 + now.minute
        start_minutes = start_hour * 60 + start_minute
        end_minutes = end_hour * 60 + end_minute
        if start_minutes <= end_minutes:
            return start_minutes <= current_minutes <= end_minutes
        return current_minutes >= start_minutes or current_minutes <= end_minutes

    def publish_enabled_state(self, active: bool):
        msg = Bool()
        msg.data = active
        self.enabled_pub.publish(msg)

    def heartbeat_callback(self):
        active = self.is_active_now()
        self.publish_enabled_state(active)
        if self.last_active is None or self.last_active != active:
            self.get_logger().info(f'patrol schedule active={active}')
            self.last_active = active

    def trigger_timer_callback(self):
        if not self.is_active_now():
            return
        self.publish_enabled_state(True)
        msg = Bool()
        msg.data = True
        self.trigger_pub.publish(msg)
        self.get_logger().debug('published patrol trigger')


def main(args=None):
    rclpy.init(args=args)
    node = PatrolSchedulerNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
