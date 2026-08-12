# Windows / WSL 离线验证指南

## 适用范围

本文说明不连接 ROS 2、摄像头或小车硬件时可以完成的验证。它不能替代树莓派上的 ROS 2、GPIO、I2C、摄像头和实际运动验证；实机项目请继续使用 [PI_VALIDATION_CHECKLIST.md](PI_VALIDATION_CHECKLIST.md)。

## 2026-08-12 已完成的 Windows 验证

在当前 Windows 工作区中完成了以下只读/离线检查：

- `python -B -m pytest src/raspbot_vision/test -q -p no:cacheprovider`：`117 passed, 2 skipped`。
- 68 个 `src/` 与 `tools/` 下的 Python 文件通过 AST 语法解析。
- 15 个视觉配置 YAML 及 3 个 `package.xml` 可解析。

两项跳过来自当前 Windows Python 环境没有安装 OpenCV；测试使用 `pytest.importorskip("cv2")`，因此它们是明确跳过而不是伪成功。当前环境也没有 `rclpy`、ROS 2、真实相机或硬件，故未运行节点、launch、colcon 构建或实车测试。

历史测试报告中的 Linux/树莓派结果保留为历史证据，不能与本次 Windows 离线结果混为同一轮测试。

## 在 Windows 上复跑

```powershell
Set-Location D:\CDevelop\project_backup\ros2_ws
$env:PYTHONDONTWRITEBYTECODE = "1"
python -B -m pytest src/raspbot_vision/test -q -p no:cacheprovider
```

若要运行依赖 OpenCV 的测试，先在隔离环境中安装运行依赖：

```powershell
python -m pip install -r requirements-runtime.txt
```

开发静态检查依赖单独安装：

```powershell
python -m pip install -r requirements-dev.txt
ruff check src/raspbot_base src/raspbot_vision
```

## 推荐的 WSL 验证层

当前机器未安装 WSL，因此以下是后续建议，不是已完成步骤。安装 Ubuntu 后，将仓库放在 Linux 文件系统中，再建立虚拟环境并复跑纯 Python 测试：

```bash
cd ~/ros2_ws
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-runtime.txt -r requirements-dev.txt
python -m pytest src/raspbot_vision/test -q
ruff check src/raspbot_base src/raspbot_vision
```

WSL 适合验证 Python 依赖、配置和打包前的代码质量，但不能验证树莓派 GPIO/I2C、USB 摄像头行为或小车运动。

## 工作区路径

运行时数据、模型和 Agent 审计日志可通过 `RASPBOT_WS` 定位；未设置时 Python 节点默认 `~/ros2_ws`。

```powershell
$env:RASPBOT_WS = "D:\CDevelop\project_backup\ros2_ws"
```

```bash
export RASPBOT_WS="$HOME/ros2_ws"
```

这项环境变量已用于主要 Python 节点的模型、巡检数据和审计日志路径。现有 `tools/openclaw/*.sh` 及部分 systemd/运维脚本仍按 Linux 默认工作区编写；移动它们之前应逐个检查路径，不能仅靠设置该变量就假设所有 shell 脚本已可移植。
