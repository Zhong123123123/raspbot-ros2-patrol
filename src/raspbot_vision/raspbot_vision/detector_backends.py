from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List, Sequence, Tuple

import cv2
import numpy as np

from .workspace import resolve_workspace_path

Detection = Tuple[int, int, int, int, float]


@dataclass
class DetectorConfig:
    backend: str = 'hog'
    min_weight: float = 0.45
    min_area: int = 4000
    hog_scale: float = 1.05
    hog_stride: int = 8
    hog_padding: int = 8
    hog_min_confidence: float = 0.70
    hog_min_box_area_ratio: float = 0.02
    hog_min_aspect_ratio: float = 1.30
    mean_shift_grouping: bool = False
    dnn_model_path: str = ''
    dnn_config_path: str = ''
    dnn_input_width: int = 300
    dnn_input_height: int = 300
    dnn_scale: float = 0.007843
    dnn_mean: float = 127.5
    dnn_swap_rb: bool = False
    dnn_person_class_id: int = 15
    dnn_confidence_threshold: float = 0.50
    # YOLOv8 ONNX settings
    yolov8_input_size: int = 416
    yolov8_confidence_threshold: float = 0.45
    yolov8_nms_threshold: float = 0.50
    yolov8_use_onnxruntime: bool = True
    # Path for OpenCV DNN fallback when onnxruntime unavailable
    yolov8_use_opencv_dnn: bool = False


class BasePersonDetector:
    backend_name = 'base'

    def __init__(self, config: DetectorConfig):
        self.config = config

    def detect(self, frame) -> List[Detection]:
        raise NotImplementedError

    def _filter_detections(self, detections: Sequence[Detection]) -> List[Detection]:
        filtered: List[Detection] = []
        for x, y, w, h, confidence in detections:
            if float(confidence) < self.config.min_weight:
                continue
            if int(w) * int(h) < self.config.min_area:
                continue
            filtered.append((int(x), int(y), int(w), int(h), float(confidence)))
        return filtered


class HogPersonDetector(BasePersonDetector):
    backend_name = 'hog'

    def __init__(self, config: DetectorConfig):
        super().__init__(config)
        self.hog = cv2.HOGDescriptor()
        self.hog.setSVMDetector(cv2.HOGDescriptor_getDefaultPeopleDetector())

    def detect(self, frame) -> List[Detection]:
        rects, weights = self.hog.detectMultiScale(
            frame,
            winStride=(self.config.hog_stride, self.config.hog_stride),
            padding=(self.config.hog_padding, self.config.hog_padding),
            scale=self.config.hog_scale,
            useMeanshiftGrouping=self.config.mean_shift_grouping,
        )
        frame_area = float(max(1, int(frame.shape[0]) * int(frame.shape[1])))
        detections: List[Detection] = []
        for rect, weight in zip(rects, weights, strict=False):
            x, y, w, h = [int(v) for v in rect]
            confidence = float(weight[0] if hasattr(weight, '__len__') else weight)
            if confidence < self.config.hog_min_confidence:
                continue
            if (int(w) * int(h)) / frame_area < self.config.hog_min_box_area_ratio:
                continue
            if h <= 0 or (float(h) / float(max(1, w))) < self.config.hog_min_aspect_ratio:
                continue
            detections.append((x, y, w, h, confidence))
        return self._filter_detections(detections)


class OpenCVDnnCaffeSSDPersonDetector(BasePersonDetector):
    backend_name = 'opencv_dnn_ssd'

    def __init__(self, config: DetectorConfig):
        super().__init__(config)
        model_path = resolve_workspace_path(config.dnn_model_path)
        config_path = resolve_workspace_path(config.dnn_config_path)
        if not model_path.is_file():
            raise FileNotFoundError(f'dnn_model_path not found: {model_path}')
        if not config_path.is_file():
            raise FileNotFoundError(f'dnn_config_path not found: {config_path}')
        self.net = cv2.dnn.readNetFromCaffe(str(config_path), str(model_path))

    def detect(self, frame) -> List[Detection]:
        blob = cv2.dnn.blobFromImage(
            cv2.resize(frame, (self.config.dnn_input_width, self.config.dnn_input_height)),
            scalefactor=self.config.dnn_scale,
            size=(self.config.dnn_input_width, self.config.dnn_input_height),
            mean=(self.config.dnn_mean, self.config.dnn_mean, self.config.dnn_mean),
            swapRB=self.config.dnn_swap_rb,
            crop=False,
        )
        self.net.setInput(blob)
        outputs = self.net.forward()
        return self._extract_ssd_detections(outputs, frame.shape[1], frame.shape[0])

    def _extract_ssd_detections(self, outputs, width: int, height: int) -> List[Detection]:
        detections: List[Detection] = []
        for idx in range(outputs.shape[2]):
            confidence = float(outputs[0, 0, idx, 2])
            class_id = int(outputs[0, 0, idx, 1])
            if class_id != self.config.dnn_person_class_id:
                continue
            if confidence < self.config.dnn_confidence_threshold:
                continue
            box = outputs[0, 0, idx, 3:7] * np.array([width, height, width, height])
            x1, y1, x2, y2 = box.astype('int')
            x = max(0, x1)
            y = max(0, y1)
            w = max(0, x2 - x1)
            h = max(0, y2 - y1)
            detections.append((x, y, w, h, confidence))
        return self._filter_detections(detections)


