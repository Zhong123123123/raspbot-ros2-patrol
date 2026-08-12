import argparse
import json
import statistics
import time
from pathlib import Path

from .detector_backends import DetectorConfig, create_person_detector
from .usb_camera import USBCamera
from .workspace import workspace_path


DEFAULT_DEVICE = '/dev/v4l/by-id/usb-Generic_HD_camera_20181212000000-video-index0'
DEFAULT_MODEL = str(workspace_path('models', 'person_detection', 'frozen_inference_graph.pb'))
DEFAULT_PBTXT = str(workspace_path('models', 'person_detection', 'ssd_mobilenet_v1_coco_2017_11_17.pbtxt'))


def parse_args():
    parser = argparse.ArgumentParser(description='Compare HOG and TF-SSD person detectors on the same camera frames.')
    parser.add_argument('--camera-device', default=DEFAULT_DEVICE)
    parser.add_argument('--width', type=int, default=640)
    parser.add_argument('--height', type=int, default=480)
    parser.add_argument('--fps', type=int, default=15)
    parser.add_argument('--frames', type=int, default=8)
    parser.add_argument('--warmup-sec', type=float, default=0.8)
    parser.add_argument('--output-json', default='')
    parser.add_argument('--tf-threshold', type=float, default=0.50)
    parser.add_argument('--hog-min-weight', type=float, default=0.60)
    parser.add_argument('--min-area', type=int, default=4000)
    return parser.parse_args()


def build_detectors(args):
    hog = create_person_detector(
        DetectorConfig(
            backend='hog',
            min_weight=args.hog_min_weight,
            min_area=args.min_area,
            hog_scale=1.05,
            hog_stride=8,
            hog_padding=8,
            mean_shift_grouping=False,
        )
    )
    tf_ssd = create_person_detector(
        DetectorConfig(
            backend='opencv_dnn_tf_ssd',
            min_weight=args.tf_threshold,
            min_area=args.min_area,
            dnn_model_path=DEFAULT_MODEL,
            dnn_config_path=DEFAULT_PBTXT,
            dnn_input_width=300,
            dnn_input_height=300,
            dnn_scale=1.0,
            dnn_mean=0.0,
            dnn_swap_rb=True,
            dnn_person_class_id=1,
            dnn_confidence_threshold=args.tf_threshold,
        )
    )
    return [('hog', hog), ('opencv_dnn_tf_ssd', tf_ssd)]


def summarize_backend(name, latencies_ms, detections_per_frame, confidences):
    frames = len(latencies_ms)
    positive_frames = sum(1 for count in detections_per_frame if count > 0)
    return {
        'backend': name,
        'frames': frames,
        'avg_latency_ms': round(statistics.mean(latencies_ms), 2) if latencies_ms else 0.0,
        'p95_latency_ms': round(max(latencies_ms), 2) if latencies_ms else 0.0,
        'positive_frames': positive_frames,
        'positive_ratio': round(positive_frames / frames, 3) if frames else 0.0,
        'avg_person_count': round(statistics.mean(detections_per_frame), 3) if detections_per_frame else 0.0,
        'max_confidence': round(max(confidences), 3) if confidences else 0.0,
        'avg_confidence': round(statistics.mean(confidences), 3) if confidences else 0.0,
    }


def main():
    args = parse_args()
    camera = USBCamera(args.camera_device, args.width, args.height, args.fps)
    camera.open(retry=1)
    if args.warmup_sec > 0.0:
        time.sleep(args.warmup_sec)

    detectors = build_detectors(args)
    results = {name: {'latencies_ms': [], 'detections_per_frame': [], 'confidences': []} for name, _ in detectors}
    frame_summaries = []

    try:
        for frame_idx in range(args.frames):
            frame = camera.read()
            if frame is None:
                raise RuntimeError(f'camera read failed at frame {frame_idx}')
            frame_summary = {'frame_index': frame_idx}
            for name, detector in detectors:
                start = time.perf_counter()
                detections = detector.detect(frame)
                latency_ms = (time.perf_counter() - start) * 1000.0
                max_conf = max((item[4] for item in detections), default=0.0)
                results[name]['latencies_ms'].append(latency_ms)
                results[name]['detections_per_frame'].append(len(detections))
                if detections:
                    results[name]['confidences'].extend(item[4] for item in detections)
                frame_summary[name] = {
                    'latency_ms': round(latency_ms, 2),
                    'count': len(detections),
                    'max_confidence': round(max_conf, 3),
                }
            frame_summaries.append(frame_summary)

        summary = {
            'camera_backend': camera.backend,
            'camera_device': args.camera_device,
            'frames': args.frames,
            'frame_summaries': frame_summaries,
            'backend_summaries': [
                summarize_backend(name, data['latencies_ms'], data['detections_per_frame'], data['confidences'])
                for name, data in results.items()
            ],
        }
        print(json.dumps(summary, ensure_ascii=True, indent=2))
        if args.output_json:
            output_path = Path(args.output_json).expanduser()
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(json.dumps(summary, ensure_ascii=True, indent=2))
            print(f'written_json={output_path}')
    finally:
        camera.release()


if __name__ == '__main__':
    main()
