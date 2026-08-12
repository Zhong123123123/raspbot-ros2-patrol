# Raspbot ROS2 小车使用说明

本文档对应新系统上的 ROS 2 Jazzy 小车环境，主机为树莓派 `ubuntu@192.168.1.100`，ROS 工作区为 `~/ros2_ws`。

当前文档内容已经按 2026-07-03 的远端实测结果更新，包含基础硬件、巡检闭环、GPIO 清理和停机收尾修复后的最终可用状态。

## 0. 系统架构

这块 Raspbot 底板不是“纯树莓派直驱”，而是“树莓派 + 底板单片机（MCU）”的混合架构。

职责大致分工如下：

- 树莓派：
  - 运行 Ubuntu 24.04 + ROS 2 Jazzy
  - 负责视觉、策略、节点通信、上层控制
  - 直接访问一部分板载 GPIO 外设
- 底板 MCU：
  - 负责一部分底层硬件驱动
  - 通过 `I2C` 与树莓派通信

当前项目里的对应关系：

- 通过底板 MCU 驱动：
  - 底盘电机
  - 舵机接口
- 由树莓派 GPIO 直接控制/读取：
  - 蜂鸣器
  - 状态灯
  - 红外避障
  - 巡线传感器
  - 超声波触发/回波

补充说明：

- 当前底盘控制板 I2C 地址为 `0x16`
- 文档中的 MCU 状态灯，表示底层单片机是否正常运行

## 1. 当前已完成的基础硬件节点

- 底盘驱动：`raspbot_base/base_driver_node`
- 云台舵机：`raspbot_base/gimbal_servo_node`
- 蜂鸣器：`raspbot_base/buzzer_node`
- 状态灯：`raspbot_base/status_led_node`
- 硬件告警联动：`raspbot_base/hardware_alert_node`
- 巡线传感器读取：`raspbot_base/line_tracker_node`
- 红外巡线跟随：`raspbot_base/ir_line_follow_node`
- 红外避障模块读取：`raspbot_base/ir_obstacle_node`
- 红外避障接管：`raspbot_vision/ir_obstacle_avoid_node`
- 超声波测距：`raspbot_vision/ultrasonic_range_node`
- 超声波避障接管：`raspbot_vision/obstacle_avoid_node`
- 摄像头巡线：`raspbot_vision/line_follow_node`
- 人体检测：`raspbot_vision/person_detect_node`
- 巡检日志：`raspbot_vision/patrol_logger_node`
- 定时巡检调度：`raspbot_vision/patrol_scheduler_node`
- 巡检行为编排：`raspbot_vision/patrol_behavior_node`
- 键盘遥控：`raspbot_base/teleop_keyboard_node`

## 2. 编译与环境加载

在树莓派上执行：

```bash
cd ~/ros2_ws
./build.sh
source ~/ros2_ws/install/setup.bash
```

说明：

- `build.sh` 会在 `colcon build` 后自动修复 ament_python 包的环境发现问题，确保 `ros2 pkg list` 能正确识别三个 raspbot 包。
- 如果只改了某个包，可以加 `--packages-select` 参数缩小编译范围：`./build.sh --packages-select raspbot_vision`
- 旧版 `fix_ros_env.sh` 仍保留在仓库中，可作为手动修复的后备方案。

日常新开终端后：

```bash
source /opt/ros/jazzy/setup.bash
source ~/ros2_ws/install/setup.bash
```

## 3. 常用启动命令

### 3.1 基础硬件

```bash
ros2 launch raspbot_bringup base_bringup.launch.py
```

会启动：

- `base_driver_node`
- `gimbal_servo_node`
- `buzzer_node`
- `status_led_node`
- `hardware_alert_node`
- `line_tracker_node`
- `ir_obstacle_node`
- `ir_obstacle_avoid_node`

### 3.2 超声波安全避障 + 摄像头巡线

```bash
ros2 launch raspbot_bringup line_follow_safe.launch.py
```

### 3.3 纯摄像头巡线

```bash
ros2 launch raspbot_bringup line_follow.launch.py
```

### 3.4 红外巡线 + 超声波安全避障

```bash
ros2 launch raspbot_bringup ir_line_follow_safe.launch.py
```

### 3.5 纯红外巡线

```bash
ros2 launch raspbot_bringup ir_line_follow.launch.py
```

### 3.6 键盘遥控

```bash
ros2 run raspbot_base teleop_keyboard_node
```

### 3.7 定时巡检检测

```bash
source /opt/ros/jazzy/setup.bash
source ~/ros2_ws/install/setup.bash
ros2 launch raspbot_bringup patrol_detection.launch.py
```

会启动：

- `person_detect_node`
- `patrol_logger_node`
- `patrol_scheduler_node`

