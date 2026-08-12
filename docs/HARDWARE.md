# 硬件参考

## 硬件清单

| 序号 | 组件 | 型号 | 数量 | 用途 |
|------|------|------|------|------|
| 1 | 主控板 | Raspberry Pi 4B 8GB | 1 | 运行 ROS2 系统 |
| 2 | 操作系统 | Ubuntu Server 24.04 (64-bit) | — | ROS2 Jazzy 运行环境 |
| 3 | 小车底盘 | Yahboom Raspbot | 1 | 含 I2C 驱动板、直流电机、电池仓 |
| 4 | USB 摄像头 | Generic HD Camera | 1 | 视觉循线 + 人体检测 |
| 5 | 超声波模块 | HC-SR04 | 1 | 前方障碍物测距 |
| 6 | 舵机云台 | 2 轴微型舵机 (SG90 或兼容) | 1 套 | 巡逻多角度扫描 |
| 7 | 蜂鸣器 | 有源蜂鸣器 3.3V | 1 | 告警声音反馈 |
| 8 | 状态 LED | 双色 LED (红/蓝) | 1 | 系统状态指示 |

### 底盘内置传感器（通过 I2C 驱动板引出）

| 传感器 | 数量 | 用途 |
|--------|------|------|
| 红外循迹模块 | 4 路 | 黑线检测（底盘底部） |
| 红外避障模块 | 2 路 | 左右障碍物检测（底盘前部） |

---

## GPIO 引脚映射

### Raspberry Pi 40-pin 引脚分配

```
                   3.3V (1)  (2) 5V
             SDA / GPIO2 (3)  (4) 5V
             SCL / GPIO3 (5)  (6) GND
                  GPIO4 (7)  (8) GPIO14 (TXD)
                       GND (9) (10) GPIO15 (RXD)
                 GPIO17 (11) (12) GPIO18
                 GPIO27 (13) (14) GND
                 GPIO22 (15) (16) GPIO23
                      3.3V (17) (18) GPIO24
             MOSI/GPIO10 (19) (20) GND
             MISO/GPIO9  (21) (22) GPIO25
             SCLK/GPIO11 (23) (24) GPIO8 (CE0)
                       GND (25) (26) GPIO7 (CE1)
             ID_SD/GPIO0 (27) (28) GPIO1 (ID_SC)
                  GPIO5 (29) (30) GND
                  GPIO6 (31) (32) GPIO12
                 GPIO13 (33) (34) GND
             MISO/GPIO19 (35) (36) GPIO16
                 GPIO26 (37) (38) GPIO20
                       GND (39) (40) GPIO21
```

### 本项目 GPIO 使用明细

| GPIO 引脚 | 物理引脚 | 用途 | 所属节点 | 方向 | 备注 |
|-----------|---------|------|---------|------|------|
| 2 (SDA) | Pin 3 | I2C 数据线 | base_driver, gimbal | I2C | 连接底盘驱动板 |
| 3 (SCL) | Pin 5 | I2C 时钟线 | base_driver, gimbal | I2C | 连接底盘驱动板 |
| 4 | Pin 7 | 红外循迹传感器 2 | line_tracker | 输入 | Yahboom 默认 |
| 17 | Pin 11 | 红外循迹传感器 1 | line_tracker | 输入 | Yahboom 默认 |
| 27 | Pin 13 | 红外循迹传感器 3 | line_tracker | 输入 | Yahboom 默认 |
| 22 | Pin 15 | 红外循迹传感器 4 | line_tracker | 输入 | Yahboom 默认 |
| 23 | Pin 16 | 超声波 Trig | ultrasonic | 输出 | HC-SR04 触发引脚 |
| 24 | Pin 18 | 超声波 Echo | ultrasonic | 输入 | HC-SR04 回波引脚 |
| 9 | Pin 21 | 红外避障左 | ir_obstacle | 输入 | 低电平有效 |
| 10 | Pin 19 | 红外避障右 | ir_obstacle | 输入 | 低电平有效 |
| 25 | Pin 22 | 红外避障使能 | ir_obstacle | 输出 | 高电平有效 |
| 12 | Pin 32 | 蜂鸣器 | buzzer | 输出 | 高电平有效 |
| 5 | Pin 29 | LED 通道 1 (红) | status_led | 输出 | 高电平有效 |
| 6 | Pin 31 | LED 通道 2 (蓝) | status_led | 输出 | 高电平有效 |

---

## I2C 通信协议

### 设备信息

