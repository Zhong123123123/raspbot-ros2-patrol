#!/usr/bin/env python3
"""Benchmark YOLOv8n ONNX vs TF-SSD MobileNet on this device.

Usage:
  # Use a sample image (generate a synthetic test frame)
  python3 -m raspbot_vision.benchmark_yolov8

  # Use a real camera
  python3 -m raspbot_vision.benchmark_yolov8 --camera 0

  # Test a single backend
  python3 -m raspbot_vision.benchmark_yolov8 --backend yolov8_onnx
"""

import argparse
import os
import sys
import time
from pathlib import Path

import cv2
import numpy as np

RESET = '\033[0m'
BOLD = '\033[1m'
GREEN = '\033[92m'
YELLOW = '\033[93m'
RED = '\033[91m'
CYAN = '\033[96m'


def _color(val, low, high, better='lower'):
    if better == 'lower':
        return GREEN if val <= low else (YELLOW if val <= high else RED)
    return GREEN if val >= high else (YELLOW if val >= low else RED)


def make_synthetic_frame(w=640, h=480) -> np.ndarray:
    """Create a synthetic test frame with a rough person-like blob."""
    frame = np.full((h, w, 3), (200, 200, 200), dtype=np.uint8)
    # Draw a person-like shape (oval torso + circle head)
    cx, cy = w // 2, h // 2
    cv2.ellipse(frame, (cx, cy + 20), (40, 70), 0, 0, 360, (60, 60, 180), -1)
    cv2.circle(frame, (cx, cy - 50), 25, (50, 50, 200), -1)
    # Add some noise
    noise = np.random.randint(0, 30, (h, w, 3), dtype=np.uint8)
    frame = cv2.addWeighted(frame, 0.9, noise, 0.1, 0)
    return frame


def _load_detector(backend: str, model_dir: str):
    """Load a detector backend, returning (detector, config)."""
    from .detector_backends import DetectorConfig, create_person_detector

    models = Path(model_dir)

    if backend in ('yolov8_onnx', 'yolov8'):
        model_path = models / 'yolov8n.onnx'
        if not model_path.is_file():
            print(
                f'  {RED}⚠  Model not found: {model_path}{RESET}\n'
                f'  Export it on your host machine:\n'
                f'    pip install ultralytics\n'
                f'    yolo export model=yolov8n.pt format=onnx imgsz=416\n'
                f'    scp yolov8n.onnx ubuntu@pi:~/ros2_ws/models/person_detection/\n'
            )
            return None, None
        config = DetectorConfig(
            backend='yolov8_onnx',
            dnn_model_path=str(model_path),
            min_weight=0.45,
            min_area=0,
            yolov8_input_size=416,
            yolov8_confidence_threshold=0.45,
            yolov8_nms_threshold=0.50,
            yolov8_use_onnxruntime=True,
            yolov8_use_opencv_dnn=False,
        )
    elif backend == 'opencv_dnn_tf_ssd':
        model_path = models / 'frozen_inference_graph.pb'
        config_path = models / 'ssd_mobilenet_v1_coco_2017_11_17.pbtxt'
        if not model_path.is_file() or not config_path.is_file():
            print(f'  {RED}⚠  TF-SSD model files not found in {models}{RESET}')
            return None, None
        config = DetectorConfig(
            backend='opencv_dnn_tf_ssd',
            dnn_model_path=str(model_path),
            dnn_config_path=str(config_path),
            dnn_input_width=300,
            dnn_input_height=300,
            dnn_scale=1.0,
            dnn_mean=0.0,
            dnn_swap_rb=True,
            dnn_person_class_id=1,
            dnn_confidence_threshold=0.45,
            min_weight=0.45,
            min_area=0,
        )
    else:
        raise ValueError(f'unsupported backend: {backend}')

    detector = create_person_detector(config)
    return detector, config


def benchmark_on_frame(detector, frame, num_warmup=5, num_runs=30):
    """Run inference repeatedly and report timing stats."""
    # Warmup
    for _ in range(num_warmup):
        _ = detector.detect(frame)

    times = []
    detections = []
    for _ in range(num_runs):
        t0 = time.perf_counter()
        dets = detector.detect(frame)
        elapsed = time.perf_counter() - t0
        times.append(elapsed)
        detections.append(len(dets))

    times = np.array(times)
    return {
        'mean_ms': float(np.mean(times) * 1000),
        'median_ms': float(np.median(times) * 1000),
        'std_ms': float(np.std(times) * 1000),
        'min_ms': float(np.min(times) * 1000),
        'max_ms': float(np.max(times) * 1000),
        'avg_detections': float(np.mean(detections)),
    }


