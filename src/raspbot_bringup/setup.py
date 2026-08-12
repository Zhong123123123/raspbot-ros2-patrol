from setuptools import setup

package_name = 'raspbot_bringup'

setup(
    name=package_name,
    version='0.0.1',
    packages=[package_name],
    data_files=[
        ('share/ament_index/resource_index/packages', ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        ('share/' + package_name + '/launch', [
            'launch/base_bringup.launch.py',
            'launch/line_follow.launch.py',
            'launch/line_follow_safe.launch.py',
            'launch/ir_line_follow.launch.py',
            'launch/ir_line_follow_safe.launch.py',
            'launch/patrol_detection.launch.py',
            'launch/patrol_detection_hog.launch.py',
            'launch/patrol_detection_tf_ssd.launch.py',
            'launch/patrol_full.launch.py',
            'launch/patrol_full_hog.launch.py',
            'launch/patrol_full_tf_ssd.launch.py',
            'launch/patrol_full_yolov8.launch.py',
            'launch/route_patrol.launch.py',
            'launch/route_patrol_only.launch.py',
        ]),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='ubuntu',
    maintainer_email='ubuntu@localhost',
    description='Launch files for Yahboom Raspbot ROS 2 bringup.',
    license='Proprietary',
)
