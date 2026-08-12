"""Unit tests for patrol_behavior_node.py — P3 multi-round confirmation.

Tests the pure function `evaluate_round_history()` which can run without
ROS2 dependencies.  The function decides whether to confirm a patrol result
based on consecutive entries in the round history deque.
"""


from raspbot_vision.patrol_logic import evaluate_round_history

# Shorthand: patrol_id doesn't affect the decision, so we use None in most tests
_E = ('empty', None)
_O = ('occupied', None)
_U = ('uncertain', None)
# _ prefix because 'E', 'O', 'U' as bare names are too short for ruff


class TestEvaluateRoundHistory:
    """evaluate_round_history(history, confirm_occupied, confirm_empty) → str."""

    # -- Empty / near-empty history ---------------------------------------

    def test_empty_history_returns_none(self):
        assert evaluate_round_history([], 2, 3) == 'none'

    def test_single_occupied_not_enough(self):
        assert evaluate_round_history([_O], 2, 3) == 'none'

    def test_single_empty_not_enough(self):
        assert evaluate_round_history([_E], 2, 3) == 'none'

    # -- Occupied confirmation --------------------------------------------

    def test_two_occupied_meets_threshold(self):
        h = [_O, _O]
        assert evaluate_round_history(h, 2, 3) == 'occupied'

    def test_three_occupied_still_confirms(self):
        h = [_O, _O, _O]
        assert evaluate_round_history(h, 2, 3) == 'occupied'

    def test_occupied_interrupted_resets_count(self):
        h = [_O, _E, _O]  # occupied streak broken by empty
        assert evaluate_round_history(h, 2, 3) == 'none'

    def test_occupied_threshold_1_confirms_immediately(self):
        assert evaluate_round_history([_O], 1, 3) == 'occupied'

    # -- Empty confirmation -----------------------------------------------

    def test_three_empty_meets_threshold(self):
        h = [_E, _E, _E]
        assert evaluate_round_history(h, 2, 3) == 'empty'

    def test_four_empty_still_empty(self):
        h = [_E, _E, _E, _E]
        assert evaluate_round_history(h, 2, 3) == 'empty'

    def test_empty_interrupted_resets_count(self):
        h = [_E, _E, _O, _E]  # empty streak broken
        assert evaluate_round_history(h, 2, 3) == 'none'

    def test_empty_threshold_2_requires_two(self):
        h = [_E]
        assert evaluate_round_history(h, 2, 2) == 'none'
        h2 = [_E, _E]
        assert evaluate_round_history(h2, 2, 2) == 'empty'

    # -- Occupied takes priority over empty --------------------------------

    def test_occupied_wins_both_met(self):
        """If both thresholds are met (last N occupied, earlier M empty),
        occupied wins because it's checked first."""
        h = [_E, _E, _E, _O, _O]
        assert evaluate_round_history(h, 2, 3) == 'occupied'

    # -- Uncertain entries -------------------------------------------------

    def test_uncertain_does_not_contribute(self):
        h = [_U, _U, _U]
        assert evaluate_round_history(h, 2, 3) == 'none'

    def test_uncertain_interrupts_streak(self):
        h = [_O, _O, _U]
        assert evaluate_round_history(h, 2, 3) == 'none'

    def test_uncertain_after_occupied_allows_later_confirm(self):
        h = [_O, _O, _U, _O, _O]
        assert evaluate_round_history(h, 2, 3) == 'occupied'

    # -- Mixed scenarios ---------------------------------------------------

    def test_long_history_mixed(self):
        h = [_E, _E, _E, _E, _O, _O, _O]
        # Last 3 are occupied → confirm occupied
        assert evaluate_round_history(h, 3, 3) == 'occupied'

    def test_long_history_empty_wins_at_end(self):
        h = [_O, _U, _E, _E, _E, _E]
        assert evaluate_round_history(h, 2, 3) == 'empty'

    # -- Edge cases: thresholds match history length exactly ---------------

    def test_exact_threshold_occupied(self):
        h = [_O, _O, _O]
        assert evaluate_round_history(h, 3, 3) == 'occupied'

    def test_exact_threshold_empty(self):
        h = [_E, _E, _E]
        assert evaluate_round_history(h, 3, 3) == 'empty'

    # -- patrol_id ignored (function only looks at decision string) --------

    def test_patrol_id_not_used_in_decision(self):
        h = [('occupied', 'patrol_001'), ('occupied', 'patrol_002')]
        assert evaluate_round_history(h, 2, 3) == 'occupied'

    def test_none_patrol_id_still_works(self):
        h = [('occupied', None), ('occupied', None)]
        assert evaluate_round_history(h, 2, 3) == 'occupied'
