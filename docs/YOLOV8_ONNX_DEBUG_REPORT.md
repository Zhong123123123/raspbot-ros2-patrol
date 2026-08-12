# YOLOv8 ONNX Debug Report

Date: 2026-07-04
Scope: `raspbot_vision` YOLOv8 ONNX person backend only. Patrol state machine, SQLite schema, and main patrol flow were not changed.

## 1. Problem Statement

On the same camera and the same pose:

- TF-SSD can detect the person with confidence around `0.8`.
- YOLOv8 ONNX previously returned no person at all.

This was treated as a pipeline issue first, not as a model-training issue.

## 2. Model Information

Actual loaded model:

- `model_path`: `/home/ubuntu/ros2_ws/models/person_detection/yolov8n.onnx`
- `model_exists`: `true`
- `load_ok`: `true`
- `onnxruntime_version`: `1.27.0`
- `requested_backend`: `yolov8_onnx`
- `actual_backend`: `yolov8_onnx`
- `fallback_reason`: empty

Model IO:

- input name: `images`
- input shape: `[1, 3, 416, 416]`
- input dtype: `tensor(float)`
- output name: `output0`
- output shape: `[1, 84, 3549]`
- output dtype: `tensor(float)`

Model metadata confirms this is a COCO detection model:

- `task = detect`
- `head = Detect`
- `names[0] = person`

## 3. Preprocessing Check

The debug script saved the model input visualization here:

- `data/patrol/checks/yolo_debug_case2/yolo_input_after_preprocess.jpg`

Preprocessing used:

- letterbox resize to `416x416`
- BGR to RGB conversion
- normalization to `float32` in `[0.0, 1.0]`
- NCHW layout before ONNXRuntime inference
- no hard-coded rotation in code; rotation is controlled by YAML

The camera/orientation check showed this is not a simple “YOLO cannot see the person” case.

## 4. Output Parsing Check

The critical finding was the output decode bug.

### What was wrong

The previous code treated YOLO box values as if they were normalized `[0, 1]` values and multiplied them by `input_size` again during decode.

That was wrong for this model export.

### What the model actually outputs

For the selected sample frame, the raw YOLO output had:

- person scores up to `0.9337` after the correct rotation
- raw candidate boxes already in input-space pixel units, not normalized fractions

The fixed decoder now supports both cases:

- normalized `[0, 1]`
- pixel-space values in the model input domain

### YOLOv5 objectness check

The code does **not** use YOLOv5-style objectness math now.

Correct YOLOv8 logic used:

- `class_scores = row[4:]`
- `class_id = argmax(class_scores)`
- `confidence = class_scores[class_id]`
- `person` is class id `0`

## 5. Evidence From the Same Frame

A TF-SSD positive raw frame was used:

- `data/patrol/images_hog/2026-07-04/detect_20260704T130651_268431_raw.jpg`

### Same frame, rotation 0

- TF-SSD: `detection_count=1`, `max_confidence=0.9114`
- YOLOv8 ONNX: `detection_count=0`, `max_person_score=0.0044`

### Same frame, rotation 270

- TF-SSD: `detection_count=1`, `max_confidence=0.9114`
- YOLOv8 ONNX: `detection_count=1`, `max_person_score=0.9337`

This shows the final failure was not model loading, not class mapping, and not thresholding alone. The main issue was the combination of camera orientation and wrong bbox decode.

## 6. Threshold Scan

Using the fixed decoder on the same frame with `rotate_deg=270`:

| conf threshold | detection_count | max_person_score |
| --- | --- | --- |
| 0.10 | 1 | 0.9337 |
| 0.25 | 1 | 0.9337 |
| 0.35 | 1 | 0.9337 |
| 0.45 | 1 | 0.9337 |

Conclusion: after the decoder fix, thresholding is no longer the blocker for this sample.

## 7. Rotation Scan

On the same frame:

| rotation | detection_count | max_person_score |
| --- | --- | --- |
| 0 | 0 | 0.0000 |
| 90 | 0 | 0.0000 |
| 180 | 0 | 0.0000 |
| 270 | 1 | 0.9337 |

Conclusion: the camera is mounted with a `270` degree correction relative to the original raw frame.

## 8. Saved Evidence

Files saved by the debug script:

- `data/patrol/checks/yolo_debug_case2/yolo_test_raw.jpg`
- `data/patrol/checks/yolo_debug_case2/tfssd_debug.jpg`
- `data/patrol/checks/yolo_debug_case2/yolo_debug.jpg`
- `data/patrol/checks/yolo_debug_case2/yolo_input_after_preprocess.jpg`
- `data/patrol/checks/yolo_debug_case2/debug_report.json`

## 9. Conclusion

This was **not** a model-load failure.

This was primarily:

1. a camera orientation issue, and
2. a YOLOv8 bbox decode bug that treated pixel-space outputs as normalized outputs.

After fixing the decode and applying `frame_rotate_deg=270`, the same frame now produces a valid person detection from YOLOv8 ONNX.

## 10. Fixes Applied

Modified files:

- `src/raspbot_vision/raspbot_vision/detector_backends.py`
- `src/raspbot_vision/config/person_detect.yaml`
- `src/raspbot_vision/config/person_detect_yolov8.yaml`
- `src/raspbot_vision/config/person_detect_tf_ssd.yaml`
- `src/raspbot_vision/config/person_detect_hog.yaml`
- `tools/debug_yolov8_onnx.py`

Fix details:

- YOLOv8 decoder now handles both normalized and pixel-space boxes.
- Default frame rotation is now `270` in the person detection YAMLs.
- Debug script now uses the same corrected decode path.

## 11. Verification

Verified on the same sample frame:

- TF-SSD detects the person.
- YOLOv8 ONNX now detects the person with `max_person_score=0.9337` after `rotate_deg=270`.
- Full test suite passed: `101 passed`（该条为本报告原始环境的历史结果；当前 Windows 离线回归见 [OFFLINE_VERIFICATION.md](OFFLINE_VERIFICATION.md)）。
- Workspace build passed.

## 12. Live Camera Retest

A real camera retest was run after the decode fix, using the same live capture flow and the same `rotate_deg=270` correction.

Command used:

```bash
cd /home/ubuntu/ros2_ws
source /opt/ros/jazzy/setup.bash
source install/setup.bash
PYTHONPATH=src/raspbot_vision python3 tools/debug_yolov8_onnx.py   --capture-positive   --rotate-deg 270   --output-dir data/patrol/checks/yolo_live_retest
```

Live retest result:

- TF-SSD: `detection_count=1`, `max_confidence=0.9063`
- YOLOv8 ONNX: `detection_count=1`, `max_person_score=0.9310`
- `rotation_scan`: `270 -> detection_count=1`
- `threshold_scan`: `0.10 / 0.25 / 0.35 / 0.45` all returned `1`

Saved evidence:

- `data/patrol/checks/yolo_live_retest/yolo_test_raw.jpg`
- `data/patrol/checks/yolo_live_retest/tfssd_debug.jpg`
- `data/patrol/checks/yolo_live_retest/yolo_debug.jpg`
- `data/patrol/checks/yolo_live_retest/yolo_input_after_preprocess.jpg`
- `data/patrol/checks/yolo_live_retest/debug_report.json`

This confirms the fix works on the live camera path, not only on archived frames.
