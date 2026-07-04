

"""
Networking module for PeerCode - host/server and client implementations
Created By Levi Enama
"""

import socket
import threading
import json
from typing import Dict, Optional, Any

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'ExCo-master'))
import qt


class PeerCodePacket:
    """Packet structure for PeerCode communication"""
    
    TYPE_TEXT_CHANGE = "text_change"
    TYPE_FULL_TEXT = "full_text"
    TYPE_CHAT = "chat"
    TYPE_PEER_JOIN = "peer_join"
    TYPE_PEER_LEAVE = "peer_leave"
    TYPE_CURSOR_POSITION = "cursor_position"
    TYPE_INIT = "init"
    TYPE_INSERT_TEXT = "insert_text"
    TYPE_DELETE_TEXT = "delete_text"
    TYPE_CREATE_FILE = "create_file"
    TYPE_DELETE_FILE = "delete_file"
    TYPE_RENAME_FILE = "rename_file"
    TYPE_FILE_TREE = "file_tree"
    TYPE_OPEN_FILE = "open_file"
    TYPE_PROJECT_STATE = "project_state"
    TYPE_SYNC_ALL = "sync_all"
    TYPE_STREAM_FRAME = "stream_frame"
    # Audio stream packet types
    TYPE_AUDIO_CHUNK = "audio_chunk"
    TYPE_AUDIO_PRESENCE = "audio_presence"
    # New features
    TYPE_CURSOR_POS = "cursor_pos"
    TYPE_TODO_ADD = "todo_add"
    TYPE_TODO_REMOVE = "todo_remove"
    TYPE_TODO_TOGGLE = "todo_toggle"
    TYPE_NOTIFICATION = "notification"
    TYPE_PRESENTER_CHANGE = "presenter_change"
    TYPE_SNIPPET_ADD = "snippet_add"
    TYPE_SNIPPET_REMOVE = "snippet_remove"
    TYPE_FIND_REPLACE = "find_replace"
    TYPE_EDIT_HISTORY = "edit_history"
    TYPE_ACCESS_CHANGE = "access_change"
    TYPE_OT_OPERATION = "ot_operation"
    
    def __init__(self, packet_type, data, sender="unknown"):
        self.packet_type = packet_type
        self.data = data
        self.sender = sender
        self.seq = None
    
    def to_bytes(self):
        """Serialize packet to bytes"""
        packet_dict = {
            "type": self.packet_type,
            "data": self.data,
            "sender": self.sender
        }
        if self.seq is not None:
            packet_dict["seq"] = int(self.seq)
        json_str = json.dumps(packet_dict, ensure_ascii=False)
        length_bytes = len(json_str).to_bytes(4, byteorder='big')
        return length_bytes + json_str.encode('utf-8')
    
    @classmethod
    def from_bytes(cls, data):
        """Deserialize bytes to packet"""
        try:
            packet_dict = json.loads(data.decode('utf-8'))
            obj = cls(
                packet_type=packet_dict["type"],
                data=packet_dict["data"],
                sender=packet_dict.get("sender", "unknown")
            )
            if "seq" in packet_dict:
                try:
                    obj.seq = int(packet_dict["seq"])
                except Exception:
                    obj.seq = None
            return obj
        except Exception as e:
            print(f"Error deserializing packet: {e}")
            return None


def recv_exact(sock, n):
    """Receive exactly n bytes from socket or return None if EOF."""
    buf = bytearray()
    while len(buf) < n:
        try:
            chunk = sock.recv(n - len(buf))
        except Exception as e:
            # Error on recv
            return None
        if not chunk:
            return None
        buf.extend(chunk)
    return bytes(buf)


