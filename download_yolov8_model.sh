#!/usr/bin/env bash
# download_yolov8_model.sh
# Export the YOLOv8n ONNX model at 416×416 for Raspberry Pi person detection.
#
# This must be run on a host with ultralytics installed (NOT the Pi itself),
# because the model must be exported at a specific resolution.
#
# Usage:
#   bash download_yolov8_model.sh              # export to default dir
#   bash download_yolov8_model.sh /custom/dir  # export to custom dir
#
# Or do it manually on your host:
#   pip install ultralytics
#   yolo export model=yolov8n.pt format=onnx imgsz=416
#   scp yolov8n.onnx ubuntu@pi:~/ros2_ws/models/person_detection/

set -euo pipefail

MODEL_DIR="${1:-${HOME}/ros2_ws/models/person_detection}"
MODEL_PATH="${MODEL_DIR}/yolov8n.onnx"
IMGSZ=416

mkdir -p "${MODEL_DIR}"

# Check if already exists
if [ -f "${MODEL_PATH}" ] && [ -s "${MODEL_PATH}" ]; then
    FILE_SIZE=$(stat -c%s "${MODEL_PATH}" 2>/dev/null || stat -f%z "${MODEL_PATH}" 2>/dev/null)
    if [ "${FILE_SIZE}" -gt 1000000 ]; then
        echo "✅  Model already exists: ${MODEL_PATH} (${FILE_SIZE} bytes)"
        exit 0
    fi
fi

# Check for ultralytics
if ! python3 -c "import ultralytics" 2>/dev/null; then
    echo "❌  ultralytics not installed. Run:  pip install ultralytics"
    echo ""
    echo "   Or export on another machine and scp:"
    echo "     yolo export model=yolov8n.pt format=onnx imgsz=${IMGSZ}"
    echo "     scp yolov8n.onnx ubuntu@pi:${MODEL_PATH}"
    exit 1
fi

echo "⬇️  Exporting YOLOv8n ONNX (${IMGSZ}×${IMGSZ})..."
python3 -c "
from ultralytics import YOLO
model = YOLO('yolov8n.pt')
model.export(format='onnx', imgsz=${IMGSZ})
import shutil, os
os.makedirs('${MODEL_DIR}', exist_ok=True)
shutil.move('yolov8n.onnx', '${MODEL_PATH}')
print(f'✅  Model saved to ${MODEL_PATH}')
"
