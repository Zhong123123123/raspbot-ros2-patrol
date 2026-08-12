#!/usr/bin/env python3
"""Remote notification node — webhook alerts on patrol events.

Subscribes to ``/patrol/alert`` and ``/patrol/confirmed_status``,
sending HTTP webhook notifications when important patrol events occur.

Supported platforms:
  - dingtalk:  DingTalk group bot (signing optional)
  - wechat:    WeChat Work (企业微信) group bot
  - generic:   Any server that accepts JSON POST

Rate-limited to avoid spamming on repeated triggers.
"""

import base64
import hashlib
import hmac
import json
import threading
import time
import urllib.request as ureq
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import rclpy
from rclpy.node import Node
from std_msgs.msg import Bool, String


class RemoteNotifyNode(Node):
    def __init__(self):
        super().__init__('raspbot_remote_notify')

        self.declare_parameter('alert_topic', 'patrol/alert')
        self.declare_parameter('confirmed_topic', 'patrol/confirmed_status')
        self.declare_parameter('webhook_url', '')
        self.declare_parameter('platform', 'generic')  # generic / dingtalk / wechat
        self.declare_parameter('secret', '')           # for dingtalk signing
        self.declare_parameter('cooldown_sec', 120.0)  # min interval between notifications
        self.declare_parameter('retry_count', 2)
        self.declare_parameter('retry_delay_sec', 5.0)
        self.declare_parameter('enabled', True)
        self.declare_parameter('notify_on_empty', False)  # notify when area clear too?

        self._load_params()

        self._last_notify = 0.0
        self._lock = threading.Lock()
        self._sender = ThreadPoolExecutor(max_workers=1, thread_name_prefix='raspbot-notify')
        self._last_state = {'alert': False, 'decision': 'none'}

        self.alert_sub = self.create_subscription(
            Bool, self.alert_topic, self._on_alert, 10,
        )
        self.confirmed_sub = self.create_subscription(
            String, self.confirmed_topic, self._on_confirmed, 10,
        )

        status = 'enabled' if self.enabled else 'disabled'
        self.get_logger().info(
            f'remote notify node started ({status}, platform={self.platform}, '
            f'cooldown={self.cooldown_sec}s)'
        )

    def _load_params(self):
        self.alert_topic = str(self.get_parameter('alert_topic').value)
        self.confirmed_topic = str(self.get_parameter('confirmed_topic').value)
        self.webhook_url = str(self.get_parameter('webhook_url').value).strip()
        self.platform = str(self.get_parameter('platform').value).strip().lower()
        self.secret = str(self.get_parameter('secret').value)
        self.cooldown_sec = max(10.0, float(self.get_parameter('cooldown_sec').value))
        self.retry_count = max(0, int(self.get_parameter('retry_count').value))
        self.retry_delay_sec = max(1.0, float(self.get_parameter('retry_delay_sec').value))
        self.enabled = bool(self.get_parameter('enabled').value)
        self.notify_on_empty = bool(self.get_parameter('notify_on_empty').value)

    # ------------------------------------------------------------------
    #  Callbacks
    # ------------------------------------------------------------------

    def _on_alert(self, msg: Bool):
        self._last_state['alert'] = msg.data

    def _on_confirmed(self, msg: String):
        try:
            data = json.loads(msg.data)
        except json.JSONDecodeError:
            return

        decision = data.get('confirmed_decision', data.get('decision', ''))
        prev = self._last_state.get('decision', '')
        self._last_state['decision'] = decision

        if decision == 'occupied' and prev != 'occupied':
            self._send_async(
                title='🚨 巡检告警：检测到人员',
                body=self._format_occupied_body(data),
            )
        elif decision == 'empty' and prev not in ('none', 'empty'):
            if self.notify_on_empty:
                self._send_async(
                    title='✅ 巡检恢复：区域安全',
                    body='巡逻区域已确认无人。',
                )

    # ------------------------------------------------------------------
    #  Message formatting
    # ------------------------------------------------------------------

    def _format_occupied_body(self, data: dict) -> str:
        confirmed_rounds = data.get('occupied_consecutive_rounds', data.get('occupied_rounds', '?'))
        required_rounds = data.get('occupied_rounds_required', '?')
        latest_round = data.get('latest_round_decision', data.get('decision', '?'))
        lines = [
            f"时间：{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}",
            f"确认轮次：{confirmed_rounds} / {required_rounds} 轮",
            f"最近轮次：{latest_round}",
        ]
        return '\n'.join(lines)

    def _build_payload(self, title: str, body: str) -> dict:
        if self.platform == 'dingtalk':
            return {
                'msgtype': 'markdown',
                'markdown': {
                    'title': title,
                    'text': f'## {title}\n\n{body}\n\n> 来自 Raspbot 巡检机器人',
                },
            }
        elif self.platform == 'wechat':
            return {
                'msgtype': 'markdown',
                'markdown': {
                    'content': f'## {title}\n{body}\n<font color="comment">Raspbot 巡检</font>',
                },
            }
        else:  # generic
            return {
                'event': 'patrol_alert',
                'title': title,
                'body': body,
                'timestamp': datetime.now(timezone.utc).isoformat(),
            }

    # ------------------------------------------------------------------
    #  HTTP sender
    # ------------------------------------------------------------------

    def _signed_webhook_url(self) -> str:
        """Add DingTalk's timestamp/sign query parameters when a secret is set."""
        if self.platform != 'dingtalk' or not self.secret:
            return self.webhook_url
        timestamp = str(int(time.time() * 1000))
        to_sign = f'{timestamp}\n{self.secret}'.encode('utf-8')
        signature = base64.b64encode(
            hmac.new(self.secret.encode('utf-8'), to_sign, hashlib.sha256).digest()
        ).decode('utf-8')
        parsed = urlsplit(self.webhook_url)
        query = dict(parse_qsl(parsed.query, keep_blank_values=True))
        query.update({'timestamp': timestamp, 'sign': signature})
        return urlunsplit((parsed.scheme, parsed.netloc, parsed.path,
                           urlencode(query), parsed.fragment))

    def _send_async(self, title: str, body: str):
        if not self.enabled or not self.webhook_url:
            return

        now = time.monotonic()
        with self._lock:
            if now - self._last_notify < self.cooldown_sec:
                return
            self._last_notify = now

        self._sender.submit(self._send_blocking, title, body)

    def _send_blocking(self, title: str, body: str):
        """Send outside the ROS callback thread so a slow webhook cannot block it."""

        payload = self._build_payload(title, body)
        data = json.dumps(payload, ensure_ascii=False).encode('utf-8')

        for attempt in range(1 + self.retry_count):
            try:
                req = ureq.Request(
                    self._signed_webhook_url(), data=data,
                    headers={'Content-Type': 'application/json; charset=utf-8'},
                )
                resp = ureq.urlopen(req, timeout=10)
                self.get_logger().info(
                    f'notification sent ({resp.status}): {title}'
                )
                return
            except Exception as exc:
                if attempt < self.retry_count:
                    self.get_logger().warning(
                        f'notification retry {attempt + 1}/{self.retry_count}: {exc}'
                    )
                    time.sleep(self.retry_delay_sec)
                else:
                    self.get_logger().error(f'notification failed: {exc}')

    def destroy_node(self):
        self._sender.shutdown(wait=False, cancel_futures=True)
        return super().destroy_node()


def main(args=None):
    rclpy.init(args=args)
    node = RemoteNotifyNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
