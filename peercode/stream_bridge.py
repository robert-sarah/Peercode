
"""
PeerCode Stream Bridge - High performance real-time camera and screen capture
Created By Levi Enama
"""

import sys
import os
import time

# Add ExCo to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'ExCo-master'))
import qt

import numpy as np
import mss
import cv2


class CaptureThread(qt.QThread):
    """Thread for capturing camera or screen"""

    frame_ready = qt.pyqtSignal(bytes, int, int)  # (data, width, height)
    error_occurred = qt.pyqtSignal(str)

    SOURCE_SCREEN = "screen"
    SOURCE_CAMERA = "camera"

    def __init__(self, source=SOURCE_SCREEN, fps=30, width=None, height=None, camera_index=0):
        super().__init__()
        self.source = source
        self.fps = fps
        self.width = width
        self.height = height
        self.camera_index = camera_index
        self._running = False

    def run(self):
        self._running = True
        frame_interval = 1.0 / self.fps
        last_frame = time.time()

        if self.source == self.SOURCE_SCREEN:
            self._capture_screen(frame_interval, last_frame)
        else:
            self._capture_camera(frame_interval, last_frame)

    def _capture_screen(self, frame_interval, last_frame):
        try:
            with mss.mss() as sct:
                monitor = sct.monitors[1]
                while self._running:
                    img = sct.grab(monitor)
                    width, height = img.size
                    data = bytearray(img.rgb)
                    # Convert BGRA -> RGBA
                    for i in range(0, len(data), 4):
                        data[i], data[i + 2] = data[i + 2], data[i]
                    self.frame_ready.emit(bytes(data), width, height)
                    elapsed = time.time() - last_frame
                    if elapsed < frame_interval:
                        time.sleep(frame_interval - elapsed)
                    last_frame = time.time()
        except Exception as e:
            self.error_occurred.emit(f"Screen capture error: {str(e)}")

    def _capture_camera(self, frame_interval, last_frame):
        try:
            cap = cv2.VideoCapture(self.camera_index)
            if not cap.isOpened():
                self.error_occurred.emit("Failed to open camera!")
                return

            while self._running:
                ret, frame = cap.read()
                if not ret:
                    continue

                # Resize if needed
                if self.width and self.height:
                    frame = cv2.resize(frame, (self.width, self.height))

                height, width, _ = frame.shape
                # Convert BGR -> RGB
                frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                # Add alpha channel
                frame_rgba = cv2.cvtColor(frame_rgb, cv2.COLOR_RGB2RGBA)
                data = frame_rgba.tobytes()

                self.frame_ready.emit(data, width, height)
                elapsed = time.time() - last_frame
                if elapsed < frame_interval:
                    time.sleep(frame_interval - elapsed)
                last_frame = time.time()

            cap.release()
        except Exception as e:
            self.error_occurred.emit(f"Camera capture error: {str(e)}")

    def stop(self):
        self._running = False
        self.wait()


class StreamBridge:
    """PeerCode Stream Bridge - No simulation! Real camera and screen only!"""

    def __init__(self):
        self._capture_thread = None

    def initialize(self):
        return True

    def start_capture(self, source=CaptureThread.SOURCE_SCREEN, fps=30, width=0, height=0, camera_index=0):
        self._capture_thread = CaptureThread(
            source=source,
            fps=fps,
            width=width if width > 0 else None,
            height=height if height > 0 else None,
            camera_index=camera_index
        )
        return True, self._capture_thread

    def stop_capture(self):
        if self._capture_thread:
            self._capture_thread.stop()
            self._capture_thread = None

    def shutdown(self):
        self.stop_capture()
