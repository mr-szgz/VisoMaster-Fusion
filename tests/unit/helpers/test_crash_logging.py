"""Exercise fatal diagnostics in a disposable process, never the test runner."""

import subprocess
import sys
from pathlib import Path


def test_native_crash_preserves_all_thread_stacks(tmp_path):
    project_root = Path(__file__).resolve().parents[3]
    entrypoint = tmp_path / "main.py"
    entrypoint.write_bytes((project_root / "main.py").read_bytes())
    script = """
import faulthandler
import importlib.abc
import runpy
import sys
import threading
from pathlib import Path
sys.path.insert(0, sys.argv[1])

ready = threading.Event()
stop = threading.Event()
def waiting_worker():
    ready.set()
    stop.wait()
worker = threading.Thread(target=waiting_worker)
worker.start()
ready.wait()
def trigger_native_fault():
    faulthandler._sigsegv()
class NativeImportFault(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path, target=None):
        if fullname == 'torch':
            trigger_native_fault()
sys.meta_path.insert(0, NativeImportFault())
runpy.run_path(str(Path(sys.argv[2]) / 'main.py'), run_name='__main__')
"""
    result = subprocess.run(
        [sys.executable, "-c", script, str(project_root), str(tmp_path)],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode != 0
    logs = list((tmp_path / "crash_logs").glob("native_*.log"))
    assert len(logs) == 1
    content = logs[0].read_text(encoding="utf-8")
    assert "Session started:" in content
    assert "PID:" in content
    assert "PySide6:" in content
    assert "torch:" in content
    assert "trigger_native_fault" in content
    assert "waiting_worker" in content
    assert "Current thread" in content


def test_sessions_keep_separate_logs(tmp_path):
    project_root = Path(__file__).resolve().parents[3]
    script = """
import faulthandler
import sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from app.helpers.crash_logging import enable_native_crash_logging
first = enable_native_crash_logging(Path(sys.argv[2]))
second = enable_native_crash_logging(Path(sys.argv[2]))
assert first.name != second.name
assert not first.closed and not second.closed
faulthandler.dump_traceback(file=second, all_threads=True)
faulthandler.disable()
first.close()
second.close()
"""
    result = subprocess.run(
        [sys.executable, "-c", script, str(project_root), str(tmp_path)],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    logs = list(tmp_path.glob("native_*.log"))
    assert len(logs) == 2
    assert all("Session started:" in log.read_text() for log in logs)