class PeerCodeHost(qt.QObject):
    """Host/server for PeerCode sessions"""
    
    peer_connected = qt.pyqtSignal(str)
    peer_disconnected = qt.pyqtSignal(str)
    packet_received = qt.pyqtSignal(object)
    chat_received = qt.pyqtSignal(str, str)
    error_occurred = qt.pyqtSignal(str)
    file_operation_received = qt.pyqtSignal(str, object)
    
    def __init__(self, host="0.0.0.0", port=5000, username="Host"):
        super().__init__()
        self.host = host
        self.port = port
        self.username = username
        self.server_socket = None
        self.clients = {}
        self.running = False
        self.accept_thread = None
        self._seq_counter = 1
        
    def start(self):
        """Start the server"""
        try:
            self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.server_socket.bind((self.host, self.port))
            self.server_socket.listen(5)
            self.running = True
            self.accept_thread = threading.Thread(target=self._accept_clients, daemon=True)
            self.accept_thread.start()
            print(f"PeerCode Host started on {self.host}:{self.port}")
        except Exception as e:
            self.error_occurred.emit(f"Failed to start host: {str(e)}")
            raise
            
    def _accept_clients(self):
        while self.running:
            try:
                if self.server_socket is None:
                    break
                self.server_socket.settimeout(1.0)
                try:
                    client_socket, client_address = self.server_socket.accept()
                    client_socket.settimeout(None)
                    client_thread = threading.Thread(
                        target=self._handle_client,
                        args=(client_socket,),
                        daemon=True
                    )
                    client_thread.start()
                except socket.timeout:
                    continue
            except Exception as e:
                if self.running:
                    self.error_occurred.emit(f"Error accepting client: {str(e)}")
                    
    def _handle_client(self, client_socket):
        username = "unknown"
        try:
            print("[DEBUG] Host: Waiting for init packet from client...")
            header = recv_exact(client_socket, 4)
            if not header or len(header) != 4:
                return
            length = int.from_bytes(header, byteorder='big')
            data = recv_exact(client_socket, length)
            if not data:
                return
            packet = PeerCodePacket.from_bytes(data)
            
            if packet and packet.packet_type == PeerCodePacket.TYPE_INIT:
                username = packet.data
                print(f"[DEBUG] Host: Received init packet from user {username}")
                self.clients[username] = client_socket
                self.peer_connected.emit(username)
                self._broadcast(PeerCodePacket(PeerCodePacket.TYPE_PEER_JOIN, username, self.username))
                peers = [self.username] + list(self.clients.keys())
                peers.remove(username)
                client_socket.sendall(PeerCodePacket(PeerCodePacket.TYPE_PEER_JOIN, peers, self.username).to_bytes())
                
            while self.running:
                header = recv_exact(client_socket, 4)
                if not header or len(header) != 4:
                    break
                length = int.from_bytes(header, byteorder='big')
                data = recv_exact(client_socket, length)
                if not data:
                    break
                packet = PeerCodePacket.from_bytes(data)
                if packet:
                    packet.sender = username
                    print(f"[DEBUG] Host: Received from {username}: type={packet.packet_type}")
                    self.packet_received.emit(packet)

                    if packet.packet_type == PeerCodePacket.TYPE_CHAT:
                        self.chat_received.emit(username, packet.data)
                        self._broadcast(packet)
                    elif packet.packet_type == PeerCodePacket.TYPE_CREATE_FILE:
                        self.file_operation_received.emit(packet.packet_type, packet.data)
                        self._broadcast(packet)
                    elif packet.packet_type == PeerCodePacket.TYPE_OT_OPERATION:
                        # OT operations are rebroadcast for all peers.
                        print(f"[DEBUG] Host: Rebroadcasting OT operation from {username}")
                        packet.seq = self._seq_counter
                        self._seq_counter += 1
                        self._broadcast(packet)
                    elif packet.packet_type in [
                        PeerCodePacket.TYPE_INSERT_TEXT,
                        PeerCodePacket.TYPE_DELETE_TEXT,
                        PeerCodePacket.TYPE_OT_OPERATION,
                        PeerCodePacket.TYPE_STREAM_FRAME,
                        PeerCodePacket.TYPE_AUDIO_CHUNK,
                        PeerCodePacket.TYPE_AUDIO_PRESENCE,
                        PeerCodePacket.TYPE_CURSOR_POS,
                        PeerCodePacket.TYPE_TODO_ADD,
                        PeerCodePacket.TYPE_TODO_REMOVE,
                        PeerCodePacket.TYPE_TODO_TOGGLE,
                        PeerCodePacket.TYPE_NOTIFICATION,
                        PeerCodePacket.TYPE_PRESENTER_CHANGE,
                        PeerCodePacket.TYPE_SNIPPET_ADD,
                        PeerCodePacket.TYPE_SNIPPET_REMOVE,
                        PeerCodePacket.TYPE_FIND_REPLACE,
                        PeerCodePacket.TYPE_EDIT_HISTORY,
                        PeerCodePacket.TYPE_ACCESS_CHANGE
                    ]:
                        print(f"[DEBUG] Host: Broadcasting {packet.packet_type} from {username}")
                        # assign sequence number for ordering
                        packet.seq = self._seq_counter
                        self._seq_counter += 1
                        self._broadcast(packet)
                        
        except Exception as e:
            if self.running:
                print(f"Error handling client {username}: {e}")
                import traceback
                traceback.print_exc()
        finally:
            if username in self.clients:
                del self.clients[username]
                self.peer_disconnected.emit(username)
                self._broadcast(PeerCodePacket(PeerCodePacket.TYPE_PEER_LEAVE, username, self.username))
            try:
                client_socket.close()
            except:
                pass
                
    def _broadcast(self, packet):
        """Send packet to all connected clients"""
        print(f"[DEBUG] Host: Broadcasting packet: type={packet.packet_type} to {len(self.clients)} clients")
        for username, client_socket in list(self.clients.items()):
            try:
                client_socket.sendall(packet.to_bytes())
            except Exception as e:
                print(f"Error sending to {username}: {e}")
                
    def send_packet(self, packet, target=None):
        """Send packet to specific target or all clients"""
        print(f"[DEBUG] Host: Sending packet: type={packet.packet_type}, target={target}")
        if target:
            if target in self.clients:
                try:
                    # assign sequence if broadcasting from host
                    if packet.seq is None:
                        packet.seq = self._seq_counter
                        self._seq_counter += 1
                    self.clients[target].sendall(packet.to_bytes())
                except Exception as e:
                    print(f"Error sending to {target}: {e}")
        else:
            if packet.seq is None:
                packet.seq = self._seq_counter
                self._seq_counter += 1
            self._broadcast(packet)
            
    def send_chat(self, message):
        """Send chat message from host"""
        packet = PeerCodePacket(PeerCodePacket.TYPE_CHAT, message, self.username)
        self.chat_received.emit(self.username, message)
        self._broadcast(packet)
        
    def stop(self):
        """Stop the server"""
        self.running = False
        
        for username, client_socket in list(self.clients.items()):
            try:
                client_socket.close()
            except:
                pass
        self.clients.clear()
        
        if self.server_socket:
            try:
                self.server_socket.close()
            except:
                pass
            self.server_socket = None
            
        if self.accept_thread and self.accept_thread.is_alive():
            self.accept_thread.join(timeout=2.0)
            
        print("PeerCode Host stopped")