- **总线**: `/dev/i2c-1`
- **地址**: `0x16` (十进制 22)
- **库**: python3-smbus (`smbus.SMBus`)

### 寄存器定义

#### 寄存器 0x01 — 电机控制

写入 4 字节数据块：

| 字节 | 字段 | 取值范围 | 说明 |
|------|------|---------|------|
| 0 | 左轮方向 | 0 或 1 | 0 = 后退, 1 = 前进 |
| 1 | 左轮速度 | 0 ~ 255 | PWM 占空比值 |
| 2 | 右轮方向 | 0 或 1 | 0 = 后退, 1 = 前进 |
| 3 | 右轮速度 | 0 ~ 255 | PWM 占空比值 |

```python
# 前进：两轮同为前进方向
self.write_array(0x01, [1, speed_L, 1, speed_R])

# 后退：两轮同为后退方向
self.write_array(0x01, [0, speed_L, 0, speed_R])

# 左转：左轮慢/后退，右轮快/前进
self.write_array(0x01, [0, 30, 1, 50])
```

#### 寄存器 0x02 — 停车

写入 1 字节：

| 值 | 功能 |
|----|------|
| `0x00` | 立即停止所有电机 |

#### 寄存器 0x03 — 舵机控制

写入 2 字节数据块：

| 字节 | 字段 | 取值范围 | 说明 |
|------|------|---------|------|
| 0 | 舵机 ID | 1 或 2 | 1 = Pan (水平), 2 = Tilt (俯仰) |
| 1 | 角度 | 0 ~ 180 | 目标角度（自动限幅至 0-180） |

---

## 底盘差速运动模型

本项目使用**差速驱动**模型，通过两轮速度差实现转向：

```
线性速度 linear.x → 基础速度分量
角速度 angular.z  → 差速分量

左轮速度 = linear.x * linear_gain - angular.z * angular_gain
右轮速度 = linear.x * linear_gain + angular.z * angular_gain

其中:
  linear_gain  = 70.0  (将 m/s 映射到 0-100 PWM)
  angular_gain = 45.0  (将 rad/s 映射到 PWM 差值)
  max_pwm      = 100.0 (限幅)
```

**运动示例**：

| Twist 指令 | linear.x | angular.z | 小车行为 |
|-----------|----------|-----------|---------|
| 前进 | 0.20 | 0.0 | 两轮同速前进 |
| 后退 | -0.10 | 0.0 | 两轮同速后退 |
| 左转 | 0 | 0.8 | 原地左转 |
| 右转 | 0 | -0.8 | 原地右转 |
| 弧线左转 | 0.14 | 0.7 | 前进同时左转 |
| 停止 | 0.0 | 0.0 | 停车 |

---

## 传感器规格与参数

### HC-SR04 超声波

| 参数 | 值 | 说明 |
|------|-----|------|
| 工作电压 | 5V | Echo 需通过分压电阻降至 3.3V 接 GPIO |
| 测距范围 | 2cm ~ 250cm | 配置中 min_range=0.02, max_range=2.50 |
| 测距精度 | ±3mm | — |
| 测量角度 | ~15° | 配置中 field_of_view=0.26 rad |
| 触发信号 | 10μs 高电平 | Trig 引脚 |
| 计算公式 | distance = pulse_width × speed_of_sound / 2 | speed_of_sound = 331.3 + 0.606 × temperature |

### 红外循迹传感器

| 参数 | 值 |
|------|-----|
| 数量 | 4 路（左到右排列） |
| 检测原理 | 红外反射式，黑线吸光 → 低电平 |
| 逻辑 | active_low=true (检测到黑线 = GPIO 读为 0) |
| 排列权重 | [-3, -1, 1, 3]（加权误差计算） |

### 红外避障传感器

| 参数 | 值 |
|------|-----|
| 数量 | 2 路 (左/右) |
| 检测原理 | 红外反射式，障碍物反射 → 低电平 |
| 逻辑 | sensor_active_low=true |
| 使能引脚 | GPIO 25，enable_active_high=true |

---

## 5V 供电注意事项

> ⚠️ **重要**：HC-SR04 超声波模块工作电压为 5V，但 Raspberry Pi GPIO 为 3.3V 电平。

Echo 引脚输出电压为 5V，**必须通过分压电阻**（如 1kΩ + 2kΩ）降至 3.3V 再连接 GPIO 24，否则可能损坏树莓派 GPIO 口。

Yahboom Raspbot 底盘的 I2C 驱动板通常已内置电平转换，但自行外接的传感器需要确认电平兼容性。