### 3.7.1 TensorFlow SSD 人体检测版

```bash
source /opt/ros/jazzy/setup.bash
source ~/ros2_ws/install/setup.bash
ros2 launch raspbot_bringup patrol_detection.launch.py
```

从 2026-07-03 起，默认检测链路已经切到 `opencv_dnn_tf_ssd`。

如果要显式启动旧版 HOG 回退链路：

```bash
source /opt/ros/jazzy/setup.bash
source ~/ros2_ws/install/setup.bash
ros2 launch raspbot_bringup patrol_detection_hog.launch.py
```

### 3.8 完整办公室巡检闭环

```bash
~/ros2_ws/cleanup_gpio.sh
source /opt/ros/jazzy/setup.bash
source ~/ros2_ws/install/setup.bash
ros2 launch raspbot_bringup patrol_full.launch.py
```

会启动：

- `base_bringup.launch.py` 内的基础硬件节点
- `ultrasonic_range_node`
- `obstacle_avoid_node`
- `person_detect_node`
- `patrol_logger_node`
- `patrol_scheduler_node`
- `patrol_behavior_node`

如果要用旧版 HOG 跑完整巡检闭环，可改用：

```bash
~/ros2_ws/cleanup_gpio.sh
source /opt/ros/jazzy/setup.bash
source ~/ros2_ws/install/setup.bash
ros2 launch raspbot_bringup patrol_full_hog.launch.py
```

这是当前已经完成远端长时间实测的主启动方式。

### 3.8.1 完整办公室巡检闭环 TensorFlow SSD 版

```bash
~/ros2_ws/cleanup_gpio.sh
source /opt/ros/jazzy/setup.bash
source ~/ros2_ws/install/setup.bash
ros2 launch raspbot_bringup patrol_full_tf_ssd.launch.py
```

### 3.9 Web 远程监控面板

```bash
# 先启动小车功能（如 patrol_full）
~/ros2_ws/cleanup_gpio.sh
source /opt/ros/jazzy/setup.bash
source ~/ros2_ws/install/setup.bash
ros2 launch raspbot_bringup patrol_full.launch.py

# 另开终端启动 Dashboard
source /opt/ros/jazzy/setup.bash
source ~/ros2_ws/install/setup.bash
ros2 run raspbot_vision web_dashboard_node
```

打开浏览器访问 `http://<树莓派IP>:8080`，面板提供：

- 📷 **实时摄像头画面**（MJPEG 流）
- 📡 **传感器仪表盘**（超声波距离、速度、角速度）
- 🎮 **虚拟摇杆遥控**（鼠标/键盘双控）
- ✅ **确认状态指示器**（`Confirmed: OCCUPIED` / `Confirmed: empty` / `Monitoring...`）
- ⚠️ **告警横幅**（确认有人时红色闪烁条）
- 🔔 **状态指示灯**（人体检测、巡逻中、安全接管）

## 4. 节点与话题清单

### 4.1 底盘与控制

`raspbot_base/base_driver_node`

- 订阅 `/cmd_vel`：常规速度控制，类型 `geometry_msgs/msg/Twist`
- 订阅 `/safety_cmd_vel`：安全接管速度控制，类型 `geometry_msgs/msg/Twist`
- 发布 `/wheel_speeds`：左右轮速度状态

规则：

- 当安全避障节点正在输出 `/safety_cmd_vel` 时，底盘优先执行安全接管速度。

### 4.2 云台舵机

`raspbot_base/gimbal_servo_node`

- 订阅 `/gimbal_cmd`，类型 `geometry_msgs/msg/Vector3`
- 发布 `/gimbal_joint_states`

说明：

- 当前用 `Vector3` 的 `x/y` 控制两个舵机角度。

### 4.3 蜂鸣器

`raspbot_base/buzzer_node`

- 订阅 `/buzzer_cmd`，类型 `std_msgs/msg/Bool`
- 订阅 `/buzzer_beep_ms`，类型 `std_msgs/msg/UInt16`

说明：

- 现在默认是静音安全策略，不会自己持续响。
- 只能做开/关和定时鸣叫，不能做真正的音量调节。

### 4.4 状态灯

`raspbot_base/status_led_node`

- 订阅 `/status_led_cmd`，类型 `std_msgs/msg/ColorRGBA`

当前映射：

- `LED1` 红灯：BCM `21`，物理脚 `40`
- `LED2` 蓝灯：BCM `20`，物理脚 `38`

补充：

- 这两个是板载状态灯，不是车头前面的红外避障传感器。
- 当前配置按低电平点亮处理。

测试命令：

