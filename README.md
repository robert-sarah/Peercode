# PeerCode
PeerCode is a real-time collaborative extension for the ExCo editor, built with PyQt6 and QScintilla.

## Prerequisites
- Python 3.8+
- See the dependencies listed in [requirements.txt](requirements.txt)

## Installation
1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

## Usage
Run the application from the project root:
```bash
python main.py
```

## Features
1. **Session Host**: Start a server to share your editor with other users
2. **Session Client**: Join an existing PeerCode session via IP address and port
3. **Live Chat**: Communicate with other participants through the integrated chat
4. **Participants List**: View users currently connected to the session
5. **Text Synchronization**: Real-time updates of the editor content
6. **C++ Bridge (streaming)**: Skeleton for future video streaming integration (`stream_bridge.cpp`)

## Application Details

- Host a session:
   - Use the PeerCode panel inside ExCo to start a hosting session and share your editor with others.

- Join a session:
   - Use the PeerCode panel to join by entering the host's IP address and port.

- User interface:
   - PeerCode adds a side panel containing the participant list, chat window, and synchronization controls.
   - The editor content is synchronized in real-time between connected participants.

- Configuration & development notes:
   - Project dependencies are listed in `requirements.txt` (PyQt6, QScintilla, and others).
   - The networking logic is implemented in `peercode/network.py`; adjust defaults there if needed.
   - The C++ streaming bridge is a skeleton (`stream_bridge.cpp`) and is optional; the Python wrapper lives at `peercode/stream_bridge.py`.

- Logs & debugging:
   - Runtime messages are printed to the console when running `main.py` from the project root.

## Quick Start

- From the project root, install dependencies and run PeerCode inside ExCo (or run the standalone demo):

```bash
pip install -r requirements.txt
python main.py
```

- By default the application prints status and debug logs to the console. Use the ExCo UI to open the PeerCode panel.

## Running as Host

- Start a host session from the PeerCode panel in ExCo. The panel exposes a "Host" button and optional port field.

- Example (if you run headless or via script):

```python
# pseudo-code: start host via programmatic API (see peercode/integration.py)
from peercode import network
server = network.start_host(port=5000)
```

## Running as Client

- Use the PeerCode panel to enter the host IP and port and click "Join".

- Example (programmatic):

```python
from peercode import network
client = network.connect_to_host('192.168.1.10', 5000)
```

## Configuration

- Default networking options and ports live in `peercode/network.py`. To change behavior, edit the default constants or expose them in a config file.

Example minimal config (optional `peercode/config.py`):

```python
# example settings
HOST_PORT = 5000
MAX_CLIENTS = 8
SYNC_INTERVAL_MS = 100
```

## Building the C++ Bridge (optional)

- The `stream_bridge.cpp` file is a skeleton for a native module. To build a shared library on Windows (MSVC) or Linux (g++), adapt the headers and compile with your toolchain.

Example (Linux):

```bash
g++ -O2 -shared -fPIC stream_bridge.cpp -o libstream_bridge.so
```

Example (Windows, MSVC):

```powershell
# compile with cl.exe and create DLL (example; adapt paths)
cl /LD /O2 stream_bridge.cpp /Fe:stream_bridge.dll
```

- The Python wrapper at `peercode/stream_bridge.py` expects a simple C ABI and uses `ctypes` to load the shared library.

## Development & Testing

- Run `main.py` to perform manual tests. Unit tests are not included in the repository; add tests under `tests/` and use `pytest`.

- Recommended workflow for contributing changes:
   1. Create a feature branch.
   2. Run the application and verify the PeerCode panel shows up in ExCo.
   3. Add tests where applicable and run them locally.

## Contributing

- Contributions are welcome. Please follow these guidelines:
   - Open an issue describing the feature or bug.
   - Create a branch named `feature/<short-description>` or `fix/<short-description>`.
   - Submit a pull request with a clear description and small, focused changes.

## Troubleshooting

- Cannot start host: check that the chosen port is free and not blocked by firewall.
- Clients cannot connect: confirm host IP is reachable and the host allowed incoming connections.
- Slow sync: reduce `SYNC_INTERVAL_MS` or increase network buffer sizes.

## FAQ

- Q: Does PeerCode modify ExCo core files?
   - A: No — PeerCode integrates with ExCo via the provided integration points and should not alter the ExCo source tree.

## Contact

- For issues and questions, open an issue in this repository or contact the maintainer listed in the project metadata.

## Project Structure
```
PeerCode/
├── ExCo-master/          # Original ExCo source (unchanged)
├── peercode/             # PeerCode module
│   ├── __init__.py
│   ├── integration.py    # Integration with ExCo
│   ├── network.py        # Network handling (host/client)
│   ├── ui.py             # User interface (side panel)
│   └── stream_bridge.py  # Python/C++ bridge for streaming
├── main.py               # Main entry point for PeerCode
├── requirements.txt      # Project dependencies
├── stream_bridge.cpp     # C++ skeleton module for streaming
└── README.md             # This file
```

## C++ Bridge (streaming)
The file [stream_bridge.cpp](stream_bridge.cpp) contains a skeleton for a high-performance C++ module intended for video capture and streaming. It is expected to be compiled as a DLL/SO and used from Python via `ctypes` in the wrapper at `peercode/stream_bridge.py`.

## License
This project is based on ExCo, which is licensed under the GNU GPLv3. See [ExCo-master/LICENSE.txt](ExCo-master/LICENSE.txt) for details.
