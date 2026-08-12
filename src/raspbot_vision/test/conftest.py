"""Shared test fixtures for raspbot_vision tests.

Fixtures that need opencv/numpy are imported lazily by individual test
files so pytest collection still works even when optional deps are absent.
"""

import sys
from pathlib import Path

import pytest

# Ensure the source package is importable during development (before colcon build).
_src = Path(__file__).resolve().parents[1]
if str(_src) not in sys.path:
    sys.path.insert(0, str(_src))


# ---------------------------------------------------------------------------
#  decision.py  fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def default_decision_maker():
    """DecisionMaker with project-default parameters."""
    from raspbot_vision.decision import DecisionMaker

    return DecisionMaker(dead_zone=100, lost_tolerance=3, smooth_window=5)


@pytest.fixture
def strict_decision_maker():
    """DecisionMaker with zero tolerance — every lost frame = STOP."""
    from raspbot_vision.decision import DecisionMaker

    return DecisionMaker(dead_zone=50, lost_tolerance=1, smooth_window=3)


# ---------------------------------------------------------------------------
#  line_detector.py  fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def blank_bgr_frame():
    """640x480 mid-grey frame (no black line — should NOT trigger detection)."""
    import numpy as np

    return np.full((480, 640, 3), 128, dtype=np.uint8)


@pytest.fixture
def centered_black_line_frame():
    """640x480 frame with a vertical black stripe at the image centre."""
    import numpy as np

    frame = np.full((480, 640, 3), 200, dtype=np.uint8)  # light-grey background
    frame[264:480, 300:340, :] = 0  # black stripe in ROI (y > 0.55×480≈264)
    return frame


@pytest.fixture
def left_black_line_frame():
    """640x480 frame with a vertical black stripe left of centre."""
    import numpy as np

    frame = np.full((480, 640, 3), 200, dtype=np.uint8)
    frame[264:480, 100:140, :] = 0
    return frame


@pytest.fixture
def right_black_line_frame():
    """640x480 frame with a vertical black stripe right of centre."""
    import numpy as np

    frame = np.full((480, 640, 3), 200, dtype=np.uint8)
    frame[264:480, 500:540, :] = 0
    return frame


@pytest.fixture
def tiny_noise_frame():
    """Frame with only a few black pixels — area < default min_area."""
    import numpy as np

    frame = np.full((480, 640, 3), 200, dtype=np.uint8)
    frame[400:405, 300:305, :] = 0  # just 25 px², far below 500
    return frame


# ---------------------------------------------------------------------------
#  detector_backends.py  fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def default_detector_config():
    from raspbot_vision.detector_backends import DetectorConfig

    return DetectorConfig()


@pytest.fixture
def sample_detections():
    """A mix of good / low-confidence / small-area detections."""
    return [
        (10, 20, 100, 200, 0.95),   # good: high confidence, large area
        (50, 60, 80, 150, 0.30),    # filtered by min_weight (< 0.45)
        (200, 300, 10, 10, 0.90),   # filtered by min_area (< 4000)
        (400, 100, 120, 180, 0.72),  # good
        (0, 0, 50, 60, 0.55),       # filtered by min_area (3000 < 4000)
    ]
