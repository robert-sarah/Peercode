"""Operational Transformation helper for text edits in PeerCode."""

import uuid
from typing import Dict, List, Any


class TextOperation:
    def __init__(
        self,
        op_type: str,
        remote_path: str,
        position: int,
        text: str = "",
        length: int = 0,
        client_id: str = "",
        base_version: int = 0,
        op_id: str = None,
    ):
        self.op_type = op_type
        self.remote_path = remote_path
        self.position = position
        self.text = text
        self.length = length
        self.client_id = client_id
        self.base_version = base_version
        self.op_id = op_id or str(uuid.uuid4())
        self.version = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "op_type": self.op_type,
            "remote_path": self.remote_path,
            "position": self.position,
            "text": self.text,
            "length": self.length,
            "client_id": self.client_id,
            "base_version": self.base_version,
            "op_id": self.op_id,
            "version": self.version,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]):
        op = cls(
            op_type=data.get("op_type", ""),
            remote_path=data.get("remote_path", ""),
            position=int(data.get("position", 0)),
            text=data.get("text", ""),
            length=int(data.get("length", 0)),
            client_id=data.get("client_id", ""),
            base_version=int(data.get("base_version", 0)),
            op_id=data.get("op_id"),
        )
        op.version = data.get("version")
        return op


def transform_operation(local_op: TextOperation, remote_op: TextOperation) -> TextOperation:
    """Transform local_op against remote_op and return a new operation."""
    if local_op.remote_path != remote_op.remote_path:
        return local_op

    op = TextOperation(
        op_type=local_op.op_type,
        remote_path=local_op.remote_path,
        position=local_op.position,
        text=local_op.text,
        length=local_op.length,
        client_id=local_op.client_id,
        base_version=local_op.base_version,
        op_id=local_op.op_id,
    )

    if local_op.op_type == "insert_text" and remote_op.op_type == "insert_text":
        if remote_op.position < op.position or (remote_op.position == op.position and remote_op.client_id < op.client_id):
            op.position += len(remote_op.text)
    elif local_op.op_type == "insert_text" and remote_op.op_type == "delete_text":
        if remote_op.position < op.position:
            op.position = max(remote_op.position, op.position - remote_op.length)
    elif local_op.op_type == "delete_text" and remote_op.op_type == "insert_text":
        if remote_op.position <= op.position:
            op.position += len(remote_op.text)
        elif remote_op.position < op.position + op.length:
            op.length += len(remote_op.text)
    elif local_op.op_type == "delete_text" and remote_op.op_type == "delete_text":
        if remote_op.position >= op.position + op.length:
            pass
        elif remote_op.position + remote_op.length <= op.position:
            op.position -= remote_op.length
        else:
            overlap_start = max(op.position, remote_op.position)
            overlap_end = min(op.position + op.length, remote_op.position + remote_op.length)
            op.length -= max(0, overlap_end - overlap_start)
            if remote_op.position < op.position:
                op.position -= max(0, remote_op.length - max(0, op.position - remote_op.position))
            op.length = max(0, op.length)
    return op


class OTDocumentState:
    def __init__(self):
        self.version = 0
        self.history: List[TextOperation] = []

    def apply_operation(self, op: TextOperation) -> TextOperation:
        """Apply an operation to the document state and return the transformed op."""
        transformed = op
        for past in self.history[op.base_version:]:
            transformed = transform_operation(transformed, past)
        self.version += 1
        transformed.version = self.version
        self.history.append(transformed)
        return transformed

    def get_version(self) -> int:
        return self.version