class PeerCodeClient(qt.QObject):
    """Client for PeerCode sessions"""
    
    connected = qt.pyqtSignal()
    disconnected = qt.pyqtSignal()
    packet_received = qt.pyqtSignal(object)
    chat_received = qt.pyqtSignal(str, str)
    error_occurred = qt.pyqtSignal(str)
    file_operation_received = qt.pyqtSignal(str, object)
    
    def __init__(self, host="127.0.0.1", port=5000, username="Client"):
        super().__init__()
        self.host = host
        self.port = port
        self.username = username
        self.socket = None
        self.running = False
        self.receive_thread = None
        
    def connect(self):
        """Connect to the host"""
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.connect((self.host, self.port))
            self.running = True
            
            # Send init packet
            init_packet = PeerCodePacket(PeerCodePacket.TYPE_INIT, self.username)
            self.socket.sendall(init_packet.to_bytes())
            
            self.receive_thread = threading.Thread(target=self._receive_loop, daemon=True)
            self.receive_thread.start()
            
            self.connected.emit()
            print(f"Connected to PeerCode Host at {self.host}:{self.port}")
            
        except Exception as e:
            self.error_occurred.emit(f"Failed to connect: {str(e)}")
            raise
            
    def _receive_loop(self):
        print("[DEBUG] Client: Starting receive loop...")
        while self.running:
            try:
                header = recv_exact(self.socket, 4)
                if not header or len(header) != 4:
                    break
                length = int.from_bytes(header, byteorder='big')
                data = recv_exact(self.socket, length)
                if not data or len(data) != length:
                    break

                packet = PeerCodePacket.from_bytes(data)
                if packet:
                    print(f"[DEBUG] Client: Received packet: type={packet.packet_type}, sender={packet.sender}")
                    self.packet_received.emit(packet)

                    if packet.packet_type == PeerCodePacket.TYPE_CHAT:
                        self.chat_received.emit(packet.sender, packet.data)
                    elif packet.packet_type in [
                        PeerCodePacket.TYPE_CREATE_FILE,
                        PeerCodePacket.TYPE_DELETE_FILE,
                        PeerCodePacket.TYPE_RENAME_FILE
                    ]:
                        self.file_operation_received.emit(packet.packet_type, packet.data)

            except Exception as e:
                if self.running:
                    print(f"Receive error: {e}")
                    import traceback
                    traceback.print_exc()
                break

        self.disconnect()
        
    def send_packet(self, packet):
        """Send a packet to the host"""
        print(f"[DEBUG] Client: Sending packet: type={packet.packet_type}")
        try:
            if self.socket:
                packet.sender = self.username
                self.socket.sendall(packet.to_bytes())
        except Exception as e:
            self.error_occurred.emit(f"Failed to send packet: {str(e)}")
            import traceback
            traceback.print_exc()
            
    def send_chat(self, message):
        """Send chat message"""
        packet = PeerCodePacket(PeerCodePacket.TYPE_CHAT, message, self.username)
        self.send_packet(packet)
        
    def send_insert_text(self, position, text, file_path=""):
        """Send text insertion"""
        packet = PeerCodePacket(
            PeerCodePacket.TYPE_INSERT_TEXT,
            {"position": position, "text": text, "file_path": file_path}
        )
        self.send_packet(packet)
        
    def send_delete_text(self, position, length, file_path=""):
        """Send text deletion"""
        packet = PeerCodePacket(
            PeerCodePacket.TYPE_DELETE_TEXT,
            {"position": position, "length": length, "file_path": file_path}
        )
        self.send_packet(packet)
        
    def send_create_file(self, file_path, content=""):
        """Send file creation"""
        packet = PeerCodePacket(
            PeerCodePacket.TYPE_CREATE_FILE,
            {"file_path": file_path, "content": content}
        )
        self.send_packet(packet)
    
    def send_open_file(self, file_path, content=""):
        """Send open file request"""
        packet = PeerCodePacket(
            PeerCodePacket.TYPE_OPEN_FILE,
            {"file_path": file_path, "content": content}
        )
        self.send_packet(packet)
    
    def send_sync_all(self, files, open_file=None):
        """Send full sync (all files)"""
        packet = PeerCodePacket(
            PeerCodePacket.TYPE_SYNC_ALL,
            {"files": files, "open_file": open_file}
        )
        self.send_packet(packet)
    
    def send_project_state(self, files, open_file=None):
        """Send project state"""
        packet = PeerCodePacket(
            PeerCodePacket.TYPE_PROJECT_STATE,
            {"files": files, "open_file": open_file}
        )
        self.send_packet(packet)
        
    def disconnect(self):
        """Disconnect from the host"""
        self.running = False
        
        if self.socket:
            try:
                self.socket.close()
            except:
                pass
            self.socket = None
            
        if self.receive_thread and self.receive_thread.is_alive():
            self.receive_thread.join(timeout=2.0)
            
        self.disconnected.emit()
        print("Disconnected from PeerCode Host")