```bash
ros2 topic pub --once /status_led_cmd std_msgs/msg/ColorRGBA "{r: 1.0, g: 0.0, b: 0.0, a: 1.0}"
ros2 topic pub --once /status_led_cmd std_msgs/msg/ColorRGBA "{r: 0.0, g: 0.0, b: 1.0, a: 1.0}"
ros2 topic pub --once /status_led_cmd std_msgs/msg/ColorRGBA "{r: 0.0, g: 0.0, b: 0.0, a: 1.0}"
```

### 4.5 超声波测距与安全避障

`raspbot_vision/ultrasonic_range_node`

- 发布 `/ultrasonic/front`

`raspbot_vision/obstacle_avoid_node`

- 订阅 `/ultrasonic/front`
- 订阅 `/patrol/active`
- 发布 `/safety_cmd_vel`
- 发布 `/safety_override_active`，类型 `std_msgs/msg/Bool`

当前逻辑：

- 超声波真触发后，直接接管底盘。
- 障碍解除到安全阈值后，再退出接管。
- 当 `/patrol/active=true` 时，超声波避障会临时释放接管，避免云台巡检阶段反复打断底盘控制。

### 4.6 巡线传感器

`raspbot_base/line_tracker_node`

- 发布 `/line_tracker`，类型 `std_msgs/msg/Int32MultiArray`

数据格式：

- 4 路数组，当前默认顺序为左到右
- 常见实测示例：`[0, 1, 1, 1]`

### 4.7 红外巡线跟随

`raspbot_base/ir_line_follow_node`

- 订阅 `/line_tracker`
- 发布 `/cmd_vel`

当前默认控制思路：

- 中间压线时前进
- 左偏时左转修正
- 右偏时右转修正
- 全丢线时小角速度搜索

### 4.8 红外避障模块

`raspbot_base/ir_obstacle_node`

- 发布 `/ir_obstacle`，类型 `std_msgs/msg/Int32MultiArray`
- 发布 `/ir_obstacle/left`，类型 `std_msgs/msg/Bool`
- 发布 `/ir_obstacle/right`，类型 `std_msgs/msg/Bool`

当前引脚：

- 左红外避障：BCM `10`
- 右红外避障：BCM `9`
- 模块使能：BCM `25`

当前极性：

- `sensor_active_low = true`
- `enable_active_high = true`

已确认：

- 节点已完成编译安装。
- 远端实测能读到 `/ir_obstacle`
- 当前车上左侧红外避障通道疑似硬件异常，长期处于触发态
- 右侧红外避障通道可随遮挡正常变化

单独测试命令：

```bash
ros2 run raspbot_base ir_obstacle_node --ros-args --params-file ~/ros2_ws/install/raspbot_base/share/raspbot_base/config/ir_obstacle.yaml
```

另开一个终端查看：

```bash
ros2 topic echo /ir_obstacle
ros2 topic echo /ir_obstacle/left
ros2 topic echo /ir_obstacle/right
```

注意：

- 如果它已经被 `base_bringup.launch.py` 启动，再手动起第二个实例会报 `GPIO busy`，这是正常的引脚占用冲突，不是驱动失效。

### 4.9 红外避障接管节点

`raspbot_vision/ir_obstacle_avoid_node`

- 订阅 `/ir_obstacle`
- 订阅 `/safety_override_active`
- 订阅 `/patrol/active`
- 发布 `/safety_cmd_vel`
- 发布 `/ir_safety_override_active`

当前策略：

- 当前按右侧单通道模式运行，左侧异常通道已在控制逻辑里忽略
- 右侧触发时：左转避让
- 动作结束后短暂停车，等待传感器恢复清空

与超声波的关系：

- 如果超声波避障已经发布 `/safety_override_active=true`，红外避障接管节点会让路，不再继续抢占控制。
- 如果巡检行为节点发布 `/patrol/active=true`，红外避障接管也会临时释放。

已确认：

- 节点已完成编译安装。
- 当前配置为 `left_enabled=false`、`right_enabled=true`
- 左侧红外异常不会再触发红外避障接管
- 可继续配合超声波避障作为主安全链路

### 4.10 人体检测节点

`raspbot_vision/person_detect_node`

- 发布 `/person_detected`，类型 `std_msgs/msg/Bool`
- 发布 `/person_detection/status`，类型 `std_msgs/msg/String`
- 发布 `/person_detection/result`，类型 `std_msgs/msg/String`
- 发布 `/person_detection/debug/compressed`
- 订阅 `/person_detection/enabled`
- 订阅 `/person_detection/trigger`

当前实现：

