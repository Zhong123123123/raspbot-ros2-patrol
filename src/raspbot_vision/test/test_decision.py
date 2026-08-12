"""Unit tests for raspbot_vision.decision.DecisionMaker.

Covers:
  - decide_raw:  decision from a single offset value
  - decide:      full pipeline (found/not-found, smoothing, voting, lost tolerance)
  - statefulness: lost counter, offset/action histories, last_action memory
  - edge cases:  zero offset, exact dead-zone boundary, rapid flips
"""

import pytest


# ============================================================================
#  decide_raw
# ============================================================================

class TestDecideRaw:
    """Pure function: offset → FORWARD / LEFT / RIGHT."""

    def test_negative_offset_returns_left(self, default_decision_maker):
        dm = default_decision_maker
        # default dead_zone = 100
        assert dm.decide_raw(-150) == "LEFT"
        assert dm.decide_raw(-101) == "LEFT"

    def test_positive_offset_returns_right(self, default_decision_maker):
        dm = default_decision_maker
        assert dm.decide_raw(150) == "RIGHT"
        assert dm.decide_raw(101) == "RIGHT"

    def test_within_dead_zone_returns_forward(self, default_decision_maker):
        dm = default_decision_maker
        assert dm.decide_raw(0) == "FORWARD"
        assert dm.decide_raw(-50) == "FORWARD"
        assert dm.decide_raw(50) == "FORWARD"

    def test_exact_boundary_returns_forward(self, default_decision_maker):
        """offset == dead_zone or offset == -dead_zone → FORWARD (not >=, not <=)."""
        dm = default_decision_maker
        assert dm.decide_raw(-100) == "FORWARD"
        assert dm.decide_raw(100) == "FORWARD"


# ============================================================================
#  decide — line found (normal tracking)
# ============================================================================

class TestDecideLineFound:
    """When found=True and offset is valid."""

    def test_single_frame_no_history(self, default_decision_maker):
        dm = default_decision_maker
        # First call has no history in the deque — runs on single value
        action = dm.decide(True, 200)
        assert action == "RIGHT"

    def test_consistent_offset_produces_stable_output(self, default_decision_maker):
        dm = default_decision_maker
        # Feed 10 identical offsets; voting should stabilise after smooth_window fills
        actions = [dm.decide(True, 200) for _ in range(10)]
        # After warm-up the vote should lock on RIGHT
        assert all(a == "RIGHT" for a in actions[-5:])

    def test_consistent_forward(self, default_decision_maker):
        dm = default_decision_maker
        actions = [dm.decide(True, 0) for _ in range(10)]
        assert all(a == "FORWARD" for a in actions[-5:])

    def test_smooth_window_damps_single_outlier(self, default_decision_maker):
        """A single large offset among many small ones should be smoothed away."""
        dm = default_decision_maker  # dead_zone=100, smooth_window=5
        # 4 frames near centre → FORWARD
        for _ in range(4):
            dm.decide(True, 10)
        # 1 large outlier: smooth_offset = (10+10+10+10+200)/5 = 48  still < 100
        action = dm.decide(True, 200)
        assert action == "FORWARD"

    def test_smooth_window_eventually_adapts(self, default_decision_maker):
        """After enough consistent frames the output adapts to new offset."""
        dm = default_decision_maker
        # Fill with FORWARD
        for _ in range(5):
            dm.decide(True, 0)
        # Then consistently feed LEFT — after voting fills, it should switch
        for _ in range(5):
            dm.decide(True, -200)
        action = dm.decide(True, -200)
        assert action == "LEFT"


# ============================================================================
#  decide — line lost
# ============================================================================

class TestDecideLineLost:
    """When found=False or offset is None."""

    def test_first_lost_frame_returns_last_action(self, default_decision_maker):
        dm = default_decision_maker
        # Prime with a found frame
        dm.decide(True, 0)  # last_action = FORWARD
        # One lost frame → still returns FORWARD (lost_tolerance=3)
        action = dm.decide(False, None)
        assert action == "FORWARD"

    def test_lost_exceeds_tolerance_returns_stop(self, default_decision_maker):
        dm = default_decision_maker  # lost_tolerance=3
        dm.decide(True, 0)  # prime
        for _ in range(2):
            action = dm.decide(False, None)
            assert action != "STOP", "should still tolerate"
        # 3rd lost frame → STOP
        action = dm.decide(False, None)
        assert action == "STOP"

    def test_lost_counter_resets_on_found(self, default_decision_maker):
        dm = default_decision_maker  # lost_tolerance=3
        dm.decide(True, 0)  # prime
        dm.decide(False, None)  # lost_count=1
        dm.decide(False, None)  # lost_count=2
        dm.decide(True, 0)      # found → lost_count=0
        dm.decide(False, None)  # lost_count=1 (reset, NOT 3 → STOP)

        # Two more lost should still be tolerated
        action = dm.decide(False, None)  # lost_count=2
        assert action != "STOP"

    def test_none_offset_handled_like_not_found(self, default_decision_maker):
        dm = default_decision_maker
        dm.decide(True, 0)
        action = dm.decide(True, None)
        # offset=None treated as lost
        assert action == "FORWARD"  # still within tolerance

    def test_zero_tolerance_stops_immediately(self, strict_decision_maker):
        dm = strict_decision_maker  # lost_tolerance=1
        dm.decide(True, 0)  # prime
        action = dm.decide(False, None)
        assert action == "STOP"


# ============================================================================
#  Voting behaviour
# ============================================================================

class TestVoting:
    """Majority voting across the action_history deque."""

    def test_majority_wins_over_noise(self):
        """Single-frame noise (e.g. LEFT) should not flip a FORWARD consensus."""
        from raspbot_vision.decision import DecisionMaker

        dm = DecisionMaker(dead_zone=80, lost_tolerance=3, smooth_window=5)
        # Fill history with FORWARD
        for _ in range(5):
            dm.decide(True, 0)  # always FORWARD
        # Inject one LEFT — it won't win the vote
        dm.decide(True, -200)  # one LEFT frame
        # The next call should still vote FORWARD (4 FORWARD vs 1 LEFT)
        action = dm.decide(True, 0)
        assert action == "FORWARD"


# ============================================================================
#  State isolation
# ============================================================================

class TestStateIsolation:
    """Each DecisionMaker carries its own history."""

    def test_two_instances_are_independent(self):
        from raspbot_vision.decision import DecisionMaker

        a = DecisionMaker()
        b = DecisionMaker()

        a.decide(True, 300)  # RIGHT
        b.decide(True, -300)  # LEFT

        assert a.last_action == "RIGHT"
        assert b.last_action == "LEFT"
