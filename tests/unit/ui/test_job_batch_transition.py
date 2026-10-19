"""Real Qt job transitions without GPU inference or workspace asset loading."""
import os
from pathlib import Path
import subprocess
import sys
import textwrap


def test_job_transition_and_final_report(tmp_path):
    script = textwrap.dedent('''
        from contextlib import ExitStack
        from pathlib import Path
        import sys
        import time
        from unittest.mock import MagicMock, patch
        from PySide6 import QtCore, QtWidgets, QtTest
        from app.ui.widgets.actions import job_manager_actions as actions
        from app.ui.widgets import job_progress_dialog
        from app.ui.widgets.job_list_widgets import JobDataRole as Role

        app = QtWidgets.QApplication([])
        root = Path(sys.argv[1])
        class Video(QtCore.QObject):
            processing_started_signal = QtCore.Signal()
            processing_stopped_signal = QtCore.Signal()
            processing_heartbeat_signal = QtCore.Signal()
            frame_processed_signal = QtCore.Signal()

        for fail_second in (False, True):
            window = QtWidgets.QMainWindow()
            window.project_root_path = root / str(fail_second)
            jobs = window.project_root_path / "jobs"
            jobs.mkdir(parents=True)
            window.video_processor = Video(window)
            window.jobQueueList = QtWidgets.QListWidget(window)
            window.jobQueueList.setSortingEnabled(True)
            window.job_marker_pairs = []
            window.job_progress_dialog = None
            window.job_processing_button = None
            for name in ("buttonProcessAll", "buttonProcessSelected", "buttonStopProcessing", "loadJobButton", "deleteJobButton", "smartJobListButton"):
                setattr(window, name, QtWidgets.QPushButton(name, window))
            items = {}
            for name in ("A", "B", "C"):
                (jobs / f"{name}.json").write_text("{}")
                item = QtWidgets.QListWidgetItem(name)
                for role, value in ((Role.JobNameRole, name), (Role.FrameCountRole, 1),
                                    (Role.FrameRateRole, 0.0), (Role.EmbeddingNamesRole, [])):
                    item.setData(role, value)
                window.jobQueueList.addItem(item)
                items[name] = item
            window.jobQueueList.setCurrentItem(items["C"])
            events = []
            reports = []
            def analyze(worker):
                worker.job_data_list = [{"job_name_internal": name} for name in worker.jobs]
                return {}
            def assets(mw, data):
                events.append("assets")
                mw.job_processor.master_assets_loaded_event.set()
            def load(mw, data):
                name = data["job_name_internal"]
                events.append("load " + name)
                if name == "B":
                    assert events == ["assets", "load A", "clear", "load B"]
                    assert mw.jobQueueList.count() == 2
                    assert mw.jobQueueList.item(0) is items["B"]
                    assert mw.jobQueueList.currentItem() is items["C"]
                mw.job_processor.job_settings_loaded_event.set()
            def process(worker, name):
                if fail_second and name == "B":
                    worker.job_failed_signal.emit(name, "test processing failure")
                    return False
                return True
            def clear_faces(mw):
                assert mw._batch_update_in_progress is True
                events.append("clear")
            def restore(mw, snapshot):
                assert not mw.job_processor.isRunning()
                events.append("restore")
            def report(dialog):
                assert events[-1] == "restore"
                reports.append((dialog.windowTitle(), dialog.findChild(QtWidgets.QPlainTextEdit).toPlainText()))
                return QtWidgets.QDialog.Accepted
            def settings(namespace, parent):
                result = QtCore.QSettings(str(root / "settings.ini"), QtCore.QSettings.IniFormat, parent)
                result.beginGroup(namespace)
                return result
            with ExitStack() as stack:
                for target, name, value in (
                    (actions, "_serialize_job_data", MagicMock(return_value={"snapshot": True})),
                    (actions, "_restore_workspace_from_snapshot", restore),
                    (actions.JobProcessor, "_analyze_job_batch", analyze),
                    (actions.JobProcessor, "_trigger_and_wait_for_processing", process),
                    (actions, "load_master_assets", assets),
                    (actions, "load_job_settings", load),
                    (actions.card_actions, "clear_target_faces", clear_faces),
                    (actions.video_control_actions, "remove_all_markers", MagicMock()),
                    (job_progress_dialog, "settings_group", settings),
                    (QtWidgets.QDialog, "exec", report),
                ):
                    stack.enter_context(patch.object(target, name, value))
                full_refresh = stack.enter_context(patch.object(actions, "refresh_job_list"))
                critical = stack.enter_context(patch.object(actions.QMessageBox, "critical"))
                actions.start_job_processor(window, ["A", "B"])
                worker = window.job_processor
                deadline = time.monotonic() + 10
                while window.job_processor is not None and time.monotonic() < deadline:
                    QtTest.QTest.qWait(10)
                assert window.job_processor is None
                assert worker.wait(1000)
                assert events == (["assets", "load A", "clear", "load B", "restore"] if fail_second
                                  else ["assets", "load A", "clear", "load B", "clear", "restore"])
                assert len(reports) == 1
                assert reports[0][0] == ("Job Processing Failed" if fail_second else "Job Processing Complete")
                assert ("B: test processing failure" in reports[0][1]) == fail_second
                assert window.jobQueueList.count() == (2 if fail_second else 1)
                assert window.jobQueueList.currentItem() is items["C"]
                assert (jobs / "completed" / "A.json").is_file()
                assert (jobs / "completed" / "B.json").is_file() == (not fail_second)
                full_refresh.assert_not_called()
                critical.assert_not_called()
            window.close()
            window.deleteLater()
            app.processEvents()
    ''')
    result = subprocess.run(
        [sys.executable, "-u", "-c", script, str(tmp_path)],
        cwd=Path(__file__).resolve().parents[3],
        env={**os.environ, "QT_QPA_PLATFORM": "offscreen"},
        capture_output=True, text=True, timeout=90,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "Traceback" not in result.stderr, result.stderr
