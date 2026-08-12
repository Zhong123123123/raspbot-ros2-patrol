"""ROS-independent patrol decision helpers."""

from __future__ import annotations

from typing import List, Optional, Tuple


RoundEntry = Tuple[str, Optional[str]]


def evaluate_round_history(
    history: List[RoundEntry],
    confirm_occupied_rounds: int,
    confirm_empty_rounds: int,
) -> str:
    """Determine the confirmed decision from trailing patrol rounds."""
    if not history:
        return 'none'

    occupied_count = 0
    for decision, _ in reversed(history):
        if decision != 'occupied':
            break
        occupied_count += 1
    if occupied_count >= confirm_occupied_rounds:
        return 'occupied'

    empty_count = 0
    for decision, _ in reversed(history):
        if decision != 'empty':
            break
        empty_count += 1
    if empty_count >= confirm_empty_rounds:
        return 'empty'
    return 'none'
