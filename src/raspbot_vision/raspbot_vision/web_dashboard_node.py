"""Web dashboard node — serves a browser-based monitoring & control panel.

Provides three services on a single HTTP port (default 8080):
  /            — dashboard HTML page
  /ws          — WebSocket for real-time telemetry + control commands
  /camera      — MJPEG stream from the robot's camera

Architecture:
  aiohttp web server runs in the main thread.
  ROS2 spinning runs in a background thread.
  Shared state is protected by asyncio locks where needed.

Usage:
  ros2 run raspbot_vision web_dashboard_node
  # then open http://<raspberry-pi-ip>:8080 in a browser
"""

from __future__ import annotations

import asyncio
import hmac
import json
import os
import threading
import time
from pathlib import Path
from typing import Optional

import rclpy
from aiohttp import web
from ament_index_python.packages import get_package_share_directory
from geometry_msgs.msg import Twist
from rclpy.node import Node
from sensor_msgs.msg import CompressedImage, Range
from std_msgs.msg import Bool, String

# ---------------------------------------------------------------------------
#  Shared telemetry state  (written by ROS2 callbacks, read by aiohttp)
# ---------------------------------------------------------------------------

class TelemetryState:
    __slots__ = (
        "linear_x", "angular_z",
        "ultrasonic_range", "ultrasonic_min", "ultrasonic_max",
        "person_detected", "patrol_active", "safety_override_active",
        "person_backend_requested", "person_backend_active", "person_backend_is_fallback",
        "person_backend_fallback_reason", "person_decision_reason", "person_frame_rotate_deg",
        "patrol_confirmed_decision", "patrol_alert",
        "latest_jpeg", "latest_jpeg_stamp",
        "camera_topic_active",
    )

    def __init__(self):
        self.linear_x: float = 0.0
        self.angular_z: float = 0.0
        self.ultrasonic_range: float = float("inf")
        self.ultrasonic_min: float = 0.02
        self.ultrasonic_max: float = 2.50
        self.person_detected: bool = False
        self.patrol_active: bool = False
        self.safety_override_active: bool = False
        self.person_backend_requested: str = ""
        self.person_backend_active: str = ""
        self.person_backend_is_fallback: bool = False
        self.person_backend_fallback_reason: str = ""
        self.person_decision_reason: str = ""
        self.person_frame_rotate_deg: int = 0
        self.patrol_confirmed_decision: str = "none"
        self.patrol_alert: bool = False
        self.latest_jpeg: Optional[bytes] = None
        self.latest_jpeg_stamp: float = 0.0
        self.camera_topic_active: str = ""


# ---------------------------------------------------------------------------
#  ROS2 node (runs in background thread)
# ---------------------------------------------------------------------------

class DashboardRosNode(Node):
    def __init__(self, state: TelemetryState):
        super().__init__("raspbot_web_dashboard")
        self._state = state

        # Subscriptions
        self.create_subscription(Twist, "cmd_vel", self._on_cmd_vel, 10)
        self.create_subscription(Range, "ultrasonic/front", self._on_ultrasonic, 10)
        self.create_subscription(Bool, "person_detected", self._on_person, 10)
        self.create_subscription(String, "person_detection/status", self._on_detection_status, 10)
        self.create_subscription(Bool, "patrol/active", self._on_patrol, 10)
        self.create_subscription(Bool, "safety_override_active", self._on_safety, 10)
        self.create_subscription(String, "patrol/confirmed_status", self._on_confirmed_status, 10)
        self.create_subscription(Bool, "patrol/alert", self._on_alert, 10)

        # Camera — subscribe to BOTH possible debug topics
        self.create_subscription(CompressedImage, "person_detection/debug/compressed", self._on_camera("person_detection"), 10)
        self.create_subscription(CompressedImage, "line_follow/debug/compressed", self._on_camera("line_follow"), 10)

        # Publisher for teleop commands from the browser
        self.cmd_pub = self.create_publisher(Twist, "cmd_vel", 10)

        self.get_logger().info("Web dashboard ROS2 node started")

    # -- subscribers --------------------------------------------------------

    def _on_cmd_vel(self, msg: Twist):
        self._state.linear_x = float(msg.linear.x)
        self._state.angular_z = float(msg.angular.z)

    def _on_ultrasonic(self, msg: Range):
        self._state.ultrasonic_range = float(msg.range)
        self._state.ultrasonic_min = float(msg.min_range)
        self._state.ultrasonic_max = float(msg.max_range)

    def _on_person(self, msg: Bool):
        self._state.person_detected = bool(msg.data)

    def _on_detection_status(self, msg: String):
        try:
            payload = json.loads(msg.data)
        except (json.JSONDecodeError, AttributeError):
            return
        self._state.person_detected = bool(payload.get("detected", False))
        self._state.person_backend_requested = str(payload.get("backend_requested", ""))
        self._state.person_backend_active = str(payload.get("backend_active", payload.get("detector_backend", "")))
        self._state.person_backend_is_fallback = bool(payload.get("backend_is_fallback", False))
        self._state.person_backend_fallback_reason = str(payload.get("backend_fallback_reason", ""))
        self._state.person_decision_reason = str(payload.get("decision_reason", ""))
        self._state.person_frame_rotate_deg = int(payload.get("frame_rotate_deg", 0))

    def _on_patrol(self, msg: Bool):
        self._state.patrol_active = bool(msg.data)

    def _on_safety(self, msg: Bool):
        self._state.safety_override_active = bool(msg.data)

    def _on_confirmed_status(self, msg: String):
        try:
            payload = json.loads(msg.data)
            self._state.patrol_confirmed_decision = str(payload.get("confirmed_decision", "none"))
        except (json.JSONDecodeError, AttributeError):
            pass

    def _on_alert(self, msg: Bool):
        self._state.patrol_alert = bool(msg.data)

    def _on_camera(self, source: str):
        def callback(msg: CompressedImage):
            if msg.format.lower() not in ("jpeg", "jpg"):
                return
            self._state.latest_jpeg = bytes(msg.data)
            self._state.latest_jpeg_stamp = time.monotonic()
            self._state.camera_topic_active = source
        return callback

    # -- teleop -------------------------------------------------------------

    def publish_teleop(self, linear_x: float, angular_z: float):
        msg = Twist()
        msg.linear.x = float(linear_x)
        msg.angular.z = float(angular_z)
        self.cmd_pub.publish(msg)


