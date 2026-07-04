"""
PeerCode Voice Stream Worker
Handles low-latency audio capture, playback, and packetized audio transport.
"""

import base64
import queue
import threading
import time

try:
    import sounddevice as sd
    import numpy as np
except Exception:
    sd = None
    np = None

import qt
from .network import PeerCodePacket


class VoiceStreamWorker(qt.QObject):
    """Voice stream controller for PeerCode."""

    error_occurred = qt.pyqtSignal(str)
    active_users_changed = qt.pyqtSignal(list)
    status_changed = qt.pyqtSignal(str)

    def __init__(self, panel, sample_rate=16000, channels=1, blocksize=512):
        super().__init__()
        self.panel = panel
        self.sample_rate = sample_rate
        self.channels = channels
        self.blocksize = blocksize
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

        if sd is None or np is None:
            raise RuntimeError(
                "sounddevice and numpy are required for voice streaming. Install them with pip."
            )

        self._running = True
        self._send_thread = threading.Thread(target=self._send_loop, daemon=True)
        self._send_thread.start()

        try:
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
        self.status_changed.emit("Voice channel active")

    def stop(self):
        print("[AUDIO DEBUG] Stopping voice worker...")
        with self._lock:
            if not self._running:
                print("[AUDIO DEBUG] Worker already stopped")
                return
            self._running = False

        try:
            self._announce_presence(active=False)
        except Exception as e:
            print(f"[AUDIO DEBUG] Error announcing presence: {e}")

        # Stop streams first
        print("[AUDIO DEBUG] Stopping input/output streams...")
        try:
            if self._input_stream:
                try:
                    self._input_stream.stop()
                except Exception:
                    pass
                try:
                    self._input_stream.close()
                except Exception:
                    pass
                self._input_stream = None
        except Exception as e:
            print(f"[AUDIO DEBUG] Input stream error: {e}")
            self._input_stream = None

        try:
            if self._output_stream:
                try:
                    self._output_stream.stop()
                except Exception:
                    pass
                try:
                    self._output_stream.close()
                except Exception:
                    pass
                self._output_stream = None
        except Exception as e:
            print(f"[AUDIO DEBUG] Output stream error: {e}")
            self._output_stream = None

        # Wait for send thread
        print("[AUDIO DEBUG] Waiting for send thread...")
        if self._send_thread:
            try:
                if self._send_thread.is_alive():
                    self._send_thread.join(timeout=2.0)
            except Exception as e:
                print(f"[AUDIO DEBUG] Send thread join error: {e}")
            self._send_thread = None

        # Drain queues
        print("[AUDIO DEBUG] Draining queues...")
        self._drain_play_queue()
        while not self._send_queue.empty():
            try:
                self._send_queue.get_nowait()
            except Exception:
                break

        print("[AUDIO DEBUG] Voice worker stopped successfully")
        self.status_changed.emit("Voice channel stopped")

    def _broadcast_audio_chunk(self, chunk_bytes: bytes):
        packet_data = {
            "payload": base64.b64encode(chunk_bytes).decode("ascii"),
            "sample_rate": self.sample_rate,
            "channels": self.channels,
        }
        packet = PeerCodePacket(PeerCodePacket.TYPE_AUDIO_CHUNK, packet_data, self.panel._current_username())
        if self.panel.host:
            print(f"[AUDIO DEBUG] Host broadcasting chunk ({len(chunk_bytes)} bytes) to all clients")
            self.panel.host.send_packet(packet)
        elif self.panel.client:
            print(f"[AUDIO DEBUG] Client sending chunk ({len(chunk_bytes)} bytes) to host")
            self.panel.client.send_packet(packet)
        else:
            print(f"[AUDIO DEBUG] No connection (host/client) to broadcast audio chunk")

    def _capture_callback(self, indata, frames, time_info, status):
        if status:
            self.error_occurred.emit(str(status))
        if not self._running:
            return

        try:
            chunk_bytes = indata.tobytes()
            try:
                self._send_queue.put_nowait(chunk_bytes)
            except queue.Full:
                print(f"[AUDIO DEBUG] Send queue full, dropping captured audio frame")
        except Exception as e:
            print(f"[AUDIO DEBUG] Audio capture error: {e}")
            self.error_occurred.emit(f"Audio capture error: {e}")

    def _playback_callback(self, outdata, frames, time_info, status):
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
            print(f"[AUDIO DEBUG] Playing audio chunk ({len(audio_bytes)} bytes)")
        except queue.Empty:
            outdata[:] = silence_bytes
        except Exception as e:
            print(f"[AUDIO DEBUG] Playback error: {e}")
            outdata[:] = silence_bytes
            self.error_occurred.emit(f"Playback error: {e}")

    def _send_loop(self):
        while self._running:
            try:
                chunk_bytes = self._send_queue.get(timeout=0.2)
                self._broadcast_audio_chunk(chunk_bytes)
            except queue.Empty:
                continue
            except Exception as e:
                print(f"[AUDIO DEBUG] Send loop error: {e}")
                self.error_occurred.emit(f"Audio send error: {e}")

    def _drain_play_queue(self):
        while not self._play_queue.empty():
            try:
                self._play_queue.get_nowait()
            except queue.Empty:
                break

    def handle_remote_audio(self, packet: PeerCodePacket):
        if packet.sender == self.panel._current_username():
            print(f"[AUDIO DEBUG] Ignoring own audio chunk")
            return

        data = packet.data or {}
        payload = data.get("payload")
        if not payload:
            print(f"[AUDIO DEBUG] Empty audio payload received from {packet.sender}")
            return

        try:
            raw_bytes = base64.b64decode(payload)
            print(f"[AUDIO DEBUG] Received audio chunk from {packet.sender} ({len(raw_bytes)} bytes) - queueing for playback")
            try:
                self._play_queue.put_nowait(raw_bytes)
            except queue.Full:
                print(f"[AUDIO DEBUG] Play queue full, dropping audio chunk from {packet.sender}")
        except Exception as e:
            print(f"[AUDIO DEBUG] Invalid audio packet from {packet.sender}: {e}")
            self.error_occurred.emit(f"Invalid audio packet: {e}")

    def _announce_presence(self, active: bool):
        packet_data = {"username": self.panel._current_username(), "active": active}
        packet = PeerCodePacket(PeerCodePacket.TYPE_AUDIO_PRESENCE, packet_data)
        if self.panel.host:
            # Host needs to update itself and broadcast to clients
            if hasattr(self.panel, 'voice_status') and self.panel.voice_status:
                self.panel.voice_status.update_presence(self.panel._current_username(), active)
            self.panel.host.send_packet(packet)
        elif self.panel.client:
            # Client sends to host (which will broadcast back)
            self.panel.client.send_packet(packet)

    def set_active_users(self, users):
        self.active_users_changed.emit(users)


class VoiceStatusManager:
    """Small helper for voice user tracking."""

    def __init__(self, panel):
        self.panel = panel
        self.active_users = []

    def update_presence(self, username, active):
        if active and username not in self.active_users:
            self.active_users.append(username)
        elif not active and username in self.active_users:
            self.active_users.remove(username)
        self.panel.voice_manager.set_active_users(list(self.active_users))

    def reset(self):
        self.active_users = []
        self.panel.voice_manager.set_active_users([])
