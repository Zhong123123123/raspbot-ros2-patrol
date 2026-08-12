"""Unit tests for raspbot_vision.line_detector.LineDetector.

Uses synthetic frames (numpy arrays) — no camera needed.

Covers:
  - Blank frame (no line)
  - Centered / left / right black lines
  - Tiny noise below min_area
  - Various thresholds
  - Return dict structure
"""

import pytest

pytest.importorskip("cv2", reason="OpenCV runtime dependency is not installed")


# ============================================================================
#  Return dict contract
# ============================================================================

class TestReturnDict:
    def test_keys_present_when_no_line(self, blank_bgr_frame):
        from raspbot_vision.line_detector import LineDetector

        ld = LineDetector()
        result = ld.detect(blank_bgr_frame)

        assert set(result.keys()) == {"found", "cx", "offset", "debug"}
        assert result["found"] is False
        assert result["cx"] is None
        assert result["offset"] is None

    def test_keys_present_when_line_found(self, centered_black_line_frame):
        from raspbot_vision.line_detector import LineDetector

        ld = LineDetector()
        result = ld.detect(centered_black_line_frame)

        assert set(result.keys()) == {"found", "cx", "offset", "debug"}
        assert result["found"] is True
        assert isinstance(result["cx"], int)
        assert isinstance(result["offset"], int)


# ============================================================================
#  Detection correctness
# ============================================================================

class TestDetection:
    def test_blank_frame_no_detection(self, blank_bgr_frame):
        from raspbot_vision.line_detector import LineDetector

        ld = LineDetector()
        result = ld.detect(blank_bgr_frame)
        assert result["found"] is False

    def test_centered_line_near_zero_offset(self, centered_black_line_frame):
        from raspbot_vision.line_detector import LineDetector

        ld = LineDetector()
        result = ld.detect(centered_black_line_frame)

        assert result["found"] is True
        # Black stripe at x=[300,340], centre=320; image_centre=320 → offset ≈ 0
        assert abs(result["offset"]) < 30

    def test_left_line_negative_offset(self, left_black_line_frame):
        from raspbot_vision.line_detector import LineDetector

        ld = LineDetector()
        result = ld.detect(left_black_line_frame)

        assert result["found"] is True
        # Black stripe near x=120; centre=320 → offset should be negative
        assert result["offset"] < -50

    def test_right_line_positive_offset(self, right_black_line_frame):
        from raspbot_vision.line_detector import LineDetector

        ld = LineDetector()
        result = ld.detect(right_black_line_frame)

        assert result["found"] is True
        # Black stripe near x=520; centre=320 → offset should be positive
        assert result["offset"] > 50


# ============================================================================
#  Noise rejection
# ============================================================================

class TestNoiseRejection:
    def test_tiny_area_filtered_out(self, tiny_noise_frame):
        from raspbot_vision.line_detector import LineDetector

        ld = LineDetector()
        result = ld.detect(tiny_noise_frame)
        # ~25 px² < 500 min_area → should NOT be detected
        assert result["found"] is False

    def test_large_min_area_rejects_valid_line(self, centered_black_line_frame):
        from raspbot_vision.line_detector import LineDetector

        ld = LineDetector()
        # The black stripe is 40×216 = 8640 px² — set min_area above that
        result = ld.detect(centered_black_line_frame, min_area=20000)
        assert result["found"] is False


# ============================================================================
#  Parameter sensitivity
# ============================================================================

class TestParameters:
    def test_different_resolution_handled(self):
        """Detector should handle non-default resolutions correctly."""
        from raspbot_vision.line_detector import LineDetector
        import numpy as np

        ld = LineDetector()
        # 320×240 frame with a centered black line
        frame = np.full((240, 320, 3), 200, dtype=np.uint8)
        frame[132:240, 150:170, :] = 0
        result = ld.detect(frame, threshold=80, min_area=300)
        assert result["found"] is True
        # Centre of 320-wide image is 160; stripe at 150-170 → cx around 160
        assert abs(result["offset"]) < 30

    def test_high_threshold_brightens_detection(self, centered_black_line_frame):
        """Threshold=200 → everything darker than 200 is 'black' → should still find line."""
        from raspbot_vision.line_detector import LineDetector

        ld = LineDetector()
        result = ld.detect(centered_black_line_frame, threshold=200)
        assert result["found"] is True

    def test_roi_ratio_changes_search_window(self, centered_black_line_frame):
        """roi_ratio=0.1 takes almost the whole frame → line is still found."""
        from raspbot_vision.line_detector import LineDetector

        ld = LineDetector()
        result = ld.detect(centered_black_line_frame, roi_ratio=0.1)
        assert result["found"] is True

    def test_roi_ratio_excludes_line(self, centered_black_line_frame):
        """roi_ratio=0.99 only looks at bottom 1% → line barely visible, area < min_area."""
        from raspbot_vision.line_detector import LineDetector

        ld = LineDetector()
        # Black stripe starts at y=264 and extends to 480.
        # ROI at 0.99 starts at y=475: only 5 px of the 40-px-wide stripe is visible
        # → 40×5 = 200 px² < 500 min_area → not found
        result = ld.detect(centered_black_line_frame, roi_ratio=0.99)
        assert result["found"] is False


# ============================================================================
#  Debug image
# ============================================================================

class TestDebugImage:
    def test_debug_frame_same_size_as_input(self, centered_black_line_frame):
        from raspbot_vision.line_detector import LineDetector

        ld = LineDetector()
        result = ld.detect(centered_black_line_frame)
        assert result["debug"].shape == centered_black_line_frame.shape
        assert result["debug"].dtype == centered_black_line_frame.dtype
