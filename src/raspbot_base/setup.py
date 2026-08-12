from setuptools import find_packages, setup

package_name = 'raspbot_base'

setup(
    name=package_name,
    version='0.0.1',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages', ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        ('share/' + package_name + '/config', [
            'config/base_driver.yaml',
            'config/gimbal_servo.yaml',
            'config/buzzer.yaml',
            'config/status_led.yaml',
            'config/hardware_alert.yaml',
            'config/line_tracker.yaml',
            'config/ir_line_follow.yaml',
            'config/ir_obstacle.yaml',
        ]),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='ubuntu',
    maintainer_email='ubuntu@localhost',
    description='ROS 2 base driver for Yahboom Raspbot.',
    license='Proprietary',
    entry_points={
        'console_scripts': [
            'base_driver_node = raspbot_base.base_driver_node:main',
            'teleop_keyboard_node = raspbot_base.teleop_keyboard_node:main',
            'gimbal_servo_node = raspbot_base.gimbal_servo_node:main',
            'buzzer_node = raspbot_base.buzzer_node:main',
            'status_led_node = raspbot_base.status_led_node:main',
            'hardware_alert_node = raspbot_base.hardware_alert_node:main',
            'line_tracker_node = raspbot_base.line_tracker_node:main',
            'ir_line_follow_node = raspbot_base.ir_line_follow_node:main',
            'ir_obstacle_node = raspbot_base.ir_obstacle_node:main',
        ],
    },
)
