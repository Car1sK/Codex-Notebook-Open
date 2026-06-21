from __future__ import annotations

import os
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA_ROOT = ROOT / "open-notebook-data"
START_BAT = ROOT / "start_open_notebook.bat"


class PortHolder(threading.Thread):
    """Hold a local TCP port open long enough for batch startup guards to probe it."""

    def __init__(self, port: int, *, delay: float = 0.0, duration: float = 5.0) -> None:
        super().__init__(daemon=True)
        self.port = port
        self.delay = delay
        self.duration = duration
        self.ready = threading.Event()
        self.stop_requested = threading.Event()
        self.error: Exception | None = None

    def run(self) -> None:
        time.sleep(self.delay)
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


def is_port_open(port: int) -> bool:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(0.5)
    try:
        sock.connect(("127.0.0.1", port))
    except OSError:
        return False
    finally:
        sock.close()
    return True


def run_subcommand(target: str, timeout: int = 25) -> str:
    result = subprocess.run(
        ["cmd.exe", "/d", "/c", "call", str(START_BAT), target],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        check=False,
    )
    output = (result.stdout + result.stderr).strip()
    if result.returncode != 0:
        raise RuntimeError(f"{target} returned {result.returncode}:\n{output}")
    return output


def assert_contains(output: str, marker: str) -> None:
    if marker not in output:
        raise RuntimeError(f"missing marker {marker!r} in output:\n{output}")


def test_existing_port_reuse(target: str, port: int, marker: str) -> None:
    holder: PortHolder | None = None
    if not is_port_open(port):
        holder = PortHolder(port, duration=5.0)
        holder.start()
        if not holder.ready.wait(timeout=5):
            raise RuntimeError(f"test listener for port {port} did not become ready")
        if holder.error:
            raise RuntimeError(f"test listener for port {port} failed: {holder.error}")

    output = run_subcommand(target)
    assert_contains(output, marker)

    if holder:
        holder.stop()
        holder.join(timeout=6)


def test_startup_lock_wait(target: str, port: int, lock_name: str, wait_marker: str, done_marker: str) -> None:
    if is_port_open(port):
        print(f"[skip] {target} lock-wait case: port {port} is already in use.")
        return

    DATA_ROOT.mkdir(exist_ok=True)
    lock_dir = DATA_ROOT / lock_name
    if lock_dir.exists():
        print(f"[skip] {target} lock-wait case: {lock_dir} already exists.")
        return

    lock_dir.mkdir()
    holder = PortHolder(port, delay=1.0, duration=6.0)
    try:
        holder.start()
        output = run_subcommand(target)
        assert_contains(output, wait_marker)
        assert_contains(output, done_marker)
        if holder.error:
            raise RuntimeError(f"test listener for port {port} failed: {holder.error}")
    finally:
        holder.stop()
        holder.join(timeout=7)
        try:
            lock_dir.rmdir()
        except FileNotFoundError:
            pass


def main() -> int:
    if os.name != "nt":
        print("[skip] startup guard smoke tests are Windows batch tests.")
        return 0

    if not START_BAT.is_file():
        raise RuntimeError(f"missing launcher: {START_BAT}")

    test_existing_port_reuse(
        "backend",
        5055,
        "Backend/API is already running on port 5055; no new backend started.",
    )
    test_existing_port_reuse(
        "frontend",
        3000,
        "Frontend is already running on port 3000; no new frontend started.",
    )
    test_startup_lock_wait(
        "backend",
        5055,
        "backend.lock",
        "Another backend start is already in progress; waiting for port 5055.",
        "Backend/API is already running on port 5055; no new backend started.",
    )
    test_startup_lock_wait(
        "frontend",
        3000,
        "frontend.lock",
        "Another frontend start is already in progress; waiting for port 3000.",
        "Frontend is already running on port 3000; no new frontend started.",
    )

    print("Startup guard smoke tests passed.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
