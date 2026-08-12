import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch_ros.actions import Node


def generate_launch_description():
    bringup_share = get_package_share_directory('raspbot_bringup')
    vision_share = get_package_share_directory('raspbot_vision')

    base_launch = os.path.join(bringup_share, 'launch', 'base_bringup.launch.py')
    ultrasonic_config = os.path.join(vision_share, 'config', 'ultrasonic.yaml')
    obstacle_avoid_config = os.path.join(vision_share, 'config', 'obstacle_avoid.yaml')
    person_detect_config = os.path.join(vision_share, 'config', 'person_detect_tf_ssd.yaml')
    patrol_logger_config = os.path.join(vision_share, 'config', 'patrol_logger.yaml')
    patrol_scheduler_config = os.path.join(vision_share, 'config', 'patrol_scheduler.yaml')
    patrol_behavior_config = os.path.join(vision_share, 'config', 'patrol_behavior.yaml')
    agent_gateway_config = os.path.join(vision_share, 'config', 'agent_command_gateway.yaml')

    return LaunchDescription([
        IncludeLaunchDescription(PythonLaunchDescriptionSource(base_launch)),
        Node(package='raspbot_vision', executable='ultrasonic_range_node', name='raspbot_ultrasonic_range', output='screen', parameters=[ultrasonic_config]),
        Node(package='raspbot_vision', executable='obstacle_avoid_node', name='raspbot_obstacle_avoid', output='screen', parameters=[obstacle_avoid_config]),
        Node(package='raspbot_vision', executable='person_detect_node', name='raspbot_person_detect', output='screen', parameters=[person_detect_config]),
        Node(package='raspbot_vision', executable='patrol_logger_node', name='raspbot_patrol_logger', output='screen', parameters=[patrol_logger_config]),
        Node(
            package='raspbot_vision',
            executable='patrol_scheduler_node',
            name='raspbot_patrol_scheduler',
            output='screen',
            parameters=[
                patrol_scheduler_config,
                {
                    'trigger_topic': 'patrol/trigger',
                    'interval_sec': 20.0,
                },
            ],
        ),
        Node(package='raspbot_vision', executable='agent_command_gateway_node', name='raspbot_agent_command_gateway', output='screen', parameters=[agent_gateway_config]),
        Node(package='raspbot_vision', executable='patrol_behavior_node', name='raspbot_patrol_behavior', output='screen', parameters=[patrol_behavior_config]),
    ])
