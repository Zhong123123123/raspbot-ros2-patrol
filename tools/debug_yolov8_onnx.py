#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import statistics
import time
from pathlib import Path
from typing import Dict, List, Tuple

import cv2
import numpy as np
import onnxruntime as ort

from raspbot_vision.detector_backends import DetectorConfig, create_person_detector
from raspbot_vision.usb_camera import USBCamera

Detection = Tuple[int, int, int, int, float]

DEFAULT_MODEL = "/home/ubuntu/ros2_ws/models/person_detection/yolov8n.onnx"
DEFAULT_TF_MODEL = "/home/ubuntu/ros2_ws/models/person_detection/frozen_inference_graph.pb"
DEFAULT_TF_CONFIG = "/home/ubuntu/ros2_ws/models/person_detection/ssd_mobilenet_v1_coco_2017_11_17.pbtxt"
DEFAULT_CAMERA = "/dev/v4l/by-id/usb-Generic_HD_camera_20181212000000-video-index0"


def parse_args():
    parser = argparse.ArgumentParser(description="YOLOv8 ONNX backend debug helper")
    parser.add_argument("--image", default="", help="Path to a raw image. If omitted, capture from camera.")
    parser.add_argument("--capture-positive", action="store_true", help="Capture frames until TF-SSD detects a person.")
    parser.add_argument("--camera-device", default=DEFAULT_CAMERA)
    parser.add_argument("--width", type=int, default=640)
    parser.add_argument("--height", type=int, default=480)
    parser.add_argument("--fps", type=int, default=15)
    parser.add_argument("--rotate-deg", type=int, default=270, choices=[0, 90, 180, 270])
    parser.add_argument("--output-dir", default="data/patrol/checks/yolo_debug")
    parser.add_argument("--yolo-model", default=DEFAULT_MODEL)
    parser.add_argument("--tf-model", default=DEFAULT_TF_MODEL)
    parser.add_argument("--tf-config", default=DEFAULT_TF_CONFIG)
    parser.add_argument("--yolo-conf-threshold", type=float, default=0.10)
    parser.add_argument("--yolo-nms-threshold", type=float, default=0.45)
    parser.add_argument("--yolo-min-area-ratio", type=float, default=0.001)
    parser.add_argument("--tf-threshold", type=float, default=0.45)
    parser.add_argument("--scan-angles", default="0,90,180,270")
    parser.add_argument("--scan-thresholds", default="0.10,0.25,0.35,0.45")
    parser.add_argument("--max-top", type=int, default=20)
    parser.add_argument("--capture-timeout-sec", type=float, default=20.0)
    return parser.parse_args()


def rotate_frame(frame: np.ndarray, rotation_deg: int) -> np.ndarray:
    rotation = int(rotation_deg) % 360
    if rotation == 0:
        return frame
    if rotation == 90:
        return cv2.rotate(frame, cv2.ROTATE_90_CLOCKWISE)
    if rotation == 180:
        return cv2.rotate(frame, cv2.ROTATE_180)
    if rotation == 270:
        return cv2.rotate(frame, cv2.ROTATE_90_COUNTERCLOCKWISE)
    raise ValueError(rotation_deg)


def make_yolo_input(frame: np.ndarray, input_size: int = 416) -> Tuple[np.ndarray, Dict[str, int], np.ndarray]:
    h, w = frame.shape[:2]
    scale = min(input_size / w, input_size / h)
    new_w = int(round(w * scale))
    new_h = int(round(h * scale))
    resized = cv2.resize(frame, (new_w, new_h), interpolation=cv2.INTER_LINEAR)
    pad_w = input_size - new_w
    pad_h = input_size - new_h
    top = pad_h // 2
    bottom = pad_h - top
    left = pad_w // 2
    right = pad_w - left
    padded = cv2.copyMakeBorder(resized, top, bottom, left, right, cv2.BORDER_CONSTANT, value=(114, 114, 114))
    rgb = cv2.cvtColor(padded, cv2.COLOR_BGR2RGB)
    blob = rgb.astype(np.float32) / 255.0
    nchw = np.expand_dims(blob.transpose(2, 0, 1), axis=0).astype(np.float32)
    return nchw, {"scale": scale, "pad_x": left, "pad_y": top, "new_w": new_w, "new_h": new_h}, padded


