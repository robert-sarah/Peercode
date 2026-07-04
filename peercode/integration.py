
"""
Integration module for connecting PeerCode with ExCo
Created By Levi Enama
"""

import sys
import os

# Make sure ExCo is in the path
def _ensure_exco_in_path():
    EXCO_PATH = os.path.join(os.path.dirname(__file__), '..', 'ExCo-master')
    if EXCO_PATH not in sys.path:
        sys.path.insert(0, EXCO_PATH)

_ensure_exco_in_path()

import qt
import data
import functions

from .ot import OTDocumentState, TextOperation
from .ui import PeerCodePanel


class PeerCodeManager:
    """Manages the PeerCode integration with ExCo"""
    
    _instance = None
    
    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    
    def __init__(self):
        self.main_window = None
        self.panel = None
        self.dock_widget = None
        self._connected_editors = set()
        self._last_text_states = {}
        self._remote_to_local_path = {}  # Maps remote filename to local absolute path
        self._local_to_remote_path = {}  # Maps local absolute path to remote filename
        self._ot_states = {}
    
    def get_project_state(self):
        """Get the current project state as a dictionary"""
        import os
        files = {}
        open_file = None
        
        if hasattr(self.main_window, "get_all_editors"):
            editors = self.main_window.get_all_editors()
            for editor in editors:
                local_path = getattr(editor, "save_path", "") or getattr(editor, "file_path", "") or ""
                if local_path:
                    # Use just the filename as remote path
                    remote_path = os.path.basename(local_path)
                    self._local_to_remote_path[local_path] = remote_path
                    self._remote_to_local_path[remote_path] = local_path
                    content = editor.text()
                    files[remote_path] = content
            
            # Try to get the currently active file
            if hasattr(self.main_window, "current_tab_widget") and hasattr(self.main_window.current_tab_widget, "currentWidget"):
                current_widget = self.main_window.current_tab_widget.currentWidget()
                if hasattr(current_widget, "save_path"):
                    local_path = current_widget.save_path
                    open_file = self._local_to_remote_path.get(local_path, os.path.basename(local_path) if local_path else None)
        
        return {"files": files, "open_file": open_file}
    
    def open_file_remote(self, remote_path, content):
        """Open a file from remote sync"""
        import os
        if hasattr(self.main_window, "open_file"):
            try:
                # Check if we already have a local path for this remote file
                if remote_path not in self._remote_to_local_path:
                    # Create it locally in current working directory
                    local_path = os.path.abspath(remote_path)
                    self._remote_to_local_path[remote_path] = local_path
                    self._local_to_remote_path[local_path] = remote_path
                    self._create_file_local(local_path, content)
                local_path = self._remote_to_local_path[remote_path]
                self.main_window.open_file(local_path)
            except Exception as e:
                print(f"Error opening remote file {remote_path}: {e}")

    def sync_project(self):
        """Broadcast the current project state to all connected peers."""
        try:
            state = self.get_project_state()
            files = state.get("files", {})
            open_file = state.get("open_file")
            if self.panel and self.panel.host:
                from .network import PeerCodePacket
                pkt = PeerCodePacket(PeerCodePacket.TYPE_SYNC_ALL, {"files": files, "open_file": open_file}, self.panel._current_username())
                self.panel.host.send_packet(pkt)
                if hasattr(self.panel, "_append_chat"):
                    self.panel._append_chat("System", "Project synced to connected peers.")
            elif self.panel and self.panel.client:
                self.panel.client.send_sync_all(files, open_file)
                if hasattr(self.panel, "_append_chat"):
                    self.panel._append_chat("System", "Sync requested from host.")
            else:
                if self.panel and hasattr(self.panel, "_append_chat"):
                    self.panel._append_chat("System", "No active session to sync.")
        except Exception as e:
            print(f"Sync error: {e}")
    
    def initialize(self, main_window):
        """Initialize PeerCode with the ExCo main window"""
        try:
            self.main_window = main_window
            
            self.panel = PeerCodePanel(main_window, self)
            
            # --- Integrate video+audio stream worker and sync button without editing UI file ---
            try:
                from .video_worker import VideoStreamWorker
                from .stream_worker import VoiceStatusManager
                from .network import PeerCodePacket

                self._worker = None
                self._status_mgr = None
                
                def _get_worker():
                    if self._worker is None:
                        self._worker = VideoStreamWorker(self.panel)
                    return self._worker
                
                def _get_status_mgr():
                    if self._status_mgr is None:
                        self._status_mgr = VoiceStatusManager(self.panel)
                    return self._status_mgr

                self.panel.voice_manager = None
                self.panel.voice_status = None

                def _start_voice():
                    try:
                        worker = _get_worker()
                        status_mgr = _get_status_mgr()
                        if not worker._running:
                            worker.start()
                            status_mgr.update_presence(self.panel._current_username(), True)
                            self.panel.is_streaming = True
                            self.panel._update_session_controls()
                            self.panel.leave_audio_button.setEnabled(True)
                            self.panel.create_audio_button.setEnabled(False)
                            self.panel.join_audio_button.setEnabled(False)
                            self.panel._append_chat("System", "Video + Audio stream started")
                            self.panel.video_label.setText("Video + Audio channel active\nYou are now broadcasting your video and audio")
                    except Exception as e:
                        print(f"Voice start error: {e}")
                        self.panel._append_chat("System", f"Stream error: {str(e)}")

                def _stop_voice():
                    try:
                        worker = self._worker
                        status_mgr = self._status_mgr
                        if worker is None:
                            self.panel.is_streaming = False
                            self.panel._update_session_controls()
                            self.panel.leave_audio_button.setEnabled(False)
                            self.panel.create_audio_button.setEnabled(True)
                            self.panel.join_audio_button.setEnabled(True)
                            self.panel.video_label.setText("Livestream idle\nClick 'Create Livestream' to start or 'Join Livestream' to connect")
                            return
                        if worker._running:
                            worker.stop()
                        if status_mgr is not None:
                            try:
                                status_mgr.update_presence(self.panel._current_username(), False)
                            except Exception:
                                pass
                            try:
                                status_mgr.reset()
                            except Exception:
                                pass
                        if hasattr(self.panel, '_clear_livestream_previews'):
                            try:
                                self.panel._clear_livestream_previews()
                            except Exception:
                                pass
                        self.panel.audio_users_list.clear()
                        self._worker = None
                        self._status_mgr = None
                        self.panel.is_streaming = False
                        self.panel._update_session_controls()
                        self.panel.leave_audio_button.setEnabled(False)
                        self.panel.create_audio_button.setEnabled(True)
                        self.panel.join_audio_button.setEnabled(True)
                        self.panel._append_chat("System", "Video + Audio stream stopped")
                        self.panel.video_label.setText("Livestream idle\nClick 'Create Livestream' to start or 'Join Livestream' to connect")
                    except Exception as e:
                        print(f"Voice stop error: {e}")
                        self.panel._append_chat("System", f"Stream error: {str(e)}")

                self._start_voice = _start_voice
                self._stop_voice = _stop_voice

                # Update peers list display when active users change
                def _update_active_users_list(users):
                    try:
                        # Update the stream users list
                        self.panel.audio_users_list.clear()
                        for user in users:
                            self.panel.audio_users_list.addItem(user)
                        # Also update the peers list to show who's in audio
                        for i in range(self.panel.peers_list.count()):
                            item = self.panel.peers_list.item(i)
                            text = item.text()
                            base = text.replace(" (You)", "").split(" (")[0]
                            is_you = " (You)" in text
                            if base in users:
                                new_text = base + (" (in audio)" if " (in audio)" not in text else "")
                            else:
                                new_text = base
                            if is_you:
                                new_text = new_text + " (You)"
                            if item.text() != new_text:
                                item.setText(new_text)
                        # Update status label
                        if len(users) > 0:
                            self.panel.video_label.setText(f"Livestream active\n{len(users)} user(s) in channel: {', '.join(users)}")
                        else:
                            self.panel.video_label.setText("Livestream idle\nClick 'Create Livestream' to start or 'Join Livestream' to connect")
                    except Exception:
                        pass

                # Attach audio packet handlers to a connection (host or client)
                def _attach_audio_handlers(conn):
                    if not conn:
                        return
                    try:
                        worker = _get_worker()
                        status_mgr = _get_status_mgr()
                        
                        self.panel.voice_manager = worker
                        self.panel.voice_status = status_mgr
                        worker.active_users_changed.connect(_update_active_users_list)
                        worker.frame_ready.connect(self.panel._on_video_frame_ready)
                        
                        def _on_packet(packet):
                            try:
                                if packet.packet_type == PeerCodePacket.TYPE_STREAM_FRAME:
                                    try:
                                        worker.handle_remote_video(packet)
                                    except Exception:
                                        pass
                                elif packet.packet_type == PeerCodePacket.TYPE_AUDIO_CHUNK:
                                    try:
                                        worker.handle_remote_audio(packet)
                                    except Exception:
                                        pass
                                elif packet.packet_type == PeerCodePacket.TYPE_AUDIO_PRESENCE:
                                    data = packet.data or {}
                                    username = data.get("username")
                                    active = data.get("active", False)
                                    try:
                                        status_mgr.update_presence(username, active)
                                        worker._sync_livestream_previews(status_mgr.active_users)
                                    except Exception:
                                        pass
                            except Exception:
                                pass
                        conn.packet_received.connect(_on_packet)
                    except Exception as e:
                        print(f"Audio handler attachment error: {e}")

                # Bind the new Create/Join/Leave buttons
                try:
                    self.panel.create_audio_button.clicked.disconnect()
                except Exception:
                    pass
                self.panel.create_audio_button.clicked.connect(_start_voice)

                try:
                    self.panel.join_audio_button.clicked.disconnect()
                except Exception:
                    pass
                self.panel.join_audio_button.clicked.connect(_start_voice)

                try:
                    self.panel.leave_audio_button.clicked.disconnect()
                except Exception:
                    pass
                self.panel.leave_audio_button.clicked.connect(_stop_voice)

                # Wrap host/join sequence to attach audio handlers after connection
                try:
                    _orig_host_clicked = self.panel._on_host_clicked
                except Exception:
                    _orig_host_clicked = None

                def _host_wrapper():
                    if _orig_host_clicked:
                        _orig_host_clicked()
                    # attach if host created
                    if hasattr(self.panel, 'host') and self.panel.host:
                        _attach_audio_handlers(self.panel.host)

                try:
                    self.panel.host_button.clicked.disconnect()
                except Exception:
                    pass
                self.panel.host_button.clicked.connect(_host_wrapper)

                try:
                    _orig_join_clicked = self.panel._on_join_clicked
                except Exception:
                    _orig_join_clicked = None

                def _join_wrapper():
                    if _orig_join_clicked:
                        _orig_join_clicked()
                    if hasattr(self.panel, 'client') and self.panel.client:
                        _attach_audio_handlers(self.panel.client)

                try:
                    self.panel.join_button.clicked.disconnect()
                except Exception:
                    pass
                self.panel.join_button.clicked.connect(_join_wrapper)

                # Make the panel stop button use the stream shutdown path.
                self.panel._on_create_audio = lambda: _start_voice()
                self.panel._on_join_audio = lambda: _start_voice()
                self.panel._on_leave_audio = lambda: _stop_voice()
                self.panel._on_stop_stream = lambda: _stop_voice()

                # Add a Sync Project button to the visible panel layout
                try:
                    if not hasattr(self.panel, 'sync_button') or self.panel.sync_button is None:
                        sync_btn = qt.QPushButton("Sync Project")
                        sync_btn.setStyleSheet("padding: 4px 8px;")

                        def _on_sync_pressed():
                            try:
                                state = self.get_project_state()
                                files = state.get('files', {})
                                open_file = state.get('open_file')
                                if getattr(self.panel, 'host', None):
                                    pkt = PeerCodePacket(PeerCodePacket.TYPE_SYNC_ALL, {"files": files, "open_file": open_file}, self.panel._current_username())
                                    self.panel.host.send_packet(pkt)
                                    self.panel._append_chat("System", "Project synced to connected peers.")
                                elif getattr(self.panel, 'client', None):
                                    self.panel.client.send_sync_all(files, open_file)
                                    self.panel._append_chat("System", "Sync requested from host.")
                                else:
                                    self.panel._append_chat("System", "No active session to sync.")
                            except Exception as e:
                                print(f"Sync error: {e}")

                        sync_btn.clicked.connect(_on_sync_pressed)
                        self.panel.sync_button = sync_btn

                        # Insert it just before the file operations group if possible
                        try:
                            layout = self.panel.layout()
                            if layout is not None:
                                layout.addWidget(sync_btn)
                        except Exception:
                            pass
                except Exception:
                    pass

            except Exception as e:
                print(f"Voice integration setup failed: {e}")

            # Docking
            self.dock_widget = qt.QDockWidget("PeerCode", main_window)
            self.dock_widget.setWidget(self.panel)
            self.dock_widget.setAllowedAreas(
                qt.Qt.DockWidgetArea.LeftDockWidgetArea | 
                qt.Qt.DockWidgetArea.RightDockWidgetArea
            )
            main_window.addDockWidget(qt.Qt.DockWidgetArea.RightDockWidgetArea, self.dock_widget)
            
            self._connect_to_all_editors()
            data.signal_dispatcher.editor_initialized.connect(self._on_new_editor)
            
            print("PeerCode initialized successfully!")
        except Exception as e:
            print("\nError initializing PeerCode:")
            import traceback
            traceback.print_exc()
    
    def _on_new_editor(self, save_path):
        """Handle new editor being created"""
        import os
        # Add to our mappings
        if save_path:
            remote_path = os.path.basename(save_path)
            self._local_to_remote_path[save_path] = remote_path
            self._remote_to_local_path[remote_path] = save_path
        self._connect_to_all_editors()
    
    def _connect_to_all_editors(self):
        """Connect PeerCode to all existing CustomEditor instances"""
        if not self.main_window:
            return
        
        if hasattr(self.main_window, "get_all_editors"):
            editors = self.main_window.get_all_editors()
            for editor in editors:
                self._connect_to_editor(editor)

    def _get_ot_state(self, remote_path: str):
        if remote_path not in self._ot_states:
            self._ot_states[remote_path] = OTDocumentState()
        return self._ot_states[remote_path]

    def _send_ot_operation(self, op: TextOperation):
        from .network import PeerCodePacket
        packet = PeerCodePacket(PeerCodePacket.TYPE_OT_OPERATION, op.to_dict(), self.panel._current_username())
        if self.panel.host:
            self._get_ot_state(op.remote_path).apply_operation(op)
            self.panel.host.send_packet(packet)
        elif self.panel.client:
            self._get_ot_state(op.remote_path).apply_operation(op)
            self.panel.client.send_packet(packet)
    
    def _connect_to_editor(self, editor):
        """Connect PeerCode to a single CustomEditor"""
        import os
        if editor in self._connected_editors:
            return
        
        local_path = getattr(editor, "save_path", "") or getattr(editor, "file_path", "") or ""
        # Set up mappings
        if local_path:
            remote_path = os.path.basename(local_path)
            self._local_to_remote_path[local_path] = remote_path
            self._remote_to_local_path[remote_path] = local_path
        self._last_text_states[local_path] = editor.text()
        
        if hasattr(editor, "SCN_MODIFIED"):
            editor.SCN_MODIFIED.connect(
                lambda pos, modt, txt, leng, add, ln, fn, fp, tk, ann, e=editor, lp=local_path: 
                    self._on_editor_scn_modified(e, lp, pos, modt, txt, leng)
            )
        
        self._connected_editors.add(editor)
    
    def _on_editor_scn_modified(self, editor, local_path, position, mod_type, text, length):
        import os
        try:
            if not (self.panel and (self.panel.host or self.panel.client)):
                return
            
            if getattr(self.panel, '_ignore_text_changes', False):
                return
            
            # Get remote path for this local file
            remote_path = self._local_to_remote_path.get(local_path, os.path.basename(local_path) if local_path else "")
            
            if mod_type & 0x1:  # SC_MOD_INSERTTEXT
                if text:
                    op = TextOperation(
                        op_type="insert_text",
                        remote_path=remote_path,
                        position=position,
                        text=text,
                        length=0,
                        client_id=self.panel._current_username(),
                        base_version=self._get_ot_state(remote_path).get_version(),
                    )
                    self._send_ot_operation(op)
            elif mod_type & 0x2:  # SC_MOD_DELETETEXT
                self._send_ot_operation(TextOperation(
                    op_type="delete_text",
                    remote_path=remote_path,
                    position=position,
                    text="",
                    length=length,
                    client_id=self.panel._current_username(),
                    base_version=self._get_ot_state(remote_path).get_version(),
                ))
            
            self._last_text_states[local_path] = editor.text()
        except Exception as e:
            print(f"Error in SCN_MODIFIED handler: {e}")
    
    def _send_insert_text(self, remote_path, position, text):
        op = TextOperation(
            op_type="insert_text",
            remote_path=remote_path,
            position=position,
            text=text,
            length=0,
            client_id=self.panel._current_username(),
            base_version=self._get_ot_state(remote_path).get_version(),
        )
        self._send_ot_operation(op)

    def _send_delete_text(self, remote_path, position, length):
        op = TextOperation(
            op_type="delete_text",
            remote_path=remote_path,
            position=position,
            text="",
            length=length,
            client_id=self.panel._current_username(),
            base_version=self._get_ot_state(remote_path).get_version(),
        )
        self._send_ot_operation(op)

    def _apply_ot_operation(self, data: dict):
        try:
            op = TextOperation.from_dict(data)
            if op.client_id == self.panel._current_username():
                return
            state = self._get_ot_state(op.remote_path)
            transformed = state.apply_operation(op)
            if transformed.op_type == "insert_text":
                self.manager.apply_remote_insert(transformed.remote_path, transformed.position, transformed.text)
            elif transformed.op_type == "delete_text":
                self.manager.apply_remote_delete(transformed.remote_path, transformed.position, transformed.length)
        except Exception as e:
            print(f"Error applying OT operation: {e}")
    
    def _on_editor_text_changed(self, editor):
        if getattr(self.panel, '_ignore_text_changes', False):
            return
        
        if (self.panel and (self.panel.host or self.panel.client) and editor):
            from .network import PeerCodePacket
            packet = PeerCodePacket(
                PeerCodePacket.TYPE_FULL_TEXT,
                editor.text()
            )
            if self.panel.host:
                self.panel.host.send_packet(packet)
            elif self.panel.client:
                self.panel.client.send_packet(packet)
    
    def apply_remote_insert(self, remote_path, position, text):
        import os
        print(f"[DEBUG] apply_remote_insert: remote_path={remote_path}, pos={position}, text={repr(text)}")
        editor = self._get_editor_for_file(remote_path)
        if editor:
            try:
                self.panel._ignore_text_changes = True
                editor.insertAt(text, position)
                print(f"[DEBUG] apply_remote_insert: success!")
            finally:
                self.panel._ignore_text_changes = False
        else:
            print(f"[DEBUG] apply_remote_insert: Editor not found for {remote_path}")
    
    def apply_remote_delete(self, remote_path, position, length):
        print(f"[DEBUG] apply_remote_delete: remote_path={remote_path}, pos={position}, length={length}")
        editor = self._get_editor_for_file(remote_path)
        if editor:
            try:
                self.panel._ignore_text_changes = True
                editor.setSelection(position, position + length)
                editor.replaceSelection("")
                print(f"[DEBUG] apply_remote_delete: success!")
            finally:
                self.panel._ignore_text_changes = False
        else:
            print(f"[DEBUG] apply_remote_delete: Editor not found for {remote_path}")
    
    def _get_editor_for_file(self, remote_path):
        """Get editor for a remote file path"""
        import os
        if not self.main_window:
            return None
        
        if remote_path in self._remote_to_local_path:
            local_path = self._remote_to_local_path[remote_path]
            if hasattr(self.main_window, "get_all_editors"):
                editors = self.main_window.get_all_editors()
                for editor in editors:
                    editor_path = getattr(editor, "save_path", "") or getattr(editor, "file_path", "") or ""
                    if editor_path == local_path:
                        return editor
        return None
    
    def apply_sync_all(self, files, open_file=None):
        """Apply sync of all files"""
        import os
        try:
            self.panel._ignore_text_changes = True
            
            for remote_path, content in files.items():
                if remote_path:
                    # Set up the path mappings first
                    if remote_path not in self._remote_to_local_path:
                        local_path = os.path.abspath(remote_path)
                        self._remote_to_local_path[remote_path] = local_path
                        self._local_to_remote_path[local_path] = remote_path
                    
                    editor = self._get_editor_for_file(remote_path)
                    if editor:
                        editor.set_all_text(content)
                    else:
                        # Create file locally first
                        self._create_file_local(self._remote_to_local_path[remote_path], content)
                        # Now open it
                        self.open_file_remote(remote_path, content)
            
            # Try to open the open_file if specified
            if open_file and open_file in files:
                self.open_file_remote(open_file, files.get(open_file, ""))
        finally:
            self.panel._ignore_text_changes = False
    
    def _create_file_local(self, file_path, content=""):
        """Create file locally"""
        try:
            import os
            full_path = os.path.abspath(file_path)
            dir_path = os.path.dirname(full_path)
            
            if dir_path and not os.path.exists(dir_path):
                os.makedirs(dir_path, exist_ok=True)
                
            with open(full_path, 'w', encoding='utf-8') as f:
                f.write(content)
                
        except Exception as e:
            print(f"Error creating file: {e}")
    
    def toggle_panel(self):
        if self.dock_widget:
            try:
                if self.main_window and self.dock_widget not in self.main_window.findChildren(qt.QDockWidget):
                    self.main_window.addDockWidget(qt.Qt.DockWidgetArea.RightDockWidgetArea, self.dock_widget)
            except Exception:
                pass
            self.dock_widget.setVisible(not self.dock_widget.isVisible())
    
    def show_panel(self):
        if self.dock_widget:
            try:
                if self.main_window and self.dock_widget not in self.main_window.findChildren(qt.QDockWidget):
                    self.main_window.addDockWidget(qt.Qt.DockWidgetArea.RightDockWidgetArea, self.dock_widget)
                self.dock_widget.setFloating(False)
                self.dock_widget.show()
                self.dock_widget.raise_()
            except Exception as e:
                print("Error showing PeerCode dock:", e)
    
    def shutdown(self):
        if self.panel:
            if self.panel.host:
                self.panel.host.stop()
            if self.panel.client:
                self.panel.client.disconnect()
        self._connected_editors.clear()
