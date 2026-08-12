import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch_ros.actions import Node


def generate_launch_description():
    base_share = get_package_share_directory('raspbot_base')
    vision_share = get_package_share_directory('raspbot_vision')
    base_config = os.path.join(base_share, 'config', 'base_driver.yaml')
    gimbal_config = os.path.join(base_share, 'config', 'gimbal_servo.yaml')
    buzzer_config = os.path.join(base_share, 'config', 'buzzer.yaml')
    status_led_config = os.path.join(base_share, 'config', 'status_led.yaml')
    hardware_alert_config = os.path.join(base_share, 'config', 'hardware_alert.yaml')
    ir_obstacle_config = os.path.join(base_share, 'config', 'ir_obstacle.yaml')
    ir_obstacle_avoid_config = os.path.join(vision_share, 'config', 'ir_obstacle_avoid.yaml')
    line_follow_config = os.path.join(vision_share, 'config', 'line_follow.yaml')
    ultrasonic_config = os.path.join(vision_share, 'config', 'ultrasonic.yaml')
    obstacle_config = os.path.join(vision_share, 'config', 'obstacle_avoid.yaml')
    return LaunchDescription([
        Node(package='raspbot_base', executable='base_driver_node', name='raspbot_base_driver', output='screen', parameters=[base_config]),
        Node(package='raspbot_base', executable='gimbal_servo_node', name='raspbot_gimbal_servo', output='screen', parameters=[gimbal_config]),
        Node(package='raspbot_base', executable='buzzer_node', name='raspbot_buzzer', output='screen', parameters=[buzzer_config]),
        Node(package='raspbot_base', executable='status_led_node', name='raspbot_status_led', output='screen', parameters=[status_led_config]),
        Node(package='raspbot_base', executable='hardware_alert_node', name='raspbot_hardware_alert', output='screen', parameters=[hardware_alert_config]),
        Node(package='raspbot_base', executable='ir_obstacle_node', name='raspbot_ir_obstacle', output='screen', parameters=[ir_obstacle_config]),
        Node(package='raspbot_vision', executable='ir_obstacle_avoid_node', name='raspbot_ir_obstacle_avoid', output='screen', parameters=[ir_obstacle_avoid_config]),
        Node(package='raspbot_vision', executable='line_follow_node', name='raspbot_line_follow', output='screen', parameters=[line_follow_config]),
        Node(package='raspbot_vision', executable='ultrasonic_range_node', name='raspbot_ultrasonic', output='screen', parameters=[ultrasonic_config]),
        Node(package='raspbot_vision', executable='obstacle_avoid_node', name='raspbot_obstacle_avoid', output='screen', parameters=[obstacle_config]),
    ])
