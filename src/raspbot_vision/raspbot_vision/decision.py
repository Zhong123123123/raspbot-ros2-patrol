from collections import deque


class DecisionMaker:
    def __init__(self, dead_zone=80, lost_tolerance=3, smooth_window=5):
        self.dead_zone = dead_zone
        self.lost_tolerance = lost_tolerance
        self.offset_history = deque(maxlen=smooth_window)
        self.action_history = deque(maxlen=smooth_window)
        self.lost_count = 0
        self.last_action = 'STOP'

    def decide_raw(self, offset):
        if offset < -self.dead_zone:
            return 'LEFT'
        if offset > self.dead_zone:
            return 'RIGHT'
        return 'FORWARD'

    def decide(self, found, offset):
        if not found or offset is None:
            self.lost_count += 1
            if self.lost_count >= self.lost_tolerance:
                self.last_action = 'STOP'
                return 'STOP'
            return self.last_action
        self.lost_count = 0
        self.offset_history.append(offset)
        smooth_offset = sum(self.offset_history) / len(self.offset_history)
        raw_action = self.decide_raw(smooth_offset)
        self.action_history.append(raw_action)
        action = max(set(self.action_history), key=list(self.action_history).count)
        self.last_action = action
        return action
