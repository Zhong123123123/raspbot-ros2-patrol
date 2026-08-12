# 环境搭建指南

## 概述

本文档涵盖从零开始在 Raspberry Pi 4B 上搭建本项目所需的全部步骤。

---

## 硬件前提

- Raspberry Pi 4B 8GB
- 已刷入 Ubuntu Server 24.04（64-bit）
- USB 摄像头已连接
- Yahboom Raspbot 底盘已组装，I2C/GPIO 排线已连接
- HC-SR04 超声波模块已安装
- 舵机云台已安装（巡逻功能需要）

---

## 第一步：系统基础配置

### 1.1 启用 I2C

```bash
# 检查 I2C 是否已启用
ls /dev/i2c-1

# 如果不存在，启用 I2C
sudo raspi-config
# Interface Options → I2C → Enable
# 或者手动编辑：
# echo "dtparam=i2c_arm=on" | sudo tee -a /boot/firmware/config.txt
# sudo reboot
```

### 1.2 验证 I2C 设备

```bash
sudo i2cdetect -y 1
```

应该看到地址 `0x16` 处有设备响应：

```
     0  1  2  3  4  5  6  7  8  9  a  b  c  d  e  f
00:                         -- -- -- -- -- -- -- --
10: -- -- -- -- -- -- 16 -- -- -- -- -- -- -- -- --
```

### 1.3 确认摄像头

```bash
# 列出视频设备
v4l2-ctl --list-devices

# 查看摄像头支持的格式
v4l2-ctl -d /dev/video0 --list-formats-ext

# 确认设备路径存在
ls /dev/v4l/by-id/
```

如果使用的是和本项目不同的摄像头，需要修改配置文件中 `camera_device` 参数的值。

---

## 第二步：安装 ROS2 Jazzy

```bash
# 添加 ROS2 仓库
sudo apt update && sudo apt install -y software-properties-common
sudo add-apt-repository universe
sudo apt update && sudo apt install -y curl
sudo curl -sSL https://raw.githubusercontent.com/ros/rosdistro/master/ros.key -o /usr/share/keyrings/ros-archive-keyring.gpg

echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/ros-archive-keyring.gpg] http://packages.ros.org/ros2/ubuntu $(. /etc/os-release && echo $UBUNTU_CODENAME) main" | sudo tee /etc/apt/sources.list.d/ros2.list > /dev/null

# 安装 ROS2 Jazzy 基础包
sudo apt update
sudo apt install -y ros-jazzy-ros-base

# 验证安装
source /opt/ros/jazzy/setup.bash
ros2 --version
```

---

## 第三步：安装系统依赖

```bash
sudo apt update
sudo apt install -y \
    python3-pip \
    python3-smbus \
    python3-lgpio \
    python3-opencv \
    python3-numpy \
    ros-jazzy-ament-index-python \
    v4l-utils \
    i2c-tools \
    lsof \
    sqlite3
```

---

## 第四步：配置用户权限

```bash
# 将用户加入 I2C 和 video 组
sudo usermod -a -G i2c,video,dialout $USER

# 重新登录使权限生效
# （或者重启）
sudo reboot
```

---

## 第五步：编译项目

```bash
cd ~/ros2_ws

# 运行项目专用编译脚本（自动修复 ament_python 环境发现）
./build.sh

# 加载工作空间环境
source install/setup.bash
```

---

## 第六步：下载人体检测模型（巡逻功能需要）

### 选项 A：使用已提供的模型

模型文件已在 `~/ros2_ws/models/person_detection/` 目录：
- `frozen_inference_graph.pb`
- `ssd_mobilenet_v1_coco_2017_11_17.pbtxt`

如果文件已存在（通过 Git LFS 或其他方式获取），跳过此步。

### 选项 B：从 TensorFlow Model Zoo 下载

```bash
cd /tmp
wget http://download.tensorflow.org/models/object_detection/ssd_mobilenet_v1_coco_2017_11_17.tar.gz
tar -xzf ssd_mobilenet_v1_coco_2017_11_17.tar.gz
mkdir -p ~/ros2_ws/models/person_detection
cp ssd_mobilenet_v1_coco_2017_11_17/frozen_inference_graph.pb ~/ros2_ws/models/person_detection/
cp ssd_mobilenet_v1_coco_2017_11_17/ssd_mobilenet_v1_coco_2017_11_17.pbtxt ~/ros2_ws/models/person_detection/
```

### 选项 C：仅使用 HOG 检测器

如果不想下载模型文件，可以使用 OpenCV 内置的 HOG 行人检测器（无需额外模型）：

```bash
ros2 launch raspbot_bringup patrol_full_hog.launch.py
```

---

## 第七步：验证安装

### 7.1 验证 ROS2 环境

```bash
source ~/ros2_ws/install/setup.bash
ros2 pkg list | grep raspbot
```

预期输出：
```
raspbot_base
raspbot_bringup
raspbot_vision
```

