"""
Simple Sync Manager for PeerCode: handles project sync operations and file system watchers.
"""
import os
import threading
import time
import json
from typing import Dict, Any, Callable

class SyncManager:
    def __init__(self, manager, panel):
        self.manager = manager
        self.panel = panel
        self._watchers = {}
        self._running = False
        self._lock = threading.Lock()

    def start(self):
        # Start watching current project files in background
        with self._lock:
            if self._running:
                return
            self._running = True
        t = threading.Thread(target=self._watch_loop, daemon=True)
        t.start()

    def stop(self):
        with self._lock:
            self._running = False

    def _watch_loop(self):
        # Basic file timestamp-based watcher. Notifies remote via panel.host/client when changes.
        last_mtimes = {}
        while True:
            with self._lock:
                if not self._running:
                    break
            project_state = self.manager.get_project_state()
            files = project_state.get("files", {})
            for remote_path, content in files.items():
                try:
                    local_path = self.manager._remote_to_local_path.get(remote_path)
                    if not local_path:
                        continue
                    if not os.path.exists(local_path):
                        continue
                    mtime = os.path.getmtime(local_path)
                    if remote_path not in last_mtimes or last_mtimes[remote_path] != mtime:
                        last_mtimes[remote_path] = mtime
                        # Read file content and broadcast update
                        with open(local_path, 'r', encoding='utf-8', errors='ignore') as f:
                            content = f.read()
                        packet = None
                        from .network import PeerCodePacket
                        packet = PeerCodePacket(PeerCodePacket.TYPE_CREATE_FILE, {"file_path": remote_path, "content": content})
                        if self.panel.host:
                            self.panel.host.send_packet(packet)
                        elif self.panel.client:
                            self.panel.client.send_packet(packet)
                except Exception:
                    pass
            time.sleep(0.5)

    def trigger_full_sync(self):
        state = self.manager.get_project_state()
        if self.panel.host:
            self.panel.host.send_packet(PeerCodePacket(PeerCodePacket.TYPE_SYNC_ALL, {"files": state['files'], "open_file": state.get('open_file')}))
        elif self.panel.client:
            self.panel.client.send_sync_all(state['files'], state.get('open_file'))

