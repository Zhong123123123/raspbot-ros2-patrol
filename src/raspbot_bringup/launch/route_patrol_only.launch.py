"""Standalone route patrol node — for use when patrol_full is already running."""

import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch_ros.actions import Node


def generate_launch_description():
    vision_share = get_package_share_directory('raspbot_vision')

    return LaunchDescription([
        Node(package='raspbot_vision', executable='route_patrol_node',
             name='raspbot_route_patrol', output='screen',
             parameters=[os.path.join(vision_share, 'config', 'route_patrol.yaml')]),
    ])
