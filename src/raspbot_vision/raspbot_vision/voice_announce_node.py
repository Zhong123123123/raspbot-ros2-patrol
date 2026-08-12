#!/usr/bin/env python3
"""Voice announce node — TTS alerts on patrol status changes.

Subscribes to ``/patrol/alert`` and ``/patrol/confirmed_status``,
calling ``espeak-ng`` (or ``espeak``) when a person is confirmed
or the alert clears.

Rate-limited: at most one announcement per cooldown interval.
"""

import json
import subprocess
import threading
import time

import rclpy
from rclpy.node import Node
from std_msgs.msg import Bool, String


class VoiceAnnounceNode(Node):
    def __init__(self):
        super().__init__('raspbot_voice_announce')

        self.declare_parameter('alert_topic', 'patrol/alert')
        self.declare_parameter('confirmed_topic', 'patrol/confirmed_status')
        self.declare_parameter('cooldown_sec', 30.0)
        self.declare_parameter('speed', 150)  # words per minute
        self.declare_parameter('volume', 100)  # 0-200
        self.declare_parameter('voice', 'en')  # espeak voice
        self.declare_parameter('enabled', True)

        self._load_params()

        self._last_speak = 0.0
        self._lock = threading.Lock()
        self._last_alert = False

        self.alert_sub = self.create_subscription(
            Bool, self.alert_topic, self._on_alert, 10,
        )
        self.confirmed_sub = self.create_subscription(
            String, self.confirmed_topic, self._on_confirmed, 10,
        )

        self.get_logger().info(
            f'voice announce node started (cooldown={self.cooldown_sec}s, '
            f'enabled={self.enabled})'
        )

    def _load_params(self):
        self.alert_topic = str(self.get_parameter('alert_topic').value)
        self.confirmed_topic = str(self.get_parameter('confirmed_topic').value)
        self.cooldown_sec = max(1.0, float(self.get_parameter('cooldown_sec').value))
        self.speed = max(80, min(450, int(self.get_parameter('speed').value)))
        self.volume = max(0, min(200, int(self.get_parameter('volume').value)))
        self.voice = str(self.get_parameter('voice').value)
        self.enabled = bool(self.get_parameter('enabled').value)

    def _on_alert(self, msg: Bool):
        if not self.enabled:
            return
        if msg.data and not self._last_alert:
            self._speak('Warning: person detected in patrol area.')
        elif not msg.data and self._last_alert:
            self._speak('Alert cleared. Area secure.')
        self._last_alert = msg.data

    def _on_confirmed(self, msg: String):
        if not self.enabled:
            return
        try:
            data = json.loads(msg.data)
        except json.JSONDecodeError:
            return
        decision = data.get('confirmed_decision', data.get('decision', ''))
        if decision == 'occupied':
            count = data.get('occupied_consecutive_rounds', data.get('occupied_rounds', '?'))
            self._speak(f'Person confirmed after {count} rounds.')
        elif decision == 'empty':
            self._speak('Area confirmed clear.')

    def _speak(self, text: str):
        now = time.monotonic()
        with self._lock:
            if now - self._last_speak < self.cooldown_sec:
                return
            self._last_speak = now

        self.get_logger().info(f'TTS: "{text}"')

        # Try espeak-ng first, fall back to espeak
        for binary in ('espeak-ng', 'espeak'):
            try:
                subprocess.run(
                    [binary, '-s', str(self.speed),
                     '-a', str(self.volume),
                     '-v', self.voice,
                     text],
                    capture_output=True, timeout=5.0,
                )
                return
            except FileNotFoundError:
                continue
            except Exception as exc:
                self.get_logger().error(f'TTS error ({binary}): {exc}')
                return

        self.get_logger().error('No TTS engine found (espeak-ng or espeak)')


def main(args=None):
    rclpy.init(args=args)
    node = VoiceAnnounceNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
