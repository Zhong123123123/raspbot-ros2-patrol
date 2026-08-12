import cv2
import rclpy
from geometry_msgs.msg import Twist
from rcl_interfaces.msg import SetParametersResult
from rclpy.node import Node
from sensor_msgs.msg import CompressedImage

from .decision import DecisionMaker
from .line_detector import LineDetector
from .usb_camera import USBCamera


class LineFollowNode(Node):
    def __init__(self):
        super().__init__('raspbot_line_follow')
        self.declare_parameter('camera_device', '/dev/v4l/by-id/usb-Generic_HD_camera_20181212000000-video-index0')
        self.declare_parameter('width', 640)
        self.declare_parameter('height', 480)
        self.declare_parameter('fps', 30)
        self.declare_parameter('loop_hz', 10.0)
        self.declare_parameter('threshold', 80)
        self.declare_parameter('min_area', 500)
        self.declare_parameter('roi_ratio', 0.55)
        self.declare_parameter('dead_zone', 100)
        self.declare_parameter('lost_tolerance', 3)
        self.declare_parameter('smooth_window', 5)
        self.declare_parameter('forward_speed', 0.20)
        self.declare_parameter('turn_speed', 0.14)
        self.declare_parameter('turn_angular', 0.70)
        self.declare_parameter('publish_debug', True)

        self.camera = USBCamera(
            device=self.get_parameter('camera_device').value,
            width=int(self.get_parameter('width').value),
            height=int(self.get_parameter('height').value),
            fps=int(self.get_parameter('fps').value),
        )
        self.detector = LineDetector()
        self._load_runtime_settings()
        self.cmd_pub = self.create_publisher(Twist, 'cmd_vel', 10)
        self.debug_pub = self.create_publisher(CompressedImage, 'line_follow/debug/compressed', 10)
        period = 1.0 / float(self.get_parameter('loop_hz').value)
        self.timer = self.create_timer(period, self.timer_callback)
        self.add_on_set_parameters_callback(self.on_set_parameters)
        self.camera.open()
        self.get_logger().info('line follow node started')

    def _load_runtime_settings(self):
        self.threshold = int(self.get_parameter('threshold').value)
        self.min_area = int(self.get_parameter('min_area').value)
        self.roi_ratio = float(self.get_parameter('roi_ratio').value)
        self.forward_speed = float(self.get_parameter('forward_speed').value)
        self.turn_speed = float(self.get_parameter('turn_speed').value)
        self.turn_angular = float(self.get_parameter('turn_angular').value)
        self.publish_debug = bool(self.get_parameter('publish_debug').value)
        self.decision = DecisionMaker(
            dead_zone=int(self.get_parameter('dead_zone').value),
            lost_tolerance=int(self.get_parameter('lost_tolerance').value),
            smooth_window=int(self.get_parameter('smooth_window').value),
        )

    def on_set_parameters(self, params):
        allowed = {
            'threshold', 'min_area', 'roi_ratio', 'dead_zone', 'lost_tolerance',
            'smooth_window', 'forward_speed', 'turn_speed', 'turn_angular', 'publish_debug'
        }
        for param in params:
            if param.name not in allowed:
                continue
            if param.name in {'threshold', 'min_area', 'dead_zone', 'lost_tolerance', 'smooth_window'} and int(param.value) < 0:
                return SetParametersResult(successful=False, reason=f'{param.name} must be >= 0')
            if param.name == 'roi_ratio' and not (0.1 <= float(param.value) <= 0.95):
                return SetParametersResult(successful=False, reason='roi_ratio must be between 0.1 and 0.95')
        self._load_runtime_settings()
        return SetParametersResult(successful=True)

    def make_twist(self, linear_x, angular_z):
        msg = Twist()
        msg.linear.x = linear_x
        msg.angular.z = angular_z
        return msg

    def action_to_twist(self, action):
        if action == 'FORWARD':
            return self.make_twist(self.forward_speed, 0.0)
        if action == 'LEFT':
            return self.make_twist(self.turn_speed, self.turn_angular)
        if action == 'RIGHT':
            return self.make_twist(self.turn_speed, -self.turn_angular)
        return self.make_twist(0.0, 0.0)

    def publish_debug_image(self, frame):
        if not self.publish_debug:
            return
        ok, encoded = cv2.imencode('.jpg', frame)
        if not ok:
            return
        msg = CompressedImage()
        msg.format = 'jpeg'
        msg.data = encoded.tobytes()
        self.debug_pub.publish(msg)

    def timer_callback(self):
        frame = self.camera.read()
        if frame is None:
            self.get_logger().warning('failed to read frame')
            self.cmd_pub.publish(self.make_twist(0.0, 0.0))
            return
        result = self.detector.detect(frame, threshold=self.threshold, min_area=self.min_area, roi_ratio=self.roi_ratio)
        action = self.decision.decide(result['found'], result['offset'])
        self.cmd_pub.publish(self.action_to_twist(action))
        self.publish_debug_image(result['debug'])

    def destroy_node(self):
        try:
            self.camera.release()
        finally:
            super().destroy_node()


def main(args=None):
    rclpy.init(args=args)
    node = LineFollowNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()
