"""Persistent Python thread stacks for native process crashes."""

import faulthandler
import os
import sys
from datetime import datetime
from importlib.metadata import version
from pathlib import Path
from typing import BinaryIO


def enable_native_crash_logging(log_dir: Path) -> BinaryIO:
    """Enable fatal-fault diagnostics; the caller must keep the file open."""
    log_dir.mkdir(parents=True, exist_ok=True)
    started = datetime.now().astimezone()
    log_path = log_dir / f"native_{started:%Y%m%d_%H%M%S_%f}_{os.getpid()}.log"
    # Keep writes independent of Python's buffered stream cleanup on a crash.
    log_file = log_path.open("xb", buffering=0)
    faulthandler.enable(file=log_file, all_threads=True)
    header = (
        "VisoMaster native crash diagnostics\n"
        f"Session started: {started.isoformat()}\n"
        f"PID: {os.getpid()}\n"
        f"Executable: {sys.executable}\n"
        f"Python: {sys.version}\n"
        f"PySide6: {version('PySide6')}\n"
        f"torch: {version('torch')}\n"
        "A header-only file means no fatal traceback was captured.\n"
        "Fatal tracebacks below list Python files, functions and line numbers "
        "for the current and other Python threads.\n\n"
    )
    log_file.write(header.encode("utf-8"))
    print(f"Native crash diagnostics: {log_path}", flush=True)
    return log_file
