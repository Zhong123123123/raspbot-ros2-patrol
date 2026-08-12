from setuptools import find_packages, setup

package_name = 'raspbot_vision'

setup(
    name=package_name,
    version='0.0.1',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages', ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        ('share/' + package_name + '/config', [
            'config/line_follow.yaml',
            'config/obstacle_avoid.yaml',
            'config/ultrasonic.yaml',
            'config/ir_obstacle_avoid.yaml',
            'config/person_detect.yaml',
            'config/person_detect_hog.yaml',
            'config/person_detect_tf_ssd.yaml',
            'config/person_detect_yolov8.yaml',
            'config/patrol_logger.yaml',
            'config/patrol_scheduler.yaml',
            'config/patrol_behavior.yaml',
            'config/voice_announce.yaml',
            'config/remote_notify.yaml',
            'config/route_patrol.yaml',
            'config/agent_command_gateway.yaml',
        ]),
        ('share/' + package_name + '/web_dashboard', [
            'raspbot_vision/web_dashboard/index.html',
        ]),
        ('share/' + package_name + '/openclaw', [
            'openclaw/OPENCLAW_SKILL.md',
        ]),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='ubuntu',
    maintainer_email='ubuntu@localhost',
    description='Line following vision nodes for Yahboom Raspbot.',
    license='Proprietary',
    entry_points={
        'console_scripts': [
            'line_follow_node = raspbot_vision.line_follow_node:main',
            'obstacle_avoid_node = raspbot_vision.obstacle_avoid_node:main',
            'ultrasonic_range_node = raspbot_vision.ultrasonic_range_node:main',
            'ir_obstacle_avoid_node = raspbot_vision.ir_obstacle_avoid_node:main',
            'person_detect_node = raspbot_vision.person_detect_node:main',
            'patrol_logger_node = raspbot_vision.patrol_logger_node:main',
            'patrol_scheduler_node = raspbot_vision.patrol_scheduler_node:main',
            'patrol_behavior_node = raspbot_vision.patrol_behavior_node:main',
            'compare_person_detectors = raspbot_vision.compare_person_detectors:main',
            'web_dashboard_node = raspbot_vision.web_dashboard_node:main',
            'voice_announce_node = raspbot_vision.voice_announce_node:main',
            'remote_notify_node = raspbot_vision.remote_notify_node:main',
            'generate_patrol_report = raspbot_vision.generate_patrol_report:main',
            'route_patrol_node = raspbot_vision.route_patrol_node:main',
            'agent_command_gateway_node = raspbot_vision.agent_command_gateway_node:main',
            'openclaw_agent_entry = raspbot_vision.openclaw_agent_entry:main',
        ],
    },
)
