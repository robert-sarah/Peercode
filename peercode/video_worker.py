"""
PeerCode Video Stream Worker with Audio
Handles low-latency video capture (screen/webcam), encoding, audio, and network broadcast.
"""

import base64
import queue
import threading
import time
import struct

try:
    import cv2
    import numpy as np
    import sounddevice as sd
except Exception:
    cv2 = None
    np = None
    sd = None

import qt
from .network import PeerCodePacket


class VideoStreamWorker(qt.QObject):
    """Video + Audio stream controller for PeerCode."""

    error_occurred = qt.pyqtSignal(str)
    active_users_changed = qt.pyqtSignal(list)
    status_changed = qt.pyqtSignal(str)
    frame_ready = qt.pyqtSignal(bytes, int, int, str)  # frame_data, width, height, sender

    SOURCE_SCREEN = 0
    SOURCE_CAMERA = 1

    def __init__(self, panel, source=SOURCE_SCREEN, camera_index=0, sample_rate=16000, channels=1, blocksize=512):
        super().__init__()
        self.panel = panel
        self.source = source
        self.camera_index = camera_index
        self.sample_rate = sample_rate
        self.channels = channels
        self.blocksize = blocksize
        
        # Video
        self._video_queue = queue.Queue(maxsize=64)
        self._capture = None
        self._video_thread = None
        self._fps = 10
        self._frame_size = (640, 360)
        
        # Audio
        self._send_queue = queue.Queue(maxsize=128)
        self._play_queue = queue.Queue(maxsize=256)
        self._send_thread = None
        self._input_stream = None
        self._output_stream = None
        
        self._running = False
        self._lock = threading.Lock()

    def start(self):
        if self._running:
            return

        if cv2 is None or np is None or sd is None:
            raise RuntimeError("cv2, numpy, and sounddevice required. Install with: pip install opencv-python numpy sounddevice")

        self._running = True
        
        # Start video capture thread
        self._video_thread = threading.Thread(target=self._video_loop, daemon=True)
        self._video_thread.start()
        
        # Start audio send thread
        self._send_thread = threading.Thread(target=self._send_loop, daemon=True)
        self._send_thread.start()

        try:
            # Setup audio streams
            self._output_stream = sd.RawOutputStream(
                samplerate=self.sample_rate,
                blocksize=self.blocksize,
                channels=self.channels,
                dtype="int16",
                callback=self._playback_callback,
                latency="low",
            )
            self._input_stream = sd.RawInputStream(
                samplerate=self.sample_rate,
                blocksize=self.blocksize,
                channels=self.channels,
                dtype="int16",
                callback=self._capture_callback,
                latency="low",
            )
            self._output_stream.start()
            self._input_stream.start()
        except Exception as e:
            self.stop()
            raise RuntimeError(f"Failed to start audio streams: {e}")

        self._announce_presence(active=True)
        self.status_changed.emit("Video + Audio stream started")

    def stop(self):
        print("[VIDEO DEBUG] Stopping video worker...")
        with self._lock:
            if not self._running:
                return
            self._running = False

        try:
            self._announce_presence(active=False)
        except Exception as e:
            print(f"[VIDEO DEBUG] Presence error: {e}")

        # Stop video capture
        print("[VIDEO DEBUG] Stopping video capture...")
        try:
            if self._capture:
                self._capture.release()
                self._capture = None
        except Exception as e:
            print(f"[VIDEO DEBUG] Video capture error: {e}")

        # Stop audio streams
        print("[VIDEO DEBUG] Stopping audio streams...")
        try:
            if self._input_stream:
                try:
                    self._input_stream.stop()
                    self._input_stream.close()
                except Exception:
                    pass
                self._input_stream = None
        except Exception as e:
            print(f"[VIDEO DEBUG] Input stream error: {e}")

        try:
            if self._output_stream:
                try:
                    self._output_stream.stop()
                    self._output_stream.close()
                except Exception:
                    pass
                self._output_stream = None
        except Exception as e:
            print(f"[VIDEO DEBUG] Output stream error: {e}")

        # Wait for threads
        print("[VIDEO DEBUG] Waiting for threads...")
        if self._video_thread and self._video_thread.is_alive():
            self._video_thread.join(timeout=2.0)
        self._video_thread = None

        if self._send_thread and self._send_thread.is_alive():
            self._send_thread.join(timeout=2.0)
        self._send_thread = None

        # Drain queues
        while not self._video_queue.empty():
            try:
                self._video_queue.get_nowait()
            except Exception:
                break
        while not self._send_queue.empty():
            try:
                self._send_queue.get_nowait()
            except Exception:
                break
        while not self._play_queue.empty():
            try:
                self._play_queue.get_nowait()
            except Exception:
                break

        print("[VIDEO DEBUG] Video worker stopped successfully")
        self.status_changed.emit("Livestream stopped")
        try:
            if hasattr(self.panel, '_clear_livestream_previews'):
                self.panel._clear_livestream_previews()
        except Exception as e:
            print(f"[VIDEO DEBUG] Error clearing previews: {e}")

    def _video_loop(self):
        """Capture and broadcast video frames"""
        if self.source == self.SOURCE_SCREEN:
            # Screen capture using mss
            try:
                import mss
                sct = mss.mss()
                monitor = sct.monitors[1]  # Primary monitor
            except Exception:
                sct = None
        else:
            # Webcam capture
            try:
                self._capture = cv2.VideoCapture(self.camera_index)
                self._capture.set(cv2.CAP_PROP_FPS, self._fps)
                self._capture.set(cv2.CAP_PROP_FRAME_WIDTH, self._frame_size[0])
                self._capture.set(cv2.CAP_PROP_FRAME_HEIGHT, self._frame_size[1])
            except Exception as e:
                print(f"[VIDEO DEBUG] Camera init error: {e}")
                return

        frame_count = 0
        while self._running:
            try:
                if self.source == self.SOURCE_SCREEN and sct:
                    # Screen capture
                    screenshot = sct.grab(monitor)
                    frame = np.array(screenshot)
                    frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)
                else:
                    # Webcam
                    ret, frame = self._capture.read()
                    if not ret:
                        continue
                    frame = cv2.resize(frame, self._frame_size)

                # Resize and compress for a smoother, more stable stream
                if frame.shape[1] != self._frame_size[0] or frame.shape[0] != self._frame_size[1]:
                    frame = cv2.resize(frame, self._frame_size)
                ret, encoded = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 60])
                if ret:
                    # Prepare RGB bytes for local preview and emit immediately
                    try:
                        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                        self.frame_ready.emit(frame_rgb.tobytes(), frame.shape[1], frame.shape[0], self.panel._current_username())
                    except Exception:
                        pass

                    frame_data = encoded.tobytes()
                    try:
                        self._video_queue.put_nowait(frame_data)
                        frame_count += 1
                        if frame_count % 30 == 0:
                            print(f"[VIDEO DEBUG] Captured {frame_count} frames")
                    except queue.Full:
                        print(f"[VIDEO DEBUG] Video queue full, dropping frame")

                time.sleep(max(0.05, 1.0 / self._fps))
            except Exception as e:
                print(f"[VIDEO DEBUG] Video loop error: {e}")
                if self._running:
                    time.sleep(0.1)

    def _broadcast_video_chunk(self, frame_data: bytes):
        """Broadcast video frame to all peers"""
        packet_data = {
            "payload": base64.b64encode(frame_data).decode("ascii"),
            "width": self._frame_size[0],
            "height": self._frame_size[1],
        }
        packet = PeerCodePacket(PeerCodePacket.TYPE_STREAM_FRAME, packet_data, self.panel._current_username())
        
        if self.panel.host:
            print(f"[VIDEO DEBUG] Host broadcasting frame ({len(frame_data)} bytes)")
            self.panel.host.send_packet(packet)
        elif self.panel.client:
            print(f"[VIDEO DEBUG] Client sending frame ({len(frame_data)} bytes)")
            self.panel.client.send_packet(packet)

    def _broadcast_audio_chunk(self, chunk_bytes: bytes):
        """Broadcast audio frame to all peers"""
        packet_data = {
            "payload": base64.b64encode(chunk_bytes).decode("ascii"),
            "sample_rate": self.sample_rate,
            "channels": self.channels,
        }
        packet = PeerCodePacket(PeerCodePacket.TYPE_AUDIO_CHUNK, packet_data, self.panel._current_username())
        
        if self.panel.host:
            self.panel.host.send_packet(packet)
        elif self.panel.client:
            self.panel.client.send_packet(packet)

    def _send_loop(self):
        """Send both video and audio"""
        while self._running:
            try:
                # Check for video frames
                try:
                    frame_data = self._video_queue.get_nowait()
                    self._broadcast_video_chunk(frame_data)
                except queue.Empty:
                    pass

                # Check for audio
                try:
                    audio_data = self._send_queue.get_nowait()
                    self._broadcast_audio_chunk(audio_data)
                except queue.Empty:
                    pass

                time.sleep(0.001)
            except Exception as e:
                print(f"[VIDEO DEBUG] Send loop error: {e}")

    def _capture_callback(self, indata, frames, time_info, status):
        """Audio capture callback"""
        if status:
            self.error_occurred.emit(str(status))
        if not self._running:
            return

        try:
            chunk_bytes = indata.tobytes()
            try:
                self._send_queue.put_nowait(chunk_bytes)
            except queue.Full:
                print(f"[VIDEO DEBUG] Audio send queue full")
        except Exception as e:
            print(f"[VIDEO DEBUG] Audio capture error: {e}")

    def _playback_callback(self, outdata, frames, time_info, status):
        """Audio playback callback"""
        if status:
            self.error_occurred.emit(str(status))

        bytes_per_frame = self.channels * 2
        silence_bytes = b"\x00" * (frames * bytes_per_frame)

        if not self._running:
            outdata[:] = silence_bytes
            return

        try:
            raw_chunk = self._play_queue.get_nowait()
            chunk = np.frombuffer(raw_chunk, dtype=np.int16)
            chunk = chunk.reshape(-1, self.channels)
            if chunk.shape[0] >= frames:
                audio_bytes = chunk[:frames, :].astype(np.int16).tobytes()
            else:
                padded = np.zeros((frames, self.channels), dtype=np.int16)
                padded[: chunk.shape[0], :] = chunk
                audio_bytes = padded.tobytes()
            outdata[:] = audio_bytes
        except queue.Empty:
            outdata[:] = silence_bytes
        except Exception as e:
            print(f"[VIDEO DEBUG] Playback error: {e}")
            outdata[:] = silence_bytes

    def handle_remote_video(self, packet: PeerCodePacket):
        """Handle incoming video frame"""
        if packet.sender == self.panel._current_username():
            return

        data = packet.data or {}
        payload = data.get("payload")
        width = data.get("width", 640)
        height = data.get("height", 480)

        if not payload:
            return

        try:
            frame_data = base64.b64decode(payload)
            nparr = np.frombuffer(frame_data, np.uint8)
            frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            if frame is not None:
                    frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    print(f"[VIDEO DEBUG] Decoded remote frame from {packet.sender}")
                    self.frame_ready.emit(frame_rgb.tobytes(), frame.shape[1], frame.shape[0], packet.sender)
        except Exception as e:
            print(f"[VIDEO DEBUG] Remote video decode error: {e}")

    def handle_remote_audio(self, packet: PeerCodePacket):
        """Handle incoming audio frame"""
        if packet.sender == self.panel._current_username():
            return

        data = packet.data or {}
        payload = data.get("payload")

        if not payload:
            return

        try:
            raw_bytes = base64.b64decode(payload)
            try:
                self._play_queue.put_nowait(raw_bytes)
            except queue.Full:
                print(f"[VIDEO DEBUG] Audio play queue full")
        except Exception as e:
            print(f"[VIDEO DEBUG] Remote audio error: {e}")

    def _announce_presence(self, active: bool):
        """Announce presence to other peers"""
        packet_data = {"username": self.panel._current_username(), "active": active}
        packet = PeerCodePacket(PeerCodePacket.TYPE_AUDIO_PRESENCE, packet_data)
        if self.panel.host and getattr(self.panel.host, 'running', False):
            if hasattr(self.panel, 'voice_status') and self.panel.voice_status:
                self.panel.voice_status.update_presence(self.panel._current_username(), active)
            self.panel.host.send_packet(packet)
        elif self.panel.client and getattr(self.panel.client, 'running', False) and getattr(self.panel.client, 'socket', None) is not None:
            self.panel.client.send_packet(packet)

    def set_active_users(self, users):
        self.active_users_changed.emit(users)
