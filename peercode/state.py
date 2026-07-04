import json
import os
import threading

STATE_FILE = os.path.join(os.path.dirname(__file__), 'peercode_state.json')
_lock = threading.Lock()

DEFAULT_STATE = {
    "shared_todos": [],
    "shared_snippets": [],
    "shared_notes": "",
    "presenter": "",
    "edit_history": {},
}


def load_state():
    try:
        if not os.path.exists(STATE_FILE):
            return DEFAULT_STATE.copy()
        with _lock:
            with open(STATE_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
            # ensure keys
            for k, v in DEFAULT_STATE.items():
                if k not in data:
                    data[k] = v
            return data
    except Exception:
        return DEFAULT_STATE.copy()


def save_state(state):
    try:
        tmp = STATE_FILE + '.tmp'
        with _lock:
            with open(tmp, 'w', encoding='utf-8') as f:
                json.dump(state, f, ensure_ascii=False, indent=2)
            os.replace(tmp, STATE_FILE)
        return True
    except Exception:
        return False
