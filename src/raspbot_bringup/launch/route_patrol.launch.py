"""Full mobile patrol launch — base hardware + sensors + detection + route."""

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

    return LaunchDescription([
        # --- Base hardware ---
        IncludeLaunchDescription(PythonLaunchDescriptionSource(base_launch)),

        # --- Sensors ---
        Node(package='raspbot_vision', executable='ultrasonic_range_node',
             name='raspbot_ultrasonic_range', output='screen',
             parameters=[os.path.join(vision_share, 'config', 'ultrasonic.yaml')]),
        Node(package='raspbot_vision', executable='obstacle_avoid_node',
             name='raspbot_obstacle_avoid', output='screen',
             parameters=[os.path.join(vision_share, 'config', 'obstacle_avoid.yaml')]),

        # --- Detection ---
        Node(package='raspbot_vision', executable='person_detect_node',
             name='raspbot_person_detect', output='screen',
             parameters=[os.path.join(vision_share, 'config', 'person_detect.yaml')]),

        # --- Patrol pipeline ---
        Node(package='raspbot_vision', executable='patrol_logger_node',
             name='raspbot_patrol_logger', output='screen',
             parameters=[os.path.join(vision_share, 'config', 'patrol_logger.yaml')]),
        Node(package='raspbot_vision', executable='patrol_behavior_node',
             name='raspbot_patrol_behavior', output='screen',
             parameters=[os.path.join(vision_share, 'config', 'patrol_behavior.yaml')]),

        # --- Advanced features ---
        Node(package='raspbot_vision', executable='voice_announce_node',
             name='raspbot_voice_announce', output='screen',
             parameters=[os.path.join(vision_share, 'config', 'voice_announce.yaml')]),
        Node(package='raspbot_vision', executable='remote_notify_node',
             name='raspbot_remote_notify', output='screen',
             parameters=[os.path.join(vision_share, 'config', 'remote_notify.yaml')]),

        # --- Route patrol (replaces scheduler) ---
        Node(package='raspbot_vision', executable='route_patrol_node',
             name='raspbot_route_patrol', output='screen',
             parameters=[os.path.join(vision_share, 'config', 'route_patrol.yaml')]),
    ])