- 直接读取 USB 摄像头
- 当前检测器已经抽象成“可切换后端”结构
- 默认后端已经切到 `opencv_dnn_tf_ssd`
- HOG 作为回退链路保留
- 已预留 `opencv_dnn_ssd` 后端接入位
- 已实际接入并验证 `opencv_dnn_tf_ssd`
- 当前默认按“触发式检测”运行，由调度节点定时触发
- 节点启动时不会因为相机暂时不可用而直接崩溃，而是继续重试
- 优先使用 OpenCV 直接打开相机，失败时再回退到 `v4l2-ctl` 单帧抓图后端
- 当前已经加入结果去抖，避免人体检测在短时间内 `True/False` 来回抖动
- 当前已经支持检测截图证据链，会按时间把原图和检测框图保存到 `~/ros2_ws/data/patrol/images/YYYY-MM-DD/`
- 当配置了不可用的主检测后端时，会自动回退到 `detector_fallback_backend`

检测原理：

- 先从 USB 摄像头读取画面
- 再调用当前配置的 detector backend 做人体检测
- 当前默认 detector backend 是 `opencv_dnn_tf_ssd`
- HOG 回退 backend 仍然可用，内部使用 `HOGDescriptor + DefaultPeopleDetector`
- 单帧检测会输出候选框和置信度，再按阈值过滤掉弱检测和过小目标
- 每次调度触发时，不只看单帧，而是连续扫描几帧并取更优结果
- 最后再做时序去抖和状态保持，避免因为某几帧漏检就立刻从“有人”跳回“没人”

补充说明：

- 这套方案不是深度学习大模型，也不是人脸识别
- 它判断的是“画面里是否存在像人体的目标”，不是“这个人是谁”
- 当前默认方案 `opencv_dnn_tf_ssd` 属于轻量深度学习检测，比 HOG 更稳定，尤其更适合坐姿、半身和复杂背景
- HOG 的优点仍然是更轻、更省资源，所以保留为回退方案
- 这两套后端都不是人脸识别，也不做身份确认

当前相机状态：

- 当前配置使用稳定路径 `/dev/v4l/by-id/usb-Generic_HD_camera_20181212000000-video-index0`
- 2026-07-02 已完成相机读取稳定性修复
- 2026-07-03 已完成“设备号漂移 + 检测结果抖动”修复
- 远端实测日志已出现 `person detection camera ready via backend=opencv`
- 也验证过 `backend=v4l2ctl` 的回退路径可工作
- 设备号发生漂移时，节点会跟随 `/dev/v4l/by-id/...` 自动解析到当前真实设备

说明：

- 不要把巡检相机长期写死成 `/dev/video0` 或 `/dev/video1`
- 如果摄像头枚举顺序变化，优先看 `/dev/v4l/by-id/` 的稳定链接
- 用 `v4l2-ctl --list-devices` 可以辅助确认当前真实设备号

当前去抖参数：

- `min_weight: 0.60`
- `detect_on_frames: 1`
- `detect_off_frames: 3`
- `min_detect_hold_sec: 2.0`

当前后端参数：

- `detector_backend: hog`
- `detector_fallback_backend: hog`
- 后续可切到 `opencv_dnn_ssd`
- 当前也可切到 `opencv_dnn_tf_ssd`
- 切 `opencv_dnn_ssd` 时需要同时提供 `dnn_model_path` 和 `dnn_config_path`
- 切 `opencv_dnn_tf_ssd` 时同样需要提供 `dnn_model_path` 和 `dnn_config_path`
- 2026-07-03 已验证：当 `opencv_dnn_ssd` 未提供模型文件时，节点会自动回退到 `hog`
- 2026-07-03 已验证：`opencv_dnn_tf_ssd` 可成功加载 `frozen_inference_graph.pb + ssd_mobilenet_v1_coco_2017_11_17.pbtxt`
- 2026-07-03 已验证：`patrol_detection_tf_ssd.launch.py` 能正常启动，并出现过 `detected=True, count=1, max_confidence=0.74`
- 2026-07-03 已验证：默认 `patrol_detection.launch.py` 已切到 `opencv_dnn_tf_ssd`
- 2026-07-03 已验证：`patrol_detection_hog.launch.py` 可作为显式回退入口继续使用

当前 TensorFlow SSD 模型文件：

- `~/ros2_ws/models/person_detection/frozen_inference_graph.pb`
- `~/ros2_ws/models/person_detection/ssd_mobilenet_v1_coco_2017_11_17.pbtxt`

当前建议阈值：

- `dnn_confidence_threshold: 0.45`
- 2026-07-03 在远端做过 `0.35 / 0.40 / 0.45 / 0.50` 的短帧对比
- 从当次样本看，`0.40 ~ 0.45` 明显比 `0.50` 更合适
- 当前先把 TF-SSD 配置默认收敛到 `0.45`

状态消息内容：

- UTC 时间
- 是否检测到人
- 检测人数
- 最大置信度
- 当前检测模式
- 相机后端
- 检测后端
- 错误信息
- `raw_image_path`
- `debug_image_path`