def print_table(results, frame_label='synthetic 640x480'):
    """Print a comparison table."""
    print(f'\n{BOLD}── Benchmark: {frame_label} ──{RESET}\n')

    headers = ['Backend', 'Mean (ms)', 'Median (ms)', 'Std (ms)', 'Min (ms)', 'Max (ms)', 'Avg dets']
    col_w = [24, 12, 12, 10, 10, 10, 10]

    # Header
    print('  ' + ''.join(h.ljust(w) for h, w in zip(headers, col_w, strict=True)))
    print('  ' + '-' * sum(col_w))

    for backend, r in results.items():
        mean_color = _color(r['mean_ms'], 300, 600)
        row = [
            backend.ljust(col_w[0]),
            f'{mean_color}{r["mean_ms"]:>7.1f}{RESET}'.ljust(col_w[1]),
            f'{r["median_ms"]:>7.1f}'.ljust(col_w[2]),
            f'{r["std_ms"]:>5.1f}'.ljust(col_w[3]),
            f'{r["min_ms"]:>5.1f}'.ljust(col_w[4]),
            f'{r["max_ms"]:>5.1f}'.ljust(col_w[5]),
            f'{r["avg_detections"]:>5.1f}'.ljust(col_w[6]),
        ]
        print('  ' + ''.join(row))

    # Speedup
    if len(results) >= 2:
        backends = list(results.keys())
        t1 = results[backends[0]]['mean_ms']
        t2 = results[backends[1]]['mean_ms']
        if t1 > 0 and t2 > 0:
            ratio = max(t1, t2) / min(t1, t2)
            faster = backends[0] if t1 < t2 else backends[1]
            print(f'\n  {CYAN}▶ {faster} is {ratio:.1f}× faster{RESET}')
    print()


def benchmark_camera(device_id: int, model_dir: str, backends: list):
    """Benchmark using a live camera."""
    cap = cv2.VideoCapture(device_id)
    if not cap.isOpened():
        print(f'{RED}Cannot open camera {device_id}{RESET}')
        return
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

    ret, frame = cap.read()
    if not ret:
        print(f'{RED}Failed to read frame from camera{RESET}')
        cap.release()
        return
    cap.release()

    h, w = frame.shape[:2]
    print(f'{CYAN}Captured frame: {w}x{h}{RESET}')

    results = {}
    for backend in backends:
        print(f'  Loading {backend}... ', end='', flush=True)
        det, _ = _load_detector(backend, model_dir)
        if det is None:
            print(f'{RED}skip{RESET}')
            continue
        print('ok')
        r = benchmark_on_frame(det, frame)
        results[backend] = r

    if results:
        print_table(results, f'camera {w}x{h}')


def benchmark_synthetic(model_dir: str, backends: list):
    """Benchmark using a synthetic test frame."""
    frame = make_synthetic_frame()
    h, w = frame.shape[:2]

    results = {}
    for backend in backends:
        print(f'  Loading {backend}... ', end='', flush=True)
        det, _ = _load_detector(backend, model_dir)
        if det is None:
            print(f'{RED}skip{RESET}')
            continue
        print('ok')
        r = benchmark_on_frame(det, frame)
        results[backend] = r

    if results:
        print_table(results, f'synthetic {w}x{h}')


def main():
    # Ensure we can import from the package
    script_dir = Path(__file__).resolve().parent
    if str(script_dir.parent) not in sys.path:
        sys.path.insert(0, str(script_dir.parent))

    parser = argparse.ArgumentParser(description='Benchmark YOLOv8n vs TF-SSD')
    parser.add_argument('--camera', type=int, default=None,
                        help='Camera device ID for real frame benchmark')
    parser.add_argument('--backend', type=str, default=None,
                        help='Single backend to test (default: both)')
    parser.add_argument('--model-dir', type=str,
                        default=os.path.join(os.environ.get('RASPBOT_WS', '~/ros2_ws'), 'models', 'person_detection'),
                        help='Directory containing model files')
    args = parser.parse_args()

    model_dir = Path(args.model_dir).expanduser()
    backends = ['yolov8_onnx', 'opencv_dnn_tf_ssd']
    if args.backend:
        backends = [args.backend]

    print(f'{BOLD}YOLOv8n vs TF-SSD Benchmark{RESET}')
    print(f'  Model dir: {model_dir}')
    print(f'  Backends:  {", ".join(backends)}')
    print()

    if args.camera is not None:
        benchmark_camera(args.camera, model_dir, backends)
    else:
        benchmark_synthetic(model_dir, backends)


if __name__ == '__main__':
    main()