### 7.2 验证硬件连接

```bash
# 验证 I2C
sudo i2cdetect -y 1  # 应看到 0x16

# 验证 GPIO
sudo lgpio info  # 应看到 gpiochip0 的信息

# 验证摄像头
v4l2-ctl -d /dev/video0 --list-formats-ext | head -20
```

### 7.3 启动基础节点测试

```bash
# 启动基础硬件层
ros2 launch raspbot_bringup base_bringup.launch.py

# 在另一个终端中查看节点
ros2 node list

# 查看 topic
ros2 topic list
```

---

## 常见问题排查

### Q: `i2cdetect` 看不到 0x16

1. 确认底盘电源已打开（电池或外接电源）
2. 检查 I2C 排线是否正确插入
3. 尝试禁用 I2C 时钟拉伸：
   ```bash
   echo "dtparam=i2c_arm_baudrate=10000" | sudo tee -a /boot/firmware/config.txt
   sudo reboot
   ```

### Q: 摄像头无法打开 (`Cannot open camera`)

1. 确认摄像头已连接：`ls /dev/v4l/by-id/`
2. 确认设备路径在 YAML 配置中正确：检查 `line_follow.yaml` 中的 `camera_device`
3. 尝试直接用 v4l2-ctl 测试：
   ```bash
   v4l2-ctl -d /dev/video0 --stream-mmap --stream-count=1 --stream-to=test.raw
   ```
4. 如果 OpenCV 后端失败，系统会自动 fallback 到 v4l2-ctl（日志中可见 `backend=v4l2ctl`）

### Q: `lgpio` 报错 `GPIO not initialized`

1. 确认 `/dev/gpiochip0` 存在
2. 检查是否有僵尸进程占用 GPIO：
   ```bash
   lsof /dev/gpiochip0
   ```
3. 如果有残留进程，运行清理脚本：
   ```bash
   ~/ros2_ws/cleanup_gpio.sh
   ```

### Q: `colcon build` 失败

1. 确认 ROS2 环境已加载：`source /opt/ros/jazzy/setup.bash`
2. 确认 Python 依赖已安装：`pip list | grep -E "smbus|lgpio|opencv"`
3. 清理重新编译：
   ```bash
   cd ~/ros2_ws && ./build.sh
   ```

### Q: 小车不动

1. 检查底盘电源
2. 确认 `base_driver_node` 在运行：`ros2 node list | grep base_driver`
3. 检查是否有安全接管活跃：`ros2 topic echo /safety_override_active`
4. 手动发送测试指令：
   ```bash
   ros2 topic pub --once /cmd_vel geometry_msgs/msg/Twist "{linear: {x: 0.1}, angular: {z: 0.0}}"
   ```

### Q: GPIO 资源被锁定 (`/dev/gpiochip0 device or resource busy`)

```bash
# 运行清理脚本
~/ros2_ws/cleanup_gpio.sh

# 如果仍然锁定，手动检查
lsof /dev/gpiochip0
# 终止列出的进程
```

---

## 开发工作流

### 修改代码后

```bash
cd ~/ros2_ws
./build.sh --packages-select raspbot_base  # 只编译改动的包
source install/setup.bash
```

### 调试单个节点

```bash
# 直接运行节点（不通过 launch）
ros2 run raspbot_vision line_follow_node --ros-args -p loop_hz:=5.0

# 查看节点日志
ros2 run raspbot_vision line_follow_node --ros-args --log-level debug
```

### 运行时调参

```bash
# 列出某节点的所有参数
ros2 param list /raspbot_line_follow

# 获取参数值
ros2 param get /raspbot_line_follow forward_speed

# 动态修改参数（无需重启）
ros2 param set /raspbot_line_follow forward_speed 0.15
```

---

## 工作区路径、离线验证与回板

主要 Python 节点的运行数据、检测模型和 Agent 审计路径由 `RASPBOT_WS` 定位；未设置时默认 `~/ros2_ws`。使用非默认目录时，在加载 ROS 环境前设置：

```bash
export RASPBOT_WS="$HOME/ros2_ws"
cd "$RASPBOT_WS"
source install/setup.bash
```

在 Windows 或 WSL 上做不接硬件的验证，请使用 [OFFLINE_VERIFICATION.md](OFFLINE_VERIFICATION.md)。当前 Windows 检查并不证明 ROS 节点、GPIO、I2C、摄像头或整车已运行。树莓派上完成构建后，请逐项执行 [PI_VALIDATION_CHECKLIST.md](PI_VALIDATION_CHECKLIST.md)，尤其是底盘有限数值保护、Agent 新鲜超声波准入和 Dashboard 远程控制授权。

`tools/openclaw/*.sh`、部分 systemd 与运维脚本仍假设 Linux 默认工作区布局；迁移工作区前应检查它们的路径，而不是只设置 `RASPBOT_WS`。