### 4.11 巡检行为编排节点

`raspbot_vision/patrol_behavior_node`

- 订阅 `/patrol/trigger`
- 订阅 `/person_detection/result`
- 发布 `/patrol/active`
- 发布 `/gimbal_cmd`
- 发布 `/person_detection/trigger`
- 发布 `/patrol/final_result`
- 发布 `/patrol/confirmed_status`（P3 新增）— 实时确认状态 JSON
- 发布 `/patrol/alert`（P4 新增）— 告警 Bool（true=确认有人）
- 发布 `/status_led_cmd`
- 发布 `/buzzer_beep_ms`
- 发布 `/cmd_vel`

当前实现：

- 收到一次巡检触发后，先停车
- 进入巡检状态时发布 `/patrol/active=true`
- 控制云台按左 / 中 / 右三个角度扫描
- 每个角度各触发一次人体检测
- 汇总三次结果后输出最终判断
- 结束后发布 `/patrol/active=false`
- `occupied` 时亮红灯并短鸣
- `empty` 时亮蓝灯
- `uncertain` 时红蓝同时亮并短鸣

最终结果消息内容：

- `patrol_id`
- `started_at_utc`
- `finished_at_utc`
- `final_decision`
- `detected`
- `positive_observation_count`
- `total_observation_count`
- `max_person_count`
- `max_confidence`
- `occupied_positions`
- `camera_backend`
- `detector_backend`
- `decision_reason`
- `error_msg`
- `observations`

当前判定策略：

- 三次扫描都没检出且没有报错时，判为 `empty`
- 没检出但存在报错时，判为 `uncertain`
- 多个角度都检出时，直接判为 `occupied`
- 单个角度检出但置信度足够高时，也判为 `occupied`
- 单个角度弱检出时，降级判为 `uncertain`

**P3 新增：多轮确认机制**

从 2026-07-03 起，patrol_behavior_node 增加了跨轮次确认逻辑：

- 每轮扫描结果（occupied/empty/uncertain）追加到 `round_history` 循环队列
- 当最近 `confirm_occupied_rounds`（默认 2）轮次全部为 occupied → 确认有人
- 当最近 `confirm_empty_rounds`（默认 3）轮次全部为 empty → 确认无人
- 确认结果为 occupied 时进入 OCCUPIED_HOLD 状态，维持灯+蜂鸣 `occupied_hold_sec` 秒
- 确认结果为 empty 时直接返回 IDLE
- 不确定（不足阈值或中间中断）时返回 IDLE，等待调度器下一轮触发
- 每个扫描角度超时后自动重试 `uncertain_retry_count`（默认 1）次

**P4 新增：patrol/confirmed_status 与 patrol/alert**

- `/patrol/confirmed_status`（String）：JSON 格式发布当前确认状态，包含 `confirmed_decision`（occupied/empty/none）、`is_confirmed`、`occupied_consecutive_rounds`、`empty_consecutive_rounds` 等字段
- `/patrol/alert`（Bool）：确认有人时发布 `true`，退出 OCCUPIED_HOLD 时发布 `false`。简化告警通知，其他模块只需订阅这个 Bool 即可联动

新参数（`config/patrol_behavior.yaml`）：

| 参数 | 默认值 | 说明 |
|------|:------:|------|
| `confirm_occupied_rounds` | 2 | 确认 occupied 所需连续轮次 |
| `confirm_empty_rounds` | 3 | 确认 empty 所需连续轮次 |
| `round_history_size` | 10 | 历史记录最大长度 |
| `occupied_hold_sec` | 15.0 | 确认有人后告警保持秒数 |
| `occupied_hold_beep_ms` | 200 | 告警蜂鸣时长 ms |
| `uncertain_retry_count` | 1 | 超时后重试次数 |

### 4.12 巡检日志节点

`raspbot_vision/patrol_logger_node`

- 订阅 `/person_detection/status`
- 订阅 `/patrol/final_result`
- 将检测结果写入 SQLite

当前数据库路径：

- `~/ros2_ws/data/patrol/patrol_events.db`

当前表结构包含：

- `timestamp_utc`
- `detected`
- `person_count`
- `max_confidence`
- `mode`
- `logged_at_utc`
- `camera_backend`
- `detector_backend`
- `error_msg`
- `raw_image_path`
- `debug_image_path`
- `scan_positive_frames`
- `scan_total_frames`

当前还会额外保存：

