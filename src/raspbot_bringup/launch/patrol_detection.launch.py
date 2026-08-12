from launch import LaunchDescription
from launch_ros.actions import Node
from ament_index_python.packages import get_package_share_directory
import os


def generate_launch_description():
    vision_share = get_package_share_directory('raspbot_vision')
    person_detect_config = os.path.join(vision_share, 'config', 'person_detect.yaml')
    patrol_logger_config = os.path.join(vision_share, 'config', 'patrol_logger.yaml')
    patrol_scheduler_config = os.path.join(vision_share, 'config', 'patrol_scheduler.yaml')
    return LaunchDescription([
        Node(package='raspbot_vision', executable='person_detect_node', name='raspbot_person_detect', output='screen', parameters=[person_detect_config]),
        Node(package='raspbot_vision', executable='patrol_logger_node', name='raspbot_patrol_logger', output='screen', parameters=[patrol_logger_config]),
        Node(package='raspbot_vision', executable='patrol_scheduler_node', name='raspbot_patrol_scheduler', output='screen', parameters=[patrol_scheduler_config]),
    ])
