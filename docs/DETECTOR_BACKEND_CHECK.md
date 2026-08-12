# Detector Backend Check

Date: 2026-07-04
Scope: `raspbot_vision/person_detect_node` only. No patrol state machine or SQLite schema changes were made.

## What was wrong

The dashboard was showing `backend=hog` because the running detector could land on the HOG path instead of the intended YAML priority path. This was either:

- an explicit HOG launch/config selection (`person_detect_hog.yaml` or the HOG launch variants), or
- a backend fallback when the requested backend failed to initialize.

Before this fix, the runtime payload did not make that distinction obvious enough. The node now publishes:

- `backend_requested`
- `backend_active`
- `backend_is_fallback`
- `backend_fallback_reason`
- `decision_reason`

So the dashboard can show when the detector is not actually running the intended backend.

## Current default policy

The default config now prefers:

1. `yolov8_onnx`
2. `opencv_dnn_tf_ssd`
3. `hog` as fallback only

HOG is no longer the default demonstration backend.

## Startup proof

Verified from the real node startup on the Pi:

- `detector backend ready: yolov8_onnx`
- `requested_backend=yolov8_onnx`
- `backend_is_fallback=False`

That means the default config is no longer silently reverting to HOG.

## Backend capability probe

Live camera probe was run on the Pi using the same camera device as the node.

| Backend | model exists | load ok | camera ok | detect ok | avg latency | note |
| --- | --- | --- | --- | --- | --- | --- |
| `hog` | yes | yes | yes | yes | 151.36 ms | No detections in this live 4-frame probe. HOG is kept conservative and should not be treated as a strong close-range person signal. |
| `opencv_dnn_tf_ssd` | yes | yes | yes | yes | 155.54 ms | Stable positive detections in the same 4-frame probe, `count=1`, `max_confidence=0.922`. |
| `yolov8_onnx` | yes | yes | yes | yes | 383.62 ms | Loaded correctly, but returned `count=0` on this live probe. This needs scene-specific validation, not a blanket assumption that YOLO is always positive. |

Probe output:

- `data/patrol/checks/backend_probe_three/probe.json`
- `data/patrol/checks/backend_probe_live_compare.json`

## HOG reliability guardrails

To prevent the close-range half-body case from being over-trusted, HOG now has stricter filters:

- `hog_min_confidence`
- `hog_min_box_area_ratio`
- `hog_min_aspect_ratio`
- `hog_valid_as_confirmed_backend: false`

Result: HOG can still produce a debug box, but it should not be treated as a strong confirmed occupied signal by itself.

## Frame rotation

If the camera is mounted sideways or upside down, use YAML instead of hard-coding rotation:

- `frame_rotate_deg: 270`
- valid values: `0`, `90`, `180`, `270`

Important:

- raw images still keep the original frame
- detection input and debug overlays use the rotated frame when configured
- current default person detector config uses `270` for this camera mounting

## Dashboard visibility

The dashboard now displays:

- active backend
- requested backend
- fallback state
- fallback reason
- decision reason

So the user can see whether the system is on the intended path or on a fallback path.

## Evidence files

Saved comparison images:

- `data/patrol/checks/backend_probe_three/scene_raw.jpg`
- `data/patrol/checks/backend_probe_three/hog_debug.jpg`
- `data/patrol/checks/backend_probe_three/opencv_dnn_tf_ssd_debug.jpg`
- `data/patrol/checks/backend_probe_three/yolov8_onnx_debug.jpg`

Additional comparison set:

- `data/patrol/checks/backend_probe/hog_debug.jpg`
- `data/patrol/checks/backend_probe/opencv_dnn_tf_ssd_debug.jpg`
- `data/patrol/checks/backend_probe/yolov8_onnx_debug.jpg`

## Remaining caution

The live probe shows TF-SSD is currently the most reliable of the three on this setup. YOLO loads, but its current live-frame behavior still needs scene-specific tuning/validation. HOG should stay as fallback only.


## Live Camera Retest

The live camera retest after the YOLO decode fix confirmed the backend is usable on the mounted camera when `frame_rotate_deg=270` is applied.

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
- `rotation_scan`: only `270` produced a positive YOLO result

This means the earlier YOLO empty result was not a model-load failure. It was a decode/orientation issue that has now been corrected.