- `patrol_final_results` 表
- 每轮巡检的 `patrol_id`
- 最终判断 `final_decision`
- 正检角度数 `positive_observation_count`
- 本轮总观测数 `total_observation_count`
- 最大人数 / 最大置信度
- 检测到人的角度集合 `occupied_positions`
- 最终判定原因 `decision_reason`
- `patrol_observations` 表
- 每轮巡检左 / 中 / 右三个角度的单独观测
- 每条观测对应的 `scan_position`
- 每条观测对应的 `raw_image_path` 和 `debug_image_path`
- 每条观测对应的 `scan_positive_frames / scan_total_frames`

2026-07-03 远端已验证：

- `patrol_behavior_node` 生成的每个 `patrol_id`，都会在 `patrol_observations` 里落下 `left / center / right` 三条记录
- 每条记录都能对应到磁盘上的原图和调试图
- `patrol_final_results` 和 `patrol_observations` 可以按 `patrol_id` 关联起来查证据链

### 4.13 定时巡检调度节点

`raspbot_vision/patrol_scheduler_node`

- 发布 `/person_detection/enabled`
- 发布 `/person_detection/trigger` 或 `/patrol/trigger`

当前作用：

- 按时间窗控制是否允许检测
- 按固定周期触发一次检测或巡检流程

补充：

- `patrol_detection.launch.py` 中仍直接触发 `/person_detection/trigger`
- `patrol_full.launch.py` 中调度器改为触发 `/patrol/trigger`，再由 `patrol_behavior_node` 接管完整流程
- `patrol_full.launch.py` 里额外把 `interval_sec` 覆盖为 `20.0`，避免一轮云台扫描和反馈尚未结束时，下一轮调度又进来
- `patrol_behavior_node` 在巡检进行中会发布 `/patrol/active=true`，超声波/红外避障节点收到后会临时释放接管，尽量避免云台扫描阶段被底盘安全动作反复打断

默认参数：

- `interval_sec: 10.0`
- `active_start: 00:00`
- `active_end: 23:59`

## 5. 常用测试命令

### 5.1 查看节点

```bash
ros2 node list
```

### 5.1.1 清理 GPIO 残留

如果之前异常退出，导致 `GPIO busy`，先执行：

```bash
~/ros2_ws/cleanup_gpio.sh
```

仓库里也保留了一份同名脚本：[cleanup_gpio.sh](/home/zh/桌面/Yahboom_project/Raspbot/cleanup_gpio.sh)

当前脚本会：

- 停掉常见 ROS 启动和 GPIO 相关节点
- 额外检查 `/dev/gpiochip0` 的实际持有者
- 必要时强制清掉残留占用

因此建议在每次运行 `patrol_full.launch.py` 之前先执行一次。

### 5.1.2 查看最近巡检结果

直接查数据库：

```bash
sqlite3 ~/ros2_ws/data/patrol/patrol_events.db "select patrol_id, final_decision, max_person_count, max_confidence, occupied_positions, finished_at_utc from patrol_final_results order by id desc limit 10;"
```

查看每个角度的图片路径：

```bash
sqlite3 ~/ros2_ws/data/patrol/patrol_events.db "select patrol_id, scan_position, detected, person_count, max_confidence, raw_image_path, debug_image_path from patrol_observations order by id desc limit 9;"
```

或使用脚本：

```bash
~/ros2_ws/check_patrol_results.sh
~/ros2_ws/check_patrol_results.sh ~/ros2_ws/data/patrol/patrol_events.db 20
~/ros2_ws/check_patrol_results.sh ~/ros2_ws/data/patrol/patrol_events.db 9 observations
```

仓库里也保留了一份同名脚本：[check_patrol_results.sh](/home/zh/桌面/Yahboom_project/Raspbot/check_patrol_results.sh)

如果要做 HOG 和 TF-SSD 的性能/检出率对比，可在树莓派上运行：

```bash
python3 -m raspbot_vision.compare_person_detectors --frames 6 --output-json ~/ros2_ws/data/patrol/benchmarks/compare_default.json
```

当前脚本会输出：

- 每帧 `hog` 与 `opencv_dnn_tf_ssd` 的检测人数、最大置信度、单帧耗时
- 两个后端的平均耗时、最大耗时、检出帧比例
- JSON 结果文件，方便后续复盘

如果要做更细的筛选，使用 Python 查询工具：

```bash
python3 ~/ros2_ws/query_patrol_results.py --mode final --limit 20
python3 ~/ros2_ws/query_patrol_results.py --mode final --decision occupied --from-time 2026-07-03T00:00:00 --limit 20
python3 ~/ros2_ws/query_patrol_results.py --mode final --detector-backend opencv_dnn_tf_ssd --limit 20
python3 ~/ros2_ws/query_patrol_results.py --mode observations --detected true --limit 9
python3 ~/ros2_ws/query_patrol_results.py --mode observations --detector-backend opencv_dnn_tf_ssd --limit 9
python3 ~/ros2_ws/query_patrol_results.py --mode observations --patrol-id patrol_20260703T060254_118390 --csv ~/ros2_ws/data/patrol/patrol_observations.csv
```

