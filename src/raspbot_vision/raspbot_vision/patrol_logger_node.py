import json
import os
import sqlite3
from pathlib import Path

import rclpy
from rcl_interfaces.msg import SetParametersResult
from rclpy.node import Node
from std_msgs.msg import String

from .workspace import resolve_workspace_path


class PatrolLoggerNode(Node):
    def __init__(self):
        super().__init__('raspbot_patrol_logger')
        self.declare_parameter('db_path', '$RASPBOT_WS/data/patrol/patrol_events.db')
        self.declare_parameter('log_only_on_change', True)
        self.declare_parameter('minimum_log_interval_sec', 30.0)

        self.log_only_on_change = bool(self.get_parameter('log_only_on_change').value)
        self.minimum_log_interval_sec = float(self.get_parameter('minimum_log_interval_sec').value)
        self.db_path = str(resolve_workspace_path(str(self.get_parameter('db_path').value)))
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.db_path)
        self._ensure_schema()
        self.last_detected = None
        self.last_log_time = 0.0
        self.create_subscription(String, 'person_detection/status', self.status_callback, 10)
        self.create_subscription(String, 'patrol/final_result', self.final_result_callback, 10)
        self.add_on_set_parameters_callback(self.on_set_parameters)
        self.get_logger().info(f'patrol logger node started (db_path={self.db_path})')

    def _ensure_column(self, table_name, column_name, column_sql):
        existing = {row[1] for row in self.conn.execute(f'PRAGMA table_info({table_name})').fetchall()}
        if column_name not in existing:
            self.conn.execute(f'ALTER TABLE {table_name} ADD COLUMN {column_name} {column_sql}')

    def _ensure_schema(self):
        self.conn.execute(
            '''
            CREATE TABLE IF NOT EXISTS patrol_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp_utc TEXT NOT NULL,
                detected INTEGER NOT NULL,
                person_count INTEGER NOT NULL,
                max_confidence REAL NOT NULL,
                mode TEXT NOT NULL,
                logged_at_utc TEXT NOT NULL DEFAULT (datetime('now'))
            )
            '''
        )
        self.conn.execute(
            '''
            CREATE TABLE IF NOT EXISTS patrol_final_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                patrol_id TEXT UNIQUE NOT NULL,
                started_at_utc TEXT NOT NULL,
                finished_at_utc TEXT NOT NULL,
                final_decision TEXT NOT NULL,
                detected INTEGER NOT NULL,
                max_person_count INTEGER NOT NULL,
                max_confidence REAL NOT NULL,
                occupied_positions TEXT NOT NULL,
                camera_backend TEXT NOT NULL,
                error_msg TEXT NOT NULL,
                logged_at_utc TEXT NOT NULL DEFAULT (datetime('now'))
            )
            '''
        )
        self.conn.execute(
            '''
            CREATE TABLE IF NOT EXISTS patrol_observations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                patrol_id TEXT NOT NULL,
                scan_position TEXT NOT NULL,
                timestamp_utc TEXT NOT NULL,
                detected INTEGER NOT NULL,
                person_count INTEGER NOT NULL,
                max_confidence REAL NOT NULL,
                mode TEXT NOT NULL,
                camera_backend TEXT NOT NULL,
                error_msg TEXT NOT NULL,
                raw_image_path TEXT NOT NULL,
                debug_image_path TEXT NOT NULL,
                logged_at_utc TEXT NOT NULL DEFAULT (datetime('now')),
                UNIQUE (patrol_id, scan_position)
            )
            '''
        )
        self._ensure_column('patrol_events', 'camera_backend', "TEXT NOT NULL DEFAULT ''")
        self._ensure_column('patrol_events', 'detector_backend', "TEXT NOT NULL DEFAULT ''")
        self._ensure_column('patrol_events', 'error_msg', "TEXT NOT NULL DEFAULT ''")
        self._ensure_column('patrol_events', 'raw_image_path', "TEXT NOT NULL DEFAULT ''")
        self._ensure_column('patrol_events', 'debug_image_path', "TEXT NOT NULL DEFAULT ''")
        self._ensure_column('patrol_events', 'scan_positive_frames', 'INTEGER NOT NULL DEFAULT 0')
        self._ensure_column('patrol_events', 'scan_total_frames', 'INTEGER NOT NULL DEFAULT 0')
        self._ensure_column('patrol_final_results', 'detector_backend', "TEXT NOT NULL DEFAULT ''")
        self._ensure_column('patrol_final_results', 'positive_observation_count', 'INTEGER NOT NULL DEFAULT 0')
        self._ensure_column('patrol_final_results', 'total_observation_count', 'INTEGER NOT NULL DEFAULT 0')
        self._ensure_column('patrol_final_results', 'decision_reason', "TEXT NOT NULL DEFAULT ''")
        self._ensure_column('patrol_observations', 'detector_backend', "TEXT NOT NULL DEFAULT ''")
        self._ensure_column('patrol_observations', 'scan_positive_frames', 'INTEGER NOT NULL DEFAULT 0')
        self._ensure_column('patrol_observations', 'scan_total_frames', 'INTEGER NOT NULL DEFAULT 0')
        self.conn.execute('CREATE INDEX IF NOT EXISTS idx_patrol_observations_patrol_id ON patrol_observations(patrol_id)')
        self.conn.commit()

    def on_set_parameters(self, params):
        for param in params:
            if param.name == 'log_only_on_change':
                self.log_only_on_change = bool(param.value)
            elif param.name == 'minimum_log_interval_sec':
                if float(param.value) < 0.0:
                    return SetParametersResult(successful=False, reason='minimum_log_interval_sec must be >= 0')
                self.minimum_log_interval_sec = float(param.value)
        return SetParametersResult(successful=True)

    def status_callback(self, msg: String):
        try:
            payload = json.loads(msg.data)
        except json.JSONDecodeError:
            self.get_logger().warning('invalid JSON on person_detection/status')
            return

        detected = bool(payload.get('detected', False))
        now_sec = self.get_clock().now().nanoseconds / 1e9
        if self.log_only_on_change and self.last_detected is not None and detected == self.last_detected:
            if now_sec - self.last_log_time < self.minimum_log_interval_sec:
                return

        self.conn.execute(
            '''
            INSERT INTO patrol_events (
                timestamp_utc, detected, person_count, max_confidence, mode,
                camera_backend, detector_backend, error_msg, raw_image_path, debug_image_path,
                scan_positive_frames, scan_total_frames
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''',
            (
                str(payload.get('timestamp_utc', '')),
                int(detected),
                int(payload.get('person_count', 0)),
                float(payload.get('max_confidence', 0.0)),
                str(payload.get('mode', 'unknown')),
                str(payload.get('camera_backend', '')),
                str(payload.get('detector_backend', '')),
                str(payload.get('error_msg', '')),
                str(payload.get('raw_image_path', '')),
                str(payload.get('debug_image_path', '')),
                int(payload.get('scan_positive_frames', 0)),
                int(payload.get('scan_total_frames', 0)),
            ),
        )
        self.conn.commit()
        self.last_detected = detected
        self.last_log_time = now_sec
        self.get_logger().info(
            f'logged patrol event: detected={detected}, count={int(payload.get("person_count", 0))}, '
            f'confidence={float(payload.get("max_confidence", 0.0)):.2f}, '
            f'detector_backend={payload.get("detector_backend", "")}'
        )

    def final_result_callback(self, msg: String):
        try:
            payload = json.loads(msg.data)
        except json.JSONDecodeError:
            self.get_logger().warning('invalid JSON on patrol/final_result')
            return

        occupied_positions = payload.get('occupied_positions', [])
        if not isinstance(occupied_positions, list):
            occupied_positions = []
        patrol_id = str(payload.get('patrol_id', ''))
        self.conn.execute(
            '''
            INSERT OR REPLACE INTO patrol_final_results (
                patrol_id, started_at_utc, finished_at_utc, final_decision, detected,
                max_person_count, max_confidence, occupied_positions, camera_backend, detector_backend,
                error_msg, positive_observation_count, total_observation_count, decision_reason
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''',
            (
                patrol_id,
                str(payload.get('started_at_utc', '')),
                str(payload.get('finished_at_utc', '')),
                str(payload.get('final_decision', 'unknown')),
                int(bool(payload.get('detected', False))),
                int(payload.get('max_person_count', 0)),
                float(payload.get('max_confidence', 0.0)),
                ','.join(occupied_positions),
                str(payload.get('camera_backend', '')),
                str(payload.get('detector_backend', '')),
                str(payload.get('error_msg', '')),
                int(payload.get('positive_observation_count', 0)),
                int(payload.get('total_observation_count', 0)),
                str(payload.get('decision_reason', '')),
            ),
        )

        observations = payload.get('observations', [])
        if not isinstance(observations, list):
            observations = []
        self.conn.execute('DELETE FROM patrol_observations WHERE patrol_id = ?', (patrol_id,))
        for item in observations:
            if not isinstance(item, dict):
                continue
            self.conn.execute(
                '''
                INSERT OR REPLACE INTO patrol_observations (
                    patrol_id, scan_position, timestamp_utc, detected, person_count,
                    max_confidence, mode, camera_backend, detector_backend, error_msg,
                    raw_image_path, debug_image_path, scan_positive_frames, scan_total_frames
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''',
                (
                    patrol_id,
                    str(item.get('scan_position', 'unknown')),
                    str(item.get('timestamp_utc', '')),
                    int(bool(item.get('detected', False))),
                    int(item.get('person_count', 0)),
                    float(item.get('max_confidence', 0.0)),
                    str(item.get('mode', 'unknown')),
                    str(item.get('camera_backend', '')),
                    str(item.get('detector_backend', '')),
                    str(item.get('error_msg', '')),
                    str(item.get('raw_image_path', '')),
                    str(item.get('debug_image_path', '')),
                    int(item.get('scan_positive_frames', 0)),
                    int(item.get('scan_total_frames', 0)),
                ),
            )
        self.conn.commit()
        self.get_logger().info(
            f"logged patrol final result: patrol_id={patrol_id} final_decision={payload.get('final_decision', 'unknown')} detector_backend={payload.get('detector_backend', '')} observations={len(observations)} reason={payload.get('decision_reason', '')}"
        )

    def destroy_node(self):
        try:
            self.conn.close()
        finally:
            return super().destroy_node()


def main(args=None):
    rclpy.init(args=args)
    node = PatrolLoggerNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