def decode_yolo(outputs: np.ndarray, img_w: int, img_h: int, scale: float, pad_x: int, pad_y: int, conf_threshold: float, nms_threshold: float, min_area_ratio: float) -> Dict:
    raw_shape = list(outputs.shape)
    raw_min = float(outputs.min())
    raw_max = float(outputs.max())
    if outputs.shape[1] != 84:
        outputs = outputs.transpose(0, 2, 1)
    anchors = outputs[0]
    boxes = anchors[:4]
    scores = anchors[4:]
    person_scores = scores[0]
    class_scores = scores.max(axis=0)
    class_ids = scores.argmax(axis=0)
    num_candidates_before_threshold = int(scores.shape[1])
    num_person_candidates_before_threshold = int((person_scores > 0).sum())
    mask = person_scores >= conf_threshold
    num_after_conf_threshold = int(mask.sum())

    box_max = float(np.max(boxes)) if boxes.size else 0.0
    box_scale = 416.0 if box_max <= 1.5 else 1.0

    raw_detections: List[Detection] = []
    pre_area_count = 0
    post_area_count = 0
    for i in np.where(mask)[0]:
        cx, cy, bw, bh = (float(v) * box_scale for v in boxes[:, i])
        x1 = (cx - bw / 2.0 - pad_x) / scale
        y1 = (cy - bh / 2.0 - pad_y) / scale
        w = bw / scale
        h = bh / scale
        x = int(max(0, x1))
        y = int(max(0, y1))
        w = int(min(w, img_w - x))
        h = int(min(h, img_h - y))
        if w > 0 and h > 0:
            pre_area_count += 1
            area_ratio = (w * h) / float(max(1, img_w * img_h))
            if area_ratio >= min_area_ratio:
                post_area_count += 1
                raw_detections.append((x, y, w, h, float(person_scores[i])))
    if len(raw_detections) < 2:
        after_nms = raw_detections
    else:
        bboxes = np.array([[d[0], d[1], d[0] + d[2], d[1] + d[3], d[4]] for d in raw_detections], dtype=np.float32)
        keep = cv2.dnn.NMSBoxes(bboxes[:, :4].tolist(), bboxes[:, 4].tolist(), conf_threshold, nms_threshold)
        if keep is None or len(keep) == 0:
            after_nms = []
        else:
            keep = keep.flatten() if isinstance(keep, np.ndarray) else [k[0] for k in keep]
            after_nms = [raw_detections[i] for i in keep]
    return {
        "raw_shape": raw_shape,
        "raw_min": raw_min,
        "raw_max": raw_max,
        "num_candidates_before_threshold": num_candidates_before_threshold,
        "num_person_candidates_before_threshold": num_person_candidates_before_threshold,
        "num_after_conf_threshold": num_after_conf_threshold,
        "num_after_area_filter": post_area_count,
        "num_before_area_filter": pre_area_count,
        "num_after_nms": len(after_nms),
        "detections": after_nms,
        "person_max": float(person_scores.max()) if person_scores.size else 0.0,
        "person_top20": [],
        "all_top20": [],
        "class_ids": class_ids,
        "class_scores": class_scores,
        "person_scores": person_scores,
        "boxes": boxes,
    }


def draw(frame: np.ndarray, detections: List[Detection], title: str) -> np.ndarray:
    out = frame.copy()
    cv2.rectangle(out, (0, 0), (out.shape[1] - 1, 70), (18, 18, 18), -1)
    cv2.rectangle(out, (0, 0), (out.shape[1] - 1, 70), (0, 255, 255), 2)
    cv2.putText(out, title, (10, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.75, (0, 255, 255), 2, cv2.LINE_AA)
    for x, y, w, h, conf in detections:
        cv2.rectangle(out, (x, y), (x + w, y + h), (0, 255, 0), 2)
        cv2.putText(out, f"person {conf:.2f}", (x, max(80, y - 6)), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 255, 0), 2, cv2.LINE_AA)
    return out


def save_preprocess_image(padded_rgb: np.ndarray, out_path: Path):
    cv2.imwrite(str(out_path), cv2.cvtColor(padded_rgb, cv2.COLOR_RGB2BGR))


def scan_thresholds(detector, frame: np.ndarray, thresholds: List[float], yolo_nms_threshold: float, min_area_ratio: float) -> Dict[str, Dict[str, float]]:
    result = {}
    yolo = detector
    for thresh in thresholds:
        cfg = DetectorConfig(
            backend="yolov8_onnx",
            min_weight=0.50,
            min_area=max(1, int(frame.shape[0] * frame.shape[1] * min_area_ratio)),
            dnn_model_path=DEFAULT_MODEL,
            yolov8_input_size=416,
            yolov8_confidence_threshold=thresh,
            yolov8_nms_threshold=yolo_nms_threshold,
            yolov8_use_onnxruntime=True,
            yolov8_use_opencv_dnn=False,
        )
        det = create_person_detector(cfg)
        detections = det.detect(frame)
        result[str(thresh)] = {
            "detection_count": len(detections),
            "max_person_score": max((d[4] for d in detections), default=0.0),
        }
    return result