仓库里对应文件是 [query_patrol_results.py](/home/zh/桌面/Yahboom_project/Raspbot/query_patrol_results.py)

2026-07-03 起，`query_patrol_results.py` 已补齐：

- `final` 视图中的 `positive_observation_count / total_observation_count / decision_reason`
- `observations` 视图中的 `scan_positive_frames / scan_total_frames`

常用排查方式：

- 先看最终结果：`check_patrol_results.sh`
- 再看三角度观测：`check_patrol_results.sh ~/ros2_ws/data/patrol/patrol_events.db 9 observations`
- 要按时间范围、结果类型、指定 `patrol_id` 或指定 `detector_backend` 精查时，用 `query_patrol_results.py`
- 最后直接打开 `raw_image_path` / `debug_image_path` 对应图片，看当时画面和框图是否一致

### 5.1.3 巡检链路交付自检

在树莓派上可直接执行：

```bash
bash ~/ros2_ws/patrol_delivery_check.sh
```

仓库里也保留了一份同名脚本：[patrol_delivery_check.sh](/home/zh/桌面/Yahboom_project/Raspbot/patrol_delivery_check.sh)

当前自检会检查：

- 默认后端是否仍是 `opencv_dnn_tf_ssd`
- TF-SSD 模型文件是否存在
- 巡检相机稳定路径是否存在
- 数据库里是否已经完成新字段迁移
- 最近几条 `final` 和 `observations` 记录能否正常查出

### 5.2 查看话题

```bash
ros2 topic list
ros2 topic info /ir_obstacle
ros2 topic echo --once /ir_obstacle
ros2 topic echo /ir_safety_override_active
ros2 topic echo /patrol/active
ros2 topic echo /person_detected
ros2 topic echo /person_detection/status
ros2 topic echo /person_detection/result
ros2 topic echo /patrol/final_result
ros2 topic echo /patrol/confirmed_status
ros2 topic echo /patrol/alert
```

### 5.3 底盘速度测试

```bash
ros2 topic pub /cmd_vel geometry_msgs/msg/Twist "{linear: {x: 0.10}, angular: {z: 0.0}}"
```

停车：

```bash
ros2 topic pub --once /cmd_vel geometry_msgs/msg/Twist "{linear: {x: 0.0}, angular: {z: 0.0}}"
```

### 5.4 蜂鸣器短鸣

```bash
ros2 topic pub --once /buzzer_beep_ms std_msgs/msg/UInt16 "{data: 80}"
```

### 5.5 红外巡线传感器查看

```bash
ros2 topic echo /line_tracker
```

## 6. 当前硬件映射摘要

- 底盘主控板 I2C 地址：`0x16`
- 巡检 USB 摄像头配置路径：`/dev/v4l/by-id/usb-Generic_HD_camera_20181212000000-video-index0`
- 巡检 USB 摄像头真实设备号：会随系统枚举变化，不建议写死
- 超声波 `Trig`：BCM `23`
- 超声波 `Echo`：BCM `24`
- 蜂鸣器：BCM `12`
- 红外接收：BCM `16`
- 状态灯红：BCM `21`
- 状态灯蓝：BCM `20`
- 红外避障左：BCM `9`
- 红外避障右：BCM `10`
- 红外避障使能：BCM `25`

## 7. 当前还没做的内容

- 电池电量/电压 ROS 节点
- 更完整的参数文档和默认值说明

当前系统已经完成并验证通过的主线能力：

- 新系统 ROS 2 Jazzy 基础硬件驱动
- 超声波与红外避障接管
- 云台三点扫描巡检
- USB 摄像头人体检测
- 定时巡检调度
- 巡检结果 SQLite 落库
- GPIO 清理脚本
- 巡检结果查询脚本

当前硬件备注：

- 左侧板载红外避障通道疑似异常，软件已临时按无效通道处理

当前结果解释方式：

- `occupied` 表示本轮巡检点检测到有人
- `empty` 表示本轮巡检点未检测到人
- `occupied_positions` 表示哪些扫描角度检测到人，不表示严格的人体精确定位

## 8. 常见故障排查

### 8.1 `GPIO busy`

现象：

- 启动 `base_bringup.launch.py` 时，`buzzer_node`、`status_led_node`、`line_tracker_node`、`ir_obstacle_node` 报 `lgpio.error: 'GPIO busy'`
- 启动 `patrol_full.launch.py` 时，`ultrasonic_range_node` 报 `lgpio.error: 'GPIO busy'`

原因：

