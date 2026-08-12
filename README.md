# Raspbot ROS2 — 基于树莓派的自主巡逻机器人

[![Platform](https://img.shields.io/badge/platform-Raspberry%20Pi%204B-red)]()
[![ROS2](https://img.shields.io/badge/ROS2-Jazzy-blue)]()
[![Python](https://img.shields.io/badge/python-3.12-green)]()
[![License](https://img.shields.io/badge/license-Proprietary-lightgrey)]()

基于 **ROS2 Jazzy** 的 Yahboom Raspbot 智能小车系统。支持**视觉/红外循线**、**超声波/红外避障**、**云台巡逻人体检测**三大功能线，具备多层安全保护机制。

<p align="center">
  <i>摄像头采集 → 视觉感知 → 决策控制 → I2C 底盘驱动</i>
</p>

---

## 目录

- [功能特性](#功能特性)
- [硬件清单](#硬件清单)
- [快速开始](#快速开始)
- [项目结构](#项目结构)
- [运行方式](#运行方式)
- [文档索引](#文档索引)

---

## 功能特性

### 已实现的完整功能

| 功能 | 描述 | 技术栈 |
|------|------|--------|
| **视觉循线** | USB 摄像头 + OpenCV 黑线检测，滑动窗口平滑 + 多数投票去抖 | OpenCV, V4L2 |
| **红外循迹** | 4 路红外传感器，加权误差线性控制 | lgpio, GPIO |
| **超声波避障** | HC-SR04 测距，障碍物检测后自动接管：后退 → 转向 → 确认安全 → 释放 | lgpio, 中值滤波 |
| **红外避障** | 左右红外传感器，支持单侧/双侧避障策略 | lgpio, GPIO |
| **巡逻人体检测** | 云台三角度扫描 + 人体检测（HOG / TF-SSD / YOLOv8 ONNX 可切换），多帧去抖 + 强信号判定 | OpenCV DNN, ONNX Runtime, TensorFlow |
| **定时调度** | 支持时间段窗口 + 定时间隔自动巡逻 | ROS2 Timer |
| **事件记录** | SQLite 持久化巡逻事件和检测结果，支持增量 schema 迁移 | sqlite3 |
| **键盘遥控** | WASD 键盘控制小车移动 | termios, tty |
| **Web 远程监控** | 浏览器实时监控 + 虚拟摇杆遥控，单 HTML 文件 | aiohttp, WebSocket, MJPEG |
| **多轮确认** | 连续 N 次 occupied/empty 才确认状态，降低单次误报 | patrol_behavior_node (P3) |
| **告警保持** | 确认有人后 LED/蜂鸣器保持 N 秒，结果可见 | patrol/alert topic |
| **语音播报** | 检测结果 TTS 语音播报（espeak-ng），含冷却限流 | voice_announce_node |
| **远程通知** | 检测到人→Webhook 推送（钉钉/企微/泛用，默认关闭） | remote_notify_node, requests |
| **自动日报** | Jinja2 Markdown 巡检日报，支持日期范围和异常统计 | generate_patrol_report.py |
| **开机自启** | systemd 服务，上电自动启动 patrol_full.launch.py | scripts/patrol-systemd-install.sh |
| **移动巡逻** | 轻量固定路线移动巡逻，时间片动作控制，stop-and-scan | route_patrol_node |
| **超时重试** | 每个扫描角度检测超时后自动重试，减少 uncertain | patrol_behavior_node (P3) |

### 安全机制（多层设计）

```
cmd_vel 看门狗超时停车
    ↓ 被覆盖时
safety_cmd_vel 安全指令优先（超声波/红外避障）
    ↓ 互相仲裁
红外避障 ←→ 超声波避障（互斥，防冲突）
    ↓ 触发时
硬件告警：LED 变色 + 蜂鸣器
    ↓ 最终防线
GPIO 清理脚本（异常崩溃后强制释放）
```

---

## 硬件清单

| 组件 | 型号/规格 | 用途 |
|------|----------|------|
| 主控 | Raspberry Pi 4B 8GB | 运行 ROS2 |
| 操作系统 | Ubuntu Server 24.04 | - |
| 小车底盘 | Yahboom Raspbot | 含 I2C 驱动板、4 路红外、2 路红外避障 |
| USB 摄像头 | Generic HD Camera (USB V4L2) | 视觉循线 / 人体检测 |
| 超声波模块 | HC-SR04 | 前方测距避障 |
| 舵机云台 | 2 轴舵机 (Pan/Tilt) | 巡逻时多角度扫描 |
| 蜂鸣器 | 有源蜂鸣器 | 告警反馈 |
| LED | 双色 LED | 状态指示 |

> 完整 GPIO 引脚映射和接线参考见 [docs/HARDWARE.md](docs/HARDWARE.md)

---

## 快速开始

### 1. 环境要求

- Ubuntu Server 24.04 (已安装于 Raspberry Pi 4B)
- ROS2 Jazzy
- Python 3.12
- I2C 已启用（`/dev/i2c-1` 可用）

### 2. 安装依赖

```bash
# 系统依赖（完整清单见 apt-deps.txt）
sudo apt update
sudo apt install -y python3-pip python3-smbus python3-lgpio \
    python3-opencv python3-aiohttp python3-jinja2 ros-jazzy-ament-index-python \
    v4l-utils i2c-tools

# Python 运行依赖（ROS 2 自带包不在 requirements 中）
pip install -r requirements-runtime.txt
```

### 3. 编译项目

```bash
cd ~/ros2_ws
./build.sh
source install/setup.bash
```

> `build.sh` 会自动修复 ament_python 包的环境发现问题，无需再运行 `fix_ros_env.sh`。

### 4. 人体检测模型（巡逻功能需要）

为避免仓库携带大体积权重，模型文件不随 GitHub 仓库发布。运行人体检测前，在 `models/person_detection/` 放入所需文件：
- `frozen_inference_graph.pb` — TensorFlow SSD MobileNet v1
- `ssd_mobilenet_v1_coco_2017_11_17.pbtxt` — 配置文件
- `yolov8n.onnx` — 416×416 YOLOv8 ONNX 模型

YOLOv8 模型可使用 `bash download_yolov8_model.sh` 导出/下载；TF-SSD 的获取步骤见 [docs/SETUP.md](docs/SETUP.md)。详细模型发布约定见 [models/README.md](models/README.md)。

如需重新下载：

**TF-SSD 模型：**
```bash
cd /tmp
wget http://download.tensorflow.org/models/object_detection/ssd_mobilenet_v1_coco_2017_11_17.tar.gz
tar -xzf ssd_mobilenet_v1_coco_2017_11_17.tar.gz
cp ssd_mobilenet_v1_coco_2017_11_17/frozen_inference_graph.pb ~/ros2_ws/models/person_detection/
```

**YOLOv8n 模型（可选，推荐）：**
```bash
cd ~/ros2_ws
bash download_yolov8_model.sh
# 依赖：pip install onnxruntime --break-system-packages
```

---

## 项目结构

```
ros2_ws/
├── src/
│   ├── raspbot_base/              # 底层硬件驱动包
│   │   ├── config/                # YAML 参数配置（8 个文件）
│   │   │   ├── base_driver.yaml       # 底盘驱动参数
│   │   │   ├── gimbal_servo.yaml      # 云台舵机参数
│   │   │   ├── buzzer.yaml            # 蜂鸣器参数
│   │   │   ├── status_led.yaml        # LED 参数
│   │   │   ├── hardware_alert.yaml    # 硬件告警参数
│   │   │   ├── line_tracker.yaml      # 红外循迹传感器参数
│   │   │   ├── ir_line_follow.yaml    # 红外循迹控制参数
│   │   │   └── ir_obstacle.yaml       # 红外避障传感器参数
│   │   └── raspbot_base/
│   │       ├── yb_pcb_car.py              # I2C 底盘驱动（地址 0x16）
│   │       ├── base_driver_node.py        # 底盘速度控制 + 看门狗 + 安全仲裁
│   │       ├── line_tracker_node.py       # 4 路红外循迹传感器
│   │       ├── ir_line_follow_node.py     # 红外循迹决策
│   │       ├── ir_obstacle_node.py        # 红外避障传感器
│   │       ├── gimbal_servo_node.py       # 两轴云台舵机
│   │       ├── buzzer_node.py             # 蜂鸣器
│   │       ├── status_led_node.py         # 双色状态灯
│   │       ├── hardware_alert_node.py     # 硬件告警协调
│   │       └── teleop_keyboard_node.py    # 键盘遥控
│   │
│   ├── raspbot_vision/            # 视觉感知与行为包
│   │   ├── config/                # YAML 参数配置（10 个文件）
│   │   └── raspbot_vision/
│   │       ├── usb_camera.py              # USB 摄像头（OpenCV + v4l2-ctl 双后端）
│   │       ├── line_detector.py           # 黑线检测（ROI + 阈值 + 轮廓）
│   │       ├── decision.py                # 决策器（去抖 + 滑动窗口 + 投票）
│   │       ├── line_follow_node.py        # 视觉循线节点
│   │       ├── ultrasonic_range_node.py   # 超声波测距（HC-SR04）
│   │       ├── obstacle_avoid_node.py     # 超声波避障安全节点
│   │       ├── ir_obstacle_avoid_node.py  # 红外避障安全节点
│   │       ├── detector_backends.py       # 人体检测后端工厂（HOG/DNN）
│   │       ├── person_detect_node.py      # 人体检测节点（连续/触发模式）
│   │       ├── patrol_behavior_node.py    # 巡逻行为状态机
│   │       ├── patrol_scheduler_node.py   # 巡逻定时调度
│   │       ├── patrol_logger_node.py      # 巡逻 SQLite 日志
│   │       ├── web_dashboard_node.py       # Web 远程监控面板
│   │       └── compare_person_detectors.py # 检测器性能对比工具
│   │       └── web_dashboard/             # 监控面板前端页面
│   │
│   └── raspbot_bringup/           # 启动编排包
│       └── launch/                # 11 个 ROS2 launch 文件
│
├── models/
│   └── person_detection/          # 人体检测模型文件
│
├── data/patrol/                   # 巡逻运行时数据
│   ├── patrol_events.db           # SQLite 事件数据库
│   ├── exports/                   # 数据导出
│   └── benchmarks/                # 检测器性能对比结果
│
├── scripts/                        # 工具脚本
│   └── patrol-systemd-install.sh    # systemd 开机自启安装
├── cleanup_gpio.sh                # GPIO 资源紧急清理脚本
├── download_yolov8_model.sh       # YOLOv8n ONNX 模型下载
└── docs/                          # 项目文档
    ├── ARCHITECTURE.md            # 架构设计文档
    ├── SETUP.md                   # 详细环境搭建指南
    └── HARDWARE.md                # 硬件接线参考
```

---

## 运行方式

### 基础启动（底盘 + 所有传感器）

```bash
ros2 launch raspbot_bringup base_bringup.launch.py
```

### 视觉循线

```bash
# 纯视觉循线
ros2 launch raspbot_bringup line_follow.launch.py

# 视觉循线 + 超声波避障保护
ros2 launch raspbot_bringup line_follow_safe.launch.py
```

### 红外循迹

```bash
# 纯红外循迹
ros2 launch raspbot_bringup ir_line_follow.launch.py

# 红外循迹 + 超声波避障保护
ros2 launch raspbot_bringup ir_line_follow_safe.launch.py
```

### 巡逻人体检测

```bash
# 仅检测 + 日志（不控制小车）
ros2 launch raspbot_bringup patrol_detection.launch.py

# 完整巡逻（底盘 + 避障 + 检测 + 云台 + 调度）
ros2 launch raspbot_bringup patrol_full.launch.py

# 使用 HOG 检测器（无需模型文件）
ros2 launch raspbot_bringup patrol_full_hog.launch.py

# 使用 TF-SSD 检测器（需要模型文件）
ros2 launch raspbot_bringup patrol_full_tf_ssd.launch.py

# 使用 YOLOv8n ONNX 检测器（需要模型文件，推荐）
ros2 launch raspbot_bringup patrol_full_yolov8.launch.py

# 移动巡逻（时间片路线 + 定点巡检）
ros2 launch raspbot_bringup route_patrol.launch.py
```

### 键盘遥控

```bash
ros2 run raspbot_base teleop_keyboard_node
# W:前进  S:后退  A:左转  D:右转  X:停止  Q:退出
```

### Web 远程监控面板

```bash
# 默认只监听本机（http://127.0.0.1:8080），仅提供监控。
ros2 run raspbot_vision web_dashboard_node
```

Dashboard 提供：
- 📷 **实时摄像头画面**（MJPEG 流，自动发现 camera topic）
- 📡 **传感器仪表盘**（超声波距离条、速度表、角速度表）
- 🎮 **虚拟摇杆遥控**（支持鼠标点击和键盘 WASD/方向键）
- 🔔 **状态指示灯**（人体检测、巡逻中、安全接管）

> Dashboard 不需要额外安装任何前端依赖，单个 HTML 文件，启动即用。远程控制默认关闭；如需在受信任局域网启用，显式设置 `DASHBOARD_HOST=0.0.0.0`、`DASHBOARD_ENABLE_CONTROL=1` 和高强度 `DASHBOARD_TOKEN`，随后通过 `http://<树莓派IP>:8080/?token=<DASHBOARD_TOKEN>` 打开页面。

### 工作区路径

运行时数据、模型和 Agent 审计日志使用 `RASPBOT_WS` 环境变量定位；未设置时默认 `~/ros2_ws`。如果工作区改名或复制到其他位置，在启动前设置：

```bash
export RASPBOT_WS="$HOME/projects/ros2_ws_clean"
```

### 语音播报 & 远程通知

```bash
# 语音播报（订阅 patrol/alert，检测到人自动播放）
ros2 run raspbot_vision voice_announce_node

# 远程通知（需先配置 webhook_url）
# 编辑 config/remote_notify.yaml，设置 webhook_url + enabled: true；钉钉 secret 会用于请求签名
ros2 run raspbot_vision remote_notify_node
```

> 通知发送在后台线程执行，避免阻塞 ROS 回调；默认仍关闭。启用后应先向测试 webhook 验证冷却、重试和签名，再接入生产群组。

> 完整巡逻已内置这两个节点（patrol_full.launch.py 自动启动）

### 生成巡检日报

```bash
# 今日日报（终端输出）
python3 -m raspbot_vision.generate_patrol_report

# 导出 Markdown 文件
python3 -m raspbot_vision.generate_patrol_report -o ~/patrol_report_$(date +%Y%m%d).md

# 指定日期范围
python3 -m raspbot_vision.generate_patrol_report --days 7 -o weekly_report.md
```

### 开机自启

```bash
# 安装 systemd 服务（需要 root）
sudo bash scripts/patrol-systemd-install.sh

# 启动
sudo systemctl start patrol

# 查看日志
sudo journalctl -u patrol -f
```

### 运行时动态调参

```bash
# 查看所有节点参数
ros2 param list

# 修改避障距离阈值
ros2 param set /raspbot_obstacle_avoid stop_distance 0.25

# 修改循线速度
ros2 param set /raspbot_line_follow forward_speed 0.15
```

---

## 文档索引

| 文档 | 内容 |
|------|------|
| [README.md](README.md) | 项目总览、快速开始（本文档） |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | 系统架构、节点拓扑、数据流、安全设计 |
| [docs/SETUP.md](docs/SETUP.md) | 详细环境搭建、依赖安装、常见问题排查 |
| [docs/HARDWARE.md](docs/HARDWARE.md) | 硬件清单、GPIO 引脚映射、I2C 协议说明 |
| [docs/ROUTE_PATROL.md](docs/ROUTE_PATROL.md) | 移动巡逻使用指南、路线配置、安全注意事项 |
| [docs/AGENT_COMMAND_GATEWAY.md](docs/AGENT_COMMAND_GATEWAY.md) | Agent 命令接口、当前准入语义与审计 |
| [docs/AGENT_SAFETY.md](docs/AGENT_SAFETY.md) | Agent 与底盘、传感器之间的安全边界 |
| [docs/OFFLINE_VERIFICATION.md](docs/OFFLINE_VERIFICATION.md) | Windows/WSL 离线验证范围与复跑命令 |
| [docs/PI_VALIDATION_CHECKLIST.md](docs/PI_VALIDATION_CHECKLIST.md) | 树莓派回板、实机和安全回归清单 |
| [docs/GITHUB_PUBLISHING.md](docs/GITHUB_PUBLISHING.md) | GitHub 发布范围、忽略规则与首次提交检查 |
