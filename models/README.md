# 模型文件

模型权重不随仓库发布：它们体积较大，且应由使用者确认来源、许可证与版本。运行人体检测前，在 `models/person_detection/` 放入所需文件。

- YOLOv8 ONNX：运行 `bash download_yolov8_model.sh`，或按脚本说明导出 416×416 的 `yolov8n.onnx`。
- TF-SSD：按 [docs/SETUP.md](../docs/SETUP.md) 的“下载人体检测模型”步骤放入 `frozen_inference_graph.pb` 和对应 `.pbtxt`。
- HOG 后端不需要额外模型文件。

模型目录由 `.gitignore` 排除；不要把私有模型、商业模型或下载缓存直接提交到 GitHub。