# ===========================================================================
#  aiohttp web application
# ===========================================================================

STATIC_DIR = Path(get_package_share_directory("raspbot_vision")) / "web_dashboard"
INDEX_HTML = (STATIC_DIR / "index.html").read_text()


async def handle_index(_request: web.Request) -> web.Response:
    return web.Response(text=INDEX_HTML, content_type="text/html")


async def handle_camera(request: web.Request) -> web.StreamResponse:
    """MJPEG stream — browser-friendly, works with <img src='/camera'>."""
    state: TelemetryState = request.app["telemetry"]

    response = web.StreamResponse(
        status=200,
        reason="OK",
        headers={
            "Content-Type": "multipart/x-mixed-replace; boundary=--raspbot",
            "Cache-Control": "no-cache",
            "Connection": "close",
        },
    )
    await response.prepare(request)

    boundary = b"--raspbot\r\n"
    no_signal_jpeg: Optional[bytes] = None

    # Build a "no signal" placeholder once
    try:
        import cv2
        import numpy as np
        placeholder = np.full((360, 640, 3), 40, dtype=np.uint8)
        cv2.putText(placeholder, "WAITING FOR CAMERA...", (80, 190),
                    cv2.FONT_HERSHEY_SIMPLEX, 1.0, (180, 180, 180), 2)
        _, no_signal_jpeg = cv2.imencode(".jpg", placeholder)
        no_signal_jpeg = no_signal_jpeg.tobytes()  # imencode returns ndarray
    except Exception:
        pass

    try:
        while True:
            jpeg = state.latest_jpeg
            if jpeg is None:
                jpeg = no_signal_jpeg
                if jpeg is None:
                    await asyncio.sleep(0.5)
                    continue

            await response.write(boundary)
            await response.write(b"Content-Type: image/jpeg\r\n")
            await response.write(f"Content-Length: {len(jpeg)}\r\n\r\n".encode())
            await response.write(jpeg)
            await response.write(b"\r\n")

            # Check if client disconnected
            if await request.content.readany():
                break

            await asyncio.sleep(0.1)  # ~10 fps
    except (ConnectionResetError, ConnectionAbortedError):
        pass

    return response


