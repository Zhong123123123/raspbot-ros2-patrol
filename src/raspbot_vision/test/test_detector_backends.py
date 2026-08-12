"""Unit tests for raspbot_vision.detector_backends.

Covers:
  - create_person_detector factory (valid and invalid backends)
  - DetectorConfig defaults and field types
  - BasePersonDetector._filter_detections (confidence + area thresholds)
  - HOG detector initialisation (no model file needed for HOG)
"""

import pytest

cv2 = pytest.importorskip("cv2", reason="OpenCV runtime dependency is not installed")
_HOG_AVAILABLE = hasattr(cv2, "HOGDescriptor")

_hog_skip_reason = "OpenCV >= 5 removed HOGDescriptor; HOG tests require opencv < 5"


# ============================================================================
#  create_person_detector factory
# ============================================================================

class TestCreatePersonDetector:
    @pytest.mark.skipif(not _HOG_AVAILABLE, reason=_hog_skip_reason)
    def test_hog_backend_returns_hog_detector(self, default_detector_config):
        from raspbot_vision.detector_backends import (
            HogPersonDetector,
            create_person_detector,
        )

        default_detector_config.backend = "hog"
        detector = create_person_detector(default_detector_config)
        assert isinstance(detector, HogPersonDetector)
        assert detector.backend_name == "hog"

    def test_unknown_backend_raises_value_error(self, default_detector_config):
        from raspbot_vision.detector_backends import create_person_detector

        default_detector_config.backend = "nonexistent_backend_xyz"
        with pytest.raises(ValueError, match="unsupported detector backend"):
            create_person_detector(default_detector_config)

    def test_empty_backend_raises_value_error(self, default_detector_config):
        from raspbot_vision.detector_backends import create_person_detector

        default_detector_config.backend = ""
        with pytest.raises(ValueError, match="unsupported detector backend"):
            create_person_detector(default_detector_config)

    @pytest.mark.skipif(not _HOG_AVAILABLE, reason=_hog_skip_reason)
    def test_backend_name_case_insensitive(self, default_detector_config):
        from raspbot_vision.detector_backends import (
            HogPersonDetector,
            create_person_detector,
        )

        default_detector_config.backend = "HOG"
        detector = create_person_detector(default_detector_config)
        assert isinstance(detector, HogPersonDetector)

    def test_dnn_caffe_requires_model_file(self, default_detector_config):
        from raspbot_vision.detector_backends import create_person_detector

        default_detector_config.backend = "opencv_dnn_ssd"
        default_detector_config.dnn_model_path = "/nonexistent/model.pb"
        with pytest.raises(FileNotFoundError):
            create_person_detector(default_detector_config)

    def test_dnn_tf_ssd_requires_model_file(self, default_detector_config):
        from raspbot_vision.detector_backends import create_person_detector

        default_detector_config.backend = "opencv_dnn_tf_ssd"
        default_detector_config.dnn_model_path = "/nonexistent/model.pb"
        with pytest.raises(FileNotFoundError):
            create_person_detector(default_detector_config)

    def test_yolov8_onnx_requires_model_file(self, default_detector_config):
        from raspbot_vision.detector_backends import create_person_detector

        default_detector_config.backend = "yolov8_onnx"
        default_detector_config.dnn_model_path = "/nonexistent/yolov8n.onnx"
        with pytest.raises(FileNotFoundError):
            create_person_detector(default_detector_config)

    def test_yolov8_alias_works(self, default_detector_config):
        from raspbot_vision.detector_backends import create_person_detector

        default_detector_config.backend = "yolov8"
        default_detector_config.dnn_model_path = "/nonexistent/yolov8n.onnx"
        with pytest.raises(FileNotFoundError, match="yolov8 model not found"):
            create_person_detector(default_detector_config)


# ============================================================================
#  DetectorConfig
# ============================================================================

class TestDetectorConfig:
    def test_defaults_match_project_convention(self):
        from raspbot_vision.detector_backends import DetectorConfig

        cfg = DetectorConfig()
        assert cfg.backend == "hog"
        assert cfg.min_weight == 0.45
        assert cfg.min_area == 4000
        assert cfg.hog_scale == 1.05
        assert cfg.hog_stride == 8
        assert cfg.hog_padding == 8
        assert cfg.mean_shift_grouping is False
        assert cfg.dnn_confidence_threshold == 0.50
        assert cfg.dnn_person_class_id == 15
        # YOLOv8 defaults
        assert cfg.yolov8_input_size == 416
        assert cfg.yolov8_confidence_threshold == 0.45
        assert cfg.yolov8_nms_threshold == 0.50
        assert cfg.yolov8_use_onnxruntime is True
        assert cfg.yolov8_use_opencv_dnn is False

    def test_custom_values(self):
        from raspbot_vision.detector_backends import DetectorConfig

        cfg = DetectorConfig(
            backend="opencv_dnn_tf_ssd",
            min_weight=0.60,
            min_area=6000,
            dnn_confidence_threshold=0.70,
        )
        assert cfg.backend == "opencv_dnn_tf_ssd"
        assert cfg.min_weight == 0.60
        assert cfg.min_area == 6000
        assert cfg.dnn_confidence_threshold == 0.70


