from __future__ import annotations

import importlib.util
import socket
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LAUNCHER = ROOT / "scripts" / "open_notebook_lm.py"


class PortHolder(threading.Thread):
    """Hold a local TCP port open long enough for launcher probes to see it."""

    def __init__(self, port: int, *, duration: float = 5.0) -> None:
        super().__init__(daemon=True)
        self.port = port
        self.duration = duration
        self.ready = threading.Event()
        self.stop_requested = threading.Event()
        self.error: Exception | None = None

    def run(self) -> None:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind(("127.0.0.1", self.port))
            sock.listen(5)
            sock.settimeout(0.2)
            self.ready.set()
            end = time.time() + self.duration
            while time.time() < end and not self.stop_requested.is_set():
                try:
                    conn, _addr = sock.accept()
                except socket.timeout:
                    continue
                else:
                    conn.close()
        except Exception as exc:  # pragma: no cover - surfaced in main thread
            self.error = exc
            self.ready.set()
        finally:
            sock.close()

    def stop(self) -> None:
        self.stop_requested.set()


def load_launcher_module():
    spec = importlib.util.spec_from_file_location("open_notebook_lm", LAUNCHER)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load launcher module: {LAUNCHER}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_port_probe(module) -> None:
    holder = PortHolder(5055)
    holder.start()
    if not holder.ready.wait(timeout=5):
        raise RuntimeError("test listener did not become ready")
    try:
        if holder.error:
            raise RuntimeError(f"test listener failed: {holder.error}")
        if not module.is_port_listening("127.0.0.1", 5055):
            raise RuntimeError("launcher port probe did not detect the held port")
    finally:
        holder.stop()
        holder.join(timeout=6)


def test_launcher_lock(module) -> None:
    module.DATA_ROOT.mkdir(exist_ok=True)
    lock_dir = module.DATA_ROOT / "launcher.lock"
    if lock_dir.exists():
        print(f"[skip] launcher lock test: {lock_dir} already exists.")
        return

    if not module.acquire_launcher_lock():
        raise RuntimeError("first launcher lock acquisition failed")
    try:
        if module.acquire_launcher_lock():
            raise RuntimeError("second launcher lock acquisition should have failed")
    finally:
        module.release_launcher_lock()

    if not module.acquire_launcher_lock():
        raise RuntimeError("launcher lock was not reusable after release")
    module.release_launcher_lock()


def test_required_markers() -> None:
    text = LAUNCHER.read_text(encoding="utf-8")
    markers = [
        "Open Notebook backend/API port 5055 is already listening; reusing it.",
        "Open Notebook frontend port 3000 is already listening; reusing it.",
        "Another launcher is already starting Open Notebook; waiting for it.",
        "setup_codex_mcp",
        "setup_hermes_mcp",
        "start_hermes",
    ]
    missing = [marker for marker in markers if marker not in text]
    if missing:
        raise RuntimeError("launcher is missing startup guard markers: " + ", ".join(missing))


def main() -> int:
    module = load_launcher_module()
    test_port_probe(module)
    test_launcher_lock(module)
    test_required_markers()
    print("Startup guard smoke tests passed.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {exc}")
        raise SystemExit(1)
