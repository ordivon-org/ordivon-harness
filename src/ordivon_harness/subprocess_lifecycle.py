from __future__ import annotations

from contextlib import suppress
import subprocess
import threading


def close_owned_process(
    process: subprocess.Popen[str] | None,
    *,
    reader_threads: tuple[threading.Thread, ...] = (),
    graceful_timeout_seconds: float = 3.0,
) -> None:
    """Bounded, idempotent cleanup for a Harness-owned Provider subprocess."""

    if process is None:
        return
    if process.poll() is None:
        with suppress(OSError):
            process.terminate()
        try:
            process.wait(timeout=graceful_timeout_seconds)
        except subprocess.TimeoutExpired:
            with suppress(OSError):
                process.kill()
            with suppress(subprocess.TimeoutExpired):
                process.wait(timeout=graceful_timeout_seconds)
    for stream in (process.stdin, process.stdout, process.stderr):
        if stream is not None:
            with suppress(OSError, ValueError):
                stream.close()
    for thread in reader_threads:
        if thread is not threading.current_thread():
            thread.join(timeout=graceful_timeout_seconds)
