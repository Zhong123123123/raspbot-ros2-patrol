# GitHub 发布说明

## 发布内容

建议公开提交源码、ROS 配置、文档、脚本、测试和 GitHub Actions CI。本仓库的 `.gitignore` 会排除 ROS 2 构建产物、日志、模型权重、历史巡检数据、缓存和常见凭据文件。

模型获取方式见 [../models/README.md](../models/README.md)。历史实机数据和 Windows 离线验证边界分别见 [SYSTEM_TEST_REPORT.md](SYSTEM_TEST_REPORT.md) 与 [OFFLINE_VERIFICATION.md](OFFLINE_VERIFICATION.md)。

## 发布前检查

在仓库根目录执行：

```bash
python -B -m pytest src/raspbot_vision/test -q -p no:cacheprovider
```

若已安装开发依赖，再执行：

```bash
ruff check src/raspbot_base src/raspbot_vision
```

不要把 Windows 离线结果写成树莓派实机验证。实机验收项见 [PI_VALIDATION_CHECKLIST.md](PI_VALIDATION_CHECKLIST.md)。

## 初始化并首次提交

```bash
git init
git branch -M main
git add .
git status
git commit -m "Initial public release"
```

在 `git status` 中确认没有 `build/`、`install/`、`log/`、`.pytest_cache/`、`data/` 中的历史记录或模型权重。再在 GitHub 创建空仓库并添加远端：

```bash
git remote add origin <你的 GitHub 仓库地址>
git push -u origin main
```

## 发布前必须自行决定的事项

- **许可证**：当前 README 标注为 `Proprietary`，且仓库没有 `LICENSE` 文件。公开仓库不等于授予他人使用权限；若要开源，请由仓库所有者选择并添加合适许可证。
- **公开范围**：`RESUME_PROJECT_REVISED.md`、规划文档与历史测试报告不含代码运行必需内容。发布前请确认是否希望它们对外可见。
- **密钥检查**：发布前再次检查 webhook、token、设备地址和真实采集图片。`.gitignore` 只能保护未被 Git 跟踪的文件，不能清除已提交历史。
