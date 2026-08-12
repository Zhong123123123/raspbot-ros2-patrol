#!/usr/bin/env bash

set -euo pipefail

WS_DIR="${WS_DIR:-$HOME/ros2_ws}"
DB_PATH="${DB_PATH:-$WS_DIR/data/patrol/patrol_events.db}"
CONFIG_PATH="$WS_DIR/src/raspbot_vision/config/person_detect.yaml"
MODEL_PATH="$WS_DIR/models/person_detection/frozen_inference_graph.pb"
PBTXT_PATH="$WS_DIR/models/person_detection/ssd_mobilenet_v1_coco_2017_11_17.pbtxt"
YOLO_MODEL_PATH="$WS_DIR/models/person_detection/yolov8n.onnx"

fail() {
  echo "[patrol_delivery_check] FAIL: $*" >&2
  exit 1
}

echo "[patrol_delivery_check] workspace: $WS_DIR"
[[ -d "$WS_DIR" ]] || fail "workspace not found"
[[ -f "$CONFIG_PATH" ]] || fail "person_detect.yaml not found"
[[ -f "$YOLO_MODEL_PATH" ]] || fail "YOLOv8 model not found"
[[ -f "$MODEL_PATH" ]] || fail "TF-SSD model not found"
[[ -f "$PBTXT_PATH" ]] || fail "TF-SSD pbtxt not found"
[[ -e /dev/v4l/by-id/usb-Generic_HD_camera_20181212000000-video-index0 ]] || fail "camera by-id path missing"

default_backend=$(python3 - <<'PY'
from pathlib import Path
import yaml
cfg = yaml.safe_load(Path.home().joinpath('ros2_ws/src/raspbot_vision/config/person_detect.yaml').read_text())
print(cfg['raspbot_person_detect']['ros__parameters'].get('detector_backend', ''))
PY
)

echo "[patrol_delivery_check] default_detector_backend: $default_backend"
[[ "$default_backend" == "yolov8_onnx" ]] || fail "default detector backend is not yolov8_onnx"

[[ -f "$DB_PATH" ]] || fail "patrol database not found: $DB_PATH"

sqlite3 "$DB_PATH" "select 1 from pragma_table_info('patrol_final_results') where name='decision_reason';" | grep -q 1 || fail "decision_reason column missing"
sqlite3 "$DB_PATH" "select 1 from pragma_table_info('patrol_observations') where name='scan_positive_frames';" | grep -q 1 || fail "scan_positive_frames column missing"

echo "[patrol_delivery_check] recent final results:"
python3 "$WS_DIR/query_patrol_results.py" --mode final --limit 5 --detector-backend opencv_dnn_tf_ssd || true

echo

echo "[patrol_delivery_check] recent observations:"
python3 "$WS_DIR/query_patrol_results.py" --mode observations --limit 5 --detector-backend opencv_dnn_tf_ssd || true

echo

echo "[patrol_delivery_check] PASS"
