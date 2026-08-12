from typing import Optional

import rclpy
from geometry_msgs.msg import Vector3
from rcl_interfaces.msg import SetParametersResult
from rclpy.node import Node
from sensor_msgs.msg import JointState

from .yb_pcb_car import YB_Pcb_Car


class GimbalServoNode(Node):
    def __init__(self):
        super().__init__('raspbot_gimbal_servo')
        self.declare_parameter('i2c_address', 0x16)
        self.declare_parameter('i2c_bus', 1)
        self.declare_parameter('pan_servo_id', 1)
        self.declare_parameter('tilt_servo_id', 2)
        self.declare_parameter('default_pan', 90)
        self.declare_parameter('default_tilt', 90)
        self.declare_parameter('min_angle', 0)
        self.declare_parameter('max_angle', 180)
        self.declare_parameter('command_topic', 'gimbal_cmd')
        self.declare_parameter('state_topic', 'gimbal_joint_states')
        self.declare_parameter('joint_names', ['gimbal_pan_joint', 'gimbal_tilt_joint'])
        self.declare_parameter('publish_rate', 5.0)

        self.driver = YB_Pcb_Car(
            address=self.get_parameter('i2c_address').value,
            i2c_bus=self.get_parameter('i2c_bus').value,
        )
        self.pan_servo_id = int(self.get_parameter('pan_servo_id').value)
        self.tilt_servo_id = int(self.get_parameter('tilt_servo_id').value)
        self.min_angle = int(self.get_parameter('min_angle').value)
        self.max_angle = int(self.get_parameter('max_angle').value)
        self.joint_names = [str(name) for name in self.get_parameter('joint_names').value]
        if len(self.joint_names) != 2:
            self.joint_names = ['gimbal_pan_joint', 'gimbal_tilt_joint']

        self.current_pan = self.clamp_angle(self.get_parameter('default_pan').value)
        self.current_tilt = self.clamp_angle(self.get_parameter('default_tilt').value)

        command_topic = str(self.get_parameter('command_topic').value)
        state_topic = str(self.get_parameter('state_topic').value)
        publish_rate = max(1.0, float(self.get_parameter('publish_rate').value))

        self.state_pub = self.create_publisher(JointState, state_topic, 10)
        self.create_subscription(Vector3, command_topic, self.command_callback, 10)
        self.timer = self.create_timer(1.0 / publish_rate, self.publish_state)
        self.add_on_set_parameters_callback(self.on_set_parameters)

        self.write_servos(self.current_pan, self.current_tilt)
        self.get_logger().info(
            f'gimbal servo node started, pan={self.current_pan}, tilt={self.current_tilt}'
        )

    def clamp_angle(self, value) -> int:
        return max(self.min_angle, min(self.max_angle, int(value)))

    def write_servos(self, pan: int, tilt: int):
        self.driver.ctrl_servo(self.pan_servo_id, pan)
        self.driver.ctrl_servo(self.tilt_servo_id, tilt)
        self.current_pan = pan
        self.current_tilt = tilt

    def command_callback(self, msg: Vector3):
        pan = self.clamp_angle(msg.x)
        tilt = self.clamp_angle(msg.y)
        self.write_servos(pan, tilt)

    def publish_state(self):
        msg = JointState()
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.name = self.joint_names
        msg.position = [
            self.current_pan * 3.141592653589793 / 180.0,
            self.current_tilt * 3.141592653589793 / 180.0,
        ]
        self.state_pub.publish(msg)

    def on_set_parameters(self, params):
        pending_pan: Optional[int] = None
        pending_tilt: Optional[int] = None
        for param in params:
            if param.name == 'min_angle':
                self.min_angle = int(param.value)
            elif param.name == 'max_angle':
                self.max_angle = int(param.value)
            elif param.name == 'default_pan':
                pending_pan = self.clamp_angle(param.value)
            elif param.name == 'default_tilt':
                pending_tilt = self.clamp_angle(param.value)
        if pending_pan is not None or pending_tilt is not None:
            self.write_servos(
                self.current_pan if pending_pan is None else pending_pan,
                self.current_tilt if pending_tilt is None else pending_tilt,
            )
        return SetParametersResult(successful=True)


def main(args=None):
    rclpy.init(args=args)
    node = GimbalServoNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
