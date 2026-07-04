

"""
UI Components for PeerCode
Created By Levi Enama
"""

import sys
import os
import socket

# Make sure ExCo is in the path
def _ensure_exco_in_path():
    EXCO_PATH = os.path.join(os.path.dirname(__file__), '..', 'ExCo-master')
    if EXCO_PATH not in sys.path:
        sys.path.insert(0, EXCO_PATH)

_ensure_exco_in_path()

import qt

from .network import PeerCodeHost, PeerCodeClient, PeerCodePacket
from .stream_bridge import StreamBridge, CaptureThread


class PeerCodePanel(qt.QWidget):
    """Dockable panel for PeerCode features"""
    
    def __init__(self, main_window, manager):
        super().__init__()
        self.main_window = main_window
        self.manager = manager
        self.host = None
        self.client = None
        self.peers = []
        self._ignore_text_changes = False
        self._notes_sync_enabled = False
        
        # Configuration
        self.default_host = "127.0.0.1"
        self.default_port = 5000
        
        # Stream bridge
        self.stream_bridge = StreamBridge()
        self.stream_bridge.initialize()
        self.capture_thread = None
        self.is_streaming = False
        self.capture_source = CaptureThread.SOURCE_SCREEN
        self.camera_index = 0
        
        # Shared state
        self.shared_todos = []
        self.shared_snippets = []
        self.presenter_username = ""
        
        self._init_ui()
        
    def _init_ui(self):
        layout = qt.QVBoxLayout(self)
        layout.setContentsMargins(5,5,5,5)
        layout.setSpacing(5)
        
        # Top Controls: Host, Join, Stop, Settings
        top_controls = qt.QHBoxLayout()
        
        self.username_label = qt.QLabel("Username:")
        self.username_edit = qt.QLineEdit()
        self.username_edit.setPlaceholderText("Enter your username")
        self.username_edit.setText("User")
        
        self.host_button = qt.QPushButton("Host Session")
        self.host_button.clicked.connect(self._on_host_clicked)
        
        self.join_button = qt.QPushButton("Join Session")
        self.join_button.clicked.connect(self._on_join_clicked)
        
        self.stop_button = qt.QPushButton("Stop Session")
        self.stop_button.clicked.connect(self._on_stop_clicked)
        self.stop_button.setEnabled(False)
        
        self.settings_button = qt.QPushButton("Settings")
        self.settings_button.clicked.connect(self._on_settings_clicked)
        
        top_controls.addWidget(self.username_label)
        top_controls.addWidget(self.username_edit)
        top_controls.addWidget(self.host_button)
        top_controls.addWidget(self.join_button)
        top_controls.addWidget(self.stop_button)
        top_controls.addWidget(self.settings_button)
        
        layout.addLayout(top_controls)
        
        # Tab Widget for new collaborative features
        self.tabs = qt.QTabWidget()
        
        # 1. Stream & Chat Tab (chat + peers only)
        stream_chat_widget = qt.QWidget()
        stream_chat_layout = qt.QVBoxLayout(stream_chat_widget)

        # Peers list
        peers_group = qt.QGroupBox("Connected Peers")
        peers_layout = qt.QVBoxLayout(peers_group)
        self.peers_list = qt.QListWidget()
        peers_layout.addWidget(self.peers_list)
        stream_chat_layout.addWidget(peers_group)

        # Chat area
        chat_group = qt.QGroupBox("Chat")
        chat_layout = qt.QVBoxLayout(chat_group)
        self.chat_display = qt.QTextEdit()
        self.chat_display.setReadOnly(True)
        chat_layout.addWidget(self.chat_display)

        chat_input_layout = qt.QHBoxLayout()
        self.chat_input = qt.QLineEdit()
        self.chat_input.setPlaceholderText("Type a message...")
        self.chat_input.returnPressed.connect(self._on_send_chat)
        self.chat_input.setEnabled(False)

        self.send_chat_button = qt.QPushButton("Send")
        self.send_chat_button.clicked.connect(self._on_send_chat)
        self.send_chat_button.setEnabled(False)

        chat_input_layout.addWidget(self.chat_input)
        chat_input_layout.addWidget(self.send_chat_button)
        chat_layout.addLayout(chat_input_layout)

        stream_chat_layout.addWidget(chat_group)
        self.tabs.addTab(stream_chat_widget, "Stream & Chat")

        # 2. Live Tab (livestream controls and preview)
        live_widget = qt.QWidget()
        live_layout = qt.QVBoxLayout(live_widget)

        stream_controls = qt.QHBoxLayout()
        self.create_audio_button = qt.QPushButton("Create Livestream")
        self.create_audio_button.clicked.connect(self._on_create_audio)
        self.create_audio_button.setEnabled(False)
        self.join_audio_button = qt.QPushButton("Join Livestream")
        self.join_audio_button.clicked.connect(self._on_join_audio)
        self.join_audio_button.setEnabled(False)
        self.leave_audio_button = qt.QPushButton("Leave Livestream")
        self.leave_audio_button.clicked.connect(self._on_leave_audio)
        self.leave_audio_button.setEnabled(False)
        stream_controls.addWidget(self.create_audio_button)
        stream_controls.addWidget(self.join_audio_button)
        stream_controls.addWidget(self.leave_audio_button)
        live_layout.addLayout(stream_controls)

        audio_users_group = qt.QGroupBox("Users in Livestream")
        audio_users_layout = qt.QVBoxLayout(audio_users_group)
        self.audio_users_list = qt.QListWidget()
        self.audio_users_list.setMaximumHeight(120)
        audio_users_layout.addWidget(self.audio_users_list)
        live_layout.addWidget(audio_users_group)

        preview_group = qt.QGroupBox("Livestream Preview")
        preview_layout = qt.QVBoxLayout(preview_group)
        # Constrain the preview group height so it cannot expand infinitely
        preview_group.setMaximumHeight(520)

        # Grid to host multiple preview containers
        self.livestream_preview_grid = qt.QWidget()
        self.livestream_preview_grid.setStyleSheet("background-color: #111; border: 1px solid #444;")
        self.livestream_preview_layout = qt.QGridLayout(self.livestream_preview_grid)
        self.livestream_preview_layout.setContentsMargins(4, 4, 4, 4)
        self.livestream_preview_layout.setSpacing(4)
        self.preview_labels = {}
        self.preview_placeholder = qt.QLabel("No livestream previews yet")
        self.preview_placeholder.setAlignment(qt.Qt.AlignmentFlag.AlignCenter)
        self.preview_placeholder.setStyleSheet("color: #aaa; padding: 32px;")
        self.livestream_preview_layout.addWidget(self.preview_placeholder, 0, 0)

        # Wrap previews in a scroll area to avoid forcing parent resize
        self._preview_scroll = qt.QScrollArea()
        self._preview_scroll.setWidgetResizable(True)
        self._preview_scroll.setFrameShape(qt.QFrame.Shape.NoFrame)
        self._preview_scroll.setWidget(self.livestream_preview_grid)
        preview_layout.addWidget(self._preview_scroll)
        live_layout.addWidget(preview_group)

        self.video_label = qt.QLabel("Livestream idle\nStart a livestream to join the room")
        self.video_label.setAlignment(qt.Qt.AlignmentFlag.AlignCenter)
        self.video_label.setStyleSheet("background-color: #222; color: #888; padding: 12px; min-height: 70px;")
        self.video_label.setWordWrap(True)
        live_layout.addWidget(self.video_label)

        self.tabs.addTab(live_widget, "Live")
        
        # 2. To-Do & Notes Tab
        todo_notes_widget = qt.QWidget()
        todo_notes_layout = qt.QVBoxLayout(todo_notes_widget)
        
        todo_group = qt.QGroupBox("Shared To-Dos")
        todo_layout = qt.QVBoxLayout(todo_group)
        
        todo_input_layout = qt.QHBoxLayout()
        self.todo_input = qt.QLineEdit()
        self.todo_input.setPlaceholderText("Add a to-do item...")
        self.todo_input.returnPressed.connect(self._on_add_todo)
        
        add_todo_btn = qt.QPushButton("Add")
        add_todo_btn.clicked.connect(self._on_add_todo)
        
        toggle_todo_btn = qt.QPushButton("Toggle Done")
        toggle_todo_btn.clicked.connect(self._on_toggle_todo)
        
        remove_todo_btn = qt.QPushButton("Remove")
        remove_todo_btn.clicked.connect(self._on_remove_todo)
        
        todo_input_layout.addWidget(self.todo_input)
        todo_input_layout.addWidget(add_todo_btn)
        todo_input_layout.addWidget(toggle_todo_btn)
        todo_input_layout.addWidget(remove_todo_btn)
        
        todo_layout.addLayout(todo_input_layout)
        self.todo_list = qt.QListWidget()
        todo_layout.addWidget(self.todo_list)
        
        notes_group = qt.QGroupBox("Shared Notes")
        notes_layout = qt.QVBoxLayout(notes_group)
        self.shared_notes_edit = qt.QTextEdit()
        self.shared_notes_edit.textChanged.connect(self._on_notes_changed)
        notes_layout.addWidget(self.shared_notes_edit)
        
        todo_notes_layout.addWidget(todo_group)
        todo_notes_layout.addWidget(notes_group)
        self.tabs.addTab(todo_notes_widget, "To-Do & Notes")
        
        # 3. Snippets & Find/Replace Tab
        snippets_find_widget = qt.QWidget()
        snippets_find_layout = qt.QVBoxLayout(snippets_find_widget)
        
        snippets_group = qt.QGroupBox("Shared Snippets")
        snippets_layout = qt.QVBoxLayout(snippets_group)
        
        snippet_add_layout = qt.QFormLayout()
        self.snippet_name_edit = qt.QLineEdit()
        self.snippet_code_edit = qt.QTextEdit()
        self.snippet_code_edit.setMaximumHeight(100)
        add_snippet_btn = qt.QPushButton("Add Snippet")
        add_snippet_btn.clicked.connect(self._on_add_snippet)
        remove_snippet_btn = qt.QPushButton("Remove Snippet")
        remove_snippet_btn.clicked.connect(self._on_remove_snippet)
        snippet_add_layout.addRow("Name:", self.snippet_name_edit)
        snippet_add_layout.addRow("Code:", self.snippet_code_edit)
        
        snippets_layout.addLayout(snippet_add_layout)
        snippets_btn_layout = qt.QHBoxLayout()
        snippets_btn_layout.addWidget(add_snippet_btn)
        snippets_btn_layout.addWidget(remove_snippet_btn)
        snippets_layout.addLayout(snippets_btn_layout)
        self.snippets_list = qt.QListWidget()
        snippets_layout.addWidget(self.snippets_list)
        
        find_replace_group = qt.QGroupBox("Shared Find & Replace")
        find_replace_layout = qt.QFormLayout(find_replace_group)
        self.find_edit = qt.QLineEdit()
        self.replace_edit = qt.QLineEdit()
        find_replace_btn = qt.QPushButton("Find & Replace")
        find_replace_btn.clicked.connect(self._on_find_replace)
        find_replace_layout.addRow("Find:", self.find_edit)
        find_replace_layout.addRow("Replace:", self.replace_edit)
        find_replace_layout.addRow(find_replace_btn)
        
        presenter_group = qt.QGroupBox("Presenter Control")
        presenter_layout = qt.QVBoxLayout(presenter_group)
        self.presenter_label = qt.QLabel("Presenter: None")
        take_presenter_btn = qt.QPushButton("Take Presenter")
        take_presenter_btn.clicked.connect(self._on_take_presenter)
        presenter_layout.addWidget(self.presenter_label)
        presenter_layout.addWidget(take_presenter_btn)
        
        snippets_find_layout.addWidget(snippets_group)
        snippets_find_layout.addWidget(find_replace_group)
        snippets_find_layout.addWidget(presenter_group)
        
        self.tabs.addTab(snippets_find_widget, "Snippets & Tools")
        
        # 4. Notifications Tab
        notifications_widget = qt.QWidget()
        notifications_layout = qt.QVBoxLayout(notifications_widget)
        notifications_group = qt.QGroupBox("Notifications")
        notifications_group_layout = qt.QVBoxLayout(notifications_group)
        self.notifications_list = qt.QListWidget()
        notifications_group_layout.addWidget(self.notifications_list)
        notifications_layout.addWidget(notifications_group)
        self.tabs.addTab(notifications_widget, "Notifications")
        
        layout.addWidget(self.tabs)
        
        # File operations (kept for compatibility)
        file_group = qt.QGroupBox("File Operations")
        file_layout = qt.QVBoxLayout(file_group)
        
        file_controls_layout = qt.QHBoxLayout()
        self.new_file_edit = qt.QLineEdit()
        self.new_file_edit.setPlaceholderText("File name...")
        
        self.create_file_button = qt.QPushButton("Create File")
        self.create_file_button.clicked.connect(self._on_create_file)
        self.create_file_button.setEnabled(False)
        
        file_controls_layout.addWidget(self.new_file_edit)
        file_controls_layout.addWidget(self.create_file_button)
        
        file_layout.addLayout(file_controls_layout)
        layout.addWidget(file_group)
        
    def _on_settings_clicked(self):
        dialog = SettingsDialog(self.default_host, self.default_port, self)
        if dialog.exec() == qt.QDialog.DialogCode.Accepted:
            self.default_host = dialog.host_edit.text().strip()
            self.default_port = dialog.port_spin.value()
            self.camera_index = dialog.camera_spin.value()
        
    def _check_host_available(self, host, port):
        """Check if host is already in use"""
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(1.0)
            result = sock.connect_ex((host, port))
            sock.close()
            return result != 0
        except Exception as e:
            return True
    
    def _on_host_clicked(self):
        username = self.username_edit.text().strip()
        if not username:
            qt.QMessageBox.warning(self, "Error", "Please enter a username!")
            return
            
        if not self._check_host_available(self.default_host, self.default_port):
            qt.QMessageBox.warning(
                self, 
                "Host Already in Use", 
                f"Host {self.default_host}:{self.default_port} is already active!"
            )
            return
            
        try:
            self.host = PeerCodeHost(host=self.default_host, port=self.default_port, username=username)
            self.host.peer_connected.connect(self._on_peer_connected)
            self.host.peer_disconnected.connect(self._on_peer_disconnected)
            self.host.packet_received.connect(self._on_packet_received)
            self.host.chat_received.connect(self._on_chat_received)
            self.host.error_occurred.connect(self._on_error)
            self.host.file_operation_received.connect(self._on_file_operation)
            
            self.host.start()
            
            self.peers = [username]
            self.peers_list.clear()
            self.peers_list.addItem(username + " (You)")
            
            self._set_session_active(True)
            self._notes_sync_enabled = True
            self._append_chat("System", f"Session hosted at {self.default_host}:{self.default_port}")
            
        except Exception as e:
            qt.QMessageBox.critical(self, "Error", str(e))
            
    def _on_join_clicked(self):
        username = self.username_edit.text().strip()
        if not username:
            qt.QMessageBox.warning(self, "Error", "Please enter a username!")
            return
            
        dialog = JoinSessionDialog(self.default_host, self.default_port, self)
        if dialog.exec() == qt.QDialog.DialogCode.Accepted:
            host = dialog.host_edit.text().strip()
            port = dialog.port_spin.value()
            
            if self._check_host_available(host, port):
                qt.QMessageBox.warning(
                    self,
                    "Host Not Found",
                    f"Host {host}:{port} is not available!"
                )
                return
            
            try:
                self.client = PeerCodeClient(host, port, username)
                self.client.connected.connect(self._on_client_connected)
                self.client.disconnected.connect(self._on_client_disconnected)
                self.client.packet_received.connect(self._on_packet_received)
                self.client.chat_received.connect(self._on_chat_received)
                self.client.error_occurred.connect(self._on_error)
                self.client.file_operation_received.connect(self._on_file_operation)
                
                self.client.connect()
                
            except Exception as e:
                qt.QMessageBox.critical(self, "Error", str(e))
                
    def _on_stop_clicked(self):
        try:
            self._on_stop_stream()
        except Exception as e:
            print(f"Error stopping stream: {e}")
        
        try:
            if self.host:
                self.host.stop()
                self.host = None
        except Exception as e:
            print(f"Error stopping host: {e}")
            self.host = None
            
        try:
            if self.client:
                self.client.disconnect()
                self.client = None
        except Exception as e:
            print(f"Error disconnecting client: {e}")
            self.client = None
            
        self.peers = []
        self.peers_list.clear()
        self._clear_livestream_previews()
        self.audio_users_list.clear()
        self.is_streaming = False
        self.video_label.setText("Livestream idle\nClick 'Create Livestream' to start or 'Join Livestream' to connect")
        self._set_session_active(False)
        
    def _set_session_active(self, active: bool):
        self.host_button.setEnabled(not active)
        self.join_button.setEnabled(not active)
        self.username_edit.setEnabled(not active)
        self.stop_button.setEnabled(active)
        self._update_session_controls()
        
    def _update_session_controls(self):
        is_session_active = self.host is not None or self.client is not None
        self.create_audio_button.setEnabled(is_session_active and not self.is_streaming)
        self.join_audio_button.setEnabled(is_session_active and not self.is_streaming)
        self.leave_audio_button.setEnabled(self.is_streaming)
        self.create_file_button.setEnabled(is_session_active)
        self.chat_input.setEnabled(is_session_active)
        self.send_chat_button.setEnabled(is_session_active)
        
    def _on_peer_connected(self, username: str):
        self.peers.append(username)
        self.peers_list.addItem(username)
        self._update_session_controls()
        
        # Send full sync of all open files
        if self.host:
            project_state = self.manager.get_project_state()
            packet = PeerCodePacket(
                PeerCodePacket.TYPE_SYNC_ALL,
                {"files": project_state["files"], "open_file": project_state["open_file"]}
            )
            self.host.send_packet(packet, target=username)
                
    def _on_peer_disconnected(self, username: str):
        if username in self.peers:
            self.peers.remove(username)
        for i in range(self.peers_list.count()):
            if self.peers_list.item(i).text() == username:
                self.peers_list.takeItem(i)
                break

        # Remove disconnected users from livestream UI if they were in the audio/video session
        for i in range(self.audio_users_list.count() - 1, -1, -1):
            item_text = self.audio_users_list.item(i).text()
            if item_text == username or item_text.startswith(username + " "):
                self.audio_users_list.takeItem(i)

        if username in self.preview_labels:
            container, _ = self.preview_labels.pop(username)
            container.setParent(None)
            self._layout_livestream_previews()

        self._update_session_controls()
                
    def _on_client_connected(self):
        self._set_session_active(True)
        self._notes_sync_enabled = True
        self._append_chat("System", "Connected to session!")
        
    def _on_client_disconnected(self):
        self._set_session_active(False)
        self._handle_stream_disconnect("The livestream host disconnected.")

    def _handle_stream_disconnect(self, reason="The livestream session ended."):
        try:
            self.is_streaming = False
            self._clear_livestream_previews()
            self.audio_users_list.clear()
            self.video_label.setText("Livestream ended\nThe host left the session.")
            self._append_chat("System", reason)
            if hasattr(self.manager, "voice_status") and self.manager.voice_status is not None:
                try:
                    self.manager.voice_status.reset()
                except Exception:
                    pass
            if hasattr(self.manager, "_stop_voice"):
                qt.QTimer.singleShot(0, self.manager._stop_voice)
        except Exception as e:
            print(f"Stream disconnect cleanup error: {e}")
        
    def _on_packet_received(self, packet: PeerCodePacket):
        print(f"[DEBUG] Received packet: type={packet.packet_type}, sender={packet.sender}")
        if packet.packet_type == PeerCodePacket.TYPE_FULL_TEXT:
            self._apply_full_text(packet.data)
        elif packet.packet_type == PeerCodePacket.TYPE_INSERT_TEXT:
            self._apply_insert_text(packet.data)
        elif packet.packet_type == PeerCodePacket.TYPE_DELETE_TEXT:
            self._apply_delete_text(packet.data)
        elif packet.packet_type == PeerCodePacket.TYPE_PEER_JOIN:
            if isinstance(packet.data, list):
                for peer in packet.data:
                    self._on_peer_connected(peer)
            else:
                self._on_peer_connected(packet.data)
        elif packet.packet_type == PeerCodePacket.TYPE_PEER_LEAVE:
            self._on_peer_disconnected(packet.data)
        elif packet.packet_type == PeerCodePacket.TYPE_CREATE_FILE:
            self._handle_create_file(packet.data)
        elif packet.packet_type == PeerCodePacket.TYPE_SYNC_ALL:
            self._handle_sync_all(packet.data)
        elif packet.packet_type == PeerCodePacket.TYPE_OPEN_FILE:
            self._handle_open_file(packet.data)
        elif packet.packet_type == PeerCodePacket.TYPE_STREAM_FRAME:
            self._handle_stream_frame(packet.data)
        elif packet.packet_type == PeerCodePacket.TYPE_TODO_ADD:
            self._handle_todo_add(packet.data)
        elif packet.packet_type == PeerCodePacket.TYPE_TODO_TOGGLE:
            self._handle_todo_toggle(packet.data)
        elif packet.packet_type == PeerCodePacket.TYPE_TODO_REMOVE:
            self._handle_todo_remove(packet.data)
        elif packet.packet_type == PeerCodePacket.TYPE_NOTIFICATION:
            self._handle_notification(packet.data)
        elif packet.packet_type == PeerCodePacket.TYPE_PRESENTER_CHANGE:
            self._handle_presenter_change(packet.data)
        elif packet.packet_type == PeerCodePacket.TYPE_SNIPPET_ADD:
            self._handle_snippet_add(packet.data)
        elif packet.packet_type == PeerCodePacket.TYPE_SNIPPET_REMOVE:
            self._handle_snippet_remove(packet.data)
        elif packet.packet_type == PeerCodePacket.TYPE_FIND_REPLACE:
            self._handle_find_replace(packet.data)
        elif packet.packet_type == PeerCodePacket.TYPE_CURSOR_POS:
            self._handle_cursor_position(packet.sender, packet.data)
        elif packet.packet_type == PeerCodePacket.TYPE_EDIT_HISTORY:
            self._handle_edit_history(packet.data)
            
    def _apply_full_text(self, text: str):
        editor = self._get_current_editor()
        if editor:
            self._ignore_text_changes = True
            editor.set_all_text(text)
            self._ignore_text_changes = False
    
    def _apply_insert_text(self, data: dict):
        remote_path = data.get("file_path", "")
        position = data.get("position", 0)
        text = data.get("text", "")
        print(f"[DEBUG] Applying insert: remote_path={remote_path}, pos={position}, text={repr(text)}")
        self.manager.apply_remote_insert(remote_path, position, text)
    
    def _apply_delete_text(self, data: dict):
        remote_path = data.get("file_path", "")
        position = data.get("position", 0)
        length = data.get("length", 0)
        print(f"[DEBUG] Applying delete: remote_path={remote_path}, pos={position}, length={length}")
        self.manager.apply_remote_delete(remote_path, position, length)
            
    def _on_chat_received(self, username: str, message: str):
        self._append_chat(username, message)
        
    def _on_error(self, error_msg: str):
        qt.QMessageBox.critical(self, "PeerCode Error", error_msg)
        
    def _on_send_chat(self):
        message = self.chat_input.text().strip()
        if not message:
            return
            
        if self.host:
            self.host.send_chat(message)
        elif self.client:
            self.client.send_chat(message)
            
        self.chat_input.clear()
        
    def _append_chat(self, username: str, message: str):
        self.chat_display.append(f"<b>{username}:</b> {message}")
        
    def _get_current_editor(self):
        if hasattr(self.main_window, "get_all_editors"):
            editors = self.main_window.get_all_editors()
            if editors:
                return editors[0]
        return None
        
    def _on_source_changed(self, index: int):
        if index == 0:
            self.capture_source = CaptureThread.SOURCE_SCREEN
        else:
            self.capture_source = CaptureThread.SOURCE_CAMERA
        
    def _on_create_audio(self):
        """Start video+audio capture and broadcast (host or first join)"""
        if hasattr(self.manager, 'panel') and self.manager.panel is self:
            try:
                self.manager._start_voice()
            except Exception as e:
                print(f"Create stream error: {e}")

    def _on_join_audio(self):
        """Join the video+audio stream session"""
        if hasattr(self.manager, 'panel') and self.manager.panel is self:
            try:
                self.manager._start_voice()
            except Exception as e:
                print(f"Join stream error: {e}")

    def _on_leave_audio(self):
        """Leave video+audio stream"""
        if hasattr(self.manager, 'panel') and self.manager.panel is self:
            try:
                self.manager._stop_voice()
            except Exception as e:
                print(f"Leave stream error: {e}")

    def _on_start_stream(self):
        """Legacy handler (kept for compatibility)"""
        self._on_create_audio()

    def _on_stop_stream(self):
        """Legacy handler (kept for compatibility)"""
        self._on_leave_audio()

    def _on_video_frame_ready(self, frame_data, width, height, sender):
        """Display a received video frame in the livestream preview grid."""
        try:
            frame_bytes = bytes(frame_data)
            if not frame_bytes:
                return
            image = qt.QImage(frame_bytes, width, height, width * 3, qt.QImage.Format.Format_RGB888)
            pixmap = qt.QPixmap.fromImage(image)
            if sender not in self.preview_labels:
                label = qt.QLabel()
                label.setAlignment(qt.Qt.AlignmentFlag.AlignCenter)
                label.setStyleSheet("background-color: #000; border: 1px solid #333;")
                label.setMinimumSize(160, 120)
                label.setMaximumSize(640, 480)
                title = qt.QLabel(sender)
                title.setAlignment(qt.Qt.AlignmentFlag.AlignCenter)
                title.setStyleSheet("color: #eee; font-weight: bold;")
                container = qt.QWidget()
                container_layout = qt.QVBoxLayout(container)
                container_layout.setContentsMargins(2, 2, 2, 2)
                container_layout.setSpacing(2)
                container_layout.addWidget(title)
                container_layout.addWidget(label)
                container.setSizePolicy(qt.QSizePolicy.Policy.Preferred, qt.QSizePolicy.Policy.Preferred)
                self.preview_labels[sender] = (container, label)
                self.preview_placeholder.hide()
            else:
                container, label = self.preview_labels[sender]

            target_width = max(160, (self._preview_scroll.viewport().width() // max(1, int(len(self.preview_labels) ** 0.5))) - 8)
            target_height = max(120, (self._preview_scroll.viewport().height() // max(1, int((len(self.preview_labels) + 1) ** 0.5))) - 8)
            label.setPixmap(pixmap.scaled(target_width, target_height, qt.Qt.AspectRatioMode.KeepAspectRatio, qt.Qt.TransformationMode.SmoothTransformation))
            self._layout_livestream_previews()
        except Exception as e:
            print(f"Video frame display error: {e}")

    def _layout_livestream_previews(self):
        count = len(self.preview_labels)
        if count == 0:
            self.preview_placeholder.show()
            return
        cols = int(count ** 0.5)
        if cols * cols < count:
            cols += 1
        rows = (count + cols - 1) // cols
        # Remove all widgets from the layout before re-placing them
        while self.livestream_preview_layout.count():
            item = self.livestream_preview_layout.takeAt(0)
            if item and item.widget():
                item.widget().setParent(None)
        self.preview_placeholder.hide()
        index = 0
        for sender, (container, _) in self.preview_labels.items():
            r = index // cols
            c = index % cols
            self.livestream_preview_layout.addWidget(container, r, c)
            index += 1

    def _sync_livestream_previews(self, active_users):
        removed = [sender for sender in self.preview_labels if sender not in active_users]
        for sender in removed:
            container, _ = self.preview_labels.pop(sender)
            container.setParent(None)
        self._layout_livestream_previews()

    def _clear_livestream_previews(self):
        for sender, (container, _) in self.preview_labels.items():
            container.setParent(None)
        self.preview_labels.clear()
        while self.livestream_preview_layout.count():
            item = self.livestream_preview_layout.takeAt(0)
            if item and item.widget():
                item.widget().setParent(None)
        self.preview_placeholder.show()
        self.livestream_preview_layout.addWidget(self.preview_placeholder, 0, 0)
        
    def _on_frame_ready(self, frame_data, width, height):
        try:
            import base64
            image = qt.QImage(frame_data, width, height, qt.QImage.Format.Format_RGBA8888)
            pixmap = qt.QPixmap.fromImage(image)
            scaled = pixmap.scaled(self.video_label.size(), qt.Qt.AspectRatioMode.KeepAspectRatio)
            self.video_label.setPixmap(scaled)
            
            if self.host or self.client:
                encoded_frame = base64.b64encode(frame_data).decode('utf-8')
                packet = PeerCodePacket(
                    PeerCodePacket.TYPE_STREAM_FRAME,
                    {"frame_data": encoded_frame, "width": width, "height": height}
                )
                if self.host:
                    self.host.send_packet(packet)
                elif self.client:
                    self.client.send_packet(packet)
        except Exception as e:
            print(f"Frame display error: {e}")
            
    def _on_stream_error(self, error_msg):
        qt.QMessageBox.warning(self, "Stream Error", error_msg)
        
    # File operations
    def _on_create_file(self):
        file_name = self.new_file_edit.text().strip()
        if not file_name:
            qt.QMessageBox.warning(self, "Error", "Please enter a file name!")
            return
            
        if self.client:
            self.client.send_create_file(file_name)
        elif self.host:
            self._create_file_local(file_name)
            self.main_window.open_file(os.path.abspath(file_name))
            packet = PeerCodePacket(PeerCodePacket.TYPE_CREATE_FILE, {"file_path": file_name, "content": ""})
            self.host.send_packet(packet)
            
        self.new_file_edit.clear()
        self._append_chat("System", f"Creating file: {file_name}")
        
    def _on_file_operation(self, op_type, data):
        if op_type == PeerCodePacket.TYPE_CREATE_FILE:
            self._handle_create_file(data)
            
    def _handle_create_file(self, data):
        file_path = data.get("file_path", "")
        content = data.get("content", "")
        
        self._create_file_local(file_path, content)
        self.main_window.open_file(os.path.abspath(file_path))
            
        self._append_chat("System", f"File created: {file_path}")
        
    def _create_file_local(self, file_path, content=""):
        try:
            full_path = os.path.abspath(file_path)
            dir_path = os.path.dirname(full_path)
            
            if dir_path and not os.path.exists(dir_path):
                os.makedirs(dir_path, exist_ok=True)
                
            with open(full_path, 'w', encoding='utf-8') as f:
                f.write(content)
                
        except Exception as e:
            print(f"Error creating file: {e}")
    
    def _handle_sync_all(self, data: dict):
        files = data.get("files", {})
        open_file = data.get("open_file")
        self.manager.apply_sync_all(files, open_file)
    
    def _handle_open_file(self, data: dict):
        file_path = data.get("file_path", "")
        content = data.get("content", "")
        self.manager.open_file_remote(file_path, content)
    
    def _handle_stream_frame(self, data: dict):
        import base64
        try:
            encoded_frame = data.get("frame_data", "")
            width = data.get("width", 640)
            height = data.get("height", 480)
            frame_data = base64.b64decode(encoded_frame)
            image = qt.QImage(frame_data, width, height, qt.QImage.Format.Format_RGBA8888)
            pixmap = qt.QPixmap.fromImage(image)
            scaled = pixmap.scaled(self.video_label.size(), qt.Qt.AspectRatioMode.KeepAspectRatio)
            self.video_label.setPixmap(scaled)
        except Exception as e:
            print(f"Stream frame error: {e}")
            
    # --- New collaborative handlers ---
    
    def _broadcast_packet(self, packet):
        if self.host:
            self.host.send_packet(packet)
        elif self.client:
            self.client.send_packet(packet)
            
    def _push_notification(self, title: str, message: str, broadcast: bool = False):
        entry = f"{title}: {message}"
        self.notifications_list.insertItem(0, entry)
        if broadcast:
            packet = PeerCodePacket(
                PeerCodePacket.TYPE_NOTIFICATION,
                {"title": title, "message": message}
            )
            self._broadcast_packet(packet)
            
    def _current_username(self):
        return self.username_edit.text().strip() or "User"
        
    def _on_add_todo(self):
        text = self.todo_input.text().strip()
        if not text:
            return
        data = {"text": text, "done": False, "author": self._current_username()}
        self._handle_todo_add(data)
        self._broadcast_packet(PeerCodePacket(PeerCodePacket.TYPE_TODO_ADD, data))
        self.todo_input.clear()
        
    def _on_toggle_todo(self):
        row = self.todo_list.currentRow()
        if row < 0:
            return
        data = {"index": row}
        self._handle_todo_toggle(data)
        self._broadcast_packet(PeerCodePacket(PeerCodePacket.TYPE_TODO_TOGGLE, data))
        
    def _on_remove_todo(self):
        row = self.todo_list.currentRow()
        if row < 0:
            return
        data = {"index": row}
        self._handle_todo_remove(data)
        self._broadcast_packet(PeerCodePacket(PeerCodePacket.TYPE_TODO_REMOVE, data))
        
    def _on_notes_changed(self):
        if self._ignore_text_changes or not self._notes_sync_enabled:
            return
        packet = PeerCodePacket(
            PeerCodePacket.TYPE_NOTIFICATION,
            {"title": "Notes Updated", "message": f"Shared notes updated by {self._current_username()}"}
        )
        self._broadcast_packet(packet)
        
    def _on_add_snippet(self):
        name = self.snippet_name_edit.text().strip()
        code = self.snippet_code_edit.toPlainText().strip()
        if not name or not code:
            return
        data = {"name": name, "code": code, "author": self._current_username()}
        self._handle_snippet_add(data)
        self._broadcast_packet(PeerCodePacket(PeerCodePacket.TYPE_SNIPPET_ADD, data))
        self.snippet_name_edit.clear()
        self.snippet_code_edit.clear()
        
    def _on_remove_snippet(self):
        row = self.snippets_list.currentRow()
        if row < 0:
            return
        data = {"index": row}
        self._handle_snippet_remove(data)
        self._broadcast_packet(PeerCodePacket(PeerCodePacket.TYPE_SNIPPET_REMOVE, data))
        
    def _on_find_replace(self):
        find_text = self.find_edit.text()
        replace_text = self.replace_edit.text()
        if not find_text:
            return
        data = {"find_text": find_text, "replace_text": replace_text}
        self._handle_find_replace(data)
        self._broadcast_packet(PeerCodePacket(PeerCodePacket.TYPE_FIND_REPLACE, data))
        
    def _on_take_presenter(self):
        username = self._current_username()
        data = {"username": username}
        self._handle_presenter_change(data)
        self._broadcast_packet(PeerCodePacket(PeerCodePacket.TYPE_PRESENTER_CHANGE, data))
        
    def _handle_todo_add(self, data):
        item = {
            "text": data.get("text", ""),
            "done": bool(data.get("done", False)),
            "author": data.get("author", "User"),
        }
        self.shared_todos.append(item)
        prefix = "[x]" if item["done"] else "[ ]"
        self.todo_list.addItem(f'{prefix} {item["text"]} ({item["author"]})')
        
    def _handle_todo_toggle(self, data):
        index = data.get("index", -1)
        if 0 <= index < len(self.shared_todos):
            self.shared_todos[index]["done"] = not self.shared_todos[index]["done"]
            item = self.shared_todos[index]
            prefix = "[x]" if item["done"] else "[ ]"
            self.todo_list.item(index).setText(f'{prefix} {item["text"]} ({item["author"]})')
            
    def _handle_todo_remove(self, data):
        index = data.get("index", -1)
        if 0 <= index < len(self.shared_todos):
            self.shared_todos.pop(index)
            self.todo_list.takeItem(index)
            
    def _handle_notification(self, data):
        self._push_notification(data.get("title", "Info"), data.get("message", ""), broadcast=False)
        
    def _handle_presenter_change(self, data):
        username = data.get("username", "")
        self.presenter_username = username
        self.presenter_label.setText(f"Presenter: {username or 'None'}")
        if username:
            self._push_notification("Presenter", f"{username} is now presenting", broadcast=False)
            
    def _handle_snippet_add(self, data):
        snippet = {
            "name": data.get("name", "Snippet"),
            "code": data.get("code", ""),
            "author": data.get("author", "User"),
        }
        self.shared_snippets.append(snippet)
        self.snippets_list.addItem(f'{snippet["name"]} ({snippet["author"]})')
        
    def _handle_snippet_remove(self, data):
        index = data.get("index", -1)
        if 0 <= index < len(self.shared_snippets):
            self.shared_snippets.pop(index)
            self.snippets_list.takeItem(index)
            
    def _handle_find_replace(self, data):
        find_text = data.get("find_text", "")
        replace_text = data.get("replace_text", "")
        if not find_text:
            return
        editor = self._get_current_editor()
        if editor:
            self._ignore_text_changes = True
            current_text = editor.text()
            new_text = current_text.replace(find_text, replace_text)
            editor.set_all_text(new_text)
            self._ignore_text_changes = False
            
    def _handle_cursor_position(self, sender, data):
        print(f"[DEBUG] Received cursor position from {sender}: {data}")
        
    def _handle_edit_history(self, data):
        print(f"[DEBUG] Received edit history: {data}")


class JoinSessionDialog(qt.QDialog):
    """Dialog for joining a PeerCode session"""
    
    def __init__(self, default_host, default_port, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Join PeerCode Session")
        self.setModal(True)
        
        layout = qt.QFormLayout(self)
        
        self.host_edit = qt.QLineEdit()
        self.host_edit.setText(default_host)
        
        self.port_spin = qt.QSpinBox()
        self.port_spin.setRange(1, 65535)
        self.port_spin.setValue(default_port)
        
        layout.addRow("Host:", self.host_edit)
        layout.addRow("Port:", self.port_spin)
        
        buttons = qt.QDialogButtonBox(
            qt.QDialogButtonBox.StandardButton.Ok | 
            qt.QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        
        layout.addRow(buttons)


class SettingsDialog(qt.QDialog):
    """Settings dialog for PeerCode"""
    
    def __init__(self, default_host, default_port, parent=None):
        super().__init__(parent)
        self.setWindowTitle("PeerCode Settings")
        self.setModal(True)
        
        layout = qt.QFormLayout(self)
        
        self.host_edit = qt.QLineEdit()
        self.host_edit.setText(default_host)
        
        self.port_spin = qt.QSpinBox()
        self.port_spin.setRange(1, 65535)
        self.port_spin.setValue(default_port)
        
        self.camera_spin = qt.QSpinBox()
        self.camera_spin.setRange(0, 10)
        self.camera_spin.setValue(0)
        
        layout.addRow("Default Host:", self.host_edit)
        layout.addRow("Default Port:", self.port_spin)
        layout.addRow("Camera Index:", self.camera_spin)
        
        buttons = qt.QDialogButtonBox(
            qt.QDialogButtonBox.StandardButton.Ok | 
            qt.QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        
        layout.addRow(buttons)