def scan_rotations(image: np.ndarray, thresholds: List[float], yolo_nms_threshold: float, min_area_ratio: float) -> Dict[str, Dict[str, float]]:
    result = {}
    for deg in [0, 90, 180, 270]:
        rotated = rotate_frame(image, deg)
        cfg = DetectorConfig(
            backend="yolov8_onnx",
            min_weight=0.50,
            min_area=max(1, int(rotated.shape[0] * rotated.shape[1] * min_area_ratio)),
            dnn_model_path=DEFAULT_MODEL,
            yolov8_input_size=416,
            yolov8_confidence_threshold=min(thresholds),
            yolov8_nms_threshold=yolo_nms_threshold,
            yolov8_use_onnxruntime=True,
            yolov8_use_opencv_dnn=False,
        )
        det = create_person_detector(cfg)
        detections = det.detect(rotated)
        result[str(deg)] = {
            "detection_count": len(detections),
            "max_person_score": max((d[4] for d in detections), default=0.0),
        }
    return result


def collect_top_candidates(info: Dict, max_top: int):
    person_scores = info["person_scores"]
    class_scores = info["class_scores"]
    class_ids = info["class_ids"]
    boxes = info["boxes"]
    person_idx = np.argsort(person_scores)[-max_top:][::-1]
    all_idx = np.argsort(class_scores)[-max_top:][::-1]
    info["person_top20"] = [
        {
            "rank": rank,
            "index": int(i),
            "person_score": float(person_scores[i]),
            "bbox": [float(v) for v in boxes[:, i]],
        }
        for rank, i in enumerate(person_idx, 1)
    ]
    info["all_top20"] = [
        {
            "rank": rank,
            "index": int(i),
            "class_id": int(class_ids[i]),
            "class_score": float(class_scores[i]),
            "bbox": [float(v) for v in boxes[:, i]],
        }
        for rank, i in enumerate(all_idx, 1)
    ]
    del info["person_scores"]
    del info["class_scores"]
    del info["class_ids"]
    del info["boxes"]


def capture_positive_frame(args, tf_detector) -> np.ndarray:
    camera = USBCamera(args.camera_device, args.width, args.height, args.fps)
    camera.open(retry=1)
    deadline = time.monotonic() + args.capture_timeout_sec
    try:
        while time.monotonic() < deadline:
            frame = camera.read()
            if frame is None:
                time.sleep(0.1)
                continue
            if not args.capture_positive:
                return frame
            if tf_detector.detect(frame):
                return frame
        raise TimeoutError("timed out waiting for a TF-SSD positive frame")
    finally:
        camera.release()