# ============================================================================
#  _filter_detections
# ============================================================================

class TestFilterDetections:
    @pytest.fixture
    def base_detector(self, default_detector_config):
        """A bare BasePersonDetector just to test _filter_detections."""
        from raspbot_vision.detector_backends import BasePersonDetector

        return BasePersonDetector(default_detector_config)

    def test_filters_low_confidence(self, base_detector, sample_detections):
        filtered = base_detector._filter_detections(sample_detections)

        confidences = [d[4] for d in filtered]
        # min_weight = 0.45; detection with 0.30 should be removed
        assert all(c >= 0.45 for c in confidences)
        # The 0.30 detection had large area but low confidence → removed
        assert len(filtered) < len(sample_detections)

    def test_filters_small_area(self, base_detector, sample_detections):
        filtered = base_detector._filter_detections(sample_detections)

        areas = [d[2] * d[3] for d in filtered]
        # min_area = 4000
        assert all(a >= 4000 for a in areas)

    def test_keeps_valid_detections(self, base_detector, sample_detections):
        filtered = base_detector._filter_detections(sample_detections)

        # The first sample (100×200=20000, 0.95) and fourth (120×180=21600, 0.72) survive
        assert len(filtered) >= 2

    def test_empty_list_returns_empty(self, base_detector):
        assert base_detector._filter_detections([]) == []

    def test_all_filtered_out_returns_empty(self, base_detector):
        detections = [
            (0, 0, 10, 10, 0.30),   # both low confidence AND small area
            (100, 100, 5, 5, 0.50),  # small area
        ]
        assert base_detector._filter_detections(detections) == []

    def test_output_types_are_correct(self, base_detector, sample_detections):
        filtered = base_detector._filter_detections(sample_detections)
        for detection in filtered:
            x, y, w, h, confidence = detection
            assert isinstance(x, int)
            assert isinstance(y, int)
            assert isinstance(w, int)
            assert isinstance(h, int)
            assert isinstance(confidence, float)


# ============================================================================
#  Debug rendering
# ============================================================================

class TestPersonDetectionDebugRendering:
    def test_empty_detections_still_draw_status_banner(self):
        import numpy as np

        from raspbot_vision.person_detect_node import render_person_detection_debug_frame

        frame = np.zeros((240, 320, 3), dtype=np.uint8)
        debug = render_person_detection_debug_frame(frame, [], backend_name="hog")

        assert debug.shape == frame.shape
        assert not np.array_equal(debug, frame)
        assert np.count_nonzero(debug != frame) > 0


class TestHogDetectorFiltering:
    @pytest.mark.skipif(not _HOG_AVAILABLE, reason=_hog_skip_reason)
    def test_hog_filters_low_reliability_boxes(self, default_detector_config):
        import numpy as np

        from raspbot_vision.detector_backends import HogPersonDetector

        default_detector_config.backend = "hog"
        default_detector_config.min_weight = 0.60
        default_detector_config.hog_min_confidence = 0.70
        default_detector_config.hog_min_box_area_ratio = 0.02
        default_detector_config.hog_min_aspect_ratio = 1.30
        detector = HogPersonDetector(default_detector_config)

        class FakeHog:
            def detectMultiScale(self, *args, **kwargs):
                return (
                    np.array([
                        [10, 10, 60, 60],    # too small: area ratio too low
                        [20, 20, 80, 180],   # valid
                        [30, 30, 120, 140],  # squat: aspect ratio too low
                        [40, 40, 90, 200],   # valid
                    ]),
                    np.array([[0.85], [0.78], [0.82], [0.71]]),
                )

        detector.hog = FakeHog()
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        detections = detector.detect(frame)

        assert detections == [(20, 20, 80, 180, 0.78), (40, 40, 90, 200, 0.71)]


# ============================================================================
#  HOG detector initialisation
# ============================================================================

class TestHogDetectorInit:
    @pytest.mark.skipif(not _HOG_AVAILABLE, reason=_hog_skip_reason)
    def test_hog_creates_without_model_files(self, default_detector_config):
        """HOG uses OpenCV's built-in people detector — no external model needed."""
        from raspbot_vision.detector_backends import (
            HogPersonDetector,
            create_person_detector,
        )

        default_detector_config.backend = "hog"
        detector = create_person_detector(default_detector_config)
        assert isinstance(detector, HogPersonDetector)
        assert detector.hog is not None