async def handle_websocket(request: web.Request) -> web.WebSocketResponse:
    """Bidirectional WebSocket: telemetry out, control commands in."""
    state: TelemetryState = request.app["telemetry"]
    ros_node: DashboardRosNode = request.app["ros_node"]
    control_enabled: bool = request.app["control_enabled"]
    control_token: str = request.app["control_token"]

    ws = web.WebSocketResponse()
    await ws.prepare(request)

    # Control mapping: client sends {"action": "forward"} etc.
    teleop_map = {
        "forward":  (0.20, 0.0),
        "back":     (-0.12, 0.0),
        "left":     (0.0, 0.80),
        "right":    (0.0, -0.80),
        "stop":     (0.0, 0.0),
    }

    # Start telemetry broadcast task
    async def telemetry_loop():
        while not ws.closed:
            payload = {
                "type": "telemetry",
                "ts": time.monotonic(),
                "linear_x": round(state.linear_x, 3),
                "angular_z": round(state.angular_z, 3),
                "ultrasonic_range": round(state.ultrasonic_range, 3),
                "ultrasonic_min": state.ultrasonic_min,
                "ultrasonic_max": state.ultrasonic_max,
                "person_detected": state.person_detected,
                "patrol_active": state.patrol_active,
                "safety_override_active": state.safety_override_active,
                "person_backend_requested": state.person_backend_requested,
                "person_backend_active": state.person_backend_active,
                "person_backend_is_fallback": state.person_backend_is_fallback,
                "person_backend_fallback_reason": state.person_backend_fallback_reason,
                "person_decision_reason": state.person_decision_reason,
                "frame_rotate_deg": state.person_frame_rotate_deg,
                "patrol_confirmed_decision": state.patrol_confirmed_decision,
                "patrol_alert": state.patrol_alert,
                "control_enabled": control_enabled,
                "camera_topic": state.camera_topic_active,
                "camera_age_ms": round(
                    (time.monotonic() - state.latest_jpeg_stamp) * 1000, 0
                ) if state.latest_jpeg_stamp > 0 else None,
            }
            try:
                await ws.send_json(payload)
            except ConnectionResetError:
                break
            await asyncio.sleep(0.1)  # 10 Hz

    telemetry_task = asyncio.ensure_future(telemetry_loop())

    try:
        async for msg in ws:
            if msg.type == web.WSMsgType.TEXT:
                try:
                    data = json.loads(msg.data)
                except json.JSONDecodeError:
                    continue

                if data.get("type") == "control":
                    if not control_enabled:
                        await ws.send_json({"type": "error", "reason": "control_disabled"})
                        continue
                    if control_token and not hmac.compare_digest(
                        str(data.get("token", "")), control_token
                    ):
                        await ws.send_json({"type": "error", "reason": "invalid_control_token"})
                        continue
                    action = data.get("action", "stop")
                    lin, ang = teleop_map.get(action, (0.0, 0.0))
                    ros_node.publish_teleop(lin, ang)

            elif msg.type == web.WSMsgType.ERROR:
                break
    finally:
        telemetry_task.cancel()
        # Auto-stop when browser disconnects
        ros_node.publish_teleop(0.0, 0.0)

    return ws


# ===========================================================================
#  Entry point
# ===========================================================================

def _spin_ros(node: DashboardRosNode):
    """Run ROS2 spinning in a background thread."""
    try:
        rclpy.spin(node)
    except Exception:
        pass


def main(args=None):
    rclpy.init(args=args)

    state = TelemetryState()
    ros_node = DashboardRosNode(state)

    # Start ROS2 spinning in a background thread
    spin_thread = threading.Thread(target=_spin_ros, args=(ros_node,), daemon=True)
    spin_thread.start()

    # Build aiohttp app
    host = os.environ.get("DASHBOARD_HOST", "127.0.0.1")
    port = int(os.environ.get("DASHBOARD_PORT", "8080"))
    control_enabled = os.environ.get("DASHBOARD_ENABLE_CONTROL", "0") == "1"
    control_token = os.environ.get("DASHBOARD_TOKEN", "")
    if host not in {"127.0.0.1", "::1", "localhost"} and control_enabled and not control_token:
        print("Dashboard remote control disabled: set DASHBOARD_TOKEN before enabling it off-host.")
        control_enabled = False

    app = web.Application()
    app["telemetry"] = state
    app["ros_node"] = ros_node
    app["control_enabled"] = control_enabled
    app["control_token"] = control_token

    app.router.add_get("/", handle_index)
    app.router.add_get("/camera", handle_camera)
    app.router.add_get("/ws", handle_websocket)

    # Also serve static assets if any (future-proof)
    if STATIC_DIR.is_dir():
        app.router.add_static("/static/", STATIC_DIR, show_index=False)

    print(f"\n{'='*60}")
    print(f"  Raspbot Dashboard → http://{host}:{port}")
    print(f"  Camera stream     → http://{host}:{port}/camera")
    print(f"  WebSocket         → ws://{host}:{port}/ws")
    print(f"{'='*60}\n")

    try:
        web.run_app(app, host=host, port=port, print=None)
    except KeyboardInterrupt:
        pass
    finally:
        ros_node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