def main():
    args = parse_args()
    outdir = Path(args.output_dir).expanduser()
    outdir.mkdir(parents=True, exist_ok=True)

    tf_detector = create_person_detector(DetectorConfig(
        backend="opencv_dnn_tf_ssd",
        min_weight=0.50,
        min_area=2000,
        dnn_model_path=args.tf_model,
        dnn_config_path=args.tf_config,
        dnn_input_width=300,
        dnn_input_height=300,
        dnn_scale=1.0,
        dnn_mean=0.0,
        dnn_swap_rb=True,
        dnn_person_class_id=1,
        dnn_confidence_threshold=args.tf_threshold,
    ))

    yolo_cfg = DetectorConfig(
        backend="yolov8_onnx",
        min_weight=0.50,
        min_area=1,
        dnn_model_path=args.yolo_model,
        yolov8_input_size=416,
        yolov8_confidence_threshold=args.yolo_conf_threshold,
        yolov8_nms_threshold=args.yolo_nms_threshold,
        yolov8_use_onnxruntime=True,
        yolov8_use_opencv_dnn=False,
    )
    yolo_detector = create_person_detector(yolo_cfg)

    model_path = Path(args.yolo_model).expanduser()
    session = yolo_detector._sess  # debug helper
    input_info = session.get_inputs()[0]
    output_info = session.get_outputs()[0]

    if args.image:
        image = cv2.imread(str(Path(args.image).expanduser()))
        if image is None:
            raise FileNotFoundError(args.image)
    else:
        image = capture_positive_frame(args, tf_detector)

    raw_path = outdir / "yolo_test_raw.jpg"
    cv2.imwrite(str(raw_path), image)

    rotated = rotate_frame(image, args.rotate_deg)
    tf_rot = tf_detector.detect(rotated)
    yolo_rot = yolo_detector.detect(rotated)

    yolo_input, prep_meta, padded_rgb = make_yolo_input(rotated, 416)
    preprocess_path = outdir / "yolo_input_after_preprocess.jpg"
    save_preprocess_image(padded_rgb, preprocess_path)

    output = session.run(None, {input_info.name: yolo_input})[0]
    yolo_info = decode_yolo(output, rotated.shape[1], rotated.shape[0], prep_meta["scale"], prep_meta["pad_x"], prep_meta["pad_y"], args.yolo_conf_threshold, args.yolo_nms_threshold, args.yolo_min_area_ratio)
    collect_top_candidates(yolo_info, args.max_top)

    tf_debug = draw(rotated, tf_rot, f"TF-SSD count={len(tf_rot)} max={max((d[4] for d in tf_rot), default=0.0):.2f}")
    yolo_debug = draw(rotated, yolo_rot, f"YOLOv8 ONNX count={len(yolo_rot)} max={max((d[4] for d in yolo_rot), default=0.0):.2f} rot={args.rotate_deg}")
    tf_debug_path = outdir / "tfssd_debug.jpg"
    yolo_debug_path = outdir / "yolo_debug.jpg"
    cv2.imwrite(str(tf_debug_path), tf_debug)
    cv2.imwrite(str(yolo_debug_path), yolo_debug)

    thresholds = [float(x) for x in args.scan_thresholds.split(",") if x.strip()]
    angles = [int(x) for x in args.scan_angles.split(",") if x.strip()]
    threshold_scan = {}
    for thresh in thresholds:
        cfg = DetectorConfig(
            backend="yolov8_onnx",
            min_weight=0.50,
            min_area=max(1, int(rotated.shape[0] * rotated.shape[1] * args.yolo_min_area_ratio)),
            dnn_model_path=args.yolo_model,
            yolov8_input_size=416,
            yolov8_confidence_threshold=thresh,
            yolov8_nms_threshold=args.yolo_nms_threshold,
            yolov8_use_onnxruntime=True,
            yolov8_use_opencv_dnn=False,
        )
        det = create_person_detector(cfg)
        dets = det.detect(rotated)
        threshold_scan[str(thresh)] = {
            "detection_count": len(dets),
            "max_person_score": max((d[4] for d in dets), default=0.0),
        }

    rotation_scan = {}
    for deg in angles:
        rot = rotate_frame(image, deg)
        dets = yolo_detector.detect(rot)
        rotation_scan[str(deg)] = {
            "detection_count": len(dets),
            "max_person_score": max((d[4] for d in dets), default=0.0),
        }

    summary = {
        "model_path": str(model_path),
        "model_exists": model_path.exists(),
        "onnxruntime_version": ort.__version__,
        "requested_backend": "yolov8_onnx",
        "actual_backend": getattr(yolo_detector, "backend_name", "yolov8_onnx"),
        "fallback_reason": "",
        "load_ok": True,
        "input": {
            "name": input_info.name,
            "shape": list(input_info.shape),
            "dtype": input_info.type,
        },
        "output": {
            "name": output_info.name,
            "shape": list(output_info.shape),
            "dtype": output_info.type,
        },
        "image_path": str(Path(args.image).expanduser()) if args.image else str(raw_path),
        "raw_image_shape": list(image.shape),
        "rotate_deg": args.rotate_deg,
        "save_paths": {
            "raw": str(raw_path),
            "tfssd_debug": str(tf_debug_path),
            "yolo_debug": str(yolo_debug_path),
            "yolo_input_after_preprocess": str(preprocess_path),
        },
        "tfssd_result": {
            "detection_count": len(tf_rot),
            "max_confidence": max((d[4] for d in tf_rot), default=0.0),
        },
        "yolo_result": {
            "detection_count": len(yolo_rot),
            "max_person_score": max((d[4] for d in yolo_rot), default=0.0),
        },
        "yolo_raw": {
            "raw_shape": yolo_info["raw_shape"],
            "raw_min": yolo_info["raw_min"],
            "raw_max": yolo_info["raw_max"],
            "num_candidates_before_threshold": yolo_info["num_candidates_before_threshold"],
            "num_person_candidates_before_threshold": yolo_info["num_person_candidates_before_threshold"],
            "num_after_conf_threshold": yolo_info["num_after_conf_threshold"],
            "num_before_area_filter": yolo_info["num_before_area_filter"],
            "num_after_area_filter": yolo_info["num_after_area_filter"],
            "num_after_nms": yolo_info["num_after_nms"],
            "person_top20": yolo_info["person_top20"],
            "all_top20": yolo_info["all_top20"],
        },
        "threshold_scan": threshold_scan,
        "rotation_scan": rotation_scan,
    }

    report_json = outdir / "debug_report.json"
    report_json.write_text(json.dumps(summary, ensure_ascii=True, indent=2))
    print(json.dumps(summary, ensure_ascii=True, indent=2))
    print(f"written_json={report_json}")


if __name__ == "__main__":
    main()