- 之前异常退出，旧的 GPIO 节点残留在后台，没有释放 `/dev/gpiochip0`

处理：

```bash
~/ros2_ws/cleanup_gpio.sh
```

然后重新启动：

```bash
ros2 launch raspbot_bringup base_bringup.launch.py
```

如果是办公室巡检闭环，推荐直接按下面完整顺序重来：

```bash
~/ros2_ws/cleanup_gpio.sh
source /opt/ros/jazzy/setup.bash
source ~/ros2_ws/install/setup.bash
ros2 launch raspbot_bringup patrol_full.launch.py
```

### 8.2 `can not open gpiochip`

现象：

- 启动时直接报 `lgpio.error: 'can not open gpiochip'`

原因：

- 当前登录会话没有拿到正确的设备访问权限，或系统状态异常

处理：

```bash
exit
ssh ubuntu@192.168.1.100
id
```

确认输出里包含 `dialout`，再测试：

```bash
python3 - <<'PY'
import lgpio
h = lgpio.gpiochip_open(0)
print('ok', h)
lgpio.gpiochip_close(h)
PY
```

### 8.3 红外避障左侧一直触发

现象：

- `/ir_obstacle/left` 长期为 `true`
- 右侧可正常随遮挡变化

当前结论：

- 左侧板载红外避障通道疑似硬件异常
- 软件已临时按无效通道处理，不再让左侧参与红外避障接管

当前策略：

- `ir_obstacle_node` 仍保留左右原始读取发布
- `ir_obstacle_avoid_node` 当前只使用右侧有效通道
- 超声波仍作为主安全接管链路

### 8.4 状态灯日志看起来像“没启用”

现象：

- 以前日志会显示 `status led node started (disabled by default...)`

说明：

- 那是早期遗留文案，不代表功能真的被禁用
- 现在已改成输出真实配置，例如 `enabled=True, led1_gpio=21, led2_gpio=20`

### 8.5 手动单起节点后，再次 launch 报冲突

现象：

- 手动 `ros2 run ...` 某个 GPIO 节点后，再启动 `base_bringup.launch.py` 报冲突

原因：

- 同一类节点重复启动，GPIO 已被前一个实例占用

处理：

- 优先在同一个终端里用 `Ctrl+C` 正常退出
- 如果已经留下残留，执行：

```bash
~/ros2_ws/cleanup_gpio.sh
```

当前系统已经按这个思路实现：

- `ir_obstacle_node` 只负责读取硬件并发布 `/ir_obstacle`
- `ir_obstacle_avoid_node` 负责消费 `/ir_obstacle` 并发布 `/safety_cmd_vel`

如果后面继续扩展，建议继续保持这种“感知节点”和“控制策略节点”分离的结构，不要把避障动作逻辑重新写回传感器节点里。

### 8.6 `Package 'raspbot_bringup' not found`

现象：

- `ros2 launch raspbot_bringup patrol_detection.launch.py` 报找不到包
- 但 `raspbot_base` 又能正常找到

原因：

- 当前 shell 没有正确叠加 `~/ros2_ws/install` 环境
- 或者编译后没有重新加载工作区环境

处理：

```bash
cd ~/ros2_ws
source /opt/ros/jazzy/setup.bash
source ~/ros2_ws/install/setup.bash
ros2 pkg list | grep '^raspbot_'
```

正常应至少看到：

- `raspbot_base`
- `raspbot_bringup`
- `raspbot_vision`

然后再启动：

```bash
ros2 launch raspbot_bringup patrol_detection.launch.py
```

### 8.7 巡检相机打不开

现象：

- 日志里反复出现 `failed to open person detection camera`
- 或启动后长时间没有出现 `person detection camera ready ...`

处理顺序：

```bash
v4l2-ctl --list-devices
ls -l /dev/v4l/by-id
```

确认当前 USB 摄像头的稳定链接和真实设备号是否正常。

更稳妥的确认方式：

```bash
ls -l /dev/v4l/by-id
```

看 `usb-Generic_HD_camera_20181212000000-video-index0` 当前实际指向哪个 `/dev/videoX`。

如果设备号没问题，再执行：

```bash
source /opt/ros/jazzy/setup.bash
source ~/ros2_ws/install/setup.bash
ros2 launch raspbot_bringup patrol_detection.launch.py
```

补充说明：

- 当前 `person_detect_node` 已做成“打开失败不崩溃、后台重试”的模式
- 当前优先走 OpenCV，必要时会自动回退到 `v4l2-ctl`
- 只要日志出现 `person detection camera ready via backend=opencv` 或 `backend=v4l2ctl`，就说明相机链路已经打通
- 如果你手工把配置改成固定的 `/dev/video1`，系统一旦重新枚举，巡检相机就可能再次打不开