class OpenCVDnnTensorflowSSDPersonDetector(OpenCVDnnCaffeSSDPersonDetector):
    backend_name = 'opencv_dnn_tf_ssd'

    def __init__(self, config: DetectorConfig):
        BasePersonDetector.__init__(self, config)
        model_path = resolve_workspace_path(config.dnn_model_path)
        config_path = resolve_workspace_path(config.dnn_config_path)
        if not model_path.is_file():
            raise FileNotFoundError(f'dnn_model_path not found: {model_path}')
        if not config_path.is_file():
            raise FileNotFoundError(f'dnn_config_path not found: {config_path}')
        self.net = cv2.dnn.readNetFromTensorflow(str(model_path), str(config_path))


class YoloV8PersonDetector(BasePersonDetector):
    """YOLOv8 ONNX person detector.

    Supports two inference backends:
      1. ONNX Runtime (default) — faster on ARM Cortex-A72
      2. OpenCV DNN — fallback, no extra dependency

    YOLOv8 ONNX output shape: (1, 84, 8400)
      - 4 bbox coords (cx, cy, w, h) normalized to [0, 1]
      - 80 COCO class scores
      - Person class ID: 0
      - 8400 anchors across three grid scales
    """

    COCO_PERSON_CLASS_ID = 0
    COCO_NUM_CLASSES = 80
    OUTPUT_CHANNELS = 84
    NUM_ANCHORS = 8400

    backend_name = 'yolov8_onnx'

    def __init__(self, config: DetectorConfig):
        super().__init__(config)
        self.input_size = config.yolov8_input_size  # 416
        self.conf_threshold = config.yolov8_confidence_threshold
        self.nms_threshold = config.yolov8_nms_threshold

        model_path = self._resolve_model_path(config)
        if not model_path.is_file():
            raise FileNotFoundError(f'yolov8 model not found: {model_path}')

        self._sess = None
        self._net = None

        # Prefer ONNX Runtime; fall back to OpenCV DNN if configured
        if config.yolov8_use_onnxruntime and not config.yolov8_use_opencv_dnn:
            self._sess = self._init_onnxruntime(str(model_path))
        else:
            self._net = cv2.dnn.readNetFromONNX(str(model_path))

    @staticmethod
    def _resolve_model_path(config: DetectorConfig) -> Path:
        """Resolve model path, preferring size-suffixed file when available.

        If config specifies ``models/yolov8n.onnx`` and input_size=320,
        checks for ``models/yolov8n_320.onnx`` first. Falls back to the
        literal path in config.
        """
        path = resolve_workspace_path(config.dnn_model_path)
        if config.yolov8_input_size != 416:
            stem = path.stem  # e.g. "yolov8n"
            parent = path.parent
            sized = parent / f'{stem}_{config.yolov8_input_size}.onnx'
            if sized.is_file():
                return sized
        return path

    # ------------------------------------------------------------------
    # Init helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _init_onnxruntime(model_path: str):
        try:
            import onnxruntime as ort
        except ImportError as exc:
            raise ImportError(
                'onnxruntime not installed; install with: pip install onnxruntime'
            ) from exc
        sess_opts = ort.SessionOptions()
        sess_opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        sess_opts.enable_cpu_mem_arena = True
        sess_opts.intra_op_num_threads = 2  # leave headroom for camera pipeline
        sess_opts.inter_op_num_threads = 1
        return ort.InferenceSession(
            model_path, sess_opts,
            providers=['CPUExecutionProvider'],
        )

    # ------------------------------------------------------------------
    # Preprocessing
    # ------------------------------------------------------------------

    def _letterbox(
        self, frame: np.ndarray,
    ) -> Tuple[np.ndarray, float, int, int]:
        """Resize with aspect-ratio-preserving padding (letterbox).

        Returns:
          (padded_rgb_frame, scale, pad_x, pad_y)
        """
        h, w = frame.shape[:2]
        size = self.input_size
        scale = min(size / w, size / h)
        new_w = int(round(w * scale))
        new_h = int(round(h * scale))

        resized = cv2.resize(frame, (new_w, new_h), interpolation=cv2.INTER_LINEAR)
        pad_w = size - new_w
        pad_h = size - new_h

        # Split padding evenly on both sides
        top = pad_h // 2
        bottom = pad_h - top
        left = pad_w // 2
        right = pad_w - left

        padded = cv2.copyMakeBorder(
            resized, top, bottom, left, right,
            cv2.BORDER_CONSTANT, value=(114, 114, 114),
        )
        # YOLO expects RGB
        rgb = cv2.cvtColor(padded, cv2.COLOR_BGR2RGB)
        return rgb, scale, left, top

    @staticmethod
    def _yolo_normalize(frame: np.ndarray) -> np.ndarray:
        """Convert uint8 [0,255] → float32 [0,1] and add batch dim."""
        return frame.astype(np.float32) / 255.0

    # ------------------------------------------------------------------
    # Postprocessing
    # ------------------------------------------------------------------

    def _decode_outputs(
        self, outputs: np.ndarray, img_w: int, img_h: int,
        scale: float, pad_x: int, pad_y: int,
    ) -> List[Detection]:
        """Decode YOLOv8 raw output into Detection list with NMS.

        ``outputs`` shape can be (1, 84, 8400) or (1, 8400, 84).
        """
        if outputs.shape[1] != self.OUTPUT_CHANNELS:
            # transposed: (1, 8400, 84) → (1, 84, 8400)
            outputs = outputs.transpose(0, 2, 1)

        anchors = outputs[0]  # (84, N)
        boxes = anchors[:4]   # (4, N) — cx, cy, w, h
        scores = anchors[4:]  # (80, N)

        # Person scores (class ID 0) — shape (N,)
        person_scores = scores[self.COCO_PERSON_CLASS_ID]

        # Filter by confidence before decoding boxes.
        mask = person_scores >= self.conf_threshold
        if not mask.any():
            return []

        boxes = boxes[:, mask]       # (4, M)
        person_scores = person_scores[mask]  # (M,)

        # YOLOv8 exports can represent boxes in either normalized [0, 1]
        # coordinates or in input-image pixel coordinates. Treat small values
        # as normalized and scale them up to the model input size.
        box_max = float(np.max(boxes)) if boxes.size else 0.0
        box_scale = float(self.input_size) if box_max <= 1.5 else 1.0

        raw_detections: List[Detection] = []
        for i in range(boxes.shape[1]):
            cx, cy, bw, bh = (float(v) * box_scale for v in boxes[:, i])
            # Convert center-format boxes from the letterboxed model space
            # back to the original image space.
            x1 = (cx - bw / 2.0 - pad_x) / scale
            y1 = (cy - bh / 2.0 - pad_y) / scale
            w = bw / scale
            h = bh / scale
            x = int(max(0, x1))
            y = int(max(0, y1))
            w = int(min(w, img_w - x))
            h = int(min(h, img_h - y))
            conf = float(person_scores[i])
            if w > 0 and h > 0:
                raw_detections.append((x, y, w, h, conf))

        # NMS
        if len(raw_detections) < 2:
            return self._filter_detections(raw_detections)

        bboxes = np.array([[d[0], d[1], d[0] + d[2], d[1] + d[3], d[4]]
                           for d in raw_detections], dtype=np.float32)
        keep = cv2.dnn.NMSBoxes(
            bboxes[:, :4].tolist(),
            bboxes[:, 4].tolist(),
            self.conf_threshold,
            self.nms_threshold,
        )
        if keep is None or len(keep) == 0:
            return []
        keep = keep.flatten() if isinstance(keep, np.ndarray) else [k[0] for k in keep]
        filtered = [raw_detections[i] for i in keep]
        return self._filter_detections(filtered)

    # ------------------------------------------------------------------
    # Detect
    # ------------------------------------------------------------------

    def detect(self, frame: np.ndarray) -> List[Detection]:
        img_h, img_w = frame.shape[:2]

        # Preprocess
        padded_rgb, scale, pad_x, pad_y = self._letterbox(frame)
        blob = self._yolo_normalize(padded_rgb)  # (640,640,3)

        # Infer
        if self._sess is not None:
            # ONNX Runtime
            input_name = self._sess.get_inputs()[0].name
            # ORT wants NCHW
            input_blob = np.expand_dims(blob.transpose(2, 0, 1), axis=0).astype(np.float32)
            outputs = self._sess.run(None, {input_name: input_blob})[0]
        else:
            # OpenCV DNN
            blob_4d = cv2.dnn.blobFromImage(
                padded_rgb, scalefactor=1.0 / 255.0,
                size=(self.input_size, self.input_size),
                mean=(0, 0, 0), swapRB=False, crop=False,
            )
            self._net.setInput(blob_4d)
            outputs = self._net.forward()
            # OpenCV DNN may return different shapes; try to handle
            if outputs.ndim == 4:
                outputs = outputs.squeeze(0)
            if outputs.shape[0] == self.NUM_ANCHORS:
                outputs = outputs.transpose(1, 0)[np.newaxis, :, :]

        return self._decode_outputs(outputs, img_w, img_h, scale, pad_x, pad_y)


def create_person_detector(config: DetectorConfig) -> BasePersonDetector:
    backend = str(config.backend).strip().lower()
    if backend == 'hog':
        return HogPersonDetector(config)
    if backend == 'opencv_dnn_ssd':
        return OpenCVDnnCaffeSSDPersonDetector(config)
    if backend == 'opencv_dnn_tf_ssd':
        return OpenCVDnnTensorflowSSDPersonDetector(config)
    if backend in ('yolov8_onnx', 'yolov8'):
        return YoloV8PersonDetector(config)
    raise ValueError(f'unsupported detector backend: {config.backend}')
