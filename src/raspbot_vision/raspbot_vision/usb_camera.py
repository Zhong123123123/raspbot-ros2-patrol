import os
import subprocess
import tempfile
import time

import cv2
import numpy as np


class USBCamera:
    def __init__(self, device, width, height, fps, warmup_frames=10):
        self.device = device
        self.width = width
        self.height = height
        self.fps = fps
        self.warmup_frames = warmup_frames
        self.cap = None
        self.backend = None
        self.real_device = os.path.realpath(str(device)) if isinstance(device, str) else device
        self.last_error = None

    def _open_opencv(self, retry=5):
        self.release()
        for _ in range(retry):
            self.cap = cv2.VideoCapture(self.real_device, cv2.CAP_V4L2)
            if self.cap.isOpened():
                self.cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'MJPG'))
                self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
                self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
                self.cap.set(cv2.CAP_PROP_FPS, self.fps)
                self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                time.sleep(1.0)
                ok = False
                for _ in range(self.warmup_frames):
                    ret, frame = self.cap.read()
                    if ret and frame is not None:
                        ok = True
                        break
                    time.sleep(0.05)
                if ok:
                    self.backend = 'opencv'
                    self.last_error = None
                    return True
                self.last_error = 'opencv opened but could not read warmup frames'
            else:
                self.last_error = f'opencv could not open {self.real_device}'
            self.release()
            time.sleep(0.3)
        return False

    def _capture_once_v4l2ctl(self):
        with tempfile.NamedTemporaryFile(prefix='raspbot_cam_', suffix='.raw', delete=False) as tmp:
            raw_path = tmp.name
        try:
            cmd = [
                'v4l2-ctl', '-d', str(self.real_device),
                f'--set-fmt-video=width={self.width},height={self.height},pixelformat=YUYV',
                '--stream-mmap', '--stream-count=1', f'--stream-to={raw_path}',
            ]
            result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=5.0, text=True)
            if result.returncode != 0:
                self.last_error = f'v4l2-ctl rc={result.returncode} stderr={result.stderr.strip()[:160]}'
                return None
            if not os.path.exists(raw_path):
                self.last_error = 'v4l2-ctl completed but output file missing'
                return None
            expected_size = self.width * self.height * 2
            data = np.fromfile(raw_path, dtype=np.uint8)
            if data.size != expected_size:
                self.last_error = f'v4l2-ctl size mismatch expected={expected_size} actual={data.size}'
                return None
            yuyv = data.reshape((self.height, self.width, 2))
            self.last_error = None
            return cv2.cvtColor(yuyv, cv2.COLOR_YUV2BGR_YUYV)
        except subprocess.TimeoutExpired:
            self.last_error = 'v4l2-ctl timeout'
            return None
        finally:
            try:
                os.remove(raw_path)
            except FileNotFoundError:
                pass

    def _read_v4l2ctl_frame(self, retry=4):
        for attempt in range(retry):
            frame = self._capture_once_v4l2ctl()
            if frame is not None:
                return frame
            time.sleep(0.15 + 0.05 * attempt)
        return None

    def _open_v4l2ctl(self):
        frame = self._read_v4l2ctl_frame()
        if frame is None:
            return False
        self.backend = 'v4l2ctl'
        return True

    def open(self, retry=5):
        if self._open_opencv(retry=retry):
            return True
        if self._open_v4l2ctl():
            return True
        raise RuntimeError(f'Cannot open camera: {self.device} ({self.last_error})')

    def read(self):
        if self.backend is None:
            self.open()
        if self.backend == 'opencv':
            if self.cap is None or not self.cap.isOpened():
                self.open()
            ret, frame = self.cap.read()
            if ret and frame is not None:
                self.last_error = None
                return frame
            self.last_error = 'opencv read returned empty frame'
            return None
        if self.backend == 'v4l2ctl':
            return self._read_v4l2ctl_frame()
        return None

    def release(self):
        if self.cap is not None:
            try:
                self.cap.release()
            except Exception:
                pass
            self.cap = None
            time.sleep(0.2)
        if self.backend == 'opencv':
            self.backend = None
