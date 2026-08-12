import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import cv2
import rclpy
from rcl_interfaces.msg import SetParametersResult
from rclpy.node import Node
from sensor_msgs.msg import CompressedImage
from std_msgs.msg import Bool, String

from .detector_backends import DetectorConfig, create_person_detector
from .workspace import resolve_workspace_path
from .usb_camera import USBCamera


def render_person_detection_debug_frame(frame, detections, backend_name='', error_msg=''):
    debug = frame.copy()
    height, width = debug.shape[:2]
    banner_height = 92
    banner_bottom = min(height - 1, banner_height)
    max_confidence = max((item[4] for item in detections), default=0.0)
    person_count = len(detections)
    detected = person_count > 0

    # Paint a permanent status banner so debug images differ from raw frames even
    # when the detector returns no people.
    cv2.rectangle(debug, (0, 0), (width - 1, banner_bottom), (18, 18, 18), -1)
    cv2.rectangle(debug, (0, 0), (width - 1, banner_bottom), (0, 255, 255), 2)

    status_text = 'PERSON DETECTED' if detected else 'NO PERSON DETECTED'
    status_color = (0, 220, 0) if detected else (0, 0, 255)
    cv2.putText(
        debug,
        status_text,
        (12, 30),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.8,
        status_color,
        2,
    )
    cv2.putText(
        debug,
        f'backend={backend_name or "unknown"}  count={person_count}  max_conf={max_confidence:.2f}',
        (12, 58),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.6,
        (245, 245, 245),
        2,
    )
    if error_msg:
        cv2.putText(
            debug,
            f'error={error_msg}',
            (12, 82),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            (0, 165, 255),
            1,
        )
    elif not detected:
        cv2.putText(
            debug,
            'status=idle',
            (width // 2, 82),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            (180, 180, 180),
            1,
        )

    for x, y, w, h, confidence in detections:
        cv2.rectangle(debug, (x, y), (x + w, y + h), (0, 255, 0), 2)
        cv2.putText(
            debug,
            f'person {confidence:.2f} [{backend_name}]',
            (x, max(banner_bottom + 18, y - 6)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            (0, 255, 0),
            2,
        )
    return debug


def rotate_frame_for_detection(frame, rotation_deg):
    rotation = int(rotation_deg) % 360
    if rotation == 0:
        return frame
    if rotation == 90:
        return cv2.rotate(frame, cv2.ROTATE_90_CLOCKWISE)
    if rotation == 180:
        return cv2.rotate(frame, cv2.ROTATE_180)
    if rotation == 270:
        return cv2.rotate(frame, cv2.ROTATE_90_COUNTERCLOCKWISE)
    raise ValueError(f'unsupported frame rotation: {rotation_deg}')


class PersonDetectNode(Node):
    def __init__(self):
        super().__init__('raspbot_person_detect')
        self.declare_parameter('camera_device', '/dev/v4l/by-id/usb-Generic_HD_camera_20181212000000-video-index0')
        self.declare_parameter('width', 640)
        self.declare_parameter('height', 480)
        self.declare_parameter('fps', 15)
        self.declare_parameter('loop_hz', 5.0)
        self.declare_parameter('publish_debug', True)
        self.declare_parameter('default_enabled', True)
        self.declare_parameter('continuous_mode', False)
        self.declare_parameter('detector_backend', 'yolov8_onnx')
        self.declare_parameter('detector_fallback_backend', 'opencv_dnn_tf_ssd')
        self.declare_parameter('frame_rotate_deg', 0)
        self.declare_parameter('hog_min_confidence', 0.70)
        self.declare_parameter('hog_min_box_area_ratio', 0.02)
        self.declare_parameter('hog_min_aspect_ratio', 1.30)
        self.declare_parameter('hog_valid_as_confirmed_backend', False)
        self.declare_parameter('hog_scale', 1.05)
        self.declare_parameter('hog_stride', 8)
        self.declare_parameter('hog_padding', 8)
        self.declare_parameter('mean_shift_grouping', False)
        self.declare_parameter('min_weight', 0.45)
        self.declare_parameter('min_area', 4000)
        self.declare_parameter('dnn_model_path', '')
        self.declare_parameter('dnn_config_path', '')
        self.declare_parameter('dnn_input_width', 300)
        self.declare_parameter('dnn_input_height', 300)
        self.declare_parameter('dnn_scale', 0.007843)
        self.declare_parameter('dnn_mean', 127.5)
        self.declare_parameter('dnn_swap_rb', False)
        self.declare_parameter('dnn_person_class_id', 15)
        self.declare_parameter('dnn_confidence_threshold', 0.50)
        self.declare_parameter('yolov8_input_size', 416)
        self.declare_parameter('yolov8_confidence_threshold', 0.45)
        self.declare_parameter('yolov8_nms_threshold', 0.50)
        self.declare_parameter('yolov8_use_onnxruntime', True)
        self.declare_parameter('yolov8_use_opencv_dnn', False)
        self.declare_parameter('frame_read_retries', 3)
        self.declare_parameter('camera_reopen_after_failures', 2)
        self.declare_parameter('detect_on_frames', 1)
        self.declare_parameter('detect_off_frames', 3)
        self.declare_parameter('min_detect_hold_sec', 2.0)
        self.declare_parameter('trigger_scan_frames', 5)
        self.declare_parameter('trigger_scan_interval_sec', 0.12)
        self.declare_parameter('trigger_scan_min_positive_frames', 1)
        self.declare_parameter('trigger_scan_strong_confidence', 0.80)
        self.declare_parameter('clear_after_no_detection_sec', 45.0)
        self.declare_parameter('save_images', True)
        self.declare_parameter('save_raw_images', True)
        self.declare_parameter('save_debug_images', True)
        self.declare_parameter('image_root_dir', '$RASPBOT_WS/data/patrol/images')

        self.camera = USBCamera(
            device=self.get_parameter('camera_device').value,
            width=int(self.get_parameter('width').value),
            height=int(self.get_parameter('height').value),
            fps=int(self.get_parameter('fps').value),
        )
        self.camera_ready = False
        self.consecutive_read_failures = 0
        self.detected_stable_state = False
        self.detect_positive_count = 0
        self.detect_negative_count = 0
        self.last_state_change_monotonic = time.monotonic()
        self.last_positive_detection_monotonic = 0.0
        self.last_positive_detections = []
        self.last_detected = None
        self.last_enabled_state = None
        self.detector = None
        self.active_detector_backend = ''

        self.detected_pub = self.create_publisher(Bool, 'person_detected', 10)
        self.status_pub = self.create_publisher(String, 'person_detection/status', 10)
        self.result_pub = self.create_publisher(String, 'person_detection/result', 10)
        self.debug_pub = self.create_publisher(CompressedImage, 'person_detection/debug/compressed', 10)
        self.create_subscription(Bool, 'person_detection/enabled', self.enabled_callback, 10)
        self.create_subscription(Bool, 'person_detection/trigger', self.trigger_callback, 10)
        self.add_on_set_parameters_callback(self.on_set_parameters)

        self._load_runtime_settings()
        self.trigger_pending = self.enabled and not self.continuous_mode
        self.last_enabled_state = self.enabled
        self.timer = self.create_timer(1.0 / max(self.loop_hz, 0.1), self.timer_callback)
        self.get_logger().info(
            'person detect node started '
            f'(enabled={self.enabled}, continuous_mode={self.continuous_mode}, '
            f'camera_device={self.get_parameter("camera_device").value}, '
            f'detector_backend={self.active_detector_backend}, requested_backend={self.requested_detector_backend}, '
            f'backend_is_fallback={getattr(self, "backend_is_fallback", False)}, '
            f'frame_rotate_deg={self.frame_rotate_deg})'
        )
        if self.frame_rotate_deg == 270:
            self.get_logger().info('person detection orientation note: frame_rotate_deg=270 is active for this camera mount')

    def _build_detector_config(self, backend_name: str) -> DetectorConfig:
        return DetectorConfig(
            backend=backend_name,
            min_weight=self.min_weight,
            min_area=self.min_area,
            hog_scale=self.hog_scale,
            hog_stride=self.hog_stride,
            hog_padding=self.hog_padding,
            hog_min_confidence=self.hog_min_confidence,
            hog_min_box_area_ratio=self.hog_min_box_area_ratio,
            hog_min_aspect_ratio=self.hog_min_aspect_ratio,
            mean_shift_grouping=self.mean_shift_grouping,
            dnn_model_path=self.dnn_model_path,
            dnn_config_path=self.dnn_config_path,
            dnn_input_width=self.dnn_input_width,
            dnn_input_height=self.dnn_input_height,
            dnn_scale=self.dnn_scale,
            dnn_mean=self.dnn_mean,
            dnn_swap_rb=self.dnn_swap_rb,
            dnn_person_class_id=self.dnn_person_class_id,
            dnn_confidence_threshold=self.dnn_confidence_threshold,
            yolov8_input_size=self.yolov8_input_size,
            yolov8_confidence_threshold=self.yolov8_confidence_threshold,
            yolov8_nms_threshold=self.yolov8_nms_threshold,
            yolov8_use_onnxruntime=self.yolov8_use_onnxruntime,
            yolov8_use_opencv_dnn=self.yolov8_use_opencv_dnn,
        )

    def _configure_detector(self):
        requested = self.detector_backend
        backends_to_try = [requested]
        if self.detector_fallback_backend and self.detector_fallback_backend not in backends_to_try:
            backends_to_try.append(self.detector_fallback_backend)
        if 'hog' not in backends_to_try:
            backends_to_try.append('hog')

        self.requested_detector_backend = requested
        self.backend_is_fallback = False
        self.backend_fallback_reason = ''
        self.backend_attempts = []

        last_error = None
        for backend_name in backends_to_try:
            try:
                self.detector = create_person_detector(self._build_detector_config(backend_name))
                self.active_detector_backend = backend_name
                self.backend_is_fallback = backend_name != requested
                if self.backend_is_fallback:
                    attempts = [f"{item['backend']}: {item['error']}" for item in self.backend_attempts]
                    self.backend_fallback_reason = '; '.join(attempts) if attempts else f'requested={requested}'
                    self.get_logger().warning(
                        f'detector backend fallback active: requested={requested}, active={backend_name}, reason={self.backend_fallback_reason}'
                    )
                else:
                    self.get_logger().info(f'detector backend ready: {backend_name}')
                return
            except Exception as exc:
                last_error = exc
                self.backend_attempts.append({'backend': backend_name, 'error': str(exc)})
                self.get_logger().warning(f'failed to initialize detector backend={backend_name}: {exc}')

        raise RuntimeError(f'no usable detector backend, requested={requested}, last_error={last_error}')

    def _load_runtime_settings(self):
        self.loop_hz = float(self.get_parameter('loop_hz').value)
        self.publish_debug = bool(self.get_parameter('publish_debug').value)
        self.enabled = bool(self.get_parameter('default_enabled').value)
        self.continuous_mode = bool(self.get_parameter('continuous_mode').value)
        self.detector_backend = str(self.get_parameter('detector_backend').value)
        self.detector_fallback_backend = str(self.get_parameter('detector_fallback_backend').value)
        self.frame_rotate_deg = int(self.get_parameter('frame_rotate_deg').value)
        self.hog_scale = float(self.get_parameter('hog_scale').value)
        self.hog_stride = int(self.get_parameter('hog_stride').value)
        self.hog_padding = int(self.get_parameter('hog_padding').value)
        self.hog_min_confidence = float(self.get_parameter('hog_min_confidence').value)
        self.hog_min_box_area_ratio = float(self.get_parameter('hog_min_box_area_ratio').value)
        self.hog_min_aspect_ratio = float(self.get_parameter('hog_min_aspect_ratio').value)
        self.hog_valid_as_confirmed_backend = bool(self.get_parameter('hog_valid_as_confirmed_backend').value)
        self.mean_shift_grouping = bool(self.get_parameter('mean_shift_grouping').value)
        self.min_weight = float(self.get_parameter('min_weight').value)
        self.min_area = int(self.get_parameter('min_area').value)
        self.dnn_model_path = str(resolve_workspace_path(self.get_parameter('dnn_model_path').value))
        self.dnn_config_path = str(resolve_workspace_path(self.get_parameter('dnn_config_path').value))
        self.dnn_input_width = max(1, int(self.get_parameter('dnn_input_width').value))
        self.dnn_input_height = max(1, int(self.get_parameter('dnn_input_height').value))
        self.dnn_scale = float(self.get_parameter('dnn_scale').value)
        self.dnn_mean = float(self.get_parameter('dnn_mean').value)
        self.dnn_swap_rb = bool(self.get_parameter('dnn_swap_rb').value)
        self.dnn_person_class_id = int(self.get_parameter('dnn_person_class_id').value)
        self.dnn_confidence_threshold = float(self.get_parameter('dnn_confidence_threshold').value)
        self.yolov8_input_size = max(32, int(self.get_parameter('yolov8_input_size').value))
        self.yolov8_confidence_threshold = float(self.get_parameter('yolov8_confidence_threshold').value)
        self.yolov8_nms_threshold = float(self.get_parameter('yolov8_nms_threshold').value)
        self.yolov8_use_onnxruntime = bool(self.get_parameter('yolov8_use_onnxruntime').value)
        self.yolov8_use_opencv_dnn = bool(self.get_parameter('yolov8_use_opencv_dnn').value)
        self.frame_read_retries = max(1, int(self.get_parameter('frame_read_retries').value))
        self.camera_reopen_after_failures = max(1, int(self.get_parameter('camera_reopen_after_failures').value))
        self.detect_on_frames = max(1, int(self.get_parameter('detect_on_frames').value))
        self.detect_off_frames = max(1, int(self.get_parameter('detect_off_frames').value))
        self.min_detect_hold_sec = max(0.0, float(self.get_parameter('min_detect_hold_sec').value))
        self.trigger_scan_frames = max(1, int(self.get_parameter('trigger_scan_frames').value))
        self.trigger_scan_interval_sec = max(0.0, float(self.get_parameter('trigger_scan_interval_sec').value))
        self.trigger_scan_min_positive_frames = max(1, int(self.get_parameter('trigger_scan_min_positive_frames').value))
        self.trigger_scan_strong_confidence = max(0.0, float(self.get_parameter('trigger_scan_strong_confidence').value))
        self.clear_after_no_detection_sec = max(0.0, float(self.get_parameter('clear_after_no_detection_sec').value))
        self.save_images = bool(self.get_parameter('save_images').value)
        self.save_raw_images = bool(self.get_parameter('save_raw_images').value)
        self.save_debug_images = bool(self.get_parameter('save_debug_images').value)
        self.image_root_dir = resolve_workspace_path(str(self.get_parameter('image_root_dir').value))
        self.image_root_dir.mkdir(parents=True, exist_ok=True)
        self._configure_detector()

    def on_set_parameters(self, params):
        allowed = {
            'loop_hz', 'publish_debug', 'default_enabled', 'continuous_mode',
            'detector_backend', 'detector_fallback_backend', 'frame_rotate_deg',
            'hog_scale', 'hog_stride', 'hog_padding', 'hog_min_confidence',
            'hog_min_box_area_ratio', 'hog_min_aspect_ratio', 'hog_valid_as_confirmed_backend', 'mean_shift_grouping',
            'min_weight', 'min_area', 'dnn_model_path', 'dnn_config_path',
            'dnn_input_width', 'dnn_input_height', 'dnn_scale', 'dnn_mean',
            'dnn_swap_rb', 'dnn_person_class_id', 'dnn_confidence_threshold',
            'frame_read_retries', 'camera_reopen_after_failures',
            'detect_on_frames', 'detect_off_frames', 'min_detect_hold_sec',
            'trigger_scan_frames', 'trigger_scan_interval_sec',
            'trigger_scan_min_positive_frames', 'trigger_scan_strong_confidence',
            'clear_after_no_detection_sec',
            'save_images', 'save_raw_images', 'save_debug_images', 'image_root_dir',
        }
        for param in params:
            if param.name not in allowed:
                continue
            if param.name in {'loop_hz', 'hog_scale', 'dnn_input_width', 'dnn_input_height'} and float(param.value) <= 0.0:
                return SetParametersResult(successful=False, reason=f'{param.name} must be > 0')
            if param.name in {'min_detect_hold_sec', 'trigger_scan_interval_sec', 'trigger_scan_strong_confidence', 'clear_after_no_detection_sec'} and float(param.value) < 0.0:
                return SetParametersResult(successful=False, reason=f'{param.name} must be >= 0')
            if param.name in {'hog_stride', 'hog_padding', 'min_area', 'trigger_scan_min_positive_frames'} and int(param.value) < 0:
                return SetParametersResult(successful=False, reason=f'{param.name} must be >= 0')
            if param.name == 'frame_rotate_deg' and int(param.value) not in {0, 90, 180, 270}:
                return SetParametersResult(successful=False, reason='frame_rotate_deg must be one of 0, 90, 180, 270')
            if param.name in {'hog_min_confidence', 'hog_min_box_area_ratio', 'hog_min_aspect_ratio'} and float(param.value) <= 0.0:
                return SetParametersResult(successful=False, reason=f'{param.name} must be > 0')
        try:
            self._load_runtime_settings()
        except Exception as exc:
            return SetParametersResult(successful=False, reason=str(exc))
        return SetParametersResult(successful=True)

    def enabled_callback(self, msg: Bool):
        self.enabled = bool(msg.data)
        if self.enabled and not self.continuous_mode:
            self.trigger_pending = True
        if self.enabled != self.last_enabled_state:
            self.get_logger().info(f'person detection enabled={self.enabled}')
            self.last_enabled_state = self.enabled

    def trigger_callback(self, msg: Bool):
        if msg.data:
            self.trigger_pending = True

    def _render_debug_frame(self, frame, detections):
        return render_person_detection_debug_frame(
            frame,
            detections,
            backend_name=self.active_detector_backend,
        )

    def _publish_debug(self, debug_frame):
        if not self.publish_debug or debug_frame is None:
            return
        ok, encoded = cv2.imencode('.jpg', debug_frame)
        if not ok:
            return
        msg = CompressedImage()
        msg.format = 'jpeg'
        msg.data = encoded.tobytes()
        self.debug_pub.publish(msg)

    def _build_payload(
        self,
        detections,
        error_msg='',
        raw_image_path='',
        debug_image_path='',
        scan_positive_frames=0,
        scan_total_frames=0,
        evidence_detections=None,
        decision_reason='',
    ):
        evidence_detections = detections if evidence_detections is None else evidence_detections
        detected = bool(detections)
        evidence_detected = bool(evidence_detections)
        max_confidence = max((item[4] for item in detections), default=0.0)
        evidence_max_confidence = max((item[4] for item in evidence_detections), default=0.0)
        return {
            'timestamp_utc': datetime.now(timezone.utc).isoformat(),
            'detected': detected,
            'person_count': len(detections),
            'max_confidence': max_confidence,
            'evidence_detected': evidence_detected,
            'evidence_person_count': len(evidence_detections),
            'evidence_max_confidence': evidence_max_confidence,
            'mode': 'continuous' if self.continuous_mode else 'triggered',
            'camera_backend': self.camera.backend or '',
            'backend_requested': getattr(self, 'requested_detector_backend', self.detector_backend),
            'backend_active': self.active_detector_backend,
            'backend_is_fallback': bool(getattr(self, 'backend_is_fallback', False)),
            'backend_fallback_reason': getattr(self, 'backend_fallback_reason', ''),
            'backend_attempts': list(getattr(self, 'backend_attempts', [])),
            'detector_backend': self.active_detector_backend,
            'decision_reason': decision_reason,
            'frame_rotate_deg': int(getattr(self, 'frame_rotate_deg', 0)),
            'error_msg': error_msg,
            'raw_image_path': raw_image_path,
            'debug_image_path': debug_image_path,
            'scan_positive_frames': int(scan_positive_frames),
            'scan_total_frames': int(scan_total_frames),
        }

    def _publish_payload(self, payload, publish_status=True):
        detected_msg = Bool()
        detected_msg.data = bool(payload.get('detected', False))
        self.detected_pub.publish(detected_msg)

        result_msg = String()
        result_msg.data = json.dumps(payload, ensure_ascii=True)
        self.result_pub.publish(result_msg)

        if publish_status:
            status_msg = String()
            status_msg.data = result_msg.data
            self.status_pub.publish(status_msg)

        detected = bool(payload.get('detected', False))
        max_confidence = float(payload.get('max_confidence', 0.0))
        person_count = int(payload.get('person_count', 0))
        error_msg = str(payload.get('error_msg', ''))
        detector_backend = str(payload.get('detector_backend', self.active_detector_backend))
        backend_requested = str(payload.get('backend_requested', self.detector_backend))
        backend_is_fallback = bool(payload.get('backend_is_fallback', False))
        backend_fallback_reason = str(payload.get('backend_fallback_reason', ''))
        decision_reason = str(payload.get('decision_reason', ''))
        if error_msg:
            self.get_logger().warning(f'person detection error ({detector_backend}): {error_msg}')
        elif backend_is_fallback and backend_fallback_reason:
            self.get_logger().warning(
                f'person detection backend fallback active: requested={backend_requested}, '
                f'active={detector_backend}, reason={backend_fallback_reason}'
            )
        elif decision_reason == 'hog_backend_detected_but_low_reliability_for_close_range':
            self.get_logger().warning(
                'person detection low reliability: '
                f'backend={detector_backend}, count={person_count}, max_confidence={max_confidence:.2f}'
            )
        elif self.last_detected is None or self.last_detected != detected:
            self.get_logger().info(
                f'person detection changed: detected={detected}, count={person_count}, '
                f'max_confidence={max_confidence:.2f}, detector_backend={detector_backend}'
            )
        self.last_detected = detected

    def _read_frame_with_retry(self):
        for attempt in range(self.frame_read_retries):
            frame = self.camera.read()
            if frame is not None:
                return frame
            if attempt + 1 < self.frame_read_retries:
                time.sleep(0.12)
        return None

    def _detect_on_frame(self, frame):
        if self.detector is None:
            raise RuntimeError('detector backend is not initialized')
        return self.detector.detect(frame)

    def _detection_rank(self, detections):
        if not detections:
            return (0.0, 0, 0)
        max_confidence = max((item[4] for item in detections), default=0.0)
        max_area = max((int(item[2]) * int(item[3]) for item in detections), default=0)
        return (float(max_confidence), len(detections), max_area)

    def _scan_trigger_window(self, first_frame):
        first_detections = self._detect_on_frame(first_frame)
        frames_and_detections = [(first_frame, first_detections)]

        if not self.continuous_mode and self.trigger_scan_frames > 1:
            for _ in range(self.trigger_scan_frames - 1):
                if self.trigger_scan_interval_sec > 0.0:
                    time.sleep(self.trigger_scan_interval_sec)
                frame = self._read_frame_with_retry()
                if frame is None:
                    continue
                detections = self._detect_on_frame(frame)
                frames_and_detections.append((frame, detections))

        best_frame, best_detections = max(
            frames_and_detections,
            key=lambda item: self._detection_rank(item[1]),
        )
        best_score = max((item[4] for item in best_detections), default=0.0)
        positive_frame_count = sum(1 for _, detections in frames_and_detections if detections)
        total_frame_count = len(frames_and_detections)

        accepted_detections = best_detections
        if not self.continuous_mode and best_detections:
            accepted = (
                positive_frame_count >= self.trigger_scan_min_positive_frames
                or best_score >= self.trigger_scan_strong_confidence
            )
            if not accepted:
                accepted_detections = []

        return best_frame, accepted_detections, best_detections, positive_frame_count, total_frame_count

    def _debounce_detections(self, detections):
        raw_detected = bool(detections)
        now = time.monotonic()
        if raw_detected:
            self.detect_positive_count += 1
            self.detect_negative_count = 0
            self.last_positive_detection_monotonic = now
            self.last_positive_detections = detections
        else:
            self.detect_negative_count += 1
            self.detect_positive_count = 0

        if not self.detected_stable_state:
            if raw_detected and self.detect_positive_count >= self.detect_on_frames:
                self.detected_stable_state = True
                self.last_state_change_monotonic = now
                return self.last_positive_detections
            return []

        if raw_detected:
            return self.last_positive_detections

        held_for = now - self.last_state_change_monotonic
        no_detection_for = now - self.last_positive_detection_monotonic if self.last_positive_detection_monotonic > 0.0 else now
        if (
            self.detect_negative_count >= self.detect_off_frames
            and held_for >= self.min_detect_hold_sec
            and no_detection_for >= self.clear_after_no_detection_sec
        ):
            self.detected_stable_state = False
            self.last_state_change_monotonic = now
            return []
        return self.last_positive_detections

    def _save_detection_images(self, raw_frame, debug_source_frame, detections):
        if not self.save_images or raw_frame is None:
            return '', '', None

        now_dt = datetime.now(timezone.utc).astimezone()
        day_dir = self.image_root_dir / now_dt.strftime('%Y-%m-%d')
        day_dir.mkdir(parents=True, exist_ok=True)
        stem = now_dt.strftime('detect_%Y%m%dT%H%M%S_%f')

        raw_image_path = ''
        if self.save_raw_images:
            raw_path = day_dir / f'{stem}_raw.jpg'
            if cv2.imwrite(str(raw_path), raw_frame):
                raw_image_path = str(raw_path)

        debug_frame = self._render_debug_frame(debug_source_frame, detections)
        debug_image_path = ''
        if self.save_debug_images:
            debug_path = day_dir / f'{stem}_debug.jpg'
            if cv2.imwrite(str(debug_path), debug_frame):
                debug_image_path = str(debug_path)

        return raw_image_path, debug_image_path, debug_frame

    def timer_callback(self):
        if not self.enabled:
            return
        if not self.continuous_mode and not self.trigger_pending:
            return
        self.trigger_pending = False

        if not self.camera_ready:
            try:
                self.camera.open(retry=1)
                self.camera_ready = True
                self.consecutive_read_failures = 0
                self.get_logger().info(f'person detection camera ready via backend={self.camera.backend}')
            except Exception as exc:
                self.get_logger().warning(f'failed to open person detection camera: {exc}')
                self._publish_payload(self._build_payload([], error_msg=f'camera_open_failed: {exc}'), publish_status=False)
                return

        raw_frame = self._read_frame_with_retry()
        if raw_frame is None:
            self.consecutive_read_failures += 1
            if self.consecutive_read_failures >= self.camera_reopen_after_failures:
                self.camera.release()
                self.camera_ready = False
            error_msg = (
                'camera_read_failed: '
                f'consecutive_failures={self.consecutive_read_failures}, '
                f'reopen_after={self.camera_reopen_after_failures}, backend={self.camera.backend}, '
                f'last_error={self.camera.last_error}'
            )
            self.get_logger().warning(error_msg)
            self._publish_payload(self._build_payload([], error_msg=error_msg), publish_status=False)
            return
        self.consecutive_read_failures = 0
        detect_frame = rotate_frame_for_detection(raw_frame, self.frame_rotate_deg)

        try:
            scan_frame, detections, evidence_detections, positive_frame_count, total_frame_count = self._scan_trigger_window(detect_frame)
        except Exception as exc:
            error_msg = f'detector_failed: backend={self.active_detector_backend}, error={exc}'
            self.get_logger().warning(error_msg)
            self._publish_payload(self._build_payload([], error_msg=error_msg), publish_status=False)
            return

        stable_detections = self._debounce_detections(detections)
        confirmed_detections = stable_detections
        if self.active_detector_backend == 'hog' and not self.hog_valid_as_confirmed_backend:
            confirmed_detections = []
        rendered_detections = confirmed_detections if confirmed_detections else evidence_detections
        raw_image_path, debug_image_path, debug_frame = self._save_detection_images(raw_frame, scan_frame, rendered_detections)

        if self.active_detector_backend == 'hog':
            decision_reason = (
                'hog_backend_detected_but_low_reliability_for_close_range'
                if evidence_detections else 'hog_backend_no_detection'
            )
        elif self.backend_is_fallback:
            decision_reason = 'backend_fallback_active'
        elif confirmed_detections:
            decision_reason = 'confirmed_detection'
        else:
            decision_reason = 'no_detection'

        payload = self._build_payload(
            confirmed_detections,
            raw_image_path=raw_image_path,
            debug_image_path=debug_image_path,
            scan_positive_frames=positive_frame_count,
            scan_total_frames=total_frame_count,
            evidence_detections=evidence_detections,
            decision_reason=decision_reason,
        )
        self._publish_payload(payload, publish_status=True)
        if debug_frame is None:
            debug_frame = self._render_debug_frame(scan_frame, rendered_detections)
        self._publish_debug(debug_frame)

    def destroy_node(self):
        try:
            self.camera.release()
        finally:
            super().destroy_node()


def main(args=None):
    rclpy.init(args=args)
    node = PersonDetectNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
